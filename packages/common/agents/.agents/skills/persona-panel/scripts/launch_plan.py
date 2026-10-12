"""What launch.py says about a study without starting anything: the plan, and the usage record.

launch.py owns the commands (plan, usage); this module works out the facts and words them. It
knows no harness: everything about one comes from its runner's capabilities(), check() and
model_status().

    unfit(cfg, entry)             why a run or job cannot be started on its runner as study.json
                                  has it. The same judgement stops "plan" and "run"
    materials(cfg)                what is captured under panel/materials, per concept and in all
    no_materials(cfg, mat)        why no panellist run may start as the materials stand. The
                                  plan lists it as missing, and "run" refuses on it
    usage_of(entry)               a run's own usage: its sessions' totals, less its follow-ups
    followup_usage(entry)         what the follow-up questions put to a run used
    unallocated(entry)            what a follow-up reported in one total with a process of the
                                  run, and nothing can split
    unreported(entry)             the attempts whose spend is in no figure, because the launcher
                                  stopped the process before its harness reported any
    usage_figures(entries, states)   what the harnesses reported: per run, per model key, per
                                  role, for follow-ups and in total
    usage_markdown(figures)       analysis/usage.md
    build(cfg, runs, jobs, states, scaffolded, launcher)   the plan, as one JSON-ready object
    render(plan)                  the plan, as the lines "plan" prints

The estimate and the ceiling are different things. The estimate is what the runs still to go
are likely to use: for each model key, the mean of what its finished runs reported, times the
runs to go. A key with no finished run gets a token figure from references/method.md and no
dollar figure, because prices are harness knowledge and change. The ceiling is what the study
can cost at most: each run's budget cap once (a cap covers all of a run's attempts) plus the
synthesis pool once. It is a maximum only where a harness enforces the cap, and then only as
far as its caveats allow: what a runner says about its cap's precision ("budget_cap_note"), and
the spend of a process that was stopped before it reported any.

Follow-up questions (followup.py) are outside both. Each run asked has limits.followup for each
question, apart from its run limits, so what a follow-up used is taken out of its run's figures
and shown under a role of its own, "follow-up": a finished run measures the same for the estimate
whether or not it was asked anything afterwards.

That holds where a follow-up's spend cannot be told from the run's, too. A harness that reports
running totals for a session gives a follow-up one total for itself and for an earlier process of
the run that was stopped before reporting. That total is "unallocated": in the totals, in neither
the run's figures nor the follow-up's, and in no estimate. A finished run whose reported usage is
known to be short, because a process of it was stopped unreported or its usage is unallocated, is
left out of the mean tokens and cost of its model key, and the plan says how many were.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import panel_lib as pl
import runners

# references/method.md, "Budget": images dominate a run's context, at roughly 20k tokens per
# concept page reviewed. It was measured on captured web pages, each read as its sheets and its
# page text, and it is the size of the context a run builds up, not the tokens a harness bills
# (every turn reads the context again). The estimate multiplies it by what a run opens
# (folder_counts(), "opens"), where a page of a PDF and a supplied image each count as one such
# page: nothing has measured those, so it stands in only until a pilot has measured the real figure.
TOKENS_PER_CONCEPT_PAGE = 20_000

IMAGE_TYPES = pl.IMAGE_TYPES
TO_GO = ("pending", "running", "partial", "blocked", "failed")  # a limited run starts again only with --extend
FIGURES = ("input_tokens", "output_tokens", "cached_tokens", "cost_usd", "duration_s")
LIST_PRICE = ("Dollar figures are list-price equivalents: under a subscription login nothing is charged per "
              "token, so they say how much allowance is used, not what is paid.")
NATIVE = ("Native mode: the lead starts each run with its own subagent tool (runs.py next, mark and resume). "
          "Native mode has no limits, no usage record and no isolation beyond the instructions in the run "
          "prompt, so there is no ceiling and nothing below is enforced.")
CEILING_LABELS = {True: "guaranteed maximum", False: "estimate"}
STOPPED = ("a process the launcher stops, at its time limit or by the stop command, can end before its harness "
           "reports what it spent. That spend is counted when its session is next resumed and reports its total, "
           "so until then the attempt that resumes it can be given more of the cap than is left")


# ---------------------------------------------------------------- wording

agree, plural = pl.agree, pl.plural  # number agreement, the same in every script


def money(x) -> str:
    if x is None:
        return "not reported"
    return f"${x:,.2f}" if abs(x * 100 - round(x * 100)) < 1e-9 else f"${x:,.4f}"  # whole cents, or finer


def stop(text: str) -> str:
    """A message from a CLI or a runner as the end of a sentence, with one full stop."""
    return str(text).strip().rstrip(".") + "."


def listed(words: list[str]) -> str:
    return ", ".join(words[:-1]) + (" and " if words[:-1] else "") + words[-1]


def attempts_named(numbers: list[int]) -> str:
    return f"{agree(len(numbers), 'attempt')} {listed([str(n) for n in numbers])}"


def earlier_sessions(n: int) -> str:
    """What the plan, "status" and "purge-sessions" say of the sessions that the runs replaced by
    init_study.py --force left with their harnesses (the earlier-sessions record, panel_lib.py)."""
    return (f"{plural(n, 'harness session')} of an earlier scaffold of this study {agree(n, 'is', 'are')} "
            f"still on record in {pl.EARLIER_SESSIONS}: init_study.py --force replaced the runs that started "
            f"{agree(n, 'it', 'them')}.")


def purge_hint(sd) -> str:
    return f"launch.py {sd} purge-sessions lists what is on that record and, with --yes, deletes it."


def size(n: int) -> str:
    for unit, scale in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if n >= scale:
            return f"{n / scale:.1f} {unit}"
    return f"{n} bytes"


def span(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.1f} min" if seconds < 5400 else f"{seconds / 3600:.1f} h"


def table(rows: list[list], indent: str = "  ") -> list[str]:
    rows = [[str(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return [(indent + "  ".join(c.ljust(w) for c, w in zip(r, widths))).rstrip() for r in rows]


# ---------------------------------------------------------------- what a runner cannot do

def label(entry: dict) -> str:
    """The name of an entry's model entry: its model key for a panellist run, its role for a job
    (synthesis.analyst and synthesis.writer are one model entry each)."""
    return entry["key"] if entry["role"] == "panellist" else entry["role"]


def reads_images(caps: dict, status: dict) -> bool:
    """Whether a model entry's runs can open an image file: what its runner found out about the
    model, and the runner-wide answer where it could not tell."""
    return caps["images_by_path"] if status["images"] is None else status["images"]


def unfit(cfg: dict, entry: dict, status: dict | None = None) -> tuple[list[str], str | None]:
    """Why a run or job cannot be started on its runner as study.json has it, and a note where
    something it asks for is left out instead: (errors, note). An error refuses the launch.
    status is the runner's model_status() for the entry, asked for here when not given."""
    runner = runners.get(entry["runner"])
    caps, effort = runner.capabilities(), runners.check_effort(entry)
    status = status or runner.model_status(entry)
    errors = [effort["error"]] if effort["error"] else []
    if status["known"] is False or status["signed_in"] is False:
        errors.append(status["message"] or f'{entry["runner"]} cannot run the model "{entry["model"]}"')
    elif entry["role"] == "panellist" and cfg["materials"] == "full" and not reads_images(caps, status):
        who = entry["runner"] if status["images"] is None else f'{entry["model"]} on {entry["runner"]}'
        errors.append(f'{who} cannot open images, and this study\'s "materials" is "full", so its '
                      'runs would review designs they cannot see. A model that reads no images is for '
                      'text-only studies: set "materials": "text", or take the model entry out')
    return errors, effort["note"]


