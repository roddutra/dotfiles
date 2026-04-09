#!/usr/bin/env python3
"""Run or resume a Codex review with safety enforcement.

Auto-detects whether this is an initial review or a follow-up based on
session metadata:
- If codex_session_id is null → initial review (`codex exec`), --cd auto-detected from cwd
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
from init_session import _resolve_git_root

# Absolute-path prefixes that commonly appear in prompts and indicate
# files outside the project directory.
_EXTERNAL_PATH_RE = re.compile(
    r"(?:"
    r"/(?:Users|home|tmp|private/tmp|var/folders|opt)/\S+"
    r"|"
    r"~/\S+"
    r")"
)

# Codex CLI persists session rollouts here, partitioned by date:
#   ~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<session_id>.jsonl
_CODEX_SESSIONS_ROOT = Path.home() / ".codex" / "sessions"


def _find_rollout_file(session_id: str) -> Path | None:
    """Locate the Codex rollout JSONL file for a given session id.

    Best-effort: rglob and stat can raise OSError on permission issues
    or races where a file disappears mid-walk. Since this lookup only
    feeds supplemental diagnostics, never let it surface a traceback
    in place of the intended error message.
    """
    if not session_id or not _CODEX_SESSIONS_ROOT.exists():
        return None
    try:
        matches = list(_CODEX_SESSIONS_ROOT.rglob(f"rollout-*-{session_id}.jsonl"))
        if not matches:
            return None
        return max(matches, key=lambda p: p.stat().st_mtime)
    except OSError:
        return None


def _diagnose_silent_failure(session_id: str) -> str | None:
    """Check the rollout file for the known empty-output signature.

    The signature is the last `task_complete` event having
    `last_agent_message=null` — meaning Codex closed the turn without
    producing any assistant tokens. Returns a diagnostic string if the
    signature is present, otherwise None (best-effort: returns None on
    any read/parse failure rather than masking the original error).
    """
    rollout = _find_rollout_file(session_id)
    if rollout is None:
        return None

    last_task_complete: dict | None = None
    try:
        with rollout.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                # Cheap pre-filter: skip lines that obviously don't contain
                # a task_complete payload before paying for json.loads.
                if '"task_complete"' not in line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = event.get("payload", {})
                if payload.get("type") == "task_complete":
                    last_task_complete = payload
    except OSError:
        return None

    if last_task_complete is None:
        return None
    if last_task_complete.get("last_agent_message") is None:
        return (
            "Codex rollout confirms the silent-failure signature: the last "
            "`task_complete` event has `last_agent_message=null` (no assistant "
            "tokens were produced for this turn).\n"
            f"Rollout file: {rollout}"
        )
    return None


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
            f"Copy files into .tmp/ within the project.",
            file=sys.stderr,
        )


def run_review(session_path: Path, project_dir: Path | None = None, timeout: int = 0) -> dict:
    """Run or resume a codex review.

    Args:
        session_path: Path to the session metadata JSON file
        project_dir: Working directory for codex (--cd). Auto-detected
            from cwd if not provided. Ignored for resumes.
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

    # Resolve project_dir priority: explicit --cd > session metadata > cwd.
    # Explicit --cd wins so callers can correct a bad persisted value.
    if project_dir:
        project_dir = _resolve_git_root(project_dir)
    elif metadata.get("project_dir"):
        project_dir = Path(metadata["project_dir"])
    else:
        project_dir = _resolve_git_root(Path.cwd())

    # Persist project_dir if not already in metadata (backwards compat with old sessions).
    if "project_dir" not in metadata:
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

    # Failure classification:
    #   1. Any non-zero return code is a real CLI error → exit 1.
    #      Output state is reported as supplemental context only.
    #   2. Clean exit (0) but missing or empty output is the silent-failure
    #      mode → exit 3. Most commonly triggered by `exec resume` after a
    #      previous turn that ended with a long final response — the model
    #      emits a `task_complete` event with `last_agent_message=null`, no
    #      assistant tokens produced, and Codex writes an empty `-o` file.
    if process.returncode != 0:
        stderr_tail = "".join(stderr_lines).strip()
        msg = f"Error: Codex exited with code {process.returncode}"
        if output_file.exists():
            size = output_file.stat().st_size
            if size == 0:
                msg += " (output file is empty)"
            else:
                msg += f" (partial output written, {size} bytes — inspect: {output_file})"
        else:
            msg += " (no output file written)"
        if stderr_tail:
            msg += f"\n\nCodex stderr:\n{stderr_tail}"
        else:
            msg += " (no stderr output captured)"
        print(msg, file=sys.stderr)
        sys.exit(1)

    # process.returncode == 0 below.
    output_missing = not output_file.exists()
    output_empty = output_file.exists() and output_file.stat().st_size == 0
    if output_missing or output_empty:
        stderr_tail = "".join(stderr_lines).strip()

        # Compute the rollout diagnostic once — it's the strong signal that
        # gates BOTH the action guidance below and the marker write further
        # down. Best-effort: returns None if the rollout file cannot be
        # located, parsed, or doesn't contain the signature.
        rollout_diag: str | None = None
        if is_resume or captured_session_id:
            diag_id = captured_session_id or session_id
            if diag_id:
                rollout_diag = _diagnose_silent_failure(diag_id)

        msg = (
            "Error: Codex exited cleanly but produced no review content "
            f"({'output file missing' if output_missing else 'output file is empty'}).\n\n"
            "This is the Codex silent-failure mode — most commonly seen "
            "with `exec resume` after a previous turn that ended with a "
            "long final response. The model emits a `task_complete` event "
            "with `last_agent_message=null`, producing no assistant tokens."
        )
        if rollout_diag is not None:
            # Confirmed: rollout shows last_agent_message=null. The session
            # is dead. write_prompt.py will block any further round below,
            # including --force, because the marker write succeeds.
            msg += (
                "\n\nThe rollout file CONFIRMS this signature for the "
                "current turn — the session is dead. Do NOT retry with "
                "resume or `--force`. Start a fresh session via "
                "init_session.py and carry context forward manually (see "
                "SKILL.md → 'Silent Failures (Empty Output)')."
                f"\n\n{rollout_diag}"
            )
        else:
            # Unconfirmed: could be the same failure mode with a missing or
            # archived rollout file, or a transient issue (sandbox error,
            # permissions) masquerading as empty output. Don't overstate
            # certainty — let the user decide whether to retry or recover.
            msg += (
                "\n\nHowever, the rollout signature could NOT be confirmed "
                "for this turn (the rollout file is missing, archived, or "
                "does not contain a matching `task_complete` event). The "
                "empty output may instead be caused by a transient issue "
                "such as a sandbox or permissions error.\n\n"
                "If you can verify the rollout signature manually, follow "
                "the fresh-session recovery in SKILL.md → 'Silent Failures "
                "(Empty Output)'. Otherwise, you may retry the next round "
                "with `write_prompt.py --force` — no silent-failure marker "
                "was written, so `write_prompt.py` will allow it."
            )

        if stderr_tail:
            msg += f"\n\nCodex stderr (last lines):\n{stderr_tail}"

        # Persist `last_round_silent_failure` ONLY when the rollout signature
        # is confirmed. Without confirmation, fall through to write_prompt.py's
        # soft (--force overridable) block so users can recover from edge
        # cases like missing rollout files or sandbox errors that masquerade
        # as empty output. The write is atomic via temp file + replace so a
        # mid-write failure cannot corrupt session.json — write_prompt.py
        # would otherwise be unable to parse it.
        if rollout_diag is not None:
            try:
                metadata["last_round_silent_failure"] = round_num
                tmp_path = session_path.parent / f"{session_path.name}.tmp"
                tmp_path.write_text(json.dumps(metadata, indent=2))
                tmp_path.replace(session_path)
            except OSError:
                pass

        print(msg, file=sys.stderr)
        sys.exit(3)

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
    parser.add_argument("--cd", default=None, help="Project directory override (default: auto-detect git root from cwd)")
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
