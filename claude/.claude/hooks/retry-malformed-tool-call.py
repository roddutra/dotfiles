#!/usr/bin/env python3
"""Stop hook: catch malformed text-format tool calls and force a retry.

Background
----------
On long `claude-opus-4-8` sessions, the model intermittently emits a tool call
as PLAIN TEXT instead of a native tool_use content block. The leaked text is a
malformed function-call block: a stray sentinel token on its own line, followed
by an `<invoke name="...">` ... `</invoke>` block with the enclosing
`<function_calls>`/`antml:` wrapper dropped. The API tool-call parser does not
recognise it, returns it as a text content block, nothing executes, and the turn
ends. The session then silently stalls until the user re-prompts.

The stray sentinel token varies between sessions/users: "court", "count",
"call", "core" have all been observed (see anthropics/claude-code#67307). A
sibling regression (#64235) drops the tool_use block ENTIRELY on a
`stop_reason == "tool_use"` turn with no `<invoke>` text leaked at all.

What this hook does
-------------------
Fires on Stop. Reads the tail of the transcript, finds the last main-agent
assistant message, and applies two independent triggers. If either fires it
returns {"decision": "block"} with a corrective instruction so Claude re-issues
the call as a real tool call instead of stalling. A bounded per-session counter
prevents infinite loops, and the last-handled message id is remembered so the
same message can never be counted twice.

Trigger A - text-format leak. A real leak always ENDS with `</invoke>` (the
leaked call is the last thing emitted). On top of that we require one of two
shapes, so prose/docs that merely discuss or fence-quote the pattern do not
match:
  * WHOLE: the message is essentially just the invoke block (optionally after a
    single lone-sentinel line); or
  * SENTINEL: a lone short token line (the stray sentinel) immediately precedes a
    line-start invoke that runs to the end of the message.
A fenced example ends with a ``` fence (not `</invoke>`), and ordinary prose has
neither shape, so both are excluded.

Trigger B - dropped tool_use block. The API reports `stop_reason == "tool_use"`
but the message carries zero `tool_use` content blocks. At Stop time that is a
contradiction (a real tool_use turn would have executed and not stopped), so it
catches the #64235 variant where the call vanishes with no text to match.

Fail-safe
---------
The operational body runs under a broad `except Exception: sys.exit(0)` and all
field accesses are defensive: any internal error exits 0 and never disrupts a
normal stop.
"""

import hashlib
import json
import os
import re
import sys
import tempfile

MAX_RETRIES = 3

# A stray sentinel is a lone short word-like token on its own line
# (court/count/call/core/...). It is the ONLY lead-in allowed before a
# whole-message leak, and the marker for a prose-trailing leak.
_SENTINEL = r"[A-Za-z][\w-]{0,19}"
# Trigger A, shape WHOLE: the whole message is a single invoke block, optionally
# after one lone-sentinel line.
WHOLE_INVOKE_RE = re.compile(
    rf'^\s*(?:{_SENTINEL}[ \t]*\r?\n)?\s*<invoke\s+name="[^"]*".*?</invoke>\s*$',
    re.IGNORECASE | re.DOTALL,
)
# Trigger A, shape SENTINEL: a lone-sentinel line immediately precedes a
# line-start invoke that runs to the end of the message (the leak may be
# preceded by ordinary prose above the sentinel line).
SENTINEL_INVOKE_RE = re.compile(
    rf'(?:\A|\n)[ \t]*{_SENTINEL}[ \t]*\r?\n[ \t]*<invoke\s+name="[^"]*".*?</invoke>\s*$',
    re.IGNORECASE | re.DOTALL,
)


def read_tail(path, max_bytes=1048576):
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


def last_assistant_message(transcript_path):
    """Return (text, stop_reason, block_types, message_id) for the last
    non-sidechain assistant message, or None if there isn't one."""
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
        types = []
        if isinstance(content, str):
            parts.append(content)
            types.append("text")
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                types.append(block.get("type"))
                if block.get("type") == "text":
                    value = block.get("text")
                    if isinstance(value, str):
                        parts.append(value)
        mid = msg.get("id")
        return "\n".join(parts), msg.get("stop_reason"), types, mid
    return None


def is_malformed_tool_call(text, stop_reason, block_types):
    """True if the last assistant turn is a stalled/malformed tool call."""
    # Trigger A: text-format <invoke> leak (any sentinel token, or none). A leak
    # always ends with </invoke> - cheap precheck before the regexes.
    if isinstance(text, str) and text:
        stripped = text.strip()
        if stripped.lower().endswith("</invoke>") and (
            WHOLE_INVOKE_RE.match(stripped) or SENTINEL_INVOKE_RE.search(stripped)
        ):
            return True
    # Trigger B: API said tool_use but no tool_use block was emitted (#64235).
    if stop_reason == "tool_use" and "tool_use" not in (block_types or []):
        return True
    return False


def state_path(session_id):
    safe = hashlib.sha256(str(session_id or "unknown").encode()).hexdigest()[:16]
    return os.path.join(tempfile.gettempdir(), f"cc-tool-call-leak-{safe}.json")


def read_state(path):
    try:
        with open(path) as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def write_state(path, count, mid):
    try:
        with open(path, "w") as fh:
            json.dump({"count": count, "mid": mid}, fh)
    except OSError:
        pass


def clear_state(path):
    try:
        os.remove(path)
    except OSError:
        pass


def run():
    payload = json.load(sys.stdin)
    transcript_path = payload.get("transcript_path")
    session_id = payload.get("session_id", "unknown")
    spath = state_path(session_id)

    if not transcript_path or not os.path.exists(transcript_path):
        sys.exit(0)

    result = last_assistant_message(transcript_path)
    if result is None:
        clear_state(spath)
        sys.exit(0)

    text, stop_reason, block_types, mid = result
    if not is_malformed_tool_call(text, stop_reason, block_types):
        clear_state(spath)  # clean stop, reset the retry budget
        sys.exit(0)

    state = read_state(spath)
    # Never act twice on the exact same assistant message (guards any pathological
    # re-fire on an unchanged message; each genuine retry is a new message id).
    if mid and state.get("mid") == mid:
        sys.exit(0)

    try:
        count = int(state.get("count", 0))
    except (TypeError, ValueError):
        count = 0  # corrupt state must not fail-open and disable retries
    if count >= MAX_RETRIES:
        # Give up rather than loop forever; let the session stop so the user can
        # intervene. Reset so a future occurrence gets a fresh budget.
        clear_state(spath)
        sys.exit(0)

    write_state(spath, count + 1, mid)

    reason = (
        "Your previous response was NOT executed: the tool call did not run, so the "
        "turn stalled. Either it was emitted as plain text (an un-wrapped "
        "`<invoke name=\"...\">` block, often preceded by a stray token such as "
        "`court`/`count`/`call`), or the API reported a tool call but no tool_use "
        "block was actually produced. This is a known claude-opus-4-8 serialisation "
        "glitch in long sessions. Re-issue the EXACT same tool call now as a proper "
        "native tool call. Do not print the `<invoke>` text again; actually invoke "
        f"the tool. (auto-retry {count + 1}/{MAX_RETRIES})"
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def main():
    try:
        run()
    except SystemExit:
        raise  # normal control flow (sys.exit) must propagate
    except Exception:
        sys.exit(0)  # fail safe: never disrupt a normal stop


if __name__ == "__main__":
    main()
