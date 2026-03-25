#!/usr/bin/env python3
"""Resume a Codex review session with safety enforcement.

Invokes `codex exec resume` with an explicit session ID in read-only sandbox
mode. Suppresses all stdout to keep the caller's context clean. Reads the
final response from the -o output file.

Safety: This script hardcodes --sandbox read-only. The session ID is required
— --last is never used to prevent cross-project session conflicts.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def resume_review(
    session_id: str,
    prompt_file: Path,
    output_file: Path,
    round_num: int,
    session_metadata: Path | None = None,
) -> dict:
    """Resume a codex review session.

    Args:
        session_id: The Codex session ID to resume
        prompt_file: Path to the follow-up prompt file
        output_file: Path where codex will write its response
        round_num: Current round number (for metadata tracking)
        session_metadata: Optional path to session.json to update

    Returns:
        Dict with output_file path
    """
    if not prompt_file.exists():
        print(f"Error: Prompt file not found: {prompt_file}", file=sys.stderr)
        sys.exit(1)

    if not session_id or session_id == "--last":
        print("Error: An explicit session ID is required. --last is not allowed.", file=sys.stderr)
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

    if session_metadata:
        metadata_path = Path(session_metadata)
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            metadata["current_round"] = round_num
            metadata_path.write_text(json.dumps(metadata, indent=2))

    if process.returncode != 0 and not output_file.exists():
        print(f"Error: Codex exited with code {process.returncode}", file=sys.stderr)
        if process.stderr:
            print(process.stderr, file=sys.stderr)
        sys.exit(1)

    return {
        "output_file": str(output_file),
        "round": round_num,
    }


def main():
    parser = argparse.ArgumentParser(description="Resume a Codex review session (read-only)")
    parser.add_argument("--session-id", required=True, help="Codex session ID to resume")
    parser.add_argument("--prompt-file", required=True, help="Path to the follow-up prompt file")
    parser.add_argument("--output-file", required=True, help="Path for Codex's output")
    parser.add_argument("--round", type=int, required=True, help="Current round number")
    parser.add_argument("--session-metadata", default=None, help="Path to session.json to update")
    args = parser.parse_args()

    result = resume_review(
        session_id=args.session_id,
        prompt_file=Path(args.prompt_file),
        output_file=Path(args.output_file),
        round_num=args.round,
        session_metadata=Path(args.session_metadata) if args.session_metadata else None,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
