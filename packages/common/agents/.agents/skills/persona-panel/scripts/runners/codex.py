"""Runner for the Codex headless CLI, `codex exec`.

Every flag and format below was checked against codex-cli 0.162.1 with a ChatGPT plan login on
12 October 2026. "Verified" means seen in a real run, "inferred" means read from the help
text, the binary's strings or old session files.

Launch (the prompt goes to stdin; `-C` sets the working directory, so the directory the
process itself starts in does not matter):

    codex exec --json --skip-git-repo-check --ignore-user-config --ignore-rules
      -c project_doc_max_bytes=0 -c skills.include_instructions=false -c approval_policy=never
      --disable plugins --disable tool_suggest
      --disable apps -c web_search="disabled" --disable image_generation
      -s workspace-write [-c sandbox_workspace_write.network_access=true
      -c sandbox_workspace_write.exclude_slash_tmp=true
      -c sandbox_workspace_write.exclude_tmpdir_env_var=true]
      [--disable shell_tool --disable unified_exec --disable view_image --disable multi_agent
      --disable sleep_tool --disable browser_use --disable computer_use --disable goals]
      -C <workdir> [-m <model>] [-c model_reasoning_effort=<level>] -

The three sandbox settings are there only for a run that may browse (see "Browsing"), and the
eight `--disable` switches of the last group only for a run with "tools": "none" (see "No
tools").

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
- `--disable apps -c web_search="disabled" --disable image_generation`: no tool of the
  signed-in account's connected apps, no web search and no image generation (see "What was open
  until 13 October 2026").
- `-s workspace-write`: the sandbox. Writes are allowed in the working directory and /tmp,
  the network is off, and the whole disk stays readable. A run that may browse gets the
  network and loses /tmp (see "Browsing" under the decisions).
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
- Browsing (run["browse"]), checked on 13 October 2026. A run cannot keep a browser of its
  own: each shell call is a process namespace of its own, and whatever it started dies when
  the call returns (verified, also with setsid and nohup). So the caller starts the
  agent-browser session outside the sandbox, and the run reaches it through its socket.
  - `-c sandbox_workspace_write.network_access=true`: with the network off the sandbox refuses
    to connect to a Unix socket at all (`Operation not permitted`). Worse, a command that
    cannot reach its session takes it for stale and deletes its socket files, which cuts the
    session off for good (verified). The page loads happen in the session, outside: the run
    needs the network for the socket alone, and gets all of it, which "browse_gaps" states.
  - `-c sandbox_workspace_write.exclude_slash_tmp=true` and `exclude_tmpdir_env_var=true`: the
    temporary directories, where the session's socket directory is, become read-only. A run
    then cannot start a session of its own there, so dropping the session's policy from a
    command ends its browsing instead of freeing it (verified: `Socket directory ... is not
    writable`). The working directory stays writable, also when it is under /tmp.
  - The environment is the caller's with run["browser_env"] applied (child_env()). Codex
    passes those variables on to the shell (verified).
- Images are opened by path (the `view_image` tool, which works in the sandbox). `-i` can
  attach images at launch, which is what "image_attach" reports, but is not used: it is
  variadic and would swallow the `-`.
- The built-in instructions (Codex's default system prompt) are kept on purpose, decided 13
  October 2026. `-c model_instructions_file=<absolute path>` would replace them, repeated
  before `resume` on every resume. The key is undocumented and an unknown `-c` key is ignored
  without a message, so a renamed key would restore the default unnoticed. The record is
  "System prompt override" in docs/specs/persona-panel-expansion.md.

What was open until 13 October 2026. Every run and job this runner started, of every study
type, had three things its options did not show: the tools of the apps connected to the
signed-in ChatGPT account, web search and image generation. `--ignore-user-config` does not
touch them: they come from the account and the CLI's defaults, not from config.toml. Found and
closed on 13 October 2026 with codex-cli 0.162.1, by asking a session for the tool list of its
own script runtime (`ALL_TOOLS` inside the `exec` tool), which is the CLI's list and not the
model's account of it (verified):

- With the options as they stood: 293 tools. The shell, `apply_patch`, `view_image`, an image
  generation tool, the goal tools, a `web` search tool, and about 280 tools named `mcp__...`,
  one for each action of each app the account had connected. A panellist could have searched
  the web for the product under review, or called a connected app.
- With `--disable apps`: no `mcp__` tool is listed.
- With `-c web_search="disabled"` and `--disable image_generation` as well, in the no-tools set
  below: neither the `web` tool nor the image generation tool is listed. A panellist or a job
  has no reason to make an image.

All three are now in ISOLATION, so no run or job has any of them, and "isolation_gaps" has no
line for them: nothing of them stays open. `web_search` is a `-c` key, and an unknown `-c` key
is ignored without a message, so check() cannot tell if a later CLI renames it: look at
`ALL_TOOLS` again when the CLI's version changes.

What a session still has besides its shell (verified on codex-cli 0.162.1, listed with the
shell and the apps off). The model is shown a script tool, `exec`, a tool to `wait`, two that
ask the user for input (`request_user_input`) and six for sub-agents, which
`--disable multi_agent` did not remove. Inside the script tool are `apply_patch`, which writes
files in the working directory, a clock, three tools that read MCP resources, `view_image` and
the goal tools. The script runtime itself has no `fs`, `process`, `fetch` or `require`: it
reaches no file, network or process of its own. No switch was found that removes the script
tool cleanly (`--disable code_mode_host` makes it fail, at the price of a warning item in every
process, and is not passed), nor the wait, input and sub-agent tools: "isolation_gaps" lists
them.

No tools (run["tools"] == "none"), checked on 13 October 2026. The CLI has no switch for a
session without tools. NO_TOOLS turns off the features that give it its shell (`exec_command`
and `write_stdin`), `view_image`, the goal tools, the sleep tool, the browser and computer
tools and the sub-agent feature. With it, and with ISOLATION as above, a session asked to run
`pwd` replies that it cannot (verified), a session asked to read a file in its folder could not
(verified), and its script runtime lists five tools: `apply_patch`, the clock and the three
that read MCP resources. What stays is in the paragraph above, less `view_image` and the goal
tools: above all `apply_patch`, which can still write a file in the working directory, and the
sub-agent tools, whose sub-agent gets the same set as its parent. So "none" on this runner is
no shell, no file read and no network, and not literally no tool. A participant and an
interviewer of an interview run this way, each in a folder that holds nothing. Launch and
resume were both run with the whole set.

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

Inside another Codex sandbox (verified on 13 October 2026, under `codex sandbox` and under a
`codex exec` session as the lead, on Linux):

- With the Codex home read-only, `codex exec` exits at once with code 1, nothing on stdout and
  `Error: failed to initialize in-process app-server client: Read-only file system (os error
  30)` on stderr. The caller reads that as a CLI that could not be started. `codex login status`
  still answers, after a warning line, so check() passes.
- With the Codex home writable, the run starts, calls the model and ends its turn with exit code
  0, and every shell command it tried is an `item.completed` of type `command_execution` with
  status `failed`, exit code 1 and the output `error building bubblewrap command: app-server
  socket directory must be a user-owned directory with mode 0700`. The CLI cannot build its own
  sandbox there: the outer sandbox hides the socket directory of Codex's app-server daemon
  (`/tmp/codex-daemon-<uid>`, mode 000 inside), the CLI must hide the same directory for its own
  sandbox, and refuses one it does not own with mode 0700. No writable directory changes that,
  and the outer sandbox refuses that directory as a writable root. A run then reads nothing and
  writes nothing, at 55,000 to 80,000 input tokens an attempt: that is "cannot_run"
  (SANDBOX_FAILED).
- `codex sandbox -c sandbox_mode="workspace-write" -- true` builds the same sandbox with no
  model, in about 50 ms: exit code 0 outside any sandbox, and inside one exit code 1 with the
  same line on stderr. shell_check() runs it. It reads the user's config.toml, which a run does
  not (`codex sandbox` has no `--ignore-user-config`), so only that line refuses: another
  failure of the probe says nothing about a run.
- Under `danger-full-access` the probe passes. No run was made there.
- Nothing was run with the home writable and its `sessions` folder not, or with a file where
  that folder belongs. shell_check() refuses both, inferred from what the folder is for: a
  session is its file there. The folder of a day beneath it is the CLI's to make, and is not
  tested.

Nothing was seen of a run that could not reach its provider: no pattern for it is here.

Not settled: the real output at a usage limit; how to remove the sub-agent blocks; whether the
trust entry can be prevented; and a network rule narrower than all or nothing. The experimental
`network_proxy` feature with a permission profile allowed the socket and one host and nothing
else under `codex sandbox`, but it puts proxy variables into the shell, agent-browser reads them
as its own proxy setting, and the session restarts blank at the first command.
"""

