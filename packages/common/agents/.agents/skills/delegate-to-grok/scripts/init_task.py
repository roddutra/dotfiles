#!/usr/bin/env python3
"""Initialize a Grok delegation session — one session per task.

Creates the session directory and session.json:

  ~/.grok-delegate/<project>/<YYYY-MM-DD>/<HHMMSS-title>/session.json

A session is a single Grok conversation with its own context window. It
must hold exactly ONE task (plus follow-up rounds on that same task). Start
a new session for every new task so unrelated work never shares context.

Optional `--worktree` creates a linked git worktree (`.worktrees/<slug>` on a
new `delegate/<slug>` branch) so several sessions can run in parallel without
touching each other's files. The executor then works inside that worktree.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from delegate_common import save_metadata
from generate_path import DELEGATE_DIR, resolve_git_project_name, to_kebab_case

# Context-window thresholds (percent of the model's window used by the last
# request). write_brief.py warns at `warn` and refuses at `block` unless
# --force. Tunable per session via init flags.
_DEFAULT_CONTEXT_WARN_PCT = 50
_DEFAULT_CONTEXT_BLOCK_PCT = 70

_VALID_EFFORTS = ("low", "medium", "high", "xhigh")


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        return None


def _resolve_git_root(project_dir: Path) -> Path:
    """Resolve project_dir to the git repository root (worktree toplevel)."""
    result = _git(["rev-parse", "--show-toplevel"], project_dir)
    if result is not None and result.returncode == 0:
        root = Path(result.stdout.strip())
        if root != project_dir.resolve():
            print(f"Note: Resolved --cd to git root: {root} (was: {project_dir})", file=sys.stderr)
        return root
    return project_dir


def _is_bare_repo(project_dir: Path) -> bool:
    result = _git(["rev-parse", "--is-bare-repository"], project_dir)
    return result is not None and result.returncode == 0 and result.stdout.strip() == "true"


def _in_git_work_tree(project_dir: Path) -> bool:
    result = _git(["rev-parse", "--is-inside-work-tree"], project_dir)
    return result is not None and result.returncode == 0 and result.stdout.strip() == "true"


def _git_head(project_dir: Path) -> str | None:
    result = _git(["rev-parse", "HEAD"], project_dir)
    if result is not None and result.returncode == 0:
        return result.stdout.strip()
    return None


def _git_branch(project_dir: Path) -> str | None:
    result = _git(["rev-parse", "--abbrev-ref", "HEAD"], project_dir)
    if result is not None and result.returncode == 0:
        return result.stdout.strip()
    return None


def _ensure_gitignored(project_dir: Path, pattern: str) -> None:
    """Make sure the directory `pattern` (e.g. ".tmp/") is ignored in this
    repo. Anything the scripts create inside the project must never leak
    into the user's commits. Skips when git already ignores it (via any
    equivalent pattern or a global excludes file)."""
    probe = _git(["check-ignore", "-q", pattern.rstrip("/")], project_dir)
    if probe is not None and probe.returncode == 0:
        return
    gitignore = project_dir / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if pattern in content.splitlines():
            return
        if content and not content.endswith("\n"):
            content += "\n"
        content += pattern + "\n"
        gitignore.write_text(content)
    else:
        gitignore.write_text(pattern + "\n")


def _ensure_tmp_gitignored(project_dir: Path) -> None:
    """Create .tmp/ in the project and ensure it's in .gitignore."""
    (project_dir / ".tmp").mkdir(exist_ok=True)
    _ensure_gitignored(project_dir, ".tmp/")


def _create_worktree(repo_root: Path, slug: str) -> Path:
    """Create `.worktrees/<slug>` on a new `delegate/<slug>` branch from HEAD.

    Only committed state is present in the worktree: uncommitted changes in
    the main checkout are NOT carried over."""
    worktrees_dir = repo_root / ".worktrees"
    worktrees_dir.mkdir(exist_ok=True)
    _ensure_gitignored(repo_root, ".worktrees/")
    path = worktrees_dir / slug
    branch = f"delegate/{slug}"
    if path.exists():
        print(f"Error: worktree path already exists: {path}", file=sys.stderr)
        sys.exit(1)
    result = _git(["worktree", "add", "-b", branch, str(path), "HEAD"], repo_root)
    if result is None or result.returncode != 0:
        err = (result.stderr.strip() if result else "git not found")
        print(f"Error: failed to create worktree {path} on branch {branch}:\n{err}", file=sys.stderr)
        sys.exit(1)
    print(f"Note: created worktree {path} (branch {branch})", file=sys.stderr)
    return path


def _resolve_project(project: str | None, force_project: str | None, start_dir: Path) -> str:
    """Effective project name: --force-project > git-derived > --project (non-git only)."""
    if force_project is not None:
        return force_project
    in_git, git_name = resolve_git_project_name(start_dir)
    if in_git and git_name:
        if project is not None:
            print(
                f"Note: Inside a git repo, using git-derived project name {git_name!r}; "
                f"ignoring --project {project!r}. Pass --force-project to override.",
                file=sys.stderr,
            )
        return git_name
    if project is not None:
        return project
    print(
        "Error: project name could not be derived from git. Pass --project <name>.",
        file=sys.stderr,
    )
    sys.exit(1)


