#!/usr/bin/env python3
"""Shared path, naming, and session helpers for the video-watcher skill.

Everything the skill writes lives under a hidden directory in the user's home,
so prompts, answers and prepared videos are never committed and never touch
the project repo:

  ~/.video-watcher/<project>/<YYYY-MM-DD>/<HHMMSS-title>/   # session
    session.json
    <HHMMSS-label>/               # one per model call
      prompt.md
      answer.md
      call.json                   # provider, model, video, window, usage
    prepared/                     # outputs of prepare.py, when used
  ~/.video-watcher/remote-files.json   # handles of uploads kept on a provider

The layout mirrors the video-inspector skill (project -> date -> session).
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

STORE_DIR = Path.home() / ".video-watcher"
REMOTE_FILES_PATH = STORE_DIR / "remote-files.json"


def to_kebab_case(text: str) -> str:
    """Convert arbitrary text to a filesystem-safe kebab-case slug."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _git(cwd: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except (FileNotFoundError, NotADirectoryError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def git_worktree_root(start_dir: Path | None = None) -> Path | None:
    """Root of the current git work tree, or None outside a repository."""
    out = _git(start_dir or Path.cwd(), "rev-parse", "--show-toplevel")
    if out is None or not out.strip():
        return None
    return Path(out.strip())


def resolve_git_project_name(start_dir: Path | None = None) -> str | None:
    """Kebab-cased basename of the MAIN working tree, or None outside git.

    Using the main working tree (first entry of `git worktree list`) means
    every linked worktree of a repo groups under one project name.
    """
    cwd = start_dir or Path.cwd()
    inside = _git(cwd, "rev-parse", "--is-inside-work-tree")
    if inside is None or inside.strip() != "true":
        return None
    listing = _git(cwd, "worktree", "list", "--porcelain")
    if listing is None:
        return None
    for line in listing.splitlines():
        if line.startswith("worktree "):
            return to_kebab_case(Path(line[len("worktree "):]).resolve().name) or None
    return None


def resolve_project_name(explicit: str | None, start_dir: Path | None = None) -> str:
    """Explicit --project, else the git-derived name, else the cwd basename."""
    if explicit is not None and explicit.strip():
        return explicit
    git_name = resolve_git_project_name(start_dir)
    if git_name:
        return git_name
    cwd = start_dir or Path.cwd()
    return to_kebab_case(cwd.resolve().name) or "video-watcher"


def validate_session_path(session_path: Path) -> None:
    """Ensure a session file lives under STORE_DIR and is session.json."""
    resolved = session_path.resolve()
    if not resolved.is_relative_to(STORE_DIR.resolve()):
        print(f"Error: Session file must be under {STORE_DIR}, got: {session_path}", file=sys.stderr)
        sys.exit(1)
    if resolved.name != "session.json":
        print(f"Error: Session file must be named session.json, got: {resolved.name}", file=sys.stderr)
        sys.exit(1)


def ensure_store() -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    STORE_DIR.chmod(0o700)


def create_session(title: str, project: str | None = None, start_dir: Path | None = None) -> Path:
    """Create a session directory and return the path to its session.json."""
    start_dir = start_dir or Path.cwd()
    ensure_store()
    effective_project = resolve_project_name(project, start_dir)
    project_slug = to_kebab_case(effective_project) or "video-watcher"
    title_slug = to_kebab_case(title) or "session"
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    session_dir = STORE_DIR / project_slug / date_str / f"{time_str}-{title_slug}"
    suffix = 2
    while session_dir.exists():
        session_dir = STORE_DIR / project_slug / date_str / f"{time_str}-{title_slug}-{suffix}"
        suffix += 1
    session_dir.mkdir(parents=True)
    metadata = {
        "project": effective_project,
        "date": date_str,
        "time": time_str,
        "title": title,
        "created_from": str(start_dir.resolve()),
        "calls": [],
    }
    session_path = session_dir / "session.json"
    session_path.write_text(json.dumps(metadata, indent=2))
    return session_path


def resolve_session(session: str | None, title: str | None, project: str | None, fallback_title: str) -> Path:
    """Use an existing session.json, or create a session when none is given."""
    if session:
        session_path = Path(session).expanduser()
        validate_session_path(session_path)
        if not session_path.exists():
            print(f"Error: Session file not found: {session_path}", file=sys.stderr)
            sys.exit(1)
        return session_path
    return create_session(title or fallback_title, project=project)


def new_subdir(session_path: Path, label: str) -> Path:
    """Create a fresh timestamped folder inside the session."""
    slug = to_kebab_case(label) or "call"
    stamp = datetime.now().strftime("%H%M%S")
    target = session_path.parent / f"{stamp}-{slug}"
    suffix = 2
    while target.exists():
        target = session_path.parent / f"{stamp}-{slug}-{suffix}"
        suffix += 1
    target.mkdir(parents=True)
    return target


def record_call(session_path: Path, entry: dict) -> None:
    """Append one call summary to the session's metadata."""
    try:
        metadata = json.loads(session_path.read_text())
    except (json.JSONDecodeError, OSError):
        metadata = {}
    metadata.setdefault("calls", []).append(entry)
    session_path.write_text(json.dumps(metadata, indent=2))
