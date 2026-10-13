#!/usr/bin/env python3
"""Validate every run file before analysis and write analysis/checks.md.

Flags, per run:
  - missing, duplicated (often from a resumed run) or unscored concept sections, or task
    sections in a usability study
  - concept labels, or task ids, that don't exist (invented or mislabelled)
  - missing final sections or ranking (a study with one concept has no ranking, and none is
    expected)
  - ranking that contradicts the run's own overall scores
  - flat scoring (very low spread across all factor scores)
  - em or en dashes, and leak terms from study.json (background-context leakage). A follow-up
    question that followups.json records, quoted by the panellist in its section, is the lead's
    writing and is left out of both: the answer under it is checked like the rest of the file
  - a review order different from the key (a variant's is its parent's: panel_lib.review_order).
    A usability study has no ranking and no review order, and neither is looked for
  - a persona file changed while other runs were running and its own was not: a panellist wrote
    outside its own file. This comes from the modification record launch.py keeps in
    logs/modifications.json (panel_lib.py), so a native-mode study is never flagged. Once you
    have dealt with a change, take its entry out of that file
  - a "## Follow-up <n>" section that followups.json does not record as an answer (the panellist or
    a hand edit added it), and an answer on record whose section is missing. Both are notes, and
    neither blocks: a follow-up never changes a score

A persona file that cannot be read as its run's own blocks, in a row of its own that names the
file and the reason: a symbolic link, a FIFO or a folder at its name, a link at a folder above
it, or a file that may not be read (panel_lib.persona_bytes). A panellist can put any of them
there, and no script reads through one: the run is not done, and nothing of it is checked,
scored or extracted. Put a plain file that can be read at the name, or remove what is there.

A usability study has more, per run (panel_lib.py, "Secrets" and run_evidence()):
  - a secret value of any run's test account in its persona file or its step log, or in the name
    of a file in its evidence folder, which blocks: the file, the line and whose secret it was
    are named, never the value. A panellist may have been shown another's by a fault in the
    product, so every run's files are looked through for every account's secrets
  - a persona file or a step log that could not be scanned, which blocks too, with the reason:
    it may not be read, or it is a symbolic link, or its evidence folder or the evidence root
    is one. "Could not be scanned" is never "nothing found", and a link is never followed: a
    panellist can put one anywhere under panel/
  - notes, none of which blocks: files in its evidence folder that are neither its step log nor
    a screenshot of a step (archive.py copies none of them); what is wrong with the form of its
    step log (panel_lib.step_notes), entries with an attempt number the launcher did not issue
    among them, and entries that lack a field; a result entry that names a screenshot which is
    not there; a task written up with no step in the step log (which is right only when the
    start page was all it took); and an identifier of another run's test account in its files,
    which suggests that one run saw another's session

Whatever a line here repeats of a panellist's own text, in a usability study, goes through
panel_lib.shown(): a task id or a label the study does not have and the name of a file or of a
screenshot. A value that holds a known secret, is long or has other characters than a name has
is described ("a value that is not a task id, 14 characters") and never repeated, so that the
check of a secret cannot print it or write it to analysis/checks.md.

Under the table, for a usability study: each markdown file of analysis/ (the analysts' and the
writer's output, the lead's notes) that holds a secret value or could not be scanned, which
blocks as a run's does; the accounts whose secrets cannot be looked for, because they were torn
down before the fingerprint record had heard of them; and the secrets that are too short to
look for.

An interview study has no run file. Each interview is checked from its turn log,
interviews/<run id>.jsonl (panel_lib.py, "The turn log"), by interview.problems(), which
interview.py documents under "The checks":
  - blocking: no end record, which is an interview that is not finished or was never held, with
    the state it reads as and how far it got; a turn log of the wrong form, such as turns that
    do not alternate or that skip a number, or a record that lacks a field every launcher
    writes or holds another kind of value there than one writes, after which nothing else of
    that log is checked (panel_lib.turn_problems). Such a record is set aside where the log is
    read (panel_lib.read_turns), so it is named here and stops nothing; and a leak term in a
    question that was delivered
  - notes, none of which blocks: topics never opened, exchanges past a topic's cap, a capped
    interview that ended with no close, a question whose words open another topic than the one
    its interviewer labelled it with, a leak term in the card or an answer, an answer that
    speaks of being an AI, a model or a persona, a question with more than two question marks,
    a median answer of more than 120 words, a reply of the interviewer that was sent back, a
    turn that left no reply, and a turn log whose last write was never finished
Under the table: how many interviews have a turn log, of the ones the study plans; what the
lead does about each kind of blocking row (interview.advice()): the command that goes on with
an unfinished interview, where one that never started is said to be that, and "status" is
named for why an interview stopped only when one has; for a leak term in a delivered question,
which cannot be undone, how to discard the interview or keep it and report the leak; and how
many turn logs under logs/ were not checked. A fresh start or a new scaffold moves a log there,
as the lead does to discard an interview, and it is then no interview of the study. With no
row to show, the table is left out and one sentence says that nothing blocks and nothing was
noted.

An interview reads running only while a launcher has the study, which the study lock says
(panel_lib.carried()): one that a killed launcher left reads as its log reads, partial with a
turn on record, and the lines under the table name the command that goes on with it.

A run whose latest follow-up question is not settled yet is checked as it stood before the
question (panel_lib.read_persona): a line under the table names each such run. Check again once a
launcher has settled it.

Exit code 1 when any run has a blocking problem (missing, duplicate, unscored, unknown, changed
by another run, holding a secret value, with a file that could not be scanned, or with a
persona file that cannot be read as its own), or an analysis file holds a secret value or could
not be scanned. In an interview study, when any interview has a blocking problem.

The table is printed, and written to analysis/checks.md. Where the system refuses the file (a
sandboxed shell tool, a study directory that is not yours to write), the table is printed all
the same, one sentence on stderr names the file and the reason, and the exit code is still what
the table says.

Usage: check_runs.py <study-dir>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accounts  # noqa: E402
import interview  # noqa: E402
import launch  # noqa: E402
import panel_lib as pl  # noqa: E402

PHASE_FIELDS = {"intent": ("sees", "expects", "action"), "result": ("happened", "screenshot")}
IDENTIFIER_MIN = 4  # an identifier shorter than this is not looked for in another run's files


def check(run: dict, cfg: dict, expected_order: list[str], changes: list[dict] = (),
          asked: dict | None = None, questions: dict | None = None, show=str) -> tuple[list[str], list[str]]:
    """changes: the modification record's entries for this run's persona file. asked: {follow-up
    number: outcome} for the follow-up questions followups.json records for this run, and
    questions: {follow-up number: the question} for the same ones. show: how a label the study
    does not have is repeated, which in a usability study is panel_lib.shown()'s to decide."""
    blocking, notes = [], []
    prog = pl.run_progress(cfg, run)
    unit, units = pl.unit_nouns(cfg)
    labels = prog["units"]
    missing = [l for l in labels if l not in prog["written"]]
    if missing:
        blocking.append(f"missing {units}: {', '.join(missing)}")
    if run["duplicates"]:
        blocking.append(f"duplicate sections: {', '.join(run['duplicates'])}")
    if run["missing_scores"]:
        blocking.append(f"no parseable score row: {', '.join(run['missing_scores'])}")
    if run["unknown_labels"]:
        blocking.append(f"unknown {unit} {'ids' if unit == 'task' else 'labels'}: "
                        f"{', '.join(sorted(show(label) for label in set(run['unknown_labels'])))}")
    for c in changes:
        others = c.get("running") or []
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(c["at"]))
        blocking.append(f"changed while {', '.join(others)} {pl.agree(len(others), 'was', 'were')} running, "
                        f"not by its own run (seen {when})")
    if not prog["has_final"]:
        notes.append("final sections missing")
    if len(run["ranking"]) < len(labels) and pl.ranked(cfg):  # one concept is not ranked, and no task is
        notes.append(f"ranking lists {len(run['ranking'])} of {len(labels)} {units}")
    ov = {l: s[-1] for l, s in run["scores"].items()}
    if run["ranking"] and ov:
        for hi, lo in zip(run["ranking"], run["ranking"][1:]):
            if hi in ov and lo in ov and ov[lo] - ov[hi] >= 2:
                notes.append(f"ranking puts {hi} ({ov[hi]:g}) above {lo} ({ov[lo]:g})")
    allscores = [x for s in run["scores"].values() for x in s]
    if len(allscores) > 5 and pl.sd(allscores) < 0.6:
        notes.append(f"flat scoring (sd {pl.sd(allscores):.2f})")
    own = pl.own_words(run, questions or {})  # a question the lead wrote is not the panellist's to answer for
    dashes = sum(own.count(d) for d in pl.DASHES)
    if dashes:
        notes.append(f"{dashes} em/en dashes")
    low = own.lower()
    leaks = [t for t in cfg["leak_terms"] if t.lower() in low]
    if leaks:
        notes.append(f"leak terms: {', '.join(leaks)}")
    if run["order"] and expected_order and run["order"] != expected_order:
        notes.append(f"review order {','.join(run['order'])} differs from key {','.join(expected_order)}")
    asked, written = asked or {}, [f["n"] for f in run["followups"]]
    expected = {n for n, outcome in asked.items() if outcome in pl.FOLLOWUP_ANSWERED}
    loose = sorted(n for n in set(written) if n not in expected and asked.get(n) != "sent by hand")
    if loose:
        notes.append(f"follow-up section {', '.join(map(str, loose))} not recorded as an answer in {pl.FOLLOWUPS}")
    if expected - set(written):
        notes.append(f"follow-up {', '.join(map(str, sorted(expected - set(written))))} is recorded as answered, but "
                     "its section is missing")
    return blocking, notes


