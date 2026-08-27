#!/usr/bin/env python3
"""Shared helpers for the delegate wrappers: atomic metadata writes, a
per-session run lock, git change tracking with a persistent per-round
baseline, verify-command execution, and report status parsing.

This file is identical in delegate-to-codex and delegate-to-grok.
"""

import contextlib
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

_VERIFY_TIMEOUT = 900

_STATUS_RE = re.compile(
    r"^\s{0,3}#{1,6}\s*status\s*\n+\s*\**\s*(DONE|PARTIAL|BLOCKED)\b",
    re.IGNORECASE | re.MULTILINE,
)
_STATUS_FALLBACK_RE = re.compile(r"\b(DONE|PARTIAL|BLOCKED)\b")

# Untracked build/cache noise that is not a meaningful change. Applied to
# untracked paths only — tracked files under e.g. dist/ are real changes.
_NOISE_RE = re.compile(
    r"(^|/)(__pycache__|node_modules|\.tmp|\.worktrees|\.pytest_cache|\.mypy_cache|"
    r"\.ruff_cache|\.cache|coverage|\.coverage)(/|$)|\.(pyc|pyo|log)$"
)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def save_metadata(session_path: Path, metadata: dict) -> None:
    """Atomic write (temp file + rename) so an interrupted write cannot leave
    a half-written session.json behind."""
    tmp = session_path.with_name(session_path.name + ".tmp")
    tmp.write_text(json.dumps(metadata, indent=2))
    os.replace(tmp, session_path)


def load_metadata(session_path: Path) -> dict:
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(session_path.read_text())
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in session file: {session_path}", file=sys.stderr)
        sys.exit(1)


class SessionLock:
    """Exclusive per-session lock on `session.lock` (advisory `flock`).

    Prevents two mutators (run_task/write_brief/handoff/cleanup) from
    racing on the same session. The kernel releases the flock when the
    holder dies, so a stale lock can never linger and no reclaim race
    exists; the file only records the holder's pid for the error message.
    """

    def __init__(self, session_path: Path) -> None:
        self.path = session_path.with_name("session.lock")
        self.fd: int | None = None

    def __enter__(self) -> "SessionLock":
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                pid = os.read(fd, 32).decode().strip()
            except OSError:
                pid = "?"
            os.close(fd)
            print(
                f"Error: another delegate script (pid {pid}) is already working on this "
                f"session. Wait for its completion notification instead of "
                f"launching a duplicate. (Lock: {self.path})",
                file=sys.stderr,
            )
            sys.exit(1)
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        self.fd = fd
        return self

    def remove(self) -> None:
        """Delete the lock file while still holding it (cleanup only)."""
        self.path.unlink(missing_ok=True)

    def __exit__(self, *exc) -> None:
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
            self.fd = None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _descendants(pid: int) -> list[int]:
    """All descendant pids of `pid` (depth-first), via `pgrep -P`."""
    out: list[int] = []
    stack = [pid]
    while stack:
        parent = stack.pop()
        try:
            r = subprocess.run(["pgrep", "-P", str(parent)], capture_output=True, text=True)
        except FileNotFoundError:
            break
        for line in r.stdout.split():
            if line.isdigit():
                child = int(line)
                out.append(child)
                stack.append(child)
    return out


def kill_tree(process: subprocess.Popen) -> None:
    """Kill the executor and everything it spawned, so a timed-out test run
    cannot outlive the wrapper. The executor runs in its own process group,
    but CLIs may start commands in further groups (Grok does), so descendants
    are enumerated first and killed individually as well."""
    kids = _descendants(process.pid) + _session_members(process.pid)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    for pid in [process.pid, *kids]:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def _session_members(sid: int) -> list[int]:
    """Pids belonging to the executor's session (start_new_session=True gives
    it its own sid, inherited by every descendant even when a CLI puts
    commands into separate process groups or they get reparented)."""
    try:
        r = subprocess.run(["ps", "-eo", "pid=,sid="], capture_output=True, text=True)
    except FileNotFoundError:
        return []
    out = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit() and int(parts[1]) == sid and int(parts[0]) != os.getpid():
            out.append(int(parts[0]))
    return out


def reap_stragglers(process: subprocess.Popen) -> int:
    """After the executor exited, kill anything it left behind (backgrounded
    or separately grouped commands). Returns the number of pids killed."""
    killed = 0
    for _ in range(5):  # rescan: a survivor may fork between enumeration and kill
        members = _session_members(process.pid)
        if not members:
            break
        for pid in members:
            try:
                os.kill(pid, signal.SIGKILL)
                killed += 1
            except (ProcessLookupError, PermissionError, OSError):
                pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    return killed