from __future__ import annotations

import glob
import json
import os
import re

from . import BROWSER_GAPS, child_env, exited, json_lines, last_line, launch_effort, model_facts, result, run_cli, \
    unwritable, usage

CLI = "codex"
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
ISOLATION = ["--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
             "-c", "project_doc_max_bytes=0", "-c", "skills.include_instructions=false",
             "-c", "approval_policy=never", "--disable", "plugins", "--disable", "tool_suggest",
             "--disable", "apps", "-c", 'web_search="disabled"', "--disable", "image_generation"]
# What a run that may browse gets on top of the sandbox: a way to the session's socket, and no
# writable temporary directory to start a session of its own in.
BROWSING = ["-c", "sandbox_workspace_write.network_access=true", "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
            "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true"]
# What a run with "tools": "none" gets on top of ISOLATION: every other feature that gives a session
# a tool to read, run or reach anything with is off (module docstring, "No tools", for what that leaves).
NO_TOOLS = ["--disable", "shell_tool", "--disable", "unified_exec", "--disable", "view_image",
            "--disable", "multi_agent", "--disable", "sleep_tool", "--disable", "browser_use",
            "--disable", "computer_use", "--disable", "goals"]
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
# How the CLI says that it cannot build its own sandbox: in the output of every shell command of a
# run, and on stderr of PROBE. Verified inside another Codex sandbox on Linux. What the macOS
# sandbox says in the same place has not been seen, and is not guessed.
SANDBOX_FAILED = "error building bubblewrap command"
# Builds the sandbox a run gets, with no model, and runs nothing in it.
PROBE = [CLI, "sandbox", "-c", 'sandbox_mode="workspace-write"', "--", "true"]
PROBE_SECONDS = 10
UUID = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def capabilities() -> dict:
    return {
        "images_by_path": True,
        "image_attach": True,
        "browser": True,
        "budget_cap": False,
        "budget_cap_note": "",
        "effort_levels": list(EFFORTS),
        "resume": True,
        "purge": True,
        "usage": {"tokens": True, "cost": False, "duration": False},
        "default_concurrency": 4,
        "provider": "OpenAI",
        "billing_env": list(BILLING_ENV),
        "interview": True,
        "no_tools": True,
        "no_tools_note": "no shell, no file or image reading and no network. That is as few tools as the CLI "
                         "allows, and not none: a patch tool can still write files in the process's own folder, "
                         "and a clock, three tools that read MCP resources, a tool to wait, tools that ask the "
                         "user for input and sub-agent tools with the same set stay.",
        "isolation_gaps": [
            "The user's global instruction file (~/.codex/AGENTS.md) is always loaded, because "
            "keeping it out would mean moving the login.",
            "The whole disk is readable from the sandbox, the home directory included. Only "
            "writes are confined.",
            "/tmp is writable as well as the working directory, except for a run that may browse.",
            "The working directory path, the shell, the date and the timezone are always in the "
            "model's context.",
            "Sub-agent tools and their instructions stay available.",
            "A script tool stays available. It reaches no file, network or process of its own, and "
            "holds a patch tool that writes files in the working directory, a clock and three tools "
            "that read MCP resources. So do a tool to wait and tools that ask the user for input.",
            "Commands run in a login shell that sources the user's shell profile.",
            "A run inside a git repository adds a trust entry for that repository to the "
            "user's Codex config.toml.",
        ],
        "browse_gaps": [
            *BROWSER_GAPS,
            "With browsing on, network access is all or nothing: the run's shell can reach the internet "
            "and the pages under review directly, without the browser and its policy, and any Unix "
            "socket the user can.",
            "With browsing on, agent-browser commands that never reach a session are not refused: one "
            "of them lists the names of the user's own browser profiles.",
        ],
    }


