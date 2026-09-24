#!/usr/bin/env python3
"""Codex model listing entrypoint. Delegates to the shared agent library."""

import os
import sys
from pathlib import Path

COMMON = Path(__file__).resolve().parents[3] / "lib" / "codex_models.py"

if __name__ == "__main__":
    os.execv(sys.executable, [sys.executable, str(COMMON), *sys.argv[1:]])
