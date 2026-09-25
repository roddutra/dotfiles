#!/usr/bin/env python3
"""Take one full-page screenshot of every HTML page in one or more site folders.

Used to archive a study compactly: keep the HTML plus one image per page, and regenerate
detailed materials with capture.py when needed. Scrolls the page once so scroll-reveal
content fires, expands collapsed content, then saves a downscaled JPEG.

Output: <out>/<site-folder-name>--<page>.jpg

Usage: snapshot.py <site-dir> [<site-dir> ...] --out <dir> [--width 1440] [--scale 50] [--quality 78] [--jobs 4]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402


def snap(site: Path, page: Path, out: Path, width: int, height: int, scale: int, quality: int) -> str:
    target = out / f"{site.name}--{page.stem}.jpg"
    b = pl.Browser(f"snap-{site.name}-{page.stem}"[:60])
    b.open(f"file://{page}", width, height)
    total = b.scroll_height()
    pos = 0
    while pos < total:
        b.run("scroll", "down", str(height - 100))
        b.run("wait", "350")
        pos += height - 100
    b.eval(pl.REVEAL_JS)
    b.eval("window.scrollTo(0,0);1")
    b.run("wait", "1200")
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "full.png"
        b.run("screenshot", "--full", str(png))
        b.close()
        if not png.exists():
            return f"FAILED {target.name}"
        subprocess.run([*pl.which_convert(), str(png), "-resize", f"{scale}%", "-strip", "-interlace", "JPEG",
                        "-quality", str(quality), str(target)], check=True)
    return f"{target.name} ({target.stat().st_size // 1024} KB)"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sites", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--scale", type=int, default=50, help="percent downscale of the saved image")
    ap.add_argument("--quality", type=int, default=78)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    jobs = [(s.resolve(), p.resolve()) for s in args.sites for p in sorted(s.glob("*.html"))]
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        for line in ex.map(lambda j: snap(j[0], j[1], args.out, args.width, args.height, args.scale,
                                          args.quality), jobs):
            print(line)


if __name__ == "__main__":
    main()
