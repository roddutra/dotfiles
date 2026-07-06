#!/usr/bin/env python3
"""Initialize a video-inspection session.

Creates a nested directory under ~/.video-inspector/ that encodes project,
date, and session identity, plus a session.json metadata file:

  ~/.video-inspector/<project>/<YYYY-MM-DD>/<HHMMSS-title>/session.json

Processed videos are added later by extract_frames.py, each in its own
timestamped subfolder inside this session directory.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from session_paths import (
    INSPECTOR_DIR,
    resolve_project_name,
    to_kebab_case,
)


def init_session(
    title: str,
    project: str | None = None,
    start_dir: Path | None = None,
) -> dict:
    """Create the session directory and return its metadata path.

    The project name groups sessions and is derived from git when available
    (shared across worktrees), else from --project, else the cwd basename.
    Nothing about the project name affects where frames are written -- they
    always live under INSPECTOR_DIR in the home directory.
    """
    start_dir = start_dir or Path.cwd()

    INSPECTOR_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    INSPECTOR_DIR.chmod(0o700)

    effective_project = resolve_project_name(project, start_dir)
    project_slug = to_kebab_case(effective_project)
    title_slug = to_kebab_case(title)

    if not project_slug:
        print(f"Error: Project name produces empty slug: {effective_project!r}", file=sys.stderr)
        sys.exit(1)
    if not title_slug:
        print(f"Error: Title produces empty slug: {title!r}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")

    session_dir = INSPECTOR_DIR / project_slug / date_str / f"{time_str}-{title_slug}"
    session_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "project": effective_project,
        "date": date_str,
        "time": time_str,
        "title": title,
        "created_from": str(start_dir.resolve()),
        "videos": [],
    }

    metadata_path = session_dir / "session.json"
    try:
        with metadata_path.open("x") as f:
            f.write(json.dumps(metadata, indent=2))
    except FileExistsError:
        print(f"Error: Session already exists: {metadata_path}", file=sys.stderr)
        sys.exit(1)

    return {"session": str(metadata_path), "session_dir": str(session_dir)}


def main():
    parser = argparse.ArgumentParser(description="Initialize a video-inspection session")
    parser.add_argument("--title", required=True, help="Session title (e.g., nav-animation-review)")
    parser.add_argument(
        "--project", default=None,
        help=(
            "Project name for grouping. Optional: derived from the git repo "
            "when inside one (shared across worktrees), otherwise from the "
            "current directory name. Pass this to override that default."
        ),
    )
    args = parser.parse_args()

    result = init_session(args.title, project=args.project)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
