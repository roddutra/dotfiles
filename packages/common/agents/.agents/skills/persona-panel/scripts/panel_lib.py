"""Shared helpers for the persona-panel scripts: study config, runs.json, and persona-file parsing.

Standard library only. Every script takes a study directory laid out as:

    <study>/study.json        lead config (never shown to panellists)
    <study>/key.md            neutral label -> concept key (lead only)
    <study>/forms.json        {concept id: form} for each "files" concept, the form its files reached
                              the panel in (lead only: concept_forms(), below)
    <study>/sites/            neutral copies of the "site" concepts, when panellists do not browse
                              (lead only: sites_dir(), below)
    <study>/study-brief.md    what the lead agreed with the user, from assets/study-brief.md (lead
                              only: init_study.py refuses a copy of it anywhere under panel/)
    <study>/runs.json         one entry per run (schema below)
    <study>/prompts/          one run prompt per run, <run id>.md, and one filled brief per analyst
                              and writer job, <job id>.md
    <study>/panel/            the only folder panellists may read
        _panel-instructions.md
        sites/concept-<L>/    neutral copies of each concept of kind "site", only in a study whose
                              panellists browse: a copy holds the page source under its own file
                              names, so a study that does not browse (a text-only study, "browse":
                              false, or a "url" concept without "browse": true) keeps them in
                              <study>/sites/ instead, where no panellist can read one. A "url" or
                              "files" concept has no copy (concept kinds, below)
        materials/concept-<L>/<page>/
        personas/<pid>-<slug>--<key>.md, or ...--<key>-r<n>.md for replicate n > 1
        scratch/<run id>/
    <study>/analysis/         scores.csv, rankings.csv, runs.csv, answers.csv, lines.csv (what each run
                              answered and quoted), quant.md, quant.json, checks.md,
                              lead-notes.md (the lead's), qual-<n>.md (one per analyst), SYNTHESIS.md
                              (the writer's) and, from launch.py, <job id>-reply.md and usage.md
                              (what each harness reported: per run, per model key, per role and
                              in total)
    <study>/logs/             launch.py only: <run id>.<attempt>.in, .out and .err, the input and
                              output of each CLI process it started; .pid, where the attempt's
                              watchdog records itself and the CLI before the CLI runs; .end, the
                              end record the watchdog writes when the attempt has ended (both
                              formats in run_watchdog.py); modifications.json (the
                              modification record, below); earlier-sessions.json (the sessions
                              of the runs init_study.py --force replaced, below); and, for an
                              attempt that put a follow-up question, .before, the persona file
                              as it was, kept until the attempt's end is in runs.json (the
                              snapshot rule, below), and .rejected.md, the file as a rejected
                              follow-up left it. A process that never
                              ran as the CLI is no attempt: its files stay until the next
                              attempt, which has the same number, replaces them
    <study>/.launch.lock      launch.py only: present while a launcher has the study
    <study>/.capture-<pid>-*/ capture.py only: the scratch folder of one capture, named after its
                              process, where each page or item is captured before it moves
                              under panel/materials, beside a record of any move under way. One
                              whose process is gone is settled by the next capture, which
                              finishes the move or puts the earlier capture back, and removed
                              (capture.py, publish() and settle())
    <study>/followups.json    followup.py only: the follow-up questions asked (format below)

Concept kinds. A concept in study.json is one of three kinds, named by its optional "kind":

    site    (default) "path": a folder with index.html. init_study.py copies it to
            concept-<L>/ under sites_dir(), and capture.py captures each <page>.html of the copy
            into materials/concept-<L>/<page>/
    url     "pages": [{"name", "url"}, ...], the first named "index", or "url" alone for a
            concept of one page. Nothing is copied: capture.py opens each address and captures it
            as it does a site page, into materials/concept-<L>/<name>/. "states" work as for a site
    files   "files": image and PDF paths in the order to go through them, or "path": a folder
            whose images and PDFs are taken in name order. Nothing is copied by init_study.py.
            capture.py writes each file to materials/concept-<L>/item-<NN>/: an image as
            image.<type>, with part-<NN>.png when it is much taller than a screen, and a PDF as
            page-<NN>.png, one per page, with page-text.txt. A text-only study takes the PDFs only

Nothing under panel/ and no run prompt carries a concept id, a source path, a file name or, unless
the study browses, a URL: key.md maps them for the lead. concept_kind(), url_pages(),
concept_items(), concept_pages() and concept_folders() read a concept, and check_concepts()
validates its shape.

Names that become paths. Every configured string that names a file or folder is checked when
study.json is loaded, so none can leave the folder it belongs in: a url page's name and a state's
name (PAGE_NAME, a folder under materials/), a pinned label (LABEL), a concept id, a persona id
and a persona slug (name_problem(): one file-name part, with no separator and no leading dot or
hyphen). A persona id holds no hyphen at all (persona_id_problem()), and a persona whose name
gives an empty slug needs a "slug". Model keys are letters and digits (KEY_RE). capture.py checks again, on the paths
themselves, that everything it writes or deletes is inside panel/materials.

Forms. forms.json records the form each "files" concept reached the panel in ("image files",
"PDF files" or "image and PDF files"), by concept id. init_study.py and capture.py write it from
the source files, and concept_forms() reads it when those can no longer be read, as in an
archived round, so that analyze.py still says when a PDF was compared with an image.

Browsing ("browse") defaults to true for a study of sites. With any "url" concept it is off unless
study.json says "browse": true, and then the instructions give each page's address. A "files"
concept has nothing to open, and a study of nothing else never browses (apply_kinds()). Where the
site copies are kept follows from it (sites_dir()).

A study with one concept ranks and compares nothing: single_concept() says so, and the
templates, checks and analysis follow it. Its instructions speak of one "artefact" (the singular
of "artefact_plural"), which study.json must give when it sets the plural.

A run is one persona on one model entry and one replicate. Its id is <pid>-<key>, or
<pid>-<key>-r<n> for replicate n > 1, where <key> is the model entry's key (letters and digits).

Model entries. Each item of study.json "models" is a bare model name or an object
{"key", "runner", "model", "effort"}; model_entries() normalises both. "runner" falls back to
the study-level "runner", and a study where no entry has one is in native mode: the lead starts
each run with its own subagent tool. A study is all native or all runners.

runs.json is a list. init_study.py writes one entry per panellist run:

    run        run id, also the prompt file name and the scratch folder
    persona    persona id
    name       persona name
    segment    persona segment, "" when unset
    key        model key: the name used in file names, run ids, limits.overrides and the
               "model" column of scores.csv
    runner     runner name, or null in native mode
    model      model name to launch with, or null for the runner's default model
    effort     thinking effort to launch with, or null
    replicate  1-based replicate number
    role       "panellist"
    file       persona file, relative to the study directory
    prompt     run prompt, relative to the study directory

Whatever starts runs adds its own fields to an entry. runs.py mark adds "agent", the subagent
id, in native mode. launch.py adds these, and an entry it has never touched has none of them:

    state         pending, running, done, partial, limited, blocked or failed (run_state())
    pid           process id of the CLI of the attempt now running, else null. For show:
                  logs/<run id>.<attempt>.pid is what a launcher goes by. It names the
                  attempt's watchdog too, and is there even when a launcher died before it
                  could note the pid here
    pid_identity  that process's start time as the system reports it, so a process id that
                  was reused is never taken for the run
    session       the harness session id of the current or last attempt, null when unknown
    sessions      {session id: usage}: what each session reported, one record per session
                  (runners.merge_usage). The run's usage is their sum (runners.total_usage)
    attempts      one object per process started: "n" (1-based), "kind" (launch, retry,
                  resume, restart for a fresh launch made by the resume command, or followup
                  for a follow-up question put to a finished run), "started"
                  (epoch seconds), "allowed" (the seconds its watchdog was given: what was
                  left of the run's time), "ended" (epoch seconds, from the watchdog's end
                  record), "seconds", "exit_code" (null when unknown), "outcome" (the
                  runner's: ok, usage_limit, budget or error), "state" (the state it left the
                  run in) and "session". "usage_reported" is there only for an attempt whose
                  process was stopped (time limit or stop) before the harness reported any
                  tokens or cost: false while that spend is in no figure, true once a later
                  result of the same session has brought its running total. False is "not
                  reported", never zero. "end_record": false is there only for an attempt
                  whose watchdog was killed before it wrote one: "ended" is then the latest
                  the process can have run within its limit, and the exit code is unknown.
                  "leftover" ({"group", "pids"}) is there only for such an attempt whose CLI
                  had gone while a process group of its id still had processes: they may be
                  the run's, the launcher could not prove it and left them alone.
                  "was" is there only while the attempt runs: the run's state, pid, session,
                  reason and reset_at before it, so that an attempt whose process never ran
                  as the CLI can be taken back.
                  A followup attempt has three more: "followup" (the follow-up's number),
                  "answer" (its outcome, as in followups.json) and "usage" (what the harness
                  reported for this process alone, each figure null when it gave none). It
                  never changes the run's "state", "reason" or "reset_at": while it runs,
                  and until a launcher has settled it, it is the last attempt and its "ended"
                  is null (asking()).
                  "unallocated" is there only for a followup attempt whose result was one
                  total for itself and for an earlier process of the run that had been
                  stopped before reporting: {"input_tokens", "output_tokens",
                  "cached_tokens", "cost_usd"}, what the two used together, and
                  "run_unreported", the figures the run itself had reported none of. Nothing
                  can split it, so it is in neither the run's usage nor the follow-up's: its
                  "usage" has no tokens or cost, and the usage record lists it apart
    seconds_used  wall-clock seconds over every attempt but the followup ones. With the
                  reported spend it counts against the run's limits, which cover all its
                  attempts. A follow-up has an allowance of its own (limits.followup)
    reason        why the run stopped, in a sentence; null while running and when done. For a
                  blocked run it carries the harness's own message, which says whether it was
                  a usage limit, a rate limit or a capacity refusal
    reset_at      epoch seconds when the limit that blocked the run lifts, when the harness
                  said, else null
    extended      times "resume --extend" gave the run one more allowance of its limits
    purged        {session id: epoch seconds}: the sessions "purge-sessions" deleted from the
                  harness. A purged session cannot be resumed. Its usage stays in "sessions"
    lost          {session id: epoch seconds}: the sessions a resume found gone from the
                  harness. Treated as purged ones are

Job entries. launch.py adds one entry per analyst and writer job (synthesis_jobs()) when
"run --role analyst" or "run --role writer" plans them, and rewrites one while its job is
pending or failed. A job is one output file, so its entry has no persona, segment or replicate:

    run        analyst-1, analyst-2 or writer; also the prompt file name
    role       "analyst" or "writer"
    name       what status shows, for example "Analyst 1 of 2"
    key, runner, model, effort   the synthesis.analyst or synthesis.writer model entry. "key" is
               null when the entry gives none
    personas   analyst only: the ids of the personas whose files it reads, in persona id order
    file       its output file, relative to the study directory. The job is done when this file
               exists and is not empty
    prompt     its brief with every placeholder filled, relative to the study directory

It gets the same launcher fields as a panellist run, and one more: "note", a sentence about a
finished job's output that the lead should know (it was taken from the job's reply, or its
process did not end cleanly), else null. Everything that lists panellist runs selects the role
"panellist", so job entries never appear in run tracking, checks, scores or analysis.

read_runs() and write_runs() pass fields they don't know through untouched. Entries written
before "key", "runner", "effort", "replicate" and "role" existed read as native-mode panellist
runs: key = model, replicate 1.

Whether a run is finished is decided by its persona file alone: see run_progress(). The state a
launcher records in an entry's "state" says why an unfinished run stopped: see run_state().

The modification record, logs/modifications.json, is how a persona file changed by a run other
than its owner is found. launch.py hashes every panellist's persona file each time it starts a
process, each time one ends, and when a launcher takes over a study, and compares each hash with
the last one recorded:

    hashes     {persona file, relative to the study directory: SHA-256 of its content, or null
               when the file is missing}: the last value seen
    changes    one object per change made while the file's own run was not running and other
               processes were: "file", "run" (the owner), "at" (epoch seconds, when the launcher
               saw it) and "running" (the runs and jobs alive since the hash before)

Between two hashings the set of live processes does not change, so a change is laid at the door
of the processes alive then. One made while the owner's process was alive, or in the moments
between its exit and the launcher noticing, counts as the owner's and is not recorded. One made
while nothing was running is the lead's own edit and is not recorded either: only the hash is
brought up to date. check_runs.py reports each entry of "changes" as a blocking problem for its
run; once dealt with, take the entry out of the file. A native-mode study has no record.

Earlier sessions. init_study.py --force replaces runs.json, and with it the only note of the
harness sessions its runs and jobs started. The ones that were not purged or lost are carried
over to logs/earlier-sessions.json, a list that each --force adds to, so "launch.py
purge-sessions" can still delete them. One object per session:

    run        the id of the run or job that started it, in the scaffold that was replaced
    runner     its runner
    session    the harness session id
    workdir    the directory its process worked in, which a runner may need to find the session
    replaced   epoch seconds when --force replaced the scaffold

purge-sessions (without --runs) takes each one out as it deletes it, and removes the file with the
last. A session whose runner cannot delete one stays on record. A native-mode study has none.

Follow-ups. followups.json is a list with one object per question followup.py asked:

    n          the follow-up's number, 1-based and counted over the study. Its answers are the
               "## Follow-up <n>" sections at the end of persona files
    question   the question, as the researcher wrote it
    asked      epoch seconds when it was asked
    mode       "runner": launch.py's supervisor resumed each run's session with it, or "native":
               the lead sent it to each run's subagent by hand
    limits     runner mode: {"minutes", "budget_usd"}, what each run was allowed for it
    runs       one object per run asked: "run", "outcome", "reason" (a sentence, or null),
               "attempt" (the number of the run's attempt that asked, null when no process ran)
               and "session" (the harness session it was sent to; the subagent id in native mode).
               "settling" is there only while a launcher is settling the attempt (below)

"outcome" is one of FOLLOWUP_OUTCOMES, or null while the question is queued, with the panellist,
or not settled yet:

    answered                the panellist appended its section, and nothing else changed
    answered from the reply it replied without writing a section, so the launcher wrote the
                            section from the reply, and says so in it
    rejected                it changed something else in its file: the file was put back as it
                            was, and what it wrote is in logs/<run id>.<attempt>.rejected.md
    unanswered              its process ended with no section and no reply
    turned away             its harness was turning requests away (a usage limit, a rate limit or
                            a capacity refusal)
    could not start         its CLI could not be started, or its session was gone
    not asked               the command stopped, its runner closed or its launcher was killed
                            before its turn came
    sent by hand            native mode: nothing was checked

Settling. When a follow-up attempt's process has ended, a launcher settles it in steps, each on
record before the next, so that a launcher killed between any two leaves a state the next one
brings to the same end:

    1. It decides, changing nothing, and writes the decision to the run's record as "settling":
       {"attempt", "outcome", "reason", "action", "section"}. "action" is what is to be done to
       the persona file: "keep" (nothing), "restore" (put it back from the copy made before the
       question, keeping what a rejected follow-up left in .rejected.md) or "append" (the copy,
       then "section", the section written from the reply).
    2. It does the action. Every write replaces a file in one step and is made from the copy, so
       doing it twice ends the same.
    3. It sets "outcome" and "reason" and takes "settling" out.
    4. It writes the attempt's end to runs.json.
    5. It deletes the copy.

A launcher that finds "settling" for the attempt does not decide again: it starts at step 2. One
that finds the outcome starts at step 4. Every launcher command settles what it finds this way
before anything else, and so does "followup.py list" when no launcher has the study. A record
with no outcome and no attempt in flight is one whose launcher was killed while the run was
queued: it becomes "not asked".

The snapshot rule. From the moment a follow-up attempt is in runs.json until its end is (step 4),
the persona file may hold what settling will reject. Until then nothing reads the file for
scores, answers, lines, checks or progress: read_persona() reads the copy made before the
question, logs/<run id>.<attempt>.before, and every reader goes through it (load_runs(),
run_records(), launch.py and runs.py). A script that read a copy says so in one line per run
(unsettled_lines()). An archive has no logs/, so there the file itself is read, and archive.py
refuses a study with a follow-up that is not settled.

The rule rests on the order a launcher keeps. To ask: the copy is written, then the attempt is
saved in runs.json, and only then is the process started, so the file cannot change before both
are there. To settle: the file is put right (step 2) before the attempt's end is saved (step 4),
and the copy goes last. A reader holds no lock, and the runs.json entry it goes by may be older
than the file it then reads. So read_persona() does not trust the entry it is handed: after
reading it looks the run's attempts up in runs.json again, and chooses and reads again when they
have changed, until two looks one after the other agree. When they never do, it returns a copy
still on disk, or with none refuses the read by exiting: content read from the file between
looks that disagree is never returned. A launcher's own reads cannot come to that, since under
the study lock nothing else writes an attempt to runs.json. What copies files out of a study
(archive.py) cannot read around a launcher that way, so it takes the study lock instead.

A follow-up never changes a score: follow-up sections come after everything parse_persona_file()
reads for scores, rankings, answers and lines, and it lists them apart, under "followups". They
are qualitative evidence only, and no script tallies them.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import statistics
import shutil
import string
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

SKILL_DIR = Path(__file__).resolve().parents[1]
ASSETS = SKILL_DIR / "assets"

DEFAULT_FACTORS = [
    {"key": "first", "label": "First impression", "short": "First",
     "question": "After 5 seconds, do I know what this is, who it's for and what it does for me?"},
    {"key": "relevance", "label": "Relevance to me", "short": "Relevance",
     "question": "Does this feel built for someone in my role and my kind of business?"},
    {"key": "problem", "label": "Problem recognition", "short": "Problem",
     "question": "Does it name problems I actually have, in words I'd use?"},
    {"key": "how", "label": "How it works", "short": "How",
     "question": "Do I understand how it would work in my business, day to day?"},
    {"key": "why_care", "label": "Why care", "short": "Why care",
     "question": "Is the benefit to me clear and big enough to act on?"},
    {"key": "trust", "label": "Trust", "short": "Trust",
     "question": "Do I believe it? Think risk, my brand, my clients' data, and the vendor itself."},
    {"key": "visual", "label": "Visual design", "short": "Visual", "needs_design": True,
     "question": "Does it look professional, calm and credible, or busy, gimmicky or cheap?"},
    {"key": "structure", "label": "Structure and flow", "short": "Structure",
     "question": "Is it easy to scan and follow, the right length, with things where I expect them?"},
    {"key": "mobile", "label": "Mobile", "short": "Mobile", "needs_design": True,
     "question": "Judged from the phone screens: would it work if I opened it on my phone?"},
    {"key": "next_step", "label": "Next step", "short": "Next step",
     "question": "How likely am I to book a demo, sign up or pass it on?"},
    {"key": "overall", "label": "Overall", "short": "Overall",
     "question": "Your overall verdict. It doesn't have to be the average of the other scores."},
]

DEFAULT_FIT_FACTORS = ["relevance", "why_care", "next_step"]
# The factors that cannot be judged without seeing the page. A factor in study.json says so with
# "needs_design": true, and one that reuses a key below needs it unless it says false.
DESIGN_FACTORS = tuple(f["key"] for f in DEFAULT_FACTORS if f.get("needs_design"))
DASHES = ("\u2013", "\u2014")
FINAL_MARKER = "## Out of character"

# Study type -> the unit a run works through: its nouns, and its section heading in a persona file.
STUDY_TYPES = {
    "review": {"unit": "concept", "units": "concepts", "heading": "Concept"},
    "usability": {"unit": "task", "units": "tasks", "heading": "Task"},
}
MATERIALS = ("full", "text")
KINDS = ("site", "url", "files")
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
DOCUMENT_TYPES = (".pdf",)
PAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")  # a url page's name or a state's, which becomes a folder name
LABEL = re.compile(r"[A-Za-z0-9]+")  # a pinned label: what the parsers read after "Concept", and a folder name
NAME_PART = re.compile(r"[^\s./\\-][^/\\\x00-\x1f\x7f]*")  # one part of a file name: name_problem()
NAME_RULE = ("must be one part of a file name: no slash, backslash or line break, and no dot, hyphen or space to "
             "begin with")
FILE_FORMS = ("image files", "PDF files", "image and PDF files")  # the forms of a "files" concept
DEFAULT_ARTEFACT = ("draft website design", "draft website designs")  # singular, plural
ENTRY_FIELDS = ("key", "runner", "model", "effort")
KEY_RE = re.compile(r"[A-Za-z0-9]+")
LIMIT_NAMES = ("minutes", "budget_usd")
DEFAULT_LIMITS = {
    "run": {"minutes": 15, "budget_usd": 2.0},        # each panellist run, over all its attempts
    "synthesis": {"minutes": 30, "budget_usd": 5.0},  # analyst and writer jobs
    "followup": {"minutes": 5, "budget_usd": 0.5},    # each run asked a follow-up, for each question
}
RUN_DEFAULTS = {"runner": None, "effort": None, "replicate": 1, "role": "panellist"}
JOB_ROLES = ("analyst", "writer")
SYNTHESIS_KEYS = ("analysts", "analyst", "writer", "decision_maker", "context_files")
DEFAULT_DECISION_MAKER = "the decision-maker"
MODIFICATIONS = "logs/modifications.json"  # the modification record, relative to the study directory
EARLIER_SESSIONS = "logs/earlier-sessions.json"  # sessions of the runs a --force replaced, relative to it too
STUDY_BRIEF = "study-brief.md"             # the lead's copy of assets/study-brief.md, beside study.json
FOLLOWUPS = "followups.json"               # the follow-up questions asked, relative to the study directory
FORMS = "forms.json"                       # the form of each "files" concept, relative to it too
FOLLOWUP_OUTCOMES = ("answered", "answered from the reply", "rejected", "unanswered", "turned away",
                     "could not start", "not asked", "sent by hand")
FOLLOWUP_ANSWERED = FOLLOWUP_OUTCOMES[:2]  # the outcomes that leave a section the launcher has checked
FOLLOWUP_HEADING = re.compile(r"^## Follow-up (\d+)\s*$")
FROM_REPLY = "(Taken from the panellist's reply by the launcher: the panellist did not write this section itself.)"
PLACEHOLDER = re.compile(r"<([A-Z][A-Z0-9_]*)>")
# The synthetic panel notice: the one line every persona file, synthesis, report and archive README
# carries, so that a file read on its own is never taken for research with real people. with_notice()
# adds it, and a brief asks for it with <NOTICE>.
NOTICE = ("Synthetic panel: the feedback in this study was generated by AI personas, not by real people. "
          "It is not user research.")
# The name roster.py gives a skeleton persona. init_study.py refuses a study that still has one.
SKELETON_NAME = "TODO"


# ---------------------------------------------------------------- wording

def agree(n: int, one: str, many: str | None = None) -> str:
    """The word that agrees with a count of n: one for exactly 1, else many, which is one + "s"
    when it is not given. Every sentence a script writes around a count takes its nouns, verbs
    and pronouns from here ("is" or "are", "it" or "them"), so none says "1 runs"."""
    return one if n == 1 else one + "s" if many is None else many


def plural(n: int, noun: str, many: str | None = None) -> str:
    """A count with its noun: "1 run", "2 runs", "1,200 pages", "2 model entries"."""
    return f"{n:,} {agree(n, noun, many)}"


# ---------------------------------------------------------------- config

def load_study(study_dir: Path) -> dict:
    study_dir = Path(study_dir).resolve()
    try:
        cfg = json.loads((study_dir / "study.json").read_text())
    except OSError as err:
        raise SystemExit(f"Cannot read {study_dir / 'study.json'} ({err.strerror}). Pass the study directory, the "
                         "one that holds study.json.")
    except ValueError as err:
        raise SystemExit(f"{study_dir / 'study.json'} is not valid JSON: {err}")
    cfg.setdefault("factors", DEFAULT_FACTORS)
    cfg.setdefault("fit_factors", [f for f in DEFAULT_FIT_FACTORS if f in {x["key"] for x in cfg["factors"]}])
    cfg.setdefault("models", ["opus", "fable"])
    cfg.setdefault("seed", 1)
    cfg.setdefault("label_style", "letters")
    cfg.setdefault("shuffle_labels", True)
    cfg.setdefault("leak_terms", [])
    cfg.setdefault("find_the_answer", [])
    cfg.setdefault("context_notes", [])
    cfg.setdefault("segments", {})
    cfg.setdefault("type", "review")
    cfg.setdefault("materials", "full")
    cfg.setdefault("replicates", 1)
    cfg.setdefault("runner", None)
    asked_to_browse = cfg.get("browse") is True  # said in study.json, which a text-only study overrides
    cfg.setdefault("browse", True)
    # The singular is known only for the default plural: a study of one concept that names its
    # own "artefact_plural" names "artefact" too (init_study.py refuses it otherwise).
    cfg.setdefault("artefact", None if "artefact_plural" in cfg else DEFAULT_ARTEFACT[0])
    cfg.setdefault("artefact_plural", DEFAULT_ARTEFACT[1])
    for k in ("limits", "runners", "synthesis"):
        cfg.setdefault(k, {})
    cfg.setdefault("concepts", [])
    cfg["_dir"] = study_dir
    check_study(cfg)
    apply_materials(cfg, asked_to_browse)
    apply_kinds(cfg, asked_to_browse)

    def resolved(path):
        p = Path(path).expanduser()
        return (p if p.is_absolute() else study_dir / p).resolve()

    for c in cfg["concepts"]:
        if "path" in c:
            c["_path"] = resolved(c["path"])
        if "files" in c:
            c["_files"] = [resolved(f) for f in c["files"]]
    if cfg["factors"][-1]["key"] != "overall":
        raise SystemExit("study.json: the last factor must be 'overall'")
    return cfg


def _fail(msg: str):
    raise SystemExit(f"study.json: {msg}")


def _positive(x, whole: bool = False) -> bool:
    return isinstance(x, int if whole else (int, float)) and not isinstance(x, bool) and x > 0


def check_study(cfg: dict):
    """Validate the shape of the optional keys. Whether a runner exists is the launcher's check."""
    if cfg["type"] not in STUDY_TYPES:
        _fail(f'unknown "type" {cfg["type"]!r} (use {" or ".join(STUDY_TYPES)})')
    if cfg["materials"] not in MATERIALS:
        _fail(f'unknown "materials" {cfg["materials"]!r} (use {" or ".join(MATERIALS)})')
    if not _positive(cfg["replicates"], whole=True):
        _fail('"replicates" must be a whole number, 1 or more')
    if cfg["runner"] is not None and not (isinstance(cfg["runner"], str) and cfg["runner"]):
        _fail('"runner" must be a runner name')
    if not isinstance(cfg["browse"], bool):
        _fail('"browse" must be true or false: whether panellists may open pages with agent-browser')
    for key in ("artefact", "artefact_plural"):
        if cfg[key] is not None and not (isinstance(cfg[key], str) and cfg[key].strip()):
            _fail(f'"{key}" must be a few words for what is reviewed, such as "{DEFAULT_ARTEFACT[key == "artefact_plural"]}"')
    if cfg["type"] == "review" and not cfg["concepts"]:
        _fail("a review study needs at least one concept")
    check_concepts(cfg)
    check_personas(cfg)
    check_capture(cfg)
    keys = model_keys(cfg)

    limits = cfg["limits"]
    if not isinstance(limits, dict) or set(limits) - {*DEFAULT_LIMITS, "overrides"}:
        _fail('"limits" must be an object with any of run, synthesis, followup and overrides')
    sets = {f"limits.{k}": limits[k] for k in DEFAULT_LIMITS if k in limits}
    overrides = limits.get("overrides", {})
    if not isinstance(overrides, dict):
        _fail("limits.overrides must be an object keyed by model key")
    for k, v in overrides.items():
        if k not in keys:
            _fail(f'limits.overrides: "{k}" is not a model key (keys: {", ".join(keys)})')
        sets[f"limits.overrides.{k}"] = v
    for where, d in sets.items():
        if not isinstance(d, dict) or set(d) - set(LIMIT_NAMES):
            _fail(f"{where} must be an object with any of {' and '.join(LIMIT_NAMES)}")
        for name, v in d.items():
            if not _positive(v):
                _fail(f"{where}.{name} must be a positive number")

    if not isinstance(cfg["runners"], dict):
        _fail('"runners" must be an object keyed by runner name')
    for name, opts in cfg["runners"].items():
        if not isinstance(opts, dict):
            _fail(f"runners.{name} must be an object")
        if "concurrency" in opts and not _positive(opts["concurrency"], whole=True):
            _fail(f"runners.{name}.concurrency must be a whole number, 1 or more")

    syn = cfg["synthesis"]
    if not isinstance(syn, dict) or set(syn) - set(SYNTHESIS_KEYS):
        _fail(f'"synthesis" must be an object with any of {", ".join(SYNTHESIS_KEYS)}')
    if syn.get("analysts", 1) not in (1, 2) or isinstance(syn.get("analysts"), bool):
        _fail("synthesis.analysts must be 1 or 2")
    for job in JOB_ROLES:
        if job in syn:
            model_entry(syn[job], cfg["runner"], f"synthesis.{job}")
    who = syn.get("decision_maker", DEFAULT_DECISION_MAKER)
    if not (isinstance(who, str) and who.strip()):
        _fail("synthesis.decision_maker must be a non-empty string: who the synthesis is written for")
    files = syn.get("context_files", [])
    if not isinstance(files, list) or not all(isinstance(f, str) and f for f in files):
        _fail("synthesis.context_files must be a list of file paths")
    for f in files:
        if Path(f).is_absolute() or ".." in Path(f).parts:
            _fail(f'synthesis.context_files: "{f}" must be a path inside the study directory, written relative '
                  "to it, because an analyst can read nothing outside it")
        if study_brief_copy(cfg["_dir"], [cfg["_dir"] / f]):
            _fail(f'synthesis.context_files: "{f}" is the study brief, or a copy of it. The brief holds the '
                  "team's hypotheses, and an analyst or writer that has read them tends to find them. Take it "
                  "out, and put what the jobs need (the decisions and constraints that apply now) in a file of "
                  "its own")
    variants(cfg)


