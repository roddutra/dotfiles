#!/usr/bin/env python3
"""List past video-watcher sessions and the calls made in each.

Use this from a fresh conversation to find an earlier answer and read it
again instead of paying for the same question twice.

  ~/.video-watcher/<project>/<YYYY-MM-DD>/<HHMMSS-title>/session.json
"""

import argparse
import json
from datetime import datetime, timedelta

from session_paths import STORE_DIR, to_kebab_case


def parse_date(value: str) -> str:
    today = datetime.now()
    if value == "today":
        return today.strftime("%Y-%m-%d")
    if value == "yesterday":
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")
    return value


def week_range() -> tuple[str, str]:
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d"), (monday + timedelta(days=6)).strftime("%Y-%m-%d")


def month_range() -> tuple[str, str]:
    today = datetime.now()
    first = today.replace(day=1)
    following = first.replace(year=first.year + 1, month=1) if first.month == 12 else first.replace(month=first.month + 1)
    return first.strftime("%Y-%m-%d"), (following - timedelta(days=1)).strftime("%Y-%m-%d")


def list_sessions(project=None, date=None, date_from=None, date_to=None) -> dict:
    sessions = []
    if not STORE_DIR.exists():
        return {"sessions": sessions}
    for project_dir in sorted(p for p in STORE_DIR.iterdir() if p.is_dir()):
        if project and project_dir.name != to_kebab_case(project):
            continue
        for date_dir in sorted(d for d in project_dir.iterdir() if d.is_dir()):
            day = date_dir.name
            if (date and day != date) or (date_from and day < date_from) or (date_to and day > date_to):
                continue
            for session_dir in sorted(d for d in date_dir.iterdir() if d.is_dir()):
                session_file = session_dir / "session.json"
                try:
                    metadata = json.loads(session_file.read_text())
                except (OSError, json.JSONDecodeError):
                    continue
                sessions.append({
                    "session_path": str(session_file),
                    "project": metadata.get("project"),
                    "title": metadata.get("title"),
                    "date": metadata.get("date"),
                    "time": metadata.get("time"),
                    "calls": metadata.get("calls", []),
                })
    return {"sessions": sessions}


def main():
    parser = argparse.ArgumentParser(description="List past video-watcher sessions")
    parser.add_argument("--project", help="Filter by project name")
    parser.add_argument("--date", help="YYYY-MM-DD, 'today' or 'yesterday'")
    parser.add_argument("--from", dest="date_from", help="Start of a date range (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", help="End of a date range (YYYY-MM-DD)")
    parser.add_argument("--week", action="store_true", help="The current week")
    parser.add_argument("--month", action="store_true", help="The current month")
    args = parser.parse_args()

    date = parse_date(args.date) if args.date else None
    date_from, date_to = args.date_from, args.date_to
    if args.week:
        date_from, date_to = week_range()
    if args.month:
        date_from, date_to = month_range()
    print(json.dumps(list_sessions(
        project=args.project,
        date=date,
        date_from=parse_date(date_from) if date_from else None,
        date_to=parse_date(date_to) if date_to else None,
    ), indent=2))


if __name__ == "__main__":
    main()
