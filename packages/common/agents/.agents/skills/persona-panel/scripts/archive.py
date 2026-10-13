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

A usability study has no concepts and no key.md. Its archive holds the other kept files and its
evidence, panel/evidence/<run id>/ as evidence/<run id>/ (panel_lib.run_evidence):
  steps.jsonl   the step log, byte for byte
  screenshots   every PNG file whose name says which step it shows, or that a result entry of
                the step log names, under its own name, so that a citation of a run, task, step
                and file is found as it was written. With ImageMagick each is brought down to
                SCALE per cent of its size and COLOURS colours, still a PNG. Without it, or when
                it cannot read one, the file is copied as it is, and a line says so
  <screenshot name>.left-out.txt   one line in place of a screenshot that was left out, saying
                why. A screenshot cannot be scanned for text, so three kinds never travel:
                every screenshot of a run whose panellist was given a secret to type (the run's
                "account" in runs.json or its account record says "secrets_given"), the
                screenshot of a step with an entry marked "sensitive", and a file that is not a
                PNG image. The step log entry stays, so the finding can still be cited. A run
                that was given no secret loses only what is marked
Nothing else in an evidence folder is copied, a link least of all, and a line counts what was
passed over. An evidence folder is opened and read without following a symbolic link, at the
evidence root, at the run's folder or at a file's name (panel_lib.evidence_fd): a panellist can
write under panel/, and a link there must never bring a file from outside the study into the
archive. Never copied: panel/scratch (a panellist's account.json), accounts/ (the account
records, the fingerprint record and what a command of the study wrote when it failed), saved
browser states and logs/. The archived study.json
has every secret of accounts.map replaced with panel_lib.REDACTED, identifiers kept, and a line
says so: it loads as before, and nothing else in it is changed. A study without a map has its
study.json copied byte for byte.

Three more refusals for a usability study, all before anything is copied and under the lock:
  - a test account is still in force (its run is not in a final state, or its teardown failed):
    the archive would describe credentials that work
  - a secret value of any run's test account is in a file the archive would hold, or in the name
    of a screenshot, of a kept file or of a kept folder, one with nothing in it included: every
    kept file is scanned, the step logs and the archived study.json among them (panel_lib.py,
    "Secrets"). Each file is named with its lines and whose secret it was, never the value
  - a file or a folder the archive would hold cannot be read as the study's own: a step log or
    another kept file that may not be read, a kept folder that may not be listed, a symbolic
    link among the kept files, or an evidence folder or the evidence root that is one. Each is
    named with the reason, and none is followed: a file that could not be scanned and a folder
    that could not be listed are not known to be clean, and a link could bring in a file from
    outside the study
A panellist can write under panel/, so the path of a file or a folder there may be its own text,
in the name of a folder as much as of a file. No message, and no note kept in place of a
screenshot, repeats one unchecked: each path and each screenshot's name stands as
panel_lib.shown_path() shows it, whole when it is clean, and otherwise as far down as it is,
with what is below described: "panel/personas/(a path of 2 names that is not shown, 17
characters)". A path with a secret value in it is said with whose secret it was.

Usage: archive.py <study-dir> --dest <archive>/customer-research/<date-topic>/panel/<round>
                  [--concepts]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accounts  # noqa: E402
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
IGNORED = ("__pycache__", ".DS_Store")  # the names copy() leaves out of a folder, whatever is under them
SCALE = 50     # per cent of its size a step's screenshot is brought down to, as snapshot.py does a concept's page
COLOURS = 256  # and the colours it keeps: a screenshot stays a PNG, under the name its step log gives it
PNG = b"\x89PNG\r\n\x1a\n"  # what every PNG file begins with


def copy(src: Path, dst: Path):
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*IGNORED))
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


def redacted(sd: Path) -> tuple[str, int] | None:
    """study.json as the archive holds it when accounts.map has secrets: its text with each one
    replaced with panel_lib.REDACTED, and how many there were. None when there is none to
    replace: the file is then copied byte for byte."""
    study = json.loads((sd / "study.json").read_text())
    held = (study.get("accounts") or {}).get("map") or {}
    n = 0
    for account in held.values():
        for name, value in (account.get("secrets") or {}).items():
            if value != pl.REDACTED:
                account["secrets"][name] = pl.REDACTED
                n += 1
    return (json.dumps(study, indent=2) + "\n", n) if n else None


