#!/usr/bin/env python3
"""Scaffold a persona-panel study from <study>/study.json.

Creates the neutral panel folder (site copies, instructions, persona files), the lead-only
key, one run prompt per persona x model entry x replicate, and runs.json (schema in
panel_lib.py). Deterministic for a given seed. Each persona reviews in an order of its own, the
same on every model and replicate, and a variant ("variant_of") reviews in its parent's order.
The shuffle can give every persona the same order, most often with two or three concepts and
personas: the summary then prints a WARNING (panel_lib.shared_order), because order is confounded
with concept, and another "seed" fixes it. Nothing is changed for it: a study already run keeps
the orders its seed gave.

A concept is of one of three kinds (panel_lib.py, "Concept kinds"). A "site" is copied under its
neutral label. A "url" and a "files" concept are not copied: capture.py takes them from the live
page and from the files. Whatever the kind, nothing under panel/ and no run prompt carries a
concept id, a source path, a file name or, unless the study browses, a URL. key.md maps them.

The site copies go to panel/sites/ only in a study whose panellists browse, because a copy is the
page source under its own file names and a run may read anything under panel/. In every other
study (a text-only one, "browse": false, a "url" concept without "browse": true) they go to
<study>/sites/, which only capture.py reads (panel_lib.sites_dir). A scaffold that finds copies
where the other setting left them removes them, so --force after changing "browse" moves them.

forms.json, beside key.md, records the form of each "files" concept (panel_lib.py, "Forms").

A study with one concept has nothing to rank or compare. Its instructions say there is one design
to review, its final sections have no ranking and no score summary, and its persona files and
key.md have no review order. It needs "artefact", the singular of "artefact_plural", when
study.json sets the plural.

study.json "browse" (default true) says whether panellists may open pages with the agent-browser
CLI. When false, the instructions and the run prompts leave the browser out. When true, a run
on a runner that cannot drive a browser is told so in its run prompt, and reviews from the files.
A run that may browse gets its screenshot folder, panel/scratch/<run id>/, here: a runner can
allow it agent-browser and no other command, so it could not make the folder itself.
With a "url" concept browsing is off unless study.json says "browse": true: the instructions then
give the address of each of its pages, and tell panellists to submit nothing. A "files" concept
has nothing to open, and the instructions say so when other concepts can be browsed.

study.json "materials": "text" makes the study a text-only pass, a quick check of the copy:
panellists read each page's page-text.txt and nothing else. The instructions and run prompts say
that they cannot see the design and must not comment on it, the factors that need the design
(visual and mobile by default) are left out of every template, and nothing mentions the browser
whatever "browse" says. Give a text pass its own study directory: its scores do not compare
with a full panel's.

These stop the scaffold before it writes anything, with or without --force:
  - a concept whose source is missing: a site without index.html, or a file that is not there
  - a name that could leave its folder: a concept id, a state name, a pinned label, a persona id
    or slug (panel_lib.py, "Names that become paths"), or a site's page file with such a name
  - a PDF among a "files" concept's files while Poppler is not installed: capture.py could not
    render it, so no run can start
  - one concept, a custom "artefact_plural" and no "artefact"
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
# The two real haiku runs of a tall image (404x3469) opened image.png, never its parts, and could not read it.
ITEM_IMAGES_NOTE = "Your context is limited: in a concept made of items, open at most four images, and rely on `page-text.txt` where an item has one. Where an item has `part-NN.png` files, open every part, in order, and do not open its `image.<type>`, which is too tall to read whole: the parts of one item count as one image."
LABEL_NOTE = "Refer to each concept only by the label in its folder name, exactly as written, and check the label before writing each section."
SUMMARY_NOTE = "For the final score summary, re-read your own persona file to collect your scores."
DEFAULT_MODEL_NOTES = {
    "haiku": [
        IMAGES_NOTE,       # left out of a study with no captured pages, and of a text-only study
        ITEM_IMAGES_NOTE,  # left out of a study with no "files" concept, and of a text-only study
        LABEL_NOTE,        # left out of a study with one concept, whose template carries the label
        SUMMARY_NOTE,      # left out of a study with one concept, which has no score summary
    ],
}

DEFAULT_IGNORE = [".git", "*.bak", ".DS_Store", "node_modules"]

# The run prompt's line about the browser: for a run that may use it, and for one that cannot
# because its runner has no browser. A study with "browse": false has neither.
BROWSER_LINE = ("- If you use agent-browser, your run id is `{run_id}`. Use it as the session name, and save "
                "screenshots to `{panel_dir}/scratch/{run_id}/`, which exists already. Run each agent-browser "
                "command on its own: a line that holds any other shell command can be refused whole.\n")
NO_BROWSER_NOTE = ("The agent-browser CLI is not available in your environment. Do not try to open a browser: "
                   "review from the files in the materials folders only.")

# What differs with study.json "materials", line by line. The blocks that only one kind of study
# has are assets: panel-instructions-images.md (full) and panel-instructions-text.md (text).
# Step 1 of "How to review" in the instructions is "{opening} {look} {impression}". "pages" is what
# a study of captured pages (site and url concepts) is told, "items" a study of "files" concepts
# alone, and "also_items" is added to "pages" when a study has both.
FIRST_LOOK = {
    "full": {"opening": "1. **First look.**",
             "pages": "Look at the home page's `desktop-sheet-01.png` and `mobile-first-screens.png` "
                      "(mobile first if your persona lives on their phone).",
             "items": "Look at the first image in `item-01`: its `part-01.png` when it has parts.",
             "also_items": "For a concept made of items, look at the first image in `item-01`: its `part-01.png` "
                           "when it has parts."},
    "text": {"opening": "1. **First read.**",
             "pages": "Read the top of the home page's `page-text.txt`, down to the main headline and the "
                      "few lines under it, and stop there.",
             "items": "Read the top of `page-text.txt` in `item-01`, down to the main headline and the few lines "
                      "under it, and stop there.",
             "also_items": "For a concept made of items, that file is in `item-01`."},
}
IMPRESSION = "Before reading further, note your 5-second impression: what is this, who is it for, what does it do for me?"
MATERIALS_LINE = {  # the run prompt's line about what to look at. "items": a full study of "files" concepts alone
    "full": "- Look at the desktop sheets and mobile screens; open raw/ single screens only to zoom in, to save "
            "context.\n",
    "items": "- Go through each item folder in order: look at its image (its parts, in order, when it has "
             "them) or its document pages, and read `page-text.txt` where there is one.\n",
    "text": "- You are reading the words only: each page's `page-text.txt` is all you have of it. You cannot see "
            "the design, so do not comment on layout, visuals or how it would look on a phone.\n",
}
IDEAL_VERSION = {  # under "If I could design it" in the final sections
    "full": "Five to ten bullets: the ideal version for someone like me, borrowing the best bits of any concept "
            "(name them).",
    "text": "Five to ten bullets: what the ideal version would say to someone like me, and in what order, "
            "borrowing the best bits of any concept (name them).",
}
IDEAL_VERSION_ONE = {  # the same, in a study with one concept
    "full": "Five to ten bullets: the ideal version for someone like me, and what it should keep from this one.",
    "text": "Five to ten bullets: what the ideal version would say to someone like me, and in what order, and "
            "what it should keep from this one.",
}
BROKEN = {  # what a panellist reports as broken, in the researcher notes
    "full": "anything in the materials that looked broken, such as clipped text, overlaps or empty panels",
    "text": "anything in the page text that looked broken, such as a sentence cut off or a section that is "
            "plainly missing",
}

# Where a page can be opened in the browser, in the instructions of a study that browses. A study
# of sites alone has SITE_PAGES and nothing else. Each "url" concept gets a URL_PAGES line with
# its addresses, the rules for a live page follow once, and each "files" concept is ruled out.
SITE_PAGES = "     - Pages are at `file://{panel_dir}/sites/concept-<label>/<page>.html`.\n"
SITE_PAGES_OF = "     - {concepts}: pages are at `file://{panel_dir}/sites/concept-<label>/<page>.html`.\n"
URL_PAGES = "     - Concept {label}: {addresses}.\n"
LIVE_RULES = ("     - Open only the addresses given here and the pages they link to on the same site. A page at such "
              "an address may be live: never submit a form, sign up, log in, buy, download or send anything.\n"
              "     - The materials were captured earlier, and a live page can change. Score from the materials. "
              "If the browser shows something different, say what in your researcher notes.\n")
NOT_BROWSABLE = ("     - {concepts} cannot be opened in a browser: review {them} from the files in {their} "
                 "materials folder alone.\n")

# How the instructions introduce the folders of "files" concepts: a study of nothing else, and a
# study that also has captured pages. {made_of} is "images and documents", or "documents" in a
# text-only study.
ITEMS_INTRO = {
    "only": "The materials in `{panel_dir}/materials/concept-<label>/`. A concept is a set of {made_of}, one in "
            "each folder: `item-01`, `item-02` and so on. Go through them in that order, and treat `item-01` as "
            "the home page.",
    "mixed": "A concept can be a set of {made_of} instead of web pages. Its folders in "
             "`{panel_dir}/materials/concept-<label>/` are then `item-01`, `item-02` and so on, with no `index`. "
             "Go through them in that order, and treat `item-01` as its home page.",
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


def concept_template(cfg, multi_page, label="<label>"):
    """The section a panellist writes for each concept. Every field opens with its label from
    pl.FIELD_LABELS, the words extract_answers.py knows it by, so the two cannot drift. A study
    with one concept gives its label, so there is nothing to fill in wrongly."""
    def field(key, rest, close=":"):
        return f"**{pl.FIELD_LABELS[key]}{close}** {rest}"

    t = [f"### Concept {label}"]
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
    """The sections a panellist writes after the last concept. A study with one concept has no
    comparison: no ranking and no score summary."""
    one = len(labels) == 1
    shorts = [f.get("short", f["label"]) for f in cfg["factors"]]
    t = []
    if not one:
        t += ["## Comparison", "### My ranking (best to worst)"]
        t += [f"{i + 1}. Concept <label> - one-line reason" for i in range(len(labels))]
        t += [
            "",
            "### Score summary",
            "| Concept | " + " | ".join(shorts) + " |",
            f"(one row per concept, in label order {labels[0]} to {labels[-1]})",
            "",
        ]
    t += [
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
        (IDEAL_VERSION_ONE if one else IDEAL_VERSION)[cfg["materials"]],
        "",
        "## Out of character: researcher notes",
        "A few honest notes stepping outside the persona: what this person would likely do that an AI simulation might miss, anything you could not properly assess, and " + BROKEN[cfg["materials"]] + ".",
    ]
    return "\n".join(t)


def persona_doc(p, key, order):
    """A persona file before its run. With one concept there is no order to follow, so no row."""
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
        *([f"| Review order | {', '.join(order)} |"] if len(order) > 1 else []),
        "",
        "## Persona",
        f"You are **{p['name']}**.",
    ]
    rows += [f"- {b}" for b in p.get("bio", [])]
    rows += ["", "## Feedback", ""]
    return "\n".join(rows)


def concept_list(labels):
    """Concept A, Concept B and Concept C."""
    named = [f"Concept {l}" for l in labels]
    return ", ".join(named[:-1]) + (" and " if named[:-1] else "") + named[-1]


def first_look(materials, paged, itemised):
    """Step 1 of "How to review": what to look at first, by what the study's concepts are made of."""
    words = FIRST_LOOK[materials]
    look = [words["pages"], *([words["also_items"]] if itemised else [])] if paged else [words["items"]]
    return " ".join([words["opening"], *look, IMPRESSION])


