#!/usr/bin/env python3
"""Start a study's visual summary page from the report kit, and bundle it into one file.

The page lives in <study>/report/: index.html, which the lead writes, with kit.css and kit.js
beside it. The kit is in the skill's assets/report-kit/: kit.html documents every part, the
helpers and the mapping from study.json and runs.json, and example-interview.html,
example-usability.html and example-review-specimen.html are finished pages
(references/report-page.md).

  init     Makes <study>/report/, copies kit.css and kit.js there from the skill, and writes
           index.html from the skeleton for the study's "type" (review, usability or
           interview): the synthetic panel notice, the verdict strip, the meta strip, the
           contents row, and that type's usual sections as headings, each with a comment on
           what goes there. index.html is written only when there is none: init never
           overwrites the page, --force included. A kit file that differs from the skill's
           copy, because the lead restyled it, is replaced only with --force, and without it
           nothing is written.
  bundle   Writes <study>/report/standalone.html: index.html with kit.css and kit.js inlined
           and a document skeleton around it, one file to open from disk, print, attach or
           archive. The web fonts and Chart.js still load from their CDNs: without a network
           the fonts fall back and each chart shows its numbers table instead. Refused when
           index.html does not carry the synthetic panel notice word for word (whitespace
           aside), when it links a kit file that report/ does not hold, and when kit.js holds
           a closing script tag or kit.css a closing style tag, which would end the inlined
           block early. Any other relative file the page points to (an image, a stylesheet of
           its own) is named: it loads beside standalone.html in report/ and nowhere else.

Each command prints what it did and what to do next.

Usage: report_kit.py <study-dir> init [--force]
       report_kit.py <study-dir> bundle
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_lib as pl  # noqa: E402

KIT = pl.ASSETS / "report-kit"
KIT_FILES = ("kit.css", "kit.js")
REPORT = "report"
PAGE = "index.html"
STANDALONE = "standalone.html"
EXAMPLES = {"review": "example-review-specimen.html", "usability": "example-usability.html",
            "interview": "example-interview.html"}
LINK_CSS = re.compile(r"""<link\b[^>]*\bhref\s*=\s*["'](?:\./)?kit\.css["'][^>]*>""", re.I)
SCRIPT_JS = re.compile(r"""<script\b[^>]*\bsrc\s*=\s*["'](?:\./)?kit\.js["'][^>]*>\s*</script\s*>""", re.I)
REFERENCE = re.compile(r"""\b(?:src|href)\s*=\s*["']([^"']*)["']""", re.I)
ABSOLUTE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#|$)", re.I)  # http:, data:, mailto:, //host, #id
HEAD_PART = re.compile(r"\s*(?:<title\b[^>]*>.*?</title\s*>|<style\b[^>]*>.*?</style\s*>|<link\b[^>]*>"
                       r"|<meta\b[^>]*>|<!--.*?-->)", re.I | re.S)
DOCUMENT = re.compile(r"\s*(?:<!doctype\b|<html\b)", re.I)
BASE_STYLE = "body { margin: 0; } img { max-width: 100%; } [hidden] { display: none !important; }"


def page_from_skeleton(cfg: dict) -> str:
    """The starting index.html for the study's type, with the notice and the study's name filled in."""
    text = (KIT / f"skeleton-{cfg['type']}.html").read_text()
    text = text.replace("${NOTICE}", html.escape(pl.NOTICE, quote=False))
    return text.replace("${STUDY}", html.escape(str(cfg.get("study") or cfg["_dir"].name), quote=False))


def init(cfg: dict, force: bool):
    sd, report = cfg["_dir"], cfg["_dir"] / REPORT
    changed = [name for name in KIT_FILES
               if (report / name).is_file() and (report / name).read_bytes() != (KIT / name).read_bytes()]
    if changed and not force:
        names = " and ".join(changed)
        raise SystemExit(f"{names} in {report} {pl.agree(len(changed), 'differs', 'differ')} from the skill's copy, "
                         f"so nothing was written: pass --force to replace {pl.agree(len(changed), 'it', 'them')} "
                         "with the skill's copy and lose the change, or keep your change and leave init alone.")
    report.mkdir(exist_ok=True)
    said = []
    for name in KIT_FILES:
        there = (report / name).is_file()
        if there and name not in changed:
            said.append(f"{name}: already the skill's copy.")
            continue
        shutil.copyfile(KIT / name, report / name)
        said.append(f"{name}: your changed copy replaced with the skill's (--force)." if there
                    else f"{name}: copied from the skill.")
    page = report / PAGE
    if page.exists():
        said.append(f"{PAGE}: kept as it is (init never overwrites the page).")
    else:
        page.write_text(page_from_skeleton(cfg))
        said.append(f"{PAGE}: written from the {cfg['type']} skeleton.")
    quotes = (f" In an interview study, build it once interview.py {sd} quotes exits 0, and quote only what that "
              "check found." if cfg["type"] == "interview" else "")
    print(*said, sep="\n")
    print(f"Next: write the page in {page} from analysis/quant.json, the synthesis, study.json and runs.json."
          f"{quotes} Every part, every helper and the PP.panel mapping are in {KIT / 'kit.html'}, and a finished "
          f"page of this type is {KIT / EXAMPLES[cfg['type']]}. Then run report_kit.py {sd} bundle, and check "
          f"{report / STANDALONE} at desktop and phone width, light and dark, and in print preview.")


def as_document(page: str) -> str:
    """The page as a whole HTML document. A page that is one already is left as it is. A fragment,
    as the kit's pages are, has what opens it (its title, styles, links, metas and comments) put in
    a head with the charset and the viewport, and the rest in the body."""
    if DOCUMENT.match(page):
        return page
    at = 0
    while (m := HEAD_PART.match(page, at)):
        at = m.end()
    head, body = page[:at].strip(), page[at:].strip()
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<style>{BASE_STYLE}</style>\n{head}\n</head>\n<body>\n{body}\n</body>\n</html>\n")


def bundle(cfg: dict):
    sd, report = cfg["_dir"], cfg["_dir"] / REPORT
    page_file = report / PAGE
    if not page_file.is_file():
        raise SystemExit(f"{page_file} is not there, so there is nothing to bundle: report_kit.py {sd} init writes a "
                         "starting page.")
    page = page_file.read_text()
    if " ".join(pl.NOTICE.split()) not in " ".join(html.unescape(page).split()):
        raise SystemExit(f"{page_file} does not carry the synthetic panel notice word for word, so no standalone page "
                         f"was written: put it under the title as a paragraph of its own, \"{pl.NOTICE}\", and "
                         "bundle again.")
    relative = sorted({ref for ref in REFERENCE.findall(LINK_CSS.sub("", SCRIPT_JS.sub("", page)))
                       if not ABSOLUTE.match(ref)})
    said, closing = [], {"kit.css": re.compile(r"</style", re.I), "kit.js": re.compile(r"</script", re.I)}
    for name, pattern, wrap in (("kit.css", LINK_CSS, "style"), ("kit.js", SCRIPT_JS, "script")):
        if not pattern.search(page):
            said.append(f"{PAGE} links no {name}, so none was inlined.")
            continue
        if not (report / name).is_file():
            raise SystemExit(f"{PAGE} links {name}, which is not in {report}, so no standalone page was written: "
                             f"report_kit.py {sd} init copies it there.")
        text = (report / name).read_text()
        if closing[name].search(text):
            raise SystemExit(f"{report / name} holds a closing {wrap} tag, which would end the inlined block early, so "
                             f"no standalone page was written: take it out (in a string, write <\\/{wrap}), and "
                             "bundle again.")
        page = pattern.sub(lambda _m, t=text, w=wrap: f"<{w}>\n{t.rstrip()}\n</{w}>", page)
    out = report / STANDALONE
    tmp = out.with_name(f".{STANDALONE}.{os.getpid()}.tmp")
    tmp.write_text(as_document(page))
    os.replace(tmp, out)
    print(*said, sep="\n", end="\n" if said else "")
    print(f"Wrote {out} ({out.stat().st_size / 1024:.0f} KB): {PAGE} with the kit inlined, one file to open from disk, "
          "print, attach or archive. The web fonts and Chart.js still load from their CDNs: without a network the "
          "fonts fall back and each chart shows its numbers table instead.")
    if relative:
        shown = ", ".join(relative[:5]) + (f" and {len(relative) - 5} more" if len(relative) > 5 else "")
        print(f"It still points to {pl.plural(len(relative), 'relative file')} ({shown}), which load only beside it in "
              f"{report}: inline {pl.agree(len(relative), 'it', 'them')} (an image as a data: URI) before the file "
              "goes anywhere else.")
    print(f"Next: open {out} and check it at desktop and phone width, light and dark, and in print preview. Then "
          f"deliver it: if your harness can publish a web page, publish {page_file} with kit.css and kit.js beside "
          "it; otherwise give the user the path of this file. Send it with the end-of-study message "
          f"({pl.SKILL_DIR / 'references/communicating.md'}).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("cmd", choices=["init", "bundle"])
    ap.add_argument("--force", action="store_true",
                    help="init: replace a kit file in report/ that differs from the skill's copy. Never index.html")
    args = ap.parse_args()
    cfg = pl.load_study(args.study_dir)
    if args.cmd == "init":
        init(cfg, args.force)
    else:
        if args.force:
            raise SystemExit("--force is for init only: bundle always writes standalone.html afresh.")
        bundle(cfg)


if __name__ == "__main__":
    main()
