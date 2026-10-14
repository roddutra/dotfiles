#!/usr/bin/env python3
"""Copy a finished study round into a research archive, leaving out regenerable bulk.

Kept: study.json, key.md, runs.json, prompts/, analysis/ (usage.md and runs.csv with it),
panel/_panel-instructions.md, panel/personas/ and, when the study has them, study-brief.md (what
was agreed with the user is part of the record) and followups.json (the questions behind the
"## Follow-up <n>" sections of the persona files, which check_runs.py reads) and interviews/ (the
turn logs and full transcripts of an interview study, below). Dropped: the site
copies, in panel/sites or <study>/sites (the archive keeps the concepts once, separately),
panel/materials (regenerate with capture.py), panel/scratch, logs/ (raw harness output, which
contains everything a panellist read and wrote), .launch.lock, which every study has and which
stays behind, and .capture-*, the scratch of a capture. Only what KEEP names is copied, so
nothing else beside study.json travels.

forms.json is written to the archive too: the form of each "files" concept, from its source files
while they can be read, else from the study's own record (panel_lib.py, "Forms"). An archive
made without --concepts has no source to tell a PDF from an image, and analyze.py needs to.

Every markdown file kept gets the synthetic panel notice (panel_lib.NOTICE) when it lacks it:
under the "# " title the file opens with, or at the very top when it opens with anything else,
a deeper heading among them (panel_lib.with_notice()). A file that has the line anywhere is
left as it is, so archiving twice changes nothing, and the
closing line says the same both times: how many markdown files of the round carry the notice,
not how many were given it. CSV, JSON
and every other kind of file are copied byte for byte, because a line added to one would break
whatever reads it, and so is everything --concepts copies. An archived round still analyses.
Archiving to a place that holds an earlier archive replaces what has the same name. For a concept
file whose content differs, a line says so.

The kept files are found by one walk (kept_files()) and copied one by one, those the walk found
and no others, each opened without following a symbolic link at its name or at a folder above
it (open_kept()), as the walk opens each folder it lists: a panellist can write under panel/,
and nothing there may bring a file from outside the study into the archive, or the names of
one into its plan. A folder is in the archive only as part of the path of a file, so one that
holds nothing kept, or only a __pycache__ or a .DS_Store, is not archived.
The round is built in a scratch folder beside the destination (scratch_beside()), and nothing of
an earlier archive is copied into it. Everything that reads the study happens there, so an
archive that stops at a refusal below, or at a file that changed under the copy, leaves the
destination as it was. Then the round is published (publish()). To a destination that is not
there, in one rename. Into one that holds an earlier archive, file by file, each moved into
place whole: what has the same name is replaced, the rest stays, and a folder left with nothing
in it is removed. One that cannot be removed, or cannot be listed to see what it holds, is
named on stderr with the system's reason and left: the round is archived all the same, and no
mode is changed to get at it. That is not one step: stopped part of the way, it leaves some
files of this round and the others as the earlier archive had them, each of them whole, and
archiving again finishes it.

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

Three refusals for every study, each with nothing archived. A study that a launcher has (launch.py, followup.py or
init_study.py --force) is refused: archive.py takes the launcher's own lock on the study
(launch.Lock) and holds it until the round is copied, so no follow-up can be asked or settled
under the copy. Of a study it cannot write, as in a sandbox that shows it read-only, it keeps a
shared lock on the same file for as long (take_study()), which turns every launcher away. The
file is there in a study at rest: the scaffold makes it and no launcher removes it (launch.Lock).
One case is left with neither lock, a study from before that which has no lock file, read from
a shell that cannot make one: it refuses that one with a run on record as running, and copies
any other with nothing to keep a first launcher from starting under the copy. A study with a
follow-up question that is not settled is refused too, checked
under that lock: a follow-up attempt with no end in runs.json, or a record in followups.json
with no outcome or with a decision still to carry out. Until a launcher has settled it, the
persona file may hold what will be rejected and put back (the snapshot rule in panel_lib.py),
and an archive has no logs/ to put it back from. A study no launcher ever ran (native mode) is
locked for the copy like any other, and an archived round, which has no logs/, has nothing to
settle and is copied as it is. The third is of a study with something at or under a kept name
that cannot be read as the study's own: a symbolic link, which could bring in a file from outside
the study, a FIFO, a socket or a device, which is no file and may never answer, and a file or a
folder that may not be read or listed. Each is named with the reason, and none is followed or
opened. Most are found by the walk, before anything is copied. A file that can no longer be read
when it is copied, or that a review study, which is scanned for nothing, first opens then, ends
the archive in the same words.

An interview study has no concepts, no key.md and no persona files. Its archive holds the other
kept files and its interviews, at the paths the study has them, so that an archived round still
extracts, analyses and has its quotes checked (extract_notes.py, analyze.py, interview.py quotes):
  interviews/<run id>.jsonl   the turn log of each interview, byte for byte: the one record of
                              what was said, and of why an interview stopped
  interviews/<run id>.md      the full transcript, with the situation card, which is meant to be
                              kept: it is what the critique was marked against
  analysis/transcripts/       the analysts' copies, with the rest of analysis/: notes.csv,
                              critique.csv, themes.md, quant.md and quote-check.md among it
Never copied: the rooms (panel/rooms) and the interviewers' folders (interviewer/), which hold
nothing, and logs/, which has every turn's raw output and the turn logs that a fresh start or a
new scaffold set aside. Those are superseded, never evidence.

Two more refusals for an interview study, under the lock (refuse_unsettled()): a turn in flight,
which is an attempt with no end on either side of an interview, and an interview that a launcher
is carrying between two turns. A mark that a killed launcher left on an interview is no reason
to refuse. An interview with no end record is archived as it stands, and a line names each with
what it reads as and how far it got, and each that has turns on record and no transcript
(interview_lines()). Nothing of an interview study is scanned: it has no test account, so no
secret is known, and a "leak_terms" entry in a question, a card or an answer is for
check_runs.py to say before the round is archived. A usability study that keeps a folder
interviews/ has every file of it scanned for its secrets with the other kept files.

A review or usability study that held debriefs (interview.py debrief; panel_lib.py, "Debriefs")
keeps their turn logs and transcripts the same way, in interviews/ and analysis/transcripts/,
and one line says how many and which have no end record (debrief_lines()). A turn of a debrief
in flight is refused like a turn of an interview, on its interviewer's entry or on the finished
run it was put to.

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
passed over and names the first few, each after its run id. An evidence folder is opened and
read without following a symbolic link, at the evidence root, at the run's folder or at a file's
name (panel_lib.evidence_fd): a panellist can write under panel/, and a link there must never
bring a file from outside the study into the archive. Never copied: panel/scratch (a panellist's
account.json), accounts/ (the account records, the fingerprint record and what a command of the
study wrote when it failed), saved browser states and logs/. The archived study.json
has every secret of accounts.map replaced with panel_lib.REDACTED, identifiers kept, and a line
says so: it loads as before, and nothing else in it is changed. A study without a map has its
study.json copied byte for byte.

Two more refusals for a usability study, both before anything is copied and under the lock, and
the third above reaches further:
  - a test account is still in force (its run is not in a final state, or its teardown failed):
    the archive would describe credentials that work
  - a secret value of any run's test account is in a file the archive would hold, or in the name
    of a screenshot, of a kept file or of a folder above one: every kept file is scanned, the
    step logs and the archived study.json among them (panel_lib.py, "Secrets"). Each file is
    named with its lines and whose secret it was, never the value. A folder that holds nothing
    kept is not archived, so its name goes nowhere
  - what cannot be read as the study's own includes a step log or another kept file that could
    not be scanned, and an evidence folder or the evidence root that is a symbolic link or no
    folder: a file that could not be scanned is not known to be clean
A panellist can write under panel/, so the path of a file or a folder there may be its own text,
in the name of a folder as much as of a file, in a study of either type. No message, and no note
kept in place of a screenshot, repeats one unchecked: each path and each screenshot's name stands
as panel_lib.shown_path() shows it, whole when it is clean, and otherwise as far down as it is,
with what is below described: "panel/personas/(a path of 2 names that is not shown, 17
characters)". A path with a secret value in it is said with whose secret it was.

Usage: archive.py <study-dir> --dest <archive>/customer-research/<date-topic>/panel/<round>
                  [--concepts]
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import fcntl
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accounts  # noqa: E402
import launch  # noqa: E402
import panel_lib as pl  # noqa: E402
import run_watchdog as watchdog  # noqa: E402
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
    pl.INTERVIEWS: pl.INTERVIEWS,  # the turn logs and the full transcripts: the same path, so an archived round reads
}
IGNORED = ("__pycache__", ".DS_Store")  # the names left out of a folder, whatever is under them
SCALE = 50     # per cent of its size a step's screenshot is brought down to, as snapshot.py does a concept's page
COLOURS = 256  # and the colours it keeps: a screenshot stays a PNG, under the name its step log gives it
PNG = b"\x89PNG\r\n\x1a\n"  # what every PNG file begins with


def copy(src: Path, dst: Path):
    """Copy a concept's source, which is the lead's own, for --concepts. Nothing of the study is
    copied with this: it follows a link (copy_kept())."""
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
    """Give every markdown file at or under dst the synthetic panel notice. Returns how many carry
    it. Not how many lacked it: the round is built afresh each time, so that would count files
    that are no different from the ones an earlier archive published."""
    carry = 0
    files = sorted(dst.rglob("*.md")) if dst.is_dir() else [dst] if dst.is_file() and dst.suffix == ".md" else []
    for f in files:
        try:
            text = f.read_text()
        except UnicodeDecodeError:  # not text, whatever its name says
            continue
        if pl.NOTICE not in text:
            f.write_text(pl.with_notice(text))
        carry += 1
    return carry


def take_study(sd: Path):
    """Take the launcher's lock on the study, so that no launcher asks or settles a follow-up
    while the round is copied. Exits while a launcher has the study. Returns the lock, to
    release once the round is copied, or None for a study that is archived with no lock at all.

    A study directory that cannot be written gives no such lock: an archived round kept
    read-only, which no launcher of this shell can have either, or a study that a sandbox shows
    read-only, which may be at work outside it. The archive then keeps a shared lock on the
    lock file, which a descriptor that only reads can take (launch.Lock.share()): no launcher
    is given the study from before the looks below until the round is copied, so none can
    start a run in between and die, leaving the copy to be made over a run that is alive. It
    is refused while a launcher has the study, and, under that lock, while a run is alive where
    this shell cannot look, which the lock of its watchdog says (launch.Lock.blind()).

    The lock file is there to share in a study at rest: the scaffold makes it, and a launcher
    that ends leaves it (launch.Lock.make(), release()). No lock can be had where there is
    none all the same, in a study from before that or in a round that was archived, or where
    no flock can tell. The same is then looked for with nothing held, and nothing keeps a
    launcher from starting afterwards. A study with a run on record as running, read last, is
    then refused: a launcher that came and went since the first look left it so, and a study
    that may be at work cannot be protected from one while it is copied. Any other is
    archived as it is, as a round that was archived read-only always was: that one case is
    not protected from a first launcher that starts while it is copied."""
    lock = launch.Lock(sd)
    if lock.acquire("archive", 0, must=False):
        return lock
    if os.access(sd, os.W_OK):
        lock.refuse()
    if lock.share("archive"):
        return lock
    try:
        running = ([launch.named(e) for e in pl.read_runs(sd) if launch.in_flight(e)]
                   if (sd / "runs.json").exists() else [])
    except ValueError:  # not valid JSON: it names no run
        running = []
    if running:
        raise SystemExit(
            f"{pl.plural(len(running), 'run')} of this study {pl.agree(len(running), 'is', 'are')} on record as "
            f"running ({'; '.join(running)}), and this shell can neither write the study nor hold a lock on "
            f"{lock.path}, so the study cannot be protected from a launcher while it is copied. Nothing was "
            f"archived. Archive it from a shell that can write the study. {pl.SANDBOX_HINT}")
    return None


def refuse_unsettled(sd: Path, held: bool = False):
    """Exit when something of the study is not settled. The caller has the study lock, so nothing
    can be asked, answered or settled after this has looked.

    A follow-up question that is not settled (launch.unsettled_followups). A turn of an
    interview in flight: an attempt with no end on an entry of a conversation
    (launch.in_flight()), whose process may still be answering, and whose answer the turn log
    does not have yet. A turn of a debrief in flight is refused the same way, on its
    interviewer's entry or on the finished run it is put to, whose persona file is read from a
    copy until the turn is settled (pl.open_attempt(), pl.TURN_KINDS). And an interview that a
    launcher is carrying between two turns, by the one rule for that (pl.carried()): the entry is
    marked as carried and a launcher has the study, which is what held says. The caller passes
    it false whenever it has the study itself, since no launcher then has: a mark that a killed
    launcher left is no reason to refuse, and such an interview is archived as its log stands
    (interview_lines())."""
    if not (sd / "logs").is_dir():  # an archive archived again: it has nothing to settle with
        return
    runs = pl.read_runs(sd) if (sd / "runs.json").exists() else []
    out = launch.unsettled_followups(sd, runs)
    if out:
        raise SystemExit(f"A follow-up question to {', '.join(out)} is not settled, so "
                         f"{pl.agree(len(out), 'its persona file', 'their persona files')} may hold what a "
                         "launcher will reject and put back. Nothing was archived. Settle it with: "
                         f"followup.py {sd} list, once any process still answering has ended (launch.py {sd} "
                         "status shows them).")
    turns = [launch.named(e) for e in runs if (pl.open_attempt(e) or {}).get("kind") in pl.TURN_KINDS]
    if turns:
        goes_on = (f"interview.py {sd} debrief --runs <ids> goes on with the debrief"
                   if any(e.get("kind") == "debrief" for e in runs) else f"launch.py {sd} resume goes on with the "
                   "interview")
        raise SystemExit(f"{pl.plural(len(turns), 'turn')} of this study {pl.agree(len(turns), 'is', 'are')} not "
                         f"settled ({'; '.join(turns)}): its process may still be answering, and what it answers is "
                         f"not on the turn log yet. Nothing was archived. launch.py {sd} stop settles it and starts "
                         f"nothing, and {goes_on}.")
    carried = list(dict.fromkeys(pl.interview_of(e) for e in runs if "interview" in e and pl.carried(e, held)))
    if carried:
        raise SystemExit(f"A launcher is carrying {pl.listed(carried)} between two turns, so "
                         f"{pl.agree(len(carried), 'its turn log is', 'their turn logs are')} still being written. "
                         f"Nothing was archived. Wait for it to end, or stop it with launch.py {sd} stop.")


def interview_lines(cfg: dict) -> list[str]:
    """What the archive says of the interviews of an interview study: how many turn logs and
    transcripts travel, each interview that has no end record, with what it reads as and how far
    it got, and each that has turns on record and no transcript to show them. An interview that
    did not finish is archived as it stands and refuses nothing: it is said plainly, so that
    nobody takes the round for a finished one. Read under the study lock, where a mark that an
    interview is carried counts for nothing (pl.carried())."""
    sd, records = cfg["_dir"], pl.run_records(cfg["_dir"], cfg)
    logs = [r for r in records if pl.turn_log(sd, r["run"]).is_file()]
    shown = [r["run"] for r in records if (sd / pl.INTERVIEWS / f"{r['run']}.md").is_file()]
    lines = [f"Interviews: {pl.plural(len(logs), 'turn log')} and {pl.plural(len(shown), 'transcript')} in "
             f"{pl.INTERVIEWS}/, with the analysts' copies in {pl.TRANSCRIPTS}/. The rooms, the interviewers' "
             "folders and logs/ stay behind."]
    unended = [r for r in records if not r["progress"]["complete"]]
    if unended:
        each = [f"{r['run']} ({r['state']}, " + (f"{r['progress']['exchanges']} of {r['progress']['cap']} exchanges)"
                                                 if any(t["t"] in pl.SPOKEN for t in r["turns"])
                                                 else "no turn on record)") for r in unended]
        n = len(unended)
        lines.append(f"{n} of the {pl.plural(len(records), 'interview')} {pl.agree(n, 'has', 'have')} no end record "
                     f"and {pl.agree(n, 'is archived as it stands', 'are archived as they stand')}: {'; '.join(each)}. "
                     f"analyze.py lists {pl.agree(n, 'it', 'them')} under \"Incomplete interviews\" and counts "
                     f"{pl.agree(n, 'it', 'them')} in no table.")
    bare = [r["run"] for r in records if r["run"] not in shown and any(t["t"] in pl.SPOKEN for t in r["turns"])]
    if bare:
        lines.append(f"{pl.listed(bare)}: turns on record and no transcript, so the archive has "
                     f"{pl.agree(len(bare), 'its turn log', 'their turn logs')} alone. interview.py {sd} render writes "
                     "the transcripts: archive again after it.")
    return lines


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


def kept_files(sd: Path) -> tuple[list[tuple[Path, Path]], list[tuple[Path, str]]]:
    """Every file the KEEP names bring into an archive, each with the path the archive holds it
    under, and what among them is not read, each with why. One walk says what everything at or
    under a kept name is, without following a link and without opening a file:
      a regular file   is kept
      a folder         is listed, and the walk goes on in it. An archive has a folder only as
                       part of the path of a file, so one that holds nothing kept is not in it
      a symbolic link  is not read: what it points at could be a file from outside the study
      anything else    (a FIFO, a socket, a device) is not read: opening one can wait for ever
    and whatever cannot be told apart, or a folder that cannot be listed, is not read either,
    with the system's reason: nothing says what it is or holds. Nothing is looked for at or
    under a name of IGNORED, and a name of KEEP that the study does not have is passed over.

    A panellist can put a link where a folder was between any two looks at it, so no folder is
    listed by its path. Each is opened from the study directory down, no part of the way through
    a link (panel_lib.folder_fd), what it holds is listed from that descriptor, and each entry
    is told apart by its name in that descriptor: what is listed is the folder that was opened,
    whatever now has its name. One opened this way that is a folder no longer is not read. Two
    descriptors are open at most, however deep the study goes."""
    files, unread = [], []

    def kind(folder: int, name: str) -> str:  # what an entry of an open folder is: "file", "folder" or why not
        mode = os.lstat(name, dir_fd=folder).st_mode
        return ("file" if stat.S_ISREG(mode) else "folder" if stat.S_ISDIR(mode) else
                "it is a symbolic link" if stat.S_ISLNK(mode) else "it is neither a regular file nor a folder")

    def why(err: OSError) -> str:  # folder_fd() names the part that is a link, which is not repeated
        return ("it or a folder above it is a symbolic link, or no folder" if isinstance(err, pl.Unsafe)
                else pl.unread(err))

    def listed(f: Path) -> list[tuple[str, str]]:  # (name, kind) of what a folder holds, in name order
        folder, found = pl.folder_fd(sd, f.relative_to(sd).parts), []
        try:
            for name in sorted(set(os.listdir(folder)) - set(IGNORED)):
                try:
                    found.append((name, kind(folder, name)))
                except OSError as err:
                    found.append((name, pl.unread(err)))
        finally:
            os.close(folder)
        return found

    for kept, held in KEEP.items():
        *above, name = Path(kept).parts
        try:
            folder = pl.folder_fd(sd, above)
            try:
                what = kind(folder, name)
            finally:
                os.close(folder)
        except FileNotFoundError:  # the study has no such name, or no panel/ to hold it
            continue
        except OSError as err:
            what = why(err)
        todo = [(sd / kept, Path(held), what)]
        while todo:
            f, to, what = todo.pop()
            if what == "file":
                files.append((f, to))
            elif what != "folder":
                unread.append((f, what))
            else:
                try:  # the last is taken first
                    todo += [(f / name, to / name, what) for name, what in reversed(listed(f))]
                except OSError as err:
                    unread.append((f, why(err)))
    return files, unread


def refuse_unread(plan: dict, unread: list[tuple[Path, str]]):
    """Exit, with nothing archived, when a file or a folder the archive would hold cannot be read
    as the study's own: unread, each with why. Each path stands as panel_lib.shown_path() shows
    it, because any part of one under panel/ may be a panellist's own text."""
    if not unread:
        return
    sd = plan["sd"]

    def said(f: Path, why: str) -> str:  # a reason of pl.evidence_fd()'s begins with the path itself
        own = str(f.relative_to(sd))
        return f"  {pl.shown_path(plan['known'], own)}{why[len(own):] if why.startswith(own) else ': ' + why}"

    raise SystemExit(
        f"{pl.plural(len(unread), 'file or folder', 'files or folders')} the archive would hold cannot be read "
        "as the study's own, so nothing was archived:\n" + "\n".join(said(f, why) for f, why in unread)
        + "\nNothing was read through a symbolic link"
        + (", and a file that could not be scanned is not known to be clean" if plan["scanned"] else "")
        + ". Put a plain file or folder that can be read at each name, or remove it, then archive again.")


