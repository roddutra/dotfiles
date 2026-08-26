#!/usr/bin/env python3
"""Preflight dependency check for the video-inspector skill.

Reports whether ffmpeg/ffprobe are installed, the detected OS, overlay
capability, and the OS-appropriate install command(s). Run this first: if
`ready` is false, surface the install command to the user and ask permission
before installing anything -- installing system packages changes their
machine and is the user's call, not the agent's.

Exit code is 0 when ready, 1 when ffmpeg/ffprobe are missing, so a caller can
branch on it without parsing JSON.
"""

import json
import sys

from ffmpeg_utils import check_dependencies


def main():
    report = check_dependencies()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ready"] else 1)


if __name__ == "__main__":
    main()
