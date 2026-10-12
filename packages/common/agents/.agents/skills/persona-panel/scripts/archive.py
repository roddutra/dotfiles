#!/usr/bin/env python3
"""Copy a finished study round into a research archive, leaving out regenerable bulk.

Kept: study.json, key.md, runs.json, prompts/, analysis/ (usage.md and runs.csv with it),
panel/_panel-instructions.md, panel/personas/ and, when the study has them, study-brief.md (what
was agreed with the user is part of the record) and followups.json (the questions behind the
"## Follow-up <n>" sections of the persona files, which check_runs.py reads). Dropped: panel/sites (the archive keeps the
concepts once, separately), panel/materials (regenerate with capture.py), panel/scratch,
logs/ (raw harness output, which contains everything a panellist read and wrote) and
.launch.lock.

Every markdown file kept gets the synthetic panel notice (panel_lib.NOTICE) when it lacks it:
under the heading the file opens with, or at the very top when it opens with anything else. A
file that has the line anywhere is left as it is, so archiving twice changes nothing. CSV, JSON
and every other kind of file are copied byte for byte, because a line added to one would break
whatever reads it, and so is everything --concepts copies. An archived round still analyses.

With --concepts, also copies each concept's source folder to <study-root>/concepts/<id>/ and
takes one full-page screenshot per page into <study-root>/screenshots/ via snapshot.py.

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
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import launch  # noqa: E402
import panel_lib as pl  # noqa: E402

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
                         f"{'its persona file' if len(out) == 1 else 'their persona files'} may hold what a "
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
    finally:  # the round is copied: what follows reads the concepts, which no launcher writes
        if lock:
            lock.release()
    if args.concepts:
        root = dest.parents[1] if dest.parent.name == "panel" else dest
        sites = []
        for c in cfg["concepts"]:
            target = root / "concepts" / c["id"]
            copy(c["_path"], target)
            sites.append(str(target))
        subprocess.run([sys.executable, str(Path(__file__).parent / "snapshot.py"), *sites,
                        "--out", str(root / "screenshots")], check=True)
    size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    print(f"Archived {sd.name} to {dest} ({size / 1e6:.1f} MB). Synthetic panel notice added to {noticed} "
          f"markdown file{'' if noticed == 1 else 's'} that lacked it.")


if __name__ == "__main__":
    main()
