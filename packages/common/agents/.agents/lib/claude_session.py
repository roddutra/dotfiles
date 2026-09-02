#!/usr/bin/env python3
"""Session-safe non-interactive Claude Code runner shared by Claude skills."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HOME = Path.home()
VALID_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
VERIFY_TIMEOUT = 900
VERIFY_PASS_MAX_LINES = 12
VERIFY_FAIL_MAX_LINES = 30
VERIFY_PASS_MAX_CHARS = 2_000
VERIFY_FAIL_MAX_CHARS = 6_000

ANSI_ESCAPE_RE = re.compile(
    r"\x1b(?:\][^\x07\x1b]*(?:\x07|\x1b\\|$)|\[[0-?]*[ -/]*[@-~]|[@-_])"
)
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PROGRESS_ONLY_RE = re.compile(r"^\s*[.·•]+\s*$")
STATUS_RE = re.compile(
    r"^\W*STATUS:\s*(DONE|PARTIAL|BLOCKED)\b",
    re.MULTILINE | re.IGNORECASE,
)
READ_ONLY_SYSTEM_PROMPT = (
    "You are a read-only reviewer. Do not create, edit, or delete files. "
    "Do not invoke external tools that change state. Return analysis as text only."
)


class ClaudeTimeout(Exception):
    def __init__(self, stdout: str, stderr: str, seconds: int) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.seconds = seconds
        super().__init__(f"Claude timed out after {seconds} seconds")


def fail(message: str, code: int = 1) -> None:
    print(json.dumps({"error": message, "exit_code": code}), file=sys.stderr)
    raise SystemExit(code)


def slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not result:
        fail("title must contain letters or numbers")
    return result[:80]


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="surrogateescape",
        capture_output=True,
    )


def run_git_bytes(args: list[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True)


def project_root(start: Path) -> Path:
    result = run_git(["rev-parse", "--show-toplevel"], start)
    if result.returncode:
        fail("Claude sessions require a git working tree")
    bare = run_git(["rev-parse", "--is-bare-repository"], start)
    if bare.stdout.strip() == "true":
        fail("bare repositories cannot host Claude sessions")
    return Path(result.stdout.strip()).resolve()


def stable_project_name(root: Path) -> str:
    listing = run_git(["worktree", "list", "--porcelain"], root)
    if listing.returncode:
        return slug(root.name)
    for line in listing.stdout.splitlines():
        if line.startswith("worktree "):
            return slug(Path(line[len("worktree ") :]).resolve().name)
    return slug(root.name)


def ensure_tmp(root: Path) -> None:
    (root / ".tmp").mkdir(exist_ok=True)
    gitignore = root / ".gitignore"
    lines = gitignore.read_text().splitlines() if gitignore.exists() else []
    if ".tmp/" not in lines:
        with gitignore.open("a") as handle:
            if lines:
                handle.write("\n")
            handle.write(".tmp/\n")


def read_metadata(session: Path) -> dict[str, Any]:
    try:
        metadata = json.loads(session.read_text())
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read session metadata: {error}")
    if not isinstance(metadata, dict) or metadata.get("kind") not in {"review", "task"}:
        fail("invalid session metadata")
    return metadata


def require_kind(metadata: dict[str, Any], expected: str) -> None:
    if metadata["kind"] != expected:
        fail(f"session kind is {metadata['kind']}, expected {expected}")


def write_metadata(session: Path, metadata: dict[str, Any]) -> None:
    temporary = session.with_suffix(".tmp")
    temporary.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    temporary.replace(session)


class SessionLock:
    """Kernel-released advisory lock preventing concurrent session mutation."""

    def __init__(self, session: Path) -> None:
        self.path = session.with_name("session.lock")
        self.fd: int | None = None

    def __enter__(self) -> SessionLock:
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                pid = os.read(fd, 32).decode().strip()
            except OSError:
                pid = "?"
            os.close(fd)
            fail(
                f"another wrapper process (pid {pid}) is using this session; "
                "wait for its completion notification instead of launching a duplicate"
            )
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        self.fd = fd
        return self

    def remove(self) -> None:
        self.path.unlink(missing_ok=True)

    def __exit__(self, *_: object) -> None:
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
            self.fd = None


def session_base(kind: str) -> Path:
    return HOME / (".claude-reviews" if kind == "review" else ".claude-delegate")


def unique_session_directory(kind: str, project: str, title: str, now: datetime) -> Path:
    parent = session_base(kind) / project / now.strftime("%Y-%m-%d")
    stem = f"{now:%H%M%S}-{slug(title)}"
    candidate = parent / stem
    suffix = 2
    while candidate.exists():
        candidate = parent / f"{stem}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def init_session(args: argparse.Namespace) -> None:
    root = project_root(Path.cwd())
    ensure_tmp(root)
    derived_project = stable_project_name(root)
    project = slug(args.force_project) if args.force_project else derived_project
    warnings = []
    if args.project and not args.force_project:
        warnings.append(
            f"ignored --project inside a git work tree; using {derived_project}. "
            "Use --force-project for deliberate regrouping."
        )
    now = datetime.now(UTC)
    directory = unique_session_directory(args.kind, project, args.title, now)
    metadata: dict[str, Any] = {
        "kind": args.kind,
        "title": args.title,
        "project": project,
        "project_dir": str(root),
        "created_at": now.isoformat(),
        "model": args.model,
        "effort": args.effort,
        "round": 0,
        "claude_session_id": str(uuid.uuid4()),
        "claude_session_started": False,
        "verify": getattr(args, "verify", None) or [],
        "verify_timeout": getattr(args, "verify_timeout", VERIFY_TIMEOUT),
        "allow_git": getattr(args, "allow_git", False),
    }
    session = directory / "session.json"
    write_metadata(session, metadata)
    print(
        json.dumps(
            {
                "session": str(session),
                "project_dir": str(root),
                "warnings": warnings,
            }
        )
    )


def next_round(session: Path, force: bool) -> tuple[dict[str, Any], int]:
    metadata = read_metadata(session)
    round_number = int(metadata["round"]) + 1
    if metadata["round"] and not force:
        output = session.parent / f"r{metadata['round']}-output.md"
        if not output.exists() or not output.read_text().strip():
            fail("previous round has no output; rerun it or pass --force")
    return metadata, round_number


def write_round(args: argparse.Namespace) -> None:
    session = Path(args.session).expanduser().resolve()
    with SessionLock(session):
        metadata, round_number = next_round(session, args.force)
        require_kind(metadata, args.kind)
        content = sys.stdin.read().strip()
        if not content:
            fail("prompt must not be empty")
        if metadata["kind"] == "task":
            required_done = "## Done when" in content or "## Acceptance" in content
            if round_number == 1 and ("## Task" not in content or not required_done):
                fail("initial task brief requires ## Task and ## Done when or ## Acceptance")
            git_rule = (
                "Git actions are allowed for this task."
                if metadata.get("allow_git")
                else "Do not modify git state."
            )
            content += (
                "\n\n## Executor contract\n"
                "- Work only on this task.\n"
                f"- {git_rule}\n"
                "- Do not stop to ask questions. Resolve reachable ambiguity from the repository.\n"
                "- End with `STATUS: DONE`, `STATUS: PARTIAL`, or `STATUS: BLOCKED`, then a summary of 400 words or fewer and verification results.\n"
            )
        prompt = session.parent / f"r{round_number}-prompt.md"
        if prompt.exists() and not args.force:
            fail(f"round {round_number} already has a prompt")
        prompt.write_text(content + "\n")
        metadata["round"] = round_number
        write_metadata(session, metadata)
    print(
        json.dumps(
            {
                "round": round_number,
                "prompt_path": str(prompt),
                "output_path": str(session.parent / f"r{round_number}-output.md"),
            }
        )
    )


def claude_session_exists(metadata: dict[str, Any]) -> bool:
    session_id = metadata.get("claude_session_id")
    if not session_id:
        return False
    config_dir = Path(
        os.environ.get("CLAUDE_CONFIG_DIR", str(HOME / ".claude"))
    ).expanduser()
    projects = config_dir / "projects"
    return any(projects.glob(f"*/{session_id}.jsonl")) if projects.exists() else False


def session_started(metadata: dict[str, Any]) -> bool:
    return claude_session_exists(metadata)


def claude_command(metadata: dict[str, Any]) -> list[str]:
    command = ["claude", "-p", "--output-format", "json", "--strict-mcp-config"]
    session_id = metadata["claude_session_id"]
    if session_started(metadata):
        command.extend(["--resume", session_id])
    else:
        command.extend(["--session-id", session_id])
    if metadata.get("model"):
        command.extend(["--model", metadata["model"]])
    if metadata.get("effort"):
        command.extend(["--effort", metadata["effort"]])
    if metadata["kind"] == "review":
        command.extend(
            [
                "--restricted",
                "--tools",
                "Read,Glob,Grep",
                "--permission-mode",
                "dontAsk",
                "--disallowedTools",
                "Write,Edit,NotebookEdit",
                "--append-system-prompt",
                READ_ONLY_SYSTEM_PROMPT,
            ]
        )
    else:
        command.extend(["--permission-mode", "acceptEdits"])
    return command


def parse_result(raw: str) -> dict[str, Any]:
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        fail(f"Claude returned invalid JSON: {error}", 3)
    if not isinstance(result, dict):
        fail("Claude returned an invalid result", 3)
    if result.get("is_error"):
        fail(str(result.get("result") or result.get("error") or "Claude request failed"), 1)
    if not result.get("result"):
        fail("Claude returned no final response", 3)
    if not result.get("session_id"):
        fail("Claude returned no session_id", 3)
    return result


def git_state(cwd: Path) -> dict[str, str | None]:
    branch = run_git(["symbolic-ref", "--short", "HEAD"], cwd)
    head = run_git(["rev-parse", "HEAD"], cwd)
    staged = run_git_bytes(["diff", "--cached", "--binary"], cwd)
    return {
        "branch": branch.stdout.strip() if branch.returncode == 0 else None,
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "index": hashlib.sha256(staged.stdout).hexdigest(),
    }


def workspace_state(cwd: Path) -> dict[str, str]:
    result = run_git_bytes(
        ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"],
        cwd,
    )
    if result.returncode:
        fail(f"cannot inspect git workspace: {os.fsdecode(result.stderr).strip()}")
    state = {}
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        status = entry[:2].decode("ascii", errors="replace")
        relative = os.fsdecode(entry[3:])
        path = cwd / relative
        if path.is_symlink():
            digest = hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
        elif path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            digest = "missing"
        state[relative] = f"{status}:{digest}"
    return state


def committed_changes(cwd: Path, before_head: str | None, after_head: str | None) -> tuple[list[str], list[str]]:
    if not before_head or not after_head or before_head == after_head:
        return [], []
    paths_result = run_git_bytes(["diff", "--name-only", "-z", before_head, after_head], cwd)
    paths = [os.fsdecode(path) for path in paths_result.stdout.split(b"\0") if path]
    commits_result = run_git(["log", "--format=%h %s", f"{before_head}..{after_head}"], cwd)
    commits = commits_result.stdout.splitlines() if commits_result.returncode == 0 else []
    return paths, commits


def sanitize_verify_output(output: str, *, passed: bool) -> str:
    cleaned = ANSI_ESCAPE_RE.sub("", output)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = CONTROL_RE.sub("", cleaned)
    lines: list[str] = []
    for raw_line in cleaned.splitlines():
        line = raw_line.rstrip()
        if PROGRESS_ONLY_RE.fullmatch(line):
            continue
        if not line:
            if lines and lines[-1]:
                lines.append("")
            continue
        lines.append(line)
    if lines and not lines[-1]:
        lines.pop()
    max_lines = VERIFY_PASS_MAX_LINES if passed else VERIFY_FAIL_MAX_LINES
    max_chars = VERIFY_PASS_MAX_CHARS if passed else VERIFY_FAIL_MAX_CHARS
    truncated = len(lines) > max_lines
    text = "\n".join(lines[-max_lines:])
    marker = "[... verification output truncated ...]\n"
    if truncated or len(text) > max_chars:
        text = marker + text[-(max_chars - len(marker)) :].lstrip("\n")
    return text


def kill_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass

def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True



@contextlib.contextmanager
def process_guard(process: subprocess.Popen[str]):
    previous = {}

    def handle_signal(signum: int, _frame: object) -> None:
        raise SystemExit(128 + signum)

    for current in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            previous[current] = signal.signal(current, handle_signal)
        except (ValueError, OSError):
            pass
    try:
        yield
    except BaseException:
        if process.poll() is None:
            kill_process_group(process)
            process.wait()
        raise
    finally:
        for current, handler in previous.items():
            signal.signal(current, handler)


def verify_commands(commands: list[str], cwd: Path, timeout: int) -> list[dict[str, Any]]:
    results = []
    for command in commands:
        process = subprocess.Popen(
            ["bash", "-lc", command],
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        with process_guard(process):
            try:
                stdout, _ = process.communicate(timeout=timeout or None)
                passed = process.returncode == 0
                results.append(
                    {
                        "command": command,
                        "passed": passed,
                        "exit_code": process.returncode,
                        "output_tail": sanitize_verify_output(stdout, passed=passed),
                    }
                )
            except subprocess.TimeoutExpired:
                kill_process_group(process)
                process.communicate()
                results.append(
                    {
                        "command": command,
                        "passed": False,
                        "exit_code": None,
                        "output_tail": f"timed out after {timeout}s (process tree killed)",
                    }
                )
    return results


def as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run_claude(
    command: list[str],
    prompt: str,
    cwd: Path,
    timeout: int,
    on_start=None,
) -> tuple[str, str, int]:
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except FileNotFoundError:
        fail("Claude Code CLI was not found", 1)
    if on_start is not None:
        on_start(process.pid)
    with process_guard(process):
        try:
            stdout, stderr = process.communicate(input=prompt, timeout=timeout or None)
        except subprocess.TimeoutExpired as error:
            partial_stdout = as_text(error.stdout)
            partial_stderr = as_text(error.stderr)
            kill_process_group(process)
            remainder_stdout, remainder_stderr = process.communicate()
            raise ClaudeTimeout(
                partial_stdout + as_text(remainder_stdout),
                partial_stderr + as_text(remainder_stderr),
                timeout,
            ) from error
    return stdout, stderr, process.returncode


def parse_status(output: str) -> str:
    match = STATUS_RE.search(output)
    return match.group(1).upper() if match else "UNKNOWN"


def run_round(args: argparse.Namespace) -> None:
    session = Path(args.session).expanduser().resolve()
    with SessionLock(session):
        metadata = read_metadata(session)
        require_kind(metadata, args.kind)
        round_number = int(metadata["round"])
        if not round_number:
            fail("write a prompt or brief before running")
        prompt_file = session.parent / f"r{round_number}-prompt.md"
        if not prompt_file.exists():
            fail(f"round {round_number} prompt is missing")
        output_file = session.parent / f"r{round_number}-output.md"
        if output_file.exists() and not args.rerun:
            fail("round already has output; use --rerun to run it again")

        active_pid = metadata.get("active_pid")
        if active_pid and process_alive(int(active_pid)):
            fail(
                f"Claude process {active_pid} from a prior run is still active; "
                "wait for it or stop it before retrying"
            )
        if active_pid:
            metadata["active_pid"] = None
            write_metadata(session, metadata)

        pending_effort = args.effort or metadata.get("effort")
        run_metadata = {**metadata, "effort": pending_effort}
        root = Path(metadata["project_dir"])
        before_git = git_state(root) if metadata["kind"] == "task" else None
        before_workspace = workspace_state(root) if metadata["kind"] == "task" else {}
        command = claude_command(run_metadata)
        result_file = session.parent / f"r{round_number}-result.json"

        def record_active_pid(pid: int) -> None:
            metadata["active_pid"] = pid
            write_metadata(session, metadata)

        try:
            stdout, stderr, returncode = run_claude(
                command,
                prompt_file.read_text(),
                root,
                args.timeout,
                on_start=record_active_pid,
            )
        except ClaudeTimeout as error:
            metadata["active_pid"] = None
            metadata["claude_session_started"] = claude_session_exists(metadata)
            write_metadata(session, metadata)
            result_file.write_text(error.stdout)
            fail(
                f"Claude timed out after {error.seconds} seconds; round {round_number} "
                "prompt remains on disk, so rerun run without writing a new prompt",
                2,
            )

        metadata["active_pid"] = None
        metadata["claude_session_started"] = claude_session_exists(metadata)
        write_metadata(session, metadata)
        result_file.write_text(stdout)
        if returncode:
            tail = stderr[-2000:].strip()
            fail(f"Claude exited {returncode}: {tail or 'no stderr'}", 1)

        result = parse_result(stdout)
        output_file.write_text(str(result["result"]).strip() + "\n")
        metadata["claude_session_id"] = result["session_id"]
        metadata["claude_session_started"] = True
        metadata["effort"] = pending_effort
        write_metadata(session, metadata)

        status = parse_status(str(result["result"])) if metadata["kind"] == "task" else "UNKNOWN"
        changes: dict[str, Any] = {
            "files_touched": [],
            "git_state_changed": False,
            "new_commits": [],
            "verify": [],
            "limitations": ["Ignored paths are not included in files_touched."],
        }
        changes_file = None
        if metadata["kind"] == "task":
            after_workspace = workspace_state(root)
            after_git = git_state(root)
            all_paths = before_workspace.keys() | after_workspace.keys()
            touched = {
                path
                for path in all_paths
                if before_workspace.get(path) != after_workspace.get(path)
            }
            committed_paths, commits = committed_changes(
                root,
                before_git["head"] if before_git else None,
                after_git["head"],
            )
            touched.update(committed_paths)
            changes["files_touched"] = sorted(touched)
            changes["git_state_changed"] = before_git != after_git
            changes["new_commits"] = commits

        verification = (
            []
            if args.skip_verify
            else verify_commands(
                metadata.get("verify", []),
                root,
                int(metadata.get("verify_timeout", VERIFY_TIMEOUT)),
            )
        )
        changes["verify"] = verification
        if metadata["kind"] == "task":
            changes_file = session.parent / f"r{round_number}-changes.json"
            changes_file.write_text(json.dumps(changes, indent=2) + "\n")

        warnings = []
        if status == "UNKNOWN" and metadata["kind"] == "task":
            warnings.append("Claude did not return the required STATUS line")
        if changes["git_state_changed"] and not metadata.get("allow_git"):
            warnings.append("Claude changed protected git state")
        if verification and not all(item["passed"] for item in verification):
            warnings.append("one or more verification commands failed")

        usage = result.get("usage", {})
        response = {
            "session_id": result["session_id"],
            "round": round_number,
            "output_file": str(output_file),
            "changes_file": str(changes_file) if changes_file else None,
            "status": status,
            "files_touched": changes["files_touched"],
            "git_state_changed": changes["git_state_changed"],
            "verify_passed": (
                all(item["passed"] for item in verification) if verification else None
            ),
            "warnings": warnings,
            "usage": {
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "duration_api_ms": result.get("duration_api_ms"),
            },
        }
    print(json.dumps(response))


def list_sessions(args: argparse.Namespace) -> None:
    root = session_base(args.kind)
    sessions = []
    warnings = []
    if root.exists():
        for session in root.glob("*/*/*/session.json"):
            try:
                metadata = json.loads(session.read_text())
                if not isinstance(metadata, dict) or metadata.get("kind") != args.kind:
                    raise ValueError("wrong or missing session kind")
                if args.project and metadata.get("project") != slug(args.project):
                    continue
                sessions.append({"session": str(session), **metadata})
            except (OSError, json.JSONDecodeError, ValueError) as error:
                warnings.append(f"skipped {session}: {error}")
    sessions.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    print(json.dumps({"sessions": sessions, "warnings": warnings}))


def cleanup(args: argparse.Namespace) -> None:
    session = Path(args.session).expanduser().resolve()
    if session.name != "session.json" or not session.is_file():
        fail("invalid session path")
    metadata = read_metadata(session)
    allowed_root = session_base(metadata["kind"]).resolve()
    if not session.is_relative_to(allowed_root):
        fail("session is outside a Claude wrapper directory")
    directory = session.parent
    import shutil

    with SessionLock(session) as lock:
        lock.remove()
        shutil.rmtree(directory)
    print(json.dumps({"cleaned": str(directory)}))


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="action", required=True)

    for kind, name in (("review", "init-review"), ("task", "init-task")):
        command = actions.add_parser(name)
        command.set_defaults(handler=init_session, kind=kind)
        command.add_argument("--title", required=True)
        command.add_argument("--project")
        command.add_argument("--force-project")
        command.add_argument("--model")
        command.add_argument("--effort", choices=sorted(VALID_EFFORTS))
        if kind == "task":
            command.add_argument("--verify", action="append")
            command.add_argument("--verify-timeout", type=int, default=VERIFY_TIMEOUT)
            command.add_argument("--allow-git", action="store_true")

    for kind, name in (("review", "write-prompt"), ("task", "write-brief")):
        command = actions.add_parser(name)
        command.set_defaults(handler=write_round, kind=kind)
        command.add_argument("--session", required=True)
        command.add_argument("--force", action="store_true")

    for kind, name in (("review", "run-review"), ("task", "run-task")):
        command = actions.add_parser(name)
        command.set_defaults(handler=run_round, kind=kind)
        command.add_argument("--session", required=True)
        command.add_argument("--timeout", type=int, default=1800)
        command.add_argument("--effort", choices=sorted(VALID_EFFORTS))
        command.add_argument("--rerun", action="store_true")
        command.add_argument("--skip-verify", action="store_true")

    for kind, name in (("review", "list-reviews"), ("task", "list-tasks")):
        command = actions.add_parser(name)
        command.set_defaults(handler=list_sessions, kind=kind)
        command.add_argument("--project")

    command = actions.add_parser("cleanup")
    command.set_defaults(handler=cleanup)
    command.add_argument("--session", required=True)
    return parser


if __name__ == "__main__":
    parsed = parser().parse_args()
    parsed.handler(parsed)
