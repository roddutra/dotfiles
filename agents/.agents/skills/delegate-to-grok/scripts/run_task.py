#!/usr/bin/env python3
"""Run or resume a delegated Grok task round.

- No grok_session_id in session.json → new Grok session (`--session-id <uuid>`,
  chosen by the wrapper so it is known before Grok starts)
- grok_session_id present → follow-up on the same session (`--resume <id>`)

The round number (set by write_brief.py) locates rN-brief.md; the wrapper
writes rN-report.md (Grok's final message), rN-changes.md (git view of what
the round changed since the round's FIRST attempt, plus the results of any
`verify` commands) and keeps rN-stream.jsonl only when the round fails or
--keep-stream is set.

Execution policy (hardcoded; no way to inject other flags):
- `--permission-mode auto`: Grok's own safety classifier gates each tool
  call; in headless mode a blocked call fails and is reported back to the
  model so the turn continues (`dontAsk`/`acceptEdits` would cancel the
  whole turn on the first prompt instead).
- `--sandbox workspace` (kernel-enforced, when it can start): writes are
  confined to the project dir (and Grok's own state under ~/.grok, /tmp);
  reads and network are allowed. Grok refuses the profile if
  `~/.grok/hooks/` contains symlink components, so `_sandbox_usable()`
  checks first and the decision is persisted per session (a resume must
  keep the profile it started with). Without it, enforcement is policy-only
  (deny rules + classifier) and the result carries a loud warning.
  GROK_DELEGATE_SANDBOX=0|1 forces the decision.
- Git: `--deny Bash(git <verb>*)` rules. Without --allow-git every
  state-changing verb is denied; with it only `add/commit/tag` are allowed.
  Push, pull, fetch, reset, rebase, checkout/switch, branch, worktree, stash,
  clean, config, merge, cherry-pick, revert, submodule are always denied.
  Prefix rules are policy-level (a wrapper shell could evade them), so the
  wrapper also flags HEAD/branch/index changes as `git_state_changed`.
- `--disallowed-tools` + `--no-subagents`: removes schedulers (persist
  jobs), image/video generation, workflow/subagent spawning, plan mode and
  the interactive question tool. Shell, file edit tools, web search/fetch
  and MCP tools stay available — an implementer legitimately needs them
  (e.g. project MCP servers); only the kernel sandbox bounds their side
  effects, and external services are outside it regardless.
- Verify commands run on the host, unsandboxed, in their own process group
  (killed as a tree on timeout). They are lead-chosen and carry the same
  trust as the lead running the test suite itself.
- `GROK_MEMORY=0`: no cross-session memory bleed between tasks.

Token accounting (the point of running one task per session):
- `usage.rounds[N]` — totals summed over attempts: from the `end` event, or
  from the per-call `usage` events when the turn never reached `end`.
- `usage.last_context_tokens` — the last `usage` event seen: input +
  cache_read + cache_creation + output, i.e. how full the session is now.
  Recorded on every exit path, so a timed-out turn still advances the guard.
- `usage.context_window` — from `~/.grok/models_cache.json` for the model
  Grok reported (longest catalogue-id prefix match, e.g. "grok-4.6-build"
  → "grok-4.6"), or $GROK_DELEGATE_CONTEXT_WINDOW.
- `usage.context_pct` — last_context_tokens / context_window. write_brief.py
  warns/blocks on this so a task never continues in a saturated session.

Exit codes: 0 ok · 1 CLI/config error or `error` event · 2 wall-clock timeout ·
3 no report / turn ended early (cancelled, max_turns, refusal; `max_tokens`
keeps the truncated report as partial) · 4 stall (no stdout events) ·
128+N killed by signal N. Exit 0 with `status: BLOCKED|PARTIAL|UNKNOWN`,
`verify_passed: false` or `blocked_tool_calls > 0` means the executor did
not get a clean run — read the report and rN-changes.md.
"""