def name_problem(name) -> str | None:
    """Why a configured string cannot be one part of a file or folder name, else None. It names a
    file or a folder, so it must stay in the folder it is put in: a string with no slash, no
    backslash and no control character, that does not begin with a dot (".." is the folder above)
    or with a hyphen (a tool given the name would read an option), and with no space at either
    end."""
    return None if isinstance(name, str) and NAME_PART.fullmatch(name) and name == name.strip() else NAME_RULE


def persona_id_problem(pid) -> str | None:
    """Why a string cannot be a persona id, else None, as the end of a sentence about it. An id
    names the persona's files, so it is one part of a file name (name_problem()), and it holds no
    hyphen: a persona file is <id>-<slug>--<key>.md and a run id <id>-<key>, and both are read
    back by their first hyphen (FILE_RE). The one rule for study.json and for a roster file."""
    if name_problem(pid):
        return f"{NAME_RULE}, because it names the persona's files"
    if "-" in pid:
        return ("cannot hold a hyphen, because the persona file is named <id>-<slug>--<key>.md and is read back by "
                "its first hyphen")
    return None


def check_personas(cfg: dict):
    """Validate what of each persona names files: its id (the persona file, the run prompt, the
    scratch folder and the logs are named after it) and its slug, given as "slug" or made from
    its name. Two personas with one id would write the same files, each over the other's."""
    people = cfg.get("personas") or []
    if not isinstance(people, list) or not all(isinstance(p, dict) for p in people):
        _fail('"personas" must be a list of objects')
    seen = set()
    for p in people:
        pid = p.get("id")
        if persona_id_problem(pid):
            _fail(f"the persona id {json.dumps(pid)} {persona_id_problem(pid)}")
        if pid.lower() in seen:
            _fail(f'two personas have the id "{pid}". Ids must be unique, ignoring case, because they name files')
        seen.add(pid.lower())
        if p.get("slug") and name_problem(p["slug"]):
            _fail(f'persona {pid}: its "slug" {json.dumps(p["slug"])} {name_problem(p["slug"])}, because it is '
                  "part of the persona file's name")
        name = p.get("name")  # a skeleton, with no name yet, is init_study.py's to refuse
        if not p.get("slug") and isinstance(name, str) and name.strip() and not slugify(name):
            _fail(f"persona {pid}: its name {json.dumps(name, ensure_ascii=False)} has no letter from a to z and no "
                  'digit to make its file name from. Give it a "slug" of such letters, digits and hyphens, for '
                  'example "slug": "persona-one"')


