"""Runner for the Codex headless CLI, `codex exec`.

Every flag and format below was checked against codex-cli 0.162.1 with a ChatGPT plan login on
12 October 2026. "Verified" means seen in a real run, "inferred" means read from the help
text, the binary's strings or old session files.

Launch (the prompt goes to stdin; `-C` sets the working directory, so the directory the
process itself starts in does not matter):

    codex exec --json --skip-git-repo-check --ignore-user-config --ignore-rules
      -c project_doc_max_bytes=0 -c skills.include_instructions=false -c approval_policy=never
      --disable plugins --disable tool_suggest
      -s workspace-write -C <workdir> [-m <model>] [-c model_reasoning_effort=<level>] -

Resume is the same options followed by `resume <thread id> -`. A bare `codex exec resume <id>`
inherits nothing: it runs read-only, in the process's own directory, on the default model, and
reloads the skills list. So every option is repeated, and placed before the word `resume`,
because `-C` and `-s` are rejected after it.

What each option is for (all verified unless marked):

- `-` as the prompt: read it from stdin. With a prompt argument instead, the CLI waits for
  stdin to close and appends it to the prompt.
- `--json`: one event per line on stdout (formats under Results).
- `--skip-git-repo-check`: required outside a git repository, harmless inside one.
- `--ignore-user-config`: skips the user's config.toml, so none of its MCP servers start and
  its session hook does not run. The login keeps working, the approval policy becomes
  `never` and the effort falls back to the model's default.
- `--ignore-rules`: skips the user's execpolicy rule files, which can pre-approve commands
  (inferred from the help text; its effect was not observed).
- `-c project_doc_max_bytes=0`: no AGENTS.md from the git root down to the working directory.
- `-c skills.include_instructions=false`: removes the skills list, about 40,000 characters
  that `--ignore-user-config` leaves in, project skills included.
- `-c approval_policy=never`: a refused command fails straight back to the model, so nothing
  waits for an approval. Already the value under `--ignore-user-config`; set to pin it
  (checked to parse, not run in the validation launch).
- `--disable plugins --disable tool_suggest`: removes the recommended-plugins block.
- `-s workspace-write`: the sandbox. Writes are allowed in the working directory and /tmp,
  the network is off, and the whole disk stays readable.
- `-m`: omitted when the run names no model, which leaves the CLI's default (the first model
  of the account's list). An unknown model fails at the first API call, exit code 1.
- `-c model_reasoning_effort=low|medium|high|xhigh|max`: an invalid level also fails only at
  the API, so the level is validated here and a bad one raises. Only low and medium were run.

Decisions this runner implements:

- CODEX_HOME is never pointed elsewhere and auth.json is never copied or linked: the skill
  does not read, store or relay a provider login. So the user's global ~/.codex/AGENTS.md
  cannot be kept out, which capabilities() lists as an isolation gap. The environment is
  passed through unchanged.
- No budget cap. The only stop found, `features.rollout_budget`, is under development and
  writes a budget notice into the model's context. The caller's time limit bounds a run.
- No browser. Each shell call gets its own process namespace, so the agent-browser daemon
  dies between calls and the next command starts a blank browser. A run with "browse" true
  still launches, without the network and socket settings browsing would need.
- Images are opened by path (the `view_image` tool, which works in the sandbox). `-i` can
  attach images at launch, which is what "image_attach" reports, but is not used: it is
  variadic and would swallow the `-`.

Results. Session id: `thread_id` on the first line, `thread.started`, printed before any model
call and again on resume. Reply: the text of the last `item.completed` whose item type is
`agent_message`; earlier ones are progress notes. An item of type `error` is a warning, not a
failure. A turn ends in `turn.completed` (exit code 0) or in an `error` event followed by
`turn.failed` (exit code 1), and FAILURES below sorts the failure message into an outcome.
With neither, the process was killed (exit code 143, no closing event) or never started (not
a trusted directory, unknown thread id, empty prompt: exit code 1, message on stderr only).
A resume of a thread whose session file is gone ends that way with `Error: thread/resume:
thread/resume failed: no rollout found for thread id <id> (code -32600)` (verified, also after
the file was removed by hand): that is "session_lost".

Usage, scope "session": `turn.completed.usage` is the running total for the whole thread,
resumes included, so the latest figure replaces earlier ones. `input_tokens` already counts
the cached part. There is no cost figure and no duration. When stdout has no usage (a killed
or failed turn), the totals are read from the last `token_count` event of the session file,
`$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<time>-<thread id>.jsonl`. That file is an internal
format, read best effort; after a kill it can miss the request that was in flight. The same
event carries the plan's limit windows, which is where a usage limit's reset time comes from.

Sessions are deleted with the CLI's own `codex delete --force <thread id>`, which removes the
session file and its database rows.

Not settled: the real output at a usage limit; a network rule narrower than all or nothing;
how to remove the sub-agent blocks; whether the trust entry can be prevented.
"""

