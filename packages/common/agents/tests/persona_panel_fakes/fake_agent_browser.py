#!/usr/bin/env python3
"""A stand-in for the `agent-browser` CLI: opens nothing, and appends one JSON line per
invocation to $FAKE_CLI_LOG, {"cli": "agent-browser", "argv": [...]}.

With $FAKE_PAGE_TEXT set it answers the one question capture.py reads the words of a page from,
`eval document.body.innerText`, with that text, as the real CLI prints a string: JSON-encoded."""

import json
import os
import sys

if os.environ.get("FAKE_CLI_LOG"):
    with open(os.environ["FAKE_CLI_LOG"], "a") as log:
        log.write(json.dumps({"cli": "agent-browser", "argv": sys.argv[1:]}) + "\n")
if os.environ.get("FAKE_PAGE_TEXT") and sys.argv[-2:] == ["eval", "document.body.innerText"]:
    print(json.dumps(os.environ["FAKE_PAGE_TEXT"]))
