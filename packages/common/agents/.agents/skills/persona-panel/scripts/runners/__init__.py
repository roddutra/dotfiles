"""Runners: one module per harness, adapting that harness's headless CLI to one interface.

Everything the skill knows about a harness lives in this package. No other script names a
harness, a flag, an environment variable, an output format or a session path; the launcher and
the plan step learn all of it through the functions below. Adding a harness is adding one module
here: the registry lists the package's modules, so nothing else changes. A module whose name
starts with "_" is not a runner.

Registry and helpers (this file):

    names() -> list[str]            the runners available
    get(name) -> module             the runner, or exit with a message listing names()
    check_effort(entry) -> dict     whether a model entry's effort can be launched on its runner
    launch_effort(run, levels)      the effort a runner passes, refusing a level it does not have
    merge_usage(recorded, usage)    one session's usage after another result
    total_usage(sessions)           a run's usage, summed over its sessions
    usage(), result(), json_lines(), last_line(), exited(), run_cli()   building blocks for runner modules

Every runner module exposes these six functions.

capabilities() -> dict
    images_by_path       bool: a panellist can open an image file by path during the run
    image_attach         bool: the harness can attach images at launch. It says what the
                         harness can do: no runner attaches one yet, and nothing reads it
    browser              bool: a panellist can drive the agent-browser CLI and keep its session
                         between commands
    budget_cap           bool: the harness enforces a spend cap
    budget_cap_note      str: how far a run can go past an enforced cap, in plain words, as a
                         clause that starts "the budget cap". "" when the cap is exact, or
                         when there is none. The plan step prints it beside the ceiling
    effort_levels        list[str]: thinking efforts accepted, empty when there is no such setting
    resume               bool: a session can be continued
    purge                bool: a session can be deleted by id
    usage                {"tokens", "cost", "duration"}: which of them the harness reports
    default_concurrency  int: runs to keep going at once when study.json sets no figure
    provider             str: who receives the materials
    billing_env          list[str]: environment variables that, when set, can change who is
                         billed. The plan step reports any that are set
    isolation_gaps       list[str]: what the runner could not switch off for any run or job, in
                         plain English. The plan step prints them
    browse_gaps          list[str]: what it could not switch off only for a run that may browse
                         ("browse" true), in the same words. Empty when "browser" is false. The
                         plan step prints them when the study's runs can browse on this runner

launch_command(run, prompt, workdir, limits) -> dict
resume_command(run, session_id, message, workdir, limits) -> dict
    run      a runs.json entry (see panel_lib): "model" (None = the harness default), "effort"
             (None = unset), "role" and "browse" (may this run use agent-browser; missing = no)
    prompt, message   delivered verbatim. A runner adds nothing
    workdir  the directory the process starts in, and the only place it may write: panel/ for
             a panellist, the study directory for an analyst or the writer. The caller starts
             the process with this as its working directory
    limits   {"minutes", "budget_usd"}: what is left of the run's allowance for this attempt.
             A runner passes budget_usd to a harness that has a cap; the caller enforces minutes
    Returns {"argv": list, "stdin": str or None, "env": dict or None, "session_id": str or None}.
    "env" is the complete environment for the child process, None meaning unchanged.
    "session_id" is set when the runner knows the id before the process starts, so a run killed
    before it prints anything can still be resumed. Resume repeats every launch setting, because
    no harness tried so far inherits the working directory, the tools or the budget.
    Both raise ValueError for an effort the harness does not have, and for a budget of zero or
    less: validate with check_effort() and stop a spent run before asking for a command.

parse_result(stdout, stderr, exit_code) -> dict
    session_id  str or None
    reply       the final assistant text, None unless the outcome is "ok"
    usage       see below
    outcome     "ok", "usage_limit" (the harness is turning requests away: a usage limit, a
                rate limit or a capacity refusal, so try again later), "budget" (the
                harness's spend cap stopped the run) or "error"
    reset_at    epoch seconds when a usage limit lifts, None when the harness did not say
    message     the reason for a non-ok outcome, in the CLI's own words where it gave any.
                The caller prints it, so it is what tells a capacity refusal from a limit
    session_lost  bool: the CLI refused a resume because the session it named is gone. The
                outcome is "error". The caller then treats the session as it does a purged one,
                and does not take the process for a CLI that could not be started
    Never raises on missing, cut-off or half-written output. A process killed at its time limit
    leaves no closing line: that parses as "error" with whatever session id and usage came out,
    and the caller, which knows it sent the signal, records the run as limited.
    "ok" means the harness finished its turn. Whether the run is done is the persona file's call.

check() -> {"ok": bool, "message": str}
    Whether the CLI is installed, signed in and still accepts the options the runner passes,
    without a model call. On failure the message carries the CLI's own words.

purge_command(session_id, workdir) -> list or None
    The argv that deletes one session, or None when it cannot be deleted.

Usage. {"input_tokens", "output_tokens", "cached_tokens", "cost_usd", "duration_s", "scope"},
None for anything not reported. input_tokens counts all input including the cached part,
cached_tokens is the part read from a cache, and output_tokens includes thinking. "scope" says
what the token and cost figures cover: "session" when they are running totals for the whole
session, earlier resumes and killed processes included, or "process" when they cover this
process alone. Tokens and cost in one result always share one scope. duration_s is the wall
time of this process as the harness reports it, whatever the scope; the caller's own clock is
what enforces a time limit. Both runners so far report "session".

Totalling a run without double counting: keep one usage per session id and fold each result in
with merge_usage(), which replaces a session-scoped figure and adds a process-scoped one. A run
that was restarted has several sessions; total_usage() sums them. The budget left for a run's
next attempt is its cap minus total_usage(...)["cost_usd"]. That figure lacks the spend of a
process that was killed before it reported any: the caller marks such an attempt, and a
session-scoped result from the same session brings the spend in.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
import subprocess

INTERFACE = ("capabilities", "launch_command", "resume_command", "parse_result", "check", "purge_command")
OUTCOMES = ("ok", "usage_limit", "budget", "error")
USAGE_FIELDS = ("input_tokens", "output_tokens", "cached_tokens", "cost_usd", "duration_s")


# ---------------------------------------------------------------- registry

def names() -> list[str]:
    return sorted(m.name for m in pkgutil.iter_modules(__path__) if not m.name.startswith("_"))


def get(name: str):
    """The runner module called name. Exits naming the available runners when there is none."""
    if name not in names():
        raise SystemExit(f'Unknown runner "{name}". Available runners: {", ".join(names())}')
    module = importlib.import_module(f"{__name__}.{name}")
    missing = [f for f in INTERFACE if not callable(getattr(module, f, None))]
    if missing:
        raise SystemExit(f'Runner "{name}" is incomplete: it lacks {", ".join(missing)}')
    return module


def check_effort(entry: dict) -> dict:
    """Whether a model entry's (or a run's) thinking effort can be launched on its runner.

    Returns {"effort", "error", "note"}. "effort" is the level to launch with, None for the
    harness default. "error" is set when the harness has effort levels and this is not one of
    them: refuse to launch, because the CLIs themselves only warn or fail at the first model
    call. "note" is set when the harness has no effort setting at all: the run proceeds
    without it and the plan step says so.
    """
    effort, levels = entry.get("effort"), get(entry["runner"]).capabilities()["effort_levels"]
    out = {"effort": None, "error": None, "note": None}
    if effort is None or effort in levels:
        out["effort"] = effort
    elif levels:
        out["error"] = f'{entry["runner"]} has no effort "{effort}" (use {", ".join(levels)})'
    else:
        out["note"] = f'{entry["runner"]} has no thinking effort setting, so "{effort}" is ignored'
    return out


def launch_effort(run: dict, levels: list[str]) -> str | None:
    """The effort a runner passes for run: its "effort", or None when unset or unsupported."""
    effort = run.get("effort")
    if effort is None or not levels:
        return None
    if effort not in levels:
        raise ValueError(f'effort "{effort}" is not one of {", ".join(levels)}')
    return effort


# ---------------------------------------------------------------- usage and results

def usage(scope: str = "session", **figures) -> dict:
    return {**dict.fromkeys(USAGE_FIELDS), **figures, "scope": scope}


def result(outcome: str = "error", **fields) -> dict:
    """A parse_result() return value with every key present."""
    return {"session_id": None, "reply": None, "usage": usage(), "outcome": outcome,
            "reset_at": None, "message": "", "session_lost": False, **fields}


def merge_usage(recorded: dict | None, new: dict) -> dict:
    """One session's usage after another result from that session, as session totals.

    A session-scoped token or cost figure replaces the recorded one, a process-scoped one is
    added to it, and duration_s always adds. A figure the new result lacks keeps its recorded
    value, so a killed process that reported nothing loses nothing.
    """
    out = usage(**{f: (recorded or {}).get(f) for f in USAGE_FIELDS})
    for f in USAGE_FIELDS:
        if new.get(f) is None:
            continue
        adds = f == "duration_s" or new.get("scope") == "process"
        out[f] = new[f] + (out[f] or 0) if adds else new[f]
    return out


def total_usage(sessions: list[dict]) -> dict:
    """A run's usage over all its sessions (each from merge_usage). None where none reported."""
    out = dict.fromkeys(USAGE_FIELDS)
    for f in USAGE_FIELDS:
        figures = [s[f] for s in sessions if s.get(f) is not None]
        out[f] = sum(figures) if figures else None
    return out


# ---------------------------------------------------------------- for runner modules

def json_lines(text) -> list[dict]:
    """The objects in a stream of JSON lines. Blank, non-JSON and half-written lines are
    skipped (a killed process leaves them), and a line holding a list contributes its objects."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line.startswith(("{", "[")):
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        out += [x for x in (value if isinstance(value, list) else [value]) if isinstance(x, dict)]
    return out


def last_line(text) -> str:
    """The last non-blank line of a CLI's stderr, where its own error message sits."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def exited(exit_code) -> str:
    """How a process ended, for a message: its exit code, which nothing recorded when it is None."""
    return "exit code unknown" if exit_code is None else f"exit code {exit_code}"


def run_cli(argv: list[str], env: dict | None = None, timeout: int = 30):
    """Run one of a CLI's own status commands with no input. Returns (exit code, stdout,
    stderr), or None when the executable is not on PATH."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env,
                           stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        return None
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", f"{' '.join(argv[:3])}: {e}"
    return r.returncode, r.stdout.strip(), r.stderr.strip()