def lacks(cfg: dict, entry: dict, caps: dict, status: dict) -> list[dict]:
    """The capabilities a model entry does not have on its runner, each with what that means here."""
    panellist, out = entry["role"] == "panellist", []
    if panellist and not reads_images(caps, status):
        out.append(("images", "it cannot open an image file" + (
            ", which a text-only study does not need" if cfg["materials"] == "text" else "")))
    if not caps["budget_cap"]:
        out.append(("budget cap", "the harness enforces no spend cap, so the time limit is what bounds its runs"))
    if not caps["resume"]:
        out.append(("resume", "an interrupted run cannot be continued in its session"))
    if panellist and cfg["browse"] and not caps["browser"]:
        out.append(("browser", "the study allows browsing, but its runs review from the files alone"))
    if not caps["purge"]:
        out.append(("purge", "its sessions cannot be deleted, so purge-sessions leaves them in place"))
    figures = {"tokens": "token", "cost": "cost", "duration": "duration"}  # what the harness reports: its figure
    silent = [name for k, name in figures.items() if not caps["usage"].get(k)]
    told = [k for k in figures if caps["usage"].get(k)]
    if silent:
        out.append((f"{listed(silent)} figures",
                    f"its harness reports {listed(told)} only" if told else "its harness reports no usage at all"))
    return [{"capability": c, "means": m} for c, m in out]


# ---------------------------------------------------------------- materials

COUNTS = ("folders", "pages", "pdfs", "pdf_pages", "images", "parts", "opens", "text_files", "bytes", "text_bytes")
PDF_PAGE = re.compile(r"page-\d+\.png")
PAGE_MARK = re.compile(r"^\[Page \d+\]$", re.M)


def captured_folder(folder: Path) -> bool:
    """Whether a page or item folder holds what a run reviews it from: its page text, or the
    image itself for an item that is an image. A folder with neither is no capture, whatever
    else it holds: capture.py puts a folder in place whole, so one like that was not made by it."""
    return (folder / "page-text.txt").is_file() or any(
        f.is_file() and f.name.startswith("image.") for f in folder.iterdir())


def folder_counts(folder: Path, filed: bool) -> dict:
    """What one captured folder of a concept's materials holds, as the counts materials() adds
    up. It is one of three things. A PDF: "pdfs" 1 and "pdf_pages" its page images, or the "[Page N]"
    lines of its text in a text-only study, which has no image (filed: the folder is an item of
    a "files" concept). A supplied image: "images" 1, and "parts" the pieces a tall one was also
    cut into, which are the same image again. A captured web page or state: "pages" 1 and
    "images" every image file of it, sheets and raw screens alike.
    "opens" is what the unmeasured estimate counts: a web page, a PDF page and a supplied image
    are each one thing a run opens."""
    names = [f.name for f in folder.iterdir() if f.is_file()]
    rendered, supplied = sum(bool(PDF_PAGE.fullmatch(n)) for n in names), sum(n.startswith("image.") for n in names)
    if rendered or (filed and not supplied):
        text = folder / "page-text.txt"
        pages = rendered or (len(PAGE_MARK.findall(text.read_text(errors="replace"))) if text.is_file() else 0)
        return {"pdfs": 1, "pdf_pages": pages, "opens": max(pages, 1)}
    if supplied:
        return {"images": supplied, "parts": sum(n.startswith("part-") for n in names), "opens": 1}
    return {"pages": 1, "images": sum(f.suffix.lower() in IMAGE_TYPES for f in folder.rglob("*") if f.is_file()),
            "opens": 1}


def materials(cfg: dict) -> dict:
    """What is under panel/materials, per concept and in all, with each concept's kind:
    "folders" (one per captured page, state or item: captured_folder()), the counts of
    folder_counts() added up, text files and bytes. "captured" says whether any such folder is
    there. When none is, "pages", "pdfs", "images" and "opens" are counted from the site copies
    or the concepts' sources, "pages_from" says which, and "pdf_pages" is None: a PDF's pages are
    not known until it is captured, so it counts as one in "opens". "uncaptured" lists the
    concepts of the study with no captured folder. "incomplete" lists the others that are short
    of one, each {"concept", "lacks"}: the pages, states and items the concept has
    (panel_lib.concept_folders) with no captured folder, and any folder there that is no capture.
    "strays" lists the concept folders that belong to no concept of the study, which a
    panellist could still read. "text_only" is None for a full-materials study, else what
    "materials": "text" changed (panel_lib.apply_materials). "live" has one entry per "url"
    concept: its pages, the hosts they are on, and when it was captured (browsing())."""
    sd = cfg["_dir"]
    root = sd / "panel" / "materials"
    lmap = pl.label_map(cfg)
    kinds = {f"concept-{label}": pl.concept_kind(c) for label, c in lmap.items()}
    concepts, captured_at, ready, hollow = [], {}, {}, {}  # ready, hollow: concept folder -> folder names
    for folder in sorted(root.glob("concept-*")) if root.is_dir() else []:
        files = [f for f in folder.rglob("*") if f.is_file()]
        text = [f for f in files if f.suffix == ".txt"]
        captured_at[folder.name] = max((f.stat().st_mtime for f in files), default=None)
        held = {"concept": folder.name, "kind": kinds.get(folder.name), **dict.fromkeys(COUNTS, 0),
                "text_files": len(text), "bytes": sum(f.stat().st_size for f in files),
                "text_bytes": sum(f.stat().st_size for f in text)}
        for page in sorted(d for d in folder.iterdir() if d.is_dir()):
            if not captured_folder(page):
                hollow.setdefault(folder.name, []).append(page.name)
                continue
            held["folders"] += 1
            ready.setdefault(folder.name, []).append(page.name)
            for k, v in folder_counts(page, held["kind"] == "files").items():
                held[k] += v
        concepts.append(held)
    out = {k: sum(c[k] for c in concepts) for k in COUNTS}
    sites, incomplete = pl.sites_dir(cfg), []
    for name, c in ((f"concept-{label}", c) for label, c in lmap.items() if f"concept-{label}" in ready):
        expected = pl.concept_folders(cfg, c, sites / name if kinds[name] == "site" else None) or []
        lacks = [x for x in expected if x not in ready[name]]
        lacks += [x for x in hollow.get(name, []) if x not in lacks]
        if lacks:
            incomplete.append({"concept": name, "lacks": lacks})
    out.update(mode=cfg["materials"], captured=out["folders"] > 0, pages_from="panel/materials", concepts=concepts,
               text_only=cfg["_text_only"], uncaptured=[name for name in kinds if name not in ready],
               incomplete=incomplete,
               strays=[c["concept"] for c in concepts if c["kind"] is None],
               live=[{"concept": f"concept-{label}", "pages": pl.url_pages(c),
                      "hosts": list(dict.fromkeys(host(p["url"]) for p in pl.url_pages(c))),
                      "captured_at": captured_at.get(f"concept-{label}")}
                     for label, c in lmap.items() if pl.concept_kind(c) == "url"])
    if not out["captured"]:
        copies = list(sites.glob("concept-*/*.html"))
        pages, pdfs, images = sum(len(c.get("states", [])) for c in cfg["concepts"]), 0, 0
        for label, c in lmap.items():
            if pl.concept_kind(c) == "files":  # its items are its files
                try:
                    items = pl.concept_items(cfg, c)[0]
                except SystemExit:  # a source the capture will refuse: build() says so
                    continue
                documents = sum(f.suffix.lower() in pl.DOCUMENT_TYPES for _, f in items)
                pdfs, images = pdfs + documents, images + len(items) - documents
            else:  # a site's pages are its copy's, or its source's before it is scaffolded. A url's are in study.json
                pages += len(pl.concept_pages(cfg, c, sites / f"concept-{label}" if copies else None) or [])
        sourced = "study.json and the concepts' sources"
        if set(kinds.values()) <= {"site"}:
            sourced = str(sites.relative_to(sd)) if copies else "the concept folders"
        out.update(pages=pages, pdfs=pdfs, pdf_pages=None, images=images, opens=pages + pdfs + images,
                   pages_from=sourced)
    return out


