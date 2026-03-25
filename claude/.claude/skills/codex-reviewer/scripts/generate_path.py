#!/usr/bin/env python3
"""Generate correctly formatted file paths for a Codex review round.

Returns both prompt and output paths following the naming convention:
  /tmp/codex-reviews/<project>-<timestamp>-<title>-r<round>-<type>.<ext>
"""

import argparse
import json
from pathlib import Path

REVIEWS_DIR = Path("/tmp/codex-reviews")


def generate_paths(project: str, timestamp: str, title: str, round_num: int) -> dict:
    """Generate prompt and output file paths for a review round.

    Args:
        project: Project name (kebab-case)
        timestamp: Session timestamp (YYYYMMDD-HHmmss)
        title: Review title (kebab-case)
        round_num: Round number (1, 2, 3, ...)

    Returns:
        Dict with prompt_path and output_path
    """
    base = f"{project}-{timestamp}-{title}-r{round_num}"
    return {
        "prompt_path": str(REVIEWS_DIR / f"{base}-prompt.txt"),
        "output_path": str(REVIEWS_DIR / f"{base}-output.md"),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate Codex review file paths for a round")
    parser.add_argument("--project", required=True, help="Project name (kebab-case)")
    parser.add_argument("--timestamp", required=True, help="Session timestamp (YYYYMMDD-HHmmss)")
    parser.add_argument("--title", required=True, help="Review title (kebab-case)")
    parser.add_argument("--round", type=int, required=True, help="Round number (1, 2, 3, ...)")
    args = parser.parse_args()

    paths = generate_paths(args.project, args.timestamp, args.title, args.round)
    print(json.dumps(paths))


if __name__ == "__main__":
    main()
