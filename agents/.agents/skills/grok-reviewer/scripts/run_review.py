#!/usr/bin/env python3
"""Run or resume a Grok review with read-only enforcement.

Auto-detects whether this is an initial review or a follow-up based on
session metadata:
- If grok_session_id is null → initial review (`grok --prompt-file ...`)
- If grok_session_id exists → resume (`grok --resume <id> --prompt-file ...`)

Reads the current round from session metadata to locate the correct prompt
and output files. The round must have been set by write_prompt.py beforehand.

Read-only enforcement (hardcoded, no way to inject other flags):
- `--permission-mode auto`: Grok's safety check gates tool calls; in
  headless mode a blocked call fails and is reported to the model so the
  turn continues. (`dontAsk` was rejected: any shell command outside the
  built-in read-only list cancels the whole turn instead of failing the
  one call.)
- `--deny Edit --deny Write` ONLY when the kernel sandbox cannot start:
  Grok applies these class rules to `spawn_subagent` as well, so they cost
  subagents. With the sandbox active the OS already blocks every write and
  the class rules are dropped, which lets Grok fan out to subagents for
  large reviews; subagents inherit the sandbox, the `--deny Bash(...)`
  rules and `--disallowed-tools` (verified empirically). Without the
  sandbox the class rules stay (they also catch `sed -i`, `> file`
  redirects and other shell writes the prefix list cannot express).
- `--deny Bash(...)` list (`_DENIED_SHELL`): git mutators, remote-write
  tools, package managers, and interpreters (`python -c "open(...,'w')"` would
  otherwise bypass the edit classifier). Read-only git (`log`, `diff`,
  `status`, `show`, `blame`) still runs.
- `--disallowed-tools` (`_DISALLOWED_TOOLS`) + `--deny MCPTool`: strips
  every built-in tool except shell/read/list/grep and subagents
  (schedulers persist jobs, image_gen writes files, workflow runs
  pipelines) and denies MCP tool dispatch. `--tools` (allowlist) is not
  honoured by grok 1.0.5 and is not used.
- `--sandbox read-only` (kernel-enforced) is added when it can start:
  Grok refuses the profile if `~/.grok/hooks/` or `~/.grok/hooks-paths`
  contains a symlink component (typical for stow-managed dotfiles), so
  `_sandbox_usable()` checks that first. The decision is persisted per
  session because a resumed session must keep its original profile.
  Set GROK_REVIEWER_SANDBOX=0 to force it off, =1 to force it on.
- `--rules`: a system-prompt guardrail telling Grok it is read-only.
- `GROK_MEMORY=0`: independent of prior cross-session memory. Web search and
  web fetch are deliberately left available so Grok can research while
  reviewing; shell `curl`/`wget` work too unless the kernel sandbox is on
  (Linux blocks child-process network under `read-only`).

This is policy-level enforcement; without the kernel sandbox a determined
model could still find a write path. Every prompt should also say "do NOT
modify any files".

File access: neither `--cwd` nor `--sandbox read-only` restricts READS —
Grok can read any file on the machine (only the `strict` profile confines
reads to CWD). Copying files into `.tmp/` is a convention for keeping
review inputs alongside the project, not a technical necessity.

Output: Grok runs with `--output-format streaming-json`. The wrapper streams
stdout, treats stdout events (not stderr) as liveness for the stall watchdog, and writes the
final assistant message (the last non-empty run of `text` events) to the
round's output file. The raw event stream is written to `rN-stream.jsonl`
while the run is in progress and kept only if the round fails (it is the
diagnostic for timeouts, stalls, and early-ended turns) or if
`--keep-stream` / `GROK_REVIEWER_KEEP_STREAM=1` is set; on success it is
deleted, since it is ~100x the output size and Grok already persists the
full transcript under `~/.grok/sessions/<id>/`.
"""

import argparse
import codecs
import collections
import json
import os
import re
import select
import subprocess
import sys
import time
import uuid
from pathlib import Path

from generate_path import generate_paths
from init_session import _resolve_git_root

# Wall-clock cap for a single Grok turn. Override with --timeout.
_DEFAULT_TIMEOUT = 1800

# Stdout-silence threshold. Grok streams thought/text/tool events on
# stdout continuously while working, so prolonged silence means a hung
# stream. stderr activity does not count.
_DEFAULT_STALL = 300

_READ_ONLY_RULES = (
    "You are acting as a strictly read-only reviewer. Never create, modify, "
    "move, or delete files, and never run commands that change state. "
    "Respond with analysis as text only."
)