def held(c: dict, captured: bool = True, images: bool = True) -> str:
    """What a concept's materials hold, or all of them, in words: "2 pages, 9 images", and for
    files "1 PDF of 3 pages, 2 images". A PDF's page images count as its pages and a tall
    image's parts as that image, so "images" is never a count of files. captured: these are
    materials, where a web page with no image is worth saying, not sources still to capture."""
    out = [plural(c["pages"], "page")] if c["pages"] else []
    if c["pdfs"]:
        out.append(plural(c["pdfs"], "PDF") + (f" of {plural(c['pdf_pages'], 'page')}" if c["pdf_pages"] is not None
                                               else ""))
    if images and (c["images"] or (captured and c["pages"])):
        out.append(plural(c["images"], "image") + (f" (plus {plural(c['parts'], 'part')} cut from a tall image)"
                                                   if c["parts"] else ""))
    return ", ".join(out) or plural(0, "page")


def no_materials(cfg: dict, mat: dict) -> str | None:
    """Why no panellist run may start as the materials stand, else None: nothing is captured,
    nothing for one of the study's concepts, or one of them is short of a page, state or item
    (materials(), "incomplete"), each named. The plan lists it as missing, and "run", "pilot" and
    "resume" refuse on it (launch.preflight), so what one says the other does."""
    if not mat["captured"]:
        return f"panel/materials has no captured page. Run capture.py {cfg['_dir']} before the runs."
    short = []
    if mat["uncaptured"]:
        n = len(mat["uncaptured"])
        short.append(f"nothing is captured for {listed(mat['uncaptured'])}, so a run would review "
                     f"{agree(n, 'it', 'them')} from nothing")
    short += [f"{c['concept']} has no capture of {listed(c['lacks'])}, so a run would review it with that missing"
              for c in mat["incomplete"]]
    return f"{', and '.join(short)}. Run capture.py {cfg['_dir']} before the runs." if short else None


def host(url: str) -> str:
    """The host a URL is on, with its port when it names one."""
    return urlsplit(url).netloc.rsplit("@", 1)[-1]


def on_this_machine(named: str) -> bool:
    name = named.rsplit(":", 1)[0] if not named.endswith("]") else named
    return name in ("localhost", "127.0.0.1", "[::1]") or name.endswith(".localhost")


def browsing(cfg: dict, mat: dict) -> dict | None:
    """What the plan says about the browser in a study with a "url" or "files" concept, None for
    a study of sites alone: whether panellists may browse, why not when the reason is the
    concepts' kinds, the hosts the instructions send them to, and the concepts with nothing to
    open."""
    kinds = {c["concept"]: c["kind"] for c in mat["concepts"]}
    kinds.update({f"concept-{label}": pl.concept_kind(c) for label, c in pl.label_map(cfg).items()})
    if set(kinds.values()) <= {"site", None}:
        return None
    hosts = list(dict.fromkeys(h for live in mat["live"] for h in live["hosts"]))
    return {"on": cfg["browse"], "off_because": cfg["_browse_off"],
            "sites": [name for name, kind in kinds.items() if kind == "site"],
            "hosts": hosts, "external_hosts": [h for h in hosts if not on_this_machine(h)],
            "local_hosts": [h for h in hosts if on_this_machine(h)],
            "not_browsable": [name for name, kind in kinds.items() if kind == "files"]}


def kind_notes(cfg: dict, mat: dict) -> list[str]:
    """What the lead should know about concepts that are not sites, and about anything under
    panel/ that the study as it is now would not have put there."""
    notes = []
    filed = [f"concept-{label}" for label, c in pl.label_map(cfg).items() if pl.concept_kind(c) == "files"]
    phone = [f["key"] for f in cfg["factors"] if f["key"] == "mobile"]
    if filed and phone and cfg["materials"] == "full":
        notes.append(f'the study scores "mobile", and {listed(filed)} {agree(len(filed), "is", "are")} made of '
                     "files, with no phone screens unless a file shows one. Panellists are told to score such a "
                     'factor on what they can see and to say so: read that score as a guess, or leave the factor '
                     'out with a "factors" list.')
    # Site copies where a scaffold made under the other "browse" left them. text_only_notes() says it
    # of a text-only study.
    if any(pl.sites_dir(cfg, used=False).glob("concept-*")) and not mat["text_only"]:
        again = (f"init_study.py {cfg['_dir']} --force scaffolds the study for the setting as it is now, and resets "
                 "every run.")
        notes.append(("the site copies are in sites/, outside panel/, from a scaffold made when the study did not "
                      "browse, and study.json now lets panellists browse: the instructions offer no browser, and "
                      "capture.py finds no site to capture. " if cfg["browse"] else
                      "panel/sites holds site copies from a scaffold that browsed, and this study's panellists do not "
                      "browse: a run could read a page's source there. ") + again)
    if mat["strays"]:
        n = len(mat["strays"])
        notes.append(f"panel/materials holds {listed(mat['strays'])}, which {agree(n, 'is', 'are')} no concept of this "
                     f"study, and a panellist could read {agree(n, 'it', 'them')}. Delete "
                     f"{agree(n, 'that folder', 'those folders')}.")
    return notes


def text_only_notes(cfg: dict, mat: dict) -> list[str]:
    """What the lead should know about a text-only study: what "materials": "text" overrode in
    study.json, and anything of the design still under panel/, where a run could open it."""
    changed, sd, notes = mat["text_only"], cfg["_dir"], []
    if not changed:
        return notes
    if changed["dropped_fit_factors"]:
        left = changed["fit_factors"]
        notes.append(f'"fit_factors" names {listed(changed["dropped_fit_factors"])}, which a text-only study does not '
                     "score. " + (f"Persona fit is the mean of {listed(left)}." if left else
                                  "No fit factor is left, so the persona-fit table says nothing: name factors "
                                  "that are scored."))
    if changed["browse_ignored"]:
        notes.append('study.json says "browse": true, but a text-only study never browses: its runs get no browser '
                     "access.")
    seen = ([f"{plural(mat['images'], 'image')} under panel/materials"] if mat["images"] else []) + (
        ["the site copies in panel/sites"] if (sd / "panel" / "sites").exists() else [])
    if seen:
        notes.append(f"panel/ holds {listed(seen)} from a full-materials scaffold or capture, which a text-only run "
                     f"could open. init_study.py {sd} --force moves the site copies out of panel/ and writes the "
                     f"text-only instructions, and capture.py {sd} removes the images.")
    return notes


# ---------------------------------------------------------------- usage

def followup_attempts(entry: dict) -> list[dict]:
    """The attempts that put a follow-up question to a run."""
    return [a for a in entry.get("attempts") or [] if a.get("kind") == "followup"]


def followup_usage(entry: dict) -> dict:
    """What the follow-up questions put to a run used: the sum of what each of those attempts
    reported for its own process (its "usage", in panel_lib.py)."""
    return runners.total_usage([a.get("usage") or {} for a in followup_attempts(entry)])


def unallocated(entry: dict) -> dict | None:
    """What follow-up attempts reported in one total with processes of the run itself that had
    been stopped before reporting (the attempts' "unallocated", in panel_lib.py), summed: tokens
    and cost, with "run_unreported", the figures the run itself had reported none of. None when
    the run has no such total."""
    shared = [a["unallocated"] for a in followup_attempts(entry) if a.get("unallocated")]
    if not shared:
        return None
    return {**runners.total_usage(shared), "run_unreported": sorted({f for u in shared for f in u["run_unreported"]})}


def usage_of(entry: dict) -> dict:
    """A run's own usage: what its sessions reported, less what its follow-ups used and less what
    is unallocated. A follow-up continues the run's session, so the session's total holds it, but
    it has an allowance of its own and never counts against the run's limits. A figure the run
    had reported none of before an unallocated total came is still None, not zero: so a run reads
    the same before and after a follow-up."""
    total, asked = runners.total_usage(list((entry.get("sessions") or {}).values())), followup_usage(entry)
    shared = unallocated(entry) or {"run_unreported": []}
    out = {}
    for f in total:
        apart = (asked[f] or 0) + (shared.get(f) or 0)
        out[f] = total[f] if total[f] is None or not apart else max(0, round(total[f] - apart, 9))
        if f in shared["run_unreported"] and not out[f]:
            out[f] = None
    return out


