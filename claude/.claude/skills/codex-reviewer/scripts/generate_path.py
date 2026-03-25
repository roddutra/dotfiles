#!/usr/bin/env python3
"""Generate correctly formatted file paths for a Codex review round.

Reads session metadata to derive all naming components. The caller only
needs to provide the session file and the round number.

Returns both prompt and output paths following the naming convention:
  /tmp/codex-reviews/<project>-<timestamp>-<title>-r<round>-<type>.<ext>
"""

import argparse
import json
import sys
from pathlib import Path

REVIEWS_DIR = Path("/tmp/codex-reviews")


def validate_session_path(session_path: Path) -> None:
    """Ensure session file lives under REVIEWS_DIR and has expected naming."""
    resolved = session_path.resolve()
    if resolved.parent != REVIEWS_DIR.resolve():
        print(f"Error: Session file must be under {REVIEWS_DIR}, got: {session_path}", file=sys.stderr)
        sys.exit(1)
    if not resolved.name.endswith("-session.json"):
        print(f"Error: Session file must match *-session.json, got: {resolved.name}", file=sys.stderr)
        sys.exit(1)


def generate_paths(session_path: Path, round_num: int) -> dict:
    """Generate prompt and output file paths for a review round.

    Args:
        session_path: Path to the session metadata JSON file
        round_num: Round number (1, 2, 3, ...)

    Returns:
        Dict with prompt_path and output_path
    """
    validate_session_path(session_path)
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    metadata = json.loads(session_path.read_text())
    base = f"{metadata['base_prefix']}-r{round_num}"

    return {
        "prompt_path": str(REVIEWS_DIR / f"{base}-prompt.md"),
        "output_path": str(REVIEWS_DIR / f"{base}-output.md"),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate Codex review file paths for a round")
    parser.add_argument("--session", required=True, help="Path to session metadata JSON file")
    parser.add_argument("--round", type=int, required=True, help="Round number (1, 2, 3, ...)")
    args = parser.parse_args()

    paths = generate_paths(Path(args.session), args.round)
    print(json.dumps(paths))


if __name__ == "__main__":
    main()
