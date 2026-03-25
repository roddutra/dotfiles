#!/usr/bin/env python3
"""Generate a correctly formatted file path for a Codex review file.

Returns the full path following the naming convention:
  /tmp/codex-reviews/<project>-<timestamp>-<title>-r<round>-<type>.<ext>
"""

import argparse
import json
from pathlib import Path

REVIEWS_DIR = Path("/tmp/codex-reviews")


def generate_path(project: str, timestamp: str, title: str, round_num: int, file_type: str) -> str:
    """Generate a review file path.

    Args:
        project: Project name (kebab-case)
        timestamp: Session timestamp (YYYYMMDD-HHmmss)
        title: Review title (kebab-case)
        round_num: Round number (1, 2, 3, ...)
        file_type: Either 'prompt' or 'output'

    Returns:
        Full file path as string
    """
    if file_type not in ("prompt", "output"):
        raise ValueError(f"file_type must be 'prompt' or 'output', got '{file_type}'")

    ext = ".txt" if file_type == "prompt" else ".md"
    filename = f"{project}-{timestamp}-{title}-r{round_num}-{file_type}{ext}"
    return str(REVIEWS_DIR / filename)


def main():
    parser = argparse.ArgumentParser(description="Generate a Codex review file path")
    parser.add_argument("--project", required=True, help="Project name (kebab-case)")
    parser.add_argument("--timestamp", required=True, help="Session timestamp (YYYYMMDD-HHmmss)")
    parser.add_argument("--title", required=True, help="Review title (kebab-case)")
    parser.add_argument("--round", type=int, required=True, help="Round number (1, 2, 3, ...)")
    parser.add_argument("--type", required=True, choices=["prompt", "output"], help="File type")
    args = parser.parse_args()

    path = generate_path(args.project, args.timestamp, args.title, args.round, args.type)
    print(json.dumps({"path": path}))


if __name__ == "__main__":
    main()