def check_capture(cfg: dict):
    """Validate study.json "capture": its values are sizes and counts that capture.py hands to the
    browser, ImageMagick and Poppler as arguments, so each must be the number or the words it
    stands for."""
    cap = cfg.get("capture", {})
    if not isinstance(cap, dict):
        _fail('"capture" must be an object')
    for key in ("max_screens", "max_pdf_pages", "pdf_pixels"):
        if key in cap and not _positive(cap[key], whole=True):
            _fail(f"capture.{key} must be a whole number, 1 or more")
    for key in ("mobile_screens_home", "mobile_screens_other"):
        if key in cap and not (isinstance(cap[key], int) and not isinstance(cap[key], bool) and cap[key] >= 0):
            _fail(f"capture.{key} must be a whole number, 0 or more")
    for key in ("desktop", "mobile"):
        if key in cap and not (isinstance(cap[key], list) and len(cap[key]) == 2
                               and all(_positive(v, whole=True) for v in cap[key])):
            _fail(f"capture.{key} must be [width, height] in pixels")
    media = cap.get("media", "")
    if not isinstance(media, str) or not all(re.fullmatch(r"[a-z][a-z-]*", word) for word in media.split()):
        _fail('capture.media must be words such as "light" or "light reduced-motion"')


def concept_kind(c: dict) -> str:
    return c.get("kind", "site")


def url_pages(c: dict) -> list[dict]:
    """The pages of a "url" concept, [{"name", "url"}, ...], home page first: its "pages", or its
    one "url" as the page "index"."""
    return c["pages"] if "pages" in c else [{"name": "index", "url": c["url"]}]


def check_concepts(cfg: dict):
    """Validate the shape of every concept for its kind. Whether a folder or a file exists is
    checked when it is needed (init_study.py, capture.py), so that an archived study, whose
    sources may be gone, still loads."""
    concepts = cfg["concepts"]
    if not isinstance(concepts, list) or not all(isinstance(c, dict) for c in concepts):
        _fail('"concepts" must be a list of objects')
    seen = set()
    for c in concepts:
        cid = c.get("id")
        if not (isinstance(cid, str) and cid.strip()):
            _fail(f'every concept needs an "id": {json.dumps(c)} has none')
        if name_problem(cid) or "--" in cid:
            _fail(f'the concept id {json.dumps(cid)} {name_problem(cid) or "must not contain two hyphens in a row"}, '
                  "because the archive names a folder after it, and its screenshots <id>--<page>")
        if cid.lower() in seen:
            _fail(f'two concepts have the id "{cid}". Ids must be unique, ignoring case, because key.md, the '
                  "labels and the archive's folders go by them")
        seen.add(cid.lower())
        where, kind = f"concept {cid}:", concept_kind(c)

        def text(key):
            return isinstance(c.get(key), str) and bool(c[key].strip())

        def only(*allowed):
            for key in ("path", "url", "pages", "files"):
                if key in c and key not in allowed:
                    hint = (f'. Add "kind": "{"url" if key in ("url", "pages") else "files"}" if that is what it is'
                            if kind == "site" and "kind" not in c else "")
                    _fail(f'{where} "{key}" does not belong to a concept of kind "{kind}"{hint}')

        def states(pages=None):
            """Check the concept's states, each of which capture.py writes to the folder
            <page>@<name>. pages: the names of the concept's pages, when study.json gives them."""
            listed, folders = c.get("states", []), set()
            if not isinstance(listed, list) or not all(isinstance(st, dict) for st in listed):
                _fail(f'{where} "states" must be a list of {{"name", "page", "js"}} objects')
            for st in listed:
                name, page = st.get("name"), st.get("page", "index")
                if not (isinstance(name, str) and PAGE_NAME.fullmatch(name)):
                    _fail(f"{where} the state name {json.dumps(name)} must be letters, digits, hyphens and "
                          "underscores only, because it names a folder that panellists see")
                if not isinstance(page, str) or (pages is not None and page not in pages):
                    _fail(f"{where} a state names the page {json.dumps(page)}, which is not one of its pages"
                          + (f" ({', '.join(pages)})" if pages else ""))
                if not (isinstance(st.get("js"), str) and st["js"].strip()):
                    _fail(f'{where} the state "{name}" needs "js": the script that sets it on the page')
                if (page, name) in folders:
                    _fail(f'{where} two states of the page "{page}" have the name "{name}", and each is captured '
                          "to a folder of that name")
                folders.add((page, name))

        if kind not in KINDS:
            _fail(f'{where} unknown "kind" {json.dumps(kind)} (use {", ".join(KINDS[:-1])} or {KINDS[-1]})')
        if kind == "site":
            only("path")
            if not text("path"):
                _fail(f'{where} a site concept needs "path": the folder that holds its index.html')
            states()
        elif kind == "url":
            only("url", "pages")
            if ("url" in c) == ("pages" in c):
                _fail(f'{where} a url concept needs "pages": [{{"name": "index", "url": "https://..."}}, ...], '
                      'or "url" alone for a concept of one page, and not both')
            if "url" in c and not text("url"):
                _fail(f'{where} "url" must be an address')
            pages = url_pages(c)
            if not isinstance(pages, list) or not pages or not all(
                    isinstance(p, dict) and set(p) == {"name", "url"} and all(isinstance(v, str) for v in p.values())
                    for p in pages):
                _fail(f'{where} "pages" must be a list of {{"name", "url"}} objects, the home page first')
            names = [p["name"] for p in pages]
            for name in names:
                if not PAGE_NAME.fullmatch(name):
                    _fail(f'{where} the page name {json.dumps(name)} must be letters, digits, hyphens and '
                          "underscores only, because it names a folder that panellists see")
            if names[0] != "index":
                _fail(f'{where} its first page must be the home page, named "index" (it is "{names[0]}"): the '
                      "instructions tell panellists that the home page is always index")
            if len(set(names)) < len(names):
                _fail(f"{where} two pages have the same name")
            for p in pages:
                try:
                    parts = urlsplit(p["url"])
                    ok = parts.scheme in ("http", "https") and bool(parts.hostname)
                except ValueError:
                    ok = False
                if not ok:
                    _fail(f'{where} the address of page "{p["name"]}", {json.dumps(p["url"])}, must be a full '
                          "http:// or https:// URL. A folder of HTML files is a site concept, with \"path\"")
            states(names)
        else:
            only("path", "files")
            if ("path" in c) == ("files" in c):
                _fail(f'{where} a files concept needs "files": the images and PDFs in the order to go through '
                      'them, or "path": a folder whose images and PDFs are taken in name order, and not both')
            if "path" in c and not text("path"):
                _fail(f'{where} "path" must be a folder')
            if "files" in c:
                files = c["files"]
                if not isinstance(files, list) or not files or not all(isinstance(f, str) and f.strip() for f in files):
                    _fail(f'{where} "files" must be a list of file paths, in the order to go through them')
                for f in files:
                    if Path(f).suffix.lower() not in (*IMAGE_TYPES, *DOCUMENT_TYPES):
                        _fail(f'{where} "{f}" is not a file type a panel can review. {SUPPORTED_FILES}')
                if cfg["materials"] == "text" and not any(Path(f).suffix.lower() in DOCUMENT_TYPES for f in files):
                    _fail(f"{where} {NO_TEXT}")
            if c.get("states"):
                _fail(f'{where} "states" run a script on a page, and a files concept has no page to run one on')
    pinned = cfg.get("labels")
    if pinned:  # {label: concept id}, in place of the shuffle (label_map())
        if not isinstance(pinned, dict):
            _fail('"labels" must be an object, {label: concept id}')
        for label in pinned:
            if not LABEL.fullmatch(label):
                _fail(f"labels: the label {json.dumps(label)} must be letters and digits only, because it names a "
                      'folder and is what a panellist writes after "Concept"')
        if len({label.lower() for label in pinned}) < len(pinned):
            _fail("labels: two labels differ only in case, and each names a folder")
        if sorted(map(str, pinned.values())) != sorted(c["id"] for c in concepts):
            _fail(f"labels: every concept id needs one label, and no label another id (ids: "
                  f"{', '.join(c['id'] for c in concepts)})")


