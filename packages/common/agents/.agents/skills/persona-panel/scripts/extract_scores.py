#!/usr/bin/env python3
"""Extract every run's scores, ranking and progress into analysis/scores.csv, rankings.csv and runs.csv.

scores.csv:   persona_id, persona, model, replicate, complete, segment, concept, position, <factor keys...>
rankings.csv: persona_id, model, replicate, complete, segment, rank, concept
runs.csv:     run, persona_id, model, replicate, segment, state, complete, written, scored, has_final

"model" is the model key. "position" is where the concept sat in that persona's review order
(1-based), for order-effect checks. A study with one concept has no ranking: rankings.csv is then
the header alone, whatever a panellist wrote. "complete" is 1 when panel_lib.run_progress says the run is
complete and 0 otherwise: analyze.py keeps the rows of incomplete runs out of its headline tables.

runs.csv has one row per expected run (panel_lib.run_records), whether or not it wrote anything.
"state" is its lifecycle state (panel_lib.run_state); "written" and "scored" are the concept
labels with a section and with a score row, separated by spaces; "has_final" is 1 when the final
sections exist.

A run whose latest follow-up question is not settled yet is read as it stood before the question
(panel_lib.read_persona), so nothing a follow-up changed reaches a CSV before a launcher has
accepted it. One line names each such run.

Usage: extract_scores.py <study-dir>
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    cfg = pl.load_study(ap.parse_args().study_dir)
    sd = cfg["_dir"]
    labels = list(pl.label_map(cfg))
    keys = pl.factor_keys(cfg)
    runs = pl.run_records(sd, cfg)
    (sd / "analysis").mkdir(exist_ok=True)
    n_rows = incomplete = 0
    with open(sd / "analysis" / "scores.csv", "w", newline="") as f, \
            open(sd / "analysis" / "rankings.csv", "w", newline="") as g, \
            open(sd / "analysis" / "runs.csv", "w", newline="") as h:
        w = csv.writer(f)
        w.writerow(["persona_id", "persona", "model", "replicate", "complete", "segment", "concept", "position",
                    *keys])
        rw = csv.writer(g)
        rw.writerow(["persona_id", "model", "replicate", "complete", "segment", "rank", "concept"])
        sw = csv.writer(h)
        sw.writerow(["run", "persona_id", "model", "replicate", "segment", "state", "complete", "written",
                     "scored", "has_final"])
        for run in runs:
            prog, r = run["progress"], run["parsed"]
            complete = int(prog["complete"])
            incomplete += not complete
            who = [run["pid"], run["model"], run["replicate"]]
            sw.writerow([run["run"], *who, run["segment"], run["state"], complete, " ".join(prog["written"]),
                         " ".join(prog["scored"]), int(prog["has_final"])])
            if not r:
                continue
            order = r["order"] or pl.review_order(cfg, run["pid"], labels)
            for label in labels:
                if label in r["scores"]:
                    pos = order.index(label) + 1 if label in order else ""
                    w.writerow([run["pid"], r["slug"], *who[1:], complete, run["segment"], label, pos,
                                *[f"{x:g}" for x in r["scores"][label]]])
                    n_rows += 1
            for i, label in enumerate([] if pl.single_concept(cfg) else r["ranking"], start=1):
                rw.writerow([*who, complete, run["segment"], i, label])
    print(*pl.unsettled_lines(runs), f"{pl.plural(n_rows, 'score row')} from {pl.plural(len(runs), 'run')}; "
          f"{pl.plural(incomplete, 'run')} incomplete "
          "(run check_runs.py for details)", sep="\n")


if __name__ == "__main__":
    main()
