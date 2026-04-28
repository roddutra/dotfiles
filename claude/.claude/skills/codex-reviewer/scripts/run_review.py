#!/usr/bin/env python3
"""Run or resume a Codex review with safety enforcement.

Auto-detects whether this is an initial review or a follow-up based on
session metadata:
- If codex_session_id is null → initial review (`codex exec`), --cd auto-detected from cwd
- If codex_session_id exists → resume (`codex exec resume`)

Reads the current round from session metadata to locate the correct prompt
and output files. The round must have been set by write_prompt.py beforehand.

Safety: This script hardcodes --sandbox read-only. The command is constructed
internally with no mechanism to inject other flags.
"""

import argparse
import codecs
import collections
import json
import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path

from generate_path import generate_paths
from init_session import _resolve_git_root

# Default wall-clock cap for a single Codex turn. 30 minutes is well above
# observed healthy review durations (~5-10 min) while still cheaply capping
# the blast radius of a hung process. Override with --timeout.
_DEFAULT_TIMEOUT = 1800

# Default stderr-silence threshold. If Codex produces no stderr output for
# this many seconds, it's almost certainly stuck — healthy runs emit
# progress frequently. Override with --stall.
_DEFAULT_STALL = 300

# Absolute-path prefixes that commonly appear in prompts and indicate
# files outside the project directory.
_EXTERNAL_PATH_RE = re.compile(
    r"(?:"
    r"/(?:Users|home|tmp|private/tmp|var/folders|opt)/\S+"
    r"|"
    r"~/\S+"
    r")"
)

# Codex CLI persists session rollouts here, partitioned by date:
#   ~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<session_id>.jsonl
_CODEX_SESSIONS_ROOT = Path.home() / ".codex" / "sessions"


def _find_rollout_file(session_id: str) -> Path | None:
    """Locate the Codex rollout JSONL file for a given session id.

    Best-effort: rglob and stat can raise OSError on permission issues
    or races where a file disappears mid-walk. Since this lookup only
    feeds supplemental diagnostics, never let it surface a traceback
    in place of the intended error message.
    """
    if not session_id or not _CODEX_SESSIONS_ROOT.exists():
        return None
    try:
        matches = list(_CODEX_SESSIONS_ROOT.rglob(f"rollout-*-{session_id}.jsonl"))
        if not matches:
            return None
        return max(matches, key=lambda p: p.stat().st_mtime)
    except OSError:
        return None