def unreported(entry: dict, followups: bool = False) -> list[int]:
    """The numbers of the attempts whose spend is in no figure: the launcher stopped the process
    before its harness reported anything, and the session has reported no total since. The
    run's own attempts, or with followups the ones that put a follow-up question."""
    return [a["n"] for a in entry.get("attempts") or []
            if a.get("usage_reported") is False and (a.get("kind") == "followup") == followups]


def summed(rows: list[dict], shared: list[dict] = ()) -> dict:
    """The figures of a group of runs. A figure is None when no run that was started reported
    it, and "unreported" counts, per figure, the started runs that did not.

    A row's "unallocated" lists the figures its run has in an unallocated total, which is in
    no row. shared are such totals to count in, for a sum that holds them. Without them
    "apart" counts, per figure, the started runs whose figure is in one, and "unallocated"
    lists the figures that any row has in one."""
    started = [r for r in rows if r["attempts"]]
    out = {"runs": len(rows), "started": len(started), "done": sum(r["state"] == "done" for r in rows),
           "attempts": sum(r["attempts"] for r in rows), "seconds": round(sum(r["seconds"] or 0 for r in rows), 3),
           "unreported": {}, "apart": {},
           "unallocated": [f for f in FIGURES if any(f in (r.get("unallocated") or []) for r in started)]}
    for f in FIGURES:
        reported = [r[f] for r in started if r[f] is not None]
        lumps = [u[f] for u in shared if u[f] is not None]
        apart = sum(r[f] is None and f in (r.get("unallocated") or []) for r in started)
        silent = sum(r[f] is None for r in started) - apart
        out[f] = sum(reported + lumps) if reported or lumps else None
        if out[f] is not None and silent:
            out["unreported"][f] = silent
        if out[f] is not None and apart and not shared:
            out["apart"][f] = apart
    return out


def usage_figures(entries: list[dict], states: dict) -> dict:
    """What the harnesses reported, as stored in runs.json: {"runs", "followups", "unallocated",
    "keys", "roles", "total"}.

    entries are runs.json entries of any role and states maps a run id to its state. "runs"
    has one row per run or job, "keys" one per model key of the panel, "roles" one per role.
    A row's "unreported_attempts" are the attempts that unreported() names: their spend is
    missing from the row's figures, which is not the same as none.
    "followups" has one row per run that was asked a follow-up question: its follow-up attempts
    and what they used, with "followups", the numbers asked. Those attempts are in no row of
    "runs" or "keys". They are the role "follow-up" in "roles", and "total" holds them: its
    "runs", "started" and "done" count runs and jobs only.
    "unallocated" has one row per run with a total that a follow-up reported for itself and for
    a process of the run together (unallocated()): tokens and cost, with "followups", the numbers
    of the follow-ups that reported one. Those figures are in no row of "runs", "followups" or
    "keys", whose rows for that run list the figures concerned under "unallocated". They are the
    role "unallocated" in "roles", and "total" holds them.
    This is the one reading of the stored usage: the usage record and the plan's estimate both
    come from it, so a session that was resumed counts once in each.
    """
    rows, asked, shared = [], [], []
    for e in entries:
        used, extra, lump = usage_of(e), followup_attempts(e), unallocated(e) or {}
        apart = [f for f in FIGURES if lump.get(f) is not None]
        attempts = len(e.get("attempts") or []) - len(extra)
        who = {"run": e["run"], "key": e.get("key"), "runner": e.get("runner"), "model": e.get("model"),
               "state": states[e["run"]]}
        rows.append({**who, "role": e["role"], "attempts": attempts,
                     "seconds": (e.get("seconds_used") or 0) if attempts else None, **{f: used[f] for f in FIGURES},
                     "unreported_attempts": unreported(e), "unallocated": apart})
        if extra:
            used = followup_usage(e)
            asked.append({**who, "role": "follow-up", "attempts": len(extra),
                          "seconds": round(sum(a["seconds"] or 0 for a in extra), 3), **{f: used[f] for f in FIGURES},
                          "unreported_attempts": unreported(e, followups=True), "unallocated": apart,
                          "followups": sorted({a["followup"] for a in extra})})
        if lump:
            shared.append({**who, "role": "unallocated", **{f: lump.get(f) for f in FIGURES},
                           "followups": sorted({a["followup"] for a in extra if a.get("unallocated")})})
    keys = list(dict.fromkeys((r["key"], r["runner"], r["model"]) for r in rows if r["role"] == "panellist"))
    own = summed(rows)
    roles = [{"role": role, **summed([r for r in rows + asked if r["role"] == role])}
             for role in dict.fromkeys(r["role"] for r in rows + asked)]
    if shared:  # no process of its own: the runs it concerns, and the figures
        lumps = summed([], shared)
        roles.append({"role": "unallocated", **lumps, "runs": len(shared), "started": len(shared)})
    return {
        "runs": rows, "followups": asked, "unallocated": shared,
        "keys": [{"key": k, "runner": runner, "model": model,
                  **summed([r for r in rows if r["role"] == "panellist" and r["key"] == k])}
                 for k, runner, model in keys],
        "roles": roles,
        "total": {**summed(rows + asked, shared), **{k: own[k] for k in ("runs", "started", "done")}}}


def usage_markdown(figures: dict) -> str:
    def cell(row, f, started):
        stopped = row.get("unreported_attempts")  # a run's row only
        if not started or (row.get("role") == "unallocated" and row[f] is None):
            return "-"
        if row[f] is None:
            if f in (row.get("unallocated") or []):
                return "unallocated"
            return "not reported" + (" (process was stopped)" if stopped else "")
        shown = f"${row[f]:.4f}" if f == "cost_usd" else f"{row[f]:,.1f} s" if f == "duration_s" else f"{row[f]:,}"
        missing, apart = (row.get(k, {}).get(f, 0) for k in ("unreported", "apart"))  # a sum's row only
        return shown + (f" ({missing} not reported)" if missing else "") + (
            f" ({apart} unallocated)" if apart else "") + (
            f" ({attempts_named(stopped)} not reported)" if stopped else "")

    def figures_of(row, started):
        return [cell(row, f, started) for f in FIGURES]

    def clock(row, started):
        return f"{row['seconds']:,.1f} s" if started and row.get("role") != "unallocated" else "-"

    heads = ["Attempts", "Time", "Tokens in", "Tokens out", "Cached", "Cost", "Harness time"]  # the last five: FIGURES

    def line(lead, row, started):
        attempts = "-" if row.get("role") == "unallocated" else str(row["attempts"])
        return "| " + " | ".join([*map(str, lead), attempts, clock(row, started), *figures_of(row, started)]) + " |"

    def block(title, lead_heads, rows):
        head = [*lead_heads, *heads]
        return ["", f"## {title}", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head), *rows]

    total = figures["total"]
    out = [
        "# Usage", "",
        "What each harness reported for the runs and jobs of this study, as stored in runs.json. launch.py "
        "rewrites this file after every process that ends, and `launch.py <study-dir> usage` rewrites it "
        "on request.", "",
        "- Tokens in counts all input, the cached part included. Tokens out includes thinking.",
        "- Time is the launcher's own clock over every attempt of a run. Harness time is what the harness "
        "reported for its processes.",
        '- "not reported" means the harness gave no such figure. "-" means nothing was started.',
        '- "not reported (process was stopped)" means the launcher stopped the process, at its time limit or '
        "by the stop command, before the harness reported anything for it. What it used is unknown, not zero, "
        "and is counted when its session is next resumed and reports its total.",
        "- A session that was resumed is counted once: a harness that reports running totals for a session "
        "has its latest total taken, not the sum of them.",
        f"- {LIST_PRICE}",
    ]
    asked = figures.get("followups") or []
    if asked:
        out.append("- A follow-up question (followup.py) has an allowance of its own, limits.followup, and is "
                   "outside the plan's ceiling. What its processes used is under the role follow-up and under "
                   "Follow-ups, and in no run's own row. Runs, there, are the runs asked.")
    shared = figures.get("unallocated") or []
    if shared:
        out.append('- "unallocated" means a follow-up\'s process reported one total for itself and for a process '
                   "of its run that had been stopped before reporting. Nothing can split it, so it is under the "
                   "role unallocated and under Unallocated, it is in the total, and it is in neither the run's "
                   "row nor the follow-up's. The plan leaves such a run out of the mean tokens and cost it "
                   "estimates from.")
    stopped = [f"{r['run']} {attempts_named(r['unreported_attempts'])}" for r in [*figures["runs"], *asked]
               if r["unreported_attempts"]]
    if stopped:
        out += ["", f"Stopped before the harness reported anything, and so missing from every figure below: "
                    f"{', '.join(stopped)}."]
    out += block("Total", ["Runs and jobs", "Done"], [line([total["runs"], total["done"]], total, total["started"])])
    out += block("By role", ["Role", "Runs", "Done"],
                 [line([r["role"], r["runs"], "-" if r["role"] in ("follow-up", "unallocated") else r["done"]], r,
                       r["started"]) for r in figures["roles"]])
    out += block("By model key", ["Key", "Runner", "Model", "Runs", "Done"],
                 [line([k["key"], k["runner"] or "-", k["model"] or "default", k["runs"], k["done"]], k, k["started"])
                  for k in figures["keys"]])
    out += block("By run", ["Run", "Role", "Key", "State"],
                 [line([r["run"], r["role"], r["key"] or "-", r["state"]], r, r["attempts"]) for r in figures["runs"]])
    if asked:
        out += block("Follow-ups", ["Run", "Key", "Asked"],
                     [line([r["run"], r["key"] or "-", ", ".join(map(str, r["followups"]))], r, r["attempts"])
                      for r in asked])
    if shared:
        out += block("Unallocated", ["Run", "Key", "Reported by follow-up"],
                     [line([r["run"], r["key"] or "-", ", ".join(map(str, r["followups"]))], r, True)
                      for r in shared])
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- the plan

