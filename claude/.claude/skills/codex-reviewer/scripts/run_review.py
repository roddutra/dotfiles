#!/usr/bin/env python3
"""Run an initial Codex review with safety enforcement.

Invokes `codex exec` in read-only sandbox mode, suppresses stdout to avoid
flooding the caller's context, captures the session ID from the output header,
and writes the final response to the specified output file via -o.

Safety: This script hardcodes --sandbox read-only and rejects any attempt
to override it. Forbidden flags are blocked at the code level.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


FORBIDDEN_FLAGS = {
    "--sandbox workspace-write",
    "--sandbox danger-full-access",
    "--full-auto",
    "--dangerously-bypass-approvals-and-sandbox",
    "--yolo",
}


def run_review(prompt_file: Path, output_file: Path, project_dir: Path, session_metadata: Path | None = None) -> dict:
    """Run an initial codex review and return the session ID.

    Args:
        prompt_file: Path to the prompt file to pipe to codex
        output_file: Path where codex will write its final response
        project_dir: Working directory for codex (--cd)
        session_metadata: Optional path to session.json to update with session ID

    Returns:
        Dict with session_id and output_file path
    """
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
        process = subprocess.run(
            cmd,
            stdin=stdin_file,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    session_id = None
    for line in process.stdout.splitlines():
        match = re.search(r"session id:\s*(\S+)", line)
        if match:
            session_id = match.group(1)
            break

    if session_id and session_metadata:
        metadata_path = Path(session_metadata)
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            metadata["codex_session_id"] = session_id
            metadata["current_round"] = 1
            metadata_path.write_text(json.dumps(metadata, indent=2))

    if process.returncode != 0 and not output_file.exists():
        print(f"Error: Codex exited with code {process.returncode}", file=sys.stderr)
        if process.stderr:
            print(process.stderr, file=sys.stderr)
        sys.exit(1)

    return {
        "session_id": session_id,
        "output_file": str(output_file),
    }


def main():
    parser = argparse.ArgumentParser(description="Run an initial Codex review (read-only)")
    parser.add_argument("--prompt-file", required=True, help="Path to the prompt file")
    parser.add_argument("--output-file", required=True, help="Path for Codex's output")
    parser.add_argument("--cd", required=True, help="Project directory for Codex to read")
    parser.add_argument("--session-metadata", default=None, help="Path to session.json to update")
    args = parser.parse_args()

    result = run_review(
        prompt_file=Path(args.prompt_file),
        output_file=Path(args.output_file),
        project_dir=Path(args.cd),
        session_metadata=Path(args.session_metadata) if args.session_metadata else None,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