import argparse
import codecs
import collections
import json
import os
import select
import subprocess
import sys
import time
import uuid
from pathlib import Path

from delegate_common import (
    SessionLock, executor_guard, kill_tree, reap_stragglers, context_status, extract_status, git_snapshot, load_metadata,
    preflight, round_baseline, run_verify, save_metadata, summarize_changes,
    write_changes_file,
)
from generate_path import generate_paths

_DEFAULT_TIMEOUT = 3600
_DEFAULT_STALL = 600

_GROK_HOME = Path(os.environ.get("GROK_HOME") or Path.home() / ".grok")

_EXECUTOR_RULES = (
    "You are the implementer for a delegated task. Stay inside the project "
    "directory. Do not change git state unless the task explicitly allows it. "
    "Do not stop to ask questions; make the smallest safe assumption and record it "
    "in your final report."
)

# Allowed only with --allow-git.
_GIT_COMMIT_VERBS = ["git add", "git commit", "git tag"]
# Denied unless --allow-git (in addition to the always-denied list).
_GIT_MUTATORS = ["git rm", "git mv", "git restore", "git notes", "git am", "git apply"]
# Always denied: remote writes, history rewrites, branch/worktree/index moves.
_GIT_ALWAYS_DENIED = [
    "git push", "git pull", "git fetch", "git reset", "git rebase",
    "git checkout", "git switch", "git branch", "git worktree", "git stash",
    "git clean", "git config", "git merge", "git cherry-pick", "git revert",
    "git submodule", "git filter-branch", "git update-ref", "git symbolic-ref",
]
_ALWAYS_DENIED_SHELL = ["sudo", "doas", "ssh", "scp"]

_DISALLOWED_TOOLS = ",".join([
    "Agent", "spawn_subagent",
    "scheduler_create", "scheduler_delete", "scheduler_list", "monitor",
    "image_gen", "image_edit", "image_to_video", "reference_to_video",
    "workflow", "enter_plan_mode", "exit_plan_mode", "ask_user_question",
])

_BLOCKED_SIGNATURES = (
    "Denied by permission policy",
    "Auto mode blocked",
    "User cancelled the execution",
)


# ---------------------------------------------------------------------------
# Grok environment helpers
# ---------------------------------------------------------------------------

def _grok_session_exists(session_id: str) -> bool:
    root = _GROK_HOME / "sessions"
    try:
        return any((d / session_id).is_dir() for d in root.iterdir() if d.is_dir())
    except OSError:
        return False


def _has_symlink_component(path: Path) -> bool:
    try:
        resolved_parent = path.parent.resolve()
    except OSError:
        return True
    return path.is_symlink() or resolved_parent != path.parent.absolute()


def _sandbox_usable() -> bool:
    """True if `--sandbox workspace` can start (mirrors Grok's refusal rule)."""
    forced = os.environ.get("GROK_DELEGATE_SANDBOX")
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
            if any(e.is_symlink() for e in hooks_dir.rglob("*")):
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


def _context_window_for(model: str | None, metadata: dict) -> int | None:
    env = os.environ.get("GROK_DELEGATE_CONTEXT_WINDOW")
    if env and env.isdigit():
        return int(env)
    cache = _GROK_HOME / "models_cache.json"
    if model and cache.exists():
        try:
            models = (json.loads(cache.read_text()).get("models") or {})
        except (OSError, json.JSONDecodeError):
            models = {}
        # Grok reports e.g. "grok-4.6-build" for the "grok-4.6" catalogue
        # entry; prefer the exact id, then the longest matching prefix.
        candidates = [model] + sorted((k for k in models if model.startswith(k)), key=len, reverse=True)
        for key in candidates:
            info = (models.get(key) or {}).get("info") or {}
            w = info.get("context_window")
            if isinstance(w, int) and w > 0:
                return w
    prior = (metadata.get("usage") or {}).get("context_window")
    if prior:
        return prior
    # Model id is only reported on `end`; a turn killed before that with the
    # default model leaves it unknown. If every catalogued model shares one
    # window (currently the case), that value is still safe to enforce.
    if cache.exists():
        try:
            models = (json.loads(cache.read_text()).get("models") or {})
        except (OSError, json.JSONDecodeError):
            models = {}
        windows = [(v.get("info") or {}).get("context_window") for v in models.values()]
        if windows and all(isinstance(w, int) and w > 0 for w in windows) and len(set(windows)) == 1:
            return windows[0]
    return None


