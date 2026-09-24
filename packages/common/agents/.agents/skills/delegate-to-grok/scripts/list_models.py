#!/usr/bin/env python3
"""Grok model listing entrypoint. Delegates to the shared agent library."""

import os
import sys
from pathlib import Path

COMMON = Path(__file__).resolve().parents[3] / "lib" / "grok_models.py"

if __name__ == "__main__":
    os.execv(sys.executable, [sys.executable, str(COMMON), *sys.argv[1:]])
