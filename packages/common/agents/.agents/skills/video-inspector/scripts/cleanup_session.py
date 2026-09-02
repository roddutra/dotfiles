#!/usr/bin/env python3
"""Delete a video-inspection session and its extracted frames/videos.

Removes the entire session directory (all per-video subfolders, their frames,
copied source videos, and manifests, plus session.json) and prunes empty
parent directories up to INSPECTOR_DIR.

Because frames and copied videos can take real disk space, cleanup matters
more here than for text-only skills -- but it is still user-initiated only.
Never clean up unless the user explicitly asks; they may want to revisit an
inspection later.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from session_paths import INSPECTOR_DIR, validate_session_path


def cleanup_session(session_path: Path) -> dict:
    validate_session_path(session_path)
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    session_dir = session_path.parent

    # Guard: the session directory must sit under INSPECTOR_DIR (validated via
    # the session file above) before we recursively delete it.
    if not session_dir.resolve().is_relative_to(INSPECTOR_DIR.resolve()):
        print(f"Error: refusing to delete outside {INSPECTOR_DIR}: {session_dir}", file=sys.stderr)
        sys.exit(1)

    # Count videos for the report before removing.
    try:
        metadata = json.loads(session_path.read_text())
        video_count = len(metadata.get("videos", []))
    except (json.JSONDecodeError, OSError):
        video_count = None

    shutil.rmtree(session_dir)

    # Prune empty parent directories (date, then project) up to INSPECTOR_DIR.
    base = INSPECTOR_DIR.resolve()
    parent = session_dir.parent
    while parent.resolve() != base and parent.resolve().is_relative_to(base):
        if parent.exists() and not any(parent.iterdir()):
            grandparent = parent.parent
            parent.rmdir()
            parent = grandparent
        else:
            break

    return {"removed_session_dir": str(session_dir), "video_count": video_count}


def main():
    parser = argparse.ArgumentParser(description="Delete a video-inspection session")
    parser.add_argument("--session", required=True, help="Path to session.json")
    args = parser.parse_args()
    result = cleanup_session(Path(args.session))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