SUPPORTED_FILES = (f"Images: {', '.join(t[1:] for t in IMAGE_TYPES)}. Documents: "
                   f"{', '.join(t[1:] for t in DOCUMENT_TYPES)}.")
NO_TEXT = ('it has only images, and a text-only study ("materials": "text") reads text alone. Give it a PDF, take '
           'the concept out, or review it with "materials": "full"')


def apply_kinds(cfg: dict, asked_to_browse: bool):
    """Set what follows from the concepts' kinds, and cfg["_browse_off"]: why the study does not
    browse although study.json did not say "browse": false, for the plan to say, else None.

    "url": the study has a "url" concept and study.json does not say "browse": true. A live page
    is opened by panellists only when the study sets it. "files": every concept is of kind
    "files", which has nothing to open, so the study never browses whatever "browse" says. A
    text-only study has its own reason (apply_materials) and none here.
    """
    kinds = {concept_kind(c) for c in cfg["concepts"]}
    cfg["_browse_off"] = None
    if cfg["materials"] == "text" or not cfg["browse"]:
        return
    if kinds == {"files"}:
        cfg["_browse_off"], cfg["browse"] = "files", False
    elif "url" in kinds and not asked_to_browse:
        cfg["_browse_off"], cfg["browse"] = "url", False


def natural(name: str) -> list:
    """A sort key that puts screen-9 before screen-10."""
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", name)]


def concept_items(cfg: dict, c: dict) -> tuple[list[tuple[str, Path]], list[Path]]:
    """The items of a "files" concept, [(folder name, source file), ...] in the order to go
    through them, and the files left out: the images, in a text-only study, which reads text.

    Folder names are item-01, item-02 and so on, never the file names, which would leak intent
    as a concept's folder name does. Exits, naming the concept, when its folder or one of its
    files is missing, when a file is of no supported type, or when nothing is left to review.
    """
    where = f"Concept {c['id']}:"
    if "_files" in c:
        files = c["_files"]
    else:
        folder = c["_path"]
        if not folder.is_dir():
            raise SystemExit(f"{where} no folder {folder}")
        files = sorted((f for f in folder.iterdir() if f.is_file()
                        and f.suffix.lower() in (*IMAGE_TYPES, *DOCUMENT_TYPES)), key=lambda f: natural(f.name))
        if not files:
            raise SystemExit(f"{where} no image or PDF in {folder}. {SUPPORTED_FILES}")
    for f in files:
        if not f.is_file():
            raise SystemExit(f"{where} no file {f}")
        if f.suffix.lower() not in (*IMAGE_TYPES, *DOCUMENT_TYPES):
            raise SystemExit(f"{where} {f.name} is not a file type a panel can review. {SUPPORTED_FILES}")
    text_only = cfg["materials"] == "text"
    kept = [f for f in files if not text_only or f.suffix.lower() in DOCUMENT_TYPES]
    if not kept:
        raise SystemExit(f"{where} {NO_TEXT}.")
    return [(f"item-{i:02d}", f) for i, f in enumerate(kept, start=1)], [f for f in files if f not in kept]


def concept_pages(cfg: dict, c: dict, site: Path | None = None) -> list[str] | None:
    """The names of a concept's page folders under panel/materials, without its states: the
    HTML files of a site (of the folder site, default its source), the page names of a url
    concept, the items of a files concept. None when the source cannot be read yet."""
    kind = concept_kind(c)
    if kind == "url":
        return [p["name"] for p in url_pages(c)]
    try:
        if kind == "files":
            return [name for name, _ in concept_items(cfg, c)[0]]
        return sorted(p.stem for p in (site or c["_path"]).glob("*.html"))
    except SystemExit:
        return None


def concept_folders(cfg: dict, c: dict, site: Path | None = None) -> list[str] | None:
    """The name of every folder capture.py makes for a concept under panel/materials: its pages
    (concept_pages()) and <page>@<state> for each state of a page it has. None when the source
    cannot be read yet. capture.py captures these and removes any other, and the plan holds a
    run back until each one is there (launch_plan.materials())."""
    pages = concept_pages(cfg, c, site)
    if pages is None:
        return None
    return pages + [f"{st.get('page', 'index')}@{st['name']}" for st in c.get("states", [])
                    if st.get("page", "index") in pages]


def source_problem(cfg: dict, c: dict) -> str | None:
    """Why a concept cannot be scaffolded or captured as its source stands, else None: a site
    folder with no index.html or with a page file whose name cannot name a folder, or what
    concept_items() says of a "files" concept. A url concept has no source to read."""
    kind = concept_kind(c)
    if kind == "site" and not (c["_path"] / "index.html").exists():
        return f"Concept {c['id']}: no index.html in {c['_path']}"
    if kind == "site":  # a page is captured to a folder named after its file: "...html" would be the folder above
        odd = sorted(p.name for p in c["_path"].glob("*.html") if name_problem(p.stem))
        if odd:
            return (f"Concept {c['id']}: the page file {json.dumps(odd[0])} in {c['_path']} cannot be captured, "
                    f"because its capture goes to a folder of that name, which {NAME_RULE}. Rename it")
    if kind == "files":
        try:
            concept_items(cfg, c)
        except SystemExit as err:
            return str(err)
    return None


def poppler_needed(cfg: dict) -> tuple[list[str], list[str]]:
    """(the Poppler tools capture.py needs for this study's PDFs, the ids of the concepts that
    have one): pdftotext for the text, and pdftoppm for the page images of a full-materials
    study. Both empty when no concept has a PDF that can be found."""
    with_pdf = []
    for c in cfg["concepts"]:
        if concept_kind(c) == "files":
            try:
                items = concept_items(cfg, c)[0]
            except SystemExit:
                continue
            if any(f.suffix.lower() in DOCUMENT_TYPES for _, f in items):
                with_pdf.append(c["id"])
    tools = ["pdftotext", *(["pdftoppm"] if cfg["materials"] == "full" else [])] if with_pdf else []
    return tools, with_pdf


def poppler_missing(cfg: dict) -> str | None:
    """What to tell the lead when the study has a PDF to capture and Poppler is not installed,
    else None."""
    tools, with_pdf = poppler_needed(cfg)
    missing = [t for t in tools if not shutil.which(t)]
    if not missing:
        return None
    return (f"Poppler is required for the {agree(len(with_pdf), 'PDF')} of {agree(len(with_pdf), 'concept')} "
            f"{', '.join(with_pdf)}: {' and '.join(missing)} {agree(len(missing), 'is', 'are')} not on PATH. "
            "Install Poppler (the package is poppler-utils on Debian and Ubuntu, poppler on Homebrew and Arch)")


KIND_NAMES = {"site": "site", "url": "live URL", "files": "files"}  # how the lead's files name a concept's kind


def read_forms(study_dir: Path) -> dict[str, str]:
    """The forms record, forms.json: {concept id: form} for the "files" concepts whose form was
    known when it was written. Empty when there is none, as in a study scaffolded before the
    record existed, and an entry that is not one of FILE_FORMS is left out."""
    try:
        held = json.loads((Path(study_dir) / FORMS).read_text())
    except (OSError, ValueError):
        return {}
    return {cid: form for cid, form in held.items() if form in FILE_FORMS} if isinstance(held, dict) else {}


def file_forms(cfg: dict) -> dict[str, str]:
    """{concept id: form} for each "files" concept whose form is known: "image files", "PDF
    files" or "image and PDF files", worked out from its source files (the images a text-only
    study leaves out among them), or taken from the forms record when they can no longer be read,
    as in an archived round or once the sources have moved."""
    recorded, forms = read_forms(cfg["_dir"]), {}
    for c in cfg["concepts"]:
        if concept_kind(c) != "files":
            continue
        try:
            kept, left_out = concept_items(cfg, c)
        except SystemExit:
            if c["id"] in recorded:
                forms[c["id"]] = recorded[c["id"]]
            continue
        pdf = {f.suffix.lower() in DOCUMENT_TYPES for f in [*(f for _, f in kept), *left_out]}
        forms[c["id"]] = " and ".join(["image"] * (False in pdf) + ["PDF"] * (True in pdf)) + " files"
    return forms


def write_forms(study_dir: Path, forms: dict[str, str]):
    """Write the forms record of a study directory, or of an archive of one: file_forms() as it
    stands. With no form to record the file is removed, so none outlives the concepts it was for.
    Lead only, like key.md: it sits beside study.json and never under panel/."""
    path = Path(study_dir) / FORMS
    if forms:
        write_atomic(path, json.dumps(forms, indent=2) + "\n")
    else:
        path.unlink(missing_ok=True)


def concept_forms(cfg: dict) -> dict[str, str]:
    """{label: the form the concept reached the panel in}, in label order: "site", "live URL", and
    for a "files" concept what file_forms() knows of it, "image files", "PDF files" or "image and
    PDF files" ("files" when neither its source nor the forms record can say). For the lead's
    files only: a panellist is never told what a concept is made of beyond what its folders show."""
    known = file_forms(cfg)
    return {label: known.get(c["id"], KIND_NAMES[concept_kind(c)]) if concept_kind(c) == "files"
            else KIND_NAMES[concept_kind(c)] for label, c in label_map(cfg).items()}


def mixed_forms(cfg: dict) -> dict[str, str] | None:
    """concept_forms() when the concepts did not all reach the panel in one form, else None. A
    site and a live URL are captured the same way, as sheets and page text, and count as one
    form. A PDF, an image and a captured page do not: a file cannot be scrolled or clicked and
    shows a phone only if it holds one, so part of any difference in score is the format. In a
    text-only study every concept reached the panel as text, and no factor that needs the design
    is scored, so it has one form."""
    forms = concept_forms(cfg)
    paged = (KIND_NAMES["site"], KIND_NAMES["url"])
    mixed = len({"pages" if form in paged else form for form in forms.values()}) > 1
    return forms if mixed and cfg["materials"] != "text" else None


def form_caution(cfg: dict) -> dict | None:
    """What the analysis and the briefs say of a study whose concepts differ in form
    (mixed_forms()), else None: "forms" (label -> form), "concepts", the same in a phrase ("A is
    a live URL and B is PDF files"), "factors", the labels of the scored factors that need the
    design ("needs_design"), which a format moves most, and "exposed", the clause that names them."""
    forms = mixed_forms(cfg)
    if not forms:
        return None
    named = [f"{label} is {'a ' if form in (KIND_NAMES['site'], KIND_NAMES['url']) else ''}{form}"
             for label, form in forms.items()]
    factors = [f["label"] for f in cfg["factors"] if needs_design(f)]
    listed = ", ".join(factors[:-1]) + (" and " if factors[:-1] else "") + (factors[-1] if factors else "")
    return {"forms": forms, "concepts": ", ".join(named[:-1]) + " and " + named[-1], "factors": factors,
            "exposed": (f"{listed} {agree(len(factors), 'is the factor', 'are the factors')} most exposed" if factors
                        else "Any score that turns on how a concept looks or behaves is exposed")}


def single_concept(cfg: dict) -> bool:
    """Whether the study has one concept: there is then nothing to rank or compare, so the
    templates ask for no ranking and no score summary, and the checks and analysis expect none."""
    return len(cfg["concepts"]) == 1


def study_brief_copy(study_dir: Path, files) -> Path | None:
    """The first of files that is the study brief or a copy of it, else None: a path named
    study-brief.md in any case, whether or not it exists, a path that resolves to the study's own
    brief (a link to it), or a file with the brief's content."""
    brief = Path(study_dir) / STUDY_BRIEF
    content = brief.read_bytes() if brief.is_file() else b""
    for f in map(Path, files):
        if f.name.lower() == STUDY_BRIEF or (brief.exists() and f.resolve() == brief.resolve()):
            return f
        if content.strip() and f.is_file() and f.stat().st_size == len(content) and f.read_bytes() == content:
            return f
    return None


def variants(cfg: dict) -> dict[str, str]:
    """{variant persona id: its parent's id}, in persona order, from each persona's "variant_of".

    A variant is its parent with one trait changed, written by the lead. It is a persona like
    any other, with its own runs and files, and it reviews in its parent's order (review_order):
    only analyze.py pairs it with its parent. Exits when a "variant_of" names no persona, the
    persona itself, or another variant.
    """
    found = {p["id"]: p["variant_of"] for p in cfg.get("personas") or [] if p.get("variant_of") is not None}
    ids = {p["id"] for p in cfg.get("personas") or []}
    for pid, parent in found.items():
        where = f'persona {pid}: "variant_of"'
        if parent == pid:
            _fail(f"{where} names the persona itself")
        if not isinstance(parent, str) or parent not in ids:
            _fail(f"{where} {json.dumps(parent)} is not a persona id (ids: {', '.join(sorted(ids))})")
        if parent in found:
            _fail(f"{where} names {parent}, which is itself a variant of {found[parent]}. Name the persona both "
                  "are variants of")
    return found