def listed(names: list[str], most: int = 3) -> str:
    return ", ".join(names[:most]) + (f" and {len(names) - most} more" if len(names) > most else "")


def identifiers(cfg: dict, records: list[dict]) -> dict[str, set[str]]:
    """{run id: the identifier values of its test account}, from the account records, which
    keep them after teardown, and from accounts.map, which an archive keeps them in."""
    held = {r["run"]: r.get("identifiers") or {} for r in records}
    for run, account in ((cfg.get("accounts") or {}).get("map") or {}).items():
        held.setdefault(run, account.get("identifiers") or {})
    return {run: {str(v) for v in values.values()} for run, values in held.items()}


def stands(text: str, value: str, own: set[str]) -> bool:
    """Whether a value stands in a text as a word of its own, somewhere other than inside one
    of the run's own identifiers: "test-P01-opus" is in "test-P01-opus-r2", and is not meant."""
    spans = [m.span() for mine in own for m in re.finditer(re.escape(mine), text)]
    return any(not any(a <= m.start() and m.end() <= b for a, b in spans)
               for m in re.finditer(rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])", text))


def check_evidence(run: dict, cfg: dict, known: dict, ids: dict[str, set[str]],
                   issued: dict[str, int]) -> tuple[list[str], list[str]]:
    """What a usability study adds to a run's checks (module docstring). known is what a scan
    knows the study's secrets by (panel_lib.known_secrets), ids each run's identifiers and
    issued the attempt the launcher gave each of the run's tasks (panel_lib.issued_attempts)."""
    sd, blocking, notes = cfg["_dir"], [], []
    evidence = pl.run_evidence(cfg, sd, run["run"])
    texts = []  # of the files that could be read
    for what, form, read in (("persona file", "", lambda: persona_text(sd, run["file"])),
                             ("step log", "jsonl", lambda: pl.step_log(sd, run["run"]))):
        try:
            text = read()
        except OSError as err:
            blocking.append(f"its {what} could not be scanned for secrets ({pl.unread(err)})")
            continue
        if text is None:
            continue
        texts.append(text)
        hits = pl.scan_text(known, text, form)
        if hits:
            blocking.append(f"a secret value in its {what}: {pl.secret_places(hits)}")
    other, entries = evidence["other"], evidence["entries"]
    named = sum(bool(pl.secrets_in(known, name)) for name in [*evidence["screenshots"], *other])
    if named:
        blocking.append(f"a secret value in the name of {pl.plural(named, 'file')} in its evidence folder")

    def show(value, what):
        return pl.shown(known, value, what)

    if other:
        notes.append(f"evidence folder holds {pl.plural(len(other), 'file')} that "
                     f"{pl.agree(len(other), 'is', 'are')} neither its step log nor a screenshot of a step, and "
                     f"{pl.agree(len(other), 'is', 'are')} not archived "
                     f"({listed([show(name, 'a file name that is not shown') for name in other])})")
    notes += [f"step log has {note}" for note in pl.step_notes(cfg, entries, evidence["odd"], issued, known)]
    lacking = sum(any(not isinstance(e.get(k), str) or not e[k].strip() for k in PHASE_FIELDS.get(e.get("phase"), ()))
                  for e in entries)
    if lacking:
        notes.append(f"step log has {pl.plural(lacking, 'entry', 'entries')} without every field of "
                     f"{pl.agree(lacking, 'its', 'their')} phase ({', '.join(PHASE_FIELDS['intent'])} for an intent; "
                     f"{', '.join(PHASE_FIELDS['result'])} for a result)")
    missing = [f"task {show(task, 'a value that is not a task id')} step {step}: "
               f"{show(name, 'a screenshot name that is not shown')}" for task, _, step, name in evidence["missing"]]
    if missing:
        notes.append(f"step log names {pl.plural(len(missing), 'screenshot')} that "
                     f"{pl.agree(len(missing), 'is', 'are')} not in its evidence folder ({listed(missing)})")
    logged = {e["task"] for e in entries}
    unlogged = [task for task in run["sections"] if task not in logged]
    if unlogged:
        notes.append(f"{pl.agree(len(unlogged), 'task', 'tasks')} {', '.join(unlogged)} written up with no step in "
                     "the step log")
    own = ids.get(run["run"], set())
    for other_run, values in sorted(ids.items()):
        seen = sorted(v for v in values - own if len(v) >= IDENTIFIER_MIN and any(stands(t, v, own) for t in texts))
        if seen:
            notes.append(f"names an identifier of {other_run}'s test account "
                         f"({listed([json.dumps(v) for v in seen])}): it may have seen that run's session")
    return blocking, notes