def left_out(sd: Path, known: dict, run: str, name: str, evidence: dict, given: bool) -> str | None:
    """Why a screenshot does not travel, as the one line kept in its place, None when it does."""
    if given:
        why = (f"the panellist of {run} was given a secret to type, so any screenshot of its tasks could show one. "
               "Its step log entries are kept in steps.jsonl")
    elif name in evidence["sensitive"]:
        task, attempt, step = evidence["sensitive"][name]
        why = (f"task {pl.shown(known, task, 'a value that is not a task id')}, step {step}"
               f"{f' of attempt {attempt}' if attempt > 1 else ''}, is marked sensitive in "
               "steps.jsonl, so its screenshot could show a secret. The step log entry is kept")
    else:
        with os.fdopen(pl.open_evidence(sd, run, name), "rb") as f:
            if f.read(len(PNG)) == PNG:
                return None
        why = "it is not a PNG image, so it is no screenshot"
    return f"{pl.shown_path(known, name)} was left out of this archive: {why}.\n"


def kept_files(sd: Path) -> tuple[list[Path], list[Path], list[tuple[Path, str]]]:
    """Every file the KEEP names would bring into an archive, study.json aside, every folder they
    would bring with nothing in it, and what among and above them is not read, each with why: a
    symbolic link, because copying follows a link, so one could bring in a file from outside the
    study, and a folder that cannot be listed, because nothing says what it holds and copying
    would stop at it. A folder that holds a file or a folder is in the path of each, so between
    them the files and the empty folders have the path of every folder an archive would hold.
    Nothing is looked for at or under a name of IGNORED: copy() brings none of it."""
    files, empty, unread = [], [], []

    def unlisted(err: OSError):  # what os.walk() would pass over without a word
        unread.append((Path(err.filename), pl.unread(err)))

    for kept in (k for k in KEEP if k != "study.json"):
        top = sd / kept
        if top.is_symlink() or not top.is_dir():
            files += [top] if top.is_symlink() or top.is_file() else []  # a link is refused when it is read
            continue
        for folder, folders, names in os.walk(top, onerror=unlisted):
            folders[:] = [name for name in folders if name not in IGNORED]  # so none of these is walked
            own = 0  # what the folder holds that is no link: a link is refused, so it keeps no folder from being empty
            for name in sorted([*folders, *(name for name in names if name not in IGNORED)]):
                f = Path(folder) / name
                if f.is_symlink():
                    unread.append((f, "it is a symbolic link"))
                    continue
                own += 1
                if name in names:
                    files.append(f)
            if not own:
                empty.append(Path(folder))
    return files, empty, unread


