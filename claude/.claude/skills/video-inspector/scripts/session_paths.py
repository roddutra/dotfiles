#!/usr/bin/env python3
"""Shared path, naming, and session helpers for the video-inspector skill.

Sessions live under a hidden directory in the user's home so extracted
frames and the source video are never version-controlled and never touch
the project repo:

  ~/.video-inspector/<project>/<YYYY-MM-DD>/<HHMMSS-title>/
    session.json
    <HHMMSS-video-slug>/          # one per processed video
      source.<ext>                # persisted copy of the source (optional)
      manifest.json
      frames/
        frame_00001_t0.000s.jpg
        frame_00002_t1.000s.jpg
        ...

This mirrors the codex-reviewer layout (project -> date -> session), with
one extra nesting level per processed video so a single inspection session
can hold several recordings (e.g. a nav clip, then a modal clip) and you
have one central place to inspect everything afterwards.
"""

import re
import subprocess
import sys
from pathlib import Path

# Base directory for all inspection sessions. In the home directory (not the
# repo) so nothing here is ever committed; there is no .gitignore to manage.
INSPECTOR_DIR = Path.home() / ".video-inspector"


def to_kebab_case(text: str) -> str:
    """Convert arbitrary text to a filesystem-safe kebab-case slug."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def resolve_git_project_name(start_dir: Path | None = None) -> str | None:
    """Derive a stable project name from the git repository, or None.

    The name is the kebab-cased basename of the MAIN working tree (the first
    entry of `git worktree list`). Using the main working tree means every
    linked worktree of a repo groups under one name, so inspections started
    from a worktree land in the same project bucket as the main checkout.

    Returns None when not inside a git work tree (no repo, or a bare repo);
    the caller then falls back to an explicit --project or the cwd basename.
    Git is entirely optional for this skill -- it only affects grouping, not
    where frames are written.
    """
    cwd = start_dir or Path.cwd()

    def _git(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True
            )
        except FileNotFoundError:
            return None  # git not installed
        if result.returncode != 0:
            return None
        return result.stdout

    inside = _git("rev-parse", "--is-inside-work-tree")
    if inside is None or inside.strip() != "true":
        return None

    listing = _git("worktree", "list", "--porcelain")
    if listing is None:
        return None
    main_path = None
    for line in listing.splitlines():
        if line.startswith("worktree "):
            main_path = line[len("worktree "):]
            break
    if not main_path:
        return None

    return to_kebab_case(Path(main_path).resolve().name) or None


def resolve_project_name(explicit: str | None, start_dir: Path | None = None) -> str:
    """Resolve the effective project name for grouping sessions.

    Precedence: explicit --project (if given) > git-derived name > cwd
    basename. Never fails -- unlike codex-reviewer this skill does not need a
    git repo, so we always produce a usable bucket rather than erroring.
    """
    if explicit is not None and explicit.strip():
        return explicit
    git_name = resolve_git_project_name(start_dir)
    if git_name:
        return git_name
    cwd = start_dir or Path.cwd()
    return to_kebab_case(cwd.resolve().name) or "video-inspection"


def validate_session_path(session_path: Path) -> None:
    """Ensure a session file lives under INSPECTOR_DIR and is session.json."""
    resolved = session_path.resolve()
    base = INSPECTOR_DIR.resolve()
    if not resolved.is_relative_to(base):
        print(
            f"Error: Session file must be under {INSPECTOR_DIR}, got: {session_path}",
            file=sys.stderr,
        )
        sys.exit(1)
    if resolved.name != "session.json":
        print(
            f"Error: Session file must be named session.json, got: {resolved.name}",
            file=sys.stderr,
        )
        sys.exit(1)
