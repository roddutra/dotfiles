#!/usr/bin/env python3
"""Scaffold a persona-panel study from <study>/study.json.

Creates the neutral panel folder (site copies, instructions, persona files), the lead-only
key, one run prompt per persona x model, and runs.json. Deterministic for a given seed.

Usage: init_study.py <study-dir> [--force]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402

DEFAULT_MODEL_NOTES = {
    "haiku": [
        "Your context is limited: for each concept view only `desktop-sheet-01.png`, `mobile-first-screens.png` and at most two more sheets, rely on `page-text.txt` for the rest, and never open raw/ files.",
        "Every concept has complete materials. If something seems missing, read `page-text.txt` again rather than skipping the concept.",
        "For the final score summary, re-read your own persona file to collect your scores.",
    ],
}

DEFAULT_IGNORE = [".git", "*.bak", ".DS_Store", "node_modules"]


def factor_table(cfg):
    rows = ["| Factor | What it means |", "|---|---|"]
    for f in cfg["factors"]:
        label = f"**{f['label']}**" if f["key"] == "overall" else f["label"]
        rows.append(f"| {label} | {f['question']} |")
    return "\n".join(rows)


def score_table(cfg):
    heads = [f["label"] for f in cfg["factors"]]
    return "\n".join([
        "| " + " | ".join(heads) + " |",
        "|" + "---|" * len(heads),
        "| " + " | ".join("n" for _ in heads) + " |",
    ])


def concept_template(cfg, multi_page):
    t = ["### Concept <label>"]
    if multi_page:
        t.append("**Pages I looked at:** ...")
    t += [
        "**5-second take (in my words):** ...",
        "**What I'd do in real life:** keep reading / skim then leave / close the tab, and why.",
        "**What worked for me:** ...",
        "**What confused, annoyed or put me off:** ...",
        "**Questions it left me with:** ...",
        "**Explain it back:** in two sentences, what this product does and who it's for, as I'd tell a colleague.",
    ]
    if cfg["find_the_answer"]:
        t.append("**Could I find the answer?** For each question, say Found (and where: page and section), Partly or Not found.")
        t += [f"- {q}" for q in cfg["find_the_answer"]]
    t += [
        '**One line to keep:** "..." (the strongest line, quoted exactly)',
        '**One line to cut:** "..." (quoted exactly)',
        '**One line I don\'t believe:** "..." (quoted exactly, or "none")',
        "**Would I forward it?** yes/no, to whom, and the one-line message I'd send with it.",
        '**Quote (my gut reaction, one line):** "..."',
        "",
        score_table(cfg),
    ]
    return "\n".join(t)


def final_template(cfg, labels):
    shorts = [f.get("short", f["label"]) for f in cfg["factors"]]
    t = ["## Comparison", "### My ranking (best to worst)"]
    t += [f"{i + 1}. Concept <label> - one-line reason" for i in range(len(labels))]
    t += [
        "",
        "### Score summary",
        "| Concept | " + " | ".join(shorts) + " |",
        f"(one row per concept, in label order {labels[0]} to {labels[-1]})",
        "",
        "## What I'd need to see to say yes",
        "- The problems that would get my attention, in my own words",
        "- The questions a page must answer for someone like me, most important first",
        "- Any dealbreakers or red flags",
    ]
    t += [f"- {b}" for b in cfg.get("extra_yes_bullets", [])]
    t += [
        "",
        "## Language check",
        "- Words, names or ideas that confused me or felt like jargon or hype",
        "- Phrases that landed and I'd repeat to a colleague",
        "",
        "## If I could design it",
        "Five to ten bullets: the ideal version for someone like me, borrowing the best bits of any concept (name them).",
        "",
        "## Out of character: researcher notes",
        "A few honest notes stepping outside the persona: what this person would likely do that an AI simulation might miss, anything you could not properly assess, and anything in the materials that looked broken, such as clipped text, overlaps or empty panels.",
    ]
    return "\n".join(t)


def persona_doc(p, model, order):
    rows = [
        f"# {p['id']} - {p['name']}, {p['role']}",
        "",
        "| | |",
        "|---|---|",
        f"| Persona id | {p['id']} |",
        f"| Role | {p['role']} |",
        f"| Personality type | {p['personality']} |",
        f"| Model | `{model}` |",
        f"| Review order | {', '.join(order)} |",
        "",
        "## Persona",
        f"You are **{p['name']}**.",
    ]
    rows += [f"- {b}" for b in p.get("bio", [])]
    rows += ["", "## Feedback", ""]
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("--force", action="store_true", help="overwrite existing persona files and site copies")
    args = ap.parse_args()

    cfg = pl.load_study(args.study_dir)
    sd = cfg["_dir"]
    panel = sd / "panel"
    lmap = pl.label_map(cfg)
    labels = list(lmap)

    existing = list((panel / "personas").glob("*.md"))
    if existing and not args.force:
        raise SystemExit(f"{len(existing)} persona files already exist. Re-run with --force to overwrite them.")

    for c in cfg["concepts"]:
        if not (c["_path"] / "index.html").exists():
            raise SystemExit(f"Concept {c['id']}: no index.html in {c['_path']}")

    for sub in ("personas", "materials", "scratch", "sites"):
        (panel / sub).mkdir(parents=True, exist_ok=True)
    for sub in ("prompts", "analysis"):
        (sd / sub).mkdir(exist_ok=True)

    multi_page = False
    for label, c in lmap.items():
        dest = panel / "sites" / f"concept-{label}"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(c["_path"], dest, ignore=shutil.ignore_patterns(*DEFAULT_IGNORE, *cfg.get("copy_ignore", [])))
        pages = sorted(p.name for p in dest.glob("*.html"))
        c["_pages"] = pages
        multi_page = multi_page or len(pages) > 1

    n = len(labels)
    values = dict(
        n=n,
        artefact_plural=cfg.get("artefact_plural", "draft website designs"),
        product_phrase=cfg.get("product_phrase", f"a product called **{cfg['product']}**"),
        label_list=", ".join(f"Concept {l}" for l in labels[:-1]) + f" and Concept {labels[-1]}",
        context_bullets="".join(f"- {b}\n" for b in cfg["context_notes"]),
        arrival=cfg.get("arrival", "a colleague, a partner or an online ad sent you there"),
        panel_dir=str(panel),
        desktop_size="x".join(str(v) for v in cfg.get("capture", {}).get("desktop", [1440, 900])),
        factor_table=factor_table(cfg),
        concept_template=concept_template(cfg, multi_page),
        final_template=final_template(cfg, labels),
    )
    (panel / "_panel-instructions.md").write_text(pl.render_template("panel-instructions.md", **values))

    model_notes = {**DEFAULT_MODEL_NOTES, **cfg.get("model_notes", {})}
    runs = []
    for p in cfg["personas"]:
        order = pl.review_order(cfg, p["id"], labels)
        p["_order"] = order
        for model in cfg["models"]:
            pf = pl.persona_file(sd, p, model)
            pf.write_text(persona_doc(p, model, order))
            rid = pl.run_id(p["id"], model)
            notes = "".join(f"- {x}\n" for x in model_notes.get(model, []))
            prompt = pl.render_template(
                "run-prompt.md", artefact_plural=values["artefact_plural"], panel_dir=str(panel),
                persona_file=str(pf), n=n, run_id=rid, model_notes=notes)
            pp = sd / "prompts" / f"{rid}.md"
            pp.write_text(prompt)
            runs.append({"run": rid, "persona": p["id"], "name": p["name"], "segment": p.get("segment", ""),
                         "model": model, "file": str(pf.relative_to(sd)), "prompt": str(pp.relative_to(sd))})
    (sd / "runs.json").write_text(json.dumps(runs, indent=2) + "\n")

    key = ["# Concept key (lead only, never give to panellists)", "",
           "| Label | Concept | Source | Pages |", "|---|---|---|---|"]
    key += [f"| {l} | {c['id']} | `{c['_path']}` | {', '.join(c['_pages'])} |" for l, c in lmap.items()]
    key += ["", "## Review orders", "", "| Persona | Order |", "|---|---|"]
    key += [f"| {p['id']} {p['name']} | {', '.join(p['_order'])} |" for p in cfg["personas"]]
    (sd / "key.md").write_text("\n".join(key) + "\n")

    print(f"Study {sd.name}: {n} concepts ({', '.join(labels)}), {len(cfg['personas'])} personas x "
          f"{len(cfg['models'])} models = {len(runs)} runs")
    print(f"Next: capture.py {sd}")


if __name__ == "__main__":
    main()