def _diagnose_rollout(session_id: str) -> dict | None:
    """Diagnose rollout state for a given session.

    Returns a dict describing the detected failure mode, or None if the
    rollout cannot be located or shows no recognizable failure pattern.

    Dict shape:
        status: "silent_failure"    — last `task_complete` event has
                                      `last_agent_message=null` (no
                                      assistant tokens for the turn); the
                                      resume session is dead.
                "network_drop_hang" — rollout ends mid-turn on a
                                      non-terminal event (function_call,
                                      function_call_output, response_item,
                                      etc.) with no subsequent
                                      `task_complete`; the HTTP stream
                                      closed mid-turn.
        message: human-readable diagnostic suitable for inclusion in an
                 error message.
        rollout_file: str path to the rollout file.
        last_event_type: the payload.type of the last meaningful event.
        last_event_timestamp: ISO timestamp of that event, or None.

    Best-effort: swallows OSError and JSONDecodeError so diagnostics never
    surface a traceback in place of the intended error.
    """
    rollout = _find_rollout_file(session_id)
    if rollout is None:
        return None

    last_task_complete: dict | None = None
    last_event_type: str | None = None
    last_event_ts: str | None = None

    try:
        with rollout.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = event.get("payload", {})
                ptype = payload.get("type")
                # Skip incremental token_count pings — they're periodic
                # bookkeeping, not turn-shape events, and would mask the
                # real last terminal/non-terminal event.
                if not ptype or ptype == "token_count":
                    continue
                last_event_type = ptype
                last_event_ts = event.get("timestamp")
                if ptype == "task_complete":
                    last_task_complete = payload
    except OSError:
        return None

    # Classify by the FINAL meaningful event in the rollout. Checking
    # network-drop hang first matters: rollout files span all turns of a
    # session, so a rollout that contains an earlier silent-failed turn
    # followed by a later mid-turn hang must be classified by its current
    # tail (hang), not by the stale earlier `task_complete` payload. The
    # earlier check reversed this precedence and could have written a
    # non-overridable silent-failure marker against a session that was
    # actually salvageable.
    if last_event_type is not None and last_event_type != "task_complete":
        # Rollout ends on a non-terminal event — network-drop hang.
        # Happens when the HTTP stream closes mid-turn and the CLI
        # deadlocks waiting for a terminal event that never arrives.
        return {
            "status": "network_drop_hang",
            "message": (
                f"Codex rollout ends mid-turn on a `{last_event_type}` "
                f"event at {last_event_ts or 'unknown time'} with no "
                f"subsequent `task_complete`. This is the network-drop "
                f"hang signature — the HTTP stream to the model likely "
                f"closed and the CLI deadlocked waiting for a terminal "
                f"event that never arrived."
            ),
            "rollout_file": str(rollout),
            "last_event_type": last_event_type,
            "last_event_timestamp": last_event_ts,
        }

    # Final event IS `task_complete`. Confirmed silent failure only when
    # `last_agent_message` is *present and explicitly null*. Treating a
    # missing key as null would misclassify future Codex event shapes.
    if (
        last_event_type == "task_complete"
        and last_task_complete is not None
        and "last_agent_message" in last_task_complete
        and last_task_complete["last_agent_message"] is None
    ):
        return {
            "status": "silent_failure",
            "message": (
                "Codex rollout confirms the silent-failure signature: the "
                "last `task_complete` event has `last_agent_message=null` "
                "(no assistant tokens were produced for this turn)."
            ),
            "rollout_file": str(rollout),
            "last_event_type": "task_complete",
            "last_event_timestamp": last_event_ts,
        }

    return None


def _warn_external_paths(prompt_file: Path, project_dir: Path) -> None:
    """Emit a warning if the prompt references absolute paths outside --cd.

    This catches the common mistake of telling Codex to read files it cannot
    access (e.g. ~/.claude/plans/, ~/.codex-reviews/, files from other projects).
    The warning is non-blocking — it prints to stderr and returns.
    """
    text = prompt_file.read_text()
    resolved_project = project_dir.resolve()
    external: set[str] = set()
    for m in _EXTERNAL_PATH_RE.finditer(text):
        p = m.group(0).rstrip(".,;:)>]\"'")
        try:
            resolved = Path(p).expanduser().resolve()
        except (OSError, ValueError):
            continue
        if not resolved.is_relative_to(resolved_project):
            external.add(p)
    if external:
        paths_str = "\n".join(f"  - {p}" for p in sorted(external))
        print(
            f"Warning: Prompt references paths outside --cd ({project_dir}):\n"
            f"{paths_str}\n"
            f"Codex cannot read files outside --cd. "
            f"Copy files into .tmp/ within the project.",
            file=sys.stderr,
        )