def estimate(rows: list[dict], pages: int, text_only: bool) -> dict:
    """What the runs still to go are likely to use, per model entry and in all. rows are
    usage_figures() rows with "entry" added, the name of each run's model entry, and pages is
    what a run opens (materials(), "opens"), for a model entry with no finished run to measure."""
    entries = []
    for name, role in dict.fromkeys((r["entry"], r["role"]) for r in rows):
        own = [r for r in rows if (r["entry"], r["role"]) == (name, role)]
        done = [r for r in own if r["state"] == "done" and r["attempts"]]
        to_go = sum(r["state"] in TO_GO for r in own)
        # A run whose reported usage is known to be short measures nothing for tokens and cost: a
        # process of it was stopped before reporting, or what it used came in one total with a
        # follow-up. The second is the first after a follow-up, so the mean does not move with one.
        short = {"unallocated": [r for r in done if r.get("unallocated")],
                 "unreported": [r for r in done if r["unreported_attempts"] and not r.get("unallocated")]}
        whole = [r for r in done if not r.get("unallocated") and not r["unreported_attempts"]]
        tokens = [r["input_tokens"] + (r["output_tokens"] or 0) for r in whole if r["input_tokens"] is not None]
        costs = [r["cost_usd"] for r in whole if r["cost_usd"] is not None]
        per = {"tokens": None, "cost_usd": None, "seconds": None}
        if done:
            basis = "measured" if tokens else "duration"
            per.update(tokens=round(sum(tokens) / len(tokens)) if tokens else None,
                       cost_usd=sum(costs) / len(costs) if costs else None,
                       seconds=sum(r["seconds"] or 0 for r in done) / len(done))
        elif role == "panellist" and not text_only:
            basis, per["tokens"] = "method", TOKENS_PER_CONCEPT_PAGE * pages
        else:
            basis = "none"  # the method has no figure for a text-only run or for a synthesis job
        entries.append({
            "entry": name, "role": role, "runner": own[0]["runner"], "runs": len(own),
            "done": sum(r["state"] == "done" for r in own), "to_go": to_go, "basis": basis,
            "measured_runs": len(done), "per_run": per, "reports_cost": own[0].get("reports_cost", True),
            # finished runs left out of the mean tokens and cost, by why: they still count for the time
            "left_out": {why: len(rows) for why, rows in short.items()},
            "tokens": per["tokens"] * to_go if per["tokens"] is not None else None,
            "cost_usd": per["cost_usd"] * to_go if per["cost_usd"] is not None else None,
            "seconds": per["seconds"] * to_go if per["seconds"] is not None else None,
            "cost": "measured" if per["cost_usd"] is not None else "not reported" if done
                    else "a pilot will provide one" if role == "panellist" else "a first job will provide one"})
    going = [e for e in entries if e["to_go"]]

    def total(field):
        known = [e[field] for e in going if e[field] is not None]
        return sum(known) if known else None

    return {"entries": entries, "tokens": total("tokens"), "cost_usd": total("cost_usd"), "seconds": total("seconds"),
            "no_tokens_for": [e["entry"] for e in going if e["tokens"] is None],
            "no_cost_for": [e["entry"] for e in going if e["cost_usd"] is None],
            "tokens_per_concept_page": TOKENS_PER_CONCEPT_PAGE, "pages": pages}


def ceiling(runs: list[dict], jobs: list[dict], pool: dict) -> dict:
    """The sum of the enforced budget caps plus the synthesis budget. runs and jobs are the
    plan's rows. Each run's cap counts once and the pool counts once."""
    capped = [r for r in runs if r["budget_enforced"]]
    uncapped, loose = ([r for r in rows if not r["budget_enforced"]] for rows in (runs, jobs))
    extended = [r for r in runs + jobs if r["extended"]]
    enforced = [r for r in runs + jobs if r["budget_enforced"]]
    caveats = [f"on {runner}, {note}" for runner, note in dict.fromkeys(
        (r["runner"], r["budget_cap_note"]) for r in enforced) if note]
    if enforced:
        silent = [f"{r['run']} {attempts_named(r['unreported_attempts'])}" for r in enforced
                  if r["unreported_attempts"]]
        caveats.append(STOPPED + (f". Not reported so far: {', '.join(silent)}" if silent else ""))
    runs_usd = round(sum(r["limits"]["budget_usd"] for r in capped), 6)
    more = sum(r["limits"]["budget_usd"] * r["extended"] for r in extended if r["budget_enforced"])
    return {
        "usd": round(runs_usd + pool["budget_usd"], 6), "guaranteed": not (uncapped or loose),
        "label": CEILING_LABELS[not (uncapped or loose)],
        "caveats": caveats,  # how the capped part of the figure can still be passed
        "capped_runs": len(capped), "capped_runs_usd": runs_usd,
        "synthesis_usd": pool["budget_usd"],
        "uncapped": [r["run"] for r in uncapped],  # runs: no cap, and so no part of the figure
        "uncapped_minutes": round(sum(r["limits"]["minutes"] for r in uncapped), 3),
        "uncapped_jobs": [r["run"] for r in loose],  # jobs: their share of the pool is counted, not enforced
        "uncapped_job_minutes": round(sum(r["limits"]["minutes"] for r in loose), 3),
        "holds": not extended, "extended": [r["run"] for r in extended],
        "with_extensions_usd": round(runs_usd + pool["budget_usd"] + more, 6)}


