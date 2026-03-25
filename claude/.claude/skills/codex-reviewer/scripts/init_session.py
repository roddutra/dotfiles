#!/usr/bin/env python3
"""Initialize a Codex review session.

Creates a nested directory structure and writes a session.json metadata
file. The directory hierarchy encodes project, date, and session identity:

  /tmp/codex-reviews/<project>/<YYYY-MM-DD>/<HHMMSS-title>/session.json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from generate_path import REVIEWS_DIR, to_kebab_case


def init_session(project: str, title: str) -> dict:
    """Create the session directory and return session metadata path."""
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    REVIEWS_DIR.chmod(0o700)

    project_slug = to_kebab_case(project)
    title_slug = to_kebab_case(title)

    if not project_slug:
        print(f"Error: Project name produces empty slug: {project!r}", file=sys.stderr)
        sys.exit(1)
    if not title_slug:
        print(f"Error: Title produces empty slug: {title!r}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")

    session_dir = REVIEWS_DIR / project_slug / date_str / f"{time_str}-{title_slug}"

    session_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "project": project,
        "date": date_str,
        "time": time_str,
        "title": title,
        "current_round": 0,
        "codex_session_id": None,
    }

    metadata_path = session_dir / "session.json"
    try:
        with metadata_path.open("x") as f:
            f.write(json.dumps(metadata, indent=2))
    except FileExistsError:
        print(f"Error: Session already exists: {metadata_path}", file=sys.stderr)
        sys.exit(1)

    return {"session": str(metadata_path)}


def main():
    parser = argparse.ArgumentParser(description="Initialize a Codex review session")
    parser.add_argument("--project", required=True, help="Project name")
    parser.add_argument("--title", required=True, help="Review title (e.g., prd-review)")
    args = parser.parse_args()

    result = init_session(args.project, args.title)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
