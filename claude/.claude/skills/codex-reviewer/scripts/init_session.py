#!/usr/bin/env python3
"""Initialize a Codex review session.

Creates the review directory and generates a session metadata file with
a fixed timestamp that all rounds will share. Idempotent — safe to call
if the directory already exists.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

REVIEWS_DIR = Path("/tmp/codex-reviews")


def init_session(project: str, title: str) -> dict:
    """Create the reviews directory and return session metadata path."""
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_prefix = f"{project}-{timestamp}-{title}"

    metadata = {
        "project": project,
        "timestamp": timestamp,
        "title": title,
        "base_prefix": base_prefix,
        "reviews_dir": str(REVIEWS_DIR),
        "current_round": 0,
        "codex_session_id": None,
    }

    metadata_path = REVIEWS_DIR / f"{base_prefix}-session.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))

    return {"session": str(metadata_path)}


def main():
    parser = argparse.ArgumentParser(description="Initialize a Codex review session")
    parser.add_argument("--project", required=True, help="Project name (kebab-case)")
    parser.add_argument("--title", required=True, help="Review title (kebab-case, e.g., prd-review)")
    args = parser.parse_args()

    result = init_session(args.project, args.title)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
