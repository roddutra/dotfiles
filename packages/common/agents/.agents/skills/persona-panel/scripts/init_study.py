#!/usr/bin/env python3
"""Scaffold a persona-panel study from <study>/study.json.

Creates the neutral panel folder (site copies, instructions, persona files), the lead-only
key, one run prompt per persona x model entry x replicate, and runs.json (schema in
panel_lib.py). Deterministic for a given seed. Each persona reviews in an order of its own, the
same on every model and replicate, and a variant ("variant_of") reviews in its parent's order.

study.json "browse" (default true) says whether panellists may open pages with the agent-browser
CLI. When false, the instructions and the run prompts leave the browser out. When true, a run
on a runner that cannot drive a browser is told so in its run prompt, and reviews from the files.

study.json "materials": "text" makes the study a text-only pass, a quick check of the copy:
panellists read each page's page-text.txt and nothing else. The instructions and run prompts say
that they cannot see the design and must not comment on it, the factors that need the design
(visual and mobile by default) are left out of every template, nothing mentions the browser
whatever "browse" says, and the site copies go to <study>/sites/, outside panel/, where no
panellist can open one. Give a text pass its own study directory: its scores do not compare
with a full panel's.

Two things stop the scaffold before it writes anything, with or without --force:
  - a persona that is still a roster skeleton (roster.py grid): its name is "TODO" or empty
  - a copy of the study brief under panel/, or in a concept folder that is about to be copied
    there: a file named study-brief.md, or any file whose content is that of
    <study>/study-brief.md (assets/study-brief.md, which holds the team's hypotheses). Panellists
    read panel/, so the brief stays beside study.json

Every persona file opens with the synthetic panel notice (panel_lib.NOTICE) under its title.

--force resets every run: it rewrites the persona files and prompts, replaces runs.json along
with anything recorded in it since (agent ids, launcher state, usage), and drops the launcher's
modification record and followups.json, the record of follow-up questions whose answers were in
the persona files it has just rewritten. It deletes no harness session. The sessions the replaced
runs and jobs started, and that were not purged, are carried over to logs/earlier-sessions.json
(format in panel_lib.py), and "launch.py <study-dir> purge-sessions" covers them as it does the
sessions of the new runs.

--force is refused while a launcher has the study, or while a run, job or follow-up question of
it still has a process at work: it would replace runs.json and the persona files under them.
Stop them first, with "launch.py <study-dir> stop". It holds the launcher's lock while it
works, so no launcher starts in the middle of it.

Usage: init_study.py <study-dir> [--force]
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import launch  # noqa: E402
import panel_lib as pl  # noqa: E402
import runners  # noqa: E402

# Calibrated against haiku-4-5 (Sept 2026): with a ~200k window it ran out of context on a
# 14-concept panel (runs peaked near 150k), abbreviated late concepts, and mislabelled concepts.
IMAGES_NOTE = "Your context is limited: for each concept view only `desktop-sheet-01.png`, `mobile-first-screens.png` and at most two more sheets, rely on `page-text.txt` for the rest, and never open raw/ files."
DEFAULT_MODEL_NOTES = {
    "haiku": [
        IMAGES_NOTE,  # left out of a text-only study, which has no images
        "Refer to each concept only by the label in its folder name, exactly as written, and check the label before writing each section.",
        "For the final score summary, re-read your own persona file to collect your scores.",
    ],
}

DEFAULT_IGNORE = [".git", "*.bak", ".DS_Store", "node_modules"]

# The run prompt's line about the browser: for a run that may use it, and for one that cannot
# because its runner has no browser. A study with "browse": false has neither.
BROWSER_LINE = ("- If you use agent-browser, your run id is `{run_id}`. Use it as the session name, and save "
                "screenshots to `{panel_dir}/scratch/{run_id}/`.\n")
NO_BROWSER_NOTE = ("The agent-browser CLI is not available in your environment. Do not try to open a browser: "
                   "review from the files in the materials folders only.")

# What differs with study.json "materials", line by line. The blocks that only one kind of study
# has are assets: panel-instructions-images.md (full) and panel-instructions-text.md (text).
FIRST_LOOK = {  # step 1 of "How to review" in the instructions
    "full": "1. **First look.** Look at the home page's `desktop-sheet-01.png` and `mobile-first-screens.png` "
            "(mobile first if your persona lives on their phone). Before reading further, note your 5-second "
            "impression: what is this, who is it for, what does it do for me?",
    "text": "1. **First read.** Read the top of the home page's `page-text.txt`, down to the main headline and the "
            "few lines under it, and stop there. Before reading further, note your 5-second impression: what is "
            "this, who is it for, what does it do for me?",
}
MATERIALS_LINE = {  # the run prompt's line about what to look at
    "full": "- Look at the desktop sheets and mobile screens; open raw/ single screens only to zoom in, to save "
            "context.\n",
    "text": "- You are reading the words only: each page's `page-text.txt` is all you have of it. You cannot see "
            "the design, so do not comment on layout, visuals or how it would look on a phone.\n",
}
IDEAL_VERSION = {  # under "If I could design it" in the final sections
    "full": "Five to ten bullets: the ideal version for someone like me, borrowing the best bits of any concept "
            "(name them).",
    "text": "Five to ten bullets: what the ideal version would say to someone like me, and in what order, "
            "borrowing the best bits of any concept (name them).",
}
BROKEN = {  # what a panellist reports as broken, in the researcher notes
    "full": "anything in the materials that looked broken, such as clipped text, overlaps or empty panels",
    "text": "anything in the page text that looked broken, such as a sentence cut off or a section that is "
            "plainly missing",
}


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
    """The section a panellist writes for each concept. Every field opens with its label from
    pl.FIELD_LABELS, the words extract_answers.py knows it by, so the two cannot drift."""
    def field(key, rest, close=":"):
        return f"**{pl.FIELD_LABELS[key]}{close}** {rest}"

    t = ["### Concept <label>"]
    if multi_page:
        t.append(field("pages", "..."))
    t += [
        field("take", "...", " (in my words):"),
        field("real_life", "keep reading / skim then leave / close the tab, and why."),
        field("worked", "..."),
        field("put_off", "...", ", annoyed or put me off:"),
        field("questions", "..."),
        field("explain", "in two sentences, what this product does and who it's for, as I'd tell a colleague."),
    ]
    if cfg["find_the_answer"]:
        t.append(field("answers", f"{pl.ANSWERS_HINT}, say Found (and where: page and section), Partly or Not found.",
                       "?"))
        t += [f"- {q}" for q in cfg["find_the_answer"]]
    t += [
        field("keep", '"..." (the strongest line, quoted exactly)'),
        field("cut", '"..." (quoted exactly)'),
        field("not_believed", '"..." (quoted exactly, or "none")'),
        field("forward", "yes/no, to whom, and the one-line message I'd send with it.", "?"),
        field("quote", '"..."', ", one line):"),
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
        IDEAL_VERSION[cfg["materials"]],
        "",
        "## Out of character: researcher notes",
        "A few honest notes stepping outside the persona: what this person would likely do that an AI simulation might miss, anything you could not properly assess, and " + BROKEN[cfg["materials"]] + ".",
    ]
    return "\n".join(t)


def persona_doc(p, key, order):
    rows = [
        f"# {p['id']} - {p['name']}, {p['role']}",
        "",
        pl.NOTICE,
        "",
        "| | |",
        "|---|---|",
        f"| Persona id | {p['id']} |",
        f"| Role | {p['role']} |",
        f"| Personality type | {p['personality']} |",
        f"| Model | `{key}` |",
        f"| Review order | {', '.join(order)} |",
        "",
        "## Persona",
        f"You are **{p['name']}**.",
    ]
    rows += [f"- {b}" for b in p.get("bio", [])]
    rows += ["", "## Feedback", ""]
    return "\n".join(rows)


def skeletons(cfg):
    """The ids of the personas that are still roster skeletons: no name, or roster.py's placeholder."""
    return [p["id"] for p in cfg["personas"] if str(p.get("name") or "").strip() in ("", pl.SKELETON_NAME)]


