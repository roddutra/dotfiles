#!/usr/bin/env python3
"""A stand-in for the `claude` CLI. No model, no network.

Answers what the runner uses: `--version`, `auth status [--text]`, and a headless run (`-p`),
for which it prints output recorded from the real CLI (claude/*.jsonl) under the session id it
was given. Like the real CLI it refuses an unknown option before anything else, stream-json
without --verbose, a session id that is not a UUID, and a run with no prompt on stdin.

Steering, through the environment:

    FAKE_CLAUDE    ok (default), usage_limit, budget or error: the recorded run to print
                   hang: print a run cut off part-way, then sleep until killed
                   signed_out: `auth status` reports no login, and a run ends as "error"
                   no_flag:<option>: the CLI no longer has that option
                   lockout: answers the runner's check, then loses its execute permission, as
                   when a sandbox refuses to start it
    FAKE_PANEL     a directory with a plan: the fake then plays whole panellist runs and analyst
                   and writer jobs, writing their files and logging events (see panellist.py)
    FAKE_CLI_LOG   a file that gets one JSON line per invocation: cli, argv, stdin, cwd, the
                   CLAUDE*, ANTHROPIC* and AI_AGENT variables it saw, and model_call (whether
                   the real CLI would have called a model)
"""

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panellist  # noqa: E402

RECORDED = Path(__file__).resolve().parent / "claude"
MODE = os.environ.get("FAKE_CLAUDE", "ok")
RUNS = {"ok": ("ok", 0), "usage_limit": ("usage-limit.inferred", 1), "budget": ("budget", 1),
        "error": ("error", 1), "signed_out": ("error", 1), "hang": ("killed", None)}
OPTIONS = {"-p": 0, "--session-id": 1, "--resume": 1, "--model": 1, "--effort": 1, "--max-budget-usd": 1,
           "--safe-mode": 0, "--restricted": 0, "--strict-mcp-config": 0, "--disable-slash-commands": 0,
           "--settings": 1, "--tools": 1, "--allowed-tools": 1, "--permission-mode": 1,
           "--output-format": 1, "--verbose": 0}
REPLY = "Reviewed 3 concepts. Ranking: B, A, C."  # the final reply in claude/ok.jsonl
UUID = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def finish(code, out="", err="", stdin=None, model_call=False):
    if os.environ.get("FAKE_CLI_LOG"):
        seen = {k: v for k, v in os.environ.items() if k.startswith(("CLAUDE", "ANTHROPIC", "AI_AGENT"))}
        with open(os.environ["FAKE_CLI_LOG"], "a") as log:
            log.write(json.dumps({"cli": "claude", "argv": sys.argv[1:], "stdin": stdin, "cwd": os.getcwd(),
                                  "env": seen, "model_call": model_call}) + "\n")
    sys.stdout.write(out)
    sys.stderr.write(err)
    sys.stdout.flush()
    if code is None:
        time.sleep(600)
    sys.exit(code)


def auth_status(text):
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    status = {"loggedIn": MODE != "signed_out", "authMethod": "claude.ai", "apiProvider": "firstParty",
              "projectsDirectory": f"{home}/projects", "configDirectory": home}
    if MODE == "signed_out":
        status["authMethod"] = "none"
        finish(1, "Not logged in. Run claude auth login to authenticate.\n" if text else json.dumps(status) + "\n")
    status.update(email="panellist@example.com", orgName="Example", subscriptionType="max")
    finish(0, "Login method: Claude Max account\nEmail: panellist@example.com\n" if text
           else json.dumps(status, indent=2) + "\n")


def options(args):
    found, i = {}, 0
    gone = MODE.partition("no_flag:")[2]
    while i < len(args):
        if args[i] not in OPTIONS or args[i] == gone:
            finish(1, err=f"error: unknown option '{args[i]}'\n")
        found[args[i]] = args[i + 1:i + 1 + OPTIONS[args[i]]]
        i += 1 + OPTIONS[args[i]]
    return found


def main():
    args = sys.argv[1:]
    if args == ["--version"]:
        finish(0, "2.1.296 (Claude Code)\n")
    if args[:2] == ["auth", "status"]:
        auth_status("--text" in args)
    found = options(args)
    if found.get("--output-format") == ["stream-json"] and "--verbose" not in found:
        finish(1, err="Error: When using --print, --output-format=stream-json requires --verbose\n")
    session = (found.get("--session-id") or found.get("--resume") or [""])[0]
    if not UUID.fullmatch(session):
        finish(1, err="Error: Invalid session ID. Must be a valid UUID.\n")
    prompt = sys.stdin.read()
    if not prompt:
        if MODE == "lockout":
            os.chmod(shutil.which("claude"), 0o644)
        finish(1, err="Error: Input must be provided either through stdin or as a prompt argument "
                      "when using --print\n", stdin=prompt)

    def recording(name):
        out = (RECORDED / f"{name}.jsonl").read_text()
        return out.replace(json.loads(out.splitlines()[0])["session_id"], session)

    panellist.play("claude", session, "--resume" in found, prompt, recording, RUNS, REPLY,
                   f"No conversation found with session ID: {session}\n")
    name, code = RUNS.get(MODE.split(":")[0], RUNS["ok"])
    finish(code, recording(name), stdin=prompt, model_call=True)


main()
