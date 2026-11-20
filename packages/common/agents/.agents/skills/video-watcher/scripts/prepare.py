#!/usr/bin/env python3
"""Shrink or trim a video with ffmpeg so it fits a provider's transport limit.

Tuned for screen recordings: resolution is kept (capped at --max-height) so
small on-screen text stays legible, while frame rate and bitrate drop. Models
sample about one frame per second, so a few frames per second loses nothing
they would have seen. Output is always mp4 (H.264 + AAC), which also converts
containers a provider does not accept.

Timestamps in a trimmed file start at zero. The JSON reports
`time_offset_seconds`; add it to any timestamp the model gives back.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from media import Video, parse_timestamp
from session_paths import resolve_session, to_kebab_case


def fail(code: str, message: str, exit_code: int = 1, **extra) -> None:
    print(json.dumps({"ok": False, "error": {"code": code, "message": message, **extra}}, indent=2))
    sys.exit(exit_code)


def main():
    parser = argparse.ArgumentParser(description="Transcode or trim a video for sending to a model")
    parser.add_argument("--video", required=True)
    parser.add_argument("--out", help="Output path (default: inside the session's prepared/ folder)")
    parser.add_argument("--session", help="Existing session.json")
    parser.add_argument("--title", help="Title for a new session (default: the video's file name)")
    parser.add_argument("--project")
    parser.add_argument("--start", help="Trim start: seconds or [HH:]MM:SS")
    parser.add_argument("--end", help="Trim end: seconds or [HH:]MM:SS")
    parser.add_argument("--fps", type=float, default=5.0, help="Output frame rate (default 5)")
    parser.add_argument("--max-height", type=int, default=1080, help="Downscale taller video to this (default 1080)")
    parser.add_argument("--crf", type=int, default=28, help="H.264 quality, lower is better and larger (default 28)")
    parser.add_argument("--audio-bitrate", default="48k", help="Mono AAC bitrate (default 48k)")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        fail("ffmpeg_missing", "ffmpeg is not installed. Ask the user before installing it.")
    video = Video(Path(args.video).expanduser().resolve())
    if not video.path.is_file():
        fail("video_not_found", f"No such file: {video.path}")
    try:
        start, end = parse_timestamp(args.start), parse_timestamp(args.end)
    except ValueError as exc:
        fail("invalid_window", str(exc))
    if start is not None and end is not None and end <= start:
        fail("invalid_window", "--end must be later than --start.")

    session_path = None
    if args.out:
        output = Path(args.out).expanduser().resolve()
    else:
        session_path = resolve_session(args.session, args.title, args.project, fallback_title=video.path.stem)
        folder = session_path.parent / "prepared"
        folder.mkdir(exist_ok=True)
        suffix = "" if start is None and end is None else f"-{int(start or 0)}s-{int(end) if end is not None else 'end'}s"
        output = folder / f"{to_kebab_case(video.path.stem) or 'video'}{suffix}.mp4"
    if output == video.path:
        fail("same_file", "The output path is the source file.")
    output.parent.mkdir(parents=True, exist_ok=True)

    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None:
        command += ["-ss", f"{start:g}"]
    if end is not None:
        command += ["-to", f"{end:g}"]
    command += [
        "-i", str(video.path),
        "-vf", f"fps={args.fps:g},scale=-2:'min({args.max_height},ih)'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(args.crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ac", "1", "-b:a", args.audio_bitrate,
        "-movflags", "+faststart",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        output.unlink(missing_ok=True)
        fail("ffmpeg_failed", result.stderr.strip()[-1500:] or "ffmpeg failed.")

    prepared = Video(output)
    print(json.dumps({
        "ok": True,
        "output": str(output),
        "session": str(session_path) if session_path else None,
        "size_bytes": prepared.size,
        "original_size_bytes": video.size,
        "duration_seconds": prepared.duration,
        "time_offset_seconds": start or 0,
        "settings": {"fps": args.fps, "max_height": args.max_height, "crf": args.crf},
    }, indent=2))


if __name__ == "__main__":
    main()