def usability_plan(cfg: dict) -> dict:
    """What archiving a usability study takes, decided before anything is copied: the text of
    its study.json when that is not copied as it is, what is kept and left out of each run's
    evidence folder, and the lines to print. Exits, with nothing archived, while a test account
    is in force, when a file the archive would hold has a secret value, and when one cannot be
    read as the study's own (module docstring)."""
    sd = cfg["_dir"]
    records = accounts.records(sd)
    known = pl.known_secrets(cfg, [r for r in records if accounts.in_force(r)])
    live = [r["run"] for r in records if accounts.in_force(r)]
    if live:
        raise SystemExit(
            f"The test {pl.agree(len(live), 'account')} of {', '.join(live)} {pl.agree(len(live), 'is', 'are')} still "
            "in force, so an archive made now would describe credentials that work. Nothing was archived. An "
            "account is torn down when its run is done, limited or failed, and a teardown that failed is tried "
            f"again by the next launcher command: launch.py {sd} stop does that and starts nothing, and launch.py "
            f"{sd} status shows each account. A run in any other state keeps its account until it has finished.")
    study, lines = redacted(sd), []
    runs = [e for e in pl.read_runs(sd) if e["role"] == "panellist"] if (sd / "runs.json").exists() else []
    given = {r["run"] for r in records if r.get("secrets_given")}
    given |= {e["run"] for e in runs if (e.get("account") or {}).get("secrets_given")}
    plan = {"study": study, "runs": [], "lines": lines, "sd": sd, "known": known}
    texts, empty, unread = kept_files(sd)

    def at(f: Path) -> str:  # a path in a message: any part of one under panel/ may be a panellist's own text
        return pl.shown_path(known, f.relative_to(sd))

    def unreadable(f: Path, why: str) -> str:  # a reason of pl.evidence_fd()'s begins with the path itself
        own = str(f.relative_to(sd))
        return f"  {at(f)}{why[len(own):] if why.startswith(own) else ': ' + why}"

    found, strays = [], []  # the files with a secret value, each with where; what an evidence folder holds besides
    try:
        loose = [name + ("/" if kind == "folder" else "") for name, kind in pl.evidence_names(sd, None)
                 if name not in {e["run"] for e in runs}]
    except OSError as err:  # the evidence root itself: no run's folder is read through it
        unread.append((pl.evidence_dir(sd, "x").parent, pl.unread(err)))
        loose, runs = [], []
    for e in runs:
        evidence, where = pl.run_evidence(cfg, sd, e["run"]), pl.evidence_dir(sd, e["run"])
        if evidence["refused"] or evidence["log_problem"]:
            unread.append((where, evidence["refused"]) if evidence["refused"] else
                          (where / pl.STEP_LOG, evidence["log_problem"]))
            continue
        try:
            notes = {name: left_out(sd, known, e["run"], name, evidence, e["run"] in given)
                     for name in evidence["screenshots"]}
            log = pl.step_log(sd, e["run"]) if evidence["log"] else None
        except OSError as err:
            unread.append((where, pl.unread(err)))
            continue
        hits = pl.scan_text(known, log, "jsonl") if log is not None else []
        if hits:
            found.append(f"  {at(where / pl.STEP_LOG)}: {pl.secret_places(hits)}")
        named = sum(bool(pl.secrets_in(known, name)) for name in evidence["screenshots"])
        if named:
            found.append(f"  {at(where)}: the name of {pl.plural(named, 'screenshot')}")
        plan["runs"].append({"run": e["run"], "evidence": evidence, "given": e["run"] in given,
                             "notes": {name: note for name, note in notes.items() if note}})
        strays += [f"{e['run']}/{name}" for name in evidence["other"]]
    plan["strays"] = [pl.shown(known, name, "a name that is not shown") for name in strays + loose]

    for f, text in [*((f, None) for f in texts), (sd / "study.json", study[0] if study else None)]:
        owners = pl.secrets_in(known, f.relative_to(sd).as_posix())  # a file is archived under its own name
        if owners:
            found.append(f"  {at(f)}: the name of the file or of a folder above it ({pl.secret_owners(owners)})")
            continue
        try:
            hits = pl.scan_file(known, f) if text is None else pl.scan_text(known, text, "json")
        except OSError as err:
            unread.append((f, pl.unread(err)))
            continue
        if hits:
            found.append(f"  {at(f)}: {pl.secret_places(hits)}")
    for f in empty:  # copied too, under its own name, and in the path of no file
        owners = pl.secrets_in(known, f.relative_to(sd).as_posix())
        if owners:
            found.append(f"  {at(f)}: the name of the folder or of a folder above it ({pl.secret_owners(owners)})")
    if unread:
        raise SystemExit(
            f"{pl.plural(len(unread), 'file or folder', 'files or folders')} the archive would hold cannot be read "
            "as the study's own, so nothing was archived:\n"
            + "\n".join(unreadable(f, why) for f, why in unread)
            + "\nNothing was read through a symbolic link, and a file that could not be scanned is not known to be "
            "clean. Put a plain file or folder that can be read at each name, or remove it, then archive again.")
    if found:
        raise SystemExit(
            f"A secret value of a test account is in {pl.plural(len(found), 'file or folder', 'files or folders')} "
            "the archive would hold, so nothing was archived:\n" + "\n".join(found)
            + "\nTake each value out of its file, or out of the name, then archive again. "
            f"check_runs.py {sd} names the same lines for the persona files, the step logs and the analysis.")
    lines += pl.secret_gaps(known, records)
    if study:
        lines.append(f"study.json: the {pl.plural(study[1], 'secret')} of accounts.map "
                     f"{pl.agree(study[1], 'was', 'were')} replaced with {json.dumps(pl.REDACTED)} in the archived "
                     "copy. The identifiers are kept.")
    return plan


def shrink(target: Path, convert: list[str]) -> bool:
    """Bring a PNG screenshot, in place, down to SCALE per cent of its size and COLOURS colours.
    Returns whether ImageMagick could: when it cannot, the file is left as it is."""
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        done = subprocess.run([*convert, f"png:{target}", "-resize", f"{SCALE}%", "-strip", "-colors", str(COLOURS),
                               f"png:{tmp}"], capture_output=True).returncode == 0 and tmp.is_file()
        if done:
            os.replace(tmp, target)
        return done
    finally:
        tmp.unlink(missing_ok=True)


