#!/usr/bin/env python3
"""Ask finished panellists a follow-up question, each in the session it reviewed in.

Usage:
  followup.py <study-dir> ask --runs <ids> --question-file <file> [--skip-unfit]
  followup.py <study-dir> ask --runs all --question-file <file>   # every finished panellist run
  followup.py <study-dir> ask --runs <ids>|all --question-file <file> --dry-run
                                                                  # what it would ask and cost
  followup.py <study-dir> list [--json]                           # the questions asked, and how
                                                                  # each run answered (settles
                                                                  # what a killed launcher left)

One "ask" is one follow-up: the question in the file, sent to every run named, under the next
number of the study. Each panellist appends a "## Follow-up <n>" section to its own persona file
and replies with its answer. followups.json records the question, the time, and for each run how
it went (format in panel_lib.py).

The rule: a follow-up never reveals another panellist's answer, a result, or what the team hopes
to hear. Ask what a moderator could ask one participant who has seen nothing but the materials.

What it does, on a study that runs through runners:
- It goes through launch.py's supervisor. A follow-up is one more attempt on the run, of kind
  "followup": the run's session is resumed through its runner, under the study lock and a
  watchdog, within the runner's concurrency. Like launch.py it stays in the foreground until the
  processes have ended, and "launch.py <study-dir> stop" stops it.
- Only a run that can be asked is asked: a panellist run that is done, with a recorded session
  that was saved and not purged or lost, on a runner that can resume, whose CLI is ready, can
  do a run from this shell and can still launch the run's model entry (launch.fitness: what
  stops "plan" and "run" stops a follow-up, such as a model no longer listed, a provider no
  longer signed in or a sandboxed shell tool that the CLI cannot work in). Every other
  run named gets a line saying why, before anything is recorded or started, and then nothing is
  asked at all, unless --skip-unfit, which asks the rest. Analyst and writer jobs cannot be
  asked. To put a question to a run that could not be reached, ask again: it becomes the next
  follow-up.
- The question is sent word for word, inside a fixed frame (assets/followup-message.md) that says
  what a follow-up is and what the panellist may do. An empty question file is refused. A run of
  a usability study gets the frame assets/usability-followup-message.md and no browser session:
  its test account is gone, so it answers from what it saw, its step log and its screenshots.
- Each run has limits.followup for each question, 5 minutes and $0.50 unless study.json says
  otherwise, apart from the run's own limits. Before anything starts, the number of runs and
  the most they can use are printed. That spend is outside the plan's ceiling.
- --dry-run prints what "ask" prints before it starts, and stops: the follow-up's number, the
  runs it would ask and the ones that cannot be asked, each run's allowance, the most they can
  use between them and whether each harness enforces that cap. It starts no run, takes no
  lock and writes nothing to the study (a runner's sign-in check may let its harness refresh
  its own login). Show it to the user first when a ceiling was agreed.
- Scores never change. The persona file is copied before the question. When the process has
  ended the file must be that copy plus the one appended section, with no other heading in it,
  and its scores, ranking and sections must read as before. Otherwise the follow-up is
  "rejected": the file is put back from the copy and what the panellist left is kept in
  logs/<run id>.<attempt>.rejected.md. A file that can no longer be read as the run's own (a
  symbolic link at its name, say) is rejected too, and nothing is read or written through the
  link. A panellist that replied without writing has its section written from the reply, marked
  as such. The run stays done throughout.
- Until a launcher has settled a follow-up, nothing reads the persona file for scores or
  progress: status, the extract scripts and check_runs.py read the copy made before the
  question, and say so in a line for each such run. So do not analyse while a question is out.
- A killed "ask" loses nothing. The next launcher command, "ask" or "list" settles what its
  processes left, to the same outcome the killed one would have recorded, and records the runs
  it had not reached as "not asked". Ask those again: it becomes the next follow-up.
- No script tallies the answers. They are qualitative evidence: the analysts' briefs name the
  follow-ups asked, so ask before "launch.py run --role analyst".

On a native-mode study nothing is sent: "ask" prints the message for each run, for you to send
to its recorded subagent, and records the follow-up as sent by hand. Nothing is checked there,
so compare analysis/scores.csv before and after if the answer matters.

An interview study is refused in one line, by "ask" and "list" alike: an interview that has
ended is closed, and a new question belongs in the next round's guide.

Exit code of "ask": 0 when every run asked has its section, 1 otherwise.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import launch  # noqa: E402
import launch_plan as planning  # noqa: E402
import panel_lib as pl  # noqa: E402
import runners  # noqa: E402

# What a panellist is sent: the question, word for word, inside the frame for its type of study.
MESSAGE = {"review": "followup-message.md", "usability": "usability-followup-message.md"}
DRY_RUN = "Dry run: nothing was asked and nothing was recorded. Leave out --dry-run to ask."

say, agree, plural = launch.say, pl.agree, pl.plural


def message(number: int, question: str, file: Path, study: str = "review") -> str:
    """The message that puts follow-up question `number` to the panellist whose persona file is
    file: assets/followup-message.md with its placeholders filled, or for a run of a usability
    study assets/usability-followup-message.md, which says that its browser and its test account
    are gone."""
    return pl.fill_brief(MESSAGE[study], {"NUMBER": number, "QUESTION": question, "PERSONA_FILE": file})


def read_question(path: str | None) -> str:
    if not path:
        raise SystemExit("ask needs --question-file <file>: a text file that holds the question.")
    try:
        question = Path(path).read_text().strip()
    except OSError as err:
        raise SystemExit(f"Cannot read the question file {path} ({err.strerror}).")
    if not question:
        raise SystemExit(f"The question file {path} is empty: write the question in it.")
    return question


def next_number(cfg: dict) -> int:
    """The number of the next follow-up: one past the highest in followups.json. A number that a
    persona file already uses in a heading is passed over too, so a section nobody recorded is
    never taken for an answer."""
    sd = cfg["_dir"]
    used = [f["n"] for f in pl.read_followups(sd) if isinstance(f.get("n"), int)]
    used += [f["n"] for r in pl.load_runs(sd, cfg) for f in r["followups"]]
    return max(used, default=0) + 1


def cannot_ask(cfg: dict, e: dict) -> str | None:
    """Why a run cannot be asked a follow-up question whatever its runner says of its CLI and its
    model, in a clause, or None. choose() then asks the runner."""
    if e["role"] != "panellist":
        job = "an analyst" if e["role"] == "analyst" else "the writer"
        return f"it is {job} job, and only a panellist run can be asked"
    state = launch.state_of(cfg, e)
    if launch.in_flight(e):
        return "a process of it is still running"
    if state != "done":
        return (f"it is {state}, and only a finished run can be asked: a question to an unfinished run would be "
                "taken for its resume")
    if e["runner"] is None:  # native mode: the lead sends the message, to the subagent runs.py mark recorded
        return None if e.get("agent") else "no subagent id was recorded for it (runs.py mark)"
    session = e.get("session")
    if not session:
        return "no session was recorded for it"
    if session in (e.get("purged") or {}):
        return "its session was purged (purge-sessions)"
    if session in (e.get("lost") or {}):
        return launch.LOST
    if session in (e.get("unsaved") or {}):  # its harness kept none: there is nothing to resume
        return launch.NOT_SAVED
    if not runners.get(e["runner"]).capabilities()["resume"]:
        return f"{e['runner']} cannot resume a session"
    return None


def choose(cfg: dict, runs: list[dict], named: str | None, skip_unfit: bool) -> list[dict]:
    """The runs to ask: the ones --runs names, or with "all" every panellist run that is done.
    Says why each run named cannot be asked, and exits unless every one can or skip_unfit. A run
    that could be asked is then judged as "run" and "resume" judge the runs they start
    (launch.fitness): its runner's CLI can be used, and its model entry is one the runner can
    still launch, signed in."""
    if not named or not named.strip():
        raise SystemExit("ask needs --runs <ids>, comma-separated, or --runs all for every finished panellist run.")
    known = {e["run"]: e for e in runs}
    if named.strip() == "all":
        ids = [e["run"] for e in runs if e["role"] == "panellist" and launch.state_of(cfg, e) == "done"]
        if not ids:
            raise SystemExit("No panellist run of this study is done, so there is no one to ask.")
    else:
        ids = list(dict.fromkeys(x.strip() for x in named.split(",") if x.strip()))
    why_not = {run_id: cannot_ask(cfg, known[run_id]) if run_id in known else "this study has no run of that name"
               for run_id in ids}
    unusable, errors, _ = launch.fitness(cfg, [known[i] for i in ids if not why_not[i] and known[i]["runner"]])
    fit, unfit = [], []
    for run_id in ids:
        runner = known[run_id]["runner"] if run_id in known else None
        why = why_not[run_id] or (
            f"{runner} cannot be used: {unusable[runner].strip().rstrip('.')}" if runner in unusable
            else "; ".join(error.strip().rstrip(".") for error in errors.get(run_id, [])))
        if why:
            unfit.append(f"{run_id}: {'skipped' if skip_unfit else 'cannot be asked'}: {why}.")
        else:
            fit.append(known[run_id])
    if unfit:
        say(*unfit)
    if unfit and not skip_unfit:
        raise SystemExit("Nothing was asked: every run named has to be one that can be asked. Take the runs above "
                         "out of --runs, or pass --skip-unfit to ask the others.")
    if not fit:
        raise SystemExit("Nothing was asked: no run named can be asked.")
    return fit


def allowance_lines(cfg: dict, fit: list[dict]) -> list[str]:
    """What the runs about to be asked may use between them, and whether each harness enforces it."""
    limits = pl.limits_for(cfg, "followup")
    capped, loose = {}, {}  # runner -> its runs, by whether its harness enforces a budget cap
    for e in fit:
        group = capped if runners.get(e["runner"]).capabilities()["budget_cap"] else loose
        group.setdefault(e["runner"], []).append(e)
    out = [f"  {agree(len(fit), 'It', 'Each')} has up to {limits['minutes']:g} min and "
           f"{planning.money(limits['budget_usd'])} for this question (limits.followup), apart from its run limits"
           + agree(len(fit), ".", f": at most {planning.span(limits['minutes'] * 60 * len(fit))} of run time "
                               "between them.")]
    n = sum(map(len, capped.values()))
    if n:
        out.append(f"  At most {planning.money(limits['budget_usd'] * n)} for the {plural(n, 'run')} on "
                   f"{planning.listed(list(capped))}, whose harness enforces the cap.")
        out += [f"  On {name}, {planning.stop(note)}" for name in capped
                for note in [runners.get(name).capabilities()["budget_cap_note"]] if note]
    n = sum(map(len, loose.values()))
    if n:
        out.append(f"  No budget cap for the {plural(n, 'run')} on {planning.listed(list(loose))}: the harness "
                   f"enforces none, so the time limit is what bounds {agree(n, 'it', 'them')}.")
    out.append("  This is outside the plan's ceiling.")
    return out


def opening(number: int, fit: list[dict], dry_run: bool = False) -> str:
    """The line that names a follow-up and the runs it is put to."""
    return (f"Follow-up {number}: {'would ask' if dry_run else 'asking'} {plural(len(fit), 'run')} "
            f"({', '.join(e['run'] for e in fit)}).")


def by_hand(cfg: dict, runs: list[dict], args, question: str) -> int:
    """ask, on a native-mode study: print each run's message for the lead to send, and record the
    follow-up as sent by hand."""
    sd = cfg["_dir"]
    fit, number = choose(cfg, runs, args.runs, args.skip_unfit), next_number(cfg)
    if args.dry_run:
        say(opening(number, fit, dry_run=True), "  Native mode: a message for each is printed for you to send to its "
            "subagent. Nothing is sent, limited or checked.", DRY_RUN)
        return 0
    for e in fit:
        say(f"=== {e['run']} (subagent: {e['agent']})", message(number, question, sd / e["file"]))
    pl.write_followups(sd, [*pl.read_followups(sd), {
        "n": number, "question": question, "asked": round(time.time()), "mode": "native",
        "runs": [{"run": e["run"], "outcome": "sent by hand", "reason": None, "attempt": None, "session": e["agent"]}
                 for e in fit]}])
    say(f"Follow-up {number}: {plural(len(fit), 'message')} to send. Native mode: nothing was sent and nothing is "
        "enforced. Send each message above to the subagent named, with your harness's tool for messaging a "
        f"subagent. It is recorded in {pl.FOLLOWUPS} as sent by hand. No script checks what a panellist then does "
        "to its file: a follow-up must only append its section, so compare analysis/scores.csv before and after.")
    return 0


def ask(args, cfg: dict) -> int:
    sd, question = cfg["_dir"], read_question(args.question_file)
    if all(e["runner"] is None for e in pl.read_runs(sd)):
        return by_hand(cfg, pl.read_runs(sd), args, question)
    if args.dry_run:  # the same choice and the same lines as below, with no lock, no supervisor and no record
        fit, held = choose(cfg, pl.read_runs(sd), args.runs, args.skip_unfit), launch.Lock.holder(sd)
        say(opening(next_number(cfg), fit, dry_run=True), *allowance_lines(cfg, fit),
            *([f'  A launcher is running "{held.get("command")}" on this study (pid {held["pid"]}): "ask" is '
               "refused until it has ended."] if held else []), DRY_RUN)
        return 0
    stop = launch.StopSignal()
    stop.listen()
    lock = launch.Lock(sd)
    lock.acquire("followup", args.grace)
    try:
        runs = pl.read_runs(sd)
        sup = launch.Supervisor(cfg, runs, args.grace, args.poll, stop=stop)
        sup.reconcile()  # an earlier follow-up that no launcher lived to settle is settled first
        fit, number = choose(cfg, runs, args.runs, args.skip_unfit), next_number(cfg)
        sup.question = {"n": number, "message": lambda e: message(number, question, sd / e["file"], cfg["type"])}
        say(opening(number, fit), *allowance_lines(cfg, fit))
        pl.write_followups(sd, [*pl.read_followups(sd), {
            "n": number, "question": question, "asked": round(time.time()), "mode": "runner",
            "limits": pl.limits_for(cfg, "followup"),
            "runs": [{"run": e["run"], "outcome": None, "reason": None, "attempt": None, "session": e["session"]}
                     for e in fit]}])
        sup.queue += [(e, "followup") for e in fit]
        sup.supervise()
        for e in fit:  # a run whose turn never came: the command was stopped, or its runner closed
            if recorded(sd, number)[e["run"]]["outcome"] is None:
                pl.record_followup(sd, number, e["run"], outcome="not asked", reason=(
                    f"{e['runner']}: {sup.closed[e['runner']]}" if e["runner"] in sup.closed
                    else "the command was stopped before its turn came"))
        outcomes = {run: r["outcome"] for run, r in recorded(sd, number).items()}
        say(f"Follow-up {number}: " + ", ".join(
            f"{o} {list(outcomes.values()).count(o)}" for o in pl.FOLLOWUP_OUTCOMES if o in outcomes.values()) + ".")
        for outcome in (o for o in pl.FOLLOWUP_OUTCOMES if o in outcomes.values() and o not in pl.FOLLOWUP_ANSWERED):
            say(f"  {outcome}: {', '.join(run for run, o in outcomes.items() if o == outcome)}.")
        say("No score was changed." + (
            f" The answers are under `## Follow-up {number}` at the end of each persona file."
            if set(outcomes.values()) & set(pl.FOLLOWUP_ANSWERED) else "") + f" followup.py {sd} list shows how "
            "each run went.")
        return 0 if set(outcomes.values()) <= set(pl.FOLLOWUP_ANSWERED) else 1
    finally:
        lock.release()


def recorded(sd: Path, number: int) -> dict[str, dict]:
    """{run id: its record} under one follow-up of followups.json."""
    return {r["run"]: r for f in pl.read_followups(sd) if f.get("n") == number for r in f.get("runs") or []}


def settle(cfg: dict):
    """Before the follow-ups are listed: settle what a launcher that was killed left unsettled,
    as the next launcher command would (Supervisor.reconcile). Only when a record has no outcome
    and no launcher has the study: with one alive, the record is its own to settle. Processes
    still at work are left to the next launcher, and nothing is settled from a shell that has
    no way to see one of them (launch.Lock.acquire()). What it says goes to stderr, apart from
    the list. An archive has no logs/ and is left as it is."""
    sd = cfg["_dir"]
    unsettled = any(r.get("outcome") is None for f in pl.read_followups(sd) if f.get("mode") != "native"
                    for r in f.get("runs") or [])
    if not (unsettled and (sd / "logs").is_dir() and (sd / "runs.json").exists()):
        return
    with contextlib.redirect_stdout(sys.stderr):
        lock = launch.Lock(sd)
        if not lock.acquire("followup list", 0, must=False):
            return
        try:
            launch.Supervisor(cfg, pl.read_runs(sd), grace=10.0, poll=1.0).reconcile(adopt=False)
        finally:
            lock.release()


def list_asked(args, cfg: dict) -> int:
    settle(cfg)
    asked = pl.read_followups(cfg["_dir"])
    if args.json:
        print(json.dumps(asked, indent=2))
        return 0
    if not asked:
        print("No follow-up question has been asked in this study.")
    for f in asked:
        runs = f.get("runs") or []
        when = launch.clock(f["asked"]) if f.get("asked") else "at a time not on record"
        print(f"Follow-up {f['n']}, asked {when} of {plural(len(runs), 'run')}"
              + (", sent by hand (native mode):" if f.get("mode") == "native" else ":"))
        print(*(f"  > {line}".rstrip() for line in (f.get("question") or "(not on record)").split("\n")), sep="\n")
        for r in runs:
            print(f"  {r['run']:<16} {r.get('outcome') or 'queued or with the panellist'}"
                  + (f": {r['reason']}" if r.get("reason") else ""))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("cmd", choices=["ask", "list"])
    ap.add_argument("--runs", help='ask: comma-separated panellist run ids, or "all" for every finished one')
    ap.add_argument("--question-file", metavar="FILE", help="ask: a text file holding the question, sent word for word")
    ap.add_argument("--skip-unfit", action="store_true",
                    help="ask: leave out the runs named that cannot be asked, and ask the others")
    ap.add_argument("--dry-run", action="store_true",
                    help="ask: print the runs it would ask and the most they can use, and stop. No run is "
                         "started and nothing is written to the study")
    ap.add_argument("--grace", type=float, default=10.0, metavar="SECONDS",
                    help="how long a process gets to finish its write after SIGTERM, before SIGKILL (default 10)")
    ap.add_argument("--poll", type=float, default=1.0, metavar="SECONDS",
                    help="how often to look for processes that have ended and for a request to stop (default 1)")
    ap.add_argument("--json", action="store_true", help="list: followups.json as it is")
    args = ap.parse_args()
    cfg = pl.load_study(args.study_dir)
    if cfg["type"] == "interview":
        raise SystemExit("An interview that has ended is closed, so an interview study takes no follow-up question: "
                         "a new question belongs in the next round's guide.")
    sys.exit({"ask": ask, "list": list_asked}[args.cmd](args, cfg))


if __name__ == "__main__":
    main()