def review_plan(cfg: dict) -> dict:
    """What archiving a review study takes, decided before anything is copied: the files it
    keeps (kept_files()). Exits, with nothing archived, when something among them cannot be read
    as the study's own. It has no test accounts, so no secret is known and no file is scanned."""
    files, unread = kept_files(cfg["_dir"])
    plan = {"sd": cfg["_dir"], "known": pl.known_secrets(cfg), "scanned": False, "files": files, "study": None}
    refuse_unread(plan, unread)
    return plan


def open_kept(sd: Path, f: Path) -> int:
    """Open a file that kept_files() listed, to copy it: a descriptor. Every folder between the
    study directory and the file is opened without following a symbolic link, and so is the
    file (panel_lib.open_below), as a persona file is opened by whatever reads one: a link put
    there since the walk brings in nothing from outside the study. Raises OSError, with the
    reason (panel_lib.unread()), when a folder on the way is a link or no folder, the file is a
    link or no regular file, or either may not be read."""
    return pl.open_below(sd, f, most=sys.maxsize)  # copied, not read whole: its size is no matter


def debrief_lines(cfg: dict) -> list[str]:
    """What the archive says of the debriefs of a review or usability study (panel_lib.py,
    "Debriefs"): how many turn logs and transcripts travel, in interviews/ and
    analysis/transcripts/ as an interview study's do, and each debrief that has no end record,
    which is archived as it stands. Nothing for a study that held none. In a usability study
    they are scanned for its secrets with every other file that is kept."""
    sd = cfg["_dir"]
    runs = pl.read_runs(sd) if (sd / "runs.json").exists() else []
    held = [e["interview"] for e in runs if e.get("kind") == "debrief" and pl.turn_log(sd, e["interview"]).is_file()]
    if not held:
        return []
    shown = [run for run in held if (sd / pl.INTERVIEWS / f"{run}.md").is_file()]
    turns = {run: pl.read_turns(sd, run) for run in held}
    lines = [f"Debriefs: {pl.plural(len(held), 'turn log')} and {pl.plural(len(shown), 'transcript')} in "
             f"{pl.INTERVIEWS}/, with the analysts' copies in {pl.TRANSCRIPTS}/. The interviewers' folders and logs/ "
             "stay behind."]
    unended = [run for run in held if not any(r["t"] == "end" for r in turns[run])]
    if unended:
        each = [f"{run} ({pl.plural(sum(r['t'] == 'answer' for r in turns[run]), 'exchange')})" for run in unended]
        lines.append(f"{len(unended)} of the {pl.plural(len(held), 'debrief')} "
                     f"{pl.agree(len(unended), 'has', 'have')} no end record and "
                     f"{pl.agree(len(unended), 'is archived as it stands', 'are archived as they stand')}: "
                     f"{'; '.join(each)}.")
    return lines


