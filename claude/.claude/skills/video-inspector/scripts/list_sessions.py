#!/usr/bin/env python3
"""List and filter past video-inspection sessions.

Walks ~/.video-inspector/ for session.json files and reports each session
plus the videos processed in it. Use this from a fresh conversation to find
and reference prior inspections.

Directory structure:
  ~/.video-inspector/<project>/<YYYY-MM-DD>/<HHMMSS-title>/session.json
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from session_paths import INSPECTOR_DIR, to_kebab_case


def parse_date(date_str: str) -> str:
    today = datetime.now()
    if date_str == "today":
        return today.strftime("%Y-%m-%d")
    if date_str == "yesterday":
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")
    return date_str


def get_week_range() -> tuple[str, str]:
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d"), (monday + timedelta(days=6)).strftime("%Y-%m-%d")


def get_month_range() -> tuple[str, str]:
    today = datetime.now()
    first = today.replace(day=1)
    if today.month == 12:
        last = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    return first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")


def list_sessions(
    project: str | None = None,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    if not INSPECTOR_DIR.exists():
        return {"sessions": []}

    sessions = []
    for project_dir in sorted(INSPECTOR_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        if project and project_dir.name != to_kebab_case(project):
            continue
        for date_dir in sorted(project_dir.iterdir()):
            if not date_dir.is_dir():
                continue
            dir_date = date_dir.name
            if date and dir_date != date:
                continue
            if date_from and dir_date < date_from:
                continue
            if date_to and dir_date > date_to:
                continue
            for session_dir in sorted(d for d in date_dir.iterdir() if d.is_dir()):
                session_file = session_dir / "session.json"
                if not session_file.exists():
                    continue
                try:
                    metadata = json.loads(session_file.read_text())
                except (json.JSONDecodeError, OSError):
                    continue
                sessions.append({
                    "session_path": str(session_file),
                    "project": metadata.get("project"),
                    "title": metadata.get("title"),
                    "date": metadata.get("date"),
                    "time": metadata.get("time"),
                    "videos": metadata.get("videos", []),
                })
    return {"sessions": sessions}


def main():
    parser = argparse.ArgumentParser(description="List past video-inspection sessions")
    parser.add_argument("--project", help="Filter by project name (slug)")
    parser.add_argument("--date", help="Filter by date: YYYY-MM-DD, 'today', or 'yesterday'")
    parser.add_argument("--from", dest="date_from", help="Start of date range (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", help="End of date range (YYYY-MM-DD)")
    parser.add_argument("--week", action="store_true", help="Sessions from the current week")
    parser.add_argument("--month", action="store_true", help="Sessions from the current month")
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

    result = list_sessions(project=args.project, date=date, date_from=date_from, date_to=date_to)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
