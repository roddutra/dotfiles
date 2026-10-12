#!/usr/bin/env python3
"""A stand-in for the `codex` CLI. No model, no network.

Answers what the runner uses: `--version`, `login status`, `delete --force <thread id>` (which
deletes nothing: the log line is the trace), and `codex exec`, for which it prints output
recorded from the real CLI (codex/*.jsonl) under a new thread id, or under the one given after
`resume`. Like the real CLI it refuses an unknown option, refuses -C and -s
after the word `resume`, prints help and stops when the options end in --help, and refuses an
empty prompt on stdin.

Steering, through the environment:

    FAKE_CODEX     ok (default), usage_limit, budget or error: the recorded run to print
                   hang: print a run cut off part-way, then sleep until killed
                   signed_out: `login status` reports no login
                   warns: `login status` prints a warning before its answer, as the real CLI
                   does where it cannot write to its own folders
                   no_flag:<option>: the CLI no longer has that option
                   sandboxed: answers the runner's check, then every `codex exec` ends at once
                   with exit code 1, nothing on stdout and the real CLI's message on stderr,
                   as it does where it cannot write to its own folders
    FAKE_PANEL     a directory with a plan: the fake then plays whole panellist runs and analyst
                   and writer jobs, writing their files and logging events (see panellist.py)
    FAKE_CLI_LOG   a file that gets one JSON line per invocation: cli, argv, stdin, cwd and
                   model_call (whether the real CLI would have called a model)
"""

import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panellist  # noqa: E402

RECORDED = Path(__file__).resolve().parent / "codex"
MODE = os.environ.get("FAKE_CODEX", "ok")
RUNS = {"ok": ("ok", 0), "usage_limit": ("usage-limit.inferred", 1), "budget": ("budget", 1),
        "error": ("error", 1), "hang": ("killed", None)}
OPTIONS = {"--json": 0, "--skip-git-repo-check": 0, "--ignore-user-config": 0, "--ignore-rules": 0,
           "-c": 1, "--disable": 1, "-s": 1, "-C": 1, "-m": 1}
REPLY = "codename=NONE; skills=0; agents=yes"  # the final reply in codex/ok.jsonl
EXEC_ONLY = ("-C", "-s")  # rejected once `resume` has been read


def finish(code, out="", err="", stdin=None, model_call=False):
    if os.environ.get("FAKE_CLI_LOG"):
        with open(os.environ["FAKE_CLI_LOG"], "a") as log:
            log.write(json.dumps({"cli": "codex", "argv": sys.argv[1:], "stdin": stdin, "cwd": os.getcwd(),
                                  "model_call": model_call}) + "\n")
    sys.stdout.write(out)
    sys.stderr.write(err)
    sys.stdout.flush()
    if code is None:
        time.sleep(600)
    sys.exit(code)


def exec_args(args):
    """The thread id to resume (None for a new run), after checking every option."""
    words, i, resumed = [], 0, False
    gone = MODE.partition("no_flag:")[2]
    while i < len(args):
        arg = args[i]
        if arg == "--help":
            finish(0, "Run Codex non-interactively\n\nUsage: codex exec [OPTIONS] [PROMPT]\n")
        if arg.startswith("-") and arg != "-":
            if arg not in OPTIONS or arg == gone or (resumed and arg in EXEC_ONLY):
                finish(2, err=f"error: unexpected argument '{arg}' found\n\nUsage: codex exec [OPTIONS] [PROMPT]\n\n"
                              "For more information, try '--help'.\n")
            i += OPTIONS[arg]
        else:
            words.append(arg)
            resumed = resumed or arg == "resume"
        i += 1
    return words[1] if words[:1] == ["resume"] else None


def main():
    args = sys.argv[1:]
    if args == ["--version"]:
        finish(0, "codex-cli 0.162.1\n")
    if args == ["login", "status"]:
        warning = ("WARNING: proceeding, even though we could not create PATH aliases: Read-only file system "
                   "(os error 30)\n" if MODE == "warns" else "")
        finish(*((1, "", "Not logged in\n") if MODE == "signed_out" else (0, "", warning + "Logged in using ChatGPT\n")))
    if args[:2] == ["delete", "--force"] and len(args) == 3:
        finish(0, f"Deleted session {args[2]}\n")
    if args[:1] != ["exec"]:
        finish(2, err=f"error: unrecognized subcommand '{' '.join(args[:1])}'\n")
    resumed = exec_args(args[1:])
    if MODE == "sandboxed":
        finish(1, err="Error: failed to initialize in-process app-server client: Read-only file system "
                      "(os error 30)\n")
    thread = resumed or str(uuid.uuid4())
    prompt = sys.stdin.read()
    if not prompt:
        finish(1, err="No prompt provided via stdin.\n", stdin=prompt)

    def recording(name, reply=None):
        out = (RECORDED / f"{name}.jsonl").read_text()
        if reply is not None:
            out = out.replace(json.dumps(REPLY)[1:-1], json.dumps(reply)[1:-1])
        return out.replace(json.loads(out.splitlines()[0])["thread_id"], thread)

    panellist.play("codex", thread, bool(resumed), prompt, recording, RUNS,
                   f"Error: thread/resume: thread/resume failed: no rollout found for thread id {thread} "
                   "(code -32600)\n")
    name, code = RUNS.get(MODE.split(":")[0], RUNS["ok"])
    finish(code, recording(name), stdin=prompt, model_call=True)


main()
