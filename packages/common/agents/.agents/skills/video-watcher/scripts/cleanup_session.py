#!/usr/bin/env python3
"""Delete a video-watcher session: its prompts, answers and prepared videos.

Removes the whole session directory and prunes empty parent folders. Source
videos are never copied into a session, so they are untouched. Uploads left
on the provider are separate; see remote_files.py.

User-initiated only. An answer costs money to regenerate, so never clean up
unless the user asks.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from session_paths import STORE_DIR, validate_session_path


def main():
    parser = argparse.ArgumentParser(description="Delete a video-watcher session")
    parser.add_argument("--session", required=True, help="Path to session.json")
    args = parser.parse_args()

    session_path = Path(args.session).expanduser()
    validate_session_path(session_path)
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)
    session_dir = session_path.resolve().parent
    base = STORE_DIR.resolve()
    if session_dir == base or not session_dir.is_relative_to(base):
        print(f"Error: refusing to delete outside {STORE_DIR}: {session_dir}", file=sys.stderr)
        sys.exit(1)

    shutil.rmtree(session_dir)
    parent = session_dir.parent
    while parent != base and parent.is_relative_to(base) and parent.exists() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent
    print(json.dumps({"removed_session_dir": str(session_dir)}))


if __name__ == "__main__":
    main()