def page_addresses(panel, lmap):
    """The lines of the browser rules that say where each concept can be opened (SITE_PAGES and
    the constants after it). The one place a URL is written where a panellist can read it."""
    of = {kind: [l for l, c in lmap.items() if pl.concept_kind(c) == kind] for kind in pl.KINDS}
    if not of["url"] and not of["files"]:
        return SITE_PAGES.format(panel_dir=panel)
    out = SITE_PAGES_OF.format(concepts=concept_list(of["site"]), panel_dir=panel) if of["site"] else ""
    for label in of["url"]:
        out += URL_PAGES.format(label=label, addresses=", ".join(
            f"`{page['name']}` is at `{page['url']}`" for page in pl.url_pages(lmap[label])))
    if of["url"]:
        out += LIVE_RULES
    if of["files"]:
        n = len(of["files"])
        out += NOT_BROWSABLE.format(concepts=concept_list(of["files"]), them=pl.agree(n, "it", "them"),
                                    their=pl.agree(n, "its", "their"))
    return out


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
    # The folders of site concepts are copied into panel/sites only in a study that browses.
    copy = brief_copy(sd, [panel, *([c["_path"] for c in cfg["concepts"] if pl.concept_kind(c) == "site"]
                                    if panel in sites.parents else [])])
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
        have = len(existing)
        raise SystemExit(f"{pl.plural(have, 'persona file')} already {pl.agree(have, 'exists', 'exist')}. Re-run with "
                         f"--force to overwrite {pl.agree(have, 'it', 'them')}.")
    if (sd / "runs.json").exists() and not force:
        raise SystemExit("runs.json already exists. Re-run with --force to replace it and the run state it records.")

    n, one = len(labels), pl.single_concept(cfg)
    kinds = {label: pl.concept_kind(c) for label, c in lmap.items()}
    items = {}  # label of a "files" concept -> ([(item folder, source file)], [files left out])
    for label, c in lmap.items():
        problem = pl.source_problem(cfg, c)
        if problem:
            raise SystemExit(problem)
        if kinds[label] == "files":
            items[label] = pl.concept_items(cfg, c)
    no_poppler = pl.poppler_missing(cfg)
    if no_poppler:
        raise SystemExit(f"{no_poppler}, then scaffold again. Nothing was written: without it capture.py cannot "
                         "turn a PDF into materials, so no run could start.")
    if one and not cfg["artefact"]:
        raise SystemExit(f'study.json: a study with one concept needs "artefact", the singular of "artefact_plural" '
                         f'("{cfg["artefact_plural"]}"), because the instructions speak of one. For example '
                         '"artefact": "draft homepage design".')

    for sub in ("personas", "materials", "scratch"):
        (panel / sub).mkdir(parents=True, exist_ok=True)
    for sub in ("prompts", "analysis"):
        (sd / sub).mkdir(exist_ok=True)
    stale = pl.sites_dir(cfg, used=False)  # copies from a scaffold made when "browse" was the other way
    if panel in stale.parents:  # a run could read them, and nothing else belongs in panel/sites
        shutil.rmtree(stale, True)
    else:  # beside study.json only the copies are the scaffold's to remove
        for old in [d for d in stale.glob("concept-*") if d.is_dir()]:
            shutil.rmtree(old)
        if stale.is_dir() and not any(stale.iterdir()):
            stale.rmdir()
    sites.mkdir(exist_ok=True)
    copied = {f"concept-{label}" for label in labels if kinds[label] == "site"}
    for old in [d for d in sites.glob("concept-*") if d.name not in copied]:  # no longer a site, or a concept
        shutil.rmtree(old)
    if not copied and not any(sites.iterdir()):  # only a site is copied: a url and files are captured from their source
        sites.rmdir()

    multi_page = False
    for label, c in lmap.items():
        if kinds[label] == "site":
            dest = sites / f"concept-{label}"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(c["_path"], dest,
                            ignore=shutil.ignore_patterns(*DEFAULT_IGNORE, *cfg.get("copy_ignore", [])))
            c["_pages"] = sorted(p.name for p in dest.glob("*.html"))
            c["_source"] = f"`{c['_path']}`"
        elif kinds[label] == "url":
            c["_pages"] = [f"{page['name']}: {page['url']}" for page in pl.url_pages(c)]
            c["_source"] = "live URL"
        else:
            kept, left_out = items[label]
            c["_pages"] = [f"{name}: `{f}`" for name, f in kept]
            if left_out:
                c["_pages"].append("left out of this text-only study: " + ", ".join(f"`{f}`" for f in left_out))
            c["_source"] = f"files in `{c['_path']}`" if "_path" in c else "files"
        multi_page = multi_page or len(pl.concept_pages(cfg, c, sites / f"concept-{label}")) > 1

    paged = [label for label in labels if kinds[label] != "files"]     # captured pages: site and url
    itemised = [label for label in labels if kinds[label] == "files"]  # images and documents
    made_of = "documents" if text_only else "images and documents"
    plural, artefact = cfg["artefact_plural"], cfg["artefact"]
    drafts = "url" not in kinds.values()  # a page at a URL may be live
    if one:
        what = (f"This is one {artefact}, labelled Concept {labels[0]}." + (" It is a draft, not live." if drafts else "")
                + (" It may have more than one page; the home page is always `index`." if paged
                   else f" It is a set of {made_of}, in numbered item folders."))
    else:
        what = (f"These are {n} alternative {plural}: {concept_list(labels)}."
                + (" They are drafts, not live." if drafts else "")
                + (" A concept may have more than one page; the home page is always `index`." if paged
                   else f" Each is a set of {made_of}, in numbered item folders."))
    image_files = "" if text_only else pl.render_template(
        "panel-instructions-images.md",
        desktop_size="x".join(str(v) for v in cfg.get("capture", {}).get("desktop", [1440, 900])))
    values = dict(
        subject=f"one {artefact}" if one else f"{n} {plural}",
        product_phrase=cfg.get("product_phrase", f"a product called **{cfg['product']}**"),
        what=what,
        text_only_bullets=(pl.ASSETS / "panel-instructions-text.md").read_text() if text_only else "",
        context_bullets="".join(f"- {b}\n" for b in cfg["context_notes"]),
        them="it" if one else "them",
        arrival=cfg.get("arrival", "a colleague, a partner or an online ad sent you there"),
        panel_dir=str(panel),
        page_materials=pl.render_template("panel-instructions-pages.md", panel_dir=str(panel),
                                          image_files=image_files) if paged else "",
        item_materials=pl.render_template(
            "panel-instructions-items-text.md" if text_only else "panel-instructions-items.md",
            items_intro=ITEMS_INTRO["mixed" if paged else "only"].format(panel_dir=panel, made_of=made_of))
        if itemised else "",
        browser_rules=(pl.render_template("panel-instructions-browser.md", panel_dir=str(panel),
                                          page_addresses=page_addresses(panel, lmap))
                       if cfg["browse"] else ""),
        how_to_review=pl.render_template(
            "panel-instructions-review-one.md" if one else "panel-instructions-review.md",
            first_look=first_look(cfg["materials"], paged, itemised), label=labels[0]),
        factor_table=factor_table(cfg),
        a_concept="the concept" if one else "a concept",
        each_concept="the concept" if one else "each concept",
        concept_template=concept_template(cfg, multi_page, labels[0] if one else "<label>"),
        after_all="After the concept's section" if one else f"After all {n} concepts",
        final_template=final_template(cfg, labels),
        summary=("your Overall score and the one change that would most improve the concept" if one
                 else "your ranking and the one change that would most improve your top concept"),
    )
    (panel / "_panel-instructions.md").write_text(pl.render_template("panel-instructions.md", **values))

    left_out = {LABEL_NOTE, SUMMARY_NOTE} if one else set()  # the default notes that do not apply to this study
    left_out |= {IMAGES_NOTE} if text_only or not paged else set()
    left_out |= {ITEM_IMAGES_NOTE} if text_only or not itemised else set()
    defaults = {k: [x for x in v if x not in left_out] for k, v in DEFAULT_MODEL_NOTES.items()}
    if one:  # IMAGES_NOTE speaks of each concept, and there is one
        defaults = {k: [x.replace("for each concept view", "view") for x in v] for k, v in defaults.items()}
    model_notes = {**defaults, **cfg.get("model_notes", {})}
    review_step = ('Review the concept. Append its section to your persona file under "## Feedback" as soon as you '
                   "finish it, then write the final sections." if one else
                   f"Review all {n} concepts in the order your persona file lists. Append each concept's section to "
                   'your persona file under "## Feedback" as soon as you finish it, then write the final sections.')
    materials_line = MATERIALS_LINE["items" if not (text_only or paged) else cfg["materials"]]
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
            if line:  # a run may be allowed agent-browser and no other command, so it cannot make the folder
                (panel / "scratch" / rid).mkdir(exist_ok=True)
            prompt = pl.render_template(
                "run-prompt.md", subject=values["subject"] if one else plural, panel_dir=str(panel),
                persona_file=str(pf), review_step=review_step, run_id=rid, browser_line=line,
                materials_line=materials_line, each_section="the concept section" if one else "each concept section",
                model_notes=notes)
            pp.write_text(prompt)
            runs.append(entry)
    earlier = keep_sessions(sd) if (sd / "runs.json").exists() else 0
    pl.write_runs(sd, runs)
    pl.write_forms(sd, pl.file_forms(cfg))
    for record in (pl.MODIFICATIONS, pl.FOLLOWUPS):  # what was recorded of the runs just replaced
        (sd / record).unlink(missing_ok=True)

    key = ["# Concept key (lead only, never give to panellists)", "",
           "| Label | Concept | Source | Pages |", "|---|---|---|---|"]
    key += [f"| {l} | {c['id']} | {c['_source']} | {', '.join(c['_pages'])} |" for l, c in lmap.items()]
    if not one:  # one concept has no order to review in
        key += ["", "## Review orders", "", "| Persona | Order |", "|---|---|"]
        parents = pl.variants(cfg)  # a variant reviews in its parent's order
        key += [f"| {p['id']} {p['name']}" + (f" (variant of {parents[p['id']]})" if p["id"] in parents else "")
                + f" | {', '.join(p['_order'])} |" for p in cfg["personas"]]
    (sd / "key.md").write_text("\n".join(key) + "\n")

    print(f"Study {sd.name}: {pl.plural(n, 'concept')} ({', '.join(labels)}), "
          f"{pl.plural(len(cfg['personas']), 'persona')} x {pl.plural(len(entries), 'model')}"
          f"{f' x {reps} replicates' if reps > 1 else ''} = {pl.plural(len(runs), 'run')}")
    one_order = pl.shared_order(cfg)
    if one_order:
        print(f"WARNING: {one_order}")
    if one:
        print("One concept: nothing is ranked or compared, so the final sections ask for no ranking and no score "
              "summary, and analyze.py reports the scores without a leaderboard.")
    for label in (label for label in labels if kinds[label] == "url"):
        print(f"Concept {label} ({lmap[label]['id']}) is a live URL: capture.py takes it from the page as it is "
              "when it runs, and nothing of it is copied.")
    for label, (kept, skipped) in items.items():
        print(f"Concept {label} ({lmap[label]['id']}) is {pl.plural(len(kept), 'file')}, which "
              f"capture.py turns into {kept[0][0]}{f' to {kept[-1][0]}' if len(kept) > 1 else ''}."
              + (f" Left out, because a text-only study reads text alone: {pl.plural(len(skipped), 'image')}."
                 if skipped else ""))
    if cfg["_browse_off"] == "url":
        print('Browsing is off: a study with a live URL browses only when study.json says "browse": true, and the '
              "instructions then give panellists its address.")
    elif cfg["browse"] and "url" in kinds.values():
        print("Browsing is on: the instructions give panellists the address of each page of the live URL. "
              f"launch.py {sd} plan says what that opens.")
    if copied and not cfg["browse"]:
        print(f"The site copies are in {sites.relative_to(sd)}/, outside panel/, because panellists do not browse: no "
              "run can read a page's source.")
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
