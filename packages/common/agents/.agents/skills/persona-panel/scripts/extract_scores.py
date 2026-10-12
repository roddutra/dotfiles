#!/usr/bin/env python3
"""Extract every run's scores, ranking and progress into analysis/scores.csv, rankings.csv and runs.csv.

scores.csv:   persona_id, persona, model, replicate, complete, segment, concept, position, <factor keys...>
rankings.csv: persona_id, model, replicate, complete, segment, rank, concept
runs.csv:     run, persona_id, model, replicate, segment, state, complete, written, scored, has_final

"model" is the model key. "position" is where the concept sat in that persona's review order
(1-based), for order-effect checks. "complete" is 1 when panel_lib.run_progress says the run is
complete and 0 otherwise: analyze.py keeps the rows of incomplete runs out of its headline tables.

runs.csv has one row per expected run (panel_lib.run_records), whether or not it wrote anything.
"state" is its lifecycle state (panel_lib.run_state); "written" and "scored" are the concept
labels with a section and with a score row, separated by spaces; "has_final" is 1 when the final
sections exist.

Usage: extract_scores.py <study-dir>
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    cfg = pl.load_study(Path(sys.argv[1]))
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
            for i, label in enumerate(r["ranking"], start=1):
                rw.writerow([*who, complete, run["segment"], i, label])
    print(f"{n_rows} score rows from {len(runs)} runs; {incomplete} runs incomplete "
          f"(run check_runs.py for details)")


if __name__ == "__main__":
    main()
