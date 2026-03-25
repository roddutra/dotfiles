#!/usr/bin/env python3
"""Generate correctly formatted file paths for a Codex review round.

Files live in the session directory alongside session.json, with simple
names: r1-prompt.md, r1-output.md, r2-prompt.md, etc.

Directory structure:
  /tmp/codex-reviews/<project>/<YYYY-MM-DD>/<HHMMSS-title>/
    session.json
    r1-prompt.md
    r1-output.md
"""

import argparse
import json
import re
import sys
from pathlib import Path

REVIEWS_DIR = Path("/tmp/codex-reviews")


def to_kebab_case(text: str) -> str:
    """Convert arbitrary text to kebab-case."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def validate_session_path(session_path: Path) -> None:
    """Ensure session file lives under REVIEWS_DIR and is named session.json."""
    resolved = session_path.resolve()
    reviews_resolved = REVIEWS_DIR.resolve()
    if not resolved.is_relative_to(reviews_resolved):
        print(f"Error: Session file must be under {REVIEWS_DIR}, got: {session_path}", file=sys.stderr)
        sys.exit(1)
    if resolved.name != "session.json":
        print(f"Error: Session file must be named session.json, got: {resolved.name}", file=sys.stderr)
        sys.exit(1)


def generate_paths(session_path: Path, round_num: int) -> dict:
    """Generate prompt and output file paths for a review round.

    Args:
        session_path: Path to the session.json file
        round_num: Round number (1, 2, 3, ...)

    Returns:
        Dict with prompt_path and output_path
    """
    validate_session_path(session_path)
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    session_dir = session_path.parent

    return {
        "prompt_path": str(session_dir / f"r{round_num}-prompt.md"),
        "output_path": str(session_dir / f"r{round_num}-output.md"),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate Codex review file paths for a round")
    parser.add_argument("--session", required=True, help="Path to session.json file")
    parser.add_argument("--round", type=int, required=True, help="Round number (1, 2, 3, ...)")
    args = parser.parse_args()

    paths = generate_paths(Path(args.session), args.round)
    print(json.dumps(paths))


if __name__ == "__main__":
    main()
