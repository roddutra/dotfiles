#!/usr/bin/env python3
"""A stand-in for the `agent-browser` CLI: opens nothing, and appends one JSON line per
invocation to $FAKE_CLI_LOG, {"cli": "agent-browser", "argv": [...]}."""

import json
import os
import sys

if os.environ.get("FAKE_CLI_LOG"):
    with open(os.environ["FAKE_CLI_LOG"], "a") as log:
        log.write(json.dumps({"cli": "agent-browser", "argv": sys.argv[1:]}) + "\n")
