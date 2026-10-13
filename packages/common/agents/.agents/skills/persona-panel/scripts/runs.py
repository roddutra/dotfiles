#!/usr/bin/env python3
"""Track panel runs: which are done, in progress or pending, and what to launch next.

A run is "done" when its persona file is complete for the study type (panel_lib.run_progress:
a scored section for every concept, or for every task of a usability study, and the final "Out
of character" section); "started" when it has at least one section.

Usage:
  runs.py <study-dir> status
  runs.py <study-dir> next [--limit 20] [--running P01-opus,P02-fable]   # prompts to launch now
  runs.py <study-dir> prompt <run-id>                                    # the run's launch prompt
  runs.py <study-dir> mark <run-id> <agent-id>                           # record the subagent id
  runs.py <study-dir> resume [<run-id>]                                  # messages to resume runs

Record each subagent id with "mark" as soon as you launch it. runs.json survives context
compaction, so an interrupted run (usage limit, crash) can be resumed by messaging the same
subagent instead of relaunched, which would duplicate sections or lose its reading.

"next", "mark" and "resume" are for native mode, where the lead starts each run with its own
subagent tool. A study whose model entries name a runner is started, tracked and resumed by
launch.py, and these three commands refuse it.

A usability study always runs through launch.py. Its resume message (usability_resume) names
the tasks already written and the tasks left, says that the browser was restarted and whether
the test account is the same one or a new one, and tells a task that was under way when the run
was cut off to start again from its start page as a new attempt in the step log, with the
attempt's number. The number is the launcher's to give (issue_attempts()): it is on the run's
entry in runs.json before the message is made, and an entry of the step log that carries any
other counts for nothing.

A follow-up question to a finished run goes through followup.py in either mode. In native mode
it prints the message for you to send to the subagent that "mark" recorded.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402


def run_view(sd: Path, cfg: dict, r: dict) -> dict:
    """A runs.json entry with how far its persona file has got: "state" (done, started or
    pending), "scored", "of", "written", "unscored" (the sections written without a score row,
    which count for nothing until they have one), "has_final" and "unsettled" (the file was read
    as it stood before a follow-up that is not settled: panel_lib.read_persona)."""
    parsed = pl.read_persona(sd, cfg, sd / r["file"], r)
    prog = pl.run_progress(cfg, parsed)
    state = "done" if prog["complete"] else "started" if prog["written"] else "pending"
    return {**r, "state": state, "scored": len(prog["scored"]), "of": len(prog["units"]),
            "written": prog["written"], "unscored": [u for u in prog["written"] if u not in prog["scored"]],
            "has_final": prog["has_final"],
            "unsettled": bool(parsed and parsed["unsettled"])}


def run_states(sd: Path, cfg: dict) -> list[dict]:
    return [run_view(sd, cfg, r) for r in pl.read_runs(sd) if r["role"] == "panellist"]


def resume_message(cfg: dict, s: dict) -> str:
    """What a run that was cut off is told when it is continued in its session. A section written
    without its score row is named, with the one thing to add to it: told only not to rewrite
    what it has written, a run never adds the row, and so is never done."""
    unit, units = pl.unit_nouns(cfg)
    if cfg["type"] == "usability":
        return usability_resume(cfg, s)
    if s["state"] == "pending":
        return (f"Your run was interrupted before any {unit} was written. Start again from step 1 of your "
                "original instructions.")
    written = f"Already written: {', '.join(s['written'])}. Do not rewrite or repeat those sections."
    unscored, left = s["unscored"], s["of"] - len(s["written"])
    rest = (f"review the remaining {units} in your listed order, append each section as you finish it, then append "
            "the final sections.")
    if s["of"] == 1 and unscored:  # one unit, written without its score row: there is nothing else to go on to
        steps = [f"Your {unit} section is started, and has no score table yet.",
                 "Re-read your persona file, complete that section where it stops without repeating what is "
                 "there, then append the final sections."]
    elif unscored:
        n = len(unscored)
        steps = [written,
                 f"Written, but with no score row: {', '.join(unscored)}. Without that row "
                 f"{pl.agree(n, 'the section does', 'those sections do')} not count. Re-read your persona file and add "
                 f"the score table at the end of {pl.agree(n, 'that section', 'each of those sections')}, as the "
                 f"template sets it out. Change nothing else in {pl.agree(n, 'it', 'them')}.",
                 "Then " + (rest if left else "append the final sections." if not s["has_final"] else
                            "nothing else is left: your final sections are written, so do not repeat them.")]
    elif s["scored"] == s["of"] and not s["has_final"]:
        steps = [written, pl.agree(s["of"], f"Your {unit} section is written.", f"All {unit} sections are written.")
                 + " Re-read your persona file, then append the final sections."]
    else:
        steps = [written, f"Re-read your persona file, {rest}"]
    return ("Your run was cut off before it finished. Pick up where you left off.\n"
            + "".join(f"- {step}\n" for step in steps)
            + "- All the original rules still apply. When done, reply with the summary the instructions ask for.")


def account_again(s: dict) -> str:
    """What a resumed usability run is told of its test account, as a sentence with a space before
    it, or nothing for a run without one. A run that was partial or blocked kept its account. One
    that reached a final state, or that the lead released, had it torn down and is given another
    by the launcher, which then sets s["new_account"]: the name on the screen and the details to
    sign in with may have changed, and nothing the run did in the first account is in this one."""
    account = s.get("account") or {}
    if not account:
        return ""
    file = f"`scratch/{s['run']}/account.json`"
    if not s.get("new_account"):
        return (" You are signed in to the same test account again." if account.get("signed_in")
                else " You are signed out again: sign in as before when a task needs it."
                if account.get("signin") == "panellist" else "")
    new = (" Your test account is a new one: the one you had was closed when your run stopped, and nothing you "
           f"did in it is in this one. Read {file} again.")
    return new + (" You are signed in to the new account already." if account.get("signed_in")
                  else " You are signed out: sign in with the details that file gives now, when a task needs it. "
                       "The earlier details no longer work." if account.get("signin") == "panellist" else "")


def issue_attempts(cfg: dict, s: dict) -> dict[str, int]:
    """The attempt each task of a usability run is to be logged under when the run is continued:
    what launch.py puts on the run's entry as "task_attempts" before it makes the resume message
    (panel_lib.issued_attempts()). s is the run's run_view(). A task that has no section yet and
    has entries that count in the attempt it was last given (panel_lib.counted()) was under way
    when the run was cut off: it gets the next number. Every other task keeps its own, so a task
    that was given a number and logged nothing under it, because that process never got so far,
    is given the same number again, and asking twice changes nothing."""
    issued = pl.issued_attempts(s)
    logged = pl.counted(pl.read_steps(cfg["_dir"], s["run"])[0], issued)
    under_way = {e["task"] for e in logged if e["attempt"] == issued.get(e["task"], 1)}
    return {**issued, **{t["id"]: issued.get(t["id"], 1) + 1 for t in cfg["tasks"]
                         if t["id"] not in s["written"] and t["id"] in under_way}}


def usability_resume(cfg: dict, s: dict) -> str:
    """resume_message() for a run of a usability study. Its browser session is a new one, so
    whatever task was under way starts again from its start page. The steps it had logged for
    that task stay in the step log, and the new ones are told apart by the attempt number given
    here: the one the launcher has issued for the task (issue_attempts(), on the run's entry),
    which is above 1 only for a task that was under way. What it is told of its test account is
    account_again()."""
    tasks = {t["id"]: t for t in cfg["tasks"]}
    written, unscored = s["written"], s["unscored"]
    left = [t for t in tasks if t not in written]
    steps = []
    if written:
        steps.append(f"Tasks already written: {', '.join(written)}. Do not attempt "
                     + pl.agree(len(written), "it again, and do not rewrite or repeat its section.",
                                "them again, and do not rewrite or repeat their sections."))
    if unscored:
        n = len(unscored)
        steps.append(f"Written, but with no score row: {', '.join(unscored)}. Without that row "
                     f"{pl.agree(n, 'the section does', 'those sections do')} not count. Re-read your persona file "
                     f"and add the score table at the end of {pl.agree(n, 'that section', 'each of those sections')}, "
                     f"as the template sets it out. Change nothing else in {pl.agree(n, 'it', 'them')}.")
    if left:
        steps.append(f"Tasks left, in this order: {', '.join(left)}.")
        signed = account_again(s)
        steps.append("Your browser was restarted: it is on a blank page, and nothing you had opened or typed is still "
                     f"there.{signed} The rules for the browser are unchanged.")
        issued = pl.issued_attempts(s)
        for tid in (t for t in left if issued.get(t, 1) > 1):
            again = issued[tid]
            steps.append(f"Task {tid} was under way when you were cut off. Start it again from its start page, "
                         f"`{pl.task_url(cfg, tasks[tid])}`, and number its steps from 1 again. Leave the entries "
                         f"already in your step log as they are. Give every new entry for this task "
                         f"`\"attempt\": {again}`, and name its screenshots `{tid}-a{again}-<step>.png`.")
        steps.append("Re-read your persona file, then attempt the tasks left: append each task's section as you "
                     "finish the task, then append the final sections.")
    elif not s["has_final"]:
        steps.append("Every task has its section. Re-read your persona file, then append the final sections.")
    else:
        steps.append("Nothing else is left: your final sections are written, so do not repeat them.")
    return ("Your run was cut off before it finished. Pick up where you left off.\n"
            + "".join(f"- {step}\n" for step in steps)
            + "- All the original rules still apply. When done, reply with the summary the instructions ask for.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("cmd", choices=["status", "next", "prompt", "mark", "resume"])
    ap.add_argument("run", nargs="?")
    ap.add_argument("agent", nargs="?")
    ap.add_argument("--limit", type=int, default=20, help="how many subagents your harness runs at once (default 20)")
    ap.add_argument("--running", default="", help="comma-separated run ids already running")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    cfg = pl.load_study(args.study_dir)
    sd = cfg["_dir"]
    states = run_states(sd, cfg)
    if args.cmd in ("next", "mark", "resume") and any(s["runner"] for s in states):
        raise SystemExit(f"This study runs through runners, so launch.py starts, tracks and resumes its runs: "
                         f"launch.py {args.study_dir} {'resume' if args.cmd == 'resume' else 'run'}. "
                         f"runs.py {args.cmd} is for native mode.")

    if args.cmd == "status":
        if args.json:
            print(json.dumps(states, indent=2))
            return
        counts = {}
        for s in states:
            counts[s["state"]] = counts.get(s["state"], 0) + 1
            print(f"{s['run']:<16} {s['state']:<8} {s['scored']}/{s['of']}  {s['name']}")
        print(" | ".join(f"{k}: {v}" for k, v in sorted(counts.items())), *pl.unsettled_lines(states), sep="\n")
    elif args.cmd == "next":
        running = {x.strip() for x in args.running.split(",") if x.strip()}
        # A pending run with a recorded agent id was launched and hasn't written yet: count it as running.
        running |= {s["run"] for s in states if s["state"] != "done" and s.get("agent")}
        slots = max(0, args.limit - len(running))
        todo = [s for s in states if s["state"] == "pending" and s["run"] not in running][:slots]
        if args.json:
            print(json.dumps([{**s, "prompt_text": (sd / s["prompt"]).read_text()} for s in todo], indent=2))
            return
        for s in todo:
            effort = f", effort: {s['effort']}" if s["effort"] else ""
            print(f"=== {s['run']} (model: {s['model']}{effort}, description: Panel {s['run']})")
            print((sd / s["prompt"]).read_text())
        print(f"{len(todo)} to launch; {sum(s['state'] == 'pending' for s in states) - len(todo)} left queued.")
    elif args.cmd == "mark":
        if not (args.run and args.agent):
            raise SystemExit("usage: runs.py <study> mark <run-id> <agent-id>")
        data = pl.read_runs(sd)
        hit = [r for r in data if r["run"] == args.run]
        if not hit:
            raise SystemExit(f"No run {args.run}")
        hit[0]["agent"] = args.agent
        pl.write_runs(sd, data)
        print(f"{args.run} -> {args.agent}")
    elif args.cmd == "resume":
        todo = [s for s in states if s["state"] != "done" and (not args.run or s["run"] == args.run)]
        for s in todo:
            print(f"=== {s['run']} ({s['state']}, agent: {s.get('agent') or 'not recorded: relaunch with runs.py prompt'})")
            print(resume_message(cfg, s))
        print(f"{pl.plural(len(todo), 'unfinished run')}.")
    else:
        match = [s for s in states if s["run"] == args.run]
        if not match:
            raise SystemExit(f"No run {args.run}")
        print((sd / match[0]["prompt"]).read_text())


if __name__ == "__main__":
    main()