@contextlib.contextmanager
def executor_guard(process: subprocess.Popen, on_abort=None):
    """While the executor runs, make sure it cannot outlive the wrapper:
    SIGTERM/SIGINT/SIGHUP are turned into SystemExit and any exception or
    exit kills the whole executor tree first, then calls `on_abort` (so the
    caller can persist accounting/failure state) before re-raising.
    (SIGKILL cannot be caught — after a hard kill of the wrapper, check for
    a stray executor before re-running.)"""
    def _handler(signum, _frame):
        raise SystemExit(128 + signum)
    previous = {}
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            previous[sig] = signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass
    try:
        yield
    except BaseException:
        if process.poll() is None:
            kill_tree(process)
            process.wait()
        reap_stragglers(process)
        if on_abort is not None:
            try:
                on_abort()
            except Exception as exc:  # never mask the original failure
                print(f"Warning: could not persist abort state: {exc}", file=sys.stderr)
        raise
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

def git(args: list[str], cwd: Path) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""
    except FileNotFoundError:
        return ""


def git_snapshot(project_dir: Path) -> dict:
    """HEAD, branch, staged paths, and a fingerprint (size, mtime_ns) of every
    dirty file, so a later round that re-edits an already-dirty file is still
    detected. Untracked noise (caches, build output) is dropped."""
    status = git(["status", "--porcelain", "--untracked-files=all"], project_dir)
    files: dict[str, list | None] = {}
    for line in status.splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if code == "??" and _NOISE_RE.search(path):
            continue
        try:
            st = (project_dir / path).stat()
            files[path] = [st.st_size, st.st_mtime_ns]
        except OSError:
            files[path] = None  # deleted
    staged = sorted(git(["diff", "--cached", "--name-only"], project_dir).splitlines())
    return {
        "head": git(["rev-parse", "HEAD"], project_dir).strip() or None,
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], project_dir).strip() or None,
        "staged": staged,
        "dirty_files": files,
    }


def round_baseline(metadata: dict, round_num: int, project_dir: Path) -> dict:
    """The git snapshot taken before the FIRST attempt of this round. Persisted
    in session.json so a retry after a timeout/stall still reports every file
    the round touched, not just the retry's delta."""
    baselines = metadata.setdefault("baselines", {})
    key = str(round_num)
    if key not in baselines:
        baselines[key] = git_snapshot(project_dir)
    return baselines[key]


def summarize_changes(project_dir: Path, before: dict, after: dict) -> dict:
    """Compute the round's change summary. Call BEFORE running verify
    commands so their build artifacts do not pollute the numbers."""
    before_files = before.get("dirty_files") or {}
    after_files = after.get("dirty_files") or {}
    touched = sorted(
        p for p, fp in after_files.items() if before_files.get(p, "absent") != fp
    ) + sorted(p for p in before_files if p not in after_files)  # reverted/deleted
    head_moved = before.get("head") != after.get("head") or before.get("branch") != after.get("branch")
    index_changed = (before.get("staged") or []) != (after.get("staged") or [])
    diffstat = git(["diff", "--stat", "HEAD", "--"], project_dir).strip()
    untracked = git(["ls-files", "--others", "--exclude-standard"], project_dir).strip()
    untracked_list = [u for u in untracked.splitlines() if not _NOISE_RE.search(u)]
    added = deleted = 0
    for line in git(["diff", "--numstat", "HEAD", "--"], project_dir).splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            added += int(parts[0])
            deleted += int(parts[1])
    untracked_set = set(untracked_list)
    for f in touched:  # new files are invisible to `git diff HEAD`
        if f in untracked_set:
            try:
                with open(project_dir / f, "rb") as fh:
                    added += sum(1 for _ in fh)
            except OSError:
                pass
    new_commits = ""
    if head_moved and before.get("head") and after.get("head"):
        new_commits = git(["log", "--oneline", f"{before['head']}..{after['head']}"], project_dir).strip()
        # Committed work leaves a clean tree; count the committed files too.
        committed = git(["diff", "--name-only", f"{before['head']}..{after['head']}"], project_dir).splitlines()
        touched = sorted(set(touched) | {c for c in committed if c.strip()})
        for line in git(["diff", "--numstat", f"{before['head']}..{after['head']}"], project_dir).splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                added += int(parts[0])
                deleted += int(parts[1])
    return {
        "files_touched": touched,
        "lines_added": added,
        "lines_deleted": deleted,
        "git_state_changed": head_moved or index_changed,
        "head_moved": head_moved,
        "index_changed": index_changed,
        "diffstat": diffstat,
        "untracked": untracked_list,
        "new_commits": new_commits,
        "before": {"head": before.get("head"), "branch": before.get("branch")},
        "after": {"head": after.get("head"), "branch": after.get("branch")},
    }


