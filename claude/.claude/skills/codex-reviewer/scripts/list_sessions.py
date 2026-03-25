#!/usr/bin/env python3
"""List and filter past Codex review sessions.

Scans the reviews directory for session metadata files and returns
matching sessions with their associated prompt/output files. Useful
for discovering previous review history from a fresh conversation.
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

REVIEWS_DIR = Path("/tmp/codex-reviews")


def parse_date(date_str: str) -> str:
    """Normalize a date string to YYYYMMDD format."""
    today = datetime.now()
    if date_str == "today":
        return today.strftime("%Y%m%d")
    if date_str == "yesterday":
        return (today - timedelta(days=1)).strftime("%Y%m%d")
    # Accept YYYY-MM-DD or YYYYMMDD
    return date_str.replace("-", "")


def get_week_range() -> tuple[str, str]:
    """Return (monday, sunday) of the current week as YYYYMMDD strings."""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y%m%d"), sunday.strftime("%Y%m%d")


def get_month_range() -> tuple[str, str]:
    """Return (first_day, last_day) of the current month as YYYYMMDD strings."""
    today = datetime.now()
    first = today.replace(day=1)
    # Last day: next month's first day minus one day
    if today.month == 12:
        last = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    return first.strftime("%Y%m%d"), last.strftime("%Y%m%d")


def find_session_files(session_path: Path) -> list[str]:
    """Find all prompt and output files belonging to a session."""
    metadata = json.loads(session_path.read_text())
    base_prefix = metadata["base_prefix"]

    files = sorted(
        str(f) for f in REVIEWS_DIR.glob(f"{base_prefix}-r*")
        if f.suffix in (".md", ".txt")
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
        project: Filter by project name (exact match)
        date: Filter by specific date (YYYYMMDD)
        date_from: Start of date range (YYYYMMDD), inclusive
        date_to: End of date range (YYYYMMDD), inclusive

    Returns:
        Dict with list of matching sessions
    """
    if not REVIEWS_DIR.exists():
        return {"sessions": []}

    sessions = []
    for session_path in sorted(REVIEWS_DIR.glob("*-session.json")):
        try:
            metadata = json.loads(session_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        # Filter by project
        if project and metadata.get("project") != project:
            continue

        # Extract date portion from timestamp (YYYYMMDD-HHMMSS -> YYYYMMDD)
        ts = metadata.get("timestamp", "")
        session_date = ts.split("-")[0] if "-" in ts else ts

        # Filter by exact date
        if date and session_date != date:
            continue

        # Filter by date range
        if date_from and session_date < date_from:
            continue
        if date_to and session_date > date_to:
            continue

        files = find_session_files(session_path)

        sessions.append({
            "session_path": str(session_path),
            "project": metadata.get("project"),
            "title": metadata.get("title"),
            "timestamp": ts,
            "current_round": metadata.get("current_round", 0),
            "codex_session_id": metadata.get("codex_session_id"),
            "files": files,
        })

    return {"sessions": sessions}


def main():
    parser = argparse.ArgumentParser(description="List past Codex review sessions")
    parser.add_argument("--project", help="Filter by project name")
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
