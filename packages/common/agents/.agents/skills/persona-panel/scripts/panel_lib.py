"""Shared helpers for the persona-panel scripts: study config, runs.json, and persona-file parsing.

Standard library only. Every script takes a study directory laid out as:

    <study>/study.json        lead config (never shown to panellists)
    <study>/key.md            neutral label -> concept key (lead only)
    <study>/runs.json         one entry per run (schema below)
    <study>/prompts/          one run prompt per run, <run id>.md, and one filled brief per analyst
                              and writer job, <job id>.md
    <study>/panel/            the only folder panellists may read
        _panel-instructions.md
        sites/concept-<L>/    neutral copies of each concept
        materials/concept-<L>/<page>/
        personas/<pid>-<slug>--<key>.md, or ...--<key>-r<n>.md for replicate n > 1
        scratch/<run id>/
    <study>/analysis/         scores.csv, rankings.csv, runs.csv, quant.md, quant.json, checks.md,
                              lead-notes.md (the lead's), qual-<n>.md (one per analyst), SYNTHESIS.md
                              (the writer's) and, from launch.py, <job id>-reply.md and usage.md
                              (what each harness reported: per run, per model key, per role and
                              in total)
    <study>/logs/             launch.py only: <run id>.<attempt>.in, .out and .err, the input and
                              output of each CLI process it started; .pid, where the attempt's
                              watchdog records itself and the CLI before the CLI runs; .end, the
                              end record the watchdog writes when the attempt has ended (both
                              formats in run_watchdog.py); and modifications.json (the
                              modification record, below). A process that never ran as the CLI
                              is no attempt: its files stay until the next attempt, which has
                              the same number, replaces them
    <study>/.launch.lock      launch.py only: present while a launcher has the study

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
                  resume, or restart for a fresh launch made by the resume command), "started"
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
                  as the CLI can be taken back
    seconds_used  wall-clock seconds over every attempt. With the reported spend it counts
                  against the run's limits, which cover all its attempts
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
    {"key": "visual", "label": "Visual design", "short": "Visual",
     "question": "Does it look professional, calm and credible, or busy, gimmicky or cheap?"},
    {"key": "structure", "label": "Structure and flow", "short": "Structure",
     "question": "Is it easy to scan and follow, the right length, with things where I expect them?"},
    {"key": "mobile", "label": "Mobile", "short": "Mobile",
     "question": "Judged from the phone screens: would it work if I opened it on my phone?"},
    {"key": "next_step", "label": "Next step", "short": "Next step",
     "question": "How likely am I to book a demo, sign up or pass it on?"},
    {"key": "overall", "label": "Overall", "short": "Overall",
     "question": "Your overall verdict. It doesn't have to be the average of the other scores."},
]

DEFAULT_FIT_FACTORS = ["relevance", "why_care", "next_step"]
DASHES = ("\u2013", "\u2014")
FINAL_MARKER = "## Out of character"

# Study type -> the unit a run works through: its nouns, and its section heading in a persona file.
STUDY_TYPES = {
    "review": {"unit": "concept", "units": "concepts", "heading": "Concept"},
    "usability": {"unit": "task", "units": "tasks", "heading": "Task"},
}
MATERIALS = ("full", "text")
ENTRY_FIELDS = ("key", "runner", "model", "effort")
KEY_RE = re.compile(r"[A-Za-z0-9]+")
LIMIT_NAMES = ("minutes", "budget_usd")
DEFAULT_LIMITS = {
    "run": {"minutes": 15, "budget_usd": 2.0},        # each panellist run, over all its attempts
    "synthesis": {"minutes": 30, "budget_usd": 5.0},  # analyst and writer jobs
}
RUN_DEFAULTS = {"runner": None, "effort": None, "replicate": 1, "role": "panellist"}
JOB_ROLES = ("analyst", "writer")
SYNTHESIS_KEYS = ("analysts", "analyst", "writer", "decision_maker", "context_files")
DEFAULT_DECISION_MAKER = "the decision-maker"
MODIFICATIONS = "logs/modifications.json"  # the modification record, relative to the study directory
PLACEHOLDER = re.compile(r"<([A-Z][A-Z0-9_]*)>")


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
    cfg.setdefault("browse", True)
    cfg.setdefault("artefact_plural", "draft website designs")
    for k in ("limits", "runners", "synthesis"):
        cfg.setdefault(k, {})
    cfg.setdefault("concepts", [])
    cfg["_dir"] = study_dir
    check_study(cfg)
    for c in cfg["concepts"]:
        p = Path(c["path"]).expanduser()
        c["_path"] = (p if p.is_absolute() else study_dir / p).resolve()
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
    if cfg["type"] == "review" and not cfg["concepts"]:
        _fail("a review study needs at least one concept")
    keys = model_keys(cfg)

    limits = cfg["limits"]
    if not isinstance(limits, dict) or set(limits) - {"run", "synthesis", "overrides"}:
        _fail('"limits" must be an object with any of run, synthesis and overrides')
    sets = {f"limits.{k}": limits[k] for k in ("run", "synthesis") if k in limits}
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
    an analyst or writer job."""
    limits = cfg.get("limits") or {}
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
    """Per-persona random order, identical across that persona's models and replicates."""
    order = list(labels)
    random.Random(f"{cfg['seed']}:order:{pid}").shuffle(order)
    return order


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
    with a placeholder left in it.
    """
    text = (ASSETS / name).read_text()
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


def parse_persona_file(path: Path, cfg: dict) -> dict:
    """Parse one run file. Returns scores per unit, ranking, order, and structural problems.

    "model" is the model key and "replicate" the replicate number, both from the file name;
    "run" is the run id they make with the persona id.
    """
    path = Path(path)
    labels, n_factors = study_units(cfg), len(cfg["factors"])
    heading = STUDY_TYPES[cfg["type"]]["heading"]
    m = FILE_RE.match(path.name)
    text = path.read_text()
    lines = text.split("\n")
    replicate = int(m["rep"] or 1) if m else 1
    out = {
        "file": path.name, "pid": m["pid"] if m else path.stem, "model": m["model"] if m else "",
        "replicate": replicate, "run": run_id(m["pid"], m["model"], replicate) if m else path.stem,
        "slug": m["slug"] if m else "", "scores": {}, "sections": {}, "ranking": [], "order": [],
        "unknown_labels": [], "duplicates": [], "missing_scores": [], "has_final": FINAL_MARKER in text,
        "dash_count": sum(text.count(d) for d in DASHES), "text": text,
    }
    label_set = set(labels)
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


def load_runs(study_dir: Path, cfg: dict) -> list[dict]:
    """Every persona file in the study, parsed. For the runs.json entries, see read_runs()."""
    seg = {p["id"]: p.get("segment", "") for p in cfg["personas"]}
    runs = []
    for p in sorted(personas_dir(study_dir).glob("*--*.md")):
        r = parse_persona_file(p, cfg)
        r["segment"] = seg.get(r["pid"], "")
        runs.append(r)
    return runs


def run_records(study_dir: Path, cfg: dict) -> list[dict]:
    """Every expected panellist run, with how far it got. Works on live and archived studies.

    Expected runs are the panellist entries of runs.json, then any persona file no entry names;
    without a runs.json, the persona files found. Each record has "run", "pid", "model" (the
    model key), "replicate", "segment", "parsed" (parse_persona_file's result, None when the run
    has no file), "progress" (run_progress) and "state" (run_state).
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
                    "parsed": parsed, "progress": prog, "state": run_state(prog, recorded)})
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
