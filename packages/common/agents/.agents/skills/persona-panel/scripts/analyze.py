#!/usr/bin/env python3
"""Quantitative analysis of a panel: writes analysis/quant.md and analysis/quant.json.

Reads analysis/scores.csv, rankings.csv and runs.csv (run extract_scores.py first) and covers:
  leaderboard (mean, median, sd, firsts, Borda, top/bottom counts), factor means and leaders,
  which factors drive Overall, segments, per-model levels and agreement, sensitivity to
  dropping each model, persona x concept matrix, order effect, and persona fit (ICP signal).

A run is one persona on one model key and one replicate. Replicates are counted and compared as
separate runs, never merged into one. A scores.csv without a replicate column reads as replicate 1.
A study with replicates gets "Replicate spread" beside model agreement: for each persona and
model key with more than one complete replicate, how closely the replicates' Overall scores agree
(Spearman with three or more concepts, and the share of concepts given the same score), their
mean absolute difference per concept and whether they put the same concept first, then one line
per model key. A finding the replicates of one model disagree on is not stable.

A persona with "variant_of" in study.json is a variant of that persona. It counts as a persona
of its own in every table. It is also shown under its parent in the persona matrix and the
persona fit table, with its difference from the parent in brackets, and "Variants" compares the
two on the strongest concepts, over the model keys both have complete runs on.

When analysis/answers.csv and analysis/lines.csv exist (extract_answers.py), "Find the answer"
counts Found, Partly, Not found, missing and unparsed for each question and concept, "Forward
test" counts yes, no and maybe for each concept, and "Lines that recur" lists the lines more than
one run quoted as the line to keep, to cut or the one not believed (matched ignoring case, quote
style, spacing and a closing full stop). Without those files the tables are left out.

quant.json has "replicates", "variants", "answers" and "lines" when their tables were written.

A study with one concept has nothing to rank or compare, so its report has no leaderboard, no
winner, no Borda count and no order effect, and says so. It has "Scores" in their place: each
factor's mean, median and spread across the runs. "By segment" and "By model" give every factor's
mean, and model agreement is measured on the one concept: the mean absolute difference between a
persona's runs on two models, in Overall and over all factors, and the Spearman across the factor
scores the two runs gave (whether the models agree on what is strong and weak). Spearman across
concepts needs three of them and is named as not available. quant.json then has "concept" and
"scores" and no "leaderboard" or "order".

When the concepts did not all reach the panel in one form (a PDF beside a captured page, or beside
a screenshot: panel_lib.mixed_forms), part of any difference between them is the format. The
report says so above "Key numbers" and under "By factor", naming each concept's form and the
factors most exposed, the ones that need the design. quant.json then has "forms". Both are the
lead's files: nothing a panellist reads says what a concept is made of. Whether a "files" concept
is images or PDFs is read from its source files, and from forms.json when they are gone, as in an
archived round (panel_lib.py, "Forms").

Every one of those tables uses complete runs only, and the output states "N of M runs complete",
where M is the runs expected after the filters. Incomplete runs that wrote something, or that
stopped as partial, limited, blocked or failed, get their own table, "Incomplete runs", with
their state, what they wrote and their Overall scores: those scores appear nowhere else, and
their answers and lines stay in the CSVs. When no run is complete there is nothing to rank, and
the output is that count and that table.

Exports from before the "complete" column and runs.csv existed read as all complete: the runs
with score rows are then the runs expected.

Filters. --exclude-model <key>, --exclude-persona <id> (each repeatable, or comma-separated) and
--segment <a,b> leave runs out of everything: the score rows, the rankings, the runs expected,
"Incomplete runs" and the answer and line tallies. The output names them in a "Filters" line and
goes to its own files, for example quant-no-haiku or quant-no-P03, so the unfiltered quant.md
stays. --exclude-persona is how a variant written only to test a trait is kept out of the
headline: read "Variants" in the unfiltered view, which has both sides of the pair.

Usage: analyze.py <study-dir> [--exclude-model haiku] [--exclude-persona P03] [--segment mortgage]
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
from panel_lib import fmt, mean, plural  # noqa: E402


# Incomplete runs in these states are listed even when they wrote nothing: they ran and stopped.
# Pending and running ones that wrote nothing are only counted.
LISTED_STATES = ("partial", "limited", "blocked", "failed")


def run_key(r: dict) -> tuple:
    return r["persona_id"], r["model"], r["replicate"]


def read_csv(sd: Path, name: str, filters: dict) -> list[dict] | None:
    """The rows of analysis/<name> left by the filters, or None when there is no such file.
    filters is {"models", "personas"} (the model keys and persona ids left out) and "segment"
    (the segments kept, None for all)."""
    path = sd / "analysis" / name
    if not path.exists():
        return None
    with open(path) as f:
        kept = [r for r in csv.DictReader(f)
                if r["model"] not in filters["models"] and r["persona_id"] not in filters["personas"]
                and (not filters["segment"] or r["segment"] in filters["segment"])]
    for r in kept:
        r["replicate"] = int(r.get("replicate") or 1)
        r["complete"] = r.get("complete") != "0"
    return kept


def load(sd: Path, keys: list[str], filters: dict):
    """Score rows, ranking rows and run records left by the filters (read_csv), complete or not."""
    def read(name):
        return read_csv(sd, name, filters)

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


def signed(x, nd=2):
    return "-" if x is None or x != x else f"{x:+.{nd}f}"


def known(xs):
    """The mean of xs, or None when there is nothing to take one of."""
    xs = [x for x in xs if x is not None and x == x]
    return mean(xs) if xs else None


def without_nan(x):
    """x with every NaN made None, through dicts and lists: NaN is not JSON, and a reader that
    is strict about it cannot load the file."""
    if isinstance(x, dict):
        return {k: without_nan(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [without_nan(v) for v in x]
    return None if isinstance(x, float) and x != x else x


def under_parents(pids: list[str], variant_of: dict[str, str]) -> list[str]:
    """pids with each variant moved to sit directly under its parent, when the parent is listed."""
    kids = defaultdict(list)
    for p in pids:
        if variant_of.get(p) in pids:
            kids[variant_of[p]].append(p)
    moved = {p for ps in kids.values() for p in ps}
    return [x for p in pids if p not in moved for x in (p, *kids[p])]


ANSWER_COUNTS = {"Found": "found", "Partly": "partly", "Not found": "not_found", "missing": "missing"}
FORWARD_COUNTS = ("yes", "no", "maybe", "missing")


def tally_answers(rows: list[dict], labels: list[str]) -> list[dict]:
    """answers.csv rows -> one entry per question: its number, text, and for each concept the
    count of each verdict. A verdict that is none of ANSWER_COUNTS counts as unparsed."""
    out = {}
    for r in sorted(rows, key=lambda r: int(r["question"])):
        q = out.setdefault(r["question"], {"question": int(r["question"]), "text": r["question_text"], "concepts": {
            c: dict.fromkeys([*ANSWER_COUNTS.values(), "unparsed"], 0) for c in labels}})
        if r["concept"] in q["concepts"]:
            q["concepts"][r["concept"]][ANSWER_COUNTS.get(r["verdict"], "unparsed")] += 1
    return list(out.values())


def tally_lines(rows: list[dict], labels: list[str]) -> dict:
    """lines.csv rows -> "forward": for each concept the count of each answer; "recurring": for
    each concept the lines more than one run quoted, most quoted first, each with the number of
    runs that quoted it at all and as the line to keep, to cut and the one not believed;
    "unparsed": the line entries that could not be read."""
    forward = {c: dict.fromkeys([*FORWARD_COUNTS, "unparsed"], 0) for c in labels}
    quoted = {c: {} for c in labels}  # concept -> line as pl.same_line has it -> its entry
    unparsed = 0
    for r in rows:
        if r["concept"] not in forward:
            continue
        if r["entry"] == "forward":
            forward[r["concept"]][r["status"] if r["status"] in FORWARD_COUNTS else "unparsed"] += 1
        elif r["entry"] in pl.LINE_FIELDS and r["status"] in ("quoted", "unquoted") and pl.same_line(r["text"]):
            line = quoted[r["concept"]].setdefault(pl.same_line(r["text"]), {
                "line": r["text"], "by": set(), **{k: set() for k in pl.LINE_FIELDS}})
            line["by"].add(run_key(r))
            line[r["entry"]].add(run_key(r))
        elif r["entry"] in pl.LINE_FIELDS:
            unparsed += r["status"] == "unparsed"
    recurring = {c: sorted(({"line": d["line"], "runs": len(d["by"]), **{k: len(d[k]) for k in pl.LINE_FIELDS}}
                            for d in lines.values() if len(d["by"]) > 1), key=lambda d: -d["runs"])
                 for c, lines in quoted.items()}
    return {"forward": forward, "recurring": recurring, "unparsed": unparsed}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("--exclude-model", action="append", default=[], metavar="KEY",
                    help="leave a model key out (repeatable, or comma-separated)")
    ap.add_argument("--exclude-persona", action="append", default=[], metavar="ID",
                    help="leave a persona out, by id (repeatable, or comma-separated)")
    ap.add_argument("--segment", help="restrict to persona segments (comma-separated)")
    ap.add_argument("--out", help="output basename in analysis/ (default quant, with -<segment>, -no-<model key> "
                                  "and -no-<persona id> added for the filters)")
    args = ap.parse_args()
    no_models, no_personas = ([x.strip() for given in flag for x in given.split(",") if x.strip()]
                              for flag in (args.exclude_model, args.exclude_persona))
    cfg = pl.load_study(args.study_dir)
    sd = cfg["_dir"]
    keys = pl.factor_keys(cfg)
    labels = list(pl.label_map(cfg))
    fl = {f["key"]: f["label"] for f in cfg["factors"]}
    unknown = [p for p in no_personas if p not in {q["id"] for q in cfg["personas"]}]
    if unknown:
        raise SystemExit(f"--exclude-persona: no persona called {', '.join(unknown)}. There are: "
                         f"{', '.join(q['id'] for q in cfg['personas'])}")
    filters = {"models": set(no_models), "personas": set(no_personas),
               "segment": set(args.segment.split(",")) if args.segment else None}
    all_rows, all_ranks, runs = load(sd, keys, filters)
    if not runs:
        raise SystemExit("No runs to analyse. Run extract_scores.py first, and check the filters.")
    rows = [r for r in all_rows if r["complete"]]  # every headline table reads these and nothing else
    ranks = [r for r in all_ranks if r["complete"]]
    models = [m for m in pl.model_keys(cfg) if any(r["model"] == m for r in rows)]
    names = {p["id"]: p["name"] for p in cfg["personas"]}
    roles = {p["id"]: p["role"] for p in cfg["personas"]}
    variant_of = pl.variants(cfg)

    def who(pid):  # how a table names a persona
        return f"{pid} {names.get(pid, '')}" + (f" (variant of {variant_of[pid]})" if pid in variant_of else "")
    res = {"filters": {"exclude_models": no_models, "exclude_personas": no_personas, "segment": args.segment}}
    md = [f"# Quantitative analysis: {sd.name}", ""]
    if no_models or no_personas or args.segment:
        md += [f"Filters: excluded models {', '.join(no_models) or 'none'}; excluded personas "
               f"{', '.join(no_personas) or 'none'}; segment {args.segment or 'all'}.", ""]
    # Concepts of different forms are compared partly on format: said before any number, and by the factors
    caution = pl.form_caution(cfg)
    if caution:
        res["forms"] = {"concepts": caution["forms"], "exposed_factors": caution["factors"]}
        md += [f"Format caution: the concepts did not all reach the panel in one form. Concept {caution['concepts']}. "
               "Part of any difference between them is the format, not the design: a PDF or an image cannot be "
               f"scrolled or clicked, and shows a phone only if the file holds one. {caution['exposed']}: compare "
               "those within one form only, or leave them out, and remember that Overall and the rankings carry them "
               "too.", ""]
    n_runs = len({run_key(r) for r in rows})
    base = args.out or ("quant" + (f"-{args.segment.replace(',', '+')}" if args.segment else "") +
                        "".join(f"-no-{x}" for x in [*no_models, *no_personas]))
    if pl.name_problem(base):  # it names analysis/<base>.md and .json, and must stay there
        raise SystemExit(f"The output name {base!r} {pl.NAME_RULE}. Give another with --out.")

    def write(printed):
        (sd / "analysis" / f"{base}.md").write_text("\n".join(md))
        (sd / "analysis" / f"{base}.json").write_text(json.dumps(without_nan(res), indent=2, default=str))
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
    runs_line = f"- {res['runs']['complete']} of {plural(len(runs), 'run')} complete." + (
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

    # Leaderboard. One concept is not ranked: its scores are reported in the leaderboard's place.
    single = pl.single_concept(cfg)
    lb, ranked_runs, k = leaderboard(rows, ranks, labels)
    if not single:
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

    def top_of(run):  # the concept a run ranked first, or the ones it scored highest when it ranked none
        best = max(overall[run].values())
        return ranked_first.get(run) or "=".join(c for c in labels if overall[run].get(c) == best)

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
            mine = [top_of(run) for run in keys_m]
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

    # One concept: the spread across runs, and model agreement on that concept's scores
    if single:
        only = labels[0]
        profile = {run_key(r): [r[f] for f in keys] for r in rows}  # run -> its score for every factor
        scores = {}
        for f in keys:
            xs = [r[f] for r in rows]
            scores[f] = {"n": len(xs), "mean": mean(xs), "median": statistics.median(xs), "sd": pl.sd(xs),
                         "min": min(xs), "max": max(xs)}
        pair_diff = {}
        for a, b in itertools.combinations(models, 2):
            ov, fa, rho = [], [], []
            for pid in sorted({r["persona_id"] for r in rows}):
                for ka, kb in itertools.product(runs_of(pid, a), runs_of(pid, b)):
                    ov.append(abs(profile[ka][-1] - profile[kb][-1]))
                    fa.append(mean([abs(x - y) for x, y in zip(profile[ka], profile[kb])]))
                    rho.append(pl.spearman(profile[ka], profile[kb]))
            pair_diff[f"{a}-{b}"] = {"pairs": len(ov), "overall": known(ov), "factors": known(fa),
                                     "profile_spearman": known(rho)}
        by_persona = []
        for pid in sorted({r["persona_id"] for r in rows}):
            per = {m: known([profile[run][-1] for run in runs_of(pid, m)]) for m in models}
            got = [v for v in per.values() if v is not None]
            by_persona.append({"persona": pid, "overall": per, "spread": max(got) - min(got) if len(got) > 1 else None})
        whole = scores["overall"]["mean"]
        drop_one = {m: {"mean": known([r["overall"] for r in rows if r["model"] != m])} for m in models
                    if len(models) > 1}
        for d in drop_one.values():
            d["change"] = d["mean"] - whole
        res.update(concept=only, scores=scores)
        res["segment_factors"] = {s: {f: mean([r[f] for r in rows if r["segment"] == s]) for f in keys} for s in segs}
        res["model_factors"] = {m: {f: mean([r[f] for r in rows if r["model"] == m]) for f in keys} for m in models}
        res["models"] = {"level": level, "per_model": per_model, "pair_difference": pair_diff, "drop_one": drop_one,
                         "persona_agreement": by_persona}

    # Replicate spread: how far one persona's repeats on one model sit from each other
    pids = sorted({r["persona_id"] for r in rows})
    spread = []
    for pid, m in itertools.product(pids, models):
        mine = runs_of(pid, m)
        if len(mine) < 2:
            continue
        rho, same, diff = [], [], []
        for a, b in itertools.combinations(mine, 2):
            xa, xb = overall[a], overall[b]
            common = [c for c in labels if c in xa and c in xb]
            v = pl.spearman([xa[c] for c in common], [xb[c] for c in common])
            if v == v:
                rho.append(v)
            same.append(mean([xa[c] == xb[c] for c in common]))
            diff.append(mean([abs(xa[c] - xb[c]) for c in common]))
        tops = [top_of(run) for run in mine]
        spread.append({"persona": pid, "model": m, "replicates": [k[2] for k in mine],
                       "spearman": mean(rho) if rho else None, "same_score": mean(same),
                       "mean_abs_diff": mean(diff), "tops": tops, "same_top": len(set(tops)) == 1})
    spread_by_model = {}
    for m in models:
        mine = [d for d in spread if d["model"] == m]
        if mine:
            rho = [d["spearman"] for d in mine if d["spearman"] is not None]
            spread_by_model[m] = {"personas": len(mine), "spearman": mean(rho) if rho else None,
                                  "same_score": mean([d["same_score"] for d in mine]),
                                  "mean_abs_diff": mean([d["mean_abs_diff"] for d in mine]),
                                  "same_top": sum(d["same_top"] for d in mine)}
    if spread:
        res["replicates"] = {"by_persona": spread, "by_model": spread_by_model}

    # Persona matrix
    pmat = {p: {c: mean([r["overall"] for r in rows if r["persona_id"] == p and r["concept"] == c])
                for c in labels} for p in pids}
    res["persona_matrix"] = pmat

    # Order effect
    pos = [(r["position"], r["overall"]) for r in rows if r["position"]]
    order_r = pl.pearson([p for p, _ in pos], [o for _, o in pos]) if pos else float("nan")
    by_pos = {p: mean([o for q, o in pos if q == p]) for p in sorted({p for p, _ in pos})}
    if not single:  # one concept has no order to review in
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
                    "variant_of": variant_of.get(p), "fit": mean([mean([r[f] for f in ff]) for r in pr]),
                    "best_overall": mean(list(run_best.values()))})
    fit.sort(key=lambda d: -d["fit"])
    res["fit"] = {"factors": ff, "concepts": best, "personas": fit}
    fit_of = {d["persona"]: d for d in fit}

    # Variants: each against its parent, over the model keys both have complete runs on
    traits = {p["id"]: p for p in cfg["personas"]}
    pairs = []
    for v, parent in variant_of.items():
        if v not in pids:
            continue
        shared = [m for m in models if runs_of(v, m) and runs_of(parent, m)]
        side = {}
        for name, pid in (("parent", parent), ("variant", v)):
            mine = [r for r in rows if r["persona_id"] == pid and r["model"] in shared]
            score = {c: mean([r["overall"] for r in mine if r["concept"] == c]) for c in labels}
            side[name] = {"runs": len({run_key(r) for r in mine}), "overall": score,
                          "fit": mean([mean([r[f] for f in ff]) for r in mine if r["concept"] in best]),
                          "top": "=".join(c for c in labels if score[c] == max(score.values())) if mine else None}
        pairs.append({
            "variant": v, "parent": parent, "models": shared,
            "differs_in": [t for t in ("role", "personality", "segment", "bio")
                           if traits[v].get(t) != traits.get(parent, {}).get(t)],
            "runs": {n: side[n]["runs"] for n in side},
            "concepts": {c: {"parent": side["parent"]["overall"][c], "variant": side["variant"]["overall"][c],
                             "diff": side["variant"]["overall"][c] - side["parent"]["overall"][c]}
                         for c in labels} if shared else {},
            "fit": {"parent": side["parent"]["fit"], "variant": side["variant"]["fit"],
                    "diff": side["variant"]["fit"] - side["parent"]["fit"]} if shared else {},
            "top": {n: side[n]["top"] for n in side} if shared else {}})
    if pairs:
        res["variants"] = pairs

    # Answers and lines, when extract_answers.py has written them
    done = {run_key(r) for r in runs if r["complete"]}
    tallies = {}
    for name in ("answers", "lines"):
        found = read_csv(sd, f"{name}.csv", filters)
        if found is not None:
            tallies[name] = [r for r in found if r["complete"] and run_key(r) in done]
    answers = lines = None
    if tallies.get("answers"):
        answers = {"runs": len({run_key(r) for r in tallies["answers"]}),
                   "questions": tally_answers(tallies["answers"], labels)}
        res["answers"] = answers
    if tallies.get("lines"):
        lines = {"runs": len({run_key(r) for r in tallies["lines"]}), **tally_lines(tallies["lines"], labels)}
        res["lines"] = lines

    # ---------------------------------------------------------------- markdown
    fs = {f["key"]: f.get("short", f["label"]) for f in cfg["factors"]}
    ranked = len(labels) >= 3  # Spearman needs three concepts
    strong = sorted(((f, v) for f, v in drivers.items() if v == v), key=lambda kv: -kv[1])
    md += ["## Key numbers", "", runs_line,
           f"- {plural(n_runs, 'run')}, {plural(len(rows), 'concept review')}, {plural(len(pids), 'persona')}, "
           f"{pl.agree(len(models), 'model')}: {', '.join(models)}."]
    if single:
        ov = scores["overall"]
        md += [f"- One concept, {only}, so nothing is ranked or compared: this report has no leaderboard, ranking, "
               "Borda count or order effect. A score here has no other concept to be read against.",
               f"- Mean Overall {fmt(ov['mean'])} across {plural(ov['n'], 'run')} (median "
               f"{fmt(ov['median'], 1)}, SD {fmt(ov['sd'])}, lowest {ov['min']:g}, highest {ov['max']:g})."]
        others = sorted(keys[:-1], key=lambda f: -scores[f]["mean"])
        if len(others) >= 4:
            md.append("- Strongest factors: " + ", ".join(f"{fl[f]} {fmt(scores[f]['mean'])}" for f in others[:2])
                      + ". Weakest: " + ", ".join(f"{fl[f]} {fmt(scores[f]['mean'])}" for f in others[:-3:-1]) + ".")
        md.append("- Overall tracks " + ", ".join(f"{fl[f]} (r {fmt(v)})" for f, v in strong[:3]) + " most closely."
                  if strong else "- What drives Overall is not computed: it needs at least three reviews whose "
                  "scores differ.")
        if pair_diff:
            md.append("- Model agreement: Spearman across concepts is not available with one concept. Mean absolute "
                      "difference in Overall between a persona's runs on two models: "
                      + ", ".join(f"{k2} {fmt(d['overall'])}" for k2, d in pair_diff.items()) + ".")
        if drop_one:
            widest = max(drop_one.items(), key=lambda kv: abs(kv[1]["change"]))
            md.append(f"- Dropping a model moves the mean Overall by at most {fmt(abs(widest[1]['change']))} "
                      f"(without {widest[0]}: {fmt(widest[1]['mean'])}).")
    else:
        w = lb[0]
        gap = w["mean"] - lb[1]["mean"]
        md += [f"- Winner on mean Overall: **{w['concept']}** ({fmt(w['mean'])}), {fmt(gap)} ahead of "
               f"{lb[1]['concept']}.",
               f"- Ranked first in {w['first']} of {plural(ranked_runs, 'run')} with a ranking."]
        top3 = sorted(drivers.items(), key=lambda kv: -(kv[1] if kv[1] == kv[1] else -9))[:3]
        md.append("- Overall tracks " + ", ".join(f"{fl[f]} (r {fmt(v)})" for f, v in top3) + " most closely.")
        if pair_agree:
            md.append("- Within-persona model agreement (Spearman): " + (
                ", ".join(f"{k2} {fmt(v)}" for k2, v in pair_agree.items()) + "." if ranked
                else f"not computed for {', '.join(pair_agree)}: it needs at least three concepts. See each persona's "
                     "top concept by model."))
        if sens:
            flips = [m for m, s in sens.items() if s["winner"] != w["concept"]]
            md.append("- Dropping any single model keeps the winner." if not flips
                      else f"- Winner changes when dropping: {', '.join(flips)}.")
    if spread:
        md.append("- Replicate spread (mean absolute difference in Overall between a persona's replicates on one "
                  "model): " + ", ".join(f"{m} {fmt(d['mean_abs_diff'])}" for m, d in spread_by_model.items()) + ".")
    if not single:
        md.append(f"- Order effect: r {fmt(order_r)} between review position and Overall.")
    if len(fit) == 1:  # one persona is neither the best fit nor the weakest
        md.append(f"- Persona fit: {fit[0]['persona']} {fit[0]['name']} {fmt(fit[0]['fit'])}, the only persona.")
    elif fit:
        md.append(f"- Best-fit persona: {fit[0]['persona']} {fit[0]['name']} (fit {fmt(fit[0]['fit'])}); "
                  f"weakest: {fit[-1]['persona']} {fit[-1]['name']} ({fmt(fit[-1]['fit'])}).")
    for d in pairs:
        if d["models"]:
            md.append(f"- Variant {d['variant']} against its parent {d['parent']} (differs in "
                      f"{', '.join(d['differs_in']) or 'no trait'}): Overall "
                      f"{', '.join(c + ' ' + signed(d['concepts'][c]['diff'], 1) for c in best)}.")
    if answers:
        total = {k: sum(q["concepts"][c][k] for q in answers["questions"] for c in labels)
                 for k in [*ANSWER_COUNTS.values(), "unparsed"]}
        md.append(f"- Find the answer, over {plural(answers['runs'], 'run')}: {total['found']} Found, "
                  f"{total['partly']} Partly, {total['not_found']} Not found, {total['missing']} missing, "
                  f"{total['unparsed']} unparsed.")
    if lines:
        total = {k: sum(d[k] for d in lines["forward"].values()) for k in [*FORWARD_COUNTS, "unparsed"]}
        md.append(f"- Would forward it, over {plural(lines['runs'], 'run')} and {plural(len(labels), 'concept')}: "
                  f"{total['yes']} yes, "
                  f"{total['no']} no, {total['maybe']} maybe, {total['missing']} missing, "
                  f"{total['unparsed']} unparsed.")
    md += ["", "Differences under about 0.4 are within noise for small panels.", ""]

    if single:
        n_done = scores["overall"]["n"]
        md += ["## Scores", "",
               f"Concept {only} over {plural(n_done, 'complete run')}. SD, Min and Max are the "
               "spread across runs.", "",
               table(["Factor", "n", "Mean", "Median", "SD", "Min", "Max"],
                     [[fl[f], d["n"], fmt(d["mean"]), fmt(d["median"], 1), fmt(d["sd"]), fmt(d["min"], 0),
                       fmt(d["max"], 0)] for f, d in scores.items()]), ""]
        md += ["## What drives Overall", ""]
        md += ["Pearson correlation of each factor with Overall across all reviews.", "",
               table(["Factor", "r"], [[fl[f], fmt(v)] for f, v in strong]), ""] if strong else [
            "Not computed: the correlation of a factor with Overall needs at least three reviews whose scores "
            "differ.", ""]
        if segs:
            md += ["## By segment", "", "Mean of each factor.", "", table(
                ["Segment", "Runs", *[fs[f] for f in keys]],
                [[cfg["segments"].get(s, s), len({run_key(r) for r in rows if r["segment"] == s}),
                  *[fmt(res["segment_factors"][s][f]) for f in keys]] for s in segs]), ""]
        md += ["## By model", "", "Mean of each factor.", "", table(
            ["Model", "Runs", *[fs[f] for f in keys]],
            [[m, len({run_key(r) for r in rows if r["model"] == m}),
              *[fmt(res["model_factors"][m][f]) for f in keys]] for m in models]), ""]
        if pair_diff:
            md += ["Agreement between models, over each pairing of one persona's runs on the two: the mean absolute "
                   f"difference in Overall and over all {len(keys)} factors, and the factor profile, which is the "
                   "Spearman across the factor scores the two runs gave (whether the models agree on what is strong "
                   "and weak, whatever level each marks at). Spearman across concepts needs at least three concepts, "
                   "so this study has none. A dash means no pairing could be compared: no persona has a complete "
                   "run on both, or a run gave every factor the same score.", "",
                   table(["Pair", "Pairings", "Overall, mean abs diff", "All factors, mean abs diff", "Factor profile"],
                         [[k2, d["pairs"], fmt(d["overall"]), fmt(d["factors"]), fmt(d["profile_spearman"])]
                          for k2, d in pair_diff.items()]), ""]
        if drop_one:
            md += ["Sensitivity (mean Overall without one model):", "",
                   table(["Dropped", "Mean Overall", "Change"],
                         [[m, fmt(d["mean"]), signed(d["change"])] for m, d in drop_one.items()]), ""]
        if len(models) > 1:
            apart = [d["persona"] for d in by_persona if d["spread"] is not None and d["spread"] >= 2]
            md += ["## Model agreement by persona", "",
                   "Each persona's mean Overall on each model, and the spread between the highest and the lowest. "
                   "A persona whose models sit 2 points or more apart tells you about model taste, not the persona: "
                   "report its result as unsettled.", "",
                   table(["Persona", *models, "Spread"],
                         [[who(d["persona"]), *[fmt(d["overall"][m], 1) for m in models], fmt(d["spread"], 1)]
                          for d in by_persona]), ""]
            if apart:
                md += [f"Unsettled personas (models 2 points or more apart): {', '.join(apart)}.", ""]
    else:
        md += ["## Leaderboard", "", table(
            ["Concept", "n", "Mean", "Median", "SD", "Min", "Ranked 1st", "Borda", f"Top {k}", f"Bottom {k}", "Mean rank"],
            [[d["concept"], d["n"], fmt(d["mean"]), fmt(d["median"], 1), fmt(d["sd"]), fmt(d["min"], 0), d["first"],
              d["borda"], d["top"], d["bottom"], fmt(d["mean_rank"])] for d in lb]), ""]

        md += ["## By factor", "", table(
            ["Factor", *labels, "Leader"],
            [[fl[f], *[fmt(fac[c][f]) for c in labels], leaders[f]] for f in keys]), ""]
        if caution:
            md += [f"Format caution: Concept {caution['concepts']}. {caution['exposed']}, so a gap between concepts "
                   "of different forms on those rows is partly the format: read them within one form only.", ""]

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
            if not ranked:
                md += ["Spearman needs at least three concepts, so this study has none: compare the models by each "
                       'persona\'s top concept, under "Model agreement by persona".', ""]
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
                         [[who(d["persona"]), fmt(d["spearman"]),
                           *[d["tops"].get(m, "-") for m in models], "yes" if d["same_top"] else "no"]
                          for d in persona_agree]), ""]
            if weak:
                md += [f"Unsettled personas (different top concepts{' and Spearman under 0.3' if ranked else ''}): "
                       f"{', '.join(weak)}.", ""]

    if spread and single:
        md += ["## Replicate spread", "",
               "One persona's replicates on one model: the Overall each gave, and the mean absolute difference "
               "between them, pair by pair. Read it beside model agreement: a result that moves this much between "
               "two runs of the same persona and model is not stable, and a gap between models no wider than this "
               "is noise.", "",
               table(["Persona", "Model", "Replicates", "Overall by replicate", "Mean abs diff"],
                     [[who(d["persona"]), d["model"], len(d["replicates"]),
                       ", ".join(f"{overall[run][only]:g}" for run in runs_of(d["persona"], d["model"])),
                       fmt(d["mean_abs_diff"])] for d in spread]), ""]
        md += [f"- {m}: {plural(d['personas'], 'persona')} with replicates, mean absolute "
               f"difference {fmt(d['mean_abs_diff'])}, the same Overall from every replicate for "
               f"{sum(x['same_score'] == 1 for x in spread if x['model'] == m)} of {d['personas']}."
               for m, d in spread_by_model.items()] + [""]
    elif spread:
            md += ["## Replicate spread", "",
                   "One persona's replicates on one model, compared pair by pair: "
                   + ("the Spearman across their Overall scores, " if ranked else "")
                   + "the share of concepts they gave the same Overall, the mean absolute difference in Overall per "
                   "concept, and the concept each replicate put first. Read it beside model agreement: a result that "
                   "moves this much between two runs of the same persona and model is not stable, and a gap between "
                   "models no wider than this is noise.", "",
                   table(["Persona", "Model", "Replicates", *(["Spearman"] if ranked else []), "Same score",
                          "Mean abs diff", "Top by replicate", "Same top"],
                         [[who(d["persona"]), d["model"], len(d["replicates"]),
                           *([fmt(d["spearman"])] if ranked else []), f"{d['same_score']:.0%}", fmt(d["mean_abs_diff"]),
                           ", ".join(d["tops"]), "yes" if d["same_top"] else "no"] for d in spread]), ""]
            md += [f"- {m}: {plural(d['personas'], 'persona')} with replicates, "
                   + (f"mean Spearman {fmt(d['spearman'])}, " if ranked else "")
                   + f"same score on {d['same_score']:.0%} of concepts, mean absolute difference "
                   f"{fmt(d['mean_abs_diff'])}, same top concept for {d['same_top']} of {d['personas']}."
                   for m, d in spread_by_model.items()] + [""]

    def beside_parent(pid, value, of, nd):  # a variant's figure, with its difference from its parent's
        parent = variant_of.get(pid)
        return fmt(value, nd) + (f" ({signed(value - of[parent], nd)})" if parent in of else "")

    md += ["## Persona x concept (mean Overall across models)", ""]
    if any(variant_of.get(p) in pids for p in pids):
        md += ["A variant sits under its parent, with its difference from the parent in brackets.", ""]
    md += [table(
        ["Persona", *labels],
        [[who(p), *[beside_parent(p, pmat[p][c], {q: pmat[q][c] for q in pids}, 1) for c in labels]]
         for p in under_parents(pids, variant_of)]), ""]

    if by_pos and not single:
        md += ["## Order effect", "", f"Pearson r between review position and Overall: {fmt(order_r)}.", "",
               table(["Position", "Mean Overall"], [[p, fmt(v)] for p, v in by_pos.items()]), ""]

    md += ["## Persona fit (ICP signal)", "",
           (f"Mean of {', '.join(fl[f] for f in ff)} on the concept. Read as: how strongly the offer resonated "
            "with each persona." if single else
            f"Mean of {', '.join(fl[f] for f in ff)} on the strongest concepts ({', '.join(best)}). "
            "Read as: how strongly the best version of the offer resonated with each persona."), "",
           table(["Persona", "Role", "Segment", "Fit", "Mean Overall" if single else "Best Overall per run"],
                 [[who(p), d["role"], d["segment"], beside_parent(p, d["fit"], {q: fit_of[q]["fit"] for q in pids}, 2),
                   fmt(d["best_overall"])]
                  for p in under_parents([d["persona"] for d in fit], variant_of) for d in [fit_of[p]]]), ""]

    if pairs:
        def both(parent, variant, nd=1):
            return f"{fmt(parent, nd)} / {fmt(variant, nd)} ({signed(variant - parent, nd)})"

        compared = [d for d in pairs if d["models"]]
        md += ["## Variants", "",
               "A variant is its parent persona with one trait changed, so the difference between the two is "
               "what that trait did. Each cell is parent / variant (difference): mean Overall on "
               + ("the concept" if single else f"the strongest concepts ({', '.join(best)})")
               + ", then persona fit, over the complete runs on the model keys both "
               "have. In every other table a variant counts as a persona of its own.", ""]
        if compared:
            md += [table(
                ["Variant", "Parent", "Differs in", "Models", "Runs", *best, "Fit",
                 *([] if single else ["Top concept"])],
                [[f"{d['variant']} {names.get(d['variant'], '')}", f"{d['parent']} {names.get(d['parent'], '')}",
                  ", ".join(d["differs_in"]) or "-", ", ".join(d["models"]),
                  f"{d['runs']['parent']} / {d['runs']['variant']}",
                  *[both(d["concepts"][c]["parent"], d["concepts"][c]["variant"]) for c in best],
                  both(d["fit"]["parent"], d["fit"]["variant"], 2),
                  *([] if single else [f"{d['top']['parent']} / {d['top']['variant']}"])]
                 for d in compared]), ""]
        if len(compared) < len(pairs):
            md += ["Nothing to compare, because the runs analysed here have no parent and variant on the same "
                   "model key: " + ", ".join(f"{d['variant']} (of {d['parent']})" for d in pairs if not d["models"])
                   + ".", ""]

    def behind(what, n):  # says so when a tally covers fewer runs than the tables above
        return "" if n == len(done) else (f" The {what} cover {n} of the {plural(len(done), 'complete run')}: run "
                                          "extract_answers.py again.")

    if answers:
        md += ["## Find the answer", "",
               "Whether each panellist could find the answer to each question, over "
               f"{plural(answers['runs'], 'complete run')}. Unparsed means the answer does not start with Found, "
               "Partly or Not found: read those in analysis/answers.csv, they are counted nowhere else. Missing "
               "means the panellist gave the question no answer." + behind("answers", answers["runs"]), "",
               table(["Question", "Concept", "Found", "Partly", "Not found", "Missing", "Unparsed"],
                     [[f"{q['question']}. {q['text']}" if c == labels[0] else "", c,
                       *[q["concepts"][c][k] for k in [*ANSWER_COUNTS.values(), "unparsed"]]]
                      for q in answers["questions"] for c in labels]), ""]

    if lines:
        md += ["## Forward test", "",
               f"Whether each panellist would forward the page, over {plural(lines['runs'], 'complete run')}. "
               "Unparsed means the answer starts with none of yes, no and maybe: read those in analysis/lines.csv, where "
               "who they would send it to and the message are too." + behind("lines", lines["runs"]), "",
               table(["Concept", "Yes", "No", "Maybe", "Missing", "Unparsed"],
                     [[c, *[lines["forward"][c][k] for k in [*FORWARD_COUNTS, "unparsed"]]] for c in labels]), ""]
        recurring = [(c, d) for c in labels for d in lines["recurring"][c]]
        md += ["## Lines that recur", "",
               "Lines more than one run quoted for a concept, with how many runs quoted each as the line to keep, "
               "the line to cut and the one they don't believe. Two quotations are the same line when they "
               "differ only in case, quote style, spacing or a closing full stop."
               + (f" {plural(lines['unparsed'], 'line entry', 'line entries')} could not be read and "
                  f"{pl.agree(lines['unparsed'], 'is', 'are')} not counted: see analysis/lines.csv."
                  if lines["unparsed"] else ""), ""]
        md += [table(["Concept", "Line", "Runs", "Keep", "Cut", "Not believed"],
                     [[c, '"' + d["line"].replace("|", "\\|") + '"', d["runs"], *[d[k] for k in pl.LINE_FIELDS]]
                      for c, d in recurring]) if recurring else "No line was quoted by more than one run.", ""]

    md += inc_md
    write(md[: md.index("## Scores" if single else "## Leaderboard")])


if __name__ == "__main__":
    main()
