#!/usr/bin/env python3
"""Generate correctly formatted file paths for a Codex review round.

Files live in the session directory alongside session.json, with simple
names: r1-prompt.md, r1-output.md, r2-prompt.md, etc.

Directory structure:
  ~/.codex-reviews/<project>/<YYYY-MM-DD>/<HHMMSS-title>/
    session.json
    r1-prompt.md
    r1-output.md
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REVIEWS_DIR = Path.home() / ".codex-reviews"


def to_kebab_case(text: str) -> str:
    """Convert arbitrary text to kebab-case."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def resolve_git_project_name(start_dir: Path | None = None) -> tuple[bool, str | None]:
    """Derive a stable project name from the git repository.

    Returns a `(in_git_work_tree, project_name)` pair so callers can tell the
    three outcomes apart:
      - `(False, None)`: not inside a git work tree (no repo, or a bare repo
        with no working tree). The caller must require an explicit name.
      - `(True, None)`: inside a work tree, but the derived directory name
        slugifies to empty. The caller must require an explicit name, but can
        report it accurately rather than claiming "not a git repo".
      - `(True, "<slug>")`: the derived project name.

    The name is the kebab-cased basename of the MAIN working tree, which is
    always the first entry of `git worktree list`. Using the main working tree
    means every linked worktree of a repo groups under one name:
      - **Main work tree / linked worktree**: both resolve to the main repo's
        own folder (e.g. a worktree `myrepo-prd025` resolves to `myrepo`).
      - **Submodule / worktree of a submodule**: both resolve to the submodule's
        own name (the first entry is the submodule's checkout), NOT the
        superproject's `.git/modules` path.

    This is intentionally different from how `--cd` is resolved in
    `init_session.py` (always `--show-toplevel`, the worktree's own root, so
    Codex reviews the files in the checkout you launched from). The chosen path
    is resolved before taking its basename so symlinked checkouts name correctly.
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

    # Must be inside a working tree. This is "false" for bare repos and fails
    # (None) when not in a repo at all; both mean the caller needs a name.
    inside = _git("rev-parse", "--is-inside-work-tree")
    if inside is None or inside.strip() != "true":
        return (False, None)

    # The main working tree is always the FIRST `worktree` entry. Parse the path
    # ourselves (rather than splitting on whitespace) so paths with spaces work.
    listing = _git("worktree", "list", "--porcelain")
    if listing is None:
        return (False, None)
    main_path = None
    for line in listing.splitlines():
        if line.startswith("worktree "):
            # splitlines() already dropped the line terminator, so take the
            # path verbatim (no .strip()) to preserve any spaces in the path.
            main_path = line[len("worktree "):]
            break
    if not main_path:
        return (False, None)

    name_dir = Path(main_path).resolve()
    return (True, to_kebab_case(name_dir.name) or None)


def validate_session_path(session_path: Path) -> None:
    """Ensure session file lives under REVIEWS_DIR and is named session.json."""
    resolved = session_path.resolve()
    reviews_resolved = REVIEWS_DIR.resolve()
    if not resolved.is_relative_to(reviews_resolved):
        print(f"Error: Session file must be under {REVIEWS_DIR}, got: {session_path}", file=sys.stderr)
        sys.exit(1)
    if resolved.name != "session.json":
        print(f"Error: Session file must be named session.json, got: {resolved.name}", file=sys.stderr)
        sys.exit(1)


def generate_paths(session_path: Path, round_num: int) -> dict:
    """Generate prompt and output file paths for a review round.

    Args:
        session_path: Path to the session.json file
        round_num: Round number (1, 2, 3, ...)

    Returns:
        Dict with prompt_path and output_path
    """
    validate_session_path(session_path)
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    session_dir = session_path.parent

    return {
        "prompt_path": str(session_dir / f"r{round_num}-prompt.md"),
        "output_path": str(session_dir / f"r{round_num}-output.md"),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate Codex review file paths for a round")
    parser.add_argument("--session", required=True, help="Path to session.json file")
    parser.add_argument("--round", type=int, required=True, help="Round number (1, 2, 3, ...)")
    args = parser.parse_args()

    paths = generate_paths(Path(args.session), args.round)
    print(json.dumps(paths))


if __name__ == "__main__":
    main()
