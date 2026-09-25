#!/usr/bin/env python3
"""Extract every run's scores and ranking into analysis/scores.csv and analysis/rankings.csv.

scores.csv:   persona_id, persona, model, segment, concept, position, <factor keys...>
rankings.csv: persona_id, model, segment, rank, concept

"position" is where the concept sat in that persona's review order (1-based), for order-effect checks.

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
    runs = pl.load_runs(sd, cfg)
    (sd / "analysis").mkdir(exist_ok=True)
    n_rows = incomplete = 0
    with open(sd / "analysis" / "scores.csv", "w", newline="") as f, \
            open(sd / "analysis" / "rankings.csv", "w", newline="") as g:
        w = csv.writer(f)
        w.writerow(["persona_id", "persona", "model", "segment", "concept", "position", *keys])
        rw = csv.writer(g)
        rw.writerow(["persona_id", "model", "segment", "rank", "concept"])
        for r in runs:
            order = r["order"] or pl.review_order(cfg, r["pid"], labels)
            for label in labels:
                if label in r["scores"]:
                    pos = order.index(label) + 1 if label in order else ""
                    w.writerow([r["pid"], r["slug"], r["model"], r["segment"], label, pos,
                                *[f"{x:g}" for x in r["scores"][label]]])
                    n_rows += 1
            if len(r["scores"]) != len(labels):
                incomplete += 1
            for i, label in enumerate(r["ranking"], start=1):
                rw.writerow([r["pid"], r["model"], r["segment"], i, label])
    print(f"{n_rows} score rows from {len(runs)} runs; {incomplete} runs incomplete "
          f"(run check_runs.py for details)")


if __name__ == "__main__":
    main()