def persona_text(sd: Path, name: str) -> str:
    """A run's persona file as it is now, to scan it: read as text whatever it holds, and as
    every persona file is read (panel_lib.persona_bytes). The run itself may have been read
    from the copy made before a follow-up that is not settled."""
    return pl.persona_bytes(sd, pl.personas_dir(sd) / name).decode(errors="replace")


def unread_rows(cfg: dict, runs: list[dict], known: dict | None) -> list[str]:
    """A row of the table for each persona file that cannot be read as its run's own (module
    docstring), which blocks. runs are the ones that were read: one read from the copy made
    before an unsettled follow-up has its file put right when that is settled, and no row here.
    The path of a file under panel/ may be a panellist's own text, and is shown as
    panel_lib.shown_path() allows."""
    sd, read, rows = cfg["_dir"], {r["file"] for r in runs}, []
    for path, entry in pl.persona_files(sd):
        why = None if path.name in read else pl.persona_problem(sd, path)
        if not why:
            continue
        if known is None:  # a review study has no secret to look for: only what a name is made of decides
            known = pl.known_secrets(cfg)
        m = pl.FILE_RE.match(path.name)
        run = (entry["run"] if entry else pl.run_id(m["pid"], m["model"], int(m["rep"] or 1)) if m
               else path.stem)
        rows.append(f"| {pl.shown(known, run, 'a run id that is not shown')} | its persona file "
                    f"{pl.shown_path(known, path.relative_to(sd))} cannot be read as the run's own ({why}) | - |")
    return rows