# Absolute-path prefixes that commonly appear in prompts and indicate
# files outside the project directory.
_EXTERNAL_PATH_RE = re.compile(
    r"(?:"
    r"/(?:Users|home|tmp|private/tmp|var/folders|opt)/\S+"
    r"|"
    r"~/\S+"
    r")"
)

# Shell command prefixes denied on top of Grok's own edit classification.
_DENIED_SHELL = [
    # git mutators (read-only git like log/diff/status/show/blame still runs)
    "git commit", "git push", "git pull", "git fetch", "git checkout",
    "git switch", "git reset", "git rebase", "git merge", "git stash",
    "git add", "git rm", "git mv", "git clean", "git restore", "git branch",
    "git tag", "git worktree", "git cherry-pick", "git revert", "git am",
    "git apply", "git config", "git submodule", "git notes",
    # privilege / remote-write / package managers (curl/wget are allowed so
    # Grok can research; they are read-only from the repo's point of view)
    "sudo", "doas", "ssh", "scp", "rsync",
    "npm", "npx", "pnpm", "yarn", "bun", "pip", "uv", "poetry", "composer",
    "cargo", "go ", "docker", "podman", "brew", "apt", "pacman", "yay",
    # interpreters / shells (can write files without a redirect)
    "python", "node", "deno", "ruby", "perl", "php", "lua",
    "bash ", "bash -", "sh ", "sh -", "zsh ", "zsh -", "eval",
    # process / filesystem mutators. With the sandbox active these prefix
    # rules are the policy layer (the Edit class rule is dropped there);
    # `> file` redirects are only caught by the kernel sandbox.
    "kill", "pkill", "dd", "ln", "chmod", "chown", "install", "make",
    "cp", "mv", "rm", "rmdir", "touch", "mkdir", "tee", "truncate",
    "sed -i", "sed --in-place", "patch", "unzip", "tar x", "tar -x",
]

# Built-in tools removed from Grok's toolset. Everything except
# run_terminal_command / read_file / list_dir / grep goes: edit tools,
# schedulers (persist jobs), image/video generation (write files), workflow
# pipelines, MCP dispatch (use_tool/search_tool), plan mode. Subagents stay
# available (they inherit every restriction) so large reviews can fan out.
# `--tools` (allowlist) was tested and is NOT honoured by grok 1.0.5 for the
# stock profile; the denylist is.
_DISALLOWED_TOOLS = ",".join([
    "write", "search_replace", "todo_write",
    "scheduler_create", "scheduler_delete", "scheduler_list", "monitor",
    "image_gen", "image_edit", "image_to_video", "reference_to_video",
    "workflow", "use_tool", "search_tool",
    "enter_plan_mode", "exit_plan_mode", "ask_user_question",
])

# Substrings Grok uses when a tool call is blocked by policy rather than
# failing on its own (permission deny rule, auto-mode safety check, or a
# permission prompt that headless mode could not answer).
_BLOCKED_SIGNATURES = (
    "Denied by permission policy",
    "Auto mode blocked",
    "User cancelled the execution",
)

def _grok_session_exists(session_id: str) -> bool:
    """True if Grok persisted a session dir for this id under GROK_HOME."""
    root = _GROK_HOME / "sessions"
    try:
        return any(
            (d / session_id).is_dir() for d in root.iterdir() if d.is_dir()
        )
    except OSError:
        return False


_GROK_HOME = Path(os.environ.get("GROK_HOME") or Path.home() / ".grok")


def _has_symlink_component(path: Path) -> bool:
    try:
        resolved_parent = path.parent.resolve()
    except OSError:
        return True
    if path.is_symlink() or resolved_parent != path.parent.absolute():
        return True
    return False


def _sandbox_usable() -> bool:
    """True if `--sandbox read-only` can start on this machine.

    Mirrors Grok's own refusal rule: the hook sources under GROK_HOME must
    not contain symlink components. Cheap filesystem check, no model call.
    """
    forced = os.environ.get("GROK_REVIEWER_SANDBOX")
    if forced is not None:
        return forced.strip().lower() in ("1", "true", "yes", "on")
    if sys.platform not in ("linux", "darwin"):
        return False
    if _GROK_HOME.is_symlink():
        return False
    hooks_dir = _GROK_HOME / "hooks"
    if hooks_dir.exists():
        if _has_symlink_component(hooks_dir):
            return False
        try:
            for entry in hooks_dir.rglob("*"):
                if entry.is_symlink():
                    return False
        except OSError:
            return False
    hooks_paths = _GROK_HOME / "hooks-paths"
    if hooks_paths.exists():
        if hooks_paths.is_symlink():
            return False
        try:
            for line in hooks_paths.read_text().splitlines():
                line = line.strip()
                if line.startswith("/"):
                    target = Path(line)
                    if not target.exists() or _has_symlink_component(target):
                        return False
        except OSError:
            return False
    return True


