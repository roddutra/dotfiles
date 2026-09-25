#!/usr/bin/env python3
"""Capture review materials for every page of every concept in a study.

For each panel/sites/concept-<L>/<page>.html writes panel/materials/concept-<L>/<page>/:
  raw/d-NN.png            desktop screens, scrolled one viewport at a time (reveals fire)
  raw/m-N.png             first phone screens
  desktop-sheet-NN.png    2x2 contact sheets of the desktop screens
  mobile-first-screens.png
  page-text.txt           innerText after expanding <details>, aria-expanded buttons and reveals

A concept's "states" in study.json (e.g. a toggle switched to another audience) are captured
as extra page folders named <page>@<state>, so every reviewer sees every variant instead of
depending on whether their model thought to click it:
  {"id": "03-x", "path": "...", "states": [{"name": "insurance", "page": "index",
   "js": "document.querySelector('[data-industry=insurance]').click()"}]}

Then scans page text for study.json "forbidden_terms" (build notes, internal terms) and
reports any hit, because panellists read everything literally.

Usage: capture.py <study-dir> [--label A] [--page index] [--jobs 3]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402


def capture_page(site: Path, page: str, out: Path, cap: dict, tag: str, state: dict | None = None) -> str:
    dw, dh = cap.get("desktop", [1440, 900])
    mw, mh = cap.get("mobile", [390, 844])
    max_screens = cap.get("max_screens", 20)
    name = page[:-5] + (f"@{state['name']}" if state else "")
    pdir = out / name
    media = cap.get("media", "")
    setup_js = state["js"] + ";1" if state else ""
    raw = pdir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for old in list(raw.glob("*.png")) + list(pdir.glob("desktop-sheet-*.png")):
        old.unlink()
    url = f"file://{site / page}"

    b = pl.Browser(f"cap-{tag}-{name}")
    b.open(url, dw, dh, media=media)
    if setup_js:
        b.eval(setup_js)
        b.run("wait", "1000")
    total = b.scroll_height()
    step = dh - 60
    i = pos = 0
    while pos < total and i < max_screens:
        b.run("screenshot", str(raw / f"d-{i:02d}.png"))
        for _ in range(3):
            b.run("scroll", "down", str(step // 3))
            b.run("wait", "300")
        b.run("wait", "1200")
        pos += step
        i += 1
    b.eval(pl.REVEAL_JS)
    b.run("wait", "800")
    text = b.eval("document.body.innerText")
    (pdir / "page-text.txt").write_text(text if isinstance(text, str) else str(text))
    b.close()

    n_mobile = cap.get("mobile_screens_home", 4) if page == "index.html" else cap.get("mobile_screens_other", 2)
    m = pl.Browser(f"cap-{tag}-{name}-m")
    m.open(url, mw, mh, media=media)
    if setup_js:
        m.eval(setup_js)
        m.run("wait", "1000")
    for j in range(n_mobile):
        m.run("screenshot", str(raw / f"m-{j}.png"))
        for _ in range(3):
            m.run("scroll", "down", str((mh - 60) // 3))
            m.run("wait", "300")
        m.run("wait", "1000")
    m.close()

    montage = pl.which_montage()
    shots = sorted(raw.glob("d-*.png"))
    for s, k in enumerate(range(0, len(shots), 4), start=1):
        subprocess.run([*montage, *map(str, shots[k:k + 4]), "-tile", "2x2", "-geometry",
                        f"{dw * 2 // 3}x{dh * 2 // 3}+6+6", "-background", "#888",
                        str(pdir / f"desktop-sheet-{s:02d}.png")], check=True)
    mshots = sorted(raw.glob("m-*.png"))
    if mshots:
        subprocess.run([*montage, *map(str, mshots), "-tile", f"{len(mshots)}x1", "-geometry",
                        f"{mw}x{mh}+6+6", "-background", "#888", str(pdir / "mobile-first-screens.png")],
                       check=True)
    return f"{tag}/{name}: height {total}px, {len(shots)} desktop screens, {len(mshots)} mobile"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("--label", action="append", help="only these concept labels")
    ap.add_argument("--page", action="append", help="only these page names (without .html)")
    ap.add_argument("--jobs", type=int, default=3, help="pages captured in parallel")
    args = ap.parse_args()

    cfg = pl.load_study(args.study_dir)
    sd = cfg["_dir"]
    cap = cfg.get("capture", {})
    jobs = []
    for site in sorted((sd / "panel" / "sites").glob("concept-*")):
        label = site.name.split("-", 1)[1]
        if args.label and label not in args.label:
            continue
        for page in sorted(p.name for p in site.glob("*.html")):
            if args.page and page[:-5] not in args.page:
                continue
            jobs.append((site, page, sd / "panel" / "materials" / site.name, label, None))
        concept = pl.label_map(cfg)[label]
        for st in concept.get("states", []):
            page = st.get("page", "index") + ".html"
            if (site / page).exists() and not (args.page and page[:-5] not in args.page):
                jobs.append((site, page, sd / "panel" / "materials" / site.name, label, st))
    if not jobs:
        raise SystemExit("Nothing to capture. Run init_study.py first.")

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        for line in ex.map(lambda j: capture_page(j[0], j[1], j[2], cap, j[3], j[4]), jobs):
            print(line)

    terms = [t.lower() for t in cfg.get("forbidden_terms", []) + cfg["leak_terms"]]
    hits = []
    for txt in sorted((sd / "panel" / "materials").glob("concept-*/*/page-text.txt")):
        body = txt.read_text().lower()
        hits += [f"{txt.relative_to(sd)}: '{t}'" for t in terms if t in body]
    if hits:
        print("\nForbidden or internal terms found in page text. Fix the concept or accept the bias:")
        print("\n".join(f"  {h}" for h in hits))
    print("\nNow look at one desktop sheet and one mobile sheet per concept yourself before launching runs.")


if __name__ == "__main__":
    main()