def brief_copy(sd, folders):
    """The first file under any of the folders that is a copy of the study brief, by name or by
    content (pl.study_brief_copy), else None."""
    return pl.study_brief_copy(sd, (f for folder in folders if folder.is_dir()
                                    for f in sorted(folder.rglob("*")) if f.is_file()))


def keep_sessions(sd):
    """Carry the harness sessions of the runs and jobs in runs.json, which is about to be
    replaced, over to the earlier-sessions record (panel_lib.py), so purge-sessions can still
    delete them. Returns how many sessions the record then holds."""
    held = pl.read_earlier_sessions(sd)
    known = {(s["runner"], s["session"]) for s in held}
    try:
        replaced = pl.held_sessions(sd, pl.read_runs(sd), time.time())
    except ValueError:
        print("Note: the runs.json being replaced is not valid JSON, so any harness sessions its runs started "
              "are on no record.")
        return len(held)
    new = [s for s in replaced if (s["runner"], s["session"]) not in known]
    if new:
        pl.write_earlier_sessions(sd, [*held, *new])
    return len(held) + len(new)


def take_study(sd):
    """Before --force replaces a scaffold: refuse while a launcher has the study, or while any
    process of its runs is alive (launch.at_work: one a killed launcher left under its
    watchdog), and take the launcher's lock. Returns the lock, to release once the new scaffold
    is written, or None when there is no runs.json to replace."""
    if not (sd / "runs.json").exists():
        return None

    def refuse_while_at_work():
        try:
            busy = launch.at_work(sd, pl.read_runs(sd))
        except ValueError:  # not valid JSON: it names no process to look for
            busy = []
        if busy:
            raise SystemExit(f"Processes of this study are still at work ({', '.join(busy)}), and --force would "
                             "replace runs.json and the persona files under them. Nothing was changed. Stop them "
                             f"first: launch.py {sd} stop")

    lock = launch.Lock(sd)
    if lock.holder(sd):
        lock.refuse()
    refuse_while_at_work()  # before the lock is taken, so that a refusal leaves the study as it found it
    lock.acquire("init_study --force", 0)
    try:
        refuse_while_at_work()  # and under it: nothing can have started one since
    except SystemExit:
        lock.release()
        raise
    return lock


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing persona files, site copies and runs.json. Refused while a "
                         "launcher has the study or a process of its runs is alive")
    args = ap.parse_args()
    cfg = pl.load_study(args.study_dir)
    lock = take_study(cfg["_dir"]) if args.force else None
    try:
        scaffold(cfg, args.force)
    finally:
        if lock:
            lock.release()


