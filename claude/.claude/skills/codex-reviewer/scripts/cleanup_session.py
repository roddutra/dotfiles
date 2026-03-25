#!/usr/bin/env python3
"""Clean up review files for a completed Codex review session.

Reads the session metadata to build explicit file paths for each round,
then deletes them along with the metadata file itself.
"""

import argparse
import json
import sys
from pathlib import Path

from generate_path import REVIEWS_DIR, validate_session_path


def cleanup_session(session_path: Path) -> dict:
    """Delete all files for a review session.

    Builds explicit file paths from metadata instead of using prefix
    matching, to avoid accidentally deleting files from other sessions.

    Args:
        session_path: Path to the session metadata JSON file

    Returns:
        Dict with count of deleted files
    """
    validate_session_path(session_path)
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    metadata = json.loads(session_path.read_text())
    base_prefix = metadata["base_prefix"]
    current_round = metadata.get("current_round", 0)

    deleted_count = 0

    # Delete prompt and output files for each round
    for r in range(1, current_round + 1):
        base = f"{base_prefix}-r{r}"
        for suffix in ("-prompt.md", "-prompt.txt", "-output.md"):
            f = REVIEWS_DIR / f"{base}{suffix}"
            if f.exists():
                f.unlink()
                deleted_count += 1

    # Delete the session metadata file itself
    if session_path.exists():
        session_path.unlink()
        deleted_count += 1

    return {"deleted_count": deleted_count}


def main():
    parser = argparse.ArgumentParser(description="Clean up Codex review session files")
    parser.add_argument("--session", required=True, help="Path to session metadata JSON file")
    args = parser.parse_args()

    result = cleanup_session(Path(args.session))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