def needs_design(factor: dict) -> bool:
    """Whether a factor can only be judged by seeing the page: its "needs_design", or for a
    factor that does not say, whether its key is one of DESIGN_FACTORS."""
    return factor.get("needs_design", factor["key"] in DESIGN_FACTORS)


def apply_materials(cfg: dict, asked_to_browse: bool):
    """Make cfg what a "materials": "text" study runs with, and set cfg["_text_only"]: None for a
    full-materials study, else what was changed, for the plan to say.

    A text-only study scores no factor that needs the design, takes those factors out of
    "fit_factors" too, and never browses, whatever "browse" says. Every script takes its factors
    from cfg["factors"], so the templates, parsers, score columns and analysis follow.
    "_text_only" holds "dropped_factors" and "dropped_fit_factors" (factor keys), "fit_factors"
    (the ones in force: the default fit factors still scored when every one named was dropped) and
    "browse_ignored" (study.json says "browse": true).
    """
    for f in cfg["factors"]:
        if not isinstance(f.get("needs_design", False), bool):
            _fail(f'factor "{f["key"]}": "needs_design" must be true or false: whether the factor can only '
                  "be judged by seeing the page")
    cfg["_text_only"] = None
    if cfg["materials"] != "text":
        return
    dropped = [f["key"] for f in cfg["factors"] if needs_design(f)]
    if "overall" in dropped:
        _fail('the factor "overall" cannot have "needs_design": a text-only study would have no verdict to rank by')
    cfg["factors"] = [f for f in cfg["factors"] if f["key"] not in dropped]
    named = cfg["fit_factors"]
    fit = [k for k in named if k not in dropped]
    if named and not fit:
        fit = [k for k in DEFAULT_FIT_FACTORS if k in factor_keys(cfg)]
    cfg["_text_only"] = {"dropped_factors": dropped, "dropped_fit_factors": [k for k in named if k in dropped],
                         "fit_factors": fit, "browse_ignored": asked_to_browse}
    cfg["fit_factors"], cfg["browse"] = fit, False


def sites_dir(cfg: dict, used: bool = True) -> Path:
    """Where the neutral copies of the "site" concepts are: panel/sites in a study whose
    panellists browse, which is where a run opens a page from, and <study>/sites in every other.
    A copy is the page source under its own file names, and a run may read anything under
    panel/, so it is there only while the browser needs it. cfg["browse"] alone decides:
    load_study() has turned it off for a text-only study, for a "url" concept without "browse":
    true, and for a study of files alone. used=False gives the other of the two folders, where a
    scaffold made under the other setting left its copies: init_study.py clears it."""
    return cfg["_dir"] / ("panel/sites" if cfg["browse"] == used else "sites")


def factor_keys(cfg: dict) -> list[str]:
    return [f["key"] for f in cfg["factors"]]


def model_entry(raw, default_runner: str | None = None, where: str = "models") -> dict:
    """Normalise one model entry, a bare model name or an object, to {key, runner, model, effort}.

    runner None means native mode, model None the runner's default model, effort None unset.
    key is None when the entry gives none and its model name cannot stand in for one.
    """
    shown = json.dumps(raw)
    if isinstance(raw, str):
        raw = {"model": raw}
    if not isinstance(raw, dict):
        _fail(f"{where}: {shown} must be a model name or an object")
    if set(raw) - set(ENTRY_FIELDS):
        _fail(f"{where}: {shown} has unknown fields: {', '.join(sorted(set(raw) - set(ENTRY_FIELDS)))} "
              f"(use {', '.join(ENTRY_FIELDS)})")
    e = {f: raw.get(f) for f in ENTRY_FIELDS}
    for f, v in e.items():
        if v is not None and not (isinstance(v, str) and v):
            _fail(f'{where}: {shown}: "{f}" must be a non-empty string')
    if e["key"] is not None and not KEY_RE.fullmatch(e["key"]):
        _fail(f'{where}: {shown}: "key" must be letters and digits only, '
              "because file names and run ids split on hyphens")
    if e["key"] is None and e["model"] and KEY_RE.fullmatch(e["model"]):
        e["key"] = e["model"]
    e["runner"] = e["runner"] or default_runner
    return e


def model_entries(cfg: dict) -> list[dict]:
    """The study's model entries, normalised: one {key, runner, model, effort} per "models" item."""
    if not isinstance(cfg["models"], list) or not cfg["models"]:
        _fail('"models" must be a list with at least one entry')
    entries, seen = [], set()
    for raw in cfg["models"]:
        e = model_entry(raw, cfg.get("runner"))
        shown = json.dumps(raw)
        if e["key"] is None:
            fix = f': write it as {{"key": "<short name>", "model": {shown}}}' if isinstance(raw, str) else ""
            _fail(f'models: {shown} needs a "key" of letters and digits only, because its model name '
                  f"cannot be used in file names and run ids{fix}")
        if e["key"].lower() in seen:
            _fail(f'models: {shown} repeats the key "{e["key"]}". Keys must be unique within a study, '
                  "ignoring case, because they name files")
        if e["runner"] is None and e["model"] is None:
            _fail(f'models: {shown} needs a "model", or a "runner" whose default model it should use')
        seen.add(e["key"].lower())
        entries.append(e)
    native = [e["key"] for e in entries if e["runner"] is None]
    if native and len(native) < len(entries):
        _fail(f"models mix native entries ({', '.join(native)}) with runner entries "
              f"({', '.join(e['key'] for e in entries if e['runner'])}). A study is one or the other: "
              'set a study-level "runner", or give every entry one')
    return entries


def model_keys(cfg: dict) -> list[str]:
    return [e["key"] for e in model_entries(cfg)]


def limits_for(cfg: dict, role: str = "panellist", key: str | None = None) -> dict:
    """{"minutes", "budget_usd"} in force: limits.run for a panellist run, with that model key's
    limits.overrides merged over it; the job's share of limits.synthesis (synthesis_share) for
    an analyst or writer job; limits.followup for "followup", what each run asked a follow-up
    question may use for that question, apart from its run limits."""
    limits = cfg.get("limits") or {}
    if role == "followup":
        return {**DEFAULT_LIMITS["followup"], **limits.get("followup", {})}
    if role == "panellist":
        return {**DEFAULT_LIMITS["run"], **limits.get("run", {}), **limits.get("overrides", {}).get(key, {})}
    if role in JOB_ROLES:
        return synthesis_share(cfg)
    raise ValueError(f"unknown role {role!r}")


def synthesis_pool(cfg: dict) -> dict:
    """limits.synthesis in force, {"minutes", "budget_usd"}: "minutes" for each analyst or writer
    job, "budget_usd" one pool for all of them. Panellist runs never spend it."""
    return {**DEFAULT_LIMITS["synthesis"], **(cfg.get("limits") or {}).get("synthesis", {})}


def synthesis_share(cfg: dict) -> dict:
    """What one analyst or writer job may use over all its attempts, {"minutes", "budget_usd"}.

    The pool's budget is divided equally among the jobs study.json plans, the analysts and the
    writer, and each share is a cap. A share is rounded down to a millionth of a dollar, so the
    caps never add up to more than the pool. "minutes" is the pool's, for each job.
    """
    pool = synthesis_pool(cfg)
    jobs = (cfg.get("synthesis") or {}).get("analysts", 1) + 1
    return {"minutes": pool["minutes"], "budget_usd": math.floor(round(pool["budget_usd"] / jobs * 1e6, 3)) / 1e6}


def synthesis_jobs(cfg: dict) -> list[dict]:
    """The analyst and writer jobs study.json plans, each as its runs.json job entry before a
    launcher has touched it (fields in the module docstring).

    With two analysts the personas are split into halves in persona id order, the first taking
    the extra one, so each analyst reads every model and replicate of its personas. A single
    analyst writes analysis/qual-1.md too. A job whose synthesis.analyst or synthesis.writer
    entry is missing has no runner and no model: there is no default, and a launcher refuses it.
    """
    syn = cfg.get("synthesis") or {}
    n = syn.get("analysts", 1)
    ids = sorted((p["id"] for p in cfg["personas"]),
                 key=lambda pid: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", pid)])
    if len(ids) < n:
        _fail(f"synthesis.analysts is {n}, but the study has {len(ids)} persona(s) to split between them")
    cut = math.ceil(len(ids) / n)
    entry = {role: model_entry(syn[role], cfg.get("runner"), f"synthesis.{role}") if role in syn
             else dict.fromkeys(ENTRY_FIELDS) for role in JOB_ROLES}
    jobs = [{"run": f"analyst-{i}", "role": "analyst", "name": f"Analyst {i} of {n}", **entry["analyst"],
             "personas": own, "file": f"analysis/qual-{i}.md", "prompt": f"prompts/analyst-{i}.md"}
            for i, own in enumerate((ids[:cut], ids[cut:])[:n], start=1)]
    return [*jobs, {"run": "writer", "role": "writer", "name": "Synthesis writer", **entry["writer"],
                    "file": "analysis/SYNTHESIS.md", "prompt": "prompts/writer.md"}]


def runner_concurrency(cfg: dict, runner_name: str, default: int) -> int:
    return (cfg.get("runners") or {}).get(runner_name, {}).get("concurrency", default)


def make_labels(n: int, style: str) -> list[str]:
    if style == "numbers":
        return [f"{i + 1:02d}" for i in range(n)]
    if n > 26:
        raise SystemExit("More than 26 concepts: use label_style 'numbers'")
    return list(string.ascii_uppercase[:n])


def label_map(cfg: dict) -> dict[str, dict]:
    """Deterministic neutral label -> concept. Shuffled with the study seed unless disabled."""
    concepts = list(cfg["concepts"])
    if cfg.get("labels"):  # explicit {"A": "<concept id>"} mapping, e.g. to reproduce an earlier study
        by_id = {c["id"]: c for c in concepts}
        return {label: by_id[cid] for label, cid in cfg["labels"].items()}
    if cfg["shuffle_labels"]:
        random.Random(f"{cfg['seed']}:labels").shuffle(concepts)
    labels = make_labels(len(concepts), cfg["label_style"])
    return dict(zip(labels, concepts))


def review_order(cfg: dict, pid: str, labels: list[str]) -> list[str]:
    """Per-persona random order, identical across that persona's models and replicates. A
    variant reviews in its parent's order, so that order is no part of the difference between
    the two."""
    order = list(labels)
    random.Random(f"{cfg['seed']}:order:{variants(cfg).get(pid, pid)}").shuffle(order)
    return order


def shared_order(cfg: dict) -> str | None:
    """What to tell the lead when every persona reviews in the same order, else None. The seeded
    shuffle can land two or three personas on one order, and order is then confounded with
    concept: whatever is read first is always the same concept. A variant takes its parent's
    order on purpose, so variants are not counted, and one concept has no order."""
    labels, own = list(label_map(cfg)), [p["id"] for p in cfg["personas"] if p["id"] not in variants(cfg)]
    orders = {tuple(review_order(cfg, pid, labels)) for pid in own}
    if len(labels) < 2 or len(own) < 2 or len(orders) > 1:
        return None
    return (f"every persona reviews in the same order ({', '.join(orders.pop())}), so order is confounded with "
            "concept: the concept read first is the same for everyone, and the order effect in the analysis measures "
            f'nothing. Set another "seed" in study.json (it is {json.dumps(cfg["seed"])}) and scaffold again '
            "(init_study.py --force) before any run. A new seed reshuffles the labels too, unless study.json pins "
            "them.")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def persona_slug(p: dict) -> str:
    return p.get("slug") or slugify(p["name"])


def run_id(pid: str, key: str, replicate: int = 1) -> str:
    """<pid>-<key>, or <pid>-<key>-r<n> for replicate n > 1."""
    return f"{pid}-{key}" + (f"-r{replicate}" if replicate > 1 else "")


def persona_file(study_dir: Path, p: dict, key: str, replicate: int = 1) -> Path:
    name = f"{p['id']}-{persona_slug(p)}--{key}" + (f"-r{replicate}" if replicate > 1 else "")
    return Path(study_dir) / "panel" / "personas" / f"{name}.md"


def run_entry(study_dir: Path, p: dict, e: dict, replicate: int = 1) -> dict:
    """The runs.json entry of persona p on model entry e, before anything has started the run."""
    rid = run_id(p["id"], e["key"], replicate)
    return {"run": rid, "persona": p["id"], "name": p["name"], "segment": p.get("segment", ""), **e,
            "replicate": replicate, "role": "panellist",
            "file": str(persona_file(study_dir, p, e["key"], replicate).relative_to(study_dir)),
            "prompt": f"prompts/{rid}.md"}


def planned_runs(cfg: dict) -> list[dict]:
    """Every panellist run study.json plans, in the order init_study.py writes them to runs.json."""
    return [run_entry(cfg["_dir"], p, e, rep) for p in cfg["personas"] for e in model_entries(cfg)
            for rep in range(1, cfg["replicates"] + 1)]


def render_template(name: str, **values) -> str:
    return string.Template((ASSETS / name).read_text()).substitute(**values)


def fill_brief(name: str, values: dict) -> str:
    """An assets/ brief with every <PLACEHOLDER> token replaced by its value.

    The tokens stay in the asset as written, because a lead fills the same ones by hand in
    native mode. A token alone on its line takes the line with it when its value is empty.
    Exits naming every token the brief holds that values does not, so a brief is never sent
    with a placeholder left in it. <NOTICE> is the synthetic panel notice unless values says
    otherwise.
    """
    text, values = (ASSETS / name).read_text(), {"NOTICE": NOTICE, **values}
    unfilled = sorted(set(PLACEHOLDER.findall(text)) - set(values))
    if unfilled:
        raise SystemExit(f"assets/{name} has placeholders with no value to fill them: "
                         f"{', '.join(f'<{t}>' for t in unfilled)}. Take them out of the brief, or write their "
                         "text into it.")
    lines = []
    for line in text.split("\n"):
        alone = PLACEHOLDER.fullmatch(line.strip())
        if not (alone and not str(values[alone.group(1)])):
            lines.append(PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), line))
    return "\n".join(lines)


