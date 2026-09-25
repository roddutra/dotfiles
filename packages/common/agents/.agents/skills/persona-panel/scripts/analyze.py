#!/usr/bin/env python3
"""Quantitative analysis of a panel: writes analysis/quant.md and analysis/quant.json.

Reads analysis/scores.csv and analysis/rankings.csv (run extract_scores.py first) and covers:
  leaderboard (mean, median, sd, firsts, Borda, top/bottom counts), factor means and leaders,
  which factors drive Overall, segments, per-model levels and agreement, sensitivity to
  dropping each model, persona x concept matrix, order effect, and persona fit (ICP signal).

Usage: analyze.py <study-dir> [--exclude-model haiku] [--segment mortgage]
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402
from panel_lib import fmt, mean  # noqa: E402


def load(sd: Path, keys: list[str], exclude: set[str], segment: set[str] | None):
    rows = []
    with open(sd / "analysis" / "scores.csv") as f:
        for r in csv.DictReader(f):
            if r["model"] in exclude or (segment and r["segment"] not in segment):
                continue
            for k in keys:
                r[k] = float(r[k])
            r["position"] = int(r["position"]) if r.get("position") else None
            rows.append(r)
    ranks = []
    rp = sd / "analysis" / "rankings.csv"
    if rp.exists():
        with open(rp) as f:
            for r in csv.DictReader(f):
                if r["model"] in exclude or (segment and r["segment"] not in segment):
                    continue
                r["rank"] = int(r["rank"])
                ranks.append(r)
    return rows, ranks


def leaderboard(rows, ranks, labels):
    by = defaultdict(list)
    for r in rows:
        by[r["concept"]].append(r["overall"])
    runs = defaultdict(list)
    for r in ranks:
        runs[(r["persona_id"], r["model"])].append(r)
    n = len(labels)
    k = 3 if n >= 6 else 1
    first, borda, top, bottom, rsum = (defaultdict(int) for _ in range(5))
    for rr in runs.values():
        rr.sort(key=lambda x: x["rank"])
        m = len(rr)
        for x in rr:
            borda[x["concept"]] += m - x["rank"] + 1
            rsum[x["concept"]] += x["rank"]
            top[x["concept"]] += x["rank"] <= k
            bottom[x["concept"]] += x["rank"] > m - k
        first[rr[0]["concept"]] += 1
    out = []
    for c in labels:
        xs = by.get(c, [])
        out.append({"concept": c, "n": len(xs), "mean": mean(xs), "median": statistics.median(xs) if xs else None,
                    "sd": pl.sd(xs), "min": min(xs) if xs else None, "first": first[c], "borda": borda[c],
                    "top": top[c], "bottom": bottom[c], "mean_rank": rsum[c] / len(runs) if runs else None})
    out.sort(key=lambda d: (-(d["mean"] if d["n"] else -1), -d["borda"]))
    return out, len(runs), k


def table(head, rows):
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] +
                     ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("--exclude-model", action="append", default=[])
    ap.add_argument("--segment", help="restrict to persona segments (comma-separated)")
    ap.add_argument("--out", help="output basename in analysis/ (default quant, or quant-<segment>)")
    args = ap.parse_args()
    cfg = pl.load_study(args.study_dir)
    sd = cfg["_dir"]
    keys = pl.factor_keys(cfg)
    labels = list(pl.label_map(cfg))
    fl = {f["key"]: f["label"] for f in cfg["factors"]}
    seg_filter = set(args.segment.split(",")) if args.segment else None
    rows, ranks = load(sd, keys, set(args.exclude_model), seg_filter)
    if not rows:
        raise SystemExit("No score rows. Run extract_scores.py first.")
    models = [m for m in cfg["models"] if any(r["model"] == m for r in rows)]
    names = {p["id"]: p["name"] for p in cfg["personas"]}
    roles = {p["id"]: p["role"] for p in cfg["personas"]}
    res = {"filters": {"exclude_models": args.exclude_model, "segment": args.segment}}
    md = [f"# Quantitative analysis: {sd.name}", ""]
    if args.exclude_model or args.segment:
        md += [f"Filters: excluded models {args.exclude_model or 'none'}; segment {args.segment or 'all'}.", ""]
    n_runs = len({(r["persona_id"], r["model"]) for r in rows})

    # Leaderboard
    lb, ranked_runs, k = leaderboard(rows, ranks, labels)
    res["leaderboard"] = lb

    # Factors
    fac = {c: {f: mean([r[f] for r in rows if r["concept"] == c]) for f in keys} for c in labels}
    res["factors"] = fac
    leaders = {f: max(labels, key=lambda c: fac[c][f]) for f in keys}

    # Drivers
    drivers = {f: pl.pearson([r[f] for r in rows], [r["overall"] for r in rows]) for f in keys[:-1]}
    res["drivers"] = drivers

    # Segments
    segs = sorted({r["segment"] for r in rows if r["segment"]})
    seg_tab = {s: {c: mean([r["overall"] for r in rows if r["segment"] == s and r["concept"] == c])
                   for c in labels} for s in segs}
    res["segments"] = seg_tab

    # Models
    level = {m: mean([r["overall"] for r in rows if r["model"] == m]) for m in models}
    per_model = {m: {c: mean([r["overall"] for r in rows if r["model"] == m and r["concept"] == c])
                     for c in labels} for m in models}
    pair_agree = {}
    for a, b in itertools.combinations(models, 2):
        vals = []
        for pid in sorted({r["persona_id"] for r in rows}):
            xa = {r["concept"]: r["overall"] for r in rows if r["persona_id"] == pid and r["model"] == a}
            xb = {r["concept"]: r["overall"] for r in rows if r["persona_id"] == pid and r["model"] == b}
            common = [c for c in labels if c in xa and c in xb]
            if len(common) >= 3:
                v = pl.spearman([xa[c] for c in common], [xb[c] for c in common])
                if v == v:
                    vals.append(v)
        pair_agree[f"{a}-{b}"] = mean(vals) if vals else None
    full_order = [d["mean"] for d in sorted(lb, key=lambda d: d["concept"])]
    sens = {}
    for m in models:
        sub = [r for r in rows if r["model"] != m]
        means = [mean([r["overall"] for r in sub if r["concept"] == c]) for c in sorted(labels)]
        if len(models) > 1:
            win = sorted(labels)[max(range(len(means)), key=lambda i: means[i])]
            sens[m] = {"winner": win, "rho_vs_full": pl.spearman(full_order, means)}
    res["models"] = {"level": level, "per_model": per_model, "pair_spearman": pair_agree, "drop_one": sens}

    # Persona matrix
    pids = sorted({r["persona_id"] for r in rows})
    pmat = {p: {c: mean([r["overall"] for r in rows if r["persona_id"] == p and r["concept"] == c])
                for c in labels} for p in pids}
    res["persona_matrix"] = pmat

    # Order effect
    pos = [(r["position"], r["overall"]) for r in rows if r["position"]]
    order_r = pl.pearson([p for p, _ in pos], [o for _, o in pos]) if pos else float("nan")
    by_pos = {p: mean([o for q, o in pos if q == p]) for p in sorted({p for p, _ in pos})}
    res["order"] = {"pearson_position_overall": order_r, "mean_by_position": by_pos}

    # Persona fit on the strongest concepts
    top_n = min(3, len(labels))
    best = [d["concept"] for d in lb[:top_n]]
    ff = cfg["fit_factors"]
    fit = []
    for p in pids:
        pr = [r for r in rows if r["persona_id"] == p and r["concept"] in best]
        run_best = defaultdict(float)
        for r in rows:
            if r["persona_id"] == p:
                run_best[r["model"]] = max(run_best[r["model"]], r["overall"])
        fit.append({"persona": p, "name": names.get(p, ""), "role": roles.get(p, ""),
                    "segment": next((r["segment"] for r in rows if r["persona_id"] == p), ""),
                    "fit": mean([mean([r[f] for f in ff]) for r in pr]),
                    "best_overall": mean(list(run_best.values()))})
    fit.sort(key=lambda d: -d["fit"])
    res["fit"] = {"factors": ff, "concepts": best, "personas": fit}

    # ---------------------------------------------------------------- markdown
    w = lb[0]
    gap = w["mean"] - lb[1]["mean"] if len(lb) > 1 else 0
    md += ["## Key numbers", "",
           f"- {n_runs} runs, {len(rows)} concept reviews, {len(pids)} personas, models: {', '.join(models)}.",
           f"- Winner on mean Overall: **{w['concept']}** ({fmt(w['mean'])}), {fmt(gap)} ahead of {lb[1]['concept']}."
           if len(lb) > 1 else f"- Only concept: {w['concept']}.",
           f"- Ranked first in {w['first']} of {ranked_runs} runs with a ranking."]
    strong = sorted(drivers.items(), key=lambda kv: -(kv[1] if kv[1] == kv[1] else -9))[:3]
    md.append("- Overall tracks " + ", ".join(f"{fl[f]} (r {fmt(v)})" for f, v in strong) + " most closely.")
    if pair_agree:
        md.append("- Within-persona model agreement (Spearman): " +
                  ", ".join(f"{k2} {fmt(v)}" for k2, v in pair_agree.items()) + ".")
    if sens:
        flips = [m for m, s in sens.items() if s["winner"] != w["concept"]]
        md.append("- Dropping any single model keeps the winner." if not flips
                  else f"- Winner changes when dropping: {', '.join(flips)}.")
    md.append(f"- Order effect: r {fmt(order_r)} between review position and Overall.")
    if fit:
        md.append(f"- Best-fit persona: {fit[0]['persona']} {fit[0]['name']} (fit {fmt(fit[0]['fit'])}); "
                  f"weakest: {fit[-1]['persona']} {fit[-1]['name']} ({fmt(fit[-1]['fit'])}).")
    md += ["", "Differences under about 0.4 are within noise for small panels.", ""]

    md += ["## Leaderboard", "", table(
        ["Concept", "n", "Mean", "Median", "SD", "Min", "Ranked 1st", "Borda", f"Top {k}", f"Bottom {k}", "Mean rank"],
        [[d["concept"], d["n"], fmt(d["mean"]), fmt(d["median"], 1), fmt(d["sd"]), fmt(d["min"], 0), d["first"],
          d["borda"], d["top"], d["bottom"], fmt(d["mean_rank"])] for d in lb]), ""]

    md += ["## By factor", "", table(
        ["Factor", *labels, "Leader"],
        [[fl[f], *[fmt(fac[c][f]) for c in labels], leaders[f]] for f in keys]), ""]

    md += ["## What drives Overall", "", "Pearson correlation of each factor with Overall across all reviews.", "",
           table(["Factor", "r"], [[fl[f], fmt(v)] for f, v in sorted(drivers.items(), key=lambda kv: -kv[1])]), ""]

    if segs:
        md += ["## By segment", "", table(
            ["Segment", "Runs", *labels],
            [[cfg["segments"].get(s, s), len({(r["persona_id"], r["model"]) for r in rows if r["segment"] == s}),
              *[fmt(seg_tab[s][c]) for c in labels]] for s in segs]), ""]

    md += ["## By model", "", table(
        ["Model", "Level", *labels, "Top"],
        [[m, fmt(level[m]), *[fmt(per_model[m][c]) for c in labels],
          max(labels, key=lambda c: per_model[m][c])] for m in models]), ""]
    if pair_agree:
        md += ["Within-persona agreement between models (mean Spearman over each persona's concept scores):", "",
               table(["Pair", "Spearman"], [[k2, fmt(v)] for k2, v in pair_agree.items()]), ""]
    if sens:
        md += ["Sensitivity (leaderboard without one model):", "",
               table(["Dropped", "Winner", "Spearman vs full"],
                     [[m, s["winner"], fmt(s["rho_vs_full"])] for m, s in sens.items()]), ""]

    md += ["## Persona x concept (mean Overall across models)", "", table(
        ["Persona", *labels],
        [[f"{p} {names.get(p, '')}", *[fmt(pmat[p][c], 1) for c in labels]] for p in pids]), ""]

    if by_pos:
        md += ["## Order effect", "", f"Pearson r between review position and Overall: {fmt(order_r)}.", "",
               table(["Position", "Mean Overall"], [[p, fmt(v)] for p, v in by_pos.items()]), ""]

    md += ["## Persona fit (ICP signal)", "",
           f"Mean of {', '.join(fl[f] for f in ff)} on the strongest concepts ({', '.join(best)}). "
           "Read as: how strongly the best version of the offer resonated with each persona.", "",
           table(["Persona", "Role", "Segment", "Fit", "Best Overall per run"],
                 [[f"{d['persona']} {d['name']}", d["role"], d["segment"], fmt(d["fit"]), fmt(d["best_overall"])]
                  for d in fit]), ""]

    base = args.out or ("quant" + (f"-{args.segment.replace(',', '+')}" if args.segment else "") +
                        "".join(f"-no-{m}" for m in args.exclude_model))
    (sd / "analysis" / f"{base}.md").write_text("\n".join(md))
    (sd / "analysis" / f"{base}.json").write_text(json.dumps(res, indent=2, default=str))
    print("\n".join(md[: md.index("## Leaderboard")]))
    print(f"Wrote analysis/{base}.md and analysis/{base}.json")


if __name__ == "__main__":
    main()
