#!/usr/bin/env python3
"""Write a review prompt file from stdin.

Reads prompt content from stdin, generates the correct file path using
session metadata, validates no overwrite, and writes the file. Returns
both prompt_path and output_path so the caller has everything needed
for the next step.

Usage:
    cat <<'PROMPT' | python write_prompt.py --session <path> --round <N>
    Your prompt content here...
    PROMPT
"""

import argparse
import json
import sys
from pathlib import Path


def write_prompt(session_path: Path, round_num: int, content: str) -> dict:
    """Write prompt content to the correct file path.

    Args:
        session_path: Path to the session metadata JSON file
        round_num: Round number (1, 2, 3, ...)
        content: Prompt content to write

    Returns:
        Dict with prompt_path and output_path
    """
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    metadata = json.loads(session_path.read_text())
    reviews_dir = Path(metadata["reviews_dir"])
    base = f"{metadata['base_prefix']}-r{round_num}"

    prompt_path = reviews_dir / f"{base}-prompt.md"
    output_path = reviews_dir / f"{base}-output.md"

    if prompt_path.exists():
        print(
            f"Error: Prompt file already exists: {prompt_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not content.strip():
        print("Error: No prompt content received on stdin", file=sys.stderr)
        sys.exit(1)

    prompt_path.write_text(content)

    return {
        "prompt_path": str(prompt_path),
        "output_path": str(output_path),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Write a review prompt file from stdin"
    )
    parser.add_argument(
        "--session", required=True, help="Path to session metadata JSON file"
    )
    parser.add_argument(
        "--round", type=int, required=True, help="Round number (1, 2, 3, ...)"
    )
    args = parser.parse_args()

    content = sys.stdin.read()
    result = write_prompt(Path(args.session), args.round, content)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
