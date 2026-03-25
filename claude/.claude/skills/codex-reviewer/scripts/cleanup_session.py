#!/usr/bin/env python3
"""Clean up review files for a completed Codex review session.

Reads the session metadata to find all matching files, then deletes them
(including the metadata file itself).
"""

import argparse
import json
import sys
from pathlib import Path


def cleanup_session(session_path: Path) -> dict:
    """Delete all files for a review session.

    Args:
        session_path: Path to the session metadata JSON file

    Returns:
        Dict with count of deleted files
    """
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    metadata = json.loads(session_path.read_text())
    base_prefix = metadata["base_prefix"]
    reviews_dir = Path(metadata["reviews_dir"])

    deleted_count = 0
    for file in reviews_dir.iterdir():
        if file.name.startswith(base_prefix):
            file.unlink()
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