def write_changes_file(
    changes_path: Path, summary: dict, verify_results: list[dict],
    blocked_calls: list[str] | None = None, attempt_note: str | None = None,
) -> None:
    b, a = summary["before"], summary["after"]
    lines = ["# Changes — round summary", ""]
    if attempt_note:
        lines.append(f"- {attempt_note}")
    lines.append(f"- Branch: `{a['branch']}` (was `{b['branch']}`)")
    lines.append(f"- HEAD: `{(a['head'] or '')[:12]}` (was `{(b['head'] or '')[:12]}`)")
    if summary["head_moved"]:
        lines.append("- **HEAD/branch moved during this round.**")
    if summary["index_changed"]:
        lines.append("- **The git index (staged files) changed during this round.**")
    if summary["new_commits"]:
        lines += ["", "## New commits", "```", summary["new_commits"], "```"]
    lines.append(f"- Files touched this round: {len(summary['files_touched'])}")
    lines.append(f"- Working tree vs HEAD: +{summary['lines_added']} / -{summary['lines_deleted']} lines (new files counted in full)")
    if summary["files_touched"]:
        lines += ["", "## Files touched this round", *[f"- `{f}`" for f in summary["files_touched"]]]
    if summary["diffstat"]:
        lines += ["", "## git diff --stat HEAD", "```", summary["diffstat"], "```"]
    if summary["untracked"]:
        lines += ["", "## Untracked files (all, noise filtered)", "```", *summary["untracked"], "```"]
    if blocked_calls:
        lines += ["", "## Tool calls blocked by policy", *[f"- {c[:300]}" for c in blocked_calls[:10]]]
    if verify_results:
        lines += ["", "## Verify commands (run unsandboxed on the host by the wrapper)"]
        for v in verify_results:
            mark = "PASS" if v["passed"] else "FAIL"
            lines.append(f"- [{mark}] `{v['command']}` (exit {v['exit_code']})")
            if v["output_tail"]:
                lines += ["  ```", *["  " + l for l in v["output_tail"].splitlines()], "  ```"]
    changes_path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def run_verify(commands: list[str], project_dir: Path) -> list[dict]:
    """Run lead-chosen acceptance commands on the host (NOT inside the
    executor sandbox — they carry the same trust as the lead running the
    test suite itself). Each runs in its own process group so a timeout
    kills the whole tree, not just the shell."""
    results = []
    for cmd in commands:
        proc = subprocess.Popen(
            ["bash", "-lc", cmd], cwd=project_dir, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, start_new_session=True,
        )
        try:
            out, _ = proc.communicate(timeout=_VERIFY_TIMEOUT)
            tail = "\n".join(out.strip().splitlines()[-30:])
            results.append({"command": cmd, "exit_code": proc.returncode, "passed": proc.returncode == 0, "output_tail": tail})
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            proc.communicate()
            results.append({"command": cmd, "exit_code": None, "passed": False, "output_tail": f"timed out after {_VERIFY_TIMEOUT}s (process tree killed)"})
    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def extract_status(report: str) -> str | None:
    m = _STATUS_RE.search(report)
    if m:
        return m.group(1).upper()
    m = _STATUS_FALLBACK_RE.search(report[:400])
    return m.group(1).upper() if m else None


def context_status(pct: float | None, warn_pct: int, block_pct: int) -> str:
    if pct is None:
        return "unknown"
    if pct >= block_pct:
        return "handoff-required"
    if pct >= warn_pct:
        return "handoff-soon"
    return "ok"


def preflight(metadata: dict, session_path: Path, force_rerun: bool, cd_override: Path | None = None) -> tuple[int, Path]:
    """Common checks before launching an executor. Returns (round, project_dir)."""
    round_num = metadata.get("current_round", 0)
    if cd_override is not None and metadata.get("project_dir"):
        try:
            same = cd_override.resolve() == Path(metadata["project_dir"]).resolve()
        except OSError:
            same = False
        if not same:
            print(
                f"Error: --cd {cd_override} differs from this session's project_dir "
                f"({metadata['project_dir']}). A session is bound to one checkout (its git "
                f"baselines and the executor's conversation refer to it); start a new "
                f"session for another directory.",
                file=sys.stderr,
            )
            sys.exit(1)
    if round_num == 0:
        print("Error: No brief written yet. Run write_brief.py first.", file=sys.stderr)
        sys.exit(1)
    if metadata.get("status") == "handed-off":
        print(
            f"Error: this session was handed off to {metadata.get('handoff_to')}. "
            f"Continue there; do not resume a handed-off session.",
            file=sys.stderr,
        )
        sys.exit(1)
    if metadata.get("completed_round") == round_num and not force_rerun:
        print(
            f"Error: round {round_num} already completed successfully (report on disk). "
            f"Write the next brief with write_brief.py instead of re-running this round. "
            f"Pass --rerun to deliberately execute the same brief again.",
            file=sys.stderr,
        )
        sys.exit(1)
    project_dir = Path(metadata["project_dir"]) if metadata.get("project_dir") else Path.cwd()
    if not project_dir.is_dir():
        print(f"Error: project directory does not exist: {project_dir}", file=sys.stderr)
        sys.exit(1)
    return round_num, project_dir
