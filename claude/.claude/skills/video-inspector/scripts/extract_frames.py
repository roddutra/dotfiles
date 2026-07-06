#!/usr/bin/env python3
"""Extract timestamped frames from a recorded video for visual inspection.

Given a session (from init_session.py) and a path to an already-recorded
video, this samples frames at a safe default rate, labels each with its
source timestamp, and persists them into a timestamped subfolder of the
session so an agent can read the stills in order.

All the media logic lives here so the invoking agent only has to run this
script with a video path and, optionally, override a few parameters. It
never needs to hand-build an ffmpeg command.

Why a low default frame rate: a screen recording is often 30-60 fps. Pulling
every frame into an agent's context is thousands of near-identical images and
tens of thousands of tokens. One frame per second (the default) is enough to
follow navigation, a button press, a dropdown opening, or an animation's
overall timing, while staying cheap. A hard max-frames cap protects against
long clips; when the cap would be exceeded the sample rate is automatically
lowered to fit, and the *effective* interval is reported so the agent knows
the real spacing between frames. If the agent needs finer detail on one
moment, it re-runs with a narrow --start/--end window and a higher --fps.
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from session_paths import to_kebab_case, validate_session_path
from ffmpeg_utils import (
    require_ffmpeg,
    probe_video,
    drawtext_available,
    find_font,
    fit_sampling,
)

# Default sample rate: one frame per second. Enough to read timing without
# flooding the agent's context.
_DEFAULT_FPS = 1.0

# Hard cap on frames produced by a single extraction. Keeps a long clip from
# blowing up the session and the agent's context. When the requested rate
# would exceed this, the rate is lowered to fit (and reported).
_DEFAULT_MAX_FRAMES = 60

# Downscale frames wider than this (preserving aspect) to bound per-image
# token cost while keeping UI text legible. Raise it when you need to read
# fine detail; lower it for cheaper overview passes.
_DEFAULT_MAX_WIDTH = 1280

# If the effective spacing between frames ends up coarser than this, the clip
# is long enough that a 1-fps overview was auto-thinned a lot -- warn the
# agent so it narrows the window rather than trusting a very sparse sample.
_COARSE_INTERVAL_WARN = 5.0


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a number, got {value!r}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"expected a value > 0, got {parsed}")
    return parsed


def _non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a number, got {value!r}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"expected a value >= 0, got {parsed}")
    return parsed


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"expected a value > 0, got {parsed}")
    return parsed


def _build_vf(fps: float, max_width: int | None, font: str | None) -> str:
    """Assemble the ffmpeg -vf filter chain: sample -> scale -> overlay."""
    parts = [f"fps={fps}"]
    if max_width:
        # Only downscale (min(iw, W)); -2 keeps dimensions even.
        parts.append(f"scale='min(iw,{max_width})':-2")
    if font:
        # Burn the frame's presentation time (h:m:s.ms) into the top-left.
        # This is a visual aid; the filename carries the authoritative
        # absolute timestamp. With an extraction window, this overlay reads
        # as time-since-window-start.
        parts.append(
            f"drawtext=fontfile={font}:text='%{{pts\\:hms}}'"
            ":x=14:y=14:fontsize=28:fontcolor=white"
            ":box=1:boxcolor=black@0.55:boxborderw=10"
        )
    return ",".join(parts)


def _run_ffmpeg(video: Path, start: float, duration: float | None,
                vf: str, out_pattern: Path, fmt: str) -> subprocess.CompletedProcess:
    """Run one ffmpeg extraction pass. Output seeking (-ss after -i) is
    frame-accurate, which matters for short UI clips."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
    if start > 0:
        cmd += ["-ss", f"{start}"]
    if duration is not None:
        cmd += ["-t", f"{duration}"]
    cmd += ["-vf", vf, "-fps_mode", "vfr"]
    if fmt in ("jpg", "jpeg"):
        cmd += ["-q:v", "3"]
    cmd += [str(out_pattern)]
    return subprocess.run(cmd, capture_output=True, text=True)