def with_notice(text: str) -> str:
    """Markdown text carrying the synthetic panel notice: unchanged when it has the line anywhere,
    else with the line as a paragraph of its own under the heading the text opens with, or at the
    very top when it opens with anything else."""
    if NOTICE in text:
        return text
    lines = text.split("\n")
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    at = first + 1 if first is not None and lines[first].startswith("#") else 0
    after = [] if at < len(lines) and not lines[at].strip() else [""]
    return "\n".join([*lines[:at], *([""] if at else []), NOTICE, *after, *lines[at:]])


def reply_document(text: str, start: str | None = None) -> str:
    """The document inside an agent's reply: everything from the first line matching the regex
    start (default: the first "# " heading), or the whole reply when no line matches, without
    the code fence a reply sometimes closes with."""
    lines = text.splitlines()
    pat = re.compile(start or r"^# ")
    first = next((i for i, line in enumerate(lines) if pat.search(line)), 0)
    return re.sub(r"\n```\s*$", "", "\n".join(lines[first:]).strip())


# ---------------------------------------------------------------- runs.json

def read_runs(study_dir: Path) -> list[dict]:
    """runs.json entries, with defaults filled for entries written before the newer fields."""
    path = Path(study_dir) / "runs.json"
    if not path.exists():
        raise SystemExit(f"No runs.json in {path.parent}: run init_study.py first")
    runs = json.loads(path.read_text())
    for r in runs:
        if r.get("role") in JOB_ROLES:  # written whole by launch.py, with none of a panellist run's fields
            continue
        r.setdefault("key", r.get("model"))
        for k, v in RUN_DEFAULTS.items():
            r.setdefault(k, v)
    return runs


def write_atomic(path: Path, text: str):
    """Replace a file in one step, so a reader or a killed writer never sees half of it."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def write_runs(study_dir: Path, runs: list[dict]):
    write_atomic(Path(study_dir) / "runs.json", json.dumps(runs, indent=2) + "\n")


def read_modifications(study_dir: Path) -> dict:
    """The modification record (module docstring): {"hashes", "changes"}, empty when no launcher
    has kept one for this study."""
    try:
        record = json.loads((Path(study_dir) / MODIFICATIONS).read_text())
    except (OSError, ValueError):
        record = {}
    return {"hashes": record.get("hashes") or {}, "changes": record.get("changes") or []}


def file_hash(path: Path) -> str | None:
    """SHA-256 of a file's content, None when there is no such file."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def workdir(study_dir: Path, role: str) -> Path:
    """The directory a run's or job's process works in: panel/ for a panellist, the study
    directory for an analyst or the writer."""
    return Path(study_dir) / "panel" if role == "panellist" else Path(study_dir)


def sessions_of(entry: dict) -> list[str]:
    """Every harness session id recorded for a run or job, over all its attempts."""
    ids = [entry.get("session"), *(a.get("session") for a in entry.get("attempts") or []),
           *(entry.get("sessions") or {})]
    return list(dict.fromkeys(i for i in ids if i and not i.startswith("attempt ")))


def held_sessions(study_dir: Path, runs: list[dict], now: float) -> list[dict]:
    """The sessions that runs.json entries record and that their harnesses still hold, neither
    purged nor lost, each as an entry of the earlier-sessions record (module docstring)."""
    return [{"run": e["run"], "runner": e["runner"], "session": session,
             "workdir": str(workdir(study_dir, e.get("role") or "panellist")), "replaced": round(now)}
            for e in runs if e.get("runner")
            for session in sessions_of(e) if session not in {**(e.get("purged") or {}), **(e.get("lost") or {})}]


def read_earlier_sessions(study_dir: Path) -> list[dict]:
    """The earlier-sessions record (module docstring): the sessions of runs that a --force
    replaced and that no purge-sessions has deleted since. Empty when there is none."""
    try:
        held = json.loads((Path(study_dir) / EARLIER_SESSIONS).read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(held, list):
        return []
    return [s for s in held if isinstance(s, dict) and s.get("run") and s.get("runner") and s.get("session")]


def write_earlier_sessions(study_dir: Path, held: list[dict]):
    """Replace the earlier-sessions record, or remove it when nothing is left to hold."""
    path = Path(study_dir) / EARLIER_SESSIONS
    if not held:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(exist_ok=True)
    write_atomic(path, json.dumps(held, indent=2) + "\n")


# ---------------------------------------------------------------- follow-ups

def read_followups(study_dir: Path) -> list[dict]:
    """followups.json (module docstring): the follow-up questions asked, oldest first. Empty when
    none was."""
    try:
        asked = json.loads((Path(study_dir) / FOLLOWUPS).read_text())
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as err:
        raise SystemExit(f"Cannot read {Path(study_dir) / FOLLOWUPS}: {err}")
    return asked if isinstance(asked, list) else []


def write_followups(study_dir: Path, asked: list[dict]):
    write_atomic(Path(study_dir) / FOLLOWUPS, json.dumps(asked, indent=2) + "\n")


def record_followup(study_dir: Path, n: int, run: str, **fields):
    """Set fields of one run's record under follow-up n in followups.json, adding the record, and
    the follow-up, when the file does not have them. settling=None takes "settling" out."""
    asked = read_followups(study_dir)
    followup = next((f for f in asked if f.get("n") == n), None)
    if followup is None:
        followup = {"n": n, "question": None, "asked": None, "mode": "runner", "runs": []}
        asked.append(followup)
    record = next((r for r in followup.setdefault("runs", []) if r.get("run") == run), None)
    if record is None:
        record = {"run": run, "outcome": None, "reason": None, "attempt": None, "session": None}
        followup["runs"].append(record)
    record.update(fields)
    if record.get("settling") is None:
        record.pop("settling", None)
    write_followups(study_dir, asked)


def asking(entry: dict) -> dict | None:
    """The attempt of a run that has a follow-up question out and is not settled yet, if there is
    one: the last attempt, of kind followup, with no end in runs.json. Its process may be at work
    or may have ended with no launcher alive to settle it. The run's "state" does not show it."""
    last = (entry.get("attempts") or [None])[-1]
    return last if last and last.get("kind") == "followup" and last.get("ended") is None else None


def copy_atomic(source: Path, dest: Path):
    """Make dest a copy of source in one step, as write_atomic() writes a text."""
    dest = Path(dest)
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
    shutil.copyfile(source, tmp)
    os.replace(tmp, dest)


def followup_section(n: int, question: str, answer: str, from_reply: bool = False) -> str:
    """A "## Follow-up <n>" section as a launcher writes one: the question quoted, then the
    answer. No line of either is left as a heading, because a heading would end the section and
    could pass for one of the run's own. from_reply marks it as taken from the panellist's reply."""
    def plain(text):
        return re.sub(r"^(\s*)#", r"\1\\#", text.strip(), flags=re.M)
    quoted = "\n".join(f"> {line}".rstrip() for line in plain(question).split("\n"))
    return "\n".join([f"## Follow-up {n}", "", quoted, "", plain(answer),
                      *(["", FROM_REPLY] if from_reply else []), ""])


def followup_change(cfg: dict, before: Path, after: Path, n: int) -> tuple[str, str]:
    """What follow-up n did to a persona file, from the copy made before the question (before)
    and the file now (after): (kind, why).

    "section": the file is the copy plus one appended section that opens with the heading
    "## Follow-up <n>", holds something under it and has no other "## " or "### " heading, and
    the scores, ranking, unit sections and progress parse as they did. That is all a follow-up
    may do. "none": nothing was added. "blank": the heading was added with nothing under it.
    "other": anything else, with why in a clause. White space at the very end of the copy is not
    held against the file, since an editor that appends may tidy it.
    """
    old = Path(before).read_text()
    try:
        new = Path(after).read_text()
    except OSError:
        return "other", "its persona file is gone"
    was, now = parse_persona_file(before, cfg), parse_persona_file(after, cfg)
    if not new.startswith(old.rstrip()):
        rescored = sorted(u for u in {*was["scores"], *now["scores"]}
                          if was["scores"].get(u) != now["scores"].get(u))
        return "other", (f"it changed the scores of {unit_nouns(cfg)[0]} {', '.join(rescored)}" if rescored
                         else "it changed its ranking" if was["ranking"] != now["ranking"]
                         else "it changed what was already in the file")
    added = new[len(old.rstrip()):].strip().split("\n")
    if added == [""]:
        return "none", ""
    if not re.fullmatch(rf"## Follow-up {n}\s*", added[0]):
        return "other", (f"what it appended does not open with the heading `## Follow-up {n}`: it opens "
                         f"`{added[0][:60]}`")
    extra = [line for line in added[1:] if line.startswith(("## ", "### "))]
    if extra:
        return "other", f"what it appended has a heading besides `## Follow-up {n}`: `{extra[0][:60]}`"
    if any(was[k] != now[k] for k in ("scores", "ranking", "sections", "duplicates", "unknown_labels", "has_final")):
        return "other", "it changed how the scores, ranking or sections of the file read"
    return ("section", "") if any(line.strip() for line in added[1:]) else ("blank", "")


def own_words(parsed: dict, questions: dict[int, str]) -> str:
    """A persona file's text without the researcher's follow-up questions: what the panellist
    itself wrote. parsed is parse_persona_file()'s result and questions maps a follow-up's
    number to its question as followups.json records it.

    A panellist quotes the question in its "## Follow-up <n>" section, so the lead's own words
    would otherwise be checked as the panellist's. The question is taken out of that section
    only, wherever it stands there word for word: line breaks, indents and block-quote marks may
    differ. A question the panellist reworded stays, and so does every answer.
    """
    text = parsed["text"]
    for f in parsed["followups"]:
        words = (questions.get(f["n"]) or "").split()
        if words:
            quoted = re.compile(r"(?:\s|>)+".join(map(re.escape, words)))
            text = text.replace(f["text"], quoted.sub("", f["text"]), 1)
    return text


# ---------------------------------------------------------------- parsing

NUM = re.compile(r"\d+(?:\.\d+)?")
FILE_RE = re.compile(r"^(?P<pid>[^-]+)-(?P<slug>.+)--(?P<model>[^-]+)(?:-r(?P<rep>[1-9]\d*))?\.md$")


def unit_nouns(cfg: dict) -> tuple[str, str]:
    """Singular and plural of what a run in this study works through: concept(s) or task(s)."""
    t = STUDY_TYPES[cfg["type"]]
    return t["unit"], t["units"]


def study_units(cfg: dict) -> list[str]:
    """The units every run must cover, in section-heading form: the concept labels of a review."""
    if cfg["type"] == "usability":
        raise SystemExit('study.json: "type": "usability" is not supported yet')
    return list(label_map(cfg))


def parse_persona_file(path: Path, cfg: dict, text: str | None = None) -> dict:
    """Parse one run file. Returns scores per unit, ranking, order, and structural problems.

    "model" is the model key and "replicate" the replicate number, both from the file name;
    "run" is the run id they make with the persona id. "followups" lists the file's follow-up
    sections in file order, each {"n", "text"}: the number in its "## Follow-up <n>" heading and
    the section from that heading to the next "## " heading. Nothing else here reads them.

    text is the file's content when it is not to be read from path, which then only names the
    run. A reader of scores or progress calls read_persona(), which decides that.
    """
    path = Path(path)
    labels, n_factors = study_units(cfg), len(cfg["factors"])
    heading = STUDY_TYPES[cfg["type"]]["heading"]
    m = FILE_RE.match(path.name)
    if text is None:
        text = path.read_text()
    lines = text.split("\n")
    replicate = int(m["rep"] or 1) if m else 1
    out = {
        "file": path.name, "pid": m["pid"] if m else path.stem, "model": m["model"] if m else "",
        "replicate": replicate, "run": run_id(m["pid"], m["model"], replicate) if m else path.stem,
        "slug": m["slug"] if m else "", "scores": {}, "sections": {}, "ranking": [], "order": [],
        "unknown_labels": [], "duplicates": [], "missing_scores": [], "has_final": FINAL_MARKER in text,
        "text": text, "followups": [],
    }
    label_set = set(labels)
    for i, line in enumerate(lines):
        mf = FOLLOWUP_HEADING.match(line)
        if mf:
            end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
            out["followups"].append({"n": int(mf.group(1)), "text": "\n".join(lines[i:end]).rstrip()})
    for line in lines:
        mo = re.match(r"^\|\s*Review order\s*\|\s*(.+?)\s*\|\s*$", line)
        if mo:
            out["order"] = [x.strip() for x in mo.group(1).split(",") if x.strip()]
            break
    for i, line in enumerate(lines):
        mc = re.match(rf"^###\s+{heading}\s+([A-Za-z0-9]+)\b", line)
        if not mc:
            continue
        label = mc.group(1)
        if label not in label_set:
            out["unknown_labels"].append(label)
            continue
        if label in out["sections"]:
            out["duplicates"].append(label)
        end = next((j for j in range(i + 1, len(lines))
                    if lines[j].startswith("### ") or lines[j].startswith("## ")), len(lines))
        out["sections"][label] = "\n".join(lines[i:end])
        for j in range(i + 1, end):
            cells = [c.strip().strip("*") for c in lines[j].strip().strip("|").split("|")]
            if len(cells) == n_factors and all(NUM.fullmatch(c) for c in cells):
                out["scores"][label] = [float(c) for c in cells]
                break
    out["missing_scores"] = [lab for lab in out["sections"] if lab not in out["scores"]]
    in_rank = False
    for line in lines:
        if re.match(r"^#{2,4}\s+My ranking", line):
            in_rank = True
            continue
        if in_rank and line.startswith("#"):
            break
        if in_rank:
            mr = re.match(r"^\s*\d+[.)]\s*\**\s*Concept\s+([A-Za-z0-9]+)", line)
            if mr and mr.group(1) in label_set and mr.group(1) not in out["ranking"]:
                out["ranking"].append(mr.group(1))
    return out


# ---------------------------------------------------------------- answers and lines

# What extract_answers.py reads from a unit section: the fields init_study.py's concept_template
# asks for, each known by the opening words of its label. The template is built from these, so a
# label changed here changes there too, and files written under the old label stop parsing. The
# parsers never guess: an entry that is not written the way its rule below says comes back as
# "unparsed" with its text, and one left out as "missing".
FIELD_LABELS = {
    "answers": "Could I find the answer",       # one bullet per find_the_answer question
    "keep": "One line to keep",
    "cut": "One line to cut",
    "not_believed": "One line I don't believe",
    "forward": "Would I forward it",
    # Not tallied. Listed so that a field ends where the next one starts.
    "pages": "Pages I looked at", "take": "5-second take", "real_life": "What I'd do in real life",
    "worked": "What worked for me", "put_off": "What confused", "questions": "Questions it left me with",
    "explain": "Explain it back", "quote": "Quote (my gut reaction",
}
LINE_FIELDS = ("keep", "cut", "not_believed")
ANSWERS_HINT = "For each question"  # how the template's own instruction under the answers label starts
VERDICTS = {"found": "Found", "partly": "Partly", "partially": "Partly", "not found": "Not found"}

_ITEM = r"(?:[-*+]|\d+[.)])\s+"
_FIELD = {key: re.compile(rf"^\s*(?:{_ITEM})?(?P<bold>\*\*|__)?\s*" + re.escape(label).replace("'", "['\u2019]")
                          + r"(?P<rest>.*)$", re.I) for key, label in FIELD_LABELS.items()}
_BULLET = re.compile(rf"^(\s*){_ITEM}")
_MARKUP = re.compile(r"\*\*|__|`")
_STRAIGHT = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})
_VERDICT = re.compile(r"(not\s+found|found|partly|partially)\b", re.I)
_AFTER_VERDICT = re.compile(r"[\s,/;-]*(?:(?:and|or|but|to)\s+)?(not\s+found|found|partly|partially|nothing|none"
                            r"|no|neither|zero)\b", re.I)
