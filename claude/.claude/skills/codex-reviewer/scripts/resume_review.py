#!/usr/bin/env python3
"""Resume a Codex review session with safety enforcement.

Reads the session ID from the metadata file and invokes `codex exec resume`
in read-only sandbox mode. Suppresses all stdout to keep the caller's
context clean. Reads the final response from the -o output file.

Safety: This script hardcodes --sandbox read-only. The session ID is read
from the metadata file — --last is never used to prevent cross-project
session conflicts.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def resume_review(
    session_path: Path,
    prompt_file: Path,
    output_file: Path,
    round_num: int,
) -> dict:
    """Resume a codex review session.

    Args:
        session_path: Path to the session metadata JSON file
        prompt_file: Path to the follow-up prompt file
        output_file: Path where codex will write its response
        round_num: Current round number (for metadata tracking)

    Returns:
        Dict with output_file path and round
    """
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    if not prompt_file.exists():
        print(f"Error: Prompt file not found: {prompt_file}", file=sys.stderr)
        sys.exit(1)

    metadata = json.loads(session_path.read_text())
    session_id = metadata.get("codex_session_id")

    if not session_id or session_id == "--last":
        print("Error: No valid session ID found in metadata. Run an initial review first.", file=sys.stderr)
        sys.exit(1)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "codex", "exec",
        "--sandbox", "read-only",
        "-o", str(output_file),
        "resume", session_id,
        "-",
    ]

    with open(prompt_file) as stdin_file:
        process = subprocess.run(
            cmd,
            stdin=stdin_file,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

    # Update round in metadata
    metadata["current_round"] = round_num
    session_path.write_text(json.dumps(metadata, indent=2))

    if process.returncode != 0 and not output_file.exists():
        print(f"Error: Codex exited with code {process.returncode}", file=sys.stderr)
        sys.exit(1)

    return {
        "output_file": str(output_file),
        "round": round_num,
    }


def main():
    parser = argparse.ArgumentParser(description="Resume a Codex review session (read-only)")
    parser.add_argument("--session", required=True, help="Path to session metadata JSON file")
    parser.add_argument("--prompt-file", required=True, help="Path to the follow-up prompt file")
    parser.add_argument("--output-file", required=True, help="Path for Codex's output")
    parser.add_argument("--round", type=int, required=True, help="Current round number")
    args = parser.parse_args()

    result = resume_review(
        session_path=Path(args.session),
        prompt_file=Path(args.prompt_file),
        output_file=Path(args.output_file),
        round_num=args.round,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
