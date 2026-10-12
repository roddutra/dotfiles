#!/usr/bin/env python3
"""Capture review materials for every page of every concept in a study.

What is captured depends on the concept's kind (panel_lib.py, "Concept kinds").

A "site" concept: for each <page>.html of its copy, concept-<L>/ under panel/sites/ or, in a study
that does not browse, <study>/sites/ (panel_lib.sites_dir), panel/materials/concept-<L>/<page>/:
  raw/d-NN.png            desktop screens, scrolled one viewport at a time (reveals fire)
  raw/m-N.png             first phone screens
  desktop-sheet-NN.png    2x2 contact sheets of the desktop screens
  mobile-first-screens.png
  page-text.txt           innerText after expanding <details>, aria-expanded buttons and reveals

A "url" concept: the same files for each of its pages, panel/materials/concept-<L>/<name>/, taken
from the live page at its address. The capture is the page as it was at that moment. A server
that answers with an error status is reported, and an address that cannot be opened is a failed
page (below).

A concept's "states" in study.json (e.g. a toggle switched to another audience) are captured
as extra page folders named <page>@<state>, so every reviewer sees every variant instead of
depending on whether their model thought to click it. They work on a site and on a url:
  {"id": "03-x", "path": "...", "states": [{"name": "insurance", "page": "index",
   "js": "document.querySelector('[data-industry=insurance]').click()"}]}

A "files" concept: one folder for each file, panel/materials/concept-<L>/item-NN/, numbered in the
order to go through them and never named after the file:
  image.<type>            an image, copied as it is
  part-NN.png             the same image cut into pieces from top to bottom, each overlapping the
                          next a little, when it is much taller than a screen: a very tall image is
                          shrunk by whatever reads it until its text cannot be read. Needs ImageMagick
  page-NN.png             the pages of a PDF, rendered with Poppler's pdftoppm, the long side
                          study.json capture.pdf_pixels (default 1600)
  page-text.txt           the text of a PDF, from Poppler's pdftotext -layout (set out as on the
                          page, so a table keeps its rows and columns sit side by side), with a
                          "[Page N]" line before each page
A PDF longer than capture.max_pdf_pages (default 20) is cut there, images and text alike, and
the capture says so loudly: raise the limit, or tell panellists in "context_notes". A PDF with no
text (a scan) is reported, and fails in a text-only capture. Without Poppler, ImageMagick or
agent-browser the capture names what it needs and stops before it captures anything.

A text-only study (study.json "materials": "text") gets page-text.txt alone, extracted the
same way. Every image an earlier capture left under panel/materials is removed, so a panellist
has nothing of the design to open. It takes the PDFs of a "files" concept and leaves its images
out, and it needs no ImageMagick.

A page or item is captured whole or not at all. Each is captured into a folder of its own in
<study>/.capture-<pid>-*/, outside panel/, and moved into place under panel/materials only when
it succeeded. A capture that was killed leaves that scratch folder behind, and the next one
settles it before it does anything else: the folder is named after its process, and one whose
process is gone is nobody's. A capture killed while it moved a folder into place left a record of
the move beside it (publish()), and the next capture finishes the move or puts the earlier
capture back, so the page or item is one whole capture or the other, and an earlier capture of a
live page that has since changed is not lost. Only then is the scratch folder removed. A page or
item that fails (an address that cannot be opened, a PDF or image that cannot be read, a tool
that exits with an error) is printed as FAILED and writes nothing: an earlier capture of it
stays as it was, and one never captured has no folder, so "launch.py plan" lists it as missing
and no run starts. The rest are captured, and the script then exits non-zero with every failure.

Everything written or deleted is inside panel/materials. Names that become folders are checked
when study.json is loaded (panel_lib.py, "Names that become paths"), and inside() checks every
folder to be filled and every path to be removed, on the path itself, before anything is touched.
The record of a move is checked the same way before it is followed (recorded()).
External tools are run with argument lists, never through a shell, and are handed absolute paths
or names this script chose, so none can be read as an option.

When a whole concept is captured (no --page), page folders that an earlier capture left and the
concept no longer has are removed, so a panellist never reads a page that is gone.

Then scans the text of every kind for study.json "forbidden_terms" (build notes, internal terms)
and "leak_terms", and reports any hit, because panellists read everything literally. It also
brings forms.json up to date with the files it read (panel_lib.py, "Forms").

Usage: capture.py <study-dir> [--label A] [--page index] [--jobs 3]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402


IMAGES = pl.IMAGE_TYPES
TALL = 1600  # an image is cut into parts when it is more than 1.5 times max(this, 1.25 x its width) high
OVERLAP = 60  # pixels that one part of a cut image shares with the next
STATUS_JS = "(performance.getEntriesByType('navigation')[0]||{}).responseStatus||0"


def inside(path: Path, materials: Path) -> Path:
    """path, once it is sure to be under the study's materials directory. Every folder this
    script puts in place and everything it deletes goes through here, whatever study.json and
    the folders on disk say: a name that climbs out of its folder, or a folder under
    panel/materials that is a link to somewhere else, stops the capture before it touches the
    place. panel_lib.py refuses such names when it loads study.json; this is the same promise
    kept on the paths themselves."""
    if materials.resolve() not in path.resolve().parents:
        raise SystemExit(f"Refusing to write or delete {path}: it is not inside {materials}, the only place a "
                         "capture writes to. Nothing was captured or removed. Look for a page, state or label name "
                         "that leaves its folder, or a folder under panel/materials that links elsewhere.")
    return path


def capture_page(pdir: Path, where: str, url: str, home: bool, cap: dict, state: dict | None = None,
                 text_only: bool = False, live: bool = False) -> str:
    """Capture one page, or one state of it, from url into the empty folder pdir. where names it
    in what is printed, home says it is the concept's home page, and live that it is at an
    address that may fail, so its status is checked."""
    dw, dh = cap.get("desktop", [1440, 900])
    mw, mh = cap.get("mobile", [390, 844])
    max_screens = cap.get("max_screens", 20)
    media = cap.get("media", "")
    setup_js = ";" + state["js"] + ";1" if state else ""  # the leading ";" keeps a script from reading as an option
    raw = pdir / "raw"

    b = pl.Browser(f"cap-{where}")
    try:
        try:
            b.open(url, dw, dh, media=media)
        except RuntimeError as err:
            raise SystemExit(f"{where}: could not open {url} ({err}). Check the address and that its server is "
                             "running.")
        if not text_only:
            raw.mkdir()
        status = b.eval(STATUS_JS) if live else 0
        warning = (f" WARNING: the server answered {status}, so this is a capture of its error page"
                   if isinstance(status, int) and status >= 400 else "")
        if setup_js:
            b.eval(setup_js)
            b.run("wait", "1000")
        total = b.scroll_height()
        step = dh - 60
        i = pos = 0
        while pos < total and i < max_screens:  # a text-only capture scrolls too, so the same reveals fire
            if not text_only:
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
    finally:
        b.close()
    if text_only:
        return f"{where}: height {total}px, page text only{warning}"

    n_mobile = cap.get("mobile_screens_home", 4) if home else cap.get("mobile_screens_other", 2)
    m = pl.Browser(f"cap-{where}-m")
    try:
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
    finally:
        m.close()

    # ImageMagick works in the page's folder and is given names this script chose, never a path: a
    # study directory with "%d" or a colon in its name would otherwise be read as a pattern or a format.
    montage = pl.which_montage()
    shots = sorted(f"raw/{f.name}" for f in raw.glob("d-*.png"))
    for s, k in enumerate(range(0, len(shots), 4), start=1):
        subprocess.run([*montage, *shots[k:k + 4], "-tile", "2x2", "-geometry",
                        f"{dw * 2 // 3}x{dh * 2 // 3}+6+6", "-background", "#888",
                        f"desktop-sheet-{s:02d}.png"], check=True, cwd=pdir, capture_output=True, text=True)
    mshots = sorted(f"raw/{f.name}" for f in raw.glob("m-*.png"))
    if mshots:
        subprocess.run([*montage, *mshots, "-tile", f"{len(mshots)}x1", "-geometry",
                        f"{mw}x{mh}+6+6", "-background", "#888", "mobile-first-screens.png"],
                       check=True, cwd=pdir, capture_output=True, text=True)
    return f"{where}: height {total}px, {pl.plural(len(shots), 'desktop screen')}, {len(mshots)} mobile{warning}"


def capture_image(pdir: Path, where: str, src: Path) -> str:
    """Copy one image of a "files" concept into the empty folder pdir as image.<type>, and cut it
    into part-NN.png pieces when it is much taller than a screen."""
    image = f"image{src.suffix.lower()}"
    shutil.copyfile(src, pdir / image)
    convert = pl.which_convert()
    identify = ["magick", "identify"] if convert == ["magick"] else ["identify"]
    size = subprocess.run([*identify, "-format", "%w %h\n", f"{image}[0]"], capture_output=True, text=True, cwd=pdir)
    try:
        width, height = map(int, size.stdout.split()[:2])  # the first frame, of an animated image
    except ValueError:
        raise SystemExit(f"{where}: ImageMagick cannot read the image ({size.stderr.strip() or 'no size'}). "
                         "Supply it as a PNG or a JPEG.")
    piece = max(TALL, round(width * 1.25))
    parts = 0
    if height > piece * 1.5:
        parts = -(-height // piece)
        # Equal pieces that overlap by OVERLAP pixels, so a line of text cut by one edge is whole in the next.
        subprocess.run([*convert, f"{image}[0]", "-crop", f"1x{parts}+0+{OVERLAP}@", "+repage", "-scene", "1",
                        "part-%02d.png"], check=True, cwd=pdir, capture_output=True, text=True)
    return (f"{where}: image {width}x{height}px"
            + (f", also cut into {parts} parts from top to bottom" if parts else ""))


def capture_pdf(pdir: Path, where: str, src: Path, cap: dict, text_only: bool) -> str:
    """Render one PDF of a "files" concept into the empty folder pdir: page-NN.png for each page
    (not in a text-only study) and page-text.txt. src is an absolute path, as every source file
    is once study.json is loaded, so Poppler cannot read it as an option."""
    limit, pixels = cap.get("max_pdf_pages", 20), cap.get("pdf_pixels", 1600)
    # -layout keeps a table's rows and a page's columns as they are set out. Without it both come out
    # a cell or a fragment to a line, and a reader reports broken sentences.
    read = subprocess.run(["pdftotext", "-layout", str(src), "-"], capture_output=True, text=True, errors="replace")
    if read.returncode:
        raise SystemExit(f"{where}: pdftotext could not read the PDF ({read.stderr.strip()}).")
    pages = read.stdout.split("\f")[:-1] or [read.stdout]  # pdftotext ends every page with a form feed
    kept = pages[:limit]
    if not any(page.strip() for page in kept):
        if text_only:
            raise SystemExit(f"{where}: the PDF has no text to extract (a scan?), and a text-only study "
                             "reads text alone. Supply a PDF with a text layer, or take the file out.")
    tidy = ["\n".join(line.rstrip() for line in re.sub(r"\n{3,}", "\n\n", page).strip("\n").split("\n"))
            for page in kept]
    if not text_only:
        done = subprocess.run(["pdftoppm", "-png", "-scale-to", str(pixels), "-l", str(limit), str(src),
                               str(pdir / "p")], capture_output=True, text=True)
        rendered = sorted(pdir.glob("p-*.png"), key=lambda f: pl.natural(f.name))
        if done.returncode or not rendered:
            raise SystemExit(f"{where}: pdftoppm could not render the PDF ({done.stderr.strip()}).")
        for n, f in enumerate(rendered, start=1):
            f.rename(pdir / f"page-{n:02d}.png")
    (pdir / "page-text.txt").write_text("\n".join(f"[Page {n}]\n{page}\n" for n, page in enumerate(tidy, start=1)))
    said = f"{where}: PDF, {pl.plural(len(kept), 'page')}"
    if not any(page.strip() for page in kept):
        said += ". WARNING: no text could be extracted (a scan?), so page-text.txt is empty and panellists have the images alone"
    if len(pages) > limit:
        said += (f". WARNING: CUT SHORT. The PDF has {len(pages)} pages and only the first {limit} "
                 f"{pl.agree(limit, 'was', 'were')} captured "
                 "(capture.max_pdf_pages), images and text alike. Panellists are told the materials are complete: "
                 'raise the limit, or say in "context_notes" that the document goes on')
    return said


def publish(work: Path, dest: Path, sd: Path, materials: Path):
    """Put a folder that was captured whole in its place under materials, so that a page or item
    is one whole capture or the other, the earlier or the new, whenever the capture is killed.

    A folder cannot take the place of one that holds files in a single step (a rename replaces an
    empty folder only), so for a moment nothing is at dest. What is to happen is recorded first,
    in <work>.publish beside the folder, and every step after that is one rename, done or not
    done and never half (a move would copy, across filesystems). What a kill leaves after each
    step, and what settle() makes of it:

        the record is written           dest as it was, the new capture in scratch. An earlier
                                        capture stays in place; with none, the new one moves in
        the earlier one is moved aside  nothing at dest, both in scratch. The new one moves in
        the new one is moved in         the new capture at dest. Nothing to move
        the earlier one is removed      the same, and the record goes last

    A rename that fails puts the earlier capture back and withdraws the record. If putting it
    back fails as well the record stays, and settle() tries again or says where the capture is."""
    inside(dest, materials)
    dest.parent.mkdir(parents=True, exist_ok=True)
    aside, record = work.with_name(f"{work.name}.earlier"), work.with_name(f"{work.name}.publish")
    draft = record.with_name(f"{record.name}.tmp")
    draft.write_text(json.dumps({"dest": str(dest.relative_to(sd)), "new": work.name, "earlier": aside.name}))
    os.replace(draft, record)  # the record is whole or not there
    try:
        if os.path.lexists(dest):
            os.rename(dest, aside)
        os.rename(work, dest)
    except OSError:
        if os.path.lexists(aside):
            os.rename(aside, dest)
        record.unlink()
        raise
    shutil.rmtree(aside, True)
    record.unlink()


def recorded(record: Path, sd: Path, materials: Path) -> tuple[Path, Path, Path]:
    """(the place under materials, the new capture, the earlier capture) that a publication record
    names. A record is read as anything found on disk is, whoever wrote it: the place must be
    inside the study's materials directory, as inside() asks of every other path, and the two
    captures must be folders of the scratch folder the record is in."""
    try:
        said = json.loads(record.read_text())
        dest, new, earlier = sd / said["dest"], said["new"], said["earlier"]
        if pl.name_problem(new) or pl.name_problem(earlier) or materials.resolve() not in dest.resolve().parents:
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit(f"Refusing to move a capture to where {record} says: it is not the record of a move into "
                         f"{materials}, the only place a capture writes to. Nothing was captured, moved or removed. "
                         f"{record.parent} may hold the only capture of a page or item: look in it, move out what "
                         "you want to keep, remove it, then capture again.")
    return dest, record.parent / new, record.parent / earlier


def settle(left: Path, sd: Path, materials: Path):
    """Finish every publication a scratch folder has a record of (publish() lists what a kill
    leaves), then remove the folder. A place that holds a capture is left alone. An empty one gets
    the new capture when it is still in scratch, where it is whole, and the earlier one otherwise.
    Each is one rename, and the folder goes only after all of them, so this can be killed and run
    again. A capture that cannot be moved stops the script with the folder as it is."""
    for record in sorted(left.glob("*.publish")):
        dest, new, earlier = recorded(record, sd, materials)
        if os.path.lexists(dest):
            continue
        for kept, did in ((new, "Finished publishing"), (earlier, "Put back the earlier capture of")):
            if kept.is_dir() and not kept.is_symlink():
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    os.rename(kept, dest)
                except OSError as err:
                    raise SystemExit(f"Could not move {kept} to {dest} ({err}). It is the only capture of that "
                                     f"page or item, so {left} is left as it is. Move it there yourself, or remove "
                                     f"{left}, then capture again.")
                print(f"{did} {dest.relative_to(sd)}, which a capture that was interrupted left out of place.")
                break
    shutil.rmtree(left, True)


def clear_scratch(sd: Path, materials: Path):
    """Settle and remove the scratch folders that earlier captures of this study left:
    <study>/.capture-<pid>-* whose process is gone, which is what a killed capture leaves. What
    one holds was not published, unless a record in it says a publication was under way, and
    settle() sees to that first. A folder whose process is alive is another capture at work on
    the study, and is left alone."""
    for left in sorted(sd.glob(".capture-*")):
        pid = left.name.split("-")[1]
        try:
            os.kill(int(pid), 0)  # signal 0 asks only whether the process is there
            continue
        except (ValueError, ProcessLookupError):  # no process id in the name, or no such process
            pass
        except OSError:  # there, and another user's
            continue
        if left.is_dir() and not left.is_symlink():
            settle(left, sd, materials)
        else:
            left.unlink(missing_ok=True)


def attempt(job: tuple, work: Path, sd: Path, materials: Path) -> tuple[bool, str]:
    """Run one capture job into work, an empty folder outside panel/, and publish it only when
    the job succeeded. Returns whether it did, and the line to print: what was captured, or why
    nothing was. A failure writes nothing under panel/materials, so an earlier capture of the
    same page or item is as it was, and one that never had a capture has no folder at all."""
    capture, dest, where, rest = job
    try:
        work.mkdir()
        line = capture(work, where, *rest)
        publish(work, dest, sd, materials)
    except SystemExit as err:
        return False, str(err)
    except subprocess.CalledProcessError as err:
        said = (err.stderr or "").strip() if isinstance(err.stderr, str) else ""
        return False, f"{where}: {err.cmd[0]} failed with exit code {err.returncode}" + (f" ({said})." if said else ".")
    except (subprocess.TimeoutExpired, RuntimeError, OSError) as err:
        return False, f"{where}: {err}"
    return True, line


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("--label", action="append", help="only these concept labels")
    ap.add_argument("--page", action="append", help="only these page names (without .html), or item names")
    ap.add_argument("--jobs", type=int, default=3, help="pages captured in parallel")
    args = ap.parse_args()

    cfg = pl.load_study(args.study_dir)
    sd = cfg["_dir"]
    materials = sd / "panel" / "materials"
    clear_scratch(sd, materials)
    cap = cfg.get("capture", {})
    text_only = cfg["materials"] == "text"
    lmap = pl.label_map(cfg)
    jobs = []     # (the function that captures, the folder it fills, how print names it, its other arguments)
    planned = {}  # concept folder -> the page folders it should have

    def wanted(name):
        return not (args.page and name not in args.page)

    for label in sorted(lmap):
        concept, kind = lmap[label], pl.concept_kind(lmap[label])
        if args.label and label not in args.label:
            continue
        out = materials / f"concept-{label}"
        if kind == "files":
            items = pl.concept_items(cfg, concept)[0]
            planned[out] = [name for name, _ in items]
            for name, src in items:
                if wanted(name):
                    jobs.append((capture_pdf, out / name, f"{label}/{name}", (src, cap, text_only))
                                if src.suffix.lower() in pl.DOCUMENT_TYPES else
                                (capture_image, out / name, f"{label}/{name}", (src,)))
            continue
        site = pl.sites_dir(cfg) / f"concept-{label}" if kind == "site" else None
        pages = ({p["name"]: p["url"] for p in pl.url_pages(concept)} if kind == "url" else
                 {p.stem: f"file://{p}" for p in sorted(site.glob("*.html"))})
        if not pages:  # not scaffolded
            continue
        planned[out] = pl.concept_folders(cfg, concept, site)
        for page, st in [*((page, None) for page in pages),
                         *((st.get("page", "index"), st) for st in concept.get("states", []))]:
            if page in pages and wanted(page):
                name = page + (f"@{st['name']}" if st else "")
                jobs.append((capture_page, out / name, f"{label}/{name}",
                             (pages[page], page == "index", cap, st, text_only, kind == "url")))
    if not jobs:
        raise SystemExit("Nothing to capture. Run init_study.py first.")
    # What is to be removed, worked out and checked with every folder to be filled before anything is touched.
    stale = []
    if text_only:  # nothing of the design stays under panel/materials, whichever pages this capture covers
        stale += [*materials.glob("concept-*/*/raw"), *(f for f in materials.rglob("*") if f.suffix.lower() in IMAGES)]
    gone = []
    if not args.page:  # a page folder the concept no longer has would be read as one of its pages
        gone = [d for out, names in planned.items() for d in sorted(out.glob("*"))
                if d.is_dir() and d.name not in names]
    for path in [*(job[1] for job in jobs), *stale, *gone]:
        inside(path, materials)
    captures = {job[0] for job in jobs}
    no_poppler = pl.poppler_missing(cfg) if capture_pdf in captures else None
    if no_poppler:
        raise SystemExit(f"{no_poppler}, then capture again. Nothing was captured.")
    if capture_page in captures:  # each of these exits, naming the tool, before anything is captured
        pl.Browser("cap-check")
        if not text_only:
            pl.which_montage()
    if capture_image in captures:
        pl.which_convert()

    for old in stale:
        if old.is_dir() and not old.is_symlink():
            shutil.rmtree(old)
        elif old.exists() or old.is_symlink():
            old.unlink()
    for old in gone:
        shutil.rmtree(old)
        print(f"Removed {old.relative_to(sd)}: the concept no longer has that page.")

    failed = []
    # Each job fills a numbered folder of its own beside study.json, where no panellist reads and no
    # name from study.json is part of a path, and the folder moves under panel/materials once it is whole.
    stage = Path(tempfile.mkdtemp(prefix=f".capture-{os.getpid()}-", dir=sd))
    try:
        works = [stage / f"{n:03d}" for n in range(len(jobs))]
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
            for ok, line in ex.map(lambda job, work: attempt(job, work, sd, materials), jobs, works):
                print(line if ok else f"FAILED {line}", flush=True)
                if not ok:
                    failed.append(line)
    finally:  # settled as a folder left behind is: an earlier capture that could not be put back does not go with it
        settle(stage, sd, materials)
    pl.write_forms(sd, pl.file_forms(cfg))

    terms = [t.lower() for t in cfg.get("forbidden_terms", []) + cfg["leak_terms"]]
    hits = []
    for txt in sorted(materials.glob("concept-*/*/page-text.txt")):
        body = txt.read_text().lower()
        hits += [f"{txt.relative_to(sd)}: '{t}'" for t in terms if t in body]
    if hits:
        print("\nForbidden or internal terms found in page text. Fix the concept or accept the bias:")
        print("\n".join(f"  {h}" for h in hits))
    kinds = {pl.concept_kind(c) for c in lmap.values()}
    if text_only:
        print("\nNow read one page-text.txt per concept yourself before launching runs. Repeated navigation and "
              "labels cut loose from their layout are expected, and the instructions say so. A missing section "
              "is not.")
    elif kinds != {"files"}:
        print("\nNow look at one desktop sheet and one mobile sheet per concept yourself before launching runs.")
    if "files" in kinds and not text_only:
        print(("\n" if kinds == {"files"} else "") + "For a concept made of files, look at one image and one document "
              "page yourself, and read one page-text.txt: an image has no text for the term scan to read.")
    if "url" in kinds:
        print("A live page was captured as it is now. Capture again if it changes before the runs.")
    if failed:
        n = len(failed)
        raise SystemExit(f"\n{n} of {pl.plural(len(jobs), 'page or item', 'pages and items')} could not be captured:\n"
                         + "\n".join(f"  {line}" for line in failed)
                         + f"\nNothing was written for {pl.agree(n, 'it', 'them')}: an earlier capture is as it was, "
                         f"and where there was none launch.py {sd} plan lists it as missing, and no run starts. Fix "
                         f"what is named and capture again (--label and --page capture one).")


if __name__ == "__main__":
    main()