def copy_kept(plan: dict, work: Path):
    """Copy the kept files into work: the files the plan lists (kept_files()), each to the path
    the archive holds it under, and nothing else. No folder is walked again, and none is made
    but to hold a file. Each file is opened without following a link (open_kept()) and written
    to a file made anew (run_watchdog.fresh()), with its modification time. study.json is
    written from the plan's text when the plan has one. Exits as refuse_unread() does, once
    every file has been tried, when one cannot be read after all: one that has changed since
    the plan was made, or one of a review study, which is scanned for nothing and so is first
    opened here."""
    unread = []
    for f, to in plan["files"]:
        target = work / to
        target.parent.mkdir(parents=True, exist_ok=True)
        if plan["study"] and to == Path("study.json"):
            with os.fdopen(watchdog.fresh(target), "w") as out:
                out.write(plan["study"][0])
            continue
        try:
            source = os.fdopen(open_kept(plan["sd"], f), "rb")
        except OSError as err:
            unread.append((f, pl.unread(err)))
            continue
        with source:
            st = os.fstat(source.fileno())
            with os.fdopen(watchdog.fresh(target), "wb") as out:
                shutil.copyfileobj(source, out)
        os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns))
    refuse_unread(plan, unread)


def claim(scratch: Path) -> int | None:
    """Take the lock that says a scratch folder is in use: flock on the folder itself, which the
    system lets go when the process that has it ends, however it ends. A descriptor that holds
    the lock, or None when another process has it, or the folder has gone. No name and no file
    says whose a scratch folder is, so none can be taken for another's. Raises OSError for a
    folder that cannot be opened or, where flock does not work, locked."""
    try:
        fd = os.open(scratch, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return None
    ours = False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ours = os.path.samestat(os.fstat(fd), os.lstat(scratch))  # not one removed since it was opened
    except (BlockingIOError, FileNotFoundError):
        pass
    finally:
        if not ours:
            os.close(fd)
    return fd if ours else None


def clear_scratch(dest: Path):
    """Remove the scratch folders that archives to dest left beside it when they were killed:
    those whose lock no process has (claim()). One that is locked is another archive at work,
    and one that cannot be opened or locked is not known to be left behind: both stay."""
    for left in sorted(f for f in dest.parent.iterdir() if f.name.startswith(f".{dest.name}.archive-")):
        with contextlib.suppress(OSError):
            lock = claim(left)
            if lock is not None:
                shutil.rmtree(left, True)
                os.close(lock)


@contextlib.contextmanager
def scratch_beside(dest: Path):
    """The folder a round is built in, before any of it is at dest: <dest's name> in a scratch
    folder of its own, <dest's folder>/.<dest's name>.archive-<random>, beside dest and so on
    its filesystem, where a move is a rename. Everything that reads the study happens while the
    round is built, so whatever stops that leaves dest untouched (publish() is what changes it).
    The scratch folder holds only this round: nothing of an earlier archive is copied into it.

    Two archives can run to one destination at once (the study lock is the study's, and a study
    kept read-only is archived under a lock that is shared, or under none), so each has a scratch
    folder of its own name, locked while its archive lives (claim()). Whatever ends the caller,
    an interruption too, the scratch folder is removed, with the folders that were made above
    dest to hold it when nothing was put in them. Only a kill leaves one behind, unlocked, and
    the next archive to that destination removes it (clear_scratch())."""
    made = [folder for folder in (dest.parent, *dest.parent.parents) if not folder.exists()]  # the deepest first
    scratch = lock = None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        clear_scratch(dest)
        while lock is None:  # None: another archive took it for one left behind, before it was locked
            scratch = Path(tempfile.mkdtemp(prefix=f".{dest.name}.archive-", dir=dest.parent))
            try:
                lock = claim(scratch)
            except OSError:  # no flock here: no archive can take it for one left behind, and one left behind stays
                break
        work = scratch / dest.name  # made with the modes of any folder, where the scratch folder is this user's alone
        work.mkdir()
        yield work
    finally:
        if scratch:
            shutil.rmtree(scratch, True)
        if lock is not None:
            os.close(lock)
        for folder in made:
            try:
                folder.rmdir()
            except OSError:  # it holds the archive, or something that is not this archive's
                break


def other_kind(plan: dict) -> list[Path]:
    """The archive paths that the evidence of this round takes the place of: for each screenshot
    the name of the other kind, the screenshot itself where a note now stands for it, and its
    note where the screenshot now travels. An earlier archive may hold one, of a screenshot
    since marked or a note since lifted, and publish() removes it."""
    return [Path("evidence", x["run"], name if name in x["notes"] else name + pl.LEFT_OUT)
            for x in plan["runs"] for name in x["evidence"]["screenshots"]]


def publish(work: Path, dest: Path, other: list[Path]) -> list[str]:
    """Put the round built in work at dest. Where nothing is at dest, in one step: work is
    renamed to it, and dest is the whole round or is not there. Where an earlier archive is, a
    folder cannot take its place in one step, and no state is made in which it has been moved
    away: each file of the round is moved into dest under its own name (os.replace), so every
    file in dest is whole at every moment, a file of the same name is replaced and every other
    file there stays. First what the round holds under the other kind of name is removed
    (other), and last every folder under dest that holds nothing, which an archive never has,
    the ones an older archive.py left there too.

    A folder that holds nothing and cannot be removed (its parent may not be written), or one
    that cannot be listed, so that nothing says whether it holds anything, is left as it is.
    The round is all there by then, so that fails nothing: returns a line for each, with the
    system's reason, for the caller to say. No mode is changed to get at one. A folder that
    holds something is never tried, because the system may refuse that with the same reason
    as one it may not remove.

    So publishing over an earlier archive is not one step. Stopped part of the way, by an error,
    an interruption or a kill, it leaves a dest in which some files are this round's and the
    others the earlier archive's, each of them whole, and a screenshot or its note may be
    missing. Archiving again finishes it. Raises OSError when the one step fails, with dest as
    it was, and exits saying the above when a later one does."""
    if not os.path.lexists(dest):
        os.rename(work, dest)
        return []
    gone, left = set(), []  # the folders removed, and a line for each that was left

    def unlisted(err: OSError):  # os.walk() passes over a folder it cannot list, and says so only here
        if err.errno == errno.ENOENT:
            gone.add(err.filename)
        else:
            left.append(f"A folder in the archive could not be listed ({pl.unread(err)}), so it was left as it is, "
                        f"empty or not: {err.filename}")

    try:
        for name in other:
            (dest / name).unlink(missing_ok=True)
        for folder, _, names in os.walk(work):
            to = dest / Path(folder).relative_to(work)
            to.mkdir(exist_ok=True)
            for name in names:
                os.replace(Path(folder, name), to / name)
        for folder, folders, names in os.walk(dest, topdown=False, onerror=unlisted):
            if Path(folder) == dest or names or any(os.path.join(folder, name) not in gone for name in folders):
                continue  # it holds something
            try:
                os.rmdir(folder)
            except OSError as err:
                if err.errno in (errno.ENOTEMPTY, errno.EEXIST):  # something was put in it since it was listed
                    continue
                if err.errno != errno.ENOENT:  # ENOENT: it has gone already
                    left.append("An empty folder was left in the archive, because it could not be removed "
                                f"({pl.unread(err)}): {folder}")
                    continue
            gone.add(folder)
        return left
    except OSError as err:
        raise SystemExit(
            f"The archive could not be finished ({err.strerror or 'a file could not be moved into place'}). "
            f"{dest} holds an earlier archive, and the files of this round were being moved into it one by one: "
            "some are there now and the others are as the earlier archive had them, each of them whole. Archive "
            "again to finish it.") from None


def usability_plan(cfg: dict) -> dict:
    """What archiving a usability study takes, decided before anything is copied: the files it
    keeps (kept_files()), the text of its study.json when that is not copied as it is, what is
    kept and left out of each run's evidence folder, and the lines to print. Exits, with nothing
    archived, while a test account is in force, when a file the archive would hold has a secret
    value, and when one cannot be read as the study's own (module docstring)."""
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
    files, unread = kept_files(sd)
    plan = {"study": study, "runs": [], "lines": lines, "sd": sd, "known": known, "scanned": True, "files": files}

    def at(f: Path) -> str:  # a path in a message: any part of one under panel/ may be a panellist's own text
        return pl.shown_path(known, f.relative_to(sd))

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
        # The run id is the study's own word, and stands: only the name, a panellist's text, may be described.
        strays += [pl.shown_path(known, f"{e['run']}/{name.rstrip('/')}") + "/" * name.endswith("/")
                   for name in evidence["other"]]
    plan["strays"] = strays + [pl.shown(known, name, "a name that is not shown") for name in loose]

    for f, to in files:
        text = study[0] if study and to == Path("study.json") else None  # as the archive will hold it
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
    refuse_unread(plan, unread)
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
    following a link (panel_lib.open_evidence), and one that cannot be read as it was then ends
    the archive as refuse_unread() does. What an earlier archive holds under a name that is now
    the other kind is not here to remove: publish() does that (other_kind()). Returns the lines
    to print."""
    convert = next(([tool] for tool in ("magick", "convert") if shutil.which(tool)), None)
    sd, jobs, logs, withheld = plan["sd"], [], 0, []

    def shot(run: str, name: str) -> str:  # a screenshot in a line: its name is the panellist's own text
        return pl.shown_path(plan["known"], f"{run}/{name}")

    def bring(run: str, name: str, target: Path):
        try:
            source = os.fdopen(pl.open_evidence(sd, run, name), "rb")
        except OSError as err:  # it has changed since the plan read it
            refuse_unread(plan, [(pl.evidence_dir(sd, run) / name, pl.unread(err))])
        with source, open(target, "wb") as copy:
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
    usability, said, left = cfg["type"] == "usability", [], []
    lock = take_study(sd)
    try:
        # With the study in hand no launcher has it. Only a study that gave no lock at all is asked.
        refuse_unsettled(sd, held=lock is None and bool(launch.Lock.holder(sd)))
        plan = usability_plan(cfg) if usability else review_plan(cfg)
        forms = pl.file_forms(cfg)
        try:
            with scratch_beside(dest) as work:
                copy_kept(plan, work)
                noticed = sum(add_notice(work / held) for held in KEEP.values())
                if usability:
                    said = plan["lines"] + copy_evidence(plan, work)
                if cfg["type"] == "interview":
                    said = interview_lines(cfg)
                else:
                    said = said + debrief_lines(cfg)
                if forms:  # with none known, a record an earlier archive left there stays
                    pl.write_forms(work, forms)
                left = publish(work, dest, other_kind(plan) if usability else [])
        except OSError as err:  # in building the archive: what could not be read of the study has its own message
            raise SystemExit(f"The archive could not be written ({err.strerror or 'a file could not be copied'}), so "
                             f"nothing was archived: {dest} is as it was.") from None
    finally:  # the round is copied: what follows reads the concepts, which no launcher writes
        if lock:
            lock.release()
    if left:  # the round is archived whole: what could not be tidied away is said, and fails nothing
        print(*left, sep="\n", file=sys.stderr, flush=True)
    print(*said, sep="\n", end="\n" if said else "")
    if args.concepts and usability:
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
    print(f"Archived {sd.name} to {dest} ({size / 1e6:.1f} MB). {pl.plural(noticed, 'markdown file')} of this round "
          f"{pl.agree(noticed, 'carries', 'carry')} the synthetic panel notice.")


if __name__ == "__main__":
    main()
