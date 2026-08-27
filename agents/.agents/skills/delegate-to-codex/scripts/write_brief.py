#!/usr/bin/env python3
"""Write the task brief for the next round, from stdin.

Round 1 is the task brief; later rounds are follow-ups on the same task
(review feedback, fixes, scope clarifications). The script:

- validates the brief has the required sections (round 1: a `Task` heading
  and a `Done when` / `Acceptance` heading — the executor needs a clear goal
  and a clear stop condition);
- refuses to continue a session whose context window is already at/over the
  block threshold (see init_task.py) unless --force — start a new session
  via handoff_session.py instead of polluting a full one;
- refuses a new round while the previous round has no report (unless
  --force, for kill/timeout recovery);
- appends the executor contract (git rules, "do not stop on a question",
  report format) so every brief enforces the same process;
- increments current_round and writes rN-brief.md.

Usage:
    cat <<'BRIEF' | python write_brief.py --session <path> [--force]
    ## Task
    ...
    BRIEF
"""

import argparse
import json
import re
import sys
from pathlib import Path

from delegate_common import SessionLock, load_metadata, save_metadata
from generate_path import generate_paths

_TASK_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*task\b", re.IGNORECASE | re.MULTILINE)
_DONE_HEADING = re.compile(
    r"^\s{0,3}#{1,6}\s*(done when|acceptance|acceptance criteria|definition of done)\b",
    re.IGNORECASE | re.MULTILINE,
)

_REPORT_FORMAT = """## Status
DONE | PARTIAL | BLOCKED — one line on the outcome.

## What changed
- `path/to/file` — one line per file (or "No files changed" and why).

## Verification
- `command` — pass/fail and the one-line result. Say explicitly if you could not run something.

## Assumptions & risks
- Decisions you made without being told; anything the lead should double-check.

## Blocked / questions
Only when Status is PARTIAL or BLOCKED: the exact question or obstacle, with what you tried."""

_GIT_RULE_LOCKED = (
    "- Do NOT commit, push, stash, rebase, reset, switch branches, or otherwise "
    "change git state. Leave all changes uncommitted in the working tree; the "
    "engineering lead owns git."
)
_GIT_RULE_OPEN = (
    "- You may create commits on the current branch when the task says so. "
    "Never push, rebase, reset, force-update, or switch branches."
)


def executor_contract(round_num: int, allow_git: bool) -> str:
    git_rule = _GIT_RULE_OPEN if allow_git else _GIT_RULE_LOCKED
    if round_num == 1:
        return f"""

---
## Executor contract (added by the delegate-to-codex wrapper — do not skip)
You are the implementer for exactly the task above. An engineering lead (a separate agent) will review your work from your report and the diff, then send follow-ups in this same session.

- Work only inside the project directory you were started in. Change what the task needs and nothing unrelated.
{git_rule}
- Do not stop to ask a question. If something is ambiguous, make the smallest safe assumption, proceed, and list it under "Assumptions & risks". Only if you truly cannot proceed, stop with Status BLOCKED and put the exact question under "Blocked / questions".
- If the task expected code changes and you made none, say so plainly — never report DONE without the changes.
- Run the tests/linters/build relevant to what you touched and report the real results. Do not claim verification you did not run.
- Your final message is the report. It must follow the exact format below, stay under 400 words, and contain no code dumps — reference files and line numbers instead.

{_REPORT_FORMAT}
"""
    return f"""

---
## Executor contract (reminder)
Same rules as round 1: stay inside the project directory; {git_rule[2:]} Do not stop on a question — assume the smallest safe thing and record it. Finish with the report in the same format (Status / What changed / Verification / Assumptions & risks / Blocked), under 400 words, no code dumps.
"""


def write_brief(session_path: Path, content: str, force: bool = False) -> dict:
    if not content.strip():
        print("Error: No brief content received on stdin", file=sys.stderr)
        sys.exit(1)
    load_metadata(session_path)
    with SessionLock(session_path):
        return _write_brief_locked(session_path, content, force)


