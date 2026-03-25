#!/usr/bin/env python3
"""Clean up review files for a completed Codex review session.

Deletes all prompt, output, and metadata files matching a session's base
prefix from /tmp/codex-reviews/.
"""

import argparse
import json
import sys
from pathlib import Path

REVIEWS_DIR = Path("/tmp/codex-reviews")


def cleanup_session(project: str, timestamp: str, title: str) -> dict:
    """Delete all files for a review session.

    Args:
        project: Project name
        timestamp: Session timestamp (YYYYMMDD-HHmmss)
        title: Review title

    Returns:
        Dict with count of deleted files and their paths
    """
    base_prefix = f"{project}-{timestamp}-{title}"
    deleted = []

    if not REVIEWS_DIR.exists():
        return {"deleted_count": 0, "deleted_files": []}

    for file in REVIEWS_DIR.iterdir():
        if file.name.startswith(base_prefix):
            file.unlink()
            deleted.append(str(file))

    return {
        "deleted_count": len(deleted),
        "deleted_files": deleted,
    }


def main():
    parser = argparse.ArgumentParser(description="Clean up Codex review session files")
    parser.add_argument("--project", required=True, help="Project name")
    parser.add_argument("--timestamp", required=True, help="Session timestamp (YYYYMMDD-HHmmss)")
    parser.add_argument("--title", required=True, help="Review title")
    args = parser.parse_args()

    result = cleanup_session(args.project, args.timestamp, args.title)
    print(json.dumps(result, indent=2))

    if result["deleted_count"] > 0:
        print(f"Cleaned up {result['deleted_count']} files", file=sys.stderr)
    else:
        print("No files found to clean up", file=sys.stderr)


if __name__ == "__main__":
    main()