def _warn_external_paths(prompt_file: Path, project_dir: Path) -> None:
    """Warn (non-blocking) if the prompt references absolute paths outside --cd."""
    text = prompt_file.read_text()
    resolved_project = project_dir.resolve()
    external: set[str] = set()
    for m in _EXTERNAL_PATH_RE.finditer(text):
        p = m.group(0).rstrip(".,;:)>]\"'")
        try:
            resolved = Path(p).expanduser().resolve()
        except (OSError, ValueError):
            continue
        if not resolved.is_relative_to(resolved_project):
            external.add(p)
    if external:
        paths_str = "\n".join(f"  - {p}" for p in sorted(external))
        print(
            f"Warning: Prompt references paths outside --cd ({project_dir}):\n"
            f"{paths_str}\n"
            f"Grok can read them, but make sure they exist; prefer copying "
            f"external inputs into .tmp/ within the project.",
            file=sys.stderr,
        )


class _StreamState:
    """Accumulates the streaming-json event stream into a final answer."""

    def __init__(self) -> None:
        self.groups: list[str] = [""]  # text per model response
        self.session_id: str | None = None
        self.stop_reason: str | None = None
        self.error_message: str | None = None
        self.saw_end = False
        self.denied_calls: list[str] = []
        self.events = 0

    def feed(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        self.events += 1
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
        etype = event.get("type")
        if etype == "text":
            self.groups[-1] += event.get("data", "")
        elif etype == "usage":
            # One `usage` per model response — start a new text group.
            self.groups.append("")
        elif etype == "end":
            self.saw_end = True
            self.session_id = event.get("sessionId") or self.session_id
            self.stop_reason = event.get("stopReason")
        elif etype == "error":
            self.error_message = event.get("message") or json.dumps(event)
        elif etype == "tool_call_update" and event.get("status") == "failed":
            for c in event.get("content") or []:
                txt = (c.get("content") or {}).get("text", "")
                if any(sig in txt for sig in _BLOCKED_SIGNATURES):
                    self.denied_calls.append(txt)

    def final_text(self) -> str:
        for g in reversed(self.groups):
            if g.strip():
                return g.strip() + "\n"
        return ""


def _build_cmd(
    prompt_file: Path,
    project_dir: Path,
    session_id: str,
    is_resume: bool,
    model: str | None,
    reasoning_effort: str | None,
    sandbox: bool,
) -> list[str]:
    cmd = [
        "grok",
        "--prompt-file", str(prompt_file.resolve()),  # relative paths resolve against --cwd
        "--cwd", str(project_dir),
        "--output-format", "streaming-json",
        "--permission-mode", "auto",
        "--deny", "MCPTool",
        "--disallowed-tools", _DISALLOWED_TOOLS,
        "--rules", _READ_ONLY_RULES,
    ]
    if not sandbox:
        # Policy-only fallback. The Edit/Write class rules also deny
        # `spawn_subagent`, so subagents are only available with the sandbox.
        cmd += ["--deny", "Edit", "--deny", "Write", "--no-subagents"]
    for prefix in _DENIED_SHELL:
        cmd += ["--deny", f"Bash({prefix}*)"]
    if sandbox:
        cmd += ["--sandbox", "read-only"]
    if model:
        cmd += ["--model", model]
    if reasoning_effort:
        cmd += ["--reasoning-effort", reasoning_effort]
    if is_resume:
        cmd += ["--resume", session_id]
    else:
        # Client-chosen UUID so the id is known (and persisted) before Grok
        # starts; a timeout/stall on round 1 then still resumes correctly.
        cmd += ["--session-id", session_id]
    return cmd


def run_review(
    session_path: Path,
    project_dir: Path | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    stall: int = _DEFAULT_STALL,
    reasoning_effort: str | None = None,
    keep_stream: bool = False,
) -> dict:
    """Run or resume a Grok review. See module docstring for exit codes."""
    keep_stream = keep_stream or os.environ.get("GROK_REVIEWER_KEEP_STREAM", "").strip().lower() in (
        "1", "true", "yes", "on"
    )
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    try:
        metadata = json.loads(session_path.read_text())
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in session file: {session_path}", file=sys.stderr)
        sys.exit(1)
    round_num = metadata.get("current_round", 0)
    session_id = metadata.get("grok_session_id")
    is_resume = bool(session_id)

    if round_num == 0:
        print("Error: No prompt written yet. Run write_prompt.py first.", file=sys.stderr)
        sys.exit(1)

    # Resolve project_dir priority: explicit --cd > session metadata > cwd.
    if project_dir:
        project_dir = _resolve_git_root(project_dir)
    elif metadata.get("project_dir"):
        project_dir = Path(metadata["project_dir"])
    else:
        project_dir = _resolve_git_root(Path.cwd())

    if "project_dir" not in metadata:
        metadata["project_dir"] = str(project_dir.resolve())
        session_path.write_text(json.dumps(metadata, indent=2))

    session_model = metadata.get("model")  # locked at init time
    if reasoning_effort is not None:
        session_reasoning_effort = reasoning_effort
    else:
        session_reasoning_effort = metadata.get("reasoning_effort")

    paths = generate_paths(session_path, round_num)
    prompt_file = Path(paths["prompt_path"])
    output_file = Path(paths["output_path"])
    stream_file = output_file.with_name(f"r{round_num}-stream.jsonl")

    if not prompt_file.exists():
        print(f"Error: Prompt file not found: {prompt_file}", file=sys.stderr)
        sys.exit(1)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    _warn_external_paths(prompt_file, project_dir)

    # The sandbox profile is fixed for the life of a Grok session (a resume
    # with a different profile is refused), so decide once and persist.
    if "sandbox" not in metadata:
        metadata["sandbox"] = _sandbox_usable()
        session_path.write_text(json.dumps(metadata, indent=2))
    sandbox = bool(metadata["sandbox"])

    if not is_resume:
        session_id = str(uuid.uuid4())
        metadata["grok_session_id"] = session_id
        session_path.write_text(json.dumps(metadata, indent=2))
    elif not _grok_session_exists(session_id):
        if round_num == 1:
            # Round 1 died before Grok created the session (e.g. auth or
            # startup failure). Reuse the persisted id but start fresh with
            # `--session-id` instead of a `--resume` that would fail.
            print(
                f"Note: Grok session {session_id} not found on disk; starting "
                f"it fresh with --session-id.",
                file=sys.stderr,
            )
            is_resume = False
        else:
            # Later rounds need the prior context; silently starting an
            # empty session would drop it.
            print(
                f"Error: Grok session {session_id} no longer exists under "
                f"{_GROK_HOME / 'sessions'} (deleted?). Prior-round context "
                f"is gone — start a fresh session and carry context forward "
                f"via .tmp/ (see SKILL.md → 'Empty Output').",
                file=sys.stderr,
            )
            sys.exit(1)

    cmd = _build_cmd(
        prompt_file, project_dir, session_id, is_resume, session_model,
        session_reasoning_effort, sandbox,
    )

    env = {**os.environ, "GROK_DISABLE_AUTOUPDATER": "1", "GROK_MEMORY": "0"}
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(project_dir),
    )

    fds = {process.stdout.fileno(): "out", process.stderr.fileno(): "err"}
    for fd in fds:
        try:
            os.set_blocking(fd, False)
        except OSError as exc:
            process.kill()
            process.wait()
            print(f"Error: failed to set pipe to nonblocking mode: {exc}", file=sys.stderr)
            sys.exit(1)

    state = _StreamState()
    stderr_lines: collections.deque[str] = collections.deque(maxlen=30)
    decoders = {fd: codecs.getincrementaldecoder("utf-8")(errors="replace") for fd in fds}
    buffers = {fd: "" for fd in fds}
    open_fds = set(fds)
    stream_out = stream_file.open("w", encoding="utf-8")

    def _emit_line(fd: int, line: str) -> None:
        if fds[fd] == "out":
            stream_out.write(line if line.endswith("\n") else line + "\n")
            state.feed(line)
        else:
            stderr_lines.append(line)

    def _drain(fd: int, chunk: bytes, final: bool = False) -> None:
        buffers[fd] += decoders[fd].decode(chunk, final=final)
        while True:
            nl = buffers[fd].find("\n")
            if nl < 0:
                break
            _emit_line(fd, buffers[fd][: nl + 1])
            buffers[fd] = buffers[fd][nl + 1:]
        if final and buffers[fd]:
            _emit_line(fd, buffers[fd])
            buffers[fd] = ""

    def _read_available(fd: int) -> bool:
        got = False
        for _ in range(16):
            try:
                chunk = os.read(fd, 65536)
            except BlockingIOError:
                break
            except OSError:
                open_fds.discard(fd)
                break
            if not chunk:
                open_fds.discard(fd)
                break
            got = True
            _drain(fd, chunk)
        return got

    timed_out = stalled = False
    last_activity = time.monotonic()
    deadline = time.monotonic() + timeout if timeout > 0 else None

    while True:
        if process.poll() is not None:
            for fd in list(open_fds):
                _read_available(fd)
            break
        now = time.monotonic()
        if deadline is not None and now > deadline:
            timed_out = True
            process.kill()
            break
        if stall > 0 and now - last_activity > stall:
            stalled = True
            process.kill()
            break
        if open_fds:
            ready, _, _ = select.select(list(open_fds), [], [], 0.5)
            for fd in ready:
                # Only stdout (the event stream) counts as liveness; chatty
                # stderr (MCP/CLI logs) must not mask a dropped model stream.
                if _read_available(fd) and fds[fd] == "out":
                    last_activity = time.monotonic()
        else:
            time.sleep(0.5)

    process.wait()
    for fd in list(open_fds):
        _read_available(fd)
    for fd in fds:
        _drain(fd, b"", final=True)
    stream_out.close()

    captured_session_id = session_id
    if state.session_id and state.session_id != session_id:
        print(
            f"Warning: Grok reported session id {state.session_id}, expected "
            f"{session_id}; keeping the reported one.",
            file=sys.stderr,
        )
        captured_session_id = state.session_id
        metadata["grok_session_id"] = captured_session_id
        session_path.write_text(json.dumps(metadata, indent=2))

    final_text = state.final_text()
    if final_text:
        output_file.write_text(final_text)

    stderr_tail = "".join(stderr_lines).strip()
    retry_hint = (
        f"  - Re-run `run_review.py` with the same --session. The round "
        f"{round_num} prompt file is still on disk — do NOT call "
        f"`write_prompt.py` again; the prompt and round number are already set."
    )

    def _tail(msg: str) -> str:
        if state.denied_calls:
            msg += "\n\nDenied tool calls (read-only policy):\n" + "\n".join(
                f"  - {d}" for d in state.denied_calls[:5]
            )
        if captured_session_id:
            msg += f"\n\nSession ID for resume: {captured_session_id}"
        if stderr_tail:
            msg += f"\n\nLast stderr output:\n{stderr_tail}"
        msg += f"\nRaw event stream: {stream_file}"
        return msg

    if timed_out:
        msg = (
            f"Error: Grok review timed out after {timeout}s (process killed).\n\n"
            f"What to try next:\n{retry_hint}\n"
            f"  - If timeouts keep happening, split the review into smaller rounds.\n"
            f"  - Pass a longer `--timeout` (current: {timeout}s); `--timeout 0` disables."
        )
        if final_text:
            msg += f"\n\nPartial output was written to: {output_file}"
        print(_tail(msg), file=sys.stderr)
        sys.exit(2)

    if stalled:
        msg = (
            f"Error: Grok went silent — no stdout activity for {stall}s (process killed).\n\n"
            f"Usually a dropped model stream. What to try next:\n{retry_hint}\n"
            f"  - Pass `--stall 0` to disable stall detection (rarely needed)."
        )
        print(_tail(msg), file=sys.stderr)
        sys.exit(4)

    if process.returncode is not None and process.returncode < 0:
        sig = -process.returncode
        msg = (
            f"Error: Grok was killed by signal {sig} (external kill, not a Grok "
            f"failure). Check with the user before retrying; then re-run "
            f"`run_review.py` with the same --session."
        )
        print(_tail(msg), file=sys.stderr)
        sys.exit(128 + sig)

    if process.returncode != 0 or state.error_message:
        msg = f"Error: Grok exited with code {process.returncode}"
        if state.error_message:
            msg += f"\nGrok error: {state.error_message}"
        if final_text:
            msg += f"\n(partial output written: {output_file})"
        msg += (
            "\n\nWhat to try next:\n"
            "  - Inspect the error above. `Session does not exist` on a resume "
            "means the Grok session was deleted — start a fresh session.\n"
            "  - Re-run `run_review.py` with the same --session if the error "
            "looks transient (network, rate limit, auth refresh)."
        )
        print(_tail(msg), file=sys.stderr)
        sys.exit(1)

    incomplete = not state.saw_end or state.stop_reason != "end_turn"
    if not final_text or incomplete:
        if state.saw_end and state.stop_reason == "max_tokens":
            msg = (
                "Error: Grok hit its output token limit (stop reason: max_tokens). "
                f"The truncated text was kept at {output_file} — treat it as "
                "partial. Ask for a shorter output format on the next round."
            )
        elif incomplete:
            msg = (
                f"Error: Grok's turn ended early (stop reason: {state.stop_reason}); "
                "any text written is intermediate narration, not a review."
            )
            if state.stop_reason == "cancelled":
                msg += (
                    " A cancelled turn usually means a tool call hit a permission "
                    "prompt that headless mode cannot answer."
                )
            elif state.stop_reason in ("max_turns", "max_turn_requests"):
                msg += " The review needed more agentic turns than allowed."
            elif state.stop_reason == "refusal":
                msg += " The model refused; reword the prompt."
            if final_text:
                output_file.unlink(missing_ok=True)
        else:
            msg = "Error: Grok exited cleanly but produced no review text."
        if not state.saw_end and state.stop_reason is None:
            msg += "\nNo `end` event was received — the stream ended prematurely."
        msg += (
            "\n\nWhat to try next (in order):\n"
            f"  1. {retry_hint.strip()}\n"
            "  2. If it fails again with no new info, pipe a fresh prompt to "
            "`write_prompt.py --force` to advance to the next round, or start a "
            "fresh session (see SKILL.md → 'Empty Output')."
        )
        print(_tail(msg), file=sys.stderr)
        sys.exit(3)

    # Persist reasoning effort only after a successful run so a typo or an
    # unsupported level never gets stuck in the session.
    if reasoning_effort is not None and metadata.get("reasoning_effort") != reasoning_effort:
        metadata["reasoning_effort"] = reasoning_effort
        session_path.write_text(json.dumps(metadata, indent=2))

    if not keep_stream:
        stream_file.unlink(missing_ok=True)

    return {
        "session_id": captured_session_id,
        "prompt_file": str(prompt_file),
        "output_file": str(output_file),
        "stream_file": str(stream_file) if keep_stream else None,
        "round": round_num,
        "mode": "resume" if is_resume else "initial",
        "stop_reason": state.stop_reason,
        "denied_tool_calls": len(state.denied_calls),
        "sandbox": sandbox,
    }


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a non-negative integer, got {value!r}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"expected a non-negative integer, got {parsed}")
    return parsed