def init_task(
    title: str,
    project: str | None = None,
    force_project: str | None = None,
    project_dir: Path | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    allow_git: bool = False,
    verify: list[str] | None = None,
    worktree: bool = False,
    context_warn_pct: int = _DEFAULT_CONTEXT_WARN_PCT,
    context_block_pct: int = _DEFAULT_CONTEXT_BLOCK_PCT,
    extra: dict | None = None,
) -> dict:
    """Create the session directory and return its metadata path.

    `model` is locked for the session (changing models mid-task changes the
    executor's behaviour unpredictably; start a new session instead).
    `reasoning_effort` seeds the value; run_task.py may override per round.
    When both are omitted the local Grok CLI defaults apply (the account's
    default model and its default effort), so the skill tracks CLI/model
    upgrades for free.
    """
    DELEGATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    DELEGATE_DIR.chmod(0o700)

    if reasoning_effort is not None and reasoning_effort not in _VALID_EFFORTS:
        print(
            f"Warning: unusual reasoning effort {reasoning_effort!r} (known: "
            f"{', '.join(_VALID_EFFORTS)}); passing it through unchanged.",
            file=sys.stderr,
        )
    if not 0 < context_warn_pct <= context_block_pct <= 100:
        print("Error: need 0 < --context-warn-pct <= --context-block-pct <= 100", file=sys.stderr)
        sys.exit(1)

    if project_dir is None:
        project_dir = Path.cwd()

    if _is_bare_repo(project_dir):
        print(f"Error: {project_dir} is a bare git repository (no working tree).", file=sys.stderr)
        sys.exit(1)
    if not _in_git_work_tree(project_dir):
        # The change tracking (rN-changes.md) and the git-state guard need a repo.
        print(
            f"Error: {project_dir} is not inside a git work tree. The wrapper tracks "
            f"changes with git; run `git init && git add -A && git commit -m init` first.",
            file=sys.stderr,
        )
        sys.exit(1)

    effective_project = _resolve_project(project, force_project, project_dir)
    repo_root = _resolve_git_root(project_dir)

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

    session_dir = DELEGATE_DIR / project_slug / date_str / f"{time_str}-{title_slug}"
    session_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = session_dir / "session.json"
    # Claim the session (exclusive create) BEFORE creating any worktree so a
    # collision cannot leave an orphaned branch/worktree behind.
    try:
        with metadata_path.open("x") as f:
            f.write(json.dumps({"status": "initializing", "title": title}, indent=2))
    except FileExistsError:
        print(f"Error: Session already exists: {metadata_path}", file=sys.stderr)
        sys.exit(1)

    worktree_path: Path | None = None
    try:
        if worktree:
            worktree_path = _create_worktree(repo_root, f"{time_str}-{title_slug}")
        work_dir = worktree_path or repo_root
        _ensure_tmp_gitignored(work_dir)
    except BaseException:
        metadata_path.unlink(missing_ok=True)  # roll back the claim
        raise

    metadata = {
        "project": effective_project,
        "date": date_str,
        "time": time_str,
        "title": title,
        "status": "new",  # new | running | done | partial | blocked | unknown | failed | handed-off
        "current_round": 0,
        "completed_round": 0,
        "grok_session_id": None,
        "project_dir": str(work_dir.resolve()),
        "repo_root": str(repo_root.resolve()),
        "worktree": str(worktree_path.resolve()) if worktree_path else None,
        "branch_at_init": _git_branch(work_dir),
        "head_at_init": _git_head(work_dir),
        "model": model,
        "reasoning_effort": reasoning_effort,
        "allow_git": allow_git,
        "verify": verify or [],
        "context_warn_pct": context_warn_pct,
        "context_block_pct": context_block_pct,
        "usage": {
            "rounds": {},
            "session_input_tokens": 0,
            "session_output_tokens": 0,
            "last_context_tokens": None,
            "context_window": None,
            "context_pct": None,
        },
    }
    if extra:
        metadata.update(extra)

    save_metadata(metadata_path, metadata)  # atomic: replaces the provisional file

    return {
        "session": str(metadata_path),
        "project_dir": str(work_dir.resolve()),
        "worktree": str(worktree_path) if worktree_path else None,
    }


def main():
    parser = argparse.ArgumentParser(description="Initialize a Grok delegation session (one task per session)")
    parser.add_argument("--title", required=True, help="Short task title, e.g. add-rate-limiter")
    parser.add_argument("--project", default=None, help="Project name; only needed outside a git repo (ignored inside one)")
    parser.add_argument("--force-project", default=None, dest="force_project", help="Override the git-derived project name")
    parser.add_argument("--cd", default=None, help="Project directory (default: git root of cwd)")
    parser.add_argument("--model", default=None, help="Grok model for the whole session (default: local CLI config)")
    parser.add_argument("--reasoning-effort", default=None, help="Initial reasoning effort (default: local CLI config)")
    parser.add_argument("--allow-git", action="store_true", dest="allow_git", help="Let Grok commit/branch (default: git state is off-limits; you own git)")
    parser.add_argument("--verify", action="append", default=None, help="Shell command run by run_task.py after every round as an independent acceptance check (repeatable)")
    parser.add_argument("--worktree", action="store_true", help="Run the task in a fresh linked worktree (.worktrees/<slug>) for parallel isolation")
    parser.add_argument("--context-warn-pct", type=int, default=_DEFAULT_CONTEXT_WARN_PCT, help=f"Warn when the session's context use exceeds this percent (default {_DEFAULT_CONTEXT_WARN_PCT})")
    parser.add_argument("--context-block-pct", type=int, default=_DEFAULT_CONTEXT_BLOCK_PCT, help=f"Refuse further rounds above this percent unless --force (default {_DEFAULT_CONTEXT_BLOCK_PCT})")
    args = parser.parse_args()

    result = init_task(
        title=args.title,
        project=args.project,
        force_project=args.force_project,
        project_dir=Path(args.cd) if args.cd else None,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        allow_git=args.allow_git,
        verify=args.verify,
        worktree=args.worktree,
        context_warn_pct=args.context_warn_pct,
        context_block_pct=args.context_block_pct,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
