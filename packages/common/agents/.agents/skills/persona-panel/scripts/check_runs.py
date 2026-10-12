#!/usr/bin/env python3
"""Validate every run file before analysis and write analysis/checks.md.

Flags, per run:
  - missing, duplicated (often from a resumed run) or unscored concept sections
  - concept labels that don't exist (invented or mislabelled concepts)
  - missing final sections or ranking
  - ranking that contradicts the run's own overall scores
  - flat scoring (very low spread across all factor scores)
  - em or en dashes, and leak terms from study.json (background-context leakage). A follow-up
    question that followups.json records, quoted by the panellist in its section, is the lead's
    writing and is left out of both: the answer under it is checked like the rest of the file
  - a review order different from the key (a variant's is its parent's: panel_lib.review_order)
  - a persona file changed while other runs were running and its own was not: a panellist wrote
    outside its own file. This comes from the modification record launch.py keeps in
    logs/modifications.json (panel_lib.py), so a native-mode study is never flagged. Once you
    have dealt with a change, take its entry out of that file
  - a "## Follow-up <n>" section that followups.json does not record as an answer (the panellist or
    a hand edit added it), and an answer on record whose section is missing. Both are notes, and
    neither blocks: a follow-up never changes a score

A run whose latest follow-up question is not settled yet is checked as it stood before the
question (panel_lib.read_persona): a line under the table names each such run. Check again once a
launcher has settled it.

Exit code 1 when any run has a blocking problem (missing, duplicate, unscored, unknown, or
changed by another run).

Usage: check_runs.py <study-dir>
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402


def check(run: dict, cfg: dict, expected_order: list[str], changes: list[dict] = (),
          asked: dict | None = None, questions: dict | None = None) -> tuple[list[str], list[str]]:
    """changes: the modification record's entries for this run's persona file. asked: {follow-up
    number: outcome} for the follow-up questions followups.json records for this run, and
    questions: {follow-up number: the question} for the same ones."""
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
        blocking.append(f"unknown {unit} labels: {', '.join(sorted(set(run['unknown_labels'])))}")
    for c in changes:
        others = c.get("running") or []
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(c["at"]))
        blocking.append(f"changed while {', '.join(others)} {'was' if len(others) == 1 else 'were'} running, "
                        f"not by its own run (seen {when})")
    if not prog["has_final"]:
        notes.append("final sections missing")
    if len(run["ranking"]) < len(labels):
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    cfg = pl.load_study(ap.parse_args().study_dir)
    sd = cfg["_dir"]
    labels = list(pl.label_map(cfg))
    runs = pl.load_runs(sd, cfg)
    changes = pl.read_modifications(sd)["changes"]
    followups = pl.read_followups(sd)
    lines = ["# Run checks", "", "| Run | Blocking | Notes |", "|---|---|---|"]
    bad = 0
    for r in runs:
        # Only studies scaffolded by init_study.py have a seeded order to compare against.
        order = pl.review_order(cfg, r["pid"], labels) if (sd / "runs.json").exists() else []
        mine = [f for f in followups if any(x["run"] == r["run"] for x in f.get("runs") or [])]
        asked = {f["n"]: x.get("outcome") for f in mine for x in f["runs"] if x["run"] == r["run"]}
        blocking, notes = check(r, cfg, order, [c for c in changes if c.get("run") == r["run"]], asked,
                                {f["n"]: f.get("question") for f in mine})
        bad += bool(blocking)
        if blocking or notes:
            lines.append(f"| {r['run']} | {'; '.join(blocking) or '-'} | {'; '.join(notes) or '-'} |")
    expected = len(cfg["personas"]) * len(pl.model_keys(cfg)) * cfg["replicates"]
    lines += ["", f"{len(runs)} run files of {expected} expected; {bad} with blocking problems."]
    lines += pl.unsettled_lines(runs)
    (sd / "analysis").mkdir(exist_ok=True)
    (sd / "analysis" / "checks.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
