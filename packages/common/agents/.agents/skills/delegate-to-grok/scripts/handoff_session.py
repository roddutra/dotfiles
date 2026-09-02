#!/usr/bin/env python3
"""Hand a task off from a saturated (or dead) session to a fresh one.

Creates a new session with the same project dir, model, effort,
git and verify settings, then copies the old session's briefs, reports and
change summaries into `<project_dir>/.tmp/grok-delegate/<old-session>/` so
the new Grok thread can read them from disk. The new session starts with
an empty context window; the wrapper never inlines old transcripts.

Prints the new `session` path and the `handoff_dir` to reference in the
round-1 brief ("Read .tmp/grok-delegate/<old>/r*-report.md for what was
already done").
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from delegate_common import SessionLock, load_metadata, save_metadata
from generate_path import validate_session_path
from init_task import _ensure_tmp_gitignored, init_task


def handoff(old_session: Path, title: str) -> dict:
    validate_session_path(old_session)
    load_metadata(old_session)
    with SessionLock(old_session):
        return _handoff_locked(old_session, title)


def _handoff_locked(old_session: Path, title: str) -> dict:
    old = load_metadata(old_session)
    if old.get("status") == "running":
        print("Error: a run_task.py is still running for this session; wait for it before handing off.", file=sys.stderr)
        sys.exit(1)
    project_dir = Path(old["project_dir"])
    if not project_dir.is_dir():
        print(f"Error: project directory no longer exists: {project_dir}", file=sys.stderr)
        sys.exit(1)

    new = init_task(
        title=title,
        force_project=old.get("project"),
        project_dir=project_dir,
        model=old.get("model"),
        reasoning_effort=old.get("reasoning_effort"),
        allow_git=bool(old.get("allow_git")),
        verify=list(old.get("verify") or []),
        worktree=False,  # reuse the existing checkout/worktree
        context_warn_pct=int(old.get("context_warn_pct", 50)),
        context_block_pct=int(old.get("context_block_pct", 70)),
        extra={"handoff_from": str(old_session)},
    )
    new_session = Path(new["session"])
    new_meta = json.loads(new_session.read_text())
    # Keep pointing at the same worktree as the old session, if any.
    new_meta["worktree"] = old.get("worktree")
    new_meta["repo_root"] = old.get("repo_root", new_meta.get("repo_root"))
    save_metadata(new_session, new_meta)

    old_dir = old_session.parent
    _ensure_tmp_gitignored(project_dir)  # .tmp/ may have been deleted since init
    handoff_dir = project_dir / ".tmp" / "grok-delegate" / old_dir.name
    handoff_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for f in sorted(old_dir.iterdir()):
        if f.suffix == ".md" and f.name.startswith("r"):
            shutil.copy2(f, handoff_dir / f.name)
            copied.append(str((handoff_dir / f.name).relative_to(project_dir)))

    old["status"] = "handed-off"
    old["handoff_to"] = str(new_session)
    save_metadata(old_session, old)

    return {
        "session": str(new_session),
        "project_dir": str(project_dir),
        "handoff_dir": str(handoff_dir.relative_to(project_dir)),
        "copied": copied,
        "note": "Tell Grok in the round-1 brief to read the copied reports for prior progress; do not inline them.",
    }


def main():
    parser = argparse.ArgumentParser(description="Start a fresh session that continues a task from an old one")
    parser.add_argument("--session", required=True, help="Old session.json path")
    parser.add_argument("--title", required=True, help="Title for the new session (e.g. add-rate-limiter-part2)")
    args = parser.parse_args()
    print(json.dumps(handoff(Path(args.session), args.title), indent=2))


if __name__ == "__main__":
    main()
