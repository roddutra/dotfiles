#!/usr/bin/env python3
"""Copy a finished study round into a research archive, leaving out regenerable bulk.

Kept: study.json, key.md, runs.json, prompts/, analysis/ (usage.md and runs.csv with it),
panel/_panel-instructions.md, panel/personas/ and, when the study has them, study-brief.md (what
was agreed with the user is part of the record) and followups.json (the questions behind the
"## Follow-up <n>" sections of the persona files, which check_runs.py reads). Dropped: the site
copies, in panel/sites or <study>/sites (the archive keeps the concepts once, separately),
panel/materials (regenerate with capture.py), panel/scratch, logs/ (raw harness output, which
contains everything a panellist read and wrote), .launch.lock and .capture-*, the scratch of a
capture. Only what KEEP names is copied, so nothing else beside study.json travels.

forms.json is written to the archive too: the form of each "files" concept, from its source files
while they can be read, else from the study's own record (panel_lib.py, "Forms"). An archive
made without --concepts has no source to tell a PDF from an image, and analyze.py needs to.

Every markdown file kept gets the synthetic panel notice (panel_lib.NOTICE) when it lacks it:
under the heading the file opens with, or at the very top when it opens with anything else. A
file that has the line anywhere is left as it is, so archiving twice changes nothing. CSV, JSON
and every other kind of file are copied byte for byte, because a line added to one would break
whatever reads it, and so is everything --concepts copies. An archived round still analyses.
Archiving to a place that holds an earlier archive replaces what has the same name. For a concept
file whose content differs, a line says so.

With --concepts, also copies each concept's source to <study-root>/concepts/<id>/ and takes one
full-page screenshot per page into <study-root>/screenshots/ via snapshot.py. What the source is
depends on the concept's kind (panel_lib.py, "Concept kinds"):
  site    its folder is copied, and every page of it is screenshotted
  files   its images and PDFs are copied, each as item-<NN>-<its own name>, numbered in the order
          study.json or the folder gives them (the item numbers of the materials, except in a
          text-only study, which leaves the images out): files from different folders can share
          a name, and none may replace another. They are their own record, so no screenshot is
          taken
  url     it has no source to copy. Its addresses are in key.md, and its pages are screenshotted
          from the live page as it is now, which may no longer be what the panel saw. A page that
          cannot be opened is skipped, and the line for the concept says how many of its pages
          were screenshotted and how many were not

Two refusals, each with nothing archived. A study that a launcher has (launch.py, followup.py or
init_study.py --force) is refused: archive.py takes the launcher's own lock on the study
(launch.Lock) and holds it until the round is copied, so no follow-up can be asked or settled
under the copy. A study with a follow-up question that is not settled is refused too, checked
under that lock: a follow-up attempt with no end in runs.json, or a record in followups.json
with no outcome or with a decision still to carry out. Until a launcher has settled it, the
persona file may hold what will be rejected and put back (the snapshot rule in panel_lib.py),
and an archive has no logs/ to put it back from. A study no launcher ever ran (native mode) is
locked for the copy like any other, and an archived round, which has no logs/, has nothing to
settle and is copied as it is.

Usage: archive.py <study-dir> --dest <archive>/customer-research/<date-topic>/panel/<round> [--concepts]
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import launch  # noqa: E402
import panel_lib as pl  # noqa: E402
import snapshot  # noqa: E402

KEEP = {  # study path -> archive path
    "study.json": "study.json",
    "key.md": "key.md",
    "runs.json": "runs.json",
    "study-brief.md": "study-brief.md",
    pl.FOLLOWUPS: pl.FOLLOWUPS,
    "prompts": "prompts",
    "analysis": "analysis",
    "panel/_panel-instructions.md": "panel-instructions.md",
    "panel/personas": "personas",
}


def copy(src: Path, dst: Path):
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
    elif src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def copy_items(items: list[tuple[str, Path]], target: Path) -> list[str]:
    """Copy the files of a "files" concept into its archive folder, each as <item>-<its name>: the
    item numbers differ, so no two files of one concept get one name, whatever folders they came
    from. Returns the names that replaced a file of other content, left by an earlier archive."""
    written, replaced = set(), []
    for item, f in items:
        name = f"{item}-{f.name}"
        if name.lower() in written:  # cannot be while item numbers differ: never one file over another
            raise SystemExit(f"Two files of one concept would be archived as {target / name}. Nothing more was copied.")
        written.add(name.lower())
        if (target / name).is_file() and (target / name).read_bytes() != f.read_bytes():
            replaced.append(name)
        copy(f, target / name)
    return replaced


def add_notice(dst: Path) -> int:
    """Give every markdown file at or under dst the synthetic panel notice. Returns how many lacked it."""
    added = 0
    files = sorted(dst.rglob("*.md")) if dst.is_dir() else [dst] if dst.is_file() and dst.suffix == ".md" else []
    for f in files:
        try:
            text = f.read_text()
        except UnicodeDecodeError:  # not text, whatever its name says
            continue
        if pl.NOTICE not in text:
            f.write_text(pl.with_notice(text))
            added += 1
    return added


def take_study(sd: Path):
    """Take the launcher's lock on the study, so that no launcher asks or settles a follow-up
    while the round is copied. Exits while a launcher has the study. Returns the lock, to
    release once the round is copied, or None for a study directory that cannot be written (an
    archived round kept read-only): no launcher can have that one either."""
    lock = launch.Lock(sd)
    if lock.acquire("archive", 0, must=False):
        return lock
    if lock.holder(sd) or os.access(sd, os.W_OK):
        lock.refuse()
    return None


def refuse_unsettled(sd: Path):
    """Exit when a follow-up question of the study is not settled (launch.unsettled_followups).
    The caller has the study lock, so none can be asked or settled after this has looked."""
    if not (sd / "logs").is_dir():  # an archive archived again: it has nothing to settle with
        return
    out = launch.unsettled_followups(sd, pl.read_runs(sd) if (sd / "runs.json").exists() else [])
    if out:
        raise SystemExit(f"A follow-up question to {', '.join(out)} is not settled, so "
                         f"{pl.agree(len(out), 'its persona file', 'their persona files')} may hold what a "
                         "launcher will reject and put back. Nothing was archived. Settle it with: "
                         f"followup.py {sd} list, once any process still answering has ended (launch.py {sd} "
                         "status shows them).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--concepts", action="store_true", help="also archive concept sources and page screenshots")
    args = ap.parse_args()
    cfg = pl.load_study(args.study_dir)
    sd = cfg["_dir"]
    dest = args.dest.resolve()
    noticed = 0
    lock = take_study(sd)
    try:
        refuse_unsettled(sd)
        for src, dst in KEEP.items():
            copy(sd / src, dest / dst)
            noticed += add_notice(dest / dst)
        forms = pl.file_forms(cfg)
        if forms:  # with none known, a record an earlier archive left there stays
            pl.write_forms(dest, forms)
    finally:  # the round is copied: what follows reads the concepts, which no launcher writes
        if lock:
            lock.release()
    if args.concepts:
        root = dest.parents[1] if dest.parent.name == "panel" else dest
        sites, live = [], {}  # live: the id of a url concept -> the screenshot name of each of its pages
        for c in cfg["concepts"]:
            target, kind = root / "concepts" / c["id"], pl.concept_kind(c)
            if kind == "url":
                live[c["id"]] = {f"{c['id']}--{page['name']}": page["url"] for page in pl.url_pages(c)}
            elif kind == "files":  # the images of a text-only study too
                for name in copy_items(pl.concept_items({**cfg, "materials": "full"}, c)[0], target):
                    print(f"Replaced {target / name}, which an earlier archive wrote with other content.")
            else:
                copy(c["_path"], target)
                sites.append(target)
        missed = []
        if sites or live:
            missed = snapshot.take(sites, [page for pages in live.values() for page in pages.items()],
                                   root / "screenshots")
        for cid, pages in live.items():
            skipped = [name.split("--", 1)[1] for name in pages if name in missed]
            got = len(pages) - len(skipped)
            print(f"Concept {cid} is a live URL, so there is no source to copy: its addresses are in key.md. "
                  f"Screenshots: {got} captured, {len(skipped)} skipped"
                  + (f" ({', '.join(skipped)}: the reason is on its line above)." if skipped else ".")
                  + (f" {pl.agree(got, 'It shows the page', 'They show the pages')} as "
                     f"{pl.agree(got, 'it is', 'they are')} now, which may no longer be what the panel saw." if got
                     else " The archive has nothing of how it looked."))
    size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    print(f"Archived {sd.name} to {dest} ({size / 1e6:.1f} MB). Synthetic panel notice added to "
          f"{pl.plural(noticed, 'markdown file')} that lacked it.")


if __name__ == "__main__":
    main()
