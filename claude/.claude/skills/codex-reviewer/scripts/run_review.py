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
import json
import re
import subprocess
import sys
from pathlib import Path

from generate_path import generate_paths


def run_review(session_path: Path, project_dir: Path | None = None) -> dict:
    """Run or resume a codex review.

    Args:
        session_path: Path to the session metadata JSON file
        project_dir: Working directory for codex (--cd). Required for
            initial reviews, ignored for resumes.

    Returns:
        Dict with session_id, prompt_file, output_file, round, and mode
    """
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    metadata = json.loads(session_path.read_text())
    round_num = metadata.get("current_round", 0)
    session_id = metadata.get("codex_session_id")
    is_resume = bool(session_id and session_id != "--last")

    if round_num == 0:
        print("Error: No prompt written yet. Run write_prompt.py first.", file=sys.stderr)
        sys.exit(1)

    if not is_resume and not project_dir:
        print("Error: --cd is required for the initial review.", file=sys.stderr)
        sys.exit(1)

    paths = generate_paths(session_path, round_num)
    prompt_file = Path(paths["prompt_path"])
    output_file = Path(paths["output_path"])

    if not prompt_file.exists():
        print(f"Error: Prompt file not found: {prompt_file}", file=sys.stderr)
        sys.exit(1)

    output_file.parent.mkdir(parents=True, exist_ok=True)

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
            text=True,
        )

    # Stream stderr line-by-line to capture the session ID from the banner
    # as early as possible — protects against later timeouts.
    captured_session_id = session_id
    for line in iter(process.stderr.readline, ""):
        if not is_resume and captured_session_id is None:
            match = re.search(r"session id:\s*(\S+)", line)
            if match:
                captured_session_id = match.group(1)
                metadata["codex_session_id"] = captured_session_id
                session_path.write_text(json.dumps(metadata, indent=2))

    process.wait()

    if process.returncode != 0 and not output_file.exists():
        print(f"Error: Codex exited with code {process.returncode}", file=sys.stderr)
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
    args = parser.parse_args()

    result = run_review(
        session_path=Path(args.session),
        project_dir=Path(args.cd) if args.cd else None,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