def scaffold(cfg, force):
    sd = cfg["_dir"]
    panel = sd / "panel"
    unwritten = skeletons(cfg)
    if unwritten:
        raise SystemExit(f'study.json: still a roster skeleton, with the name "{pl.SKELETON_NAME}" or none: '
                         f"{', '.join(unwritten)}. Write the name and bio of each (references/personas.md), or "
                         "take it out, before scaffolding.")
    text_only, sites = cfg["materials"] == "text", pl.sites_dir(cfg)
    # Concept folders are copied into panel/sites, except in a text-only study.
    copy = brief_copy(sd, [panel, *([] if text_only else [c["_path"] for c in cfg["concepts"]])])
    if copy:
        where = "inside" if panel in copy.parents else "in a concept folder that is copied into"
        raise SystemExit(f"{copy} is a copy of the study brief, {where} {panel}, where panellists read "
                         "everything. The brief holds the team's hypotheses, which they must never see. Delete "
                         f"that file: the brief stays at {sd / pl.STUDY_BRIEF}, beside study.json.")
    lmap = pl.label_map(cfg)
    labels = list(lmap)
    entries = pl.model_entries(cfg)
    # Which model entries can drive a browser. A runner that does not exist stops the scaffold here.
    can_browse = {name: runners.get(name).capabilities()["browser"] for name in {e["runner"] for e in entries} - {None}}
    browser = {e["key"]: cfg["browse"] and can_browse.get(e["runner"], True) for e in entries}

    existing = list((panel / "personas").glob("*.md"))
    if existing and not force:
        raise SystemExit(f"{len(existing)} persona files already exist. Re-run with --force to overwrite them.")
    if (sd / "runs.json").exists() and not force:
        raise SystemExit("runs.json already exists. Re-run with --force to replace it and the run state it records.")

    for c in cfg["concepts"]:
        if not (c["_path"] / "index.html").exists():
            raise SystemExit(f"Concept {c['id']}: no index.html in {c['_path']}")

    for sub in ("personas", "materials", "scratch"):
        (panel / sub).mkdir(parents=True, exist_ok=True)
    for sub in ("prompts", "analysis"):
        (sd / sub).mkdir(exist_ok=True)
    if text_only and (panel / "sites").exists():  # copies from when this was a full-materials study
        shutil.rmtree(panel / "sites")
    sites.mkdir(exist_ok=True)

    multi_page = False
    for label, c in lmap.items():
        dest = sites / f"concept-{label}"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(c["_path"], dest, ignore=shutil.ignore_patterns(*DEFAULT_IGNORE, *cfg.get("copy_ignore", [])))
        pages = sorted(p.name for p in dest.glob("*.html"))
        c["_pages"] = pages
        multi_page = multi_page or len(pages) > 1

    n = len(labels)
    values = dict(
        n=n,
        artefact_plural=cfg["artefact_plural"],
        product_phrase=cfg.get("product_phrase", f"a product called **{cfg['product']}**"),
        label_list=(", ".join(f"Concept {l}" for l in labels[:-1]) + (" and " if n > 1 else "")
                    + f"Concept {labels[-1]}"),
        text_only_bullets=(pl.ASSETS / "panel-instructions-text.md").read_text() if text_only else "",
        context_bullets="".join(f"- {b}\n" for b in cfg["context_notes"]),
        arrival=cfg.get("arrival", "a colleague, a partner or an online ad sent you there"),
        panel_dir=str(panel),
        browser_rules=(pl.render_template("panel-instructions-browser.md", panel_dir=str(panel))
                       if cfg["browse"] else ""),
        image_files="" if text_only else pl.render_template(
            "panel-instructions-images.md",
            desktop_size="x".join(str(v) for v in cfg.get("capture", {}).get("desktop", [1440, 900]))),
        first_look=FIRST_LOOK[cfg["materials"]],
        factor_table=factor_table(cfg),
        concept_template=concept_template(cfg, multi_page),
        final_template=final_template(cfg, labels),
    )
    (panel / "_panel-instructions.md").write_text(pl.render_template("panel-instructions.md", **values))

    defaults = {k: [x for x in v if not (text_only and x == IMAGES_NOTE)] for k, v in DEFAULT_MODEL_NOTES.items()}
    model_notes = {**defaults, **cfg.get("model_notes", {})}
    reps = cfg["replicates"]
    runs = []
    for p in cfg["personas"]:
        order = pl.review_order(cfg, p["id"], labels)
        p["_order"] = order
        for e, rep in ((e, rep) for e in entries for rep in range(1, reps + 1)):
            entry = pl.run_entry(sd, p, e, rep)
            pf, pp, rid = sd / entry["file"], sd / entry["prompt"], entry["run"]
            pf.write_text(persona_doc(p, e["key"], order))
            # Notes for a model key win over notes for the model it runs on.
            found = model_notes[e["key"]] if e["key"] in model_notes else model_notes.get(e["model"], [])
            if cfg["browse"] and not browser[e["key"]]:
                found = [NO_BROWSER_NOTE, *found]
            notes = "".join(f"- {x}\n" for x in found)
            line = BROWSER_LINE.format(run_id=rid, panel_dir=panel) if browser[e["key"]] else ""
            prompt = pl.render_template(
                "run-prompt.md", artefact_plural=values["artefact_plural"], panel_dir=str(panel),
                persona_file=str(pf), n=n, run_id=rid, browser_line=line,
                materials_line=MATERIALS_LINE[cfg["materials"]], model_notes=notes)
            pp.write_text(prompt)
            runs.append(entry)
    earlier = keep_sessions(sd) if (sd / "runs.json").exists() else 0
    pl.write_runs(sd, runs)
    for record in (pl.MODIFICATIONS, pl.FOLLOWUPS):  # what was recorded of the runs just replaced
        (sd / record).unlink(missing_ok=True)

    key = ["# Concept key (lead only, never give to panellists)", "",
           "| Label | Concept | Source | Pages |", "|---|---|---|---|"]
    key += [f"| {l} | {c['id']} | `{c['_path']}` | {', '.join(c['_pages'])} |" for l, c in lmap.items()]
    key += ["", "## Review orders", "", "| Persona | Order |", "|---|---|"]
    parents = pl.variants(cfg)  # a variant reviews in its parent's order
    key += [f"| {p['id']} {p['name']}" + (f" (variant of {parents[p['id']]})" if p["id"] in parents else "")
            + f" | {', '.join(p['_order'])} |" for p in cfg["personas"]]
    (sd / "key.md").write_text("\n".join(key) + "\n")

    print(f"Study {sd.name}: {n} concepts ({', '.join(labels)}), {len(cfg['personas'])} personas x "
          f"{len(entries)} models{f' x {reps} replicates' if reps > 1 else ''} = {len(runs)} runs")
    if text_only:
        dropped = cfg["_text_only"]["dropped_factors"]
        print("Text-only study: panellists read page-text.txt only, with no images and no browser"
              + (f", and do not score {', '.join(dropped[:-1])}{' or ' if dropped[:-1] else ''}{dropped[-1]}."
                 if dropped else "."))
    if earlier:
        print(f"Harness sessions of the earlier scaffold still held by their harnesses: {earlier}, on record in "
              f"{pl.EARLIER_SESSIONS}. launch.py {sd} purge-sessions lists what is on that record and, with --yes, "
              "deletes it.")
    print(f"Next: capture.py {sd}")


if __name__ == "__main__":
    main()
