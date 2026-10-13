#!/usr/bin/env python3
"""A stand-in for the `agent-browser` CLI: opens nothing, and appends one JSON line per
invocation to $FAKE_CLI_LOG, {"cli": "agent-browser", "argv": [...], "env": {...}, "cwd": ...},
"env" being the AGENT_BROWSER_* variables it was run with. A call that loads a saved browser
state (`--state <file> ...`) also logs "state": what that file held, parsed, null when it could
not be read.

With $FAKE_PAGE_TEXT set it answers the one question capture.py reads the words of a page from,
`eval document.body.innerText`, with that text, as the real CLI prints a string: JSON-encoded.

With $AGENT_BROWSER_SOCKET_DIR set it keeps a session there as the real CLI does, as far as
browser_session.py goes by it:

    open ...        starts the session's daemon when it has none: a process in a session of its
                    own that listens on <socket dir>/<session>.sock and is recorded in
                    <socket dir>/<session>.pid. It ends on SIGTERM, and on the request to close
                    that the real CLI sends a session, one JSON line {"id", "action": "close"}
                    on that socket, which it answers as the real daemon does: with "success",
                    false while the policy does not allow "close". A request to close is
                    logged, as {"event": "session closed", "session": ...}
    close [--all]   as the real CLI can when a session does not answer: signals the process
                    that the session's pid file names, or with --all every pid file of the
                    directory, whatever process that is by now. browser_session.py never runs it
    any command     is refused with the real CLI's message and exit code 1 when the policy file
                    in $AGENT_BROWSER_ACTION_POLICY denies by default and does not allow it

Steering, by $FAKE_AGENT_BROWSER: no_launch makes `open` fail as when no browser can be started,
and hang makes it start the daemon, log {"event": "open hung", "pid": its own} and never return."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

DAEMON = """
import json, os, signal, socket, sys
path, pid_file, policy, session, log = sys.argv[1:6]


def end(*_):
    for left in (path, pid_file):
        try:
            os.unlink(left)
        except OSError:
            pass
    os._exit(0)


signal.signal(signal.SIGTERM, end)
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(path)
server.listen()
while True:
    conn = server.accept()[0]
    with conn, conn.makefile() as asked:
        try:
            request = json.loads(asked.readline() or "{}")
        except (OSError, ValueError):
            continue
        if request.get("action") != "close":
            continue
        try:
            rules = json.loads(open(policy).read())
        except (OSError, ValueError):
            rules = {}
        allowed = rules.get("default") != "deny" or "close" in rules.get("allow", [])
        if log:
            with open(log, "a") as f:
                f.write(json.dumps({"event": "session closed", "session": session}) + "\\n")
        refusal = {} if allowed else {"error": "Action 'close' denied by policy"}
        conn.sendall((json.dumps({"id": request.get("id"), "success": allowed, **refusal}) + "\\n").encode())
        if allowed:
            end()
"""

ACTIONS = {"open": "navigate", "eval": "evaluate", "set": "viewport"}  # a command's action, where the names differ
SEEN = {k: v for k, v in os.environ.items() if k.startswith("AGENT_BROWSER_")}
args = sys.argv[1:]
if os.environ.get("FAKE_CLI_LOG"):
    loaded = {}
    if args[:1] == ["--state"]:
        try:
            loaded = {"state": json.loads(Path(args[1]).read_text())}
        except (OSError, ValueError):
            loaded = {"state": None}
    with open(os.environ["FAKE_CLI_LOG"], "a") as log:
        log.write(json.dumps({"cli": "agent-browser", "argv": args, "env": SEEN, "cwd": os.getcwd(), **loaded}) + "\n")
if os.environ.get("FAKE_PAGE_TEXT") and args[-2:] == ["eval", "document.body.innerText"]:
    print(json.dumps(os.environ["FAKE_PAGE_TEXT"]))

sockets = os.environ.get("AGENT_BROWSER_SOCKET_DIR")
words = args[2:] if args[:1] == ["--state"] else args  # the one option browser_session.py puts first
if sockets and words:
    command, session = words[0], os.environ.get("AGENT_BROWSER_SESSION", "default")
    pid_file = Path(sockets) / f"{session}.pid"
    try:
        policy = json.loads(Path(os.environ["AGENT_BROWSER_ACTION_POLICY"]).read_text())
    except (KeyError, OSError, ValueError):
        policy = {}
    action = words[1] if command == "get" else ACTIONS.get(command, command)  # `get url` is the action "url"
    if policy.get("default") == "deny" and action not in policy.get("allow", []):
        sys.exit(f"✗ Action '{action}' denied by policy: Action '{action}' is not in the allow list")
    if command == "open" and os.environ.get("FAKE_AGENT_BROWSER") == "no_launch":
        sys.exit("✗ Chrome exited early without writing DevToolsActivePort")
    if command == "open" and not pid_file.exists():
        listening = pid_file.with_suffix(".sock")
        daemon = subprocess.Popen(
            [sys.executable, "-c", DAEMON, str(listening), str(pid_file),
             os.environ.get("AGENT_BROWSER_ACTION_POLICY", ""), session, os.environ.get("FAKE_CLI_LOG", "")],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        pid_file.write_text(str(daemon.pid))
        while not listening.exists() and daemon.poll() is None:  # as the real CLI, back once the session answers
            time.sleep(0.005)
    if command == "open" and os.environ.get("FAKE_AGENT_BROWSER") == "hang":
        with open(os.environ["FAKE_CLI_LOG"], "a") as log:
            log.write(json.dumps({"event": "open hung", "pid": os.getpid()}) + "\n")
        signal.pause()
    if command == "close":
        for recorded in Path(sockets).glob("*.pid") if "--all" in args else [pid_file]:
            try:
                os.kill(int(recorded.read_text()), signal.SIGTERM)
            except (OSError, ValueError):
                pass
