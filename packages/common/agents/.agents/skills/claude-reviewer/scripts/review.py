#!/usr/bin/env python3
"""Claude reviewer entrypoint. Delegates mechanics to the shared agent library."""

import os
import sys
from pathlib import Path

COMMON = Path(__file__).resolve().parents[3] / "lib" / "claude_session.py"

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in {"init", "write", "run", "list", "cleanup"}:
        raise SystemExit("usage: review.py {init,write,run,list,cleanup} [...]")
    action = {"init": "init-review", "write": "write-prompt", "run": "run-review", "list": "list-reviews", "cleanup": "cleanup"}[sys.argv[1]]
    os.execv(sys.executable, [sys.executable, str(COMMON), action, *sys.argv[2:]])
