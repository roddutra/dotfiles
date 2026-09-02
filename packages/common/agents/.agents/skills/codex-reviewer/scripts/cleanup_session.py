#!/usr/bin/env python3
"""Clean up review files for a completed Codex review session.

Deletes all files in the session directory, removes the directory itself,
and prunes empty parent directories (date, project) up to REVIEWS_DIR.
"""

import argparse
import json
import sys
from pathlib import Path

from generate_path import REVIEWS_DIR, validate_session_path


def cleanup_session(session_path: Path) -> dict:
    """Delete all files for a review session and remove empty parent dirs.

    Args:
        session_path: Path to the session.json file

    Returns:
        Dict with count of deleted files
    """
    validate_session_path(session_path)
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    session_dir = session_path.parent
    deleted_count = 0

    # Delete all round files found on disk (not trusting metadata)
    for f in sorted(session_dir.glob("r*-prompt.md")) + sorted(session_dir.glob("r*-output.md")):
        f.unlink()
        deleted_count += 1

    # Delete the session metadata file
    if session_path.exists():
        session_path.unlink()
        deleted_count += 1

    # Remove the session directory if empty
    if session_dir.exists() and not any(session_dir.iterdir()):
        session_dir.rmdir()

    # Prune empty parent directories up to REVIEWS_DIR
    reviews_resolved = REVIEWS_DIR.resolve()
    parent = session_dir.parent
    while parent.resolve() != reviews_resolved and parent.resolve().is_relative_to(reviews_resolved):
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
        else:
            break

    return {"deleted_count": deleted_count}


def main():
    parser = argparse.ArgumentParser(description="Clean up Codex review session files")
    parser.add_argument("--session", required=True, help="Path to session.json file")
    args = parser.parse_args()

    result = cleanup_session(Path(args.session))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
