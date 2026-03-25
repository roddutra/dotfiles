#!/usr/bin/env python3
"""List and filter past Codex review sessions.

Walks the directory tree under /tmp/codex-reviews/ looking for session.json
files. Supports filtering by project, date, date range, week, and month.

Directory structure:
  /tmp/codex-reviews/<project>/<YYYY-MM-DD>/<HHMMSS-title>/session.json
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from generate_path import REVIEWS_DIR, to_kebab_case


def parse_date(date_str: str) -> str:
    """Normalize a date string to YYYY-MM-DD format."""
    today = datetime.now()
    if date_str == "today":
        return today.strftime("%Y-%m-%d")
    if date_str == "yesterday":
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")
    # Already YYYY-MM-DD
    return date_str


def get_week_range() -> tuple[str, str]:
    """Return (monday, sunday) of the current week as YYYY-MM-DD strings."""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def get_month_range() -> tuple[str, str]:
    """Return (first_day, last_day) of the current month as YYYY-MM-DD strings."""
    today = datetime.now()
    first = today.replace(day=1)
    if today.month == 12:
        last = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    return first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")


def find_round_files(session_dir: Path) -> list[str]:
    """Find all prompt and output files in a session directory."""
    files = sorted(
        str(f) for f in session_dir.iterdir()
        if f.suffix == ".md" and f.name.startswith("r")
    )
    return files


def list_sessions(
    project: str | None = None,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """List sessions matching the given filters.

    Args:
        project: Filter by project name (matches project directory slug)
        date: Filter by specific date (YYYY-MM-DD)
        date_from: Start of date range (YYYY-MM-DD), inclusive
        date_to: End of date range (YYYY-MM-DD), inclusive

    Returns:
        Dict with list of matching sessions
    """
    if not REVIEWS_DIR.exists():
        return {"sessions": []}

    sessions = []

    # Walk: project dirs -> date dirs -> session dirs -> session.json
    for project_dir in sorted(REVIEWS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue

        # Filter by project (slugify input to match directory name)
        if project and project_dir.name != to_kebab_case(project):
            continue

        for date_dir in sorted(project_dir.iterdir()):
            if not date_dir.is_dir():
                continue

            dir_date = date_dir.name  # YYYY-MM-DD

            # Filter by exact date
            if date and dir_date != date:
                continue

            # Filter by date range
            if date_from and dir_date < date_from:
                continue
            if date_to and dir_date > date_to:
                continue

            for session_dir in sorted(session_dir for session_dir in date_dir.iterdir() if session_dir.is_dir()):
                session_file = session_dir / "session.json"
                if not session_file.exists():
                    continue

                try:
                    metadata = json.loads(session_file.read_text())
                except (json.JSONDecodeError, OSError):
                    continue

                files = find_round_files(session_dir)

                sessions.append({
                    "session_path": str(session_file),
                    "project": metadata.get("project"),
                    "title": metadata.get("title"),
                    "date": metadata.get("date"),
                    "time": metadata.get("time"),
                    "current_round": metadata.get("current_round", 0),
                    "codex_session_id": metadata.get("codex_session_id"),
                    "files": files,
                })

    return {"sessions": sessions}


def main():
    parser = argparse.ArgumentParser(description="List past Codex review sessions")
    parser.add_argument("--project", help="Filter by project name (slug)")
    parser.add_argument(
        "--date",
        help="Filter by date: YYYY-MM-DD, 'today', or 'yesterday'",
    )
    parser.add_argument("--from", dest="date_from", help="Start of date range (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", help="End of date range (YYYY-MM-DD)")
    parser.add_argument("--week", action="store_true", help="Show sessions from the current week")
    parser.add_argument("--month", action="store_true", help="Show sessions from the current month")
    args = parser.parse_args()

    date = None
    date_from = args.date_from
    date_to = args.date_to

    if args.date:
        date = parse_date(args.date)
    if args.week:
        date_from, date_to = get_week_range()
    if args.month:
        date_from, date_to = get_month_range()

    if date_from:
        date_from = parse_date(date_from)
    if date_to:
        date_to = parse_date(date_to)

    result = list_sessions(
        project=args.project,
        date=date,
        date_from=date_from,
        date_to=date_to,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
