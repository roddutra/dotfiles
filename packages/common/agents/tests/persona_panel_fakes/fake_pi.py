#!/usr/bin/env python3
"""A stand-in for the `pi` CLI. No model, no network.

Answers what the runner uses: `--version`, `--offline -ne --list-models`, `auth check --provider
<name> --json`, and a headless run (`-p --mode text`). A run prints the final reply on stdout,
as the real CLI does in text mode, and keeps a session file under --session-dir made of entries
recorded from the real CLI (pi/*.jsonl): the runner reads its facts from that file. Like the real
CLI it refuses an unknown option, knows --panel-guard only once the extension given with -e has
loaded, refuses to start when that extension cannot be loaded, ends a `--session <id>` that has no
file with its own message, and with nothing on stdin exits 0 without a request.

Steering, through the environment:

    FAKE_PI        ok (default), usage_limit or error: how the run ends
                   hang: get as far as the first tool call, then sleep until killed
                   signed_out: no provider has a login, so no model is listed
                   dead_login: the models are listed, and `auth check` finds the login invalid
                   no_guard: the extension given with -e fails to load
                   no_flag:<option>: the CLI no longer has that option
    FAKE_PANEL     a directory with a plan: the fake then plays whole panellist runs and analyst
                   and writer jobs, writing their files and logging events (see panellist.py)
    FAKE_CLI_LOG   a file that gets one JSON line per invocation: cli, argv, stdin, cwd and
                   model_call (whether the real CLI would have called a model)
"""

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panellist  # noqa: E402

RECORDED = Path(__file__).resolve().parent / "pi"
MODE = os.environ.get("FAKE_PI", "ok")
RUNS = {"ok": ("ok", 0), "usage_limit": ("usage-limit.inferred", 1), "error": ("error", 1), "hang": ("killed", None)}
OPTIONS = {"-p": 0, "--mode": 1, "--session-id": 1, "--session": 1, "--session-dir": 1, "--provider": 1,
           "--model": 1, "--thinking": 1, "-nc": 0, "-ns": 0, "-ne": 0, "-np": 0, "--no-themes": 0, "--no-mcp": 0,
           "--no-approve": 0, "--system-prompt": 1, "--append-system-prompt": 1, "-e": 1, "--panel-guard": 1,
           "--tools": 1}
# Two rows of the real listing, one model that takes images and one that does not, under four
# rows as the real CLI lists the models of a provider added in its models.json. The real CLI
# takes "custom/foo" for "foo" and "bar" for "Bar" or the other way round, so the runner must
# refuse one of each pair.
LISTING = ("provider      model                context  max-out  thinking  images\n"
           "custom        bar                  128K     16.4K    no        no    \n"
           "custom        Bar                  128K     16.4K    no        no    \n"
           "custom        custom/foo           128K     16.4K    no        no    \n"
           "custom        foo                  128K     16.4K    no        no    \n"
           "openai-codex  gpt-5.3-codex-spark  128K     128K     yes       no    \n"
           "openai-codex  gpt-6-luna           272K     128K     yes       yes   \n")
UUID = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def finish(code, out="", err="", stdin=None, model_call=False):
    if os.environ.get("FAKE_CLI_LOG"):
        with open(os.environ["FAKE_CLI_LOG"], "a") as log:
            log.write(json.dumps({"cli": "pi", "argv": sys.argv[1:], "stdin": stdin, "cwd": os.getcwd(),
                                  "model_call": model_call}) + "\n")
    sys.stdout.write(out)
    sys.stderr.write(err)
    sys.stdout.flush()
    if code is None:
        time.sleep(600)
    sys.exit(code)


def auth_check(provider):
    if MODE == "dead_login":
        finish(2, json.dumps({"status": "invalid", "provider": provider, "reason": "invalid_state"}) + "\n")
    if MODE == "signed_out" or provider != "openai-codex":
        finish(1, json.dumps({"status": "not_ready", "provider": provider,
                              "reason": "credentials_not_configured"}) + "\n")
    finish(0, json.dumps({"status": "ready", "provider": provider, "authType": "oauth"}) + "\n")