_NONE = re.compile(r"(none|nothing|n/a)\b", re.I)
# Where the recipient of a forward ends and the message is announced: ", with the message", "and a
# short note", ", saying". "message" is the template's own word for what goes with the page.
_MESSAGE_NEXT = r",?\s+(?:with|and)\s+(?:the|a|this|my|one)\s+(?:[\w-]+\s+)?(?:message|note)\b|,\s+saying\b"
_RECIPIENT = re.compile(r"[\s,.:;-]*(?i:to)\s+((?:(?i:my|our|the|an?|one|two|three|four|five|some|any|anyone|"
                        r"everyone|another|other|every|all|both|his|her|their|that|this|those|these|whoever)\b"
                        r"|[A-Z])[^:\"]*?)(?=\s*(?::|\.(?:\s|$)|\"|$)|(?i:" + _MESSAGE_NEXT + "))")
_STOPWORDS = frozenset("a already an and any are at be can do does each for how i in is it many me much my of on "
                       "or our per that the there this to we what which who will with would you your".split())


def _straight(text: str) -> str:
    """Curly quotes and apostrophes made straight. One character for one, so positions hold."""
    return text.translate(_STRAIGHT)


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def section_fields(section: str) -> dict[str, list[str]]:
    """The lines of each template field in a unit section, keyed as FIELD_LABELS.

    A field starts at the line that opens with its label, through a bullet marker and bold, and
    its first line is what follows the label on that line. It runs to the next label, table row
    or heading. When a section repeats a label the first field stands.
    """
    fields, current = {}, None
    for line in section.split("\n")[1:]:
        key, m = next(((k, m) for k, m in ((k, pat.match(line)) for k, pat in _FIELD.items()) if m), (None, None))
        if m:
            rest = m["rest"]
            close = rest.find(m["bold"]) if m["bold"] else -1
            end = re.search(r"[:?]", rest)
            value = rest[close + 2:] if close >= 0 else rest[end.end():] if end else rest
            current = None if key in fields else fields.setdefault(key, [value.lstrip(" :")])
        elif line.lstrip().startswith(("|", "#")):
            current = None
        elif current is not None:
            current.append(line)
    return fields


def _field_text(lines: list[str] | None) -> str:
    """A one-line field's text: its first paragraph, cut where a bullet or a bold label starts."""
    text = []
    for line in lines or []:
        if text and (not line.strip() or _BULLET.match(line) or line.lstrip().startswith(("**", "__"))):
            break
        if line.strip():
            text.append(line)
    return _one_line(" ".join(text))


def read_verdict(text: str) -> tuple[str | None, str]:
    """(verdict, where it was found) from an answer with its question taken off, or (None, "").

    Only an answer that starts with Found, Partly, Partially or Not found counts, in any case.
    One that goes straight on to another verdict or to a denial ("Found, partly", "Found nothing")
    is ambiguous and does not count; "Partly found" is Partly. A later sentence may qualify the
    verdict without changing it.
    """
    text = text.lstrip(" \t:*_-")
    m = _VERDICT.match(text)
    if not m:
        return None, ""
    verdict, rest = VERDICTS[" ".join(m[1].lower().split())], text[m.end():]
    more = _AFTER_VERDICT.match(rest)
    if more:
        word = " ".join(more[1].lower().split())
        if (verdict, word) == ("Partly", "found"):
            rest = rest[more.end():]
        elif verdict == "Found" or (word in VERDICTS and VERDICTS[word] != verdict):
            return None, ""
    return verdict, rest.strip().lstrip(",;:.-").strip()


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", _straight(text).casefold().replace("'", ""))
            if w not in _STOPWORDS]


def _overlap(words: list[str], others: list[str]) -> float:
    """The share of words that are in others, taking "month" and "monthly" as one word."""
    def same(a, b):
        n = len(os.path.commonprefix([a, b]))
        return a == b or (n >= 4 and n >= min(len(a), len(b)) - 1)
    return sum(any(same(w, o) for o in others) for w in words) / len(words) if words else 0.0


def _answer_items(lines: list[str]) -> list[str]:
    """The entries of an answers field: its top-level bullets, each with the lines and nested
    bullets under it folded in, or its lines when it has no bullet. The template's own
    instruction is no entry."""
    marks = [m for m in map(_BULLET.match, lines) if m]
    if not marks:
        return [t for t in map(_one_line, lines) if t and not t.startswith(ANSWERS_HINT)]
    top = min(len(m[1]) for m in marks)
    items = []
    for line in lines:
        m = _BULLET.match(line)
        if m and len(m[1]) == top:
            items.append(line[m.end():])
        elif items and line.strip():
            items[-1] += " " + (line[m.end():] if m else line)
    return [_one_line(t) for t in items]


def parse_answers(section: str, questions: list[str]) -> list[dict]:
    """A unit section's answer to each find_the_answer question, in question order.

    Each is {"verdict", "where", "raw"}: verdict is Found, Partly or Not found (read_verdict),
    "missing" when the panellist gave the question no answer, or "unparsed"; where is what
    followed the verdict; raw is the entry as written, "" when missing.

    An entry belongs to a question when it starts with the question's text or with "Q<n>"; or,
    when the panellist reworded the question, when the words before its first colon or question
    mark point at one question only: either some of them are that question's and the entry sits
    at its position among as many entries as questions, or most of them (0.6) are. An entry that
    starts with its verdict takes the question at its position, when there are as many entries as
    questions. An entry that fits no question leaves every question without one "unparsed", as
    does a question two entries claim.
    """
    def blank(verdict, raw=""):
        return {"verdict": verdict, "where": "", "raw": raw}

    lines = section_fields(section).get("answers")
    if lines is None:
        return [blank("missing") for _ in questions]
    items = _answer_items(lines)
    aligned = len(items) == len(questions)
    asked = [re.compile(r"\s*" + r"\s+".join(map(re.escape, _straight(_MARKUP.sub("", q)).strip(" ?:.").split()))
                        + r"(?!\w)\s*[?:.]*", re.I) for q in questions]
    q_words = [_words(q) for q in questions]
    claims, loose = {}, {}  # question index -> [(entry, its answer)]; entry index -> entry that fits none
    for i, item in enumerate(items):
        text = _one_line(_MARKUP.sub("", item))
        flat = _straight(text)
        q, answer = None, text
        starts = [(m.end(), j) for j, m in enumerate(rx.match(flat) for rx in asked) if m]
        if starts:
            end, q = max(starts)
            answer = text[end:]
        elif _VERDICT.match(flat.lstrip(" \t:*_-")):
            q = i if aligned else None
        else:
            cut = re.search(r"[:?](?=\s|$)", flat)
            label, answer = (text[:cut.start()], text[cut.end():]) if cut else (text, "")
            number = re.fullmatch(r"(?:q|question)\s*#?(\d+)", label.strip(), re.I)
            if number:
                q = int(number[1]) - 1 if 0 < int(number[1]) <= len(questions) else None
            else:
                score = [_overlap(_words(label), w) for w in q_words]
                best = max(score, default=0)
                if best > 0 and score.count(best) == 1 and ((aligned and score.index(best) == i) or best >= 0.6):
                    q = score.index(best)
        if q is None:
            loose[i] = item
        else:
            claims.setdefault(q, []).append((item, answer))
    out = []
    for j in range(len(questions)):
        got = claims.get(j, [])
        if len(got) == 1:
            item, answer = got[0]
            verdict, where = read_verdict(answer)
            if verdict:
                out.append({"verdict": verdict, "where": where, "raw": item})
            else:
                out.append(blank("unparsed", item) if answer.strip(" .:*_-") else blank("missing"))
        elif got:
            out.append(blank("unparsed", " / ".join(item for item, _ in got)))
        elif loose:
            out.append(blank("unparsed", loose[j] if aligned and j in loose else " / ".join(loose.values())))
        else:
            out.append(blank("missing"))
    return out


def read_line(value: str) -> dict:
    """One "line to keep", "to cut" or "I don't believe" field: {"status", "text", "to", "note"}.

    quoted: the field opens with a line in double quotes, straight or curly. text is the line,
    note what the panellist added after it. Further quotes outside brackets make it "unparsed":
    two lines, or a line with quotes inside it, and which is not for this script to say.
    none: the panellist wrote none, nothing or n/a, quoted or not. unquoted: anything else, kept
    whole in text. missing: empty, or the template's "..." left in place.
    """
    def entry(status, text="", note=""):
        return {"status": status, "text": text, "to": "", "note": note}

    v = _one_line(_MARKUP.sub("", value))
    flat = _straight(v)
    if not flat.strip(' ."'):
        return entry("missing")
    if flat.startswith('"'):
        end = flat.find('"', 1)
        if end < 0 or '"' in re.sub(r"\([^)]*\)", "", flat[end + 1:]):
            return entry("unparsed")
        text, note = v[1:end].strip(), v[end + 1:].strip()
        if not text.strip(" ."):
            return entry("missing")
        return entry("none", note=note) if _NONE.fullmatch(text.rstrip(" .")) else entry("quoted", text, note)
    m = _NONE.match(flat)
    if m and flat[m.end():].lstrip()[:1] in ("", *".,;:("):
        return entry("none", note=v[m.end():].lstrip(" .,;:"))
    return entry("unquoted", v)


def read_forward(value: str) -> dict:
    """The "Would I forward it?" field: {"status", "text", "to", "note"}.

    status is yes, no or maybe when the answer starts with that word, else "unparsed" (so "Not
    yet" and "yes/no" are), or "missing". to is who it would go to, read only where "to" and a
    person follow the answer directly ("Yes, to my bookkeeper: ..."), and never for a no. It
    ends at a colon, a full stop or a quotation mark, or sooner where the answer announces the
    message ("to a client who asked, with the message: ..." gives "a client who asked"). text
    is the message: the one passage in double quotes, "" when there is none or more than one.
    """
    v = _one_line(_MARKUP.sub("", value))
    flat = _straight(v)
    out = {"status": "missing", "text": "", "to": "", "note": ""}
    if not flat.strip(" .*_"):
        return out
    m = re.match(r"(yes|no|maybe)\b(?!\s*(?:/|(?:and|or)\s+(?:yes|no)\b))", flat, re.I)
    if not m:
        return {**out, "status": "unparsed"}
    out["status"] = m[1].lower()
    who = _RECIPIENT.match(flat, m.end()) if out["status"] != "no" else None
    if who:
        out["to"] = v[who.start(1):who.end(1)]
    quoted = list(re.finditer(r'"([^"]+)"', flat))
    if len(quoted) == 1:
        out["text"] = v[quoted[0].start(1):quoted[0].end(1)].strip()
    return out


