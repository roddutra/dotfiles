#!/usr/bin/env python3
"""Run or resume a Codex review with safety enforcement.

Auto-detects whether this is an initial review or a follow-up based on
session metadata:
- If codex_session_id is null → initial review (`codex exec`), requires --cd
- If codex_session_id exists → resume (`codex exec resume`)

Reads the current round from session metadata to locate the correct prompt
and output files. The round must have been set by write_prompt.py beforehand.

Safety: This script hardcodes --sandbox read-only. The command is constructed
internally with no mechanism to inject other flags.
"""

import argparse
import collections
import json
import re
import signal
import subprocess
import sys
from pathlib import Path

from generate_path import generate_paths

# Absolute-path prefixes that commonly appear in prompts and indicate
# files outside the project directory.
_EXTERNAL_PATH_RE = re.compile(
    r"(?:"
    r"/(?:Users|home|tmp|private/tmp|var/folders|opt)/\S+"
    r"|"
    r"~/\S+"
    r")"
)


def _warn_external_paths(prompt_file: Path, project_dir: Path) -> None:
    """Emit a warning if the prompt references absolute paths outside --cd.

    This catches the common mistake of telling Codex to read files it cannot
    access (e.g. ~/.claude/plans/, /tmp/, files from other projects).
    The warning is non-blocking — it prints to stderr and returns.
    """
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
            f"Codex cannot read files outside --cd. "
            f"Inline the content or copy files into the project.",
            file=sys.stderr,
        )


def run_review(session_path: Path, project_dir: Path | None = None, timeout: int = 0) -> dict:
    """Run or resume a codex review.

    Args:
        session_path: Path to the session metadata JSON file
        project_dir: Working directory for codex (--cd). Required for
            initial reviews, ignored for resumes.
        timeout: Maximum seconds to wait for Codex to complete.
            Defaults to 0 (no timeout). Pass e.g. 1200 for 20 min.

    Returns:
        Dict with session_id, prompt_file, output_file, round, and mode
    """
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    try:
        metadata = json.loads(session_path.read_text())
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in session file: {session_path}", file=sys.stderr)
        sys.exit(1)
    round_num = metadata.get("current_round", 0)
    session_id = metadata.get("codex_session_id")
    is_resume = bool(session_id and session_id != "--last")

    if round_num == 0:
        print("Error: No prompt written yet. Run write_prompt.py first.", file=sys.stderr)
        sys.exit(1)

    # Resolve project_dir: required on first run (and persisted), reused on resumes.
    # On resume, always prefer the saved value — codex exec resume ignores --cd,
    # so the warning must validate against the directory Codex is actually using.
    if is_resume:
        saved_dir = metadata.get("project_dir")
        if saved_dir:
            project_dir = Path(saved_dir)

    if not is_resume and not project_dir:
        print("Error: --cd is required for the initial review.", file=sys.stderr)
        sys.exit(1)

    # Persist project_dir so resume rounds can reuse it for path warnings.
    if project_dir and "project_dir" not in metadata:
        metadata["project_dir"] = str(project_dir.resolve())
        session_path.write_text(json.dumps(metadata, indent=2))

    paths = generate_paths(session_path, round_num)
    prompt_file = Path(paths["prompt_path"])
    output_file = Path(paths["output_path"])

    if not prompt_file.exists():
        print(f"Error: Prompt file not found: {prompt_file}", file=sys.stderr)
        sys.exit(1)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Pre-flight: warn if the prompt references file paths outside --cd.
    # Codex cannot read these, so the review will be based on assumptions.
    if project_dir:
        _warn_external_paths(prompt_file, project_dir)

    if is_resume:
        cmd = [
            "codex", "exec",
            "--sandbox", "read-only",
            "-o", str(output_file),
            "resume", session_id,
            "-",
        ]
    else:
        cmd = [
            "codex", "exec",
            "--sandbox", "read-only",
            "--cd", str(project_dir),
            "-o", str(output_file),
            "-",
        ]

    with open(prompt_file) as stdin_file:
        process = subprocess.Popen(
            cmd,
            stdin=stdin_file,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )

    # Set up a SIGALRM-based timeout to break out of the blocking stderr
    # readline loop if Codex hangs (e.g. trying to run tests in read-only sandbox).
    timed_out = False

    def _timeout_handler(signum, frame):
        nonlocal timed_out
        timed_out = True
        process.kill()

    original_handler = signal.getsignal(signal.SIGALRM)
    if timeout > 0:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout)

    try:
        # Stream stderr line-by-line to capture the session ID from the banner
        # as early as possible — protects against later timeouts.
        # Also collect all lines so we can report them on failure.
        captured_session_id = session_id
        stderr_lines: collections.deque[str] = collections.deque(maxlen=30)
        for line in iter(process.stderr.readline, ""):
            stderr_lines.append(line)
            if not is_resume and captured_session_id is None:
                match = re.search(r"session id:\s*(\S+)", line)
                if match:
                    captured_session_id = match.group(1)
                    metadata["codex_session_id"] = captured_session_id
                    session_path.write_text(json.dumps(metadata, indent=2))

        process.wait()
    finally:
        if timeout > 0:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, original_handler)

    if timed_out:
        process.wait()
        stderr_tail = "".join(stderr_lines).strip()
        if captured_session_id:
            resume_hint = " You can resume the session."
        else:
            resume_hint = " No session ID was captured — the next run will start fresh."
        msg = (
            f"Error: Codex review timed out after {timeout}s. "
            f"The process was killed.{resume_hint}"
        )
        if stderr_tail:
            msg += f"\n\nLast stderr output:\n{stderr_tail}"
        print(msg, file=sys.stderr)
        sys.exit(2)

    if process.returncode != 0 and not output_file.exists():
        stderr_tail = "".join(stderr_lines).strip()
        msg = f"Error: Codex exited with code {process.returncode}"
        if stderr_tail:
            msg += f"\n\nCodex stderr:\n{stderr_tail}"
        else:
            msg += " (no stderr output captured)"
        print(msg, file=sys.stderr)
        sys.exit(1)

    return {
        "session_id": captured_session_id,
        "prompt_file": str(prompt_file),
        "output_file": str(output_file),
        "round": round_num,
        "mode": "resume" if is_resume else "initial",
    }


def main():
    parser = argparse.ArgumentParser(description="Run or resume a Codex review (read-only)")
    parser.add_argument("--session", required=True, help="Path to session metadata JSON file")
    parser.add_argument("--cd", default=None, help="Project directory for Codex to read (required for initial review)")
    parser.add_argument("--timeout", type=int, default=0, help="Max seconds to wait for Codex (default 0 = no timeout, e.g. 1200 for 20 min)")
    args = parser.parse_args()

    result = run_review(
        session_path=Path(args.session),
        project_dir=Path(args.cd) if args.cd else None,
        timeout=args.timeout,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