def _options(run: dict, workdir) -> list[str]:
    bare = run.get("tools") == "none"
    if bare and run.get("browse"):
        raise ValueError("a run with no tools cannot browse")
    argv = [CLI, "exec", "--json", *ISOLATION, "-s", "workspace-write", *(BROWSING if run.get("browse") else []),
            *(NO_TOOLS if bare else []), "-C", os.path.abspath(workdir)]
    if run.get("model"):
        argv += ["-m", run["model"]]
    effort = launch_effort(run, EFFORTS)
    if effort:
        argv += ["-c", f"model_reasoning_effort={effort}"]
    return argv


def launch_command(run: dict, prompt: str, workdir, limits: dict | None) -> dict:
    return {"argv": [*_options(run, workdir), "-"], "stdin": prompt, "env": child_env(run), "session_id": None}


def resume_command(run: dict, session_id: str, message: str, workdir, limits: dict | None) -> dict:
    if not UUID.fullmatch(session_id or ""):
        raise ValueError(f"not a thread id: {session_id!r}")
    return {"argv": [*_options(run, workdir), "resume", session_id, "-"], "stdin": message,
            "env": child_env(run), "session_id": session_id}


def _usage(reported) -> dict:
    if not isinstance(reported, dict):
        return usage()
    return usage(input_tokens=reported.get("input_tokens"), output_tokens=reported.get("output_tokens"),
                 cached_tokens=reported.get("cached_input_tokens"))


