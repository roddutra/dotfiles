#!/usr/bin/env python3
"""Stop hook: catch leaked text-format tool calls and force a retry.

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
"call", "core" have all been observed (see anthropics/claude-code#67307).

What this hook does
-------------------
Fires on Stop. Reads the tail of the transcript, finds the last main-agent
assistant message, and detects a leaked text-format tool call. If one is found it
forces a retry (see "Blocking mechanism" below) with a corrective instruction so
Claude re-issues the call as a real tool call instead of stalling. A bounded
per-session counter prevents infinite loops, and the last-handled message id is
remembered so the same message can never be counted twice.

Blocking mechanism - EXIT CODE 2, not stdout JSON
-------------------------------------------------
A Stop hook blocks (forces continuation) by exiting 2 with the corrective message
on STDERR. This is what Claude Code's interactive REPL actually honors: its Stop
handler triggers a block ONLY on `exitCode === 2` and feeds stderr (falling back
to stdout) back to the model. The widely-documented `{"decision": "block"}` JSON
on stdout is recognised only by the non-REPL/SDK hook executor - on the REPL Stop
path that JSON is parsed solely for `metrics`/`rewakeSummary`, so a hook that
prints it and exits 0 is silently ignored and the session stalls (observed on
claude-opus-4-8 in anthropics/claude-code#67307). Exit 2 is honoured by BOTH the
REPL and non-REPL executors (`status === 2 || decision === "block"`), so it is
the correct, portable choice. A normal (non-blocking) stop is exit 0.

The leaked-text trigger is the ONLY action this hook takes, and it is provably
safe: leaked `<invoke>` text never executes, so re-issuing it can never cause a
double action. (An earlier draft also acted on a `stop_reason == "tool_use"`
turn that carried no tool_use block - the text-free #64235 variant - but that
state is ambiguous: an aborted/interrupted turn or a teammate handoff can leave
it AFTER the tool already ran. Under an auto-execute setup a retry there could
double-run a side-effecting action, so it was dropped. That variant now simply
stalls and the user re-prompts, which is safe.)

Detection
---------
A real leak always ENDS with `</invoke>` (the leaked call is the last thing
emitted). On top of that we require one of two shapes, so prose/docs that merely
discuss or fence-quote the pattern do not match:
  * WHOLE: the message is essentially just the invoke block (optionally after a
    single lone-sentinel line); or
  * SENTINEL: a lone short token line (the stray sentinel) immediately precedes a
    line-start invoke that runs to the end of the message.
A fenced example ends with a ``` fence (not `</invoke>`), and ordinary prose has
neither shape, so both are excluded.

Scope - model gate
------------------
The glitch is exclusive to claude-opus-4-8 (it never occurred on 4.7). The hook
reads the model off the last assistant message and no-ops on any other model, so
Sonnet/Haiku/Fable and teammate turns are never touched. The match is
case-insensitive and separator-tolerant (so `Claude-Opus-4-8`, `claude-opus-4.8`,
and dated variants like `claude-opus-4-8-20260101` all match). If the transcript
omits the model field, the hook falls through rather than silently disabling
itself - safe to do, since the only action is the provably-safe leak retry.

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
# Shape WHOLE: the whole message is a single invoke block, optionally after one
# lone-sentinel line.
WHOLE_INVOKE_RE = re.compile(
    rf'^\s*(?:{_SENTINEL}[ \t]*\r?\n)?\s*<invoke\s+name="[^"]*".*?</invoke>\s*$',
    re.IGNORECASE | re.DOTALL,
)
# Shape SENTINEL: a lone-sentinel line immediately precedes a line-start invoke
# that runs to the end of the message (the leak may be preceded by ordinary prose
# above the sentinel line).
SENTINEL_INVOKE_RE = re.compile(
    rf'(?:\A|\n)[ \t]*{_SENTINEL}[ \t]*\r?\n[ \t]*<invoke\s+name="[^"]*".*?</invoke>\s*$',
    re.IGNORECASE | re.DOTALL,
)

# Case/separator-insensitive marker for the only affected model.
_MODEL_SEP_RE = re.compile(r"[._]")


def is_opus_4_8(model):
    """True if the model string denotes claude-opus-4-8 (any case/separator/suffix)."""
    if not isinstance(model, str) or not model:
        return False
    return "opus-4-8" in _MODEL_SEP_RE.sub("-", model.lower())


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
    """Return (text, message_id, model) for the last non-sidechain assistant
    message, or None if there isn't one."""
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
                    value = block.get("text")
                    if isinstance(value, str):
                        parts.append(value)
        return "\n".join(parts), msg.get("id"), msg.get("model")
    return None


def is_text_format_leak(text):
    """True if the last assistant turn is a leaked text-format tool call.

    A leak always ends with </invoke> (cheap precheck before the regexes) and
    matches the WHOLE or SENTINEL shape. Prose/docs that merely discuss the
    pattern do not match - a fenced example ends with ``` , not </invoke>.
    """
    if not isinstance(text, str) or not text:
        return False
    stripped = text.strip()
    if not stripped.lower().endswith("</invoke>"):
        return False
    return bool(WHOLE_INVOKE_RE.match(stripped) or SENTINEL_INVOKE_RE.search(stripped))


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

    text, mid, model = result

    # Model gate: the glitch is exclusive to claude-opus-4-8. No-op on any other
    # model so Sonnet/Haiku/Fable and teammate turns are never touched. A missing
    # model field (unexpected format) falls through rather than silently disabling
    # the protection - safe, since the only action is the provably-safe leak retry.
    if isinstance(model, str) and model and not is_opus_4_8(model):
        sys.exit(0)

    if not is_text_format_leak(text):
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

    # Provably safe: leaked <invoke> text never executes, so nothing ran.
    reason = (
        "[malformed-tool-call hook] "
        "Your previous reply was emitted as PLAIN TEXT, not as a real tool call: "
        "an un-wrapped `<invoke name=\"...\">` block (often preceded by a stray "
        "token such as `court`/`count`/`call`). Leaked tool-call text never "
        "executes, so NOTHING ran and no action was taken. This is a known "
        "claude-opus-4-8 serialisation glitch in long sessions. Re-issue the same "
        "call now as a proper native tool call - do not print the `<invoke>` text "
        f"again, actually invoke the tool. (auto-retry {count + 1}/{MAX_RETRIES})"
    )
    # Block via exit code 2 + stderr - the ONLY signal the interactive REPL Stop
    # handler honours (stdout JSON `decision:block` is ignored there). See the
    # "Blocking mechanism" note in the module docstring.
    print(reason, file=sys.stderr)
    sys.exit(2)


def main():
    try:
        run()
    except SystemExit:
        raise  # normal control flow (sys.exit) must propagate
    except Exception:
        sys.exit(0)  # fail safe: never disrupt a normal stop


if __name__ == "__main__":
    main()