def _write_brief_locked(session_path: Path, content: str, force: bool) -> dict:
    metadata = load_metadata(session_path)
    if metadata.get("status") == "handed-off":
        print(
            f"Error: this session was handed off to {metadata.get('handoff_to')}; write "
            f"briefs against that session instead.",
            file=sys.stderr,
        )
        sys.exit(1)
    if metadata.get("status") == "running":
        print(
            "Error: a run_task.py is still running (or died without cleanup) for this "
            "session. Wait for its completion notification before writing the next brief.",
            file=sys.stderr,
        )
        sys.exit(1)

    current_round = metadata.get("current_round", 0)
    round_num = current_round + 1

    # --- Context-window guard -------------------------------------------
    usage = metadata.get("usage") or {}
    pct = usage.get("context_pct")
    warn_pct = metadata.get("context_warn_pct", 50)
    block_pct = metadata.get("context_block_pct", 70)
    if pct is not None:
        if pct >= block_pct and not force:
            print(
                f"Error: this session's context window is {pct:.0f}% used "
                f"({usage.get('last_context_tokens')} of {usage.get('context_window')} tokens), "
                f"above the block threshold ({block_pct}%). Do not keep piling rounds "
                f"onto a nearly-full session — Codex's quality degrades and it may "
                f"compact away earlier instructions.\n"
                f"Start a fresh session for the remaining work with "
                f"`handoff_session.py --session {session_path} --title <new-title>` "
                f"(it copies this session's briefs/reports into .tmp/ for the new "
                f"session to read). Pass --force only if the user explicitly wants "
                f"to continue this session anyway.",
                file=sys.stderr,
            )
            sys.exit(1)
        if pct >= warn_pct:
            print(
                f"Warning: session context is {pct:.0f}% used (warn threshold "
                f"{warn_pct}%, block {block_pct}%). Keep this follow-up small and "
                f"plan a handoff to a fresh session for further work.",
                file=sys.stderr,
            )

    # --- Previous round must have completed ------------------------------
    if current_round > 0 and not force:
        if metadata.get("last_round_failed") == current_round:
            print(
                f"Error: Round {current_round} failed (timeout/stall/CLI error/no report) and "
                f"has not been re-run successfully. Re-run `run_task.py --session {session_path}` "
                f"first — the round-{current_round} brief is still on disk. Use --force only to "
                f"deliberately abandon that round and move on (e.g. to split the task).",
                file=sys.stderr,
            )
            sys.exit(1)
        prev = generate_paths(session_path, current_round)
        prev_report = Path(prev["report_path"])
        if not prev_report.exists() or prev_report.stat().st_size == 0:
            print(
                f"Error: Round {current_round} has no report yet. Run run_task.py "
                f"before writing the next brief. Use --force only if the previous "
                f"round was killed/timed out and you are deliberately moving on.",
                file=sys.stderr,
            )
            sys.exit(1)

    # --- Round-1 structure check ------------------------------------------
    if round_num == 1 and not force:
        missing = []
        if not _TASK_HEADING.search(content):
            missing.append("`## Task` (what to build/change, precisely)")
        if not _DONE_HEADING.search(content):
            missing.append("`## Done when` (observable acceptance criteria)")
        if missing:
            print(
                "Error: the round-1 brief is missing required sections:\n  - "
                + "\n  - ".join(missing)
                + "\nA delegated task needs an explicit goal and an explicit stop "
                "condition, otherwise the executor guesses. See SKILL.md → "
                "'Brief template'. Use --force to bypass (not recommended).",
                file=sys.stderr,
            )
            sys.exit(1)

    paths = generate_paths(session_path, round_num)
    brief_path = Path(paths["brief_path"])
    if brief_path.exists():
        print(f"Error: Brief file already exists: {brief_path}", file=sys.stderr)
        sys.exit(1)

    full = content.rstrip("\n") + executor_contract(round_num, bool(metadata.get("allow_git")))
    brief_path.write_text(full)

    metadata["current_round"] = round_num
    save_metadata(session_path, metadata)

    result = {
        "brief_path": str(brief_path),
        "report_path": paths["report_path"],
        "round": round_num,
    }
    if pct is not None:
        result["context_pct"] = pct
    return result


def main():
    parser = argparse.ArgumentParser(description="Write the next-round task brief from stdin")
    parser.add_argument("--session", required=True, help="Path to session metadata JSON file")
    parser.add_argument("--force", action="store_true", help="Bypass the previous-report, structure and context-window checks")
    args = parser.parse_args()
    print(json.dumps(write_brief(Path(args.session), sys.stdin.read(), force=args.force)))


if __name__ == "__main__":
    main()
