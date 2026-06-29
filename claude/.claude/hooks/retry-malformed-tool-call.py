#!/usr/bin/env python3
"""Stop hook: catch malformed text-format tool calls and force a retry.

Background
----------
On long `claude-opus-4-8` sessions, the model intermittently emits a tool call
as PLAIN TEXT instead of a native tool_use block. The text is a malformed
function-call block: a stray leading token (consistently "court") followed by an
un-wrapped `<invoke name="...">` ... `</invoke>` block with no enclosing
`<function_calls>` wrapper. The API tool-call parser does not recognise it, so it
is returned as a text content block, nothing executes, and the turn ends. The
session then silently stalls until the user re-prompts.

This most often triggers when resuming a long, heavily-cached session from a
background-task completion notification (e.g. the codex-reviewer skill, which
runs reviews with run_in_background: true and reads rN-output.md when notified).

What this hook does
-------------------
Fires on Stop. Reads the tail of the transcript, finds the last main-agent
assistant message, and checks whether its text content is (essentially) just a
leaked `<invoke name="...">` block. If so, it returns {"decision": "block"} with
a corrective instruction so Claude re-issues the call as a real tool call instead
of stalling. A bounded per-session counter prevents infinite loops.

Detection is intentionally conservative: the `<invoke name="` must appear at the
very start of the message (optionally after a single stray token line), so prose
that merely mentions `<invoke>` mid-sentence does not trigger it.
"""

import hashlib
import json
import os
import re
import sys
import tempfile

MAX_RETRIES = 3

# The leaked block always starts the message, optionally after a single stray
# token line (e.g. "court\n"). Anchored at start of string so prose that
# mentions <invoke> mid-text does not match.
LEAK_RE = re.compile(r'^\s*(?:\S+[ \t]*\r?\n)?\s*<invoke\s+name="', re.IGNORECASE)


def read_tail(path, max_bytes=262144):
    """Return the last max_bytes of a file as text (utf-8, lenient)."""
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        start = max(0, size - max_bytes)
        fh.seek(start)
        data = fh.read()
    text = data.decode("utf-8", "replace")
    if start > 0:
        # Drop the (likely partial) first line.
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1:]
    return text


def last_assistant_text(transcript_path):
    """Extract the text content of the last non-sidechain assistant message."""
    try:
        text = read_tail(transcript_path)
    except OSError:
        return None
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("isSidechain") is True:
            continue  # subagent turns are handled by SubagentStop
        msg = obj.get("message")
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        parts = []
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
        return "\n".join(parts)
    return None


def counter_path(session_id):
    safe = hashlib.sha256((session_id or "unknown").encode()).hexdigest()[:16]
    return os.path.join(tempfile.gettempdir(), f"cc-tool-call-leak-{safe}.count")


def read_counter(path):
    try:
        with open(path) as fh:
            return int(fh.read().strip() or "0")
    except (OSError, ValueError):
        return 0


def write_counter(path, value):
    try:
        with open(path, "w") as fh:
            fh.write(str(value))
    except OSError:
        pass


def clear_counter(path):
    try:
        os.remove(path)
    except OSError:
        pass


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, TypeError):
        sys.exit(0)  # never block on our own parse error

    transcript_path = payload.get("transcript_path")
    session_id = payload.get("session_id", "unknown")
    cpath = counter_path(session_id)

    if not transcript_path or not os.path.exists(transcript_path):
        sys.exit(0)

    text = last_assistant_text(transcript_path)
    if text is None or not LEAK_RE.search(text):
        clear_counter(cpath)  # clean stop, reset the retry budget
        sys.exit(0)

    count = read_counter(cpath)
    if count >= MAX_RETRIES:
        # Give up rather than loop forever; let the session stop so the user can
        # intervene. Reset so a future occurrence gets a fresh budget.
        clear_counter(cpath)
        sys.exit(0)

    write_counter(cpath, count + 1)

    reason = (
        "Your previous response was NOT executed: it emitted a tool call as plain "
        "text (an un-wrapped `<invoke name=\"...\">` block, often preceded by a "
        "stray token such as `court`) instead of a real tool_use call, so nothing "
        "ran and the turn stalled. This is a known claude-opus-4-8 serialisation "
        "glitch that occurs when resuming a long session (e.g. after a background "
        "task completes). Re-issue the EXACT same tool call now as a proper native "
        "tool call. Do not print the `<invoke>` text again; actually invoke the "
        f"tool. (auto-retry {count + 1}/{MAX_RETRIES})"
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    main()