def main():
    parser = argparse.ArgumentParser(description="Run or resume a Grok review (read-only)")
    parser.add_argument("--session", required=True, help="Path to session metadata JSON file")
    parser.add_argument("--cd", default=None, help="Project directory override (default: persisted in session metadata)")
    parser.add_argument(
        "--timeout", type=_non_negative_int, default=_DEFAULT_TIMEOUT,
        help=f"Max wall-clock seconds. Default {_DEFAULT_TIMEOUT}. 0 disables. Exceeding exits 2.",
    )
    parser.add_argument(
        "--stall", type=_non_negative_int, default=_DEFAULT_STALL,
        help=f"Seconds of stdout silence before a stall kill. Default {_DEFAULT_STALL}. 0 disables. Exits 4.",
    )
    parser.add_argument(
        "--keep-stream", action="store_true",
        help=(
            "Keep rN-stream.jsonl (raw Grok event stream) after a successful "
            "round. By default it is kept only when the round fails. "
            "GROK_REVIEWER_KEEP_STREAM=1 has the same effect."
        ),
    )
    parser.add_argument(
        "--reasoning-effort", default=None,
        help=(
            "Reasoning-effort override for this run (low, medium, high, ...). "
            "Persisted on success so later rounds inherit it. Model is NOT "
            "overridable here — it is locked at session-init time."
        ),
    )
    args = parser.parse_args()

    result = run_review(
        session_path=Path(args.session),
        project_dir=Path(args.cd) if args.cd else None,
        timeout=args.timeout,
        stall=args.stall,
        reasoning_effort=args.reasoning_effort,
        keep_stream=args.keep_stream,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