def parse_lines(section: str) -> dict[str, dict]:
    """A unit section's keep, cut, not_believed and forward entries (read_line, read_forward),
    each with "raw": the field as written, on one line."""
    fields = section_fields(section)
    out = {}
    for key in (*LINE_FIELDS, "forward"):
        raw = _field_text(fields.get(key))
        out[key] = {**(read_forward if key == "forward" else read_line)(raw), "raw": raw}
    return out


def same_line(text: str) -> str:
    """A quoted line reduced to what makes two quotations of it the same: straight quotes, single
    spaces, no case and no closing full stop."""
    return _one_line(_straight(text)).casefold().rstrip(".").strip()


def personas_dir(study_dir: Path) -> Path:
    """panel/personas in a live study; personas/ in an archived round (archive.py flattens panel/)."""
    live = Path(study_dir) / "panel" / "personas"
    return live if live.is_dir() else Path(study_dir) / "personas"


def run_progress(cfg: dict, parsed: dict | None) -> dict:
    """How far a run has got, from its parsed persona file (None when it has no file yet).

    units: every unit the study expects; written: those with a section; scored: those with a
    score row; has_final: the final marker is present. A run is complete, for every study type,
    when every unit is scored and the final marker is present. Nothing else decides "done".
    """
    units = study_units(cfg)
    sections, scores = (parsed["sections"], parsed["scores"]) if parsed else ({}, {})
    scored = [u for u in units if u in scores]
    has_final = bool(parsed and parsed["has_final"])
    return {"units": units, "written": [u for u in units if u in sections], "scored": scored,
            "has_final": has_final, "complete": has_final and len(scored) == len(units)}


def run_state(progress: dict, recorded: str | None = None, ended: dict | None = None) -> str:
    """A run's lifecycle state, from its run_progress() and the "state" its runs.json entry records.

    The persona file decides whether a run is done: a complete file is "done" whatever was
    recorded and however its process ended, and an incomplete one never is.

    ended is given by a launcher when a process has just ended, and then decides the state of
    an incomplete run, first match first: {"limit": true} (the launcher stopped it at a run
    limit) or {"outcome": "budget"} (the harness's spend cap did) is "limited";
    {"outcome": "usage_limit"} is "blocked"; {"stopped": true} (the stop command) is "partial"
    with a section written and "pending" with none; anything else is "partial" with a section
    written and "failed" with none.

    Without ended the recorded state stands (pending, running, partial, limited, blocked or
    failed), except that "pending" and "failed" mean nothing is written: with a section on
    file they read as "partial", so nothing ever launches such a run afresh. With none
    recorded, or "done" recorded for an incomplete file, the state is "partial" when at least
    one unit section is written and "pending" when none is.
    """
    if progress["complete"]:
        return "done"
    some = "partial" if progress["written"] else None
    if ended is not None:
        if ended.get("limit") or ended.get("outcome") == "budget":
            return "limited"
        if ended.get("outcome") == "usage_limit":
            return "blocked"
        return some or ("pending" if ended.get("stopped") else "failed")
    if recorded in ("running", "partial", "limited", "blocked"):
        return recorded
    return some or (recorded if recorded == "failed" else "pending")


UNSETTLED = "a follow-up is unsettled, so its file was read as it stood before the question"
LOOKS = 5  # how many times read_persona() chooses and reads while the run's attempts change under it


def _attempts(entry: dict | None) -> list:
    return (entry or {}).get("attempts") or []


def _entry_now(study_dir: Path, path: Path, entry: dict | None, run: str | None) -> dict | None:
    """A run's entry as runs.json has it at this moment, None when it has none: the entry of the
    run id, or without one the entry whose persona file has path's name (an archive moves the
    file). With no runs.json, or one that cannot be read, entry stands: there is no later word."""
    try:
        runs = json.loads((study_dir / "runs.json").read_text())
    except (OSError, ValueError):
        return entry
    for e in runs if isinstance(runs, list) else []:
        if isinstance(e, dict) and (e.get("run") == run if run else Path(e.get("file") or "").name == path.name):
            return e
    return None


def read_persona(study_dir: Path, cfg: dict, path: Path, entry: dict | None = None) -> dict | None:
    """A run's persona file as its scores, answers and progress stand: parse_persona_file() with
    "unsettled" added, or None when the run has no file. The one place that chooses what to read.

    path is the persona file and entry the run's runs.json entry, when it has one. For a run
    whose latest follow-up attempt is not settled (asking()), the copy made before the question
    is read in place of the file, and "unsettled" is true: the file may hold what settling will
    reject and put back (the snapshot rule, module docstring). The copy is in logs/, which only
    a live study has, and it is there until the attempt's end is in runs.json. Without one the
    file itself is read.

    entry is only the first word on the run: the caller read it some time ago, and a follow-up
    may have started or been settled since. So once the content is read, the run's attempts are
    read again from runs.json, and when they are not the ones the choice was made from (an
    attempt was added, ended or taken back), the choice and the read are made again from the
    newer ones, until two looks one after the other agree. A launcher has the copy on disk and
    the attempt in runs.json before it starts the process that may change the file, and puts
    the file right before it writes the attempt's end, so content read between two looks that
    agree is never what a follow-up has yet to have settled. An archive has no logs/, and a
    study with no runs.json has no attempts: there the file is read as it is.

    After LOOKS reads with no two looks in agreement, nothing read from the file is returned: it
    may be what a follow-up left before it was put back. The newest copy still on disk of a
    follow-up attempt of the run is returned in its place, with "unsettled" true as for any
    copy. Any such copy will do, because a launcher makes one in a single step, under the study
    lock, of a file no follow-up has unsettled: the review and the sections of the follow-ups
    accepted before it, which is also what a rejected follow-up is put back to. So its scores
    and ranking are the review's own, and at worst it lacks a later follow-up's section. With
    no copy on disk the read is refused: the script exits, saying to run it again.
    """
    study_dir, path = Path(study_dir), Path(path)
    run = entry["run"] if entry else None

    def copy(e, attempt):
        try:
            return (study_dir / "logs" / f"{e['run']}.{attempt['n']}.before").read_text()
        except OSError:  # an archive, or settled since runs.json was read
            return None

    for _ in range(LOOKS):
        attempt = asking(entry or {})
        before = copy(entry, attempt) if attempt else None
        try:
            text = path.read_text() if before is None else before
        except OSError:  # the run has no file
            text = None
        now = _entry_now(study_dir, path, entry, run)
        steady = _attempts(now) == _attempts(entry)
        entry = now
        if steady:
            break
    else:  # never the same attempts twice: a copy is the file before a question, whatever happened since
        copies = (copy(entry, a) for a in reversed(_attempts(entry)) if a.get("kind") == "followup")
        text = before = next((c for c in copies if c is not None), before)
        if before is None:  # what was read from the file may be what a follow-up left: it is not returned
            raise SystemExit(
                f"Follow-up questions to {(entry or {}).get('run') or run or path.stem} kept starting and settling "
                f"while its persona file {path} was being read, so nothing was read from it: run the command "
                f"again once they have finished (launch.py {study_dir} status shows them).")
    return None if text is None else {**parse_persona_file(path, cfg, text), "unsettled": before is not None}


def unsettled_lines(runs: list[dict]) -> list[str]:
    """One line for each run that was read from the copy made before an unsettled follow-up, for
    the script that read it to print. runs are read_persona() results or run_records() records."""
    return [f"{r['run']}: {UNSETTLED}" for r in runs if r.get("unsettled")]


def load_runs(study_dir: Path, cfg: dict) -> list[dict]:
    """Every persona file in the study, parsed (read_persona()). For the runs.json entries, see
    read_runs()."""
    study_dir = Path(study_dir)
    seg = {p["id"]: p.get("segment", "") for p in cfg["personas"]}
    entries = {}  # persona file name -> its run's entry: an archive moves the file, so match it by name
    if (study_dir / "runs.json").exists():
        entries = {Path(e["file"]).name: e for e in read_runs(study_dir) if e["role"] == "panellist"}
    folder = personas_dir(study_dir)
    names = {p.name for p in folder.glob("*--*.md")} | {name for name, e in entries.items() if asking(e)}
    runs = []
    for name in sorted(names):
        r = read_persona(study_dir, cfg, folder / name, entries.get(name))
        if r:
            r["segment"] = seg.get(r["pid"], "")
            runs.append(r)
    return runs


def run_records(study_dir: Path, cfg: dict) -> list[dict]:
    """Every expected panellist run, with how far it got. Works on live and archived studies.

    Expected runs are the panellist entries of runs.json, then any persona file no entry names;
    without a runs.json, the persona files found. Each record has "run", "pid", "model" (the
    model key), "replicate", "segment", "parsed" (parse_persona_file's result, None when the run
    has no file), "progress" (run_progress), "state" (run_state) and "unsettled" (whether the
    file was read as it stood before a follow-up that is not settled: read_persona()).
    """
    study_dir = Path(study_dir)
    seg = {p["id"]: p.get("segment", "") for p in cfg["personas"]}
    files = {r["file"]: r for r in load_runs(study_dir, cfg)}
    found = []  # (pid, key, replicate, run id, recorded state, parsed file)
    if (study_dir / "runs.json").exists():
        for e in read_runs(study_dir):
            if e["role"] == "panellist":  # an archive moves the file, so match it by name
                found.append((e["persona"], e["key"], e["replicate"], e["run"], e.get("state"),
                              files.pop(Path(e["file"]).name, None)))
    found += [(r["pid"], r["model"], r["replicate"], r["run"], None, r) for r in files.values()]
    out = []
    for pid, key, replicate, run, recorded, parsed in found:
        prog = run_progress(cfg, parsed)
        out.append({"run": run, "pid": pid, "model": key, "replicate": replicate, "segment": seg.get(pid, ""),
                    "parsed": parsed, "progress": prog, "state": run_state(prog, recorded),
                    "unsettled": bool(parsed and parsed["unsettled"])})
    return out


# ---------------------------------------------------------------- stats

def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else float("nan")


def sd(xs):
    xs = [x for x in xs if x is not None]
    return statistics.stdev(xs) if len(xs) > 1 else 0.0


def ranks(values: list[float]) -> list[float]:
    """Average ranks, 1 = smallest."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(x: list[float], y: list[float]) -> float:
    if len(x) < 3:
        return float("nan")
    mx, my = mean(x), mean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def spearman(x: list[float], y: list[float]) -> float:
    return pearson(ranks(x), ranks(y))


def fmt(x, nd=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    return f"{x:.{nd}f}"


# ---------------------------------------------------------------- browser

# Expands collapsed content and forces common scroll-reveal patterns visible, so captured
# text and screenshots show what a reader who scrolled and clicked would see.
REVEAL_JS = (
    "document.querySelectorAll('details').forEach(d=>d.open=true);"
    "document.querySelectorAll('[aria-expanded=\"false\"]').forEach(b=>{try{b.click()}catch(e){}});"
    "document.querySelectorAll('.reveal,[data-reveal],[data-animate],.fade-in,.animate-in')"
    ".forEach(e=>{e.classList.add('is-visible','in','visible','revealed','in-view');"
    "e.style.opacity='1';e.style.transform='none';});1"
)


def which_montage() -> list[str]:
    if shutil.which("magick"):
        return ["magick", "montage"]
    if shutil.which("montage"):
        return ["montage"]
    raise SystemExit("ImageMagick is required (magick or montage on PATH)")


def which_convert() -> list[str]:
    if shutil.which("magick"):
        return ["magick"]
    if shutil.which("convert"):
        return ["convert"]
    raise SystemExit("ImageMagick is required (magick or convert on PATH)")


class Browser:
    """Thin wrapper over the agent-browser CLI with one named session."""

    def __init__(self, session: str):
        if not shutil.which("agent-browser"):
            raise SystemExit("agent-browser CLI is required")
        self.session = re.sub(r"[^A-Za-z0-9_-]", "-", session)

    def run(self, *args: str, check: bool = False) -> str:
        r = subprocess.run(["agent-browser", "--session", self.session, *args],
                           capture_output=True, text=True, timeout=180)
        if check and r.returncode != 0:
            raise RuntimeError(f"agent-browser {' '.join(args)}: {r.stderr.strip()}")
        return r.stdout.strip()

    def eval(self, js: str) -> str:
        out = self.run("eval", js)
        try:
            return json.loads(out)
        except (json.JSONDecodeError, ValueError):
            return out

    def open(self, url: str, width: int, height: int, settle_ms: int = 2500, media: str = ""):
        self.run("set", "viewport", str(width), str(height))
        if media:  # e.g. "light" or "light reduced-motion": stops captures landing mid-animation
            self.run("set", "media", *media.split())
        self.run("open", url, check=True)
        self.run("wait", str(settle_ms))

    def scroll_height(self) -> int:
        v = self.eval("document.documentElement.scrollHeight")
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0

    def close(self):
        self.run("close")