def run_review(
    session_path: Path,
    project_dir: Path | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    stall: int = _DEFAULT_STALL,
    reasoning_effort: str | None = None,
) -> dict:
    """Run or resume a codex review.

    Args:
        session_path: Path to the session metadata JSON file
        project_dir: Working directory for codex (--cd). Auto-detected
            from cwd if not provided. Ignored for resumes.
        timeout: Wall-clock seconds to wait for Codex. Default 1800
            (30 min). Pass 0 to disable. Exceeding it kills the process
            and exits code 2.
        stall: Seconds of stderr silence that triggers a stall kill.
            Default 300. Pass 0 to disable. Exceeding it kills the
            process and exits code 4 (network-drop hang signature).
        reasoning_effort: Optional reasoning-effort override for this
            run (passed as `-c model_reasoning_effort=<value>`). When
            provided, the value is also persisted into session metadata
            so subsequent rounds inherit it without the caller having
            to re-pass the flag. When omitted, the persisted value (if
            any) is used; otherwise Codex falls back to its locally-
            configured default.

            Model is intentionally NOT overridable here — it is locked
            at session-init time. Changing models mid-session can
            materially change Codex's outputs across rounds; start a
            fresh session to switch models.

    Returns:
        Dict with session_id, prompt_file, output_file, round, and mode
    """
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)

    try:
        metadata = json.loads(session_path.read_text())
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in session file: {session_path}", file=sys.stderr)
        sys.exit(1)
    round_num = metadata.get("current_round", 0)
    session_id = metadata.get("codex_session_id")
    is_resume = bool(session_id and session_id != "--last")

    if round_num == 0:
        print("Error: No prompt written yet. Run write_prompt.py first.", file=sys.stderr)
        sys.exit(1)

    # Resolve project_dir priority: explicit --cd > session metadata > cwd.
    # Explicit --cd wins so callers can correct a bad persisted value.
    if project_dir:
        project_dir = _resolve_git_root(project_dir)
    elif metadata.get("project_dir"):
        project_dir = Path(metadata["project_dir"])
    else:
        project_dir = _resolve_git_root(Path.cwd())

    # Backfill project_dir for older sessions that predate the field.
    # Persist immediately because the resume path depends on a valid
    # value and reads metadata back from disk on subsequent invocations.
    if "project_dir" not in metadata:
        metadata["project_dir"] = str(project_dir.resolve())
        session_path.write_text(json.dumps(metadata, indent=2))

    # Model is read-only here — locked at init_session.py time. Missing
    # key (old sessions) means "no override", same as a None value.
    session_model = metadata.get("model")

    # Reasoning-effort: caller's value (if any) overrides for this run.
    # Otherwise fall back to whatever the session has persisted.
    # We deliberately do NOT persist the override here — see the deferred
    # write at the success path below.
    if reasoning_effort is not None:
        session_reasoning_effort = reasoning_effort
    else:
        session_reasoning_effort = metadata.get("reasoning_effort")

    paths = generate_paths(session_path, round_num)
    prompt_file = Path(paths["prompt_path"])
    output_file = Path(paths["output_path"])

    if not prompt_file.exists():
        print(f"Error: Prompt file not found: {prompt_file}", file=sys.stderr)
        sys.exit(1)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Pre-flight: warn if the prompt references file paths outside --cd.
    # Codex cannot read these, so the review will be based on assumptions.
    if project_dir:
        _warn_external_paths(prompt_file, project_dir)

    # Optional model / reasoning-effort overrides resolved from session
    # metadata above. When neither is set, Codex falls back to whatever
    # the local CLI is configured with (typically ~/.codex/config.toml).
    # Flags must come before the `resume` subcommand on resume
    # invocations.
    override_flags: list[str] = []
    if session_model:
        override_flags += ["--model", session_model]
    if session_reasoning_effort:
        override_flags += ["-c", f"model_reasoning_effort={session_reasoning_effort}"]

    if is_resume:
        cmd = [
            "codex", "exec",
            "--sandbox", "read-only",
            *override_flags,
            "-o", str(output_file),
            "resume", session_id,
            "-",
        ]
    else:
        cmd = [
            "codex", "exec",
            "--sandbox", "read-only",
            *override_flags,
            "--cd", str(project_dir),
            "-o", str(output_file),
            "-",
        ]

    # Open stderr as a raw byte pipe so we can drive it with nonblocking
    # os.read. Text-mode readline() on a pipe can block indefinitely on
    # a partial line (select sees bytes, readline waits for a newline that
    # never arrives), which would defeat the stall watchdog entirely.
    with open(prompt_file) as stdin_file:
        process = subprocess.Popen(
            cmd,
            stdin=stdin_file,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    stderr_fd = process.stderr.fileno()
    try:
        os.set_blocking(stderr_fd, False)
    except OSError as exc:
        # The whole watchdog design relies on nonblocking stderr — without
        # it, the inner read loop in `_read_available` could block on the
        # second iteration (no `select` between iterations) and defeat the
        # stall timer entirely. Fail loudly rather than silently downgrade.
        process.kill()
        process.wait()
        print(
            f"Error: failed to set stderr pipe to nonblocking mode: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Watchdog loop: poll stderr with a 0.5s tick so we can check both
    # the wall-clock deadline and the stderr-stall threshold between
    # reads. The previous design used SIGALRM, which only covered
    # wall-clock timeout — the network-drop hang mode (HTTP stream drops
    # mid-turn, tokio runtime deadlocks) can keep Codex "alive" with zero
    # stderr for hours. The stall watchdog catches that case explicitly.
    timed_out = False
    stalled = False
    captured_session_id = session_id
    stderr_lines: collections.deque[str] = collections.deque(maxlen=30)
    last_activity = time.monotonic()
    deadline = time.monotonic() + timeout if timeout > 0 else None
    stderr_open = True
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    line_buffer = ""

    def _capture_session_id(line: str) -> None:
        nonlocal captured_session_id
        if not is_resume and captured_session_id is None:
            match = re.search(r"session id:\s*(\S+)", line)
            if match:
                captured_session_id = match.group(1)
                metadata["codex_session_id"] = captured_session_id
                session_path.write_text(json.dumps(metadata, indent=2))

    def _drain_chunk(chunk: bytes, final: bool = False) -> None:
        """Feed a raw byte chunk through the UTF-8 decoder and emit any
        complete lines to stderr_lines. On final=True, also flush any
        trailing partial line (e.g. because the process exited mid-line).
        """
        nonlocal line_buffer
        line_buffer += decoder.decode(chunk, final=final)
        while True:
            nl = line_buffer.find("\n")
            if nl < 0:
                break
            line = line_buffer[: nl + 1]
            line_buffer = line_buffer[nl + 1 :]
            stderr_lines.append(line)
            _capture_session_id(line)
        if final and line_buffer:
            stderr_lines.append(line_buffer)
            _capture_session_id(line_buffer)
            line_buffer = ""

    def _read_available() -> bool:
        """Read whatever bytes are currently available on stderr without
        blocking. Returns True if ANY bytes were read (so callers can
        treat that as stderr activity). Sets stderr_open=False on EOF.
        Does NOT flush the decoder on EOF — the single flush point lives
        after the main watchdog loop so every exit path is handled
        uniformly and we never call decoder.decode(final=True) twice.
        """
        nonlocal stderr_open
        got_bytes = False
        # Drain up to a bounded number of chunks per tick so a chatty
        # Codex can't starve the watchdog loop.
        for _ in range(16):
            try:
                chunk = os.read(stderr_fd, 65536)
            except BlockingIOError:
                break
            except OSError:
                stderr_open = False
                break
            if not chunk:
                stderr_open = False
                break
            got_bytes = True
            _drain_chunk(chunk)
        return got_bytes

    while True:
        # Check process exit first. If Codex finished, drain any
        # remaining stderr nonblockingly (no blocking .read() — a
        # stray child process inheriting the pipe could otherwise keep
        # us hanging indefinitely after the watchdog loop has exited).
        if process.poll() is not None:
            if stderr_open:
                _read_available()
            break

        now = time.monotonic()
        if deadline is not None and now > deadline:
            timed_out = True
            process.kill()
            break
        if stall > 0 and now - last_activity > stall:
            stalled = True
            process.kill()
            break

        if stderr_open:
            ready, _, _ = select.select([process.stderr], [], [], 0.5)
            if ready:
                if _read_available():
                    last_activity = time.monotonic()
        else:
            time.sleep(0.5)

    process.wait()

    # Final nonblocking drain + decoder flush — covers the timeout/stall
    # kill paths (which break out of the main loop before the
    # poll()-triggered drain runs) and also any bytes that landed between
    # the last read and process exit. Without this, a partial stderr line
    # or partial session-id banner sitting in line_buffer would be dropped
    # from the error report.
    if stderr_open:
        _read_available()
    _drain_chunk(b"", final=True)

    # Failure classification order:
    #   timed_out → exit 2 (wall-clock deadline hit; Codex killed)
    #   stalled   → exit 4 (stderr silent too long; network-drop hang)
    #   returncode != 0 → exit 1 (genuine CLI error)
    #   clean exit + no/empty output → exit 3 (silent failure — confirmed
    #                                           or unconfirmed)
    stderr_tail = "".join(stderr_lines).strip()
    diag_id = captured_session_id or session_id

    if timed_out:
        diagnosis = _diagnose_rollout(diag_id) if diag_id else None
        msg = (
            f"Error: Codex review timed out after {timeout}s (process killed).\n\n"
            f"What to try next:\n"
            f"  - Re-run `run_review.py` with the same --session. The "
            f"round {round_num} prompt file is still on disk — do NOT call "
            f"`write_prompt.py` again; the prompt and round number are "
            f"already set.\n"
            f"  - If timeouts keep happening on this session, the review "
            f"scope may be too large. Consider splitting the work into "
            f"smaller follow-up rounds, or starting a fresh session with a "
            f"tighter scope (see SKILL.md).\n"
            f"  - Pass a longer `--timeout` if the review is legitimately "
            f"slow (current: {timeout}s). Pass `--timeout 0` to disable."
        )
        if captured_session_id:
            msg += f"\n\nSession ID for resume: {captured_session_id}"
        else:
            msg += (
                "\n\nNo session ID was captured — the next run will start "
                "fresh instead of resuming."
            )
        if diagnosis:
            msg += f"\n\nRollout diagnostic: {diagnosis['message']}"
        if stderr_tail:
            msg += f"\n\nLast stderr output:\n{stderr_tail}"
        print(msg, file=sys.stderr)
        sys.exit(2)

    if stalled:
        diagnosis = _diagnose_rollout(diag_id) if diag_id else None
        msg = (
            f"Error: Codex process went silent — no stderr activity for "
            f"{stall}s (process killed).\n\n"
            f"This is almost certainly the network-drop hang mode: the "
            f"HTTP stream to the model closed mid-turn and the CLI "
            f"deadlocked waiting for a terminal event that never arrived."
        )
        if diagnosis:
            msg += (
                f"\n\nRollout diagnostic: {diagnosis['message']}"
                f"\nRollout file: {diagnosis['rollout_file']}"
            )
        msg += (
            f"\n\nWhat to try next:\n"
            f"  - Re-run `run_review.py` with the same --session. The "
            f"round {round_num} prompt file is still on disk — do NOT call "
            f"`write_prompt.py` again. The resume session should still be "
            f"valid.\n"
            f"  - If stalls keep happening, check network stability or "
            f"start a fresh session (see SKILL.md).\n"
            f"  - Pass `--stall 0` to disable stall detection if Codex is "
            f"legitimately silent for long periods (uncommon — healthy "
            f"runs emit progress frequently)."
        )
        if captured_session_id:
            msg += f"\n\nSession ID for resume: {captured_session_id}"
        if stderr_tail:
            msg += f"\n\nLast stderr output:\n{stderr_tail}"
        print(msg, file=sys.stderr)
        sys.exit(4)

    if process.returncode != 0:
        msg = f"Error: Codex exited with code {process.returncode}"
        if output_file.exists():
            size = output_file.stat().st_size
            if size == 0:
                msg += " (output file is empty)"
            else:
                msg += f" (partial output written, {size} bytes — inspect: {output_file})"
        else:
            msg += " (no output file written)"
        if stderr_tail:
            msg += f"\n\nCodex stderr:\n{stderr_tail}"
        else:
            msg += " (no stderr output captured)"
        msg += (
            f"\n\nWhat to try next:\n"
            f"  - Inspect the stderr above to identify the cause.\n"
            f"  - Re-run `run_review.py` with the same --session if the "
            f"error looks transient (network, rate limit, etc.)."
        )
        if captured_session_id:
            msg += f"\n\nSession ID for resume: {captured_session_id}"
        print(msg, file=sys.stderr)
        sys.exit(1)

    # process.returncode == 0 below.
    output_missing = not output_file.exists()
    output_empty = output_file.exists() and output_file.stat().st_size == 0
    if output_missing or output_empty:
        diagnosis = _diagnose_rollout(diag_id) if diag_id else None

        msg = (
            "Error: Codex exited cleanly but produced no review content "
            f"({'output file missing' if output_missing else 'output file is empty'})."
        )

        if diagnosis and diagnosis["status"] == "silent_failure":
            # Confirmed silent failure. Session is dead. Write marker so
            # write_prompt.py blocks any further round on this session
            # (including --force overrides).
            msg += (
                "\n\nThis is the confirmed Codex silent-failure mode — the "
                "model emitted a `task_complete` event with no assistant "
                "tokens. The resume session is dead.\n\n"
                f"{diagnosis['message']}\n"
                f"Rollout file: {diagnosis['rollout_file']}\n\n"
                "What to try next:\n"
                "  - Do NOT retry with resume or `--force` — the session "
                "is dead and will keep producing empty output.\n"
                "  - Start a fresh session via `init_session.py` and carry "
                "context forward by copying prior artifacts into `.tmp/` "
                "(see SKILL.md → 'Silent Failures (Empty Output)')."
            )
            # Atomic marker write via temp file + replace, so a mid-write
            # failure cannot corrupt session.json.
            try:
                metadata["last_round_silent_failure"] = round_num
                tmp_path = session_path.parent / f"{session_path.name}.tmp"
                tmp_path.write_text(json.dumps(metadata, indent=2))
                tmp_path.replace(session_path)
            except OSError:
                pass
        elif diagnosis and diagnosis["status"] == "network_drop_hang":
            # Rollout ends mid-turn on a non-terminal event. Codex exited
            # cleanly (likely the process got reaped after the TCP stream
            # closed) but produced no output. Resume should still work —
            # the session state is consistent, just incomplete for this
            # turn. No marker: leave --force retry open.
            msg += (
                "\n\nThe rollout shows the network-drop hang signature "
                "(HTTP stream closed mid-turn). Codex exited cleanly but "
                "emitted no assistant tokens for this turn.\n\n"
                f"{diagnosis['message']}\n"
                f"Rollout file: {diagnosis['rollout_file']}\n\n"
                "What to try next:\n"
                "  - Re-run `run_review.py` with the same --session. The "
                "resume session should still be valid.\n"
                "  - If the next attempt also hangs, start a fresh session "
                "(see SKILL.md)."
            )
        else:
            # Unknown state — the rollout file is missing, archived, or
            # ends on a `task_complete` with non-null last_agent_message
            # (which shouldn't happen alongside an empty output file, so
            # something upstream is unusual). Could also be a transient
            # sandbox or permissions issue. Don't overstate certainty;
            # leave the --force retry path open.
            msg += (
                "\n\nThe rollout signature could not be confirmed (the "
                "rollout file is missing, archived, or does not contain a "
                "recognizable failure pattern). The empty output may be a "
                "transient issue such as a sandbox or permissions error.\n\n"
                "What to try next (in order):\n"
                "  1. Re-run `run_review.py` with the same --session "
                f"first — the round {round_num} prompt file is still on "
                "disk, and a transient failure may just retry cleanly. "
                "If the session is actually dead, the next attempt will "
                "exit 3 again (hopefully with a confirmed diagnosis this "
                "time, which will write the marker and stop further "
                "retries).\n"
                "  2. Only if step 1 also fails with no new info, advance "
                "to the next round by piping a fresh prompt to "
                "`write_prompt.py --force`. IMPORTANT: this increments "
                f"`current_round` from {round_num} to {round_num + 1}; "
                "it does NOT retry the current prompt. Use this path only "
                "to move past a persistently broken round.\n"
                "  3. If you can verify the rollout signature manually, "
                "follow the fresh-session recovery in SKILL.md → 'Silent "
                "Failures (Empty Output)'."
            )

        if captured_session_id:
            msg += f"\n\nSession ID: {captured_session_id}"
        if stderr_tail:
            msg += f"\n\nCodex stderr (last lines):\n{stderr_tail}"

        print(msg, file=sys.stderr)
        sys.exit(3)

    # Deferred persistence: only now do we know Codex accepted the
    # `--reasoning-effort` value (clean exit + non-empty output). Writing
    # eagerly would make a typo or invalid value sticky for future
    # rounds. _capture_session_id may have written metadata mid-run, so
    # the in-memory dict is already current — just patch the one field
    # and rewrite.
    if (
        reasoning_effort is not None
        and metadata.get("reasoning_effort") != reasoning_effort
    ):
        metadata["reasoning_effort"] = reasoning_effort
        session_path.write_text(json.dumps(metadata, indent=2))

    return {
        "session_id": captured_session_id,
        "prompt_file": str(prompt_file),
        "output_file": str(output_file),
        "round": round_num,
        "mode": "resume" if is_resume else "initial",
    }


def _non_negative_int(value: str) -> int:
    """argparse type: accept only integers >= 0. Matches the documented
    disable semantics (`0` disables a watchdog) and rejects `-1` etc.
    which would otherwise silently behave like disable.
    """
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected a non-negative integer, got {value!r}"
        ) from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(
            f"expected a non-negative integer, got {parsed}"
        )
    return parsed


def main():
    parser = argparse.ArgumentParser(description="Run or resume a Codex review (read-only)")
    parser.add_argument("--session", required=True, help="Path to session metadata JSON file")
    parser.add_argument("--cd", default=None, help="Project directory override (default: auto-detect git root from cwd)")
    parser.add_argument(
        "--timeout", type=_non_negative_int, default=_DEFAULT_TIMEOUT,
        help=(
            f"Max wall-clock seconds for Codex. Default {_DEFAULT_TIMEOUT} "
            f"({_DEFAULT_TIMEOUT // 60} min). Pass 0 to disable. Exceeding "
            f"it kills the process and exits code 2."
        ),
    )
    parser.add_argument(
        "--stall", type=_non_negative_int, default=_DEFAULT_STALL,
        help=(
            f"Seconds of stderr silence that triggers a stall kill. "
            f"Default {_DEFAULT_STALL} ({_DEFAULT_STALL // 60} min). Pass "
            f"0 to disable. Exceeding it kills the process and exits "
            f"code 4 (network-drop hang signature)."
        ),
    )
    parser.add_argument(
        "--reasoning-effort", default=None,
        help=(
            "Optional reasoning-effort override for this run (e.g. low, "
            "medium, high). When provided, the value is also persisted "
            "into session metadata so subsequent rounds inherit it. When "
            "omitted, the persisted value (set by init_session.py or a "
            "prior run) is used; if none, Codex falls back to its "
            "locally-configured default. Model is intentionally NOT "
            "overridable here — it is locked at session-init time."
        ),
    )
    args = parser.parse_args()

    result = run_review(
        session_path=Path(args.session),
        project_dir=Path(args.cd) if args.cd else None,
        timeout=args.timeout,
        stall=args.stall,
        reasoning_effort=args.reasoning_effort,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
