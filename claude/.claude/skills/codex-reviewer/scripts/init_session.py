#!/usr/bin/env python3
"""Initialize a Codex review session.

Creates a nested directory structure and writes a session.json metadata
file. The directory hierarchy encodes project, date, and session identity:

  /tmp/codex-reviews/<project>/<YYYY-MM-DD>/<HHMMSS-title>/session.json
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from generate_path import REVIEWS_DIR, to_kebab_case


def _resolve_git_root(project_dir: Path) -> Path:
    """Resolve project_dir to the git repository root.

    Prevents the common mistake of passing a subdirectory (e.g. apps/api/)
    in a monorepo, which would cut off Codex's access to files outside it.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            root = Path(result.stdout.strip())
            if root != project_dir.resolve():
                print(
                    f"Note: Resolved --cd to git root: {root} "
                    f"(was: {project_dir})",
                    file=sys.stderr,
                )
            return root
    except FileNotFoundError:
        pass
    return project_dir


def _ensure_tmp_gitignored(project_dir: Path) -> None:
    """Create .tmp/ in the project and ensure it's in .gitignore."""
    tmp_dir = project_dir / ".tmp"
    tmp_dir.mkdir(exist_ok=True)

    gitignore = project_dir / ".gitignore"
    pattern = ".tmp/"
    if gitignore.exists():
        content = gitignore.read_text()
        # Check if already ignored (exact line match)
        if pattern in content.splitlines():
            return
        # Append with a newline if file doesn't end with one
        if content and not content.endswith("\n"):
            content += "\n"
        content += pattern + "\n"
        gitignore.write_text(content)
    else:
        gitignore.write_text(pattern + "\n")


def init_session(project: str, title: str, project_dir: Path | None = None) -> dict:
    """Create the session directory and return session metadata path.

    If project_dir is None, auto-detects from cwd via git rev-parse.
    """
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    REVIEWS_DIR.chmod(0o700)

    # Default to cwd if --cd not provided
    if project_dir is None:
        project_dir = Path.cwd()
    resolved_root = _resolve_git_root(project_dir)
    _ensure_tmp_gitignored(resolved_root)

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
        "project_dir": str(resolved_root),
    }

    metadata_path = session_dir / "session.json"
    try:
        with metadata_path.open("x") as f:
            f.write(json.dumps(metadata, indent=2))
    except FileExistsError:
        print(f"Error: Session already exists: {metadata_path}", file=sys.stderr)
        sys.exit(1)

    return {"session": str(metadata_path), "project_dir": str(resolved_root)}


def main():
    parser = argparse.ArgumentParser(description="Initialize a Codex review session")
    parser.add_argument("--project", required=True, help="Project name")
    parser.add_argument("--title", required=True, help="Review title (e.g., prd-review)")
    parser.add_argument("--cd", default=None, help="Project directory override (default: auto-detect git root from cwd)")
    args = parser.parse_args()

    result = init_session(args.project, args.title, project_dir=Path(args.cd) if args.cd else None)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