def _home() -> str:
    return os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")


def _sessions() -> str:
    """Where the CLI keeps its session files, each in a folder for its day."""
    return os.path.join(_home(), "sessions")


def _token_count(session_id) -> dict:
    """The session's last token_count event, from its session file. {} when there is none."""
    if not UUID.fullmatch(session_id or ""):
        return {}
    pattern = os.path.join(glob.escape(_sessions()), "*", "*", "*", f"rollout-*-{session_id}.jsonl")
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


def _sandbox_failed(lines: list[dict]) -> str:
    """What the CLI said when it could not build its sandbox, when every shell command the run
    tried ended that way. "" when it tried none, or one of them ran."""
    said = [str(_dig(x, "item", "aggregated_output") or "") for x in lines
            if x.get("type") == "item.completed" and _dig(x, "item", "type") == "command_execution"]
    return said[0].strip() if said and all(SANDBOX_FAILED in output for output in said) else ""


def parse_result(stdout, stderr, exit_code, session_id=None) -> dict:
    """"session_saved" stays None: no run has been seen to finish without its session file (with
    the Codex home read-only the CLI does not start at all), so its absence is not read as one."""
    lines = json_lines(stdout)
    out = result(session_id=next((x["thread_id"] for x in lines if x.get("type") == "thread.started"
                                  and isinstance(x.get("thread_id"), str)), None))
    refused = _sandbox_failed(lines)
    if refused:
        out["cannot_run"] = f"it could not build its sandbox ({refused})"
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
    adds --help to the launch options, which the CLI prints only once the options are accepted.
    It is run twice: as a run that may browse, and as one with no tools."""
    version = run_cli([CLI, "--version"])
    if version is None:
        return {"ok": False, "message": f"The {CLI} CLI is not on PATH"}
    if version[0] != 0:
        return {"ok": False, "message": version[2] or version[1] or f"{CLI} --version failed"}
    code, out, err = run_cli([CLI, "login", "status"]) or (1, "", "")
    said = last_line(err) or last_line(out)  # the answer is the last line: warnings can come before it
    if code != 0:
        return {"ok": False, "message": said or f"{CLI} login status failed"}
    for options in ({"browse": True}, {"tools": "none"}):
        probe = run_cli([*_options({"model": "default", "effort": EFFORTS[0], **options}, "."), "--help"]) or (
            1, "", "")
        if probe[0] != 0:
            return {"ok": False, "message": next((x for x in probe[2].splitlines() if x.strip()), "")
                    or f"{CLI} refused the launch options"}
    return {"ok": True, "message": f"{version[1]}, {said}"}


def shell_check() -> dict:
    """Whether the Codex home, where the CLI keeps its state, and the sessions folder beneath it
    can be written, and whether the CLI can build the sandbox a run gets (PROBE). A home that
    cannot be written and a sandbox that cannot be built both fail inside another Codex sandbox
    (module docstring). The sessions folder is tested apart because it can be the one that
    cannot be written (INFERRED: a session is its file, which a resume, the usage of a run that
    was cut short and a purge all read). Nothing here makes a model call."""
    cannot = []
    for folder in (_home(), _sessions()):
        why = unwritable(folder)
        if why:  # one clause: a home that cannot be written is why its sessions folder cannot be either
            cannot.append(f"cannot write to {folder}, where it keeps its sessions ({why})")
            break
    _, _, err = run_cli(PROBE, timeout=PROBE_SECONDS) or (1, "", "")
    said = next((line.strip() for line in err.splitlines() if SANDBOX_FAILED in line), "")
    if said:
        cannot.append(f"cannot build its own sandbox ({said})")
    return {"ok": not cannot, "message": ", and ".join(cannot)}


def model_status(entry: dict) -> dict:
    """Nothing is known of one model without a call to it, so the answers for the whole CLI
    stand: every model reads images, and check() covers the login. An unknown model fails at the first API call."""
    return model_facts(images=capabilities()["images_by_path"])


def purge_command(session_id: str, workdir) -> list | None:
    return [CLI, "delete", "--force", session_id] if UUID.fullmatch(session_id or "") else None
