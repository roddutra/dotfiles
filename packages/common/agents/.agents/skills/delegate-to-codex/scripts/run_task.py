#!/usr/bin/env python3
"""Run or resume a delegated Codex task round.

- No codex_session_id in session.json → new Codex thread (`codex exec`)
- codex_session_id present → follow-up on the same thread (`codex exec resume`)

The round number (set by write_brief.py) locates rN-brief.md; the wrapper
writes rN-report.md (Codex's final message), rN-changes.md (git view of what
the round changed since the round's FIRST attempt, plus the results of any
`verify` commands) and keeps rN-stream.jsonl only when the round fails or
--keep-stream is set.

Execution policy (hardcoded; no way to inject other flags):
- `--sandbox workspace-write`: Codex may edit files under the project dir
  and run commands; writes elsewhere are blocked by the OS sandbox. Network
  inside the sandbox is off unless the session was created with --network.
- `--json`: event stream on stdout; the wrapper extracts the final
  `agent_message`, per-turn token usage, and counts file changes/commands.
- Git: Codex has no CLI deny-list, so "do not touch git state" is enforced
  by the brief contract plus detection: HEAD/branch movement and index
  (staged set) changes are flagged as `git_state_changed`.
- Verify commands run on the host, unsandboxed, in their own process group
  (killed as a tree on timeout). They are lead-chosen and carry the same
  trust as the lead running the test suite itself.

Token accounting (the point of running one task per session):
- `usage.rounds[N]` — usage summed over all attempts of the round, charged
  from the rollout's cumulative totals (delta per attempt; falls back to
  `turn.completed.usage` if the rollout file cannot be found).
- `usage.last_context_tokens` — input + output of the last model request,
  i.e. how full this thread's context is now.
- `usage.context_window` — from the rollout's `token_count` event
  (`model_context_window`), or $CODEX_DELEGATE_CONTEXT_WINDOW.
  Both context numbers come from `~/.codex/sessions/.../rollout-*.jsonl`
  because the `--json` stream only reports per-turn totals (summed over
  every request in the turn), which say nothing about how full the thread is.
  Accounting runs on every exit path, so a timed-out turn still advances
  the context guard.
- `usage.context_pct` — last_context_tokens / context_window. write_brief.py
  warns/blocks on this so a task never continues in a saturated thread.

Exit codes: 0 ok · 1 CLI/config error · 2 wall-clock timeout · 3 no report
(clean exit without a final message) · 4 stall (no stdout events) ·
128+N killed by signal N. Exit 0 with `status: BLOCKED|PARTIAL|UNKNOWN` or
`verify_passed: false` means the executor did not get a clean, verified
run — read the report and rN-changes.md.
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
from pathlib import Path

from delegate_common import (
    SessionLock, executor_guard, kill_tree, reap_stragglers, context_status, extract_status, git_snapshot, load_metadata,
    preflight, round_baseline, run_verify, save_metadata, summarize_changes,
    write_changes_file,
)
from generate_path import generate_paths

# Implementation rounds run longer than reviews: 60 min wall clock, 10 min
# without a single stdout event before we call it hung.
_DEFAULT_TIMEOUT = 3600
_DEFAULT_STALL = 600

_CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
_CODEX_SESSIONS_ROOT = _CODEX_HOME / "sessions"


# ---------------------------------------------------------------------------
# Rollout lookup (live context size)
# ---------------------------------------------------------------------------

def _find_rollout_file(session_id: str) -> Path | None:
    if not session_id or not _CODEX_SESSIONS_ROOT.exists():
        return None
    try:
        matches = list(_CODEX_SESSIONS_ROOT.rglob(f"rollout-*-{session_id}.jsonl"))
        return max(matches, key=lambda p: p.stat().st_mtime) if matches else None
    except OSError:
        return None


def _rollout_token_state(session_id: str) -> dict:
    """Last `token_count.info` from the rollout (best-effort): has
    `last_token_usage` (size of the most recent request = live context),
    `total_token_usage` and `model_context_window`."""
    rollout = _find_rollout_file(session_id)
    if rollout is None:
        return {}
    info: dict = {}
    try:
        with rollout.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"token_count"' not in line:
                    continue
                try:
                    payload = json.loads(line).get("payload", {})
                except json.JSONDecodeError:
                    continue
                if payload.get("type") == "token_count" and payload.get("info"):
                    info = payload["info"]
    except OSError:
        return {}
    return info


def _context_window(token_state: dict, metadata: dict) -> int | None:
    env = os.environ.get("CODEX_DELEGATE_CONTEXT_WINDOW")
    if env and env.isdigit():
        return int(env)
    w = token_state.get("model_context_window")
    if isinstance(w, int) and w > 0:
        return w
    return (metadata.get("usage") or {}).get("context_window")


def _context_tokens(token_state: dict) -> int | None:
    last = token_state.get("last_token_usage") or {}
    n = int(last.get("input_tokens") or 0) + int(last.get("output_tokens") or 0)
    return n or None


# ---------------------------------------------------------------------------
# Event stream
# ---------------------------------------------------------------------------

class _StreamState:
    def __init__(self) -> None:
        self.thread_id: str | None = None
        self.last_message: str | None = None
        self.usage: dict | None = None
        self.error: str | None = None
        self.turn_failed = False
        self.file_changes = 0
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
        if etype == "thread.started":
            self.thread_id = event.get("thread_id") or self.thread_id
        elif etype == "item.completed":
            item = event.get("item") or {}
            itype = item.get("type")
            if itype == "agent_message" and item.get("text"):
                self.last_message = item["text"]
            elif itype == "file_change":
                self.file_changes += len(item.get("changes") or [])
            elif itype == "command_execution":
                self.commands += 1
        elif etype == "turn.completed":
            self.usage = event.get("usage") or self.usage
        elif etype == "turn.failed":
            self.turn_failed = True
            self.error = (event.get("error") or {}).get("message") or json.dumps(event)
        elif etype == "error":
            self.error = event.get("message") or json.dumps(event)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _build_cmd(metadata: dict, report_file: Path, project_dir: Path,
               session_id: str | None, reasoning_effort: str | None) -> list[str]:
    flags = ["--json", "--sandbox", "workspace-write"]
    if metadata.get("network"):
        flags += ["-c", "sandbox_workspace_write.network_access=true"]
    if metadata.get("model"):
        flags += ["--model", metadata["model"]]
    if reasoning_effort:
        flags += ["-c", f"model_reasoning_effort={reasoning_effort}"]
    if session_id:
        return ["codex", "exec", *flags, "-o", str(report_file), "resume", session_id, "-"]
    return ["codex", "exec", *flags, "--cd", str(project_dir), "-o", str(report_file), "-"]


def _account(metadata: dict, round_num: int, state: _StreamState, session_id: str | None) -> dict:
    """Record token usage and live context for this attempt. Runs on every
    exit path so failed turns still advance the context guard."""
    usage = metadata.setdefault("usage", {"rounds": {}, "session_input_tokens": 0, "session_output_tokens": 0})
    token_state = _rollout_token_state(session_id) if session_id else {}
    turn = state.usage or {}
    total = token_state.get("total_token_usage") or {}
    if total:
        # The rollout's cumulative totals are authoritative for every attempt
        # (completed or killed): charge the delta since the previous attempt.
        # A resumed turn's `turn.completed.usage` overlaps the killed attempt
        # already charged from the rollout, so it is never added on top.
        prev_total = usage.get("rollout_total") or {}
        in_tok = max(0, int(total.get("input_tokens") or 0) - int(prev_total.get("input_tokens") or 0))
        out_tok = max(0, int(total.get("output_tokens") or 0) - int(prev_total.get("output_tokens") or 0))
        usage["rollout_total"] = total
        usage_complete = True
    elif turn:
        in_tok = int(turn.get("input_tokens") or 0)
        out_tok = int(turn.get("output_tokens") or 0)
        usage_complete = True
        # Keep the cumulative baseline in step so a later attempt that does
        # find the rollout charges only its own delta.
        prev_total = usage.get("rollout_total") or {}
        usage["rollout_total"] = {
            "input_tokens": int(prev_total.get("input_tokens") or 0) + in_tok,
            "output_tokens": int(prev_total.get("output_tokens") or 0) + out_tok,
            "estimated": True,
        }
    else:
        in_tok = out_tok = 0
        usage_complete = False  # killed before any usage was recorded anywhere
    rounds = usage.setdefault("rounds", {})
    prev = rounds.get(str(round_num)) or {}
    rounds[str(round_num)] = {
        "input_tokens": int(prev.get("input_tokens") or 0) + in_tok,
        "cached_input_tokens": int(prev.get("cached_input_tokens") or 0) + int(turn.get("cached_input_tokens") or 0),
        "output_tokens": int(prev.get("output_tokens") or 0) + out_tok,
        "reasoning_output_tokens": int(prev.get("reasoning_output_tokens") or 0) + int(turn.get("reasoning_output_tokens") or 0),
        "file_changes": int(prev.get("file_changes") or 0) + state.file_changes,
        "commands": int(prev.get("commands") or 0) + state.commands,
        "attempts": int(prev.get("attempts") or 0) + 1,
        "usage_complete": bool(prev.get("usage_complete", True)) and usage_complete,
    }
    usage["session_input_tokens"] = int(usage.get("session_input_tokens") or 0) + in_tok
    usage["session_output_tokens"] = int(usage.get("session_output_tokens") or 0) + out_tok
    window = _context_window(token_state, metadata)
    fresh = _context_tokens(token_state)
    # A killed turn may not have written a fresh token_count; the previous
    # value is then still the thread's true size, so keep it.
    usage["last_context_tokens"] = fresh or usage.get("last_context_tokens")
    usage["context_window"] = window
    usage["context_pct"] = (
        round(100.0 * usage["last_context_tokens"] / window, 1)
        if (window and usage["last_context_tokens"]) else None
    )
    rec = rounds[str(round_num)]
    return {
        "attempt_input_tokens": in_tok,
        "attempt_output_tokens": out_tok,
        "round_input_tokens": rec["input_tokens"],
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
    keep_stream = keep_stream or os.environ.get("CODEX_DELEGATE_KEEP_STREAM", "").strip().lower() in ("1", "true", "yes", "on")
    load_metadata(session_path)  # fail early on a missing/corrupt file
    with SessionLock(session_path):
        metadata = load_metadata(session_path)  # re-read under the lock
        return _run_locked(session_path, metadata, project_dir, timeout, stall, reasoning_effort, keep_stream, skip_verify, rerun)


def _run_locked(session_path, metadata, project_dir, timeout, stall, reasoning_effort, keep_stream, skip_verify, rerun) -> dict:
    round_num, project_dir = preflight(metadata, session_path, rerun, project_dir)
    session_id = metadata.get("codex_session_id")
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

    # A stale report from a killed attempt must never be mistaken for this
    # attempt's result: Codex rewrites `-o` only when the turn completes.
    report_file.unlink(missing_ok=True)

    baseline = round_baseline(metadata, round_num, project_dir)
    attempt = int((metadata.get("usage", {}).get("rounds", {}).get(str(round_num)) or {}).get("attempts") or 0) + 1
    cmd = _build_cmd(metadata, report_file, project_dir, session_id, effort)

    def _save() -> None:
        save_metadata(session_path, metadata)

    metadata["status"] = "running"
    _save()

    try:
        with open(brief_file) as stdin_file:
            process = subprocess.Popen(
                cmd, stdin=stdin_file, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=str(project_dir),  # `resume` has no --cd; Codex needs cwd inside the repo
                start_new_session=True,  # own process group so kill_tree() reaches children
            )
    except OSError as exc:
        metadata["status"] = "failed"
        _save()
        print(f"Error: could not launch codex: {exc}", file=sys.stderr)
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
        _account(metadata, round_num, state, metadata.get("codex_session_id"))
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
                if state.thread_id and metadata.get("codex_session_id") != state.thread_id:
                    metadata["codex_session_id"] = state.thread_id  # persist early: a later kill can still resume
                    _save()
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
        print(f"Warning: killed {stragglers} process(es) Codex left running after it exited.", file=sys.stderr)

    session_id = metadata.get("codex_session_id")

    # Report: the `-o` file is written only when the turn completes; fall
    # back to the last agent_message seen in the stream.
    report_text = ""
    if report_file.exists() and report_file.stat().st_size > 0:
        report_text = report_file.read_text()
    elif state.last_message:
        report_text = state.last_message.rstrip() + "\n"
        report_file.write_text(report_text)

    # Codex can linger after `turn.completed` (MCP servers shutting down). If
    # the turn finished and the report is on disk, the deadline is moot.
    killed_by_wrapper = timed_out or stalled
    lingered = False
    if (timed_out or stalled) and state.usage is not None and report_text.strip():
        lingered = True
        timed_out = stalled = False

    # Change summary against the round's first-attempt baseline, taken BEFORE
    # verify commands run so their artifacts do not pollute it.
    after = git_snapshot(project_dir)
    changes = summarize_changes(project_dir, baseline, after)
    usage_out = _account(metadata, round_num, state, session_id)

    stderr_tail = "".join(stderr_lines).strip()
    retry_hint = (
        f"  - Re-run `run_task.py` with the same --session. The round {round_num} brief is "
        f"still on disk — do NOT call `write_brief.py` again."
    )

    def _tail(msg: str) -> str:
        if changes["files_touched"]:
            msg += f"\n\nFiles touched so far this round ({len(changes['files_touched'])}): see {changes_file}"
        if session_id:
            msg += f"\n\nSession ID for resume: {session_id}"
        msg += f"\nContext: {usage_out['context_pct']}% of window ({usage_out['context_status']})"
        if stderr_tail:
            msg += f"\n\nLast stderr output:\n{stderr_tail}"
        msg += f"\nRaw event stream: {stream_file}"
        return msg

    def _fail(msg: str, code: int) -> None:
        write_changes_file(changes_file, changes, [], attempt_note=f"Attempt {attempt} FAILED (exit {code}); summary vs. round baseline")
        metadata["status"] = "failed"
        metadata["last_round_failed"] = round_num  # write_brief.py refuses to advance past it without --force
        _save()
        print(_tail(msg), file=sys.stderr)
        sys.exit(code)

    if timed_out:
        _fail(
            f"Error: Codex task timed out after {timeout}s (process killed).\n\n"
            f"What to try next:\n{retry_hint}\n"
            f"  - Codex kept its thread; a re-run resumes it. If the task is too big for one "
            f"round, split it: write a narrower follow-up brief (--force) or hand off.\n"
            f"  - Pass a longer `--timeout` (current: {timeout}s); `--timeout 0` disables.",
            2,
        )
    if stalled:
        _fail(
            f"Error: Codex went silent — no stdout events for {stall}s (process killed).\n\n"
            f"Usually a dropped model stream. What to try next:\n{retry_hint}\n"
            f"  - Pass `--stall 0` to disable stall detection if a single command legitimately "
            f"runs that long (e.g. a slow test suite).",
            4,
        )
    if process.returncode is not None and process.returncode < 0 and not killed_by_wrapper:
        sig = -process.returncode
        _fail(
            f"Error: Codex was killed by signal {sig} (external kill). Check with the user "
            f"before retrying; then re-run `run_task.py` with the same --session.",
            128 + sig,
        )
    if (process.returncode != 0 and not lingered) or state.error or state.turn_failed:
        msg = f"Error: Codex exited with code {process.returncode}"
        if state.error:
            msg += f"\nCodex error: {state.error}"
        if report_text:
            msg += f"\n(partial report written: {report_file})"
        msg += (
            "\n\nWhat to try next:\n"
            "  - Inspect the error above. Re-run `run_task.py` with the same --session if it "
            "looks transient (network, rate limit, auth refresh).\n"
            "  - `Not inside a trusted directory` means the project dir is not a git repo."
        )
        _fail(msg, 1)
    if not report_text.strip():
        _fail(
            "Error: Codex exited cleanly but produced no final message (no report).\n\n"
            "What to try next (in order):\n"
            f"  1. {retry_hint.strip()}\n"
            "  2. If it happens again, the thread is likely dead: hand off to a fresh "
            "session with `handoff_session.py`.",
            3,
        )

    # --- Success path ---------------------------------------------------------
    verify_cmds = [] if skip_verify else list(metadata.get("verify") or [])
    verify_results = run_verify(verify_cmds, project_dir) if verify_cmds else []
    write_changes_file(changes_file, changes, verify_results, attempt_note=(f"Attempt {attempt} of this round" if attempt > 1 else None))

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
        warnings.append(f"Codex left {stragglers} background process(es) running after exit; the wrapper killed them.")
    if lingered:
        warnings.append("The turn completed but the process outlived the timeout/stall window and was killed while shutting down; the report is valid.")
    if status == "UNKNOWN":
        warnings.append("Report has no parsable `## Status` — Codex ignored the contract; read the report carefully and consider a follow-up asking for the required format.")
    if changes["git_state_changed"] and not metadata.get("allow_git"):
        warnings.append("Codex changed git state (HEAD/branch/index) although the session forbids it — inspect rN-changes.md.")
    if status == "DONE" and not changes["files_touched"] and state.file_changes == 0:
        warnings.append("Report says DONE but no files changed this round — verify the task really needed no edits.")
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
        "report_file": str(report_file),
        "changes_file": str(changes_file),
        "brief_file": str(brief_file),
        "stream_file": str(stream_file) if keep_stream else None,
        "files_touched": changes["files_touched"],
        "lines_added": changes["lines_added"],
        "lines_deleted": changes["lines_deleted"],
        "git_state_changed": changes["git_state_changed"],
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
    parser = argparse.ArgumentParser(description="Run or resume a delegated Codex task round")
    parser.add_argument("--session", required=True, help="Path to session metadata JSON file")
    parser.add_argument("--cd", default=None, help="Project directory; must equal the session's persisted project_dir (sanity check only)")
    parser.add_argument("--timeout", type=_non_negative_int, default=_DEFAULT_TIMEOUT, help=f"Max wall-clock seconds (default {_DEFAULT_TIMEOUT}; 0 disables; exit 2)")
    parser.add_argument("--stall", type=_non_negative_int, default=_DEFAULT_STALL, help=f"Seconds without stdout events before a stall kill (default {_DEFAULT_STALL}; 0 disables; exit 4)")
    parser.add_argument("--reasoning-effort", default=None, help="Reasoning-effort override for this round (persisted on success)")
    parser.add_argument("--keep-stream", action="store_true", help="Keep rN-stream.jsonl after a successful round (default: only kept on failure). CODEX_DELEGATE_KEEP_STREAM=1 does the same.")
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