def copy_evidence(plan: dict, dest: Path) -> list[str]:
    """Copy each run's step log and screenshots to dest/evidence/<run id>/, with a note in place
    of each screenshot the plan leaves out. Each file is read as the plan read it, without
    following a link (panel_lib.open_evidence). What an earlier archive left under a name that
    is now the other kind, a screenshot since marked or a note since lifted, is removed.
    Returns the lines to print."""
    convert = next(([tool] for tool in ("magick", "convert") if shutil.which(tool)), None)
    sd, jobs, logs, withheld = plan["sd"], [], 0, []

    def shot(run: str, name: str) -> str:  # a screenshot in a line: its name is the panellist's own text
        return pl.shown_path(plan["known"], f"{run}/{name}")

    def bring(run: str, name: str, target: Path):
        with os.fdopen(pl.open_evidence(sd, run, name), "rb") as source, open(target, "wb") as copy:
            shutil.copyfileobj(source, copy)

    for x in plan["runs"]:
        evidence, target = x["evidence"], dest / "evidence" / x["run"]
        if not (evidence["log"] or evidence["screenshots"]):
            continue
        target.mkdir(parents=True, exist_ok=True)
        if evidence["log"]:
            bring(x["run"], pl.STEP_LOG, target / pl.STEP_LOG)
            logs += 1
        for name in evidence["screenshots"]:
            note = x["notes"].get(name)
            (target / (name if note else name + pl.LEFT_OUT)).unlink(missing_ok=True)
            if note:
                (target / (name + pl.LEFT_OUT)).write_text(note)
                withheld.append((x, name))
            else:
                bring(x["run"], name, target / name)
                jobs.append(target / name)
    with ThreadPoolExecutor(4) as pool:
        shrunk = list(pool.map(lambda job: bool(convert) and shrink(job, convert), jobs))
    whole = [job for job, done in zip(jobs, shrunk) if not done]

    def some(names: list[str]) -> str:
        return ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")

    lines = [f"Evidence: {pl.plural(logs, 'step log')} and {pl.plural(len(jobs), 'screenshot')} in evidence/<run id>/, "
             "each screenshot under the name its step log gives it."]
    if jobs and not convert:
        lines.append("ImageMagick is not installed (magick or convert on PATH), so the "
                     f"{pl.plural(len(jobs), 'screenshot')} {pl.agree(len(jobs), 'was', 'were')} copied at full size.")
    elif jobs:
        lines.append(f"{pl.plural(len(jobs) - len(whole), 'screenshot')} brought down to {SCALE}% of "
                     f"{pl.agree(len(jobs) - len(whole), 'its', 'their')} size and {COLOURS} colours."
                     + (f" ImageMagick could not read {len(whole)}, copied as "
                        f"{pl.agree(len(whole), 'it is', 'they are')}: "
                        f"{some([shot(t.parent.name, t.name) for t in whole])}." if whole else ""))
    if withheld:
        given = sorted({x["run"] for x, _ in withheld if x["given"]})
        marked = [shot(x["run"], name) for x, name in withheld if not x["given"] and name in x["evidence"]["sensitive"]]
        other = [shot(x["run"], name) for x, name in withheld
                 if not x["given"] and name not in x["evidence"]["sensitive"]]
        why = ([f"{sum(x['given'] for x, _ in withheld)} of {', '.join(given)}, whose "
                f"{pl.agree(len(given), 'panellist was', 'panellists were')} given a secret to type"] if given else [])
        why += [f"{len(marked)} of a step marked sensitive ({some(marked)})"] if marked else []
        why += [f"{len(other)} that {pl.agree(len(other), 'is', 'are')} no PNG image ({some(other)})"] if other else []
        lines.append(f"Left out, each with a one-line note in its place (<name>{pl.LEFT_OUT}): "
                     f"{pl.plural(len(withheld), 'screenshot')}: {'; '.join(why)}. The step log entries are kept.")
    missing = sum(len(x["evidence"]["missing"]) for x in plan["runs"])
    if missing:
        lines.append(f"{pl.plural(missing, 'step log entry', 'step log entries')} "
                     f"{pl.agree(missing, 'names', 'name')} a screenshot that was not there to archive: check_runs.py "
                     f"lists {pl.agree(missing, 'it', 'them')}.")
    if plan["strays"]:
        n = len(plan["strays"])
        lines.append(f"Not archived: {pl.plural(n, 'thing')} under {pl.EVIDENCE} that {pl.agree(n, 'is', 'are')} "
                     f"neither a step log nor a screenshot of a step ({some(plan['strays'])}).")
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_dir", type=Path)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--concepts", action="store_true", help="also archive concept sources and page screenshots")
    args = ap.parse_args()
    cfg = pl.load_study(args.study_dir)
    sd = cfg["_dir"]
    dest = args.dest.resolve()
    noticed, said = 0, []
    lock = take_study(sd)
    try:
        refuse_unsettled(sd)
        plan = usability_plan(cfg) if cfg["type"] == "usability" else None
        for src, dst in KEEP.items():
            if plan and plan["study"] and src == "study.json":
                dest.mkdir(parents=True, exist_ok=True)
                (dest / dst).write_text(plan["study"][0])
                continue
            copy(sd / src, dest / dst)
            noticed += add_notice(dest / dst)
        if plan:
            said = plan["lines"] + copy_evidence(plan, dest)
        forms = pl.file_forms(cfg)
        if forms:  # with none known, a record an earlier archive left there stays
            pl.write_forms(dest, forms)
    finally:  # the round is copied: what follows reads the concepts, which no launcher writes
        if lock:
            lock.release()
    print(*said, sep="\n", end="\n" if said else "")
    if args.concepts and plan:
        print("A usability study has no concepts, so --concepts copied nothing.")
    elif args.concepts:
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
