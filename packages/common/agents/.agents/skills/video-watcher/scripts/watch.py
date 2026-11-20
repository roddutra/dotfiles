#!/usr/bin/env python3
"""Send a video and a prompt to a model with native video input.

The model receives the real video (frames and audio), not extracted stills.
The answer is written to a file in the session directory; stdout carries one
JSON object describing the call. Progress goes to stderr.

Exit codes: 0 answered, 2 configuration missing or invalid, 3 preflight
refused the request (nothing was sent to the model), 4 the provider failed,
1 anything else.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import settings
from media import Video, format_timestamp, load_remote_files, parse_timestamp, remote_key, save_remote_files
from providers import PreflightError, ProviderError, make_adapter
from session_paths import new_subdir, record_call, resolve_session

# Held back from the model's input window for its answer when no explicit
# --max-output-tokens is given.
DEFAULT_ANSWER_RESERVE = 16000
# Rough text density for budgeting prompt and context files.
CHARS_PER_TOKEN = 4


def log(message: str) -> None:
    print(f"[video-watcher] {message}", file=sys.stderr, flush=True)


def emit(payload: dict, code: int = 0) -> None:
    print(json.dumps(payload, indent=2))
    sys.exit(code)


def fail(code: str, message: str, exit_code: int, **extra) -> None:
    emit({"ok": False, "error": {"code": code, "message": message, **extra}}, exit_code)


def read_text_file(path_text: str, what: str) -> tuple[Path, str]:
    path = Path(path_text).expanduser()
    try:
        return path, path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        fail("unreadable_file", f"Could not read {what} {path}: {exc}", 1)


def build_texts(prompt: str, context: list[tuple[Path, str]], window: tuple | None) -> list[str]:
    """Text parts in sending order: context files, then the prompt last."""
    texts = [
        f"Context file: {path.name}\n\n{body}" for path, body in context
    ]
    if window:
        start, end = window
        span = f"from {format_timestamp(start or 0)}" + (f" to {format_timestamp(end)}" if end is not None else "")
        prompt = (
            f"{prompt}\n\nYou are seeing only part of the recording: {span}. "
            "Give timestamps as they would read on the full recording's clock."
        )
    texts.append(prompt)
    return texts


def main():
    parser = argparse.ArgumentParser(description="Ask a video-native model about a video file")
    parser.add_argument("--video", required=True, help="Path to the video file")
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="The question or instruction")
    prompt_group.add_argument("--prompt-file", help="File holding the prompt")
    parser.add_argument("--context-file", action="append", default=[],
                        help="Text file sent with the video, such as a transcript (repeatable)")
    parser.add_argument("--session", help="Existing session.json to add this call to")
    parser.add_argument("--title", help="Title for a new session (default: the video's file name)")
    parser.add_argument("--project", help="Project bucket for a new session (default: derived from git)")
    parser.add_argument("--label", help="Name for this call's folder (default: the video's file name)")
    parser.add_argument("--provider", help="Override VIDEO_WATCHER_PROVIDER")
    parser.add_argument("--model", help="Override VIDEO_WATCHER_MODEL")
    parser.add_argument("--base-url", help="Override VIDEO_WATCHER_BASE_URL")
    parser.add_argument("--start", help="Window start: seconds or [HH:]MM:SS")
    parser.add_argument("--end", help="Window end: seconds or [HH:]MM:SS")
    parser.add_argument("--fps", type=float, help="Frames sampled per second (provider default: 1)")
    parser.add_argument("--resolution", choices=("low", "medium", "high"),
                        help="Detail per frame; high reads small on-screen text and costs about 4x")
    parser.add_argument("--max-output-tokens", type=int, help="Cap on the answer's length")
    parser.add_argument("--timeout", type=float, default=1800, help="Seconds to wait for the answer (default 1800)")
    parser.add_argument("--max-inline-mb", type=float, help="Size cap for providers that take video inline")
    parser.add_argument("--delete-remote", action="store_true",
                        help="Delete the uploaded video from the provider after this call")
    parser.add_argument("--force", action="store_true", help="Send even if the context estimate says it will not fit")
    args = parser.parse_args()

    video = Video(Path(args.video).expanduser().resolve())
    if not video.path.is_file():
        fail("video_not_found", f"No such file: {video.path}", 1)
    if video.size == 0:
        fail("video_empty", f"The file is empty: {video.path}", 1)
    try:
        start, end = parse_timestamp(args.start), parse_timestamp(args.end)
    except ValueError as exc:
        fail("invalid_window", str(exc), 1)
    if start is not None and end is not None and end <= start:
        fail("invalid_window", "--end must be later than --start.", 1)

    prompt = args.prompt if args.prompt else read_text_file(args.prompt_file, "prompt file")[1]
    if not prompt.strip():
        fail("empty_prompt", "The prompt is empty.", 1)
    context = [read_text_file(path, "context file") for path in args.context_file]

    try:
        resolved = settings.resolve({"PROVIDER": args.provider, "MODEL": args.model, "BASE_URL": args.base_url})
    except settings.ConfigError as exc:
        fail(exc.code, exc.message, 2, missing=exc.missing,
             hint=f"Show the current state with: python3 {Path(__file__).with_name('config.py')} show")
    adapter = make_adapter(resolved)
    destination = {
        "provider": resolved.provider,
        "model": resolved.model,
        "endpoint": resolved.base_url,
        "sources": {
            "provider": resolved.sources.get("PROVIDER"),
            "model": resolved.sources.get("MODEL"),
            "endpoint": resolved.sources.get("BASE_URL"),
            "api_key": resolved.sources.get("API_KEY"),
        },
    }
    options = {
        "start": start,
        "end": end,
        "fps": args.fps,
        "resolution": args.resolution,
        "max_inline_mb": args.max_inline_mb,
    }
    window = (start, end) if (start is not None or end is not None) else None
    texts = build_texts(prompt, context, window)
    notes = list(resolved.notes)

    try:
        adapter.check_transport(video, options)
        limits = adapter.model_limits()

        log(f"Sending {video.path.name} ({video.size / 1024 ** 2:.0f} MB) to "
            f"{urlsplit(resolved.base_url).hostname}, model {resolved.model}")
        cache, cache_key = load_remote_files(), None
        if adapter.keeps_uploads:
            cache_key = remote_key(adapter.name, resolved.base_url, resolved.key_fingerprint, video.sha256)
            options["cached_remote"] = cache.get(cache_key)
        handle = adapter.ensure_video(video, options, log)
        if cache_key and handle.get("name"):
            cache[cache_key] = {
                "name": handle["name"],
                "expires": handle.get("expires"),
                "provider": resolved.provider,
                "endpoint": resolved.base_url,
                "video": str(video.path),
                "sha256": video.sha256,
                "size_bytes": video.size,
            }
            save_remote_files(cache)

        duration = handle.get("duration_seconds") or video.duration
        sent_seconds = None
        if duration is not None:
            sent_seconds = max(0.0, min(end if end is not None else duration, duration) - (start or 0))
        estimate = None
        if sent_seconds is not None:
            video_tokens = adapter.estimate_video_tokens(sent_seconds, options)
            if video_tokens is not None:
                text_tokens = sum(len(text) for text in texts) // CHARS_PER_TOKEN
                estimate = {"video_tokens": video_tokens, "text_tokens": text_tokens,
                            "input_tokens": video_tokens + text_tokens}
        input_limit = (limits or {}).get("input_tokens")
        if estimate and input_limit and not args.force:
            reserve = args.max_output_tokens or DEFAULT_ANSWER_RESERVE
            if estimate["input_tokens"] + reserve > input_limit:
                raise PreflightError(
                    "context_exceeded",
                    f"About {estimate['input_tokens']:,} input tokens for {format_timestamp(sent_seconds)} of video "
                    f"plus {estimate['text_tokens']:,} tokens of text, with {reserve:,} held for the answer, "
                    f"does not fit this model's {input_limit:,} token input limit.",
                    ["Send a shorter window with --start/--end and cover the recording in several calls.",
                     "Use a lower --resolution or --fps.",
                     "Pass --force to send it anyway."],
                )

        started = time.monotonic()
        result = adapter.run(handle, {
            "texts": texts,
            "start": start,
            "end": end,
            "fps": args.fps,
            "resolution": args.resolution,
            "max_output_tokens": args.max_output_tokens,
            "timeout": args.timeout,
        }, log)
        elapsed = round(time.monotonic() - started, 1)
    except PreflightError as exc:
        fail(exc.code, exc.message, 3, options=exc.options, destination=destination)
    except ProviderError as exc:
        fail("provider_error", exc.message, 4, status=exc.status, destination=destination)

    notes.extend(result["notes"])
    remote = None
    if handle.get("name"):
        remote = {"name": handle["name"], "expires": handle.get("expires"), "reused": handle.get("reused", False),
                  "deleted": False}
        if args.delete_remote:
            try:
                remote["deleted"] = adapter.delete_remote(handle["name"])
            except ProviderError as exc:
                notes.append(f"Could not delete the upload {handle['name']}: {exc.message}")
            if remote["deleted"] and cache_key:
                cache.pop(cache_key, None)
                save_remote_files(cache)

    session_path = resolve_session(args.session, args.title, args.project, fallback_title=video.path.stem)
    call_dir = new_subdir(session_path, args.label or video.path.stem)
    answer_path = call_dir / "answer.md"
    answer_path.write_text(result["text"] if result["text"].endswith("\n") else result["text"] + "\n")
    (call_dir / "prompt.md").write_text(prompt if prompt.endswith("\n") else prompt + "\n")
    summary = {
        "ok": True,
        "answer_path": str(answer_path),
        "session": str(session_path),
        "call_dir": str(call_dir),
        "destination": destination,
        "video": {
            "path": str(video.path),
            "size_bytes": video.size,
            "sha256": video.sha256,
            "duration_seconds": duration,
        },
        "window": {"start_seconds": start, "end_seconds": end} if window else None,
        "context_files": [str(path) for path, _ in context],
        "estimate": estimate,
        "usage": result["usage"],
        "status": result["status"],
        "elapsed_seconds": elapsed,
        "remote": remote,
        "notes": notes,
    }
    (call_dir / "call.json").write_text(json.dumps(
        {**summary, "created": datetime.now().isoformat(timespec="seconds"),
         "options": {"fps": args.fps, "resolution": args.resolution, "max_output_tokens": args.max_output_tokens}},
        indent=2,
    ))
    record_call(session_path, {
        "dir": call_dir.name,
        "video": str(video.path),
        "model": resolved.model,
        "provider": resolved.provider,
        "window": summary["window"],
        "answer": str(answer_path),
    })
    emit(summary)


if __name__ == "__main__":
    main()