def options(args):
    found, i = {}, 0
    gone = MODE.partition("no_flag:")[2]
    while i < len(args):
        if args[i] not in OPTIONS or args[i] == gone:
            finish(1, err=f"Error: Unknown option: {args[i]}\n")
        found[args[i]] = args[i + 1:i + 1 + OPTIONS[args[i]]]
        i += 1 + OPTIONS[args[i]]
    guard = (found.get("-e") or [None])[0]
    if "--panel-guard" in found and (guard is None or MODE == "no_guard" or not Path(guard).is_file()):
        finish(1, err="Error: Unknown option: --panel-guard\n" + (
            f'Error: Failed to load extension "{guard}": Failed to load extension: ParseError: Unexpected token\n'
            'Hint: Start without extensions using "pi -ne".\n' if guard else ""))
    return found


def lines(name):
    return [json.loads(line) for line in (RECORDED / f"{name}.jsonl").read_text().splitlines()]


def main():
    args = sys.argv[1:]
    if args == ["--version"]:
        finish(0, "1.1.0\n")
    if args == ["--offline", "-ne", "--list-models"]:
        finish(0, "No models available. Use /login to log into a provider via OAuth or API key.\n"
               if MODE == "signed_out" else LISTING)
    if args[:3] == ["auth", "check", "--provider"] and args[4:] == ["--json"]:
        auth_check(args[3])
    found = options(args)
    if found.get("--mode") != ["text"]:
        finish(1, err="fake pi: only --mode text is played\n")
    resumed = "--session" in found
    session = (found.get("--session") or found.get("--session-id") or [""])[0]
    folder = Path((found.get("--session-dir") or ["."])[0])
    if not UUID.fullmatch(session):
        finish(1, err="Error: Session id must be non-empty, contain only alphanumeric characters, '-', '_', "
                      "and '.', and start and end with an alphanumeric character\n")
    kept = next(iter(sorted(folder.glob(f"*_{session}.jsonl"))), None)
    if resumed and kept is None:
        finish(1, err=f"No session found matching '{session}'\n")
    created = "" if resumed else (f"Warning: No project session found with id '{session}'; creating a new "
                                  "session with that id.\n")
    prompt = sys.stdin.read()
    if not prompt:
        finish(0, err=created, stdin=prompt)
    kept = kept or folder / f"2026-10-12T19-49-16-390Z_{session}.jsonl"
    opened = []

    def append(entries):
        folder.mkdir(parents=True, exist_ok=True)
        with open(kept, "a") as f:
            f.write("".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries))

    def recording(name, reply=None):
        """Add to the session file what the recorded run `name` leaves there, print what it
        prints on stderr, and return what it prints on stdout. The first call also adds the
        start of the run: everything up to its first finished request ("killed" is that alone)."""
        if not opened:
            opened.append(True)
            start = lines("resume" if resumed else "ok")[:-1]
            for entry in start:
                if entry["type"] == "session":
                    entry["id"] = session
                elif entry.get("message", {}).get("role") == "user":
                    entry["message"]["content"][0]["text"] = prompt
            append(start)
            sys.stderr.write(created)
        if name == "killed":
            return ""
        last = lines("resume" if resumed and name == "ok" else name)[-1]
        if name != "ok":
            append([last])
            sys.stderr.write(last["message"]["errorMessage"] + "\n")
            return ""
        if reply is not None:
            last["message"]["content"][0]["text"] = reply
        append([last])
        return last["message"]["content"][0]["text"] + "\n"

    panellist.play("pi", session, resumed, prompt, recording, RUNS, f"No session found matching '{session}'\n")
    name, code = RUNS.get(MODE.split(":")[0], RUNS["ok"])
    finish(code, recording(name), stdin=prompt, model_call=True)


main()
