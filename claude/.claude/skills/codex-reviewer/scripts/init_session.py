#!/usr/bin/env python3
"""Initialize a Codex review session.

Creates a nested directory structure and writes a session.json metadata
file. The directory hierarchy encodes project, date, and session identity:

  ~/.codex-reviews/<project>/<YYYY-MM-DD>/<HHMMSS-title>/session.json
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from generate_path import REVIEWS_DIR, resolve_git_project_name, to_kebab_case


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


def _is_bare_repo(project_dir: Path) -> bool:
    """True if project_dir is inside a bare git repository (no working tree)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-bare-repository"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


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


def _resolve_project(
    project: str | None, force_project: str | None, start_dir: Path
) -> str:
    """Determine the effective project name for the session.

    Precedence:
      1. `--force-project` always wins, anywhere. It is the deliberate escape
         hatch for naming a project something other than the git-derived name
         (e.g. splitting one repo into several logical projects).
      2. Inside a git work tree, the git-derived name is authoritative: a plain
         `--project` is ignored (with a note) so reviews never fragment across
         worktree-named projects. The note also nudges the caller toward
         `--force-project` when an override is genuinely intended.
      3. In a non-git directory, an explicit name is required: `--project`
         (or `--force-project`) must be supplied. (Bare repos never reach here;
         `init_session` rejects them up front.)

    `--force-project` is named distinctly from `--project` on purpose: the
    primary caller is an LLM whose habit of inventing `--project` values caused
    the original mis-naming, so the escape hatch must be something it will only
    reach for deliberately.
    """
    # `is not None` (not truthiness): an explicitly-supplied empty string should
    # fall through to the empty-slug validation downstream, not be treated as
    # "flag absent" and silently replaced by the git-derived name.
    if force_project is not None:
        return force_project

    in_git, git_name = resolve_git_project_name(start_dir)

    if in_git and git_name:
        if project is not None:
            print(
                f"Note: Inside a git repo, using git-derived project name "
                f"{git_name!r}; ignoring --project {project!r}. Pass "
                f"--force-project to override the git-derived name.",
                file=sys.stderr,
            )
        return git_name

    if project is not None:
        return project

    if in_git:
        # In a work tree, but the repo directory name slugified to empty.
        print(
            "Error: Inside a git repository, but a project name could not be "
            "derived from the repository directory. Pass --project <name> (or "
            "--force-project <name>) to name this review project.",
            file=sys.stderr,
        )
    else:
        print(
            "Error: Not inside a git repository, so the project name cannot be "
            "derived automatically. Pass --project <name> to name this review "
            "project.",
            file=sys.stderr,
        )
    sys.exit(1)


def init_session(
    project: str | None,
    title: str,
    project_dir: Path | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    force_project: str | None = None,
) -> dict:
    """Create the session directory and return session metadata path.

    If neither `project` nor `force_project` is given, the project name is
    derived from the git repository (shared across worktrees); see
    `_resolve_project`. If `project_dir` is None, auto-detects from cwd via
    git rev-parse.

    `model` is locked for the lifetime of the session — `run_review.py`
    cannot override it, since changing models mid-session can materially
    change Codex's outputs across rounds. To use a different model, start
    a fresh session.

    `reasoning_effort` seeds the initial value. `run_review.py` may update
    it on a later round (per-round overrides are persisted back into
    session metadata), so this is just the starting setting.
    """
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    REVIEWS_DIR.chmod(0o700)

    # Default to cwd if --cd not provided. This is the directory from which both
    # the project name and the git root are resolved.
    if project_dir is None:
        project_dir = Path.cwd()

    # A bare repo has no working tree: Codex cannot review files in it, and we
    # must not scaffold .tmp/ into a work-tree-less layout. Reject early, before
    # any name resolution or .tmp setup, regardless of an explicit project name.
    if _is_bare_repo(project_dir):
        print(
            f"Error: Project directory is a bare git repository (no working "
            f"tree): {project_dir}. Codex needs a working tree to review files; "
            f"run from a normal checkout instead.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve the project name BEFORE collapsing project_dir to the worktree
    # root. The name is the main working tree's basename (shared across all
    # worktrees of a repo), while the --cd root below is this checkout's own
    # toplevel (--show-toplevel) so Codex reads the files where you launched.
    effective_project = _resolve_project(project, force_project, project_dir)

    resolved_root = _resolve_git_root(project_dir)
    _ensure_tmp_gitignored(resolved_root)

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

    session_dir = REVIEWS_DIR / project_slug / date_str / f"{time_str}-{title_slug}"

    session_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "project": effective_project,
        "date": date_str,
        "time": time_str,
        "title": title,
        "current_round": 0,
        "codex_session_id": None,
        "project_dir": str(resolved_root),
        "model": model,
        "reasoning_effort": reasoning_effort,
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
    parser.add_argument(
        "--project", default=None,
        help=(
            "Project name. Optional inside a git repository, where the name is "
            "derived from the repo root and shared across worktrees, so omit "
            "this flag in a repo (it is ignored there). Required only when "
            "running outside any git repository."
        ),
    )
    parser.add_argument(
        "--force-project", default=None, dest="force_project",
        help=(
            "Force a specific project name, overriding the git-derived name "
            "even inside a repository. Use only to deliberately name a project "
            "something other than its repo (e.g. splitting one repo into "
            "several logical projects). Unlike --project, this is honored "
            "inside a git repo."
        ),
    )
    parser.add_argument("--title", required=True, help="Review title (e.g., prd-review)")
    parser.add_argument("--cd", default=None, help="Project directory override (default: auto-detect git root from cwd)")
    parser.add_argument(
        "--model", default=None,
        help=(
            "Optional Codex model for the entire session (e.g. gpt-5.5). "
            "Persisted into session metadata and used for every round. "
            "Cannot be changed after init — start a fresh session to use "
            "a different model. If omitted, Codex uses its locally-"
            "configured default."
        ),
    )
    parser.add_argument(
        "--reasoning-effort", default=None,
        help=(
            "Optional initial reasoning effort (e.g. low, medium, high). "
            "Persisted into session metadata. May be overridden on a "
            "per-round basis via run_review.py --reasoning-effort, which "
            "also updates the persisted value. If omitted, Codex uses "
            "its locally-configured default."
        ),
    )
    args = parser.parse_args()

    result = init_session(
        args.project,
        args.title,
        project_dir=Path(args.cd) if args.cd else None,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        force_project=args.force_project,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
