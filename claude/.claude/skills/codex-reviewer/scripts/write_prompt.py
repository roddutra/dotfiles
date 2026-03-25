#!/usr/bin/env python3
"""Write a review prompt file from stdin.

Reads prompt content from stdin, auto-increments the round number from
session metadata, generates the correct file path, validates no overwrite,
and writes the file. Returns prompt_path, output_path, and the round number.

Usage:
    cat <<'PROMPT' | python write_prompt.py --session <path>
    Your prompt content here...
    PROMPT
"""

import argparse
import json
import sys
from pathlib import Path

from generate_path import generate_paths


def write_prompt(session_path: Path, content: str) -> dict:
    """Write prompt content to the correct file path.

    Auto-increments current_round in session metadata.

    Args:
        session_path: Path to the session metadata JSON file
        content: Prompt content to write

    Returns:
        Dict with prompt_path, output_path, and round
    """
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    if not content.strip():
        print("Error: No prompt content received on stdin", file=sys.stderr)
        sys.exit(1)

    metadata = json.loads(session_path.read_text())
    round_num = metadata.get("current_round", 0) + 1

    paths = generate_paths(session_path, round_num)
    prompt_path = Path(paths["prompt_path"])

    if prompt_path.exists():
        print(
            f"Error: Prompt file already exists: {prompt_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    prompt_path.write_text(content)

    # Update round in metadata
    metadata["current_round"] = round_num
    session_path.write_text(json.dumps(metadata, indent=2))

    return {
        "prompt_path": str(prompt_path),
        "output_path": paths["output_path"],
        "round": round_num,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Write a review prompt file from stdin"
    )
    parser.add_argument(
        "--session", required=True, help="Path to session metadata JSON file"
    )
    args = parser.parse_args()

    content = sys.stdin.read()
    result = write_prompt(Path(args.session), content)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
