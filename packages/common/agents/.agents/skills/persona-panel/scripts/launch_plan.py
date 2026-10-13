"""What launch.py says about a study without starting anything: the plan, and the usage record.

launch.py owns the commands (plan, usage); this module works out the facts and words them. It
knows no harness: everything about one comes from its runner's capabilities(), check(),
shell_check() and model_status().

    usable(name)                  whether a runner's CLI can be used from this shell: installed
                                  and signed in, and able to do a run here at all. The same
                                  judgement stops "plan", "run" and a follow-up
    unwritable_study(cfg)         why this shell cannot start a run as far as the study directory
                                  goes: the launcher records every run there
    unfit(cfg, entry)             why a run or job cannot be started on its runner as study.json
                                  has it. The same judgement stops "plan" and "run"
    materials(cfg)                what is captured under panel/materials, per concept and in all
    no_materials(cfg, mat)        why no panellist run may start as the materials stand. The
                                  plan lists it as missing, and "run" refuses on it
    usability(cfg)                what the plan says of a usability study: its target, tasks,
                                  step limits, success checks, accounts and time rule. It
                                  provisions nothing and runs no check
    interview(cfg, runs, states)  what the plan says of an interview study: every interview with
                                  both its sides, its caps and its limits, the tools each side
                                  has on its runner, and how many are carried at once
    no_browser(cfg, names)        why no run that browses can start: the agent-browser CLI is
                                  not on PATH. The plan lists it as a problem, and "run" refuses
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

An interview study (panel_lib.py, "Interview studies"). An interview is two runs.json entries,
its participant's and its interviewer's, and the plan is given both: runs holds the
interviewers' entries with the participants'. Each side has limits of its own, so each is a
row of the model entries, a line of the estimate and a cap of the ceiling, which counts each
side of each interview once. The section on the study (interview_lines()) takes the place of
the materials, and the interviews, one row each with both sides' limits (interview_rows()),
the place of the runs.

Its estimate. A model entry with a finished interview is measured as any other: the mean of
what that side of its finished interviews reported, times the interviews to go, with what
that came to for each exchange (interview.measured()), so that an interview of another length
can be judged. One with none gets the method's figure for an interview, TURN_TOKENS: the input
tokens of one process of a side at each exchange, added up to the interview's cap. Those were
measured for a runner and a side, never for a model, on the date and the CLI versions
TURN_TOKENS_FROM names, and they are the one place where this module names a runner: a runner
with no figure there gets none. The figure is what it says and no ceiling: an interview that
ends before its cap uses less, and the participant's first reply, a reply that is sent back
and a turn that is put again are processes it does not count, so what a capped interview
used has come in a little over it. It is input alone, nearly all of it read from a cache after
a side's first process. No interview is ever given the per-page figure of a review.

A runner's note on its budget cap ("budget_cap_note") is in its harness's words, where a run
is one process and a turn one request of that process to the model. An interview study's plan
uses "turn" for a turn of the interview, so there what the note's words mean is said
(HARNESS_WORDS): once under the notes of the model entries, and with the ceiling's caveat.

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
import shutil
import time
from pathlib import Path
from urllib.parse import urlsplit

import browser_session as browser
import interview as rules  # the module: interview() below is the plan's section on an interview study
import panel_lib as pl
import runners

# references/method.md, "Budget": images dominate a run's context, at roughly 20k tokens per
# concept page reviewed. It was measured on captured web pages, each read as its sheets and its
# page text, and it is the size of the context a run builds up, not the tokens a harness bills
# (every turn reads the context again). The estimate multiplies it by what a run opens
# (folder_counts(), "opens"), where a page of a PDF and a supplied image each count as one such
# page: nothing has measured those, so it stands in only until a pilot has measured the real figure.
TOKENS_PER_CONCEPT_PAGE = 20_000
# The method's figure for an interview: the input tokens of one process of a side at exchange e are about
# base + slope * e, as (base, slope). Fitted to interviews of 23 to 34 exchanges with the situation card on, every
# turn a resumed session, the reference notes in the interviewer's brief and no tools on either side
# (docs/specs/persona-panel-interviews.md, discovery items 1 and 7). By runner and side, never by model: the
# harness's own fixed prefix is the larger part of every request. A runner with no entry has no figure.
TURN_TOKENS = {("claude", "participant"): (4_300, 200), ("claude", "interviewer"): (10_600, 260),
               ("codex", "participant"): (12_100, 62), ("codex", "interviewer"): (18_250, 155)}
TURN_TOKENS_FROM = "13 October 2026 with Claude Code 2.1.296 and codex-cli 0.162.1"  # when, and on which CLIs

IMAGE_TYPES = pl.IMAGE_TYPES
TO_GO = ("pending", "running", "partial", "blocked", "failed")  # a limited run starts again only with --extend
FIGURES = ("input_tokens", "output_tokens", "cached_tokens", "cost_usd", "duration_s")
LIST_PRICE = ("Dollar figures are list-price equivalents: under a subscription login nothing is charged per "
              "token, so they say how much allowance is used, not what is paid.")
NATIVE = ("Native mode: the lead starts each run with its own subagent tool (runs.py next, mark and resume). "
          "Native mode has no limits, no usage record and no isolation beyond the instructions in the run "
          "prompt, so there is no ceiling and nothing below is enforced.")
CEILING_LABELS = {True: "guaranteed maximum", False: "estimate"}
# The floor for the models of an interview study, in every plan of one. By tier: the plan cannot tell a tier from
# a model's name, no model is named or matched anywhere, and the launcher holds the floor by what a model does.
TIERS = ("Both sides need a mid-tier model or larger, never a vendor's smallest and fastest tier, and the "
         "interviewer the strongest model you have. In testing, small models refused the participant's role, asked "
         "two questions at once and left topics unopened.")
# What a runner's note on its budget cap means by its words, for the plan of an interview study, where a turn is
# a turn of the interview: after "In the lines above on a budget cap, " or "There ".
HARNESS_WORDS = ('"run" and "turn" are the harness\'s words: a run is one process, which here is one turn of an '
                 "interview or one job, and a turn is one request of that process to the model.")
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

def usable(name: str) -> dict:
    """Whether a runner's CLI can be used from the shell this command runs in: {"ok", "message",
    "shell"}. First its check(): installed, signed in, its options still accepted. Then, when
    that passes, its shell_check(): whether this shell lets the CLI do a run at all, which a
    sandboxed shell tool may not while the check passes. "shell" is False when that is what
    stops it, and the message then says what the CLI cannot do here and the two ways out
    (pl.SANDBOX_HINT). None when the check itself failed, and the message is the CLI's. Neither
    makes a model call. The plan asks here, and so does every command that starts a process
    (launch.fitness()): what one refuses, the others do."""
    runner = runners.get(name)
    checked = runner.check()
    if not checked["ok"]:
        return {"ok": False, "message": checked["message"], "shell": None}
    here = runner.shell_check()
    if here["ok"]:
        return {"ok": True, "message": checked["message"], "shell": True}
    return {"ok": False, "shell": False,
            "message": f"{checked['message'].strip().rstrip('.')}, but from this shell it "
                       f"{stop(here['message'])} {pl.SANDBOX_HINT}"}


def unwritable_study(cfg: dict) -> str | None:
    """Why nothing can be started from this shell as far as the study directory goes, as the end
    of a sentence, or None when a file can be written there. The launcher's own part of what a
    shell must allow (usable() asks each runner for its CLI's): it records every run in the
    study directory, and every run writes there."""
    why = runners.unwritable(cfg["_dir"])
    return (f"this shell cannot write to the study directory {cfg['_dir']} ({why}), where the launcher records "
            f"every run and every run writes, so no run can be started from it. {pl.SANDBOX_HINT}") if why else None


def label(entry: dict) -> str:
    """The name of an entry's model entry: its model key for a panellist run, its role for a job
    (synthesis.analyst and synthesis.writer are one model entry each) and for an interviewer
    (interview.interviewer is one too)."""
    return entry["key"] if entry["role"] == "panellist" else entry["role"]


def side_of(entry: dict) -> str:
    """Which side of a conversation an entry speaks for (pl.SIDES): the interviewer's entry is
    the interviewer, and any other the participant."""
    return "interviewer" if entry["role"] == "interviewer" else "participant"


def no_interview(name: str) -> str | None:
    """Why no side of an interview can be on a runner, else None. A runner must declare that it
    is verified for interviews (runners.can(), "interview"), and must be able to resume a
    session: every turn after a side's first continues one."""
    runner = runners.get(name)
    if not runners.can(runner, "interview"):
        verified = []
        for other in runners.names():
            try:
                verified += [other] if runners.can(runners.get(other), "interview") else []
            except SystemExit:  # a module of the package that is no whole runner
                continue
        return (f"{name} is not verified for interviews, and an interview is carried turn by turn through its "
                f"runner. Put the model entry on a runner that is ({', '.join(verified)})")
    if not runner.capabilities()["resume"]:
        return f"{name} cannot resume a session, and every turn of an interview after the first is one"
    return None


def reads_images(caps: dict, status: dict) -> bool:
    """Whether a model entry's runs can open an image file: what its runner found out about the
    model, and the runner-wide answer where it could not tell."""
    return caps["images_by_path"] if status["images"] is None else status["images"]


def unfit(cfg: dict, entry: dict, status: dict | None = None,
          interview: bool | None = None) -> tuple[list[str], str | None]:
    """Why a run or job cannot be started on its runner as study.json has it, and a note where
    something it asks for is left out instead: (errors, note). An error refuses the launch.
    status is the runner's model_status() for the entry, asked for here when not given.
    interview: the entry is a side of a conversation, which is what "interview" on it says when
    this is not given. Its runner must be one that can carry an interview (no_interview()), and
    nothing more is asked of a runner that cannot. Such an entry reviews and browses nothing,
    so it is held to neither the browser of a usability study nor the images of a review: it
    is given words alone."""
    runner = runners.get(entry["runner"])
    caps, effort = runner.capabilities(), runners.check_effort(entry)
    errors = [effort["error"]] if effort["error"] else []
    talks = "interview" in entry if interview is None else interview
    refused = no_interview(entry["runner"]) if talks else None
    if refused:
        return [*errors, refused], effort["note"]
    status = status or runner.model_status(entry)
    reviews = entry["role"] == "panellist" and not talks
    if status["known"] is False or status["signed_in"] is False:
        errors.append(status["message"] or f'{entry["runner"]} cannot run the model "{entry["model"]}"')
    elif reviews and cfg["type"] == "usability" and not caps["browser"]:
        errors.append(f'{entry["runner"]} cannot drive a browser, and a usability study is done in one: its runs '
                      "could attempt no task. Take the model entry out, or put it on a runner that can browse")
    elif reviews and cfg["materials"] == "full" and not reads_images(caps, status):
        who = entry["runner"] if status["images"] is None else f'{entry["model"]} on {entry["runner"]}'
        errors.append(f'{who} cannot open images, and this study\'s "materials" is "full", so its '
                      'runs would review designs they cannot see. A model that reads no images is for '
                      'text-only studies: set "materials": "text", or take the model entry out')
    return errors, effort["note"]


def lacks(cfg: dict, entry: dict, caps: dict, status: dict) -> list[dict]:
    """The capabilities a model entry does not have on its runner, each with what that means here.
    A side of an interview opens no image and no browser, and lacks neither."""
    talks = "interview" in entry
    panellist, out = entry["role"] == "panellist" and not talks, []
    if panellist and not reads_images(caps, status):
        out.append(("images", "it cannot open an image file" + (
            ", which a text-only study does not need" if cfg["materials"] == "text" else "")))
    if not caps["budget_cap"]:
        out.append(("budget cap", "the harness enforces no spend cap, so the time limit is what bounds "
                                  + ("its side of an interview" if talks else "its runs")))
    if not caps["resume"]:
        out.append(("resume", "an interrupted run cannot be continued in its session"))
    if panellist and cfg["browse"] and not caps["browser"] and cfg["type"] != "usability":  # there it is refused
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
    "resume" refuse on it (launch.preflight), so what one says the other does. A usability study
    and an interview study have no materials, and none to wait for."""
    if cfg["type"] != "review":
        return None
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


def no_browser(cfg: dict, names) -> str | None:
    """Why no run that browses can start, else None: the study's runs may browse, on one of the
    runners named, and the agent-browser CLI that the launcher starts each run's browser session
    with (browser_session.py) is not on PATH. The plan lists it as a problem, and "run", "pilot"
    and "resume" refuse on it (launch.preflight)."""
    if not cfg["browse"] or not any(runners.get(name).capabilities()["browser"] for name in names if name):
        return None
    if shutil.which(browser.CLI):
        return None
    return (f"the {browser.CLI} CLI is not on PATH, and the launcher starts a browser session with it for every run "
            "that may browse: none could be started. Install it, or add its folder to PATH"
            + ("" if cfg["type"] == "usability" else ', or set "browse": false to review from the materials alone'))


# ---------------------------------------------------------------- usability studies

def usability(cfg: dict) -> dict | None:
    """What the plan says of a usability study, None for a review: the target and whether it is
    a local development host, the tasks, the accounts arrangement, whether runs are sequential,
    and the rule a run's time limit comes from. Read from study.json alone: no command of the
    study is run, so nothing is provisioned."""
    if cfg["type"] != "usability":
        return None
    acc, steps = cfg["accounts"], sum(t["steps"] for t in cfg["tasks"])
    states = [bool(a.get("state")) for a in (acc or {}).get("map", {}).values()]
    return {
        "base_url": cfg["target"]["base_url"], "local": not cfg["_remote"],
        "tasks": [{"id": t["id"], "goal": " ".join(t["goal"].split()), "start": pl.task_url(cfg, t),
                   "steps": t["steps"], "success_check": t.get("success_check"), "read_only": t["read_only"]}
                  for t in cfg["tasks"]],
        "accounts": None if not acc else {
            "source": "map" if "map" in acc else "provision", "provision": acc.get("provision"),
            "signin": acc["signin"], "teardown": acc.get("teardown"), "reset": acc.get("reset"),
            # with a map, how many of its accounts name a saved browser state: a command says only when it is run
            "with_state": sum(states) if "map" in acc else None, "accounts": len(states) if "map" in acc else None},
        "sequential": cfg["sequential"],
        "time": {"minutes": pl.usability_minutes(cfg), "steps": steps, "step_seconds": pl.STEP_SECONDS,
                 "run_minutes": pl.RUN_MINUTES, "set": "minutes" in (cfg["limits"].get("run") or {})}}


def usability_lines(plan: dict) -> list[str]:
    """The plan's section on a usability study, in place of the materials."""
    u = plan["usability"]
    out = ["", "Usability study, what each run does in the running product:"]
    if u["local"]:
        out.append(f"  Target: {u['base_url']}, a local development host. It must be running during the runs.")
    else:
        out += [f"  REMOTE TARGET: {u['base_url']} is not a local development host, and study.json allows it "
                '("allow_remote").',
                "  Every task is read-only: panellists are told to submit nothing, sign in nowhere and change "
                "nothing, and no account is used.",
                "  Only that instruction stands between a panellist and a form: nothing limits what its browser "
                "submits, and every visit reaches the site's server and its analytics."]
    out.append(f"  {plural(len(u['tasks']), 'task')}, attempted in this order by every run:")
    out += table([["Task", "Step limit", "Starts at", "Success check", "Goal"],
                  *([t["id"], t["steps"], t["start"], t["success_check"] or "none", t["goal"]] for t in u["tasks"])],
                 "    ")
    out += ["  Step limits: a panellist is told each task's limit and keeps to it itself. At the limit it records "
            '"ran out of steps" and goes on to the next task.',
            "    The launcher is the backstop: it reads each run's step log while the run is in flight, and an "
            "intent entry numbered above its task's limit stops the run as limited, after the grace period.",
            "    It counts the steps a log shows, and stops a run whose log it cannot read: a run that logs no step "
            "is bounded by its time limit alone."]
    checked = [t for t in u["tasks"] if t["success_check"]]
    if checked:
        out += [f"  Success checks: {plural(len(checked), 'task')} of {len(u['tasks'])} "
                f"{agree(len(checked), 'has', 'have')} one ({', '.join(t['id'] for t in checked)}). Each is run with "
                "the run id when a run is done, limited or failed, before its test account is torn down.",
                "    Exit code 0 says the task was really completed, 1 that it was not, and any other that the "
                "check failed to run, which is no verdict. A check is the lead's: no panellist is shown one."]
        unchecked = [t["id"] for t in u["tasks"] if not t["success_check"]]
        if unchecked:
            out.append(f"    No success check for {listed(unchecked)}: whether "
                       f"{agree(len(unchecked), 'it was', 'they were')} completed is each panellist's own claim.")
    else:
        out.append("  Success checks: none. Whether a task was completed is each panellist's own claim.")
    time = u["time"]
    if not time["set"]:
        out.append(f"  Time limit: {time['minutes']:g} min a run, from the tasks: {time['step_seconds']} s for each "
                   f"of the {plural(time['steps'], 'step')} they permit, plus {time['run_minutes']} min. Set "
                   "limits.run.minutes to choose another.")
    acc = u["accounts"]
    if acc:
        how = (f"its entry of accounts.map ({plural(acc['accounts'], 'account')})" if acc["source"] == "map"
               else f"accounts.provision ({acc['provision']} <run id>), run once for it")
        out.append(f"  Accounts: each run gets a test account from {how}, just before it starts. This plan "
                   "provisions nothing.")
        if acc["signin"] == "panellist":
            out += ['    SECRETS ARE GIVEN TO PANELLISTS: accounts.signin is "panellist", so each panellist reads '
                    "its account's secrets in panel/scratch/<run id>/account.json and types them. Use it only when "
                    "signing in is the task under test.",
                    "    Those secrets reach each model's provider and stay in its harness's session record, and "
                    "any screenshot of such a run may show one."]
        elif acc["source"] == "map":
            without = acc["accounts"] - acc["with_state"]
            out.append(f"    Signed-in start: {plural(acc['with_state'], 'run')} "
                       f"{agree(acc['with_state'], 'starts', 'start')} signed in, from the saved browser state "
                       "its account names, and no panellist is given a secret."
                       + (f" {plural(without, 'account')} {agree(without, 'names', 'name')} no state: "
                          f"{agree(without, 'that run starts', 'those runs start')} signed out, with nothing to "
                          "sign in with." if without else ""))
        else:
            out.append("    Signed-in start: a run whose account names a saved browser state starts signed in, and "
                       "no panellist is given a secret. A run whose account names none starts signed out, with "
                       "nothing to sign in with.")
        out.append(f"    Teardown: accounts.teardown ({acc['teardown']} <run id>) is run once when a run is done, "
                   "limited or failed." if acc["teardown"] else
                   "    No accounts.teardown: an account outlives its run, and so does its saved session.")
        out.append("    A panellist is given the account's identifiers. What it reads or types stays in its "
                   "harness's session record: purge-sessions deletes those where the harness allows it.")
    elif u["local"]:
        out.append("  No accounts: every task is attempted without signing in.")
    out.append("  Runs: one at a time, across all runners (\"sequential\": true)"
               + (f", with accounts.reset ({acc['reset']} <run id>) between runs." if acc and acc["reset"] else ".")
               if u["sequential"] else "  Runs: side by side, within each runner's concurrency.")
    return out


# ---------------------------------------------------------------- interview studies

def interview_tokens(runner: str, side: str, exchanges: int) -> int | None:
    """The method's figure for one side of an interview of that many exchanges, in input tokens:
    one process of TURN_TOKENS for each exchange, added up. None for a runner it has no figure
    for."""
    if (runner, side) not in TURN_TOKENS:
        return None
    base, slope = TURN_TOKENS[runner, side]
    return exchanges * base + slope * exchanges * (exchanges + 1) // 2


def interview(cfg: dict, runs: list[dict], states: dict) -> dict | None:
    """What the plan says of an interview study, None for a study of another type. runs are the
    participants' entries and the interviewers', and states maps each to its state.

    "interviews" has one object for each interview: its run id and persona, both sides
    ("participant" and "interviewer": the model entry, its limits, whether its harness enforces
    the budget, the tools it is started with and the allowances --extend gave it), the
    interview's cap, the cap of each topic its persona gets, the exchanges on record, its state
    and, from its turn log, what it waits for and why it stopped (interview.standing()), with
    "malformed", what is wrong with a turn log that is not as a launcher writes one, else None
    (interview.malformed()): "run" and "resume" leave such an interview alone.
    "tools" says, for each runner, which model entries are on it and what a side there is left
    with: "none" with the runner's own account of that ("no_tools_note"), or "files" on a runner
    that cannot start a process without tools. "carried" is how many interviews a launcher
    carries at once, which is the slots of the interviewer's runner. "notes" are what the lead
    should know: a participant or the critic on the interviewer's runner and model, and topic
    caps that add up to more than the interview's. Read from study.json, runs and the turn
    logs: nothing is started."""
    if cfg["type"] != "interview":
        return None
    sd, held = cfg["_dir"], cfg["interview"]
    panel, hosts = ([e for e in runs if e["role"] == role] for role in ("panellist", "interviewer"))
    host_of = {h["interview"]: h for h in hosts}
    host_of = {e["run"]: host_of.get(e["run"]) or pl.interviewer_entry(cfg, e) for e in panel}

    def side(e: dict) -> dict:
        runner = runners.get(e["runner"])
        return {"run": e["run"], "entry": label(e), "runner": e["runner"], "model": e["model"], "effort": e["effort"],
                "limits": pl.limits_for(cfg, e["role"], e.get("key")),
                "budget_enforced": runner.capabilities()["budget_cap"], "tools": rules.tools(side_of(e), runner),
                "extended": e.get("extended") or 0}

    interviews, over = [], {}
    for e in panel:
        guide, records = pl.guide(cfg, e["persona"]), pl.read_turns(sd, e["run"])
        stands = rules.standing(records, guide)
        interviews.append({
            "run": e["run"], "persona": e["persona"], "name": e.get("name", ""), "participant": side(e),
            "interviewer": side(host_of[e["run"]]), "cap": guide["turns"],
            "topics": [{"id": t["id"], "turns": t["turns"]} for t in guide["topics"]],
            "exchanges": sum(r["t"] == "answer" for r in records), "state": states[e["run"]],
            "awaiting": stands["awaiting"], "reason": stands["reason"], "malformed": rules.malformed(records)})
        if sum(t["turns"] for t in guide["topics"]) > guide["turns"]:
            over[e["persona"]] = sum(t["turns"] for t in guide["topics"])

    sides, tools = [*panel, *host_of.values()], []
    for name in dict.fromkeys(e["runner"] for e in sides):
        runner = runners.get(name)
        for given in dict.fromkeys(rules.tools(side_of(e), runner) for e in sides if e["runner"] == name):
            mine = [e for e in sides if e["runner"] == name and rules.tools(side_of(e), runner) == given]
            tools.append({"runner": name, "tools": given, "entries": list(dict.fromkeys(label(e) for e in mine)),
                          "sides": [x for x in pl.SIDES if any(side_of(e) == x for e in mine)],
                          "note": runner.capabilities().get("no_tools_note") if given == "none" else None})

    def named(pair: tuple) -> str:
        return f"{pair[0]}, {pair[1] or 'its default model'}"

    asks, notes = list(dict.fromkeys((h["runner"], h["model"]) for h in host_of.values())), []
    same = list(dict.fromkeys(e["key"] for e in panel if (e["runner"], e["model"]) in asks))
    if same:
        n = len(same)
        notes.append(f"{listed(same)} {agree(n, 'is', 'are')} on the interviewer's runner and model "
                     f"({listed([named(a) for a in asks])}): in {agree(n, 'its', 'their')} interviews one model "
                     "asks and answers, each in a session of its own that is given only what the other says. That "
                     "is allowed.")
    critic = cfg["synthesis"].get("critic")
    critic = pl.model_entry(critic, cfg.get("runner"), "synthesis.critic") if critic is not None else None
    if critic and (critic["runner"], critic["model"]) in asks:
        notes.append(f"synthesis.critic is on the interviewer's runner and model ({named(asks[0])}): the critique "
                     "of the interviewer's questions would come from the model that asked them. Give it another "
                     "model where you have one.")
    if over:  # by what they add up to, which "segments" can make another figure for another persona
        everyone = len({e["persona"] for e in panel})
        sums = [f"{total} exchanges for " + ("every persona" if len(own) == everyone > 1 else listed(own))
                for total in dict.fromkeys(over.values()) for own in [[p for p, t in over.items() if t == total]]]
        notes.append(f"the topic caps add up to {listed(sums)}, and an interview has at most {held['turns']}: "
                     "not every topic can run to its cap.")
    first = next(iter(host_of.values()))
    return {
        "about": held["about"], "goals": [g["id"] for g in held["goals"]],
        "topics": [{"id": t["id"], "area": t["area"], "turns": t["turns"], "segments": t["segments"]}
                   for t in held["topics"]],
        "turns": held["turns"], "card": held["situation_card"],
        "interviewer": {k: first[k] for k in ("runner", "model", "effort")},
        "limits": {"turn": pl.limits_for(cfg, "turn"), "interviewer": pl.limits_for(cfg, "interviewer")},
        "carried": [{"runner": name, "interviews": sum(h["runner"] == name for h in host_of.values()),
                     "at_once": pl.runner_concurrency(cfg, name,
                                                      runners.get(name).capabilities()["default_concurrency"])}
                    for name in dict.fromkeys(h["runner"] for h in host_of.values())],
        "tools": tools, "tiers": TIERS, "notes": notes, "interviews": interviews}


def interview_lines(plan: dict) -> list[str]:
    """The plan's section on an interview study, in place of the materials: what an interview
    is, the guide, the caps and limits and who enforces each, how many are carried at once, the
    tools each side has on each runner, the floor for the models, and the notes."""
    t = plan["interview"]
    seat, topics = t["interviewer"], t["topics"]
    limited = [f"{x['id']} is put only to the {agree(len(x['segments']), 'segment', 'segments')} "
               f"{listed(x['segments'])}" for x in topics if x["segments"]]
    out = ["", "Interview study, what each interview is:",
           "  Two sessions: a participant, who plays its persona, and an interviewer, who follows the guide. The "
           "launcher carries every turn between them, so each side is given the other's words and nothing else.",
           f"  Guide: {plural(len(t['goals']), 'learning goal')} and {plural(len(topics), 'topic')} "
           f"({', '.join(x['id'] for x in topics)}). " + "".join(f"{x}. " for x in limited)
           + ("Each participant writes a situation card before the first question, which its interviewer never sees."
              if t["card"] else 'No situation card: each participant replies "Ready", and the interview begins.'),
           f"  Interviewer: {seat['runner']}, {seat['model'] or 'its default model'}"
           + (f", effort {seat['effort']}" if seat["effort"] else "")
           + ", for every interview (interview.interviewer).",
           "  Caps and limits:",
           f"    interview.turns: at most {plural(t['turns'], 'exchange')} an interview, each a question and its "
           "answer. The launcher counts them, and ends the interview there.",
           "    A topic's cap: the interviewer is told when a topic reaches it, and may still go on. An exchange "
           "past it is delivered and counted, and check_runs.py notes it.",
           "    limits.run and limits.interviewer: what the participant and the interviewer may each use over a "
           "whole interview, in spend and in the time of its own processes. Both are in the tables below.",
           f"    limits.turn: {t['limits']['turn']['minutes']:g} min for one turn of either side. A turn stopped "
           "there is not put again unasked: its interview reads partial until resume takes it up, or failed at a "
           "side's first turn, which run starts once more."]
    for c in t["carried"]:
        out.append(f"  At once: up to {plural(c['at_once'], 'interview')} carried at a time, as many as the "
                   f"interviewer's runner ({c['runner']}) runs processes at once. Each turn is one process on the "
                   "runner of its own side, and waits there for a slot.")
    out.append("  Tools: no side is given one where its runner can start a process without. Each side starts in a "
               "folder of its own that holds nothing.")
    for x in t["tools"]:
        who = f"{x['runner']} ({', '.join(x['entries'])})"
        kept = " and ".join(f"{side}s" for side in x["sides"])
        out.append(f"    {who}: {stop(x['note'] or 'as few tools as its harness allows')}" if x["tools"] == "none" else
                   f"    {who}: it cannot start a process without tools. Its {kept} keep the file tools a review run "
                   "has. What keeps them to their folders is their instructions, and whatever its runner does about "
                   "it, which is under Runners, below.")
    return out + [f"  Models: {t['tiers']}", *(f"  Note: {note}" for note in t["notes"])]


def interview_rows(plan: dict) -> list[str]:
    """The plan's table of interviews, in place of the runs: one row each, with the model entry
    of its participant, what each of its two sides may use, the caps of its persona's topics,
    how far it has got of its own cap, and its state. Under it, a line for each interview whose
    turn log is not as a launcher writes one, which no command goes on with."""
    def may(side: dict) -> str:  # one allowance of its limits, and how many it has when --extend gave it more
        return (f"{side['limits']['minutes']:g} min, " + money(side["limits"]["budget_usd"])
                + (" cap" if side["budget_enforced"] else ", not enforced")
                + (f", {1 + side['extended']} allowances" if side["extended"] else ""))

    rows = plan["interview"]["interviews"]
    return ["", f"Interviews ({len(rows)}), each with what its two sides may use over the whole of it:",
            *table([["Interview", "Persona", "Participant", "Participant may use", "Interviewer may use",
                     "Topic caps", "Exchanges", "State"],
                    *([i["run"], f"{i['persona']} {i['name']}".strip(), i["participant"]["entry"],
                       may(i["participant"]), may(i["interviewer"]),
                       ", ".join(f"{x['id']} {x['turns']}" for x in i["topics"]),
                       f"{i['exchanges']} of {i['cap']}", i["state"]] for i in rows)]),
            *(f"  {i['run']}: {i['malformed']}. run and resume leave it alone, and its state and exchanges are "
              f"those of the records that are left: check_runs.py names what to do." for i in rows if i["malformed"])]


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
    A side of a conversation is a row like any other, with "side" ("participant" or
    "interviewer", None on every other row) and "interview", the run id both sides share: the
    usage record names it by those, never by "panellist" or by an interviewer's entry id. The
    interviewer's model entry is a row of "keys" too, so that the rows there add up to the
    panel's and the interviewers' together, and a role whose rows are all one side has "side".
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
               "state": states[e["run"]], "side": side_of(e) if "interview" in e else None,
               "interview": e.get("interview")}
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
    panel = [r for r in rows if r["role"] == "panellist" or r["side"]]  # the runs, and both sides of a conversation
    keys = list(dict.fromkeys((r["key"], r["runner"], r["model"]) for r in panel))
    own = summed(rows)
    roles = [{"role": role, "side": next(iter(sides)) if len(sides) == 1 else None,
              **summed([r for r in rows + asked if r["role"] == role])}
             for role in dict.fromkeys(r["role"] for r in rows + asked)
             for sides in [{r["side"] for r in rows if r["role"] == role}]]
    if shared:  # no process of its own: the runs it concerns, and the figures
        lumps = summed([], shared)
        roles.append({"role": "unallocated", **lumps, "runs": len(shared), "started": len(shared)})
    return {
        "runs": rows, "followups": asked, "unallocated": shared,
        "keys": [{"key": k, "runner": runner, "model": model,
                  **summed([r for r in panel if (r["key"], r["runner"], r["model"]) == (k, runner, model)])}
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
                 [line([r.get("side") or r["role"], r["runs"],
                        "-" if r["role"] in ("follow-up", "unallocated") else r["done"]], r, r["started"])
                  for r in figures["roles"]])
    out += block("By model key", ["Key", "Runner", "Model", "Runs", "Done"],
                 [line([k["key"], k["runner"] or "-", k["model"] or "default", k["runs"], k["done"]], k, k["started"])
                  for k in figures["keys"]])
    out += block("By run", ["Run", "Role", "Key", "State"],  # a side of a conversation: its interview, and the side
                 [line([r.get("interview") or r["run"], r.get("side") or r["role"], r["key"] or "-", r["state"]], r,
                       r["attempts"]) for r in figures["runs"]])
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

def estimate(rows: list[dict], pages: int, text_only: bool, turns: dict | None = None) -> dict:
    """What the runs still to go are likely to use, per model entry and in all. rows are
    usage_figures() rows with "entry" added, the name of each run's model entry, and pages is
    what a run opens (materials(), "opens"), for a model entry with no finished run to measure.
    text_only: the method has no figure for a run of this study, a text-only one or a usability
    one, so a model entry with no finished run gets none.

    turns is given for an interview study, and no model entry of one is ever given the figure
    per page: {(entry, role): the method's tokens for one interview (interview_tokens())}, None
    or no key where it has none. Such an entry's basis is "exchanges". A row of a finished
    interview there has "exchanges", its length, and the entry gets "per_exchange", what its
    finished interviews came to for each (interview.measured())."""
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
        each = rules.measured([
            {"exchanges": r["exchanges"], "seconds": r["seconds"] or 0,
             "tokens": r["input_tokens"] + (r["output_tokens"] or 0)
             if r["input_tokens"] is not None and any(r is w for w in whole) else None}
            for r in done if r.get("exchanges") is not None])
        if done:
            basis = "measured" if tokens else "duration"
            per.update(tokens=round(sum(tokens) / len(tokens)) if tokens else None,
                       cost_usd=sum(costs) / len(costs) if costs else None,
                       seconds=sum(r["seconds"] or 0 for r in done) / len(done))
        elif turns is not None:  # an interview study: the figure for its runner and side, or none
            per["tokens"] = turns.get((name, role))
            basis = "exchanges" if per["tokens"] is not None else "none"
        elif role == "panellist" and not text_only:
            basis, per["tokens"] = "method", TOKENS_PER_CONCEPT_PAGE * pages
        else:
            basis = "none"  # the method has no figure for a text-only or usability run, or for a synthesis job
        entries.append({
            "entry": name, "role": role, "runner": own[0]["runner"], "runs": len(own),
            "done": sum(r["state"] == "done" for r in own), "to_go": to_go, "basis": basis,
            "measured_runs": len(done), "per_run": per, "per_exchange": each,
            "reports_cost": own[0].get("reports_cost", True),
            # finished runs left out of the mean tokens and cost, by why: they still count for the time
            "left_out": {why: len(rows) for why, rows in short.items()},
            "tokens": per["tokens"] * to_go if per["tokens"] is not None else None,
            "cost_usd": per["cost_usd"] * to_go if per["cost_usd"] is not None else None,
            "seconds": per["seconds"] * to_go if per["seconds"] is not None else None,
            "cost": "measured" if per["cost_usd"] is not None else "not reported" if done
                    else "a pilot will provide one" if role in ("panellist", "interviewer")
                    else "a first job will provide one"})
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
    only processes are each runner's check(), shell_check() and model_status(), which make no
    model call. A check or a model status may let a harness refresh its own login.

    runs are the panellist entries (runs.json's, or the ones study.json plans when scaffolded
    is false), jobs the analyst and writer entries study.json plans with anything a launcher
    recorded about them, and states maps each run and job id to its state. In an interview
    study runs holds the interviewers' entries too, each with its state: "interview" is then
    the section on the study (interview()), "runs" stays the participants' rows, one for each
    interview, and the ceiling counts both sides of each.
    """
    sd, native = cfg["_dir"], all(e["runner"] is None for e in runs)
    runs = sorted(runs, key=lambda e: e["role"] == "interviewer")  # the panel first, as it is without interviewers
    mat = materials(cfg)
    talk = interview(cfg, runs, states)
    planned = [] if native else [j for j in jobs if j["runner"]]
    pool, missing, notes, problems = pl.synthesis_pool(cfg), [], [], []

    if not scaffolded:
        missing.append(f"runs.json: run init_study.py {sd} first. The {'interviews' if talk else 'runs'} below are "
                       "the ones it will create.")
    else:
        expected = {e["run"] for e in [*pl.planned_runs(cfg), *pl.planned_interviewers(cfg)]}
        found = {e["run"] for e in runs}
        if expected != found:
            notes.append("study.json no longer plans the runs that runs.json holds (they differ in "
                         + ", ".join(sorted(expected ^ found)[:6]) + (", ..." if len(expected ^ found) > 6 else "")
                         + f"). This plan follows runs.json. init_study.py {sd} --force scaffolds the study again, "
                         "and resets every run.")
    gone = [e["prompt"] for e in runs if not (sd / e["prompt"]).is_file()]
    if scaffolded and gone:
        missing.append(f"{plural(len(gone), 'prompt' if talk else 'run prompt')} ({', '.join(gone[:3])}"
                       f"{', ...' if len(gone) > 3 else ''})")
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
    problems += pl.usability_problems(cfg)  # a command of the study whose file is not there
    problems += [stop(problem) for problem in pl.interview_problems(cfg)]  # what would spoil its interviews
    locked = None if native else unwritable_study(cfg)  # a native study starts nothing through the launcher
    if locked:
        problems.append(locked[0].upper() + locked[1:])
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

    # One row per model entry: a model key of the panel, synthesis.analyst or synthesis.writer, and in an
    # interview study interview.interviewer.
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

    # The interviewers' rows are no run of the plan, and a cap of its ceiling each.
    run_rows = [run_row(e) for e in runs if e["role"] != "interviewer"]
    host_rows, job_rows = [run_row(e) for e in runs if e["role"] == "interviewer"], [run_row(e) for e in planned]

    checked = []
    for name in dict.fromkeys(m["runner"] for m in models if not native):
        caps = runners.get(name).capabilities()
        check = usable(name)  # installed, signed in, and able to do a run from this shell
        checked.append({
            "runner": name, "provider": caps["provider"], "ok": bool(check["ok"]), "message": check["message"],
            "shell": check["shell"],
            "concurrency": pl.runner_concurrency(cfg, name, caps["default_concurrency"]),
            "entries": [m["entry"] for m in models if m["runner"] == name],
            "billing_env_set": [v for v in caps["billing_env"] if os.environ.get(v)],  # names, never values
            "isolation_gaps": list(caps["isolation_gaps"]),
            # The gaps that browsing opens, when a panellist run of this study can browse on this runner.
            "browse_gaps": list(caps["browse_gaps"]) if cfg["browse"] and caps["browser"] and any(
                m["runner"] == name and m["role"] == "panellist" for m in models) else []})
        if not check["ok"]:
            problems.append(f"{name}: cannot be used: {check['message']}")

    # The browser sessions: every run in flight that may browse holds one of its own (browser_session.py).
    at_once = sum(min(r["concurrency"], sum(m["runs"] for m in models if m["runner"] == r["runner"]
                                            and m["role"] == "panellist"))
                  for r in checked if cfg["browse"] and runners.get(r["runner"]).capabilities()["browser"])
    at_once = min(at_once, 1) if cfg.get("sequential") else at_once  # one panellist at a time
    sessions = {"at_once": at_once, "mib_each": browser.MEMORY_MIB, "policy": browser.REFUSES} if at_once else None
    missing_cli = None if native else no_browser(cfg, {m["runner"] for m in models if m["role"] == "panellist"})
    if missing_cli:
        problems.append(missing_cli[0].upper() + missing_cli[1:])

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
    study = usability(cfg)
    if study:
        lent = study["accounts"] and ("identifiers and secrets" if study["accounts"]["signin"] == "panellist"
                                      else "identifiers")
        receives = ("its run prompt, the usability instructions, its persona file with the tasks"
                    + (f", its test account's {lent}" if lent else ""))
    given = {  # an interview study: what each side's provider is sent, and what a job is
        "panellist": "its prompt (the participant brief, the persona and the study's context notes) and every "
                     "question its interviewer puts to it. Nothing of the guide",
        "interviewer": "its prompt (the interviewer brief with its reference notes, the guide, and the "
                       "participant's name, role and segment) and every answer the participant gives. Nothing of "
                       "the persona's bio or personality, and no situation card",
        "job": "the transcripts it is given, analysis/ and whatever else in the study directory it opens, where "
               "it works"}
    opens = []  # what a run that browses can open, besides what it reads
    if study:
        opens.append(f"every page it opens at {study['base_url']}, with what it types there")
    elif not browse or browse["sites"]:
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
                "receives": given.get(m["role"], given["job"]) if talk else
                            (receives + (", and " + " and ".join(opens) if browses else "")
                             if m["role"] == "panellist" else
                             "the persona files it is given, analysis/ and whatever else in the study "
                             "directory it opens, where it works")})
        providers.append({"provider": provider, "entries": entries})

    usage = usage_figures([*runs, *planned], states)
    asked = pl.read_followups(sd)
    followups = {"asked": len(asked), "runs": sum(len(f.get("runs") or []) for f in asked),
                 "limits": None if native or talk else pl.limits_for(cfg, "followup"),  # no interview is asked one
                 "used": summed(usage["followups"]) if usage["followups"] else None,
                 "unallocated": summed([], usage["unallocated"]) if usage["unallocated"] else None}
    names = {e["run"]: label(e) for e in [*runs, *planned]}
    costed = {name: runners.get(name).capabilities()["usage"]["cost"] for name in {e["runner"] for e in runs + planned}
              if name}
    rows = [{**r, "entry": names[r["run"]], "reports_cost": costed.get(r["runner"], False)} for r in usage["runs"]]
    turns = None
    if talk:  # the method's figure for each side, to the interview's cap, and how long each finished one was
        turns = {(label(e), e["role"]): interview_tokens(e["runner"], side_of(e), talk["turns"]) for e in runs}
        ended = {i[side]["run"]: i["exchanges"] for i in talk["interviews"] if i["state"] == "done"
                 for side in pl.SIDES}
        rows = [{**r, "exchanges": ended.get(r["run"])} for r in rows]
    forecast = estimate(rows, mat["opens"], cfg["materials"] == "text" or bool(study), turns)
    if browse and browse["not_browsable"] and any(e["basis"] == "method" for e in forecast["entries"]):
        unread = mat["pdfs"] and mat["pdf_pages"] is None  # its pages are not known until it is captured
        notes.append("the estimate's figure per page was measured on captured web pages. It counts every page of a "
                     "PDF and every supplied image as one such page, which is a guess until a pilot has measured one."
                     + (" A PDF that is not captured yet counts as one page." if unread else ""))
    return {
        "study": cfg.get("study") or sd.name, "dir": str(sd), "native": native, "launcher": launcher,
        "missing": missing, "notes": notes,
        "materials": None if talk else mat, "usability": study, "interview": talk, "browsing": browse,
        "browser_sessions": sessions, "models": models,
        "runs": run_rows,
        "runners": checked,
        "providers": providers,
        "synthesis": None if native else {
            "pool": pool, "share": pl.synthesis_share(cfg), "shares": cfg["synthesis"].get("analysts", 1) + 1,
            "jobs": job_rows,
            "missing": [role for role in pl.JOB_ROLES if not any(j["role"] == role for j in planned)]},
        "estimate": forecast,
        "used": summed(usage["runs"]),  # the runs and jobs: follow-ups are apart, under "followups"
        "ceiling": None if native else ceiling(run_rows + host_rows, job_rows, pool),
        "followups": followups, "earlier_sessions": earlier,
        "problems": problems, "ok": not problems}


def render(plan: dict) -> list[str]:
    """The plan as the lines the plan command prints."""
    sd, native, talk = plan["dir"], plan["native"], plan["interview"]
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

    out += (interview_lines(plan) if talk else usability_lines(plan) if plan["usability"]
            else materials_lines(plan))
    sessions = plan["browser_sessions"]
    if sessions:
        n, each = sessions["at_once"], sessions["mib_each"]
        out += ["", "Browser sessions, for the runs that may browse:",
                "  The launcher starts an agent-browser session for each attempt of such a run before its process, "
                "and stops it after. A run only sends it commands.",
                f"  Each holds about {each} MiB while its run is in flight: about {n * each / 1024:.1f} GiB with "
                f"{plural(n, 'such run')} at once, the most the concurrency in force allows.",
                f"  {sessions['policy']}",
                "  What that leaves open is listed for each runner under Runners, below."]

    # An interview study's interviewer is a model entry of its own, with limits of its own: a row beside the panel's.
    panel = [m for m in plan["models"] if m["role"] == "panellist" or (talk and m["role"] == "interviewer")]
    out += ["", f"Model entries ({len(panel)})"
            + (":" if native else ", each with the limits in force for its side of an interview:" if talk
               else ", with the limits in force for each of their runs:")]
    out += table([["Key", *(["Side"] if talk else []), "Runner", "Model", "Effort", "Interviews" if talk else "Runs",
                   "Time limit", "Budget", "Provider"],
                  *([m["entry"], *([side_of(m)] if talk else []), *entry_cells(m), m["runs"], *limits_of(m),
                     m["provider"] or "-"] for m in panel)])
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

    if talk and any(m["budget_cap_note"] for m in plan["models"]):
        out.append(f"  In the lines above on a budget cap, {HARNESS_WORDS}")
    if talk:
        out += interview_rows(plan)
    else:
        out += ["", f"Runs ({len(plan['runs'])}):"]
        out += table([["Run", "Persona", "Key", "Runner", "Model", "Effort", "Time limit", "Budget", "State", "Prompt"],
                      *([r["run"], f"{r['persona']} {r['name']}".strip(), r["key"], *entry_cells(r), *limits_of(r),
                         r["state"], r["prompt"] + ("" if r["prompt_exists"] else " (missing)")]
                        for r in plan["runs"])])
    if native:
        out += ["", *estimate_lines(plan), *followup_lines(plan["followups"]), ""]
        return out

    bare = {x["runner"] for x in talk["tools"] if x["tools"] == "none"} if talk else set()
    out += ["", "Runners:"]
    for r in plan["runners"]:
        said = f"ready: {r['message']}" if r["ok"] else f"CANNOT BE USED: {r['message']}"
        most = plural(r["concurrency"], "process", "processes") if talk else plural(r["concurrency"], "run")
        out.append(f"  {r['runner']}: {stop(said)} Up to {most} at once.")
        if r["billing_env_set"]:
            out.append("    Set in this environment, and able to change who is billed: "
                       f"{', '.join(r['billing_env_set'])}.")
        if r["isolation_gaps"] or r["browse_gaps"]:
            # A side with no tools has nothing to read a file or run a command with, whatever its sandbox allows.
            out.append("    Not switched off for its processes. A side of an interview has no tool to read a file or "
                       "run a command with (Tools, above), so a line on what a run can read or run is about the jobs "
                       "of the synthesis alone:" if r["runner"] in bare else
                       "    Not switched off for its runs:")
            out += [f"      - {gap}" for gap in [*r["isolation_gaps"], *r["browse_gaps"]]]

    out += ["", "What each provider receives:"]
    for p in plan["providers"]:
        out.append(f"  {p['provider']}")
        for e in p["entries"]:
            unit = "interview" if talk and e["role"] in ("panellist", "interviewer") else (
                "run" if e["role"] == "panellist" else "job")
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

    sides = {i[x]["run"]: f"{i['run']} {x}" for i in talk["interviews"] for x in pl.SIDES} if talk else None
    out += ["", *estimate_lines(plan), "", *ceiling_lines(plan["ceiling"], syn, sides),
            *followup_lines(plan["followups"]), "", LIST_PRICE]
    if plan["problems"]:
        out += ["", 'Problems, which stop "run" as they stop this plan:', *(f"  {stop(p)}" for p in plan["problems"])]
    out.append("")
    return out


def materials_lines(plan: dict) -> list[str]:
    """The plan's section on what each run of a review study can read."""
    mat = plan["materials"]
    out = ["", "Materials, what each run can read under panel/materials:"]
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
    return out + browsing_lines(plan)


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
    est, used, talk = plan["estimate"], plan["used"], plan.get("interview")
    out = [f"Estimate of what the {'interviews' if talk else 'runs'} still to go will use (a forecast, not a limit):"]
    for e in est["entries"]:
        per = e["per_run"]
        unit = "interview" if talk and e["role"] in ("panellist", "interviewer") else (
            "run" if e["role"] == "panellist" else "job")
        a, go = f"{'an' if unit == 'interview' else 'a'} {unit}", plural(e["to_go"], unit) + " to go"
        if e["basis"] in ("measured", "duration"):
            cost = money(per["cost_usd"]) if per["cost_usd"] is not None else "cost not reported"
            tokens = f"{per['tokens']:,} tokens" if per["tokens"] is not None else "tokens not reported"
            line = (f"measured on {plural(e['measured_runs'], 'finished ' + unit)}: {tokens}, {cost} and "
                    f"{span(per['seconds'])} {a}. ")
            each = e.get("per_exchange")
            if each and each["seconds"] is not None:  # an interview: what its side came to for each exchange
                line += ((f"It ran {plural(round(each['exchanges']), 'exchange')}" if each["interviews"] == 1
                          else f"They ran {each['exchanges']:.3g} exchanges on average") + ": about "
                         + (f"{each['tokens']:,.0f} tokens and " if each["tokens"] is not None else "")
                         + f"{each['seconds']:.1f}s an exchange. ")
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
                    f"{span(e['seconds'])} of {'process' if unit == 'interview' else 'run'} time"]
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
        elif e["basis"] == "exchanges":
            line = (f"no finished interview to measure. About {per['tokens']:,} input tokens for an interview that "
                    f"runs to its cap of {plural(talk['turns'], 'exchange')}: {e['tokens']:,} for {go}. No dollar "
                    "figure: "
                    + ("a pilot will provide one." if e["reports_cost"]
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
    if any(e["basis"] == "exchanges" and e["to_go"] for e in est["entries"]):
        out += ["  Where no interview has finished, the figure is the input tokens of an interview that runs to its "
                "cap, by runner and by side and not by model: one process of the side for each exchange, at the size "
                f"measured on {TURN_TOKENS_FROM}.",
                "    It is a forecast and no ceiling. An interview that ends before its cap uses less. The "
                "participant's first reply, a reply that is sent back and a turn that is put again are processes "
                "too, and the figure leaves them out. Nearly all of that input is read from a cache after a side's "
                "first process."]
    if used["started"]:
        tokens = (f"{used['input_tokens'] + (used['output_tokens'] or 0):,} tokens"
                  if used["input_tokens"] is not None else "tokens not reported")
        started = (plural(used["started"], "side or job", "sides and jobs") if talk
                   else plural(used["started"], "run or job", "runs and jobs"))
        out.append(f"  Used so far, by the {started} started: {tokens}, "
                   f"{money(used['cost_usd']) if used['cost_usd'] is not None else 'cost not reported'}.")
    elif talk:
        out.append("  Nothing has run yet: launch.py pilot holds the first persona's interview on each model entry, "
                   "and the next plan estimates from what it measured. Read its transcripts before the rest.")
    elif not plan["native"]:
        out.append("  Nothing has run yet: launch.py pilot runs one persona on each model entry, and the next plan "
                   "estimates from what it measured.")
    return out


def ceiling_lines(c: dict, syn: dict, sides: dict | None = None) -> list[str]:
    """The plan's lines on the ceiling. sides is given for an interview study, whose caps are
    those of each side of each interview: {entry id: what the lines call that side}."""
    def called(run: str) -> str:
        return (sides or {}).get(run, run)

    whole, one, each = (("every side of every interview", "side", "each side of each interview") if sides
                        else ("every run", "run", "each"))
    out = [f"Ceiling: {money(c['usd'])}, " + (
        f"a guaranteed maximum{' apart from the caveats below' if c['caveats'] else ''}: {whole} and job has a "
        "budget cap that its harness enforces." if c["guaranteed"]
        else f"an estimate, not a guaranteed maximum: some {one}s or jobs have no budget cap.")]
    out.append(f"  {money(c['capped_runs_usd'])} for {plural(c['capped_runs'], one)} with an enforced cap, {each} "
               f"counted once, because a cap covers all of a {one}'s {'turns' if sides else 'attempts'}.")
    out.append(f"  {money(c['synthesis_usd'])} for the synthesis pool, counted once, because it is split into the "
               f"jobs' caps. {'No interview spends it' if sides else 'Panellist runs never spend it'}.")
    if c["uncapped"]:
        shown = ", ".join(map(called, c["uncapped"][:8])) + (", ..." if len(c["uncapped"]) > 8 else "")
        n = len(c["uncapped"])
        out.append(f"  {plural(n, one)} on a runner without a budget cap {agree(n, 'is', 'are')} left out of the "
                   f"figure ({shown}). The time limit is what bounds {agree(n, 'it', 'them')}: at most "
                   f"{span(c['uncapped_minutes'] * 60)} of {'process' if sides else 'run'} time"
                   f"{agree(n, '', ' between them')}.")
    if c["uncapped_jobs"]:
        n = len(c["uncapped_jobs"])
        out.append(f"  {plural(n, 'job')} on a runner without a budget cap {agree(n, 'has its', 'have their')} share "
                   f"of the pool counted, but nothing enforces it ({', '.join(c['uncapped_jobs'])}). The time limit "
                   f"is what bounds {agree(n, 'it', 'them')}: at most {span(c['uncapped_job_minutes'] * 60)} of run "
                   f"time{agree(n, '', ' between them')}.")
    # A runner's note on its cap is in its harness's words: in an interview study's plan, what they mean follows it.
    said = f" There {HARNESS_WORDS}" if sides else ""
    out += [f"  Caveat: {stop(caveat)}" + ("" if caveat.startswith(STOPPED) else said) for caveat in c["caveats"]]
    if not c["holds"]:
        out.append(f"  The ceiling no longer holds: resume --extend gave more than one allowance of the limits to "
                   f"{', '.join(map(called, c['extended']))}. With those allowances it comes to "
                   f"{money(c['with_extensions_usd'])}.")
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