def build(cfg: dict, runs: list[dict], jobs: list[dict], states: dict, scaffolded: bool, launcher: dict | None) -> dict:
    """The plan as one JSON-ready object. Starts no run and writes nothing to the study: the
    only processes are each runner's check() and model_status(), which make no model call. Either
    may let a harness refresh its own login.

    runs are the panellist entries (runs.json's, or the ones study.json plans when scaffolded
    is false), jobs the analyst and writer entries study.json plans with anything a launcher
    recorded about them, and states maps each run and job id to its state.
    """
    sd, native = cfg["_dir"], all(e["runner"] is None for e in runs)
    mat = materials(cfg)
    planned = [] if native else [j for j in jobs if j["runner"]]
    pool, missing, notes, problems = pl.synthesis_pool(cfg), [], [], []

    if not scaffolded:
        missing.append(f"runs.json: run init_study.py {sd} first. The runs below are the ones it will create.")
    else:
        expected, found = {e["run"] for e in pl.planned_runs(cfg)}, {e["run"] for e in runs}
        if expected != found:
            notes.append("study.json no longer plans the runs that runs.json holds (they differ in "
                         + ", ".join(sorted(expected ^ found)[:6]) + (", ..." if len(expected ^ found) > 6 else "")
                         + f"). This plan follows runs.json. init_study.py {sd} --force scaffolds the study again, "
                         "and resets every run.")
    gone = [e["prompt"] for e in runs if not (sd / e["prompt"]).is_file()]
    if scaffolded and gone:
        missing.append(f"{plural(len(gone), 'run prompt')} ({', '.join(gone[:3])}{', ...' if len(gone) > 3 else ''})")
    uncaptured = no_materials(cfg, mat)
    if uncaptured:
        missing.append(f"the materials: {uncaptured}" + (
            "" if mat["captured"] else f" The estimate counts the pages in {mat['pages_from']}."))
    # A source the scaffold or the capture will refuse: a site not copied yet, files not captured yet.
    short = {*mat["uncaptured"], *(c["concept"] for c in mat["incomplete"])}
    for name, c in ((f"concept-{label}", c) for label, c in pl.label_map(cfg).items()):
        needed = not scaffolded if pl.concept_kind(c) == "site" else name in short
        problem = pl.source_problem(cfg, c) if needed else None
        if problem:
            missing.append(f"{stop(problem)} init_study.py and capture.py stop on it, so no run can start.")
    no_poppler = pl.poppler_missing(cfg)
    if no_poppler and short:
        missing.append(f"{no_poppler}. capture.py cannot turn a PDF into materials without it.")
    notes += text_only_notes(cfg, mat) + kind_notes(cfg, mat)
    one_order = pl.shared_order(cfg)
    if one_order:
        notes.append(one_order)
    earlier = len(pl.read_earlier_sessions(sd))
    if earlier:
        notes.append(f"{earlier_sessions(earlier)} {purge_hint(sd)}")

    # One row per model entry: a model key of the panel, synthesis.analyst or synthesis.writer.
    groups = {}
    for e in runs + planned:
        groups.setdefault((e["role"], label(e)), []).append(e)
    models, by_entry = [], {}
    for (role, name), own in groups.items():
        first = own[0]
        row = {"entry": name, "role": role, "runner": first["runner"], "model": first["model"],
               "effort": first["effort"], "runs": len(own), "provider": None, "limits": None,
               "budget_enforced": False, "budget_cap_note": None, "lacks": [], "effort_note": None,
               "status": None}
        if not native:
            caps = runners.get(first["runner"]).capabilities()
            status = runners.get(first["runner"]).model_status(first)  # what only this model can answer
            errors, note = unfit(cfg, first, status)
            row.update(provider=status["provider"] or caps["provider"], status=status,
                       limits=pl.limits_for(cfg, role, first.get("key")),
                       budget_enforced=caps["budget_cap"], lacks=lacks(cfg, first, caps, status), effort_note=note,
                       budget_cap_note=(caps["budget_cap_note"] or None) if caps["budget_cap"] else None)
            problems += [f"{name}: {err}" for err in errors]
        models.append(row)
        by_entry[role, name] = row

    def run_row(e):
        m = by_entry[e["role"], label(e)]
        return {"run": e["run"], "role": e["role"], "persona": e.get("persona"), "name": e.get("name", ""),
                "key": e.get("key"), "runner": e["runner"], "model": e["model"], "effort": e["effort"],
                "limits": m["limits"], "budget_enforced": m["budget_enforced"],
                "budget_cap_note": m["budget_cap_note"], "unreported_attempts": unreported(e), "prompt": e["prompt"],
                "prompt_exists": (sd / e["prompt"]).is_file(), "file": e["file"], "state": states[e["run"]],
                "extended": e.get("extended") or 0}

    run_rows, job_rows = [run_row(e) for e in runs], [run_row(e) for e in planned]

    checked = []
    for name in dict.fromkeys(m["runner"] for m in models if not native):
        caps = runners.get(name).capabilities()
        check = runners.get(name).check()
        checked.append({
            "runner": name, "provider": caps["provider"], "ok": bool(check["ok"]), "message": check["message"],
            "concurrency": pl.runner_concurrency(cfg, name, caps["default_concurrency"]),
            "entries": [m["entry"] for m in models if m["runner"] == name],
            "billing_env_set": [v for v in caps["billing_env"] if os.environ.get(v)],  # names, never values
            "isolation_gaps": list(caps["isolation_gaps"]),
            # The gaps that browsing opens, when a panellist run of this study can browse on this runner.
            "browse_gaps": list(caps["browse_gaps"]) if cfg["browse"] and caps["browser"] and any(
                m["runner"] == name and m["role"] == "panellist" for m in models) else []})
        if not check["ok"]:
            problems.append(f"{name}: cannot be used: {check['message']}")

    there = f"{held(mat)}, {size(mat['bytes'])}" if mat["captured"] else "not captured yet"
    browse = browsing(cfg, mat)
    # With browsing on, the instructions every run reads give the address of each live page.
    told = " (which give the addresses of the live pages)" if browse and browse["on"] and browse["hosts"] else ""
    receives = {
        "full": f"its run prompt, the panel instructions{told} and everything under panel/materials ({there})",
        "text": "its run prompt, the panel instructions and the page text under panel/materials ("
                + (f"{plural(mat['text_files'], 'file')}, {size(mat['text_bytes'])}" if mat["captured"] else there)
                + "), with no images",
    }[cfg["materials"]]
    opens = []  # what a run that browses can open, besides what it reads
    if not browse or browse["sites"]:
        opens.append("any page of panel/sites it opens in the browser")
    if browse and browse["hosts"]:
        opens.append(f"any page it opens at {listed(browse['hosts'])}, as that page is at the time")
    providers = []
    for provider in dict.fromkeys(m["provider"] for m in models if not native):
        entries = []
        for m in (m for m in models if m["provider"] == provider):
            browses = (m["role"] == "panellist" and cfg["browse"]
                       and runners.get(m["runner"]).capabilities()["browser"])
            entries.append({
                "entry": m["entry"], "role": m["role"], "runner": m["runner"], "runs": m["runs"],
                "receives": (receives + (", and " + " and ".join(opens) if browses else "")
                             if m["role"] == "panellist" else
                             "the persona files it is given, analysis/ and whatever else in the study "
                             "directory it opens, where it works")})
        providers.append({"provider": provider, "entries": entries})

    usage = usage_figures([*runs, *planned], states)
    asked = pl.read_followups(sd)
    followups = {"asked": len(asked), "runs": sum(len(f.get("runs") or []) for f in asked),
                 "limits": None if native else pl.limits_for(cfg, "followup"),
                 "used": summed(usage["followups"]) if usage["followups"] else None,
                 "unallocated": summed([], usage["unallocated"]) if usage["unallocated"] else None}
    names = {e["run"]: label(e) for e in [*runs, *planned]}
    costed = {name: runners.get(name).capabilities()["usage"]["cost"] for name in {e["runner"] for e in runs + planned}
              if name}
    rows = [{**r, "entry": names[r["run"]], "reports_cost": costed.get(r["runner"], False)} for r in usage["runs"]]
    forecast = estimate(rows, mat["opens"], cfg["materials"] == "text")
    if browse and browse["not_browsable"] and any(e["basis"] == "method" for e in forecast["entries"]):
        unread = mat["pdfs"] and mat["pdf_pages"] is None  # its pages are not known until it is captured
        notes.append("the estimate's figure per page was measured on captured web pages. It counts every page of a "
                     "PDF and every supplied image as one such page, which is a guess until a pilot has measured one."
                     + (" A PDF that is not captured yet counts as one page." if unread else ""))
    return {
        "study": cfg.get("study") or sd.name, "dir": str(sd), "native": native, "launcher": launcher,
        "missing": missing, "notes": notes,
        "materials": mat, "browsing": browse, "models": models, "runs": run_rows, "runners": checked,
        "providers": providers,
        "synthesis": None if native else {
            "pool": pool, "share": pl.synthesis_share(cfg), "shares": cfg["synthesis"].get("analysts", 1) + 1,
            "jobs": job_rows,
            "missing": [role for role in pl.JOB_ROLES if not any(j["role"] == role for j in planned)]},
        "estimate": forecast,
        "used": summed(usage["runs"]),  # the runs and jobs: follow-ups are apart, under "followups"
        "ceiling": None if native else ceiling(run_rows, job_rows, pool),
        "followups": followups, "earlier_sessions": earlier,
        "problems": problems, "ok": not problems}