def scan_study(cfg: dict) -> tuple[dict, dict, list[str], int]:
    """What a usability study's checks need beside its runs: what a scan knows the secrets by,
    each run's identifiers, the lines to print under the table, and how many analysis files hold
    a secret value or could not be scanned."""
    sd = cfg["_dir"]
    records = accounts.records(sd)
    known = pl.known_secrets(cfg, [r for r in records if accounts.in_force(r)])
    lines, leaks, unscanned = [], 0, 0
    for f in sorted((sd / "analysis").rglob("*.md")):
        if f.name == "checks.md":  # this script's own, written anew below
            continue
        try:
            hits = pl.scan_file(known, f)
        except OSError as err:
            unscanned += 1
            lines.append(f"Not scanned for secrets: {f.relative_to(sd)} ({pl.unread(err)}).")
            continue
        if hits:
            leaks += 1
            lines.append(f"A secret value in {f.relative_to(sd)}: {pl.secret_places(hits)}.")
    if leaks:
        lines.append(f"{pl.plural(leaks, 'analysis file')} with a secret value: take it out before anyone reads "
                     f"{pl.agree(leaks, 'it', 'them')}.")
    if unscanned:
        lines.append(f"{pl.plural(unscanned, 'analysis file')} that could not be scanned: a file that cannot be read "
                     "is not known to be clean. Make it a plain file that can be read, then check again.")
    return known, identifiers(cfg, records), lines + pl.secret_gaps(known, records), leaks + unscanned


