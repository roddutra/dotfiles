#!/usr/bin/env python3
"""Quantitative analysis of a panel: writes analysis/quant.md and analysis/quant.json.

Reads analysis/scores.csv, rankings.csv and runs.csv (run extract_scores.py first) and covers:
  leaderboard (mean, median, sd, firsts, Borda, top/bottom counts), factor means and leaders,
  which factors drive Overall, segments, per-model levels and agreement, sensitivity to
  dropping each model, persona x concept matrix, order effect, and persona fit (ICP signal).

A run is one persona on one model key and one replicate. Replicates are counted and compared as
separate runs, never merged into one. A scores.csv without a replicate column reads as replicate 1.

Each of those tables uses complete runs only, and the output states "N of M runs complete", where M
is the runs expected after the filters. Incomplete runs that wrote something, or that stopped as
partial, limited, blocked or failed, get their own table, "Incomplete runs", with their state,
what they wrote and their Overall scores: those scores appear nowhere else. When no run is
complete there is nothing to rank, and the output is that count and that table.

Exports from before the "complete" column and runs.csv existed read as all complete: the runs
with score rows are then the runs expected.

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


# Incomplete runs in these states are listed even when they wrote nothing: they ran and stopped.
# Pending and running ones that wrote nothing are only counted.
LISTED_STATES = ("partial", "limited", "blocked", "failed")


def run_key(r: dict) -> tuple:
    return r["persona_id"], r["model"], r["replicate"]


def load(sd: Path, keys: list[str], exclude: set[str], segment: set[str] | None):
    """Score rows, ranking rows and run records left by the filters, complete or not."""
    def read(name):
        path = sd / "analysis" / name
        if not path.exists():
            return None
        with open(path) as f:
            kept = [r for r in csv.DictReader(f)
                    if r["model"] not in exclude and (not segment or r["segment"] in segment)]
        for r in kept:
            r["replicate"] = int(r.get("replicate") or 1)
            r["complete"] = r.get("complete") != "0"
        return kept

    rows = read("scores.csv")
    if rows is None:
        raise SystemExit("No analysis/scores.csv. Run extract_scores.py first.")
    for r in rows:
        for k in keys:
            r[k] = float(r[k])
        r["position"] = int(r["position"]) if r.get("position") else None
    ranks = read("rankings.csv") or []
    for r in ranks:
        r["rank"] = int(r["rank"])
    runs = read("runs.csv")
    if runs is None:  # exported before runs.csv existed: the runs with score rows are all that is known
        by = defaultdict(list)
        for r in rows:
            by[run_key(r)].append(r)
        runs = [{"run": pl.run_id(*k), "persona_id": k[0], "model": k[1], "replicate": k[2],
                 "segment": rr[0]["segment"], "complete": rr[0]["complete"],
                 "state": "done" if rr[0]["complete"] else "partial", "has_final": rr[0]["complete"],
                 "written": [r["concept"] for r in rr], "scored": [r["concept"] for r in rr]}
                for k, rr in by.items()]
    else:
        for r in runs:
            r["written"], r["scored"] = r["written"].split(), r["scored"].split()
            r["has_final"] = r["has_final"] == "1"
    return rows, ranks, runs


def leaderboard(rows, ranks, labels):
    by = defaultdict(list)
    for r in rows:
        by[r["concept"]].append(r["overall"])
    runs = defaultdict(list)
    for r in ranks:
        runs[run_key(r)].append(r)
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
    all_rows, all_ranks, runs = load(sd, keys, set(args.exclude_model), seg_filter)
    if not runs:
        raise SystemExit("No runs to analyse. Run extract_scores.py first, and check the filters.")
    rows = [r for r in all_rows if r["complete"]]  # every headline table reads these and nothing else
    ranks = [r for r in all_ranks if r["complete"]]
    models = [m for m in pl.model_keys(cfg) if any(r["model"] == m for r in rows)]
    names = {p["id"]: p["name"] for p in cfg["personas"]}
    roles = {p["id"]: p["role"] for p in cfg["personas"]}
    res = {"filters": {"exclude_models": args.exclude_model, "segment": args.segment}}
    md = [f"# Quantitative analysis: {sd.name}", ""]
    if args.exclude_model or args.segment:
        md += [f"Filters: excluded models {args.exclude_model or 'none'}; segment {args.segment or 'all'}.", ""]
    n_runs = len({run_key(r) for r in rows})
    base = args.out or ("quant" + (f"-{args.segment.replace(',', '+')}" if args.segment else "") +
                        "".join(f"-no-{m}" for m in args.exclude_model))

    def write(printed):
        (sd / "analysis" / f"{base}.md").write_text("\n".join(md))
        (sd / "analysis" / f"{base}.json").write_text(json.dumps(res, indent=2, default=str))
        print("\n".join(printed))
        print(f"Wrote analysis/{base}.md and analysis/{base}.json")

    # Incomplete runs: counted, listed in their own table, and kept out of everything else
    partial = defaultdict(dict)  # incomplete run -> {concept: Overall}
    for r in all_rows:
        if not r["complete"]:
            partial[run_key(r)][r["concept"]] = r["overall"]
    unfinished = [r for r in runs if not r["complete"]]
    listed = [{"run": r["run"], "persona": r["persona_id"], "model": r["model"], "replicate": r["replicate"],
               "segment": r["segment"], "state": r["state"], "written": r["written"], "scored": r["scored"],
               "has_final": r["has_final"], "overall": partial.get(run_key(r), {})}
              for r in unfinished if r["written"] or r["state"] in LISTED_STATES]
    not_started = len(unfinished) - len(listed)
    res["runs"] = {"complete": len(runs) - len(unfinished), "expected": len(runs), "not_started": not_started,
                   "incomplete": listed}
    runs_line = f"- {res['runs']['complete']} of {len(runs)} runs complete." + (
        ' Every table uses complete runs only, except "Incomplete runs".' if unfinished and rows else "")
    inc_md = []
    if unfinished:
        inc_md = ["## Incomplete runs", "", "These runs are in no other table. The concept columns show the Overall "
                  "score each run gave before it stopped: partial evidence, not results.", ""]
        if listed:
            inc_md += [table(
                ["Run", "Persona", "State", "Sections written", "Scored", "Final sections", *labels],
                [[d["run"], names.get(d["persona"], ""), d["state"], f"{len(d['written'])} of {len(labels)}",
                  f"{len(d['scored'])} of {len(labels)}", "yes" if d["has_final"] else "no",
                  *[f"{d['overall'][c]:g}" if c in d["overall"] else "-" for c in labels]] for d in listed]), ""]
        if not_started:
            inc_md += [f"Runs not started, or running with nothing written yet: {not_started}.", ""]
    if not rows:
        md += ["## Key numbers", "", runs_line, "- No run is complete, so there is nothing to rank.", "", *inc_md]
        return write(md)

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
    overall = defaultdict(dict)  # run -> {concept: Overall}
    for r in rows:
        overall[run_key(r)][r["concept"]] = r["overall"]
    ranked_first = {run_key(r): r["concept"] for r in ranks if r["rank"] == 1}

    def runs_of(pid, m):  # a persona's runs on one model: one per replicate
        return [k for k in sorted(overall) if k[:2] == (pid, m)]

    def agreement(pid, a, b):  # Spearman for every pairing of the persona's runs on two models
        vals = []
        for ka, kb in itertools.product(runs_of(pid, a), runs_of(pid, b)):
            xa, xb = overall[ka], overall[kb]
            common = [c for c in labels if c in xa and c in xb]
            if len(common) >= 3:
                v = pl.spearman([xa[c] for c in common], [xb[c] for c in common])
                if v == v:
                    vals.append(v)
        return vals

    pair_agree = {}
    for a, b in itertools.combinations(models, 2):
        vals = [v for pid in sorted({r["persona_id"] for r in rows}) for v in agreement(pid, a, b)]
        pair_agree[f"{a}-{b}"] = mean(vals) if vals else None
    persona_agree = []
    for pid in sorted({r["persona_id"] for r in rows}):
        per = {m: runs_of(pid, m) for m in models}
        per = {m: v for m, v in per.items() if v}
        vals = [v for a, b in itertools.combinations(per, 2) for v in agreement(pid, a, b)]
        tops, firsts = {}, set()
        for m, keys_m in per.items():
            mine = []
            for run in keys_m:
                best = max(overall[run].values())
                mine.append(ranked_first.get(run) or "=".join(c for c in labels if overall[run].get(c) == best))
            tops[m] = "/".join(dict.fromkeys(mine))  # replicates that disagree show as A/B
            firsts.update(mine)
        persona_agree.append({"persona": pid, "spearman": mean(vals) if vals else None, "tops": tops,
                              "same_top": len(firsts) == 1})
    full_order = [d["mean"] for d in sorted(lb, key=lambda d: d["concept"])]
    sens = {}
    for m in models:
        sub = [r for r in rows if r["model"] != m]
        means = [mean([r["overall"] for r in sub if r["concept"] == c]) for c in sorted(labels)]
        if len(models) > 1:
            win = sorted(labels)[max(range(len(means)), key=lambda i: means[i])]
            sens[m] = {"winner": win, "rho_vs_full": pl.spearman(full_order, means)}
    res["models"] = {"level": level, "per_model": per_model, "pair_spearman": pair_agree, "drop_one": sens,
                     "persona_agreement": persona_agree}

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
                run_best[run_key(r)] = max(run_best[run_key(r)], r["overall"])
        fit.append({"persona": p, "name": names.get(p, ""), "role": roles.get(p, ""),
                    "segment": next((r["segment"] for r in rows if r["persona_id"] == p), ""),
                    "fit": mean([mean([r[f] for f in ff]) for r in pr]),
                    "best_overall": mean(list(run_best.values()))})
    fit.sort(key=lambda d: -d["fit"])
    res["fit"] = {"factors": ff, "concepts": best, "personas": fit}

    # ---------------------------------------------------------------- markdown
    w = lb[0]
    gap = w["mean"] - lb[1]["mean"] if len(lb) > 1 else 0
    md += ["## Key numbers", "", runs_line,
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
            [[cfg["segments"].get(s, s), len({run_key(r) for r in rows if r["segment"] == s}),
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

    if len(models) > 1:
        weak = [d["persona"] for d in persona_agree
                if not d["same_top"] and (d["spearman"] is None or d["spearman"] < 0.3)]
        md += ["## Model agreement by persona", "",
               "Spearman across a persona's model runs, and each run's first-ranked concept (ties shown as 12=13 when a run has no ranking). A persona whose models disagree "
               "tells you about model taste, not the persona: report its result as unsettled.", "",
               table(["Persona", "Spearman", *models, "Same top"],
                     [[f"{d['persona']} {names.get(d['persona'], '')}", fmt(d["spearman"]),
                       *[d["tops"].get(m, "-") for m in models], "yes" if d["same_top"] else "no"]
                      for d in persona_agree]), ""]
        if weak:
            md += [f"Unsettled personas (different top concepts and Spearman under 0.3): {', '.join(weak)}.", ""]

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

    md += inc_md
    write(md[: md.index("## Leaderboard")])


if __name__ == "__main__":
    main()