def render(plan: dict) -> list[str]:
    """The plan as the lines the plan command prints."""
    sd, native, mat = plan["dir"], plan["native"], plan["materials"]
    out = [f"Plan for {plan['study']} ({sd}). This command starts no run and changes no file of the study. "
           "A runner's sign-in check may let its harness refresh its own login."]
    if plan["launcher"]:
        out.append(f'A launcher is running "{plan["launcher"].get("command")}" on this study '
                   f'(pid {plan["launcher"]["pid"]}).')
    out += [f"Missing: {m}" for m in plan["missing"]] + [f"Note: {n}" for n in plan["notes"]]
    if native:
        out += ["", NATIVE]

    def limits_of(row):
        if row["limits"] is None:
            return ["-", "-"]
        return [f"{row['limits']['minutes']:g} min",
                money(row["limits"]["budget_usd"]) + (" cap" if row["budget_enforced"] else ", not enforced")]

    def entry_cells(row):
        return [row["runner"] or "-", row["model"] or "default", row["effort"] or "-"]

    out += ["", "Materials, what each run can read under panel/materials:"]
    if mat["mode"] == "text":
        dropped = mat["text_only"]["dropped_factors"]
        out.append("  Text-only study: panellists receive the page text only, page-text.txt for each page, with no "
                   "images and no browser." + (f" They do not score {listed(dropped)}." if dropped else ""))
    if not mat["captured"]:
        out.append(f"  Not captured yet. {held(mat, captured=False)} to capture, counted from {mat['pages_from']}.")
    elif mat["mode"] == "text":
        out.append(f"  {plural(mat['text_files'], 'page text file')}, {size(mat['text_bytes'])} "
                   f"({held(mat, images=False)}).")
    else:
        out.append(f"  {held(mat)}, {size(mat['bytes'])} in all, of which page text {size(mat['text_bytes'])}.")
        kinds = plan["browsing"] is not None  # a study of sites alone has no kind to tell apart
        out += table([[c["concept"], *([pl.KIND_NAMES.get(c["kind"], "no concept of this study")] if kinds else []),
                       held(c), size(c["bytes"])] for c in mat["concepts"]], "    ")
    out += browsing_lines(plan)

    panel = [m for m in plan["models"] if m["role"] == "panellist"]
    out += ["", f"Model entries ({len(panel)})"
            + (":" if native else ", with the limits in force for each of their runs:")]
    out += table([["Key", "Runner", "Model", "Effort", "Runs", "Time limit", "Budget", "Provider"],
                  *([m["entry"], *entry_cells(m), m["runs"], *limits_of(m), m["provider"] or "-"] for m in panel)])
    for m in plan["models"]:
        for lack in m["lacks"]:
            out.append(f"  {m['entry']} lacks {lack['capability']}: {stop(lack['means'])}")
        if m["budget_cap_note"]:
            out.append(f"  {m['entry']}: {stop(m['budget_cap_note'])}")
        if m["effort_note"]:
            out.append(f"  {m['entry']}: {stop(m['effort_note'])}")
        status = m["status"] or {}
        if status.get("message") and False not in (status["known"], status["signed_in"]):  # else it is a problem, below
            out.append(f"  {m['entry']}: {stop(status['message'])}")

    out += ["", f"Runs ({len(plan['runs'])}):"]
    out += table([["Run", "Persona", "Key", "Runner", "Model", "Effort", "Time limit", "Budget", "State", "Prompt"],
                  *([r["run"], f"{r['persona']} {r['name']}".strip(), r["key"], *entry_cells(r), *limits_of(r),
                     r["state"], r["prompt"] + ("" if r["prompt_exists"] else " (missing)")] for r in plan["runs"])])
    if native:
        out += ["", *estimate_lines(plan), *followup_lines(plan["followups"]), ""]
        return out

    out += ["", "Runners:"]
    for r in plan["runners"]:
        said = f"ready: {r['message']}" if r["ok"] else f"CANNOT BE USED: {r['message']}"
        out.append(f"  {r['runner']}: {stop(said)} Up to {plural(r['concurrency'], 'run')} at once.")
        if r["billing_env_set"]:
            out.append("    Set in this environment, and able to change who is billed: "
                       f"{', '.join(r['billing_env_set'])}.")
        if r["isolation_gaps"] or r["browse_gaps"]:
            out.append("    Not switched off for its runs:")
            out += [f"      - {gap}" for gap in [*r["isolation_gaps"], *r["browse_gaps"]]]

    out += ["", "What each provider receives:"]
    for p in plan["providers"]:
        out.append(f"  {p['provider']}")
        for e in p["entries"]:
            unit = "run" if e["role"] == "panellist" else "job"
            out.append(f"    {e['entry']} ({e['runner']}, {plural(e['runs'], unit)}): from each {unit}, "
                       f"{e['receives']}.")

    syn = plan["synthesis"]
    out += ["", f"Analysts and writer, under limits.synthesis ({syn['pool']['minutes']:g} min for each job, "
                f"{money(syn['pool']['budget_usd'])} as one pool):"]
    if syn["jobs"]:
        out += table([["Job", "Runner", "Model", "Effort", "Time limit", "Budget", "State", "Prompt"],
                      *([j["run"], *entry_cells(j), *limits_of(j), j["state"], j["prompt"]] for j in syn["jobs"])])
        out.append(f"  Each job's budget is its share of the pool, divided equally among the {syn['shares']} jobs "
                   "study.json plans. A brief is written to prompts/ when its job is started.")
    for role in syn["missing"]:
        out.append(f'  synthesis.{role} is missing from study.json: there is no default, so "run --role {role}" '
                   f'will refuse. Add "synthesis": {{"{role}": {{"runner": "<runner>", "model": "<model>"}}}}.')

    out += ["", *estimate_lines(plan), "", *ceiling_lines(plan["ceiling"], syn),
            *followup_lines(plan["followups"]), "", LIST_PRICE]
    if plan["problems"]:
        out += ["", 'Problems, which stop "run" as they stop this plan:', *(f"  {stop(p)}" for p in plan["problems"])]
    out.append("")
    return out


def browsing_lines(plan: dict) -> list[str]:
    """What the plan says of live pages and of the browser, in a study with a "url" or "files"
    concept: when each live page was captured, whether panellists may browse and where the
    instructions send them, and which concepts have nothing to open."""
    mat, browse = plan["materials"], plan["browsing"]
    if browse is None:
        return []
    out = []
    for live in mat["live"]:
        when = (time.strftime("on %Y-%m-%d at %H:%M", time.localtime(live["captured_at"])) if live["captured_at"]
                else None)
        out.append(f"  {live['concept']} is a live URL ({plural(len(live['pages']), 'page')} at "
                   f"{listed(live['hosts'])}). " + (
            f"It was captured {when}: the materials show the page as it was then, and it may have changed since."
            if when else "It is not captured yet: the capture will show the page as it is at that moment."))
    if browse["on"]:
        places = (["the copies in panel/sites"] if browse["sites"] else []) + (
            [f"the live pages at {listed(browse['hosts'])}"] if browse["hosts"] else [])
        out.append(f"  Browsing is on: panellists may open {' and '.join(places)} with agent-browser, on runners "
                   "that can.")
        if browse["hosts"]:
            out.append("  A panellist who browses a live page sees it as it is at review time, which may differ from "
                       "the capture. The instructions say to score from the materials and to note any difference.")
            out.append("  External hosts the instructions send panellists to: "
                       + (listed(browse["external_hosts"]) if browse["external_hosts"] else "none") + "."
                       + (f" On this machine: {listed(browse['local_hosts'])}, whose server must be running during "
                          "the runs." if browse["local_hosts"] else ""))
            out.append("  Nothing limits agent-browser to those hosts. The instructions tell panellists to stay on "
                       "them and to submit nothing, and every visit reaches the site's server and its analytics.")
        if browse["not_browsable"]:
            out.append(f"  {listed(browse['not_browsable'])} cannot be opened in a browser: "
                       f"{agree(len(browse['not_browsable']), 'it is', 'they are')} reviewed from the files, and "
                       "the instructions say so.")
    elif browse["off_because"] == "url":
        out.append('  Browsing is off: a study with a live URL browses only when study.json says "browse": true. '
                   "Panellists see the capture alone, and are given no address.")
    elif browse["off_because"] == "files":
        out.append("  Browsing is off: every concept is made of files, which have nothing to open.")
    elif mat["mode"] != "text":
        out.append('  Browsing is off ("browse": false): panellists see the capture alone.')
    return out