def extract_frames(
    session_path: Path,
    video: Path,
    fps: float = _DEFAULT_FPS,
    start: float = 0.0,
    end: float | None = None,
    max_frames: int = _DEFAULT_MAX_FRAMES,
    max_width: int | None = _DEFAULT_MAX_WIDTH,
    fmt: str = "jpg",
    label: str | None = None,
    overlay: bool = True,
    font: str | None = None,
    copy_video: bool = True,
) -> dict:
    require_ffmpeg()

    validate_session_path(session_path)
    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}", file=sys.stderr)
        sys.exit(1)
    try:
        metadata = json.loads(session_path.read_text())
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in session file: {session_path}", file=sys.stderr)
        sys.exit(1)

    video = video.expanduser()
    if not video.is_file():
        print(f"Error: Video not found: {video}", file=sys.stderr)
        sys.exit(1)
    video = video.resolve()

    probe = probe_video(video)
    duration = probe["duration"]

    # Resolve the extraction window and validate it.
    win_start = start
    win_end = end if end is not None else duration
    if win_end > duration:
        win_end = duration
    if win_start >= win_end:
        print(
            f"Error: empty extraction window: start={win_start}s, end={win_end}s "
            f"(video duration {duration}s).",
            file=sys.stderr,
        )
        sys.exit(1)
    window_dur = round(win_end - win_start, 3)

    # Fit the requested rate under the frame cap. If the requested fps would
    # produce more than max_frames, lower it to fit and record that we did.
    notes: list[str] = []
    fit = fit_sampling(window_dur, fps, max_frames)
    requested_fps = fit["requested_fps"]
    fps = fit["fps"]
    downsampled = fit["downsampled"]
    interval = fit["interval_seconds"]
    if downsampled:
        notes.append(
            f"Requested {requested_fps} fps over {window_dur}s would yield "
            f"~{max(1, round(window_dur * requested_fps))} frames (> --max-frames "
            f"{max_frames}); lowered to {round(fps, 4)} fps to fit."
        )
    if interval > _COARSE_INTERVAL_WARN:
        notes.append(
            f"Effective interval is {interval}s between frames -- coarse. If "
            f"you need to see a specific moment, re-run with a narrow "
            f"--start/--end window and a higher --fps."
        )

    # Resolve the overlay (best-effort; frames are still labelled by filename).
    use_overlay = overlay
    resolved_font = None
    if use_overlay:
        if not drawtext_available():
            use_overlay = False
            notes.append("Timestamp overlay skipped: this ffmpeg build lacks the drawtext filter.")
        else:
            resolved_font = find_font(font)
            if not resolved_font:
                use_overlay = False
                notes.append(
                    "Timestamp overlay skipped: no usable font found. Pass "
                    "--font <path-to-.ttf> to enable it."
                )

    # Create the per-video subfolder inside the session.
    session_dir = session_path.parent
    slug = to_kebab_case(label) if label else to_kebab_case(video.stem)
    slug = slug or "video"
    time_str = datetime.now().strftime("%H%M%S")
    video_dir = session_dir / f"{time_str}-{slug}"
    video_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = video_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    ext = "jpg" if fmt == "jpeg" else fmt
    out_pattern = frames_dir / f"raw_%05d.{ext}"

    # Extract. If the overlay pass fails (font/filter edge case), retry once
    # without it so the agent still gets labelled frames.
    vf = _build_vf(fps, max_width, resolved_font if use_overlay else None)
    proc = _run_ffmpeg(video, win_start, window_dur, vf, out_pattern, ext)
    if proc.returncode != 0 and use_overlay:
        for f in frames_dir.glob(f"raw_*.{ext}"):
            f.unlink()
        use_overlay = False
        notes.append(f"Timestamp overlay failed and was disabled; retried without it. ({proc.stderr.strip()[:200]})")
        vf = _build_vf(fps, max_width, None)
        proc = _run_ffmpeg(video, win_start, window_dur, vf, out_pattern, ext)

    if proc.returncode != 0:
        print(
            f"Error: ffmpeg frame extraction failed.\n{proc.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Rename raw_00001.ext -> frame_00001_t<abs-seconds>s.ext. The timestamp is
    # computed authoritatively (window start + index/fps), independent of any
    # overlay, so the agent can always read the exact time from the filename.
    raw_frames = sorted(frames_dir.glob(f"raw_*.{ext}"))
    if not raw_frames:
        print(
            "Error: ffmpeg produced no frames. The window may be shorter than "
            "one frame interval -- try a lower --fps or a wider window.",
            file=sys.stderr,
        )
        sys.exit(1)

    frames: list[dict] = []
    for i, raw in enumerate(raw_frames, start=1):
        ts = round(win_start + (i - 1) / fps, 3)
        name = f"frame_{i:05d}_t{ts:0.3f}s.{ext}"
        dest = frames_dir / name
        raw.rename(dest)
        frames.append({
            "index": i,
            "timestamp": ts,
            "path": str(dest),
        })

    # Persist a copy of the source video centrally (unless told not to), so the
    # session is a self-contained record for later inspection/debugging.
    stored_video = None
    if copy_video:
        stored_video = video_dir / f"source{video.suffix.lower() or '.mp4'}"
        try:
            shutil.copy2(video, stored_video)
            stored_video = str(stored_video)
        except OSError as exc:
            stored_video = None
            notes.append(f"Could not copy source video into the session ({exc}); left in place.")

    result = {
        "session": str(session_path),
        "video_dir": str(video_dir),
        "frames_dir": str(frames_dir),
        "frame_count": len(frames),
        "requested_fps": requested_fps,
        "effective_fps": round(fps, 4),
        "interval_seconds": interval,
        "downsampled": downsampled,
        "window": {"start": win_start, "end": round(win_end, 3), "duration": window_dur},
        "format": ext,
        "overlay": use_overlay,
        "source": {"path": str(video), **probe},
        "stored_video": stored_video,
        "frames": frames,
        "notes": notes,
    }

    # Write the per-video manifest and append a lightweight summary to the
    # session so list_sessions can show what's inside without opening manifests.
    manifest_path = video_dir / "manifest.json"
    manifest_path.write_text(json.dumps(result, indent=2))
    result["manifest"] = str(manifest_path)

    metadata.setdefault("videos", []).append({
        "slug": slug,
        "time": time_str,
        "video_dir": str(video_dir),
        "source_path": str(video),
        "frame_count": len(frames),
        "effective_fps": round(fps, 4),
        "interval_seconds": interval,
    })
    session_path.write_text(json.dumps(metadata, indent=2))

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Extract timestamped frames from a video for visual inspection."
    )
    parser.add_argument("--session", required=True, help="Path to session.json (from init_session.py)")
    parser.add_argument("--video", required=True, help="Path to the already-recorded video file")
    parser.add_argument(
        "--fps", type=_positive_float, default=_DEFAULT_FPS,
        help=f"Frames sampled per second (default {_DEFAULT_FPS}). Use e.g. 0.5 for one every 2s, "
             f"or a higher value on a narrow window for fine detail.",
    )
    parser.add_argument("--start", type=_non_negative_float, default=0.0, help="Window start in seconds (default 0)")
    parser.add_argument("--end", type=_positive_float, default=None, help="Window end in seconds (default: end of video)")
    parser.add_argument(
        "--max-frames", type=_positive_int, default=_DEFAULT_MAX_FRAMES,
        help=f"Cap on frames per extraction (default {_DEFAULT_MAX_FRAMES}). If the rate would "
             f"exceed this, it is lowered to fit and reported.",
    )
    parser.add_argument(
        "--max-width", type=_positive_int, default=_DEFAULT_MAX_WIDTH,
        help=f"Downscale frames wider than this, preserving aspect (default {_DEFAULT_MAX_WIDTH}). "
             f"Pass a larger value to read fine UI detail; 0 disables scaling.",
    )
    parser.add_argument("--format", dest="fmt", choices=["jpg", "jpeg", "png", "webp"], default="jpg", help="Frame image format (default jpg)")
    parser.add_argument("--label", default=None, help="Short label for the video subfolder (default: source filename)")
    parser.add_argument("--no-overlay", dest="overlay", action="store_false", help="Do not burn the timestamp into each frame (filenames still carry it)")
    parser.add_argument("--font", default=None, help="Font file (.ttf/.ttc) for the timestamp overlay (default: auto-detect)")
    parser.add_argument("--no-copy-video", dest="copy_video", action="store_false", help="Do not copy the source video into the session folder")
    args = parser.parse_args()

    result = extract_frames(
        session_path=Path(args.session),
        video=Path(args.video),
        fps=args.fps,
        start=args.start,
        end=args.end,
        max_frames=args.max_frames,
        max_width=(args.max_width or None),
        fmt=args.fmt,
        label=args.label,
        overlay=args.overlay,
        font=args.font,
        copy_video=args.copy_video,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