def check_interviews(cfg: dict) -> tuple[list[str], int]:
    """The checks of an interview study (module docstring): the lines of the table and what
    stands under it, and how many interviews have a blocking problem. Every interview the study
    has is checked, one that was never started too, each from its turn log in interviews/. The
    report carries the synthetic panel notice (pl.NOTICE) under its title, as every report of an
    interview study does where it is written: the file is then the same in the study, in an
    archive of it, and when this script runs again inside the archive."""
    sd = cfg["_dir"]
    entries = pl.read_runs(sd) if (sd / "runs.json").exists() else pl.planned_runs(cfg)
    entries = {e["run"]: e for e in entries if e["role"] == "panellist"}
    rows, found = [], []
    records = pl.run_records(sd, cfg, bool(launch.Lock.holder(sd)))  # carried only while a launcher has the study
    for r in records:
        blocking, notes = interview.problems(cfg, entries[r["run"]], r["turns"], r["state"])
        found.append((r["run"], r["state"], blocking))
        if blocking or notes:
            rows.append(f"| {r['run']} | {'; '.join(blocking) or '-'} | {'; '.join(notes) or '-'} |")
    bad = sum(bool(blocking) for _, _, blocking in found)
    expected = len(cfg["personas"]) * len(pl.model_keys(cfg)) * cfg["replicates"]
    held = sum(pl.turn_log(sd, r["run"]).exists() for r in records)
    lines = ["# Run checks", "", pl.NOTICE, "",
             *(["| Run | Blocking | Notes |", "|---|---|---|", *rows, ""] if rows else [])]
    lines += [f"{pl.plural(held, 'interview')} with a turn log, of {expected} expected; {bad} with blocking "
              "problems." + ("" if rows else " Nothing blocks, and nothing was noted of any interview.")]
    lines += interview.advice(cfg, found)
    aside = len([*sd.glob("logs/*.jsonl"), *sd.glob("logs/interviews-*/*.jsonl"),  # nothing else there is one
                 *sd.glob("logs/interviews-*/logs/*.jsonl")])
    if aside:
        lines.append(f"Not checked: {pl.plural(aside, 'turn log')} under logs/, set aside by a fresh start, a new "
                     f"scaffold or the lead. {pl.agree(aside, 'It is', 'They are')} no interview of this study.")
    return lines, bad


def report(sd: Path, lines: list[str], failed: bool):
    """Print the checks, write them to analysis/checks.md, and exit with 1 when failed. The
    table is printed first: a study directory that cannot be written still gets its checks."""
    print("\n".join(lines), flush=True)
    kept = sd / "analysis" / "checks.md"
    try:
        kept.parent.mkdir(exist_ok=True)
        kept.write_text("\n".join(lines) + "\n")
    except OSError as err:
        print(pl.not_written(kept, err), file=sys.stderr)
    sys.exit(1 if failed else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    cfg = pl.load_study(ap.parse_args().study_dir)
    sd = cfg["_dir"]
    if cfg["type"] == "interview":  # no run file: every interview is checked from its turn log
        lines, bad = check_interviews(cfg)
        report(sd, lines, bool(bad))
    runs = pl.load_runs(sd, cfg)
    changes = pl.read_modifications(sd)["changes"]
    followups = pl.read_followups(sd)
    lines = ["# Run checks", "", "| Run | Blocking | Notes |", "|---|---|---|"]
    bad = leaks = 0
    known, ids, found, entries = None, {}, [], {}
    if cfg["type"] == "usability":
        known, ids, found, leaks = scan_study(cfg)
        entries = {e["run"]: e for e in pl.read_runs(sd)} if (sd / "runs.json").exists() else {}
    for r in runs:
        # Only studies scaffolded by init_study.py have a seeded order to compare against.
        order = pl.unit_order(cfg, r["pid"]) if (sd / "runs.json").exists() and pl.ranked(cfg) else []
        mine = [f for f in followups if any(x["run"] == r["run"] for x in f.get("runs") or [])]
        asked = {f["n"]: x.get("outcome") for f in mine for x in f["runs"] if x["run"] == r["run"]}
        blocking, notes = check(r, cfg, order, [c for c in changes if c.get("run") == r["run"]], asked,
                                {f["n"]: f.get("question") for f in mine},
                                *([lambda label: pl.shown(known, label, "a value that is not a task id")] if known
                                  else []))
        if known:
            more = check_evidence(r, cfg, known, ids, pl.issued_attempts(entries.get(r["run"])))
            blocking, notes = blocking + more[0], notes + more[1]
        bad += bool(blocking)
        if blocking or notes:  # a run id is made from a file's name, which in panel/ may be a panellist's own
            name = pl.shown(known, r["run"], "a run id that is not shown") if known else r["run"]
            lines.append(f"| {name} | {'; '.join(blocking) or '-'} | {'; '.join(notes) or '-'} |")
    unread = unread_rows(cfg, runs, known)
    lines, bad = lines + unread, bad + len(unread)
    expected = len(cfg["personas"]) * len(pl.model_keys(cfg)) * cfg["replicates"]
    lines += ["", f"{pl.plural(len(runs), 'run file')} of {expected} expected; {bad} with blocking problems."]
    lines += found + pl.unsettled_lines(runs)
    report(sd, lines, bool(bad or leaks))


if __name__ == "__main__":
    main()