# ---------------------------------------------------------------------------
# Event stream
# ---------------------------------------------------------------------------

class _StreamState:
    def __init__(self) -> None:
        self.groups: list[str] = [""]
        self.session_id: str | None = None
        self.stop_reason: str | None = None
        self.error_message: str | None = None
        self.saw_end = False
        self.blocked_calls: list[str] = []
        self.last_usage: dict | None = None
        self.end_usage: dict | None = None
        self.sum_usage: dict = {"input_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}
        self.model: str | None = None
        self.model_calls = 0
        self.edits = 0
        self.commands = 0
        self.events = 0

    def feed(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
        self.events += 1
        etype = event.get("type")
        if etype == "text":
            self.groups[-1] += event.get("data", "")
        elif etype == "usage":
            u = event.get("usage") or {}
            self.last_usage = u or self.last_usage
            for k in self.sum_usage:
                self.sum_usage[k] += int(u.get(k) or 0)
            self.model_calls += 1
            self.groups.append("")
        elif etype == "tool_call":
            kind = event.get("kind") or ""
            name = event.get("toolName") or ""
            if kind in ("edit", "write") or name in ("write", "search_replace"):
                self.edits += 1
            elif kind == "execute" or name == "run_terminal_command":
                self.commands += 1
        elif etype == "tool_call_update" and event.get("status") == "failed":
            for c in event.get("content") or []:
                txt = (c.get("content") or {}).get("text", "")
                if any(sig in txt for sig in _BLOCKED_SIGNATURES):
                    self.blocked_calls.append(txt)
        elif etype == "end":
            self.saw_end = True
            self.session_id = event.get("sessionId") or self.session_id
            self.stop_reason = event.get("stopReason")
            self.end_usage = event.get("usage") or self.end_usage
            model_usage = event.get("modelUsage") or {}
            if model_usage:
                self.model = max(model_usage, key=lambda k: (model_usage[k] or {}).get("modelCalls", 0))
        elif etype == "error":
            self.error_message = event.get("message") or json.dumps(event)

    def final_text(self) -> str:
        for g in reversed(self.groups):
            if g.strip():
                return g.strip() + "\n"
        return ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _build_cmd(metadata: dict, brief_file: Path, project_dir: Path, session_id: str,
               is_resume: bool, reasoning_effort: str | None, sandbox: bool) -> list[str]:
    cmd = [
        "grok",
        "--prompt-file", str(brief_file.resolve()),
        "--cwd", str(project_dir),
        "--output-format", "streaming-json",
        "--permission-mode", "auto",
        "--no-subagents",
        "--disallowed-tools", _DISALLOWED_TOOLS,
        "--rules", _EXECUTOR_RULES,
    ]
    denied = list(_ALWAYS_DENIED_SHELL) + list(_GIT_ALWAYS_DENIED) + list(_GIT_MUTATORS)
    if not metadata.get("allow_git"):
        denied += _GIT_COMMIT_VERBS
    for prefix in denied:
        cmd += ["--deny", f"Bash({prefix}*)"]
    if sandbox:
        cmd += ["--sandbox", "workspace"]
    if metadata.get("model"):
        cmd += ["--model", metadata["model"]]
    if reasoning_effort:
        cmd += ["--reasoning-effort", reasoning_effort]
    cmd += ["--resume", session_id] if is_resume else ["--session-id", session_id]
    return cmd


def _account(metadata: dict, round_num: int, state: _StreamState) -> dict:
    """Record token usage and live context for this attempt. Runs on every
    exit path so failed turns still advance the context guard."""
    usage = metadata.setdefault("usage", {"rounds": {}, "session_input_tokens": 0, "session_output_tokens": 0})
    # Prefer the `end` totals; a turn that never reached `end` (timeout,
    # stall, kill) is charged from the per-call `usage` events instead.
    end_u = state.end_usage or state.sum_usage
    usage_complete = state.end_usage is not None
    in_tok = int(end_u.get("input_tokens") or 0) + int(end_u.get("cache_read_input_tokens") or 0) + int(end_u.get("cache_creation_input_tokens") or 0)
    out_tok = int(end_u.get("output_tokens") or 0)
    rounds = usage.setdefault("rounds", {})
    prev = rounds.get(str(round_num)) or {}
    rounds[str(round_num)] = {
        "input_tokens": int(prev.get("input_tokens") or 0) + int(end_u.get("input_tokens") or 0),
        "cache_read_input_tokens": int(prev.get("cache_read_input_tokens") or 0) + int(end_u.get("cache_read_input_tokens") or 0),
        "cache_creation_input_tokens": int(prev.get("cache_creation_input_tokens") or 0) + int(end_u.get("cache_creation_input_tokens") or 0),
        "output_tokens": int(prev.get("output_tokens") or 0) + out_tok,
        "reasoning_tokens": int(prev.get("reasoning_tokens") or 0) + int(end_u.get("reasoning_tokens") or 0),
        "model_calls": int(prev.get("model_calls") or 0) + state.model_calls,
        "edits": int(prev.get("edits") or 0) + state.edits,
        "commands": int(prev.get("commands") or 0) + state.commands,
        "attempts": int(prev.get("attempts") or 0) + 1,
        "usage_complete": bool(prev.get("usage_complete", True)) and usage_complete,
        "model": state.model or prev.get("model"),
    }
    usage["session_input_tokens"] = int(usage.get("session_input_tokens") or 0) + in_tok
    usage["session_output_tokens"] = int(usage.get("session_output_tokens") or 0) + out_tok
    last = state.last_usage or {}
    fresh = (
        int(last.get("input_tokens") or 0) + int(last.get("cache_read_input_tokens") or 0)
        + int(last.get("cache_creation_input_tokens") or 0) + int(last.get("output_tokens") or 0)
    ) or None
    model = state.model or usage.get("model") or metadata.get("model")
    window = _context_window_for(model, metadata)
    usage["last_context_tokens"] = fresh or usage.get("last_context_tokens")
    usage["context_window"] = window
    usage["context_pct"] = (
        round(100.0 * usage["last_context_tokens"] / window, 1)
        if (window and usage["last_context_tokens"]) else None
    )
    usage["model"] = model
    rec = rounds[str(round_num)]
    return {
        "attempt_input_tokens": in_tok,
        "attempt_output_tokens": out_tok,
        "round_input_tokens": rec["input_tokens"] + rec["cache_read_input_tokens"] + rec["cache_creation_input_tokens"],
        "round_output_tokens": rec["output_tokens"],
        "round_attempts": rec["attempts"],
        "session_input_tokens": usage["session_input_tokens"],
        "session_output_tokens": usage["session_output_tokens"],
        "context_tokens": usage["last_context_tokens"],
        "context_window": window,
        "context_pct": usage["context_pct"],
        "context_status": context_status(
            usage["context_pct"], metadata.get("context_warn_pct", 50), metadata.get("context_block_pct", 70)
        ),
        "model": model,
        "usage_complete": rec["usage_complete"],
    }


def run_task(
    session_path: Path,
    project_dir: Path | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    stall: int = _DEFAULT_STALL,
    reasoning_effort: str | None = None,
    keep_stream: bool = False,
    skip_verify: bool = False,
    rerun: bool = False,
) -> dict:
    keep_stream = keep_stream or os.environ.get("GROK_DELEGATE_KEEP_STREAM", "").strip().lower() in ("1", "true", "yes", "on")
    load_metadata(session_path)  # fail early on a missing/corrupt file
    with SessionLock(session_path):
        metadata = load_metadata(session_path)  # re-read under the lock
        return _run_locked(session_path, metadata, project_dir, timeout, stall, reasoning_effort, keep_stream, skip_verify, rerun)


def _run_locked(session_path, metadata, project_dir, timeout, stall, reasoning_effort, keep_stream, skip_verify, rerun) -> dict:
    round_num, project_dir = preflight(metadata, session_path, rerun, project_dir)
    session_id = metadata.get("grok_session_id")
    is_resume = bool(session_id)
    effort = reasoning_effort if reasoning_effort is not None else metadata.get("reasoning_effort")

    paths = generate_paths(session_path, round_num)
    brief_file = Path(paths["brief_path"])
    report_file = Path(paths["report_path"])
    changes_file = Path(paths["changes_path"])
    stream_file = Path(paths["stream_path"])
    if not brief_file.exists():
        print(f"Error: Brief file not found: {brief_file}", file=sys.stderr)
        sys.exit(1)
    report_file.unlink(missing_ok=True)  # never mistake a stale report for this attempt's

    def _save() -> None:
        save_metadata(session_path, metadata)

    # Sandbox profile is fixed for the life of a Grok session: decide once.
    if "sandbox" not in metadata:
        metadata["sandbox"] = _sandbox_usable()
    sandbox = bool(metadata["sandbox"])
    if not sandbox:
        print(
            "Warning: Grok's kernel sandbox (--sandbox workspace) cannot start on this "
            "machine (symlinked ~/.grok/hooks or unsupported platform). The executor runs "
            "with policy-only enforcement: it can write anywhere the user can. Fix the "
            "hooks layout or set GROK_DELEGATE_SANDBOX=1 to force the profile.",
            file=sys.stderr,
        )

    if not is_resume:
        session_id = str(uuid.uuid4())
        metadata["grok_session_id"] = session_id
    elif not _grok_session_exists(session_id):
        if round_num == 1:
            print(f"Note: Grok session {session_id} not found on disk; starting it fresh with --session-id.", file=sys.stderr)
            is_resume = False
        else:
            print(
                f"Error: Grok session {session_id} no longer exists under {_GROK_HOME / 'sessions'}. "
                f"Prior-round context is gone — hand off to a fresh session with handoff_session.py.",
                file=sys.stderr,
            )
            sys.exit(1)

    baseline = round_baseline(metadata, round_num, project_dir)
    attempt = int((metadata.get("usage", {}).get("rounds", {}).get(str(round_num)) or {}).get("attempts") or 0) + 1
    cmd = _build_cmd(metadata, brief_file, project_dir, session_id, is_resume, effort, sandbox)
    metadata["status"] = "running"
    _save()

    env = {**os.environ, "GROK_DISABLE_AUTOUPDATER": "1", "GROK_MEMORY": "0"}
    try:
        process = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, cwd=str(project_dir),
            start_new_session=True,  # own process group so kill_tree() reaches children
        )
    except OSError as exc:
        metadata["status"] = "failed"
        _save()
        print(f"Error: could not launch grok: {exc}", file=sys.stderr)
        sys.exit(1)

    state = _StreamState()

    def _abort() -> None:
        # Wrapper is dying (signal/exception): keep what we know, including
        # events still buffered in the pipes.
        try:
            for fd in list(open_fds):
                _read_available(fd)
            for fd in fds:
                _drain(fd, b"", final=True)
            stream_out.close()
        except NameError:
            pass  # died before the stream plumbing existed
        except Exception:
            pass
        _account(metadata, round_num, state)
        metadata["status"] = "failed"
        metadata["last_round_failed"] = round_num
        _save()

    with executor_guard(process, on_abort=_abort):
        fds = {process.stdout.fileno(): "out", process.stderr.fileno(): "err"}
        for fd in fds:
            try:
                os.set_blocking(fd, False)
            except OSError as exc:
                process.kill()
                process.wait()
                metadata["status"] = "failed"
                _save()
                print(f"Error: failed to set pipe to nonblocking mode: {exc}", file=sys.stderr)
                sys.exit(1)

        stderr_lines: collections.deque[str] = collections.deque(maxlen=30)
        decoders = {fd: codecs.getincrementaldecoder("utf-8")(errors="replace") for fd in fds}
        buffers = {fd: "" for fd in fds}
        open_fds = set(fds)
        stream_out = stream_file.open("w", encoding="utf-8")

        def _emit(fd: int, line: str) -> None:
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
                _emit(fd, buffers[fd][: nl + 1])
                buffers[fd] = buffers[fd][nl + 1:]
            if final and buffers[fd]:
                _emit(fd, buffers[fd])
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
                kill_tree(process)
                break
            if stall > 0 and now - last_activity > stall:
                stalled = True
                kill_tree(process)
                break
            if open_fds:
                ready, _, _ = select.select(list(open_fds), [], [], 0.5)
                for fd in ready:
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
    stragglers = reap_stragglers(process)
    if stragglers:
        print(f"Warning: killed {stragglers} process(es) Grok left running after it exited.", file=sys.stderr)

    if state.session_id and state.session_id != session_id:
        print(f"Warning: Grok reported session id {state.session_id}, expected {session_id}; keeping the reported one.", file=sys.stderr)
        session_id = state.session_id
        metadata["grok_session_id"] = session_id

    report_text = state.final_text()
    if report_text:
        report_file.write_text(report_text)

    # Grok can linger after the `end` event (shutting down MCP servers). If
    # the turn ended cleanly and the report is on disk, the deadline is moot.
    killed_by_wrapper = timed_out or stalled
    lingered = False
    if (timed_out or stalled) and state.saw_end and state.stop_reason == "end_turn" and report_text.strip():
        lingered = True
        timed_out = stalled = False

    # Change summary against the round's first-attempt baseline, taken BEFORE
    # verify commands run so their artifacts do not pollute it.
    after = git_snapshot(project_dir)
    changes = summarize_changes(project_dir, baseline, after)
    usage_out = _account(metadata, round_num, state)

    stderr_tail = "".join(stderr_lines).strip()
    retry_hint = (
        f"  - Re-run `run_task.py` with the same --session. The round {round_num} brief is "
        f"still on disk — do NOT call `write_brief.py` again."
    )

    def _tail(msg: str) -> str:
        if state.blocked_calls:
            msg += "\n\nTool calls blocked by policy:\n" + "\n".join(f"  - {d[:200]}" for d in state.blocked_calls[:5])
        if changes["files_touched"]:
            msg += f"\n\nFiles touched so far this round ({len(changes['files_touched'])}): see {changes_file}"
        msg += f"\n\nSession ID for resume: {session_id}"
        msg += f"\nContext: {usage_out['context_pct']}% of window ({usage_out['context_status']})"
        if stderr_tail:
            msg += f"\n\nLast stderr output:\n{stderr_tail}"
        msg += f"\nRaw event stream: {stream_file}"
        return msg

    def _fail(msg: str, code: int) -> None:
        write_changes_file(changes_file, changes, [], state.blocked_calls, attempt_note=f"Attempt {attempt} FAILED (exit {code}); summary vs. round baseline")
        metadata["status"] = "failed"
        metadata["last_round_failed"] = round_num  # write_brief.py refuses to advance past it without --force
        _save()
        print(_tail(msg), file=sys.stderr)
        sys.exit(code)

    if timed_out:
        _fail(
            f"Error: Grok task timed out after {timeout}s (process killed).\n\n"
            f"What to try next:\n{retry_hint}\n"
            f"  - Grok kept its session; a re-run resumes it. If the task is too big for one "
            f"round, split it: write a narrower follow-up brief (--force) or hand off.\n"
            f"  - Pass a longer `--timeout` (current: {timeout}s); `--timeout 0` disables.",
            2,
        )
    if stalled:
        _fail(
            f"Error: Grok went silent — no stdout events for {stall}s (process killed).\n\n"
            f"Usually a dropped model stream. What to try next:\n{retry_hint}\n"
            f"  - Pass `--stall 0` to disable stall detection if a single command legitimately "
            f"runs that long (e.g. a slow test suite).",
            4,
        )
    if process.returncode is not None and process.returncode < 0 and not killed_by_wrapper:
        sig = -process.returncode
        _fail(
            f"Error: Grok was killed by signal {sig} (external kill). Check with the user "
            f"before retrying; then re-run `run_task.py` with the same --session.",
            128 + sig,
        )
    if (process.returncode != 0 and not lingered) or state.error_message:
        msg = f"Error: Grok exited with code {process.returncode}"
        if state.error_message:
            msg += f"\nGrok error: {state.error_message}"
        if report_text:
            msg += f"\n(partial report written: {report_file})"
        msg += (
            "\n\nWhat to try next:\n"
            "  - Inspect the error above. `Session does not exist` on a resume means the Grok "
            "session was deleted — hand off to a fresh session.\n"
            "  - Re-run `run_task.py` with the same --session if it looks transient "
            "(network, rate limit, auth refresh)."
        )
        _fail(msg, 1)

    incomplete = not state.saw_end or state.stop_reason != "end_turn"
    if not report_text or incomplete:
        if state.saw_end and state.stop_reason == "max_tokens":
            msg = (
                "Error: Grok hit its output token limit (stop reason: max_tokens). "
                f"The truncated report was kept at {report_file} — treat it as partial."
            )
        elif incomplete:
            msg = (
                f"Error: Grok's turn ended early (stop reason: {state.stop_reason}); "
                "any text written is intermediate narration, not a report."
            )
            if state.stop_reason == "cancelled":
                msg += " A cancelled turn usually means a tool call hit a permission prompt that headless mode cannot answer."
            elif state.stop_reason in ("max_turns", "max_turn_requests"):
                msg += " The task needed more agentic turns than allowed — split it."
            elif state.stop_reason == "refusal":
                msg += " The model refused; reword the brief."
            if report_text:
                report_file.unlink(missing_ok=True)
        else:
            msg = "Error: Grok exited cleanly but produced no report text."
        if not state.saw_end and state.stop_reason is None:
            msg += "\nNo `end` event was received — the stream ended prematurely."
        msg += (
            "\n\nWhat to try next (in order):\n"
            f"  1. {retry_hint.strip()}\n"
            "  2. If it fails again with no new info, hand off to a fresh session with "
            "`handoff_session.py`."
        )
        _fail(msg, 3)

    # --- Success path ---------------------------------------------------------
    verify_cmds = [] if skip_verify else list(metadata.get("verify") or [])
    verify_results = run_verify(verify_cmds, project_dir) if verify_cmds else []
    write_changes_file(changes_file, changes, verify_results, state.blocked_calls, attempt_note=(f"Attempt {attempt} of this round" if attempt > 1 else None))

    status = extract_status(report_text) or "UNKNOWN"
    verify_passed = all(v["passed"] for v in verify_results) if verify_results else None
    metadata["status"] = {"DONE": "done", "PARTIAL": "partial", "BLOCKED": "blocked"}.get(status, "unknown")
    metadata["completed_round"] = round_num
    metadata.pop("last_round_failed", None)
    if reasoning_effort is not None and metadata.get("reasoning_effort") != reasoning_effort:
        metadata["reasoning_effort"] = reasoning_effort
    _save()

    if not keep_stream:
        stream_file.unlink(missing_ok=True)

    warnings = []
    if stragglers:
        warnings.append(f"Grok left {stragglers} background process(es) running after exit; the wrapper killed them.")
    if not sandbox:
        warnings.append("Kernel sandbox was NOT active for this session (policy-only enforcement) — review the diff with extra care.")
    if lingered:
        warnings.append("The turn completed but the process outlived the timeout/stall window and was killed while shutting down; the report is valid.")
    if status == "UNKNOWN":
        warnings.append("Report has no parsable `## Status` — Grok ignored the contract; read the report carefully and consider a follow-up asking for the required format.")
    if changes["git_state_changed"] and not metadata.get("allow_git"):
        warnings.append("Grok changed git state (HEAD/branch/index) although the session forbids it — inspect rN-changes.md.")
    if status == "DONE" and not changes["files_touched"] and state.edits == 0:
        warnings.append("Report says DONE but no files changed this round — verify the task really needed no edits.")
    if state.blocked_calls:
        warnings.append(f"{len(state.blocked_calls)} tool call(s) were blocked by policy — check whether the task needs --allow-git or a different approach (see rN-changes.md).")
    if verify_passed is False:
        warnings.append("One or more verify commands FAILED — see rN-changes.md before accepting the report.")
    if usage_out["context_status"] == "handoff-required":
        warnings.append(f"Context window {usage_out['context_pct']}% used — write_brief.py will refuse another round; hand off to a new session.")
    elif usage_out["context_status"] == "handoff-soon":
        warnings.append(f"Context window {usage_out['context_pct']}% used — keep follow-ups short and plan a handoff.")

    return {
        "session_id": session_id,
        "round": round_num,
        "attempt": attempt,
        "mode": "resume" if is_resume else "initial",
        "status": status,
        "stop_reason": state.stop_reason,
        "report_file": str(report_file),
        "changes_file": str(changes_file),
        "brief_file": str(brief_file),
        "stream_file": str(stream_file) if keep_stream else None,
        "files_touched": changes["files_touched"],
        "lines_added": changes["lines_added"],
        "lines_deleted": changes["lines_deleted"],
        "git_state_changed": changes["git_state_changed"],
        "blocked_tool_calls": len(state.blocked_calls),
        "sandbox": sandbox,
        "verify_passed": verify_passed,
        "verify": [{"command": v["command"], "passed": v["passed"], "exit_code": v["exit_code"]} for v in verify_results],
        "usage": usage_out,
        "warnings": warnings,
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
    parser = argparse.ArgumentParser(description="Run or resume a delegated Grok task round")
    parser.add_argument("--session", required=True, help="Path to session metadata JSON file")
    parser.add_argument("--cd", default=None, help="Project directory; must equal the session's persisted project_dir (sanity check only)")
    parser.add_argument("--timeout", type=_non_negative_int, default=_DEFAULT_TIMEOUT, help=f"Max wall-clock seconds (default {_DEFAULT_TIMEOUT}; 0 disables; exit 2)")
    parser.add_argument("--stall", type=_non_negative_int, default=_DEFAULT_STALL, help=f"Seconds without stdout events before a stall kill (default {_DEFAULT_STALL}; 0 disables; exit 4)")
    parser.add_argument("--reasoning-effort", default=None, help="Reasoning-effort override for this round (persisted on success)")
    parser.add_argument("--keep-stream", action="store_true", help="Keep rN-stream.jsonl after a successful round (default: only kept on failure). GROK_DELEGATE_KEEP_STREAM=1 does the same.")
    parser.add_argument("--skip-verify", action="store_true", help="Do not run the session's verify commands after this round")
    parser.add_argument("--rerun", action="store_true", help="Execute the current round again even though it already completed")
    args = parser.parse_args()
    result = run_task(
        session_path=Path(args.session),
        project_dir=Path(args.cd) if args.cd else None,
        timeout=args.timeout,
        stall=args.stall,
        reasoning_effort=args.reasoning_effort,
        keep_stream=args.keep_stream,
        skip_verify=args.skip_verify,
        rerun=args.rerun,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
