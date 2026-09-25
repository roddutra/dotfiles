#!/usr/bin/env python3
"""Copy a finished study round into a research archive, leaving out regenerable bulk.

Kept: study.json, key.md, runs.json, prompts/, analysis/, panel/_panel-instructions.md,
panel/personas/. Dropped: panel/sites (the archive keeps the concepts once, separately),
panel/materials (regenerate with capture.py) and panel/scratch.

With --concepts, also copies each concept's source folder to <study-root>/concepts/<id>/ and
takes one full-page screenshot per page into <study-root>/screenshots/ via snapshot.py.

Usage: archive.py <study-dir> --dest <archive>/customer-research/<date-topic>/panel/<round> [--concepts]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402

KEEP = {  # study path -> archive path
    "study.json": "study.json",
    "key.md": "key.md",
    "runs.json": "runs.json",
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--concepts", action="store_true", help="also archive concept sources and page screenshots")
    args = ap.parse_args()
    cfg = pl.load_study(args.study_dir)
    sd = cfg["_dir"]
    dest = args.dest.resolve()
    for src, dst in KEEP.items():
        copy(sd / src, dest / dst)
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
    print(f"Archived {sd.name} to {dest} ({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
