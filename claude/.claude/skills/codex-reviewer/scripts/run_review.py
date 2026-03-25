#!/usr/bin/env python3
"""Run an initial Codex review with safety enforcement.

Invokes `codex exec` in read-only sandbox mode, suppresses stdout (which
contains a duplicate of the response text), captures the session ID from
stderr (where Codex sends its session banner when piped), and writes the
final response to the specified output file via -o.

The session ID is written to the metadata file as soon as it appears in
stderr — before Codex finishes its review. This means the session can be
recovered even if the process is interrupted (e.g., by a timeout).

Safety: This script hardcodes --sandbox read-only. The command is constructed
internally with no mechanism to inject other flags.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def run_review(session_path: Path, prompt_file: Path, output_file: Path, project_dir: Path) -> dict:
    """Run an initial codex review and return the session ID.

    Args:
        session_path: Path to the session metadata JSON file
        prompt_file: Path to the prompt file to pipe to codex
        output_file: Path where codex will write its final response
        project_dir: Working directory for codex (--cd)

    Returns:
        Dict with session_id and output_file path
    """
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    if not prompt_file.exists():
        print(f"Error: Prompt file not found: {prompt_file}", file=sys.stderr)
        sys.exit(1)

    output_file.parent.mkdir(parents=True, exist_ok=True)

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

    # Stream stderr line-by-line. The session ID appears in the banner at
    # the very start, so we capture it almost immediately and persist it to
    # the metadata file right away — protecting against later timeouts.
    session_id = None
    for line in iter(process.stderr.readline, ""):
        if session_id is None:
            match = re.search(r"session id:\s*(\S+)", line)
            if match:
                session_id = match.group(1)
                metadata = json.loads(session_path.read_text())
                metadata["codex_session_id"] = session_id
                metadata["current_round"] = 1
                session_path.write_text(json.dumps(metadata, indent=2))

    process.wait()

    if process.returncode != 0 and not output_file.exists():
        print(f"Error: Codex exited with code {process.returncode}", file=sys.stderr)
        sys.exit(1)

    return {
        "session_id": session_id,
        "output_file": str(output_file),
    }


def main():
    parser = argparse.ArgumentParser(description="Run an initial Codex review (read-only)")
    parser.add_argument("--session", required=True, help="Path to session metadata JSON file")
    parser.add_argument("--prompt-file", required=True, help="Path to the prompt file")
    parser.add_argument("--output-file", required=True, help="Path for Codex's output")
    parser.add_argument("--cd", required=True, help="Project directory for Codex to read")
    args = parser.parse_args()

    result = run_review(
        session_path=Path(args.session),
        prompt_file=Path(args.prompt_file),
        output_file=Path(args.output_file),
        project_dir=Path(args.cd),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
