#!/usr/bin/env python3
"""Take one full-page screenshot of every HTML page in one or more site folders, and of any
page at a URL.

Used to archive a study compactly: keep the HTML plus one image per page, and regenerate
detailed materials with capture.py when needed. Scrolls the page once so scroll-reveal
content fires, expands collapsed content, then saves a downscaled JPEG.

--url <name>=<address> (repeatable) takes a page from its address: a concept of kind "url" has
no folder. A page that cannot be opened is skipped with a line saying so, and the rest are taken.
take() is the same for a caller that needs to know which pages were not taken (archive.py).

Output: <out>/<site-folder-name>--<page>.jpg, and <out>/<name>.jpg for each --url

Nothing is taken when two pages would be saved under one name (two site folders of the same
name, or a --url name that repeats one), or when a --url name is not one part of a file name or
its address is not an http://, https:// or file:// URL: one screenshot would replace another, or
land outside <out>. ImageMagick writes to a name of this script's choosing in a temporary folder,
and the image is moved to its place from there, so no page name reaches a tool.

Usage: snapshot.py [<site-dir> ...] [--url <name>=<address> ...] --out <dir> [--width 1440] [--scale 50]
                   [--quality 78] [--jobs 4]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402


def snap(name: str, url: str, out: Path, width: int, height: int, scale: int, quality: int) -> str:
    """Take one page into out/<name>.jpg. Returns the line to print: it opens with SKIPPED when
    the page could not be opened and with FAILED when no screenshot came of it."""
    target = out / f"{name}.jpg"
    b = pl.Browser(f"snap-{name}"[:60])
    try:
        b.open(url, width, height)
    except RuntimeError as err:
        b.close()
        return f"SKIPPED {target.name}: could not open {url} ({err})"
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
        subprocess.run([*pl.which_convert(), png.name, "-resize", f"{scale}%", "-strip", "-interlace", "JPEG",
                        "-quality", str(quality), "full.jpg"], check=True, cwd=tmp)
        shutil.move(Path(tmp) / "full.jpg", target)
    return f"{target.name} ({target.stat().st_size // 1024} KB)"


def take(sites: list[Path], urls: list[tuple[str, str]], out: Path, width: int = 1440, height: int = 900,
         scale: int = 50, quality: int = 78, workers: int = 4) -> list[str]:
    """Take every HTML page of the site folders and every (name, address) of urls into out,
    printing a line for each. Returns the names that were not taken: skipped or failed. Exits,
    with nothing taken, when a name or an address is not usable or two pages share a name."""
    for name, url in urls:
        if pl.name_problem(name):
            raise SystemExit(f"The screenshot name {name!r} {pl.NAME_RULE}. Nothing was taken.")
        if urlsplit(url).scheme not in ("http", "https", "file"):
            raise SystemExit(f"The address of {name}, {url!r}, must be an http://, https:// or file:// URL. "
                             "Nothing was taken.")
    jobs = [(f"{s.resolve().name}--{p.stem}", f"file://{p.resolve()}") for s in sites for p in sorted(s.glob("*.html"))]
    jobs += urls
    names = [name for name, _ in jobs]
    twice = sorted({name for name in names if names.count(name) > 1})
    if twice:
        raise SystemExit(f"Two pages would be saved as {twice[0]}.jpg, and the second would replace the first. "
                         "Nothing was taken: give them different names, or site folders of different names.")
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    missed = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for (name, _), line in zip(jobs, ex.map(lambda j: snap(j[0], j[1], out, width, height, scale, quality), jobs)):
            print(line)
            if line.startswith(("SKIPPED ", "FAILED ")):
                missed.append(name)
    return missed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sites", nargs="*", type=Path)
    ap.add_argument("--url", action="append", default=[], metavar="NAME=ADDRESS",
                    help="also take the page at this address, saved as <name>.jpg (repeatable)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--scale", type=int, default=50, help="percent downscale of the saved image")
    ap.add_argument("--quality", type=int, default=78)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    urls = []
    for given in args.url:
        name, _, url = given.partition("=")
        if not (name and url):
            ap.error(f"--url takes <name>=<address>, not {given!r}")
        urls.append((name, url))
    take(args.sites, urls, args.out, args.width, args.height, args.scale, args.quality, args.jobs)


if __name__ == "__main__":
    main()