from __future__ import annotations

import glob
import json
import os
import re

from . import exited, json_lines, last_line, launch_effort, model_facts, result, run_cli, usage

CLI = "codex"
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
ISOLATION = ["--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
             "-c", "project_doc_max_bytes=0", "-c", "skills.include_instructions=false",
             "-c", "approval_policy=never", "--disable", "plugins", "--disable", "tool_suggest"]
BILLING_ENV = ["OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "CODEX_HOME"]  # INFERRED: names in the binary

# What a turn.failed message means: (text it contains, outcome, whether the plan's reset time
# applies). The first match wins and anything else is an error. No limit could be triggered,
# so only the event shape (error, then turn.failed, exit code 1) is verified.
FAILURES = [
    ("usage limit", "usage_limit", True),         # INFERRED: "You've hit your usage limit. ..." in the binary
    ("rate limit", "usage_limit", False),         # INFERRED
    ("exceeded retry limit", "usage_limit", False),  # INFERRED: how repeated 429s end
    ("at capacity", "usage_limit", False),        # verified: a real run was refused this way and ended blocked
    ("rollout token budget exhausted", "budget", False),  # verified, but needs a feature this runner never enables
]
SESSION_LOST = "no rollout found for thread id"  # verified: in the stderr line of a resume whose session is gone
UUID = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def capabilities() -> dict:
    return {
        "images_by_path": True,
        "image_attach": True,
        "browser": False,
        "budget_cap": False,
        "budget_cap_note": "",
        "effort_levels": list(EFFORTS),
        "resume": True,
        "purge": True,
        "usage": {"tokens": True, "cost": False, "duration": False},
        "default_concurrency": 4,
        "provider": "OpenAI",
        "billing_env": list(BILLING_ENV),
        "isolation_gaps": [
            "The user's global instruction file (~/.codex/AGENTS.md) is always loaded, because "
            "keeping it out would mean moving the login.",
            "The whole disk is readable from the sandbox, the home directory included. Only "
            "writes are confined.",
            "/tmp is writable as well as the working directory.",
            "The working directory path, the shell, the date and the timezone are always in the "
            "model's context.",
            "Sub-agent tools and their instructions stay available.",
            "Commands run in a login shell that sources the user's shell profile.",
            "A run inside a git repository adds a trust entry for that repository to the "
            "user's Codex config.toml.",
        ],
        "browse_gaps": [],  # no run browses on this runner
    }


def _options(run: dict, workdir) -> list[str]:
    argv = [CLI, "exec", "--json", *ISOLATION, "-s", "workspace-write", "-C", os.path.abspath(workdir)]
    if run.get("model"):
        argv += ["-m", run["model"]]
    effort = launch_effort(run, EFFORTS)
    if effort:
        argv += ["-c", f"model_reasoning_effort={effort}"]
    return argv


def launch_command(run: dict, prompt: str, workdir, limits: dict | None) -> dict:
    return {"argv": [*_options(run, workdir), "-"], "stdin": prompt, "env": None, "session_id": None}


def resume_command(run: dict, session_id: str, message: str, workdir, limits: dict | None) -> dict:
    if not UUID.fullmatch(session_id or ""):
        raise ValueError(f"not a thread id: {session_id!r}")
    return {"argv": [*_options(run, workdir), "resume", session_id, "-"], "stdin": message,
            "env": None, "session_id": session_id}


def _usage(reported) -> dict:
    if not isinstance(reported, dict):
        return usage()
    return usage(input_tokens=reported.get("input_tokens"), output_tokens=reported.get("output_tokens"),
                 cached_tokens=reported.get("cached_input_tokens"))


def _token_count(session_id) -> dict:
    """The session's last token_count event, from its session file. {} when there is none."""
    if not UUID.fullmatch(session_id or ""):
        return {}
    home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    pattern = os.path.join(glob.escape(home), "sessions", "*", "*", "*", f"rollout-*-{session_id}.jsonl")
    last = {}
    for path in glob.glob(pattern):
        try:
            with open(path, errors="replace") as f:
                for line in f:
                    for event in json_lines(line) if '"token_count"' in line else []:
                        payload = event.get("payload")
                        if isinstance(payload, dict) and payload.get("type") == "token_count":
                            last = payload
        except OSError:
            pass
    return last


def _dig(value, *keys):
    for k in keys:
        value = value.get(k) if isinstance(value, dict) else None
    return value


def _reason(message) -> str:
    """The API's own sentence, when the CLI passes its JSON error object through as text."""
    try:
        inner = _dig(json.loads(message), "error", "message")
    except (TypeError, ValueError):
        inner = None
    return inner if isinstance(inner, str) else str(message or "")


def parse_result(stdout, stderr, exit_code, session_id=None) -> dict:
    lines = json_lines(stdout)
    out = result(session_id=next((x["thread_id"] for x in lines if x.get("type") == "thread.started"
                                  and isinstance(x.get("thread_id"), str)), None))
    end = next((x for x in reversed(lines) if x.get("type") in ("turn.completed", "turn.failed")), None)
    reported = next((x.get("usage") for x in reversed(lines) if x.get("type") == "turn.completed"), None)
    resets = False
    if isinstance(reported, dict):
        out["usage"] = _usage(reported)
    if end is None:
        out["message"] = last_line(stderr) or f"{CLI} ended before finishing its turn ({exited(exit_code)})"
        out["session_lost"] = SESSION_LOST in out["message"]
    elif end["type"] == "turn.completed":
        messages = [_dig(x, "item", "text") for x in lines
                    if x.get("type") == "item.completed" and _dig(x, "item", "type") == "agent_message"]
        out.update(outcome="ok", reply=next((m for m in reversed(messages) if isinstance(m, str)), None))
    else:
        out["message"] = _reason(_dig(end, "error", "message")) or f"{CLI} failed its turn ({exited(exit_code)})"
        _, outcome, resets = next((f for f in FAILURES if f[0] in out["message"].lower()), ("", "error", False))
        out["outcome"] = outcome
    if end is None or end["type"] == "turn.failed":
        tail = _token_count(out["session_id"])
        if not isinstance(reported, dict):
            out["usage"] = _usage(_dig(tail, "info", "total_token_usage"))
        reset = _dig(tail, "rate_limits", "primary", "resets_at")
        if resets and isinstance(reset, (int, float)):
            out["reset_at"] = reset
    return out


def check() -> dict:
    """Installed, signed in, and every launch option still parses. No model call: the last step
    adds --help to the launch options, which the CLI prints only once the options are accepted."""
    version = run_cli([CLI, "--version"])
    if version is None:
        return {"ok": False, "message": f"The {CLI} CLI is not on PATH"}
    if version[0] != 0:
        return {"ok": False, "message": version[2] or version[1] or f"{CLI} --version failed"}
    code, out, err = run_cli([CLI, "login", "status"]) or (1, "", "")
    said = last_line(err) or last_line(out)  # the answer is the last line: warnings can come before it
    if code != 0:
        return {"ok": False, "message": said or f"{CLI} login status failed"}
    probe = run_cli([*_options({"model": "default", "effort": EFFORTS[0]}, "."), "--help"]) or (1, "", "")
    if probe[0] != 0:
        return {"ok": False, "message": next((x for x in probe[2].splitlines() if x.strip()), "")
                or f"{CLI} refused the launch options"}
    return {"ok": True, "message": f"{version[1]}, {said}"}


def model_status(entry: dict) -> dict:
    """Nothing is known of one model without a call to it, so the answers for the whole CLI
    stand: every model reads images, and check() covers the login. An unknown model fails at the first API call."""
    return model_facts(images=capabilities()["images_by_path"])


def purge_command(session_id: str, workdir) -> list | None:
    return [CLI, "delete", "--force", session_id] if UUID.fullmatch(session_id or "") else None
