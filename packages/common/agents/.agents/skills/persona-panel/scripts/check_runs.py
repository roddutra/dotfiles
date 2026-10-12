#!/usr/bin/env python3
"""Validate every run file before analysis and write analysis/checks.md.

Flags, per run:
  - missing, duplicated (often from a resumed run) or unscored concept sections
  - concept labels that don't exist (invented or mislabelled concepts)
  - missing final sections or ranking
  - ranking that contradicts the run's own overall scores
  - flat scoring (very low spread across all factor scores)
  - em or en dashes, and leak terms from study.json (background-context leakage)
  - a review order different from the key
  - a persona file changed while other runs were running and its own was not: a panellist wrote
    outside its own file. This comes from the modification record launch.py keeps in
    logs/modifications.json (panel_lib.py), so a native-mode study is never flagged. Once you
    have dealt with a change, take its entry out of that file

Exit code 1 when any run has a blocking problem (missing, duplicate, unscored, unknown, or
changed by another run).

Usage: check_runs.py <study-dir>
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402


def check(run: dict, cfg: dict, expected_order: list[str], changes: list[dict] = ()) -> tuple[list[str], list[str]]:
    """changes: the modification record's entries for this run's persona file."""
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
    if run["dash_count"]:
        notes.append(f"{run['dash_count']} em/en dashes")
    low = run["text"].lower()
    leaks = [t for t in cfg["leak_terms"] if t.lower() in low]
    if leaks:
        notes.append(f"leak terms: {', '.join(leaks)}")
    if run["order"] and expected_order and run["order"] != expected_order:
        notes.append(f"review order {','.join(run['order'])} differs from key {','.join(expected_order)}")
    return blocking, notes


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    cfg = pl.load_study(Path(sys.argv[1]))
    sd = cfg["_dir"]
    labels = list(pl.label_map(cfg))
    runs = pl.load_runs(sd, cfg)
    changes = pl.read_modifications(sd)["changes"]
    lines = ["# Run checks", "", "| Run | Blocking | Notes |", "|---|---|---|"]
    bad = 0
    for r in runs:
        # Only studies scaffolded by init_study.py have a seeded order to compare against.
        order = pl.review_order(cfg, r["pid"], labels) if (sd / "runs.json").exists() else []
        blocking, notes = check(r, cfg, order, [c for c in changes if c.get("run") == r["run"]])
        bad += bool(blocking)
        if blocking or notes:
            lines.append(f"| {r['run']} | {'; '.join(blocking) or '-'} | {'; '.join(notes) or '-'} |")
    expected = len(cfg["personas"]) * len(pl.model_keys(cfg)) * cfg["replicates"]
    lines += ["", f"{len(runs)} run files of {expected} expected; {bad} with blocking problems."]
    (sd / "analysis").mkdir(exist_ok=True)
    (sd / "analysis" / "checks.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