def estimate_lines(plan: dict) -> list[str]:
    est, used = plan["estimate"], plan["used"]
    out = ["Estimate of what the runs still to go will use (a forecast, not a limit):"]
    for e in est["entries"]:
        per, unit = e["per_run"], "run" if e["role"] == "panellist" else "job"
        go = plural(e["to_go"], unit) + " to go"
        if e["basis"] in ("measured", "duration"):
            cost = money(per["cost_usd"]) if per["cost_usd"] is not None else "cost not reported"
            tokens = f"{per['tokens']:,} tokens" if per["tokens"] is not None else "tokens not reported"
            line = (f"measured on {plural(e['measured_runs'], 'finished ' + unit)}: {tokens}, {cost} and "
                    f"{span(per['seconds'])} a {unit}. ")
            out_of = e["left_out"]
            if out_of["unreported"] or out_of["unallocated"]:
                why = ([f"{out_of['unreported']} stopped before the harness reported what it used"]
                       if out_of["unreported"] else []) + (
                    [f"{out_of['unallocated']} whose usage cannot be told apart from a follow-up's"]
                    if out_of["unallocated"] else [])
                line += (f"Left out of the tokens and cost, and counted for the time: {' and '.join(why)}. ")
            if not e["to_go"]:
                line += f"No {unit} to go."
            else:
                parts = ([f"{e['tokens']:,} tokens"] if e["tokens"] is not None else []) + (
                    [money(e["cost_usd"])] if e["cost_usd"] is not None else []) + [
                    f"{span(e['seconds'])} of run time"]
                line += f"{go}: about {', '.join(parts)}" + (
                    "." if e["cost_usd"] is not None else ". No dollar figure, so judge it by the time.")
        elif e["basis"] == "method":
            line = ("no finished run to measure. A rough forecast, from the method's figure of about "
                    f"{est['tokens_per_concept_page']:,} tokens of context per concept page per run, and "
                    f"{plural(est['pages'], 'page')} for a run to open: about "
                    f"{per['tokens']:,} tokens a run, {e['tokens']:,} for {go}. No dollar figure: "
                    + ("native mode records no usage." if plan["native"]
                       else "a pilot will provide one." if e["reports_cost"]
                       else "its harness reports no cost, so judge it by the time."))
        else:
            line = (f"no finished {unit} to measure, and the method has no figure for it. {go.capitalize()}. "
                    f"No token or dollar figure: {e['cost']}.")
        out.append(f"  {e['entry']}: {line}")
    if est["tokens"] is not None or est["cost_usd"] is not None:
        def without(names, what):  # a sum covers only the model entries that have the figure: name the others
            return (f" (without {listed(names)}, which {agree(len(names), 'has', 'have')} no {what} figure)"
                    if names else "")

        parts = ([f"{est['tokens']:,} tokens" + without(est["no_tokens_for"], "token")]
                 if est["tokens"] is not None else []) + (
            [money(est["cost_usd"]) + without(est["no_cost_for"], "dollar")] if est["cost_usd"] is not None else [])
        out.append(f"  In all: about {' and '.join(parts)}." + (
            " No token figure for any of them." if est["tokens"] is None else
            " No dollar figure for any of them." if est["cost_usd"] is None else ""))
    if used["started"]:
        tokens = (f"{used['input_tokens'] + (used['output_tokens'] or 0):,} tokens"
                  if used["input_tokens"] is not None else "tokens not reported")
        out.append(f"  Used so far, by the {plural(used['started'], 'run or job', 'runs and jobs')} started: {tokens}, "
                   f"{money(used['cost_usd']) if used['cost_usd'] is not None else 'cost not reported'}.")
    elif not plan["native"]:
        out.append("  Nothing has run yet: launch.py pilot runs one persona on each model entry, and the next plan "
                   "estimates from what it measured.")
    return out


def ceiling_lines(c: dict, syn: dict) -> list[str]:
    out = [f"Ceiling: {money(c['usd'])}, " + (
        f"a guaranteed maximum{' apart from the caveats below' if c['caveats'] else ''}: every run and job has a "
        "budget cap that its harness enforces." if c["guaranteed"]
        else "an estimate, not a guaranteed maximum: some runs or jobs have no budget cap.")]
    out.append(f"  {money(c['capped_runs_usd'])} for {plural(c['capped_runs'], 'run')} with an enforced cap, each "
               "counted once, because a cap covers all of a run's attempts.")
    out.append(f"  {money(c['synthesis_usd'])} for the synthesis pool, counted once, because it is split into the "
               "jobs' caps. Panellist runs never spend it.")
    if c["uncapped"]:
        shown = ", ".join(c["uncapped"][:8]) + (", ..." if len(c["uncapped"]) > 8 else "")
        n = len(c["uncapped"])
        out.append(f"  {plural(n, 'run')} on a runner without a budget cap {agree(n, 'is', 'are')} left out of the "
                   f"figure ({shown}). The time limit is what bounds {agree(n, 'it', 'them')}: at most "
                   f"{span(c['uncapped_minutes'] * 60)} of run time{agree(n, '', ' between them')}.")
    if c["uncapped_jobs"]:
        n = len(c["uncapped_jobs"])
        out.append(f"  {plural(n, 'job')} on a runner without a budget cap {agree(n, 'has its', 'have their')} share "
                   f"of the pool counted, but nothing enforces it ({', '.join(c['uncapped_jobs'])}). The time limit "
                   f"is what bounds {agree(n, 'it', 'them')}: at most {span(c['uncapped_job_minutes'] * 60)} of run "
                   f"time{agree(n, '', ' between them')}.")
    out += [f"  Caveat: {stop(caveat)}" for caveat in c["caveats"]]
    if not c["holds"]:
        out.append(f"  The ceiling no longer holds: resume --extend gave more than one allowance of the limits to "
                   f"{', '.join(c['extended'])}. With those allowances it comes to {money(c['with_extensions_usd'])}.")
    return out


def followup_lines(f: dict) -> list[str]:
    """What the plan says of follow-up questions: how many were asked, and, for a study that
    runs through runners, that they are limited apart from the runs and outside the ceiling."""
    asked = (f"{plural(f['asked'], 'question')} asked so far, of {plural(f['runs'], 'run')} in all"
             if f["asked"] else "none asked so far")
    if f["limits"] is None:
        return ["", f"Follow-up questions (followup.py): {asked}, each sent by hand."] if f["asked"] else []
    used = f["used"]
    shared = f.get("unallocated")
    spent = "" if not used else (f" So far they have used {money(used['cost_usd'])}." if used["cost_usd"] is not None
                                 else "" if shared else " Their cost so far was not reported.")
    if shared:
        spent += (f" {money(shared['cost_usd']) if shared['cost_usd'] is not None else 'Usage'} was reported for a "
                  "follow-up and its run in one figure, which cannot be split (analysis/usage.md, Unallocated).")
    return ["", f"Follow-up questions (followup.py): {asked}.",
            f"  Each run asked may use up to {f['limits']['minutes']:g} min and {money(f['limits']['budget_usd'])} "
            "for each question (limits.followup), apart from its run limits. That spend is outside the ceiling "
            f"above.{spent}"]
