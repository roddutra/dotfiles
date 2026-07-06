#!/usr/bin/env python3
"""Build a single contact-sheet (montage) image from a recorded video.

This is the CHEAP overview pass. Reading N separate full-size frames costs N
image payloads and can be tens of thousands of vision tokens; a contact sheet
tiles those same moments into ONE image so an agent can grasp the whole
timeline -- overall staging, what changes and roughly when -- for the token
cost of a single picture. Drill into specific moments afterwards with
extract_frames.py at full resolution (to read fine UI text, exact motion, etc).

Frames are laid out in reading order: left-to-right, top-to-bottom, starting at
the window start. When this ffmpeg build has the drawtext filter, each cell is
labelled with its time; when it doesn't, the returned `cells` array is the
authoritative index -> timestamp map (cell 0 is top-left, filled row by row).

All the media logic lives here so the invoking agent only runs this script with
a video path and, optionally, a few layout overrides. It never hand-builds an
ffmpeg command.
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from math import ceil
from pathlib import Path

from session_paths import to_kebab_case, validate_session_path
from ffmpeg_utils import (
    require_ffmpeg,
    probe_video,
    drawtext_available,
    find_font,
    fit_sampling,
)

# One frame per second of source, same rhythm as extract_frames' overview.
_DEFAULT_FPS = 1.0

# Cap on tiles in a single sheet. Beyond this the sheet gets too dense to read
# and the sampling is thinned to fit (and reported). 40 in a 5-wide grid is 8
# rows -- comfortably legible while covering a ~40s clip at 1 fps.
_DEFAULT_MAX_CELLS = 40

# Grid width. 5 columns keeps each cell wide enough to tell stages apart on a
# 16:9 screen recording while fitting a long clip in a few rows.
_DEFAULT_COLUMNS = 5

# Per-cell width in px (height follows the source aspect). ~320 shows a
# desktop UI's layout and colour clearly; raise it to make small text in the
# thumbnails legible, though a full-res extract_frames drill-in is better for
# reading text.
_DEFAULT_CELL_WIDTH = 320

# Sheet background / gutter colour (dark, so light UIs stand out).
_SHEET_COLOR = "0x111417"


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


def _build_vf(fps: float, cell_width: int, cols: int, rows: int,
              font: str | None) -> str:
    """ffmpeg -vf chain: sample -> scale each cell -> (label) -> tile."""
    parts = [f"fps={fps}", f"scale={cell_width}:-2"]
    if font:
        # Burn time-since-window-start into each cell as a visual aid. The
        # returned `cells` map remains authoritative.
        parts.append(
            f"drawtext=fontfile={font}:text='%{{pts\\:hms}}'"
            ":x=6:y=6:fontsize=20:fontcolor=white"
            ":box=1:boxcolor=black@0.55:boxborderw=6"
        )
    parts.append(f"tile={cols}x{rows}:margin=6:padding=6:color={_SHEET_COLOR}")
    return ",".join(parts)


def contact_sheet(
    session_path: Path,
    video: Path,
    fps: float = _DEFAULT_FPS,
    start: float = 0.0,
    end: float | None = None,
    max_cells: int = _DEFAULT_MAX_CELLS,
    columns: int = _DEFAULT_COLUMNS,
    cell_width: int = _DEFAULT_CELL_WIDTH,
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

    win_start = start
    win_end = end if end is not None else duration
    if win_end > duration:
        win_end = duration
    if win_start >= win_end:
        print(
            f"Error: empty window: start={win_start}s, end={win_end}s "
            f"(video duration {duration}s).",
            file=sys.stderr,
        )
        sys.exit(1)
    window_dur = round(win_end - win_start, 3)

    notes: list[str] = []

    # Decide the tile count. Sample at the requested rate, but never more than
    # max_cells (thin to fit, and report it). Then even the rate out over the
    # window so the tiles are regularly spaced and the timestamp map is exact.
    fit = fit_sampling(window_dur, fps, max_cells)
    requested_fps = fit["requested_fps"]
    if fit["downsampled"]:
        notes.append(
            f"Requested {requested_fps} fps over {window_dur}s would need "
            f"~{max(1, round(window_dur * requested_fps))} tiles (> --max-cells "
            f"{max_cells}); thinned to fit one sheet."
        )
    cells = max(1, min(fit["est_frames"], max_cells))
    effective_fps = cells / window_dur
    interval = round(1.0 / effective_fps, 3)

    cols = max(1, min(columns, cells))
    rows = max(1, ceil(cells / cols))

    # Resolve the optional per-cell overlay (best-effort; ordering + the cells
    # map are the real labels).
    use_overlay = overlay
    resolved_font = None
    if use_overlay:
        if not drawtext_available():
            use_overlay = False
            notes.append(
                "Cell timestamps not burned in: this ffmpeg build lacks the "
                "drawtext filter. Cells are in reading order (left-to-right, "
                "top-to-bottom) from the window start; use the `cells` map for "
                "exact times."
            )
        else:
            resolved_font = find_font(font)
            if not resolved_font:
                use_overlay = False
                notes.append(
                    "Cell timestamps not burned in: no usable font found. Pass "
                    "--font <path-to-.ttf> to enable, or use the `cells` map."
                )

    # Per-video subfolder inside the session (suffix marks it as a sheet).
    session_dir = session_path.parent
    slug = to_kebab_case(label) if label else to_kebab_case(video.stem)
    slug = slug or "video"
    time_str = datetime.now().strftime("%H%M%S")
    sheet_dir = session_dir / f"{time_str}-{slug}-sheet"
    sheet_dir.mkdir(parents=True, exist_ok=True)

    ext = "jpg" if fmt == "jpeg" else fmt
    sheet_path = sheet_dir / f"contact-sheet.{ext}"

    vf = _build_vf(effective_fps, cell_width, cols, rows,
                   resolved_font if use_overlay else None)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
    if win_start > 0:
        cmd += ["-ss", f"{win_start}"]
    cmd += ["-t", f"{window_dur}", "-vf", vf, "-frames:v", "1"]
    if ext in ("jpg", "jpeg"):
        cmd += ["-q:v", "3"]
    cmd += [str(sheet_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    # If the labelled pass fails (font/filter edge case), retry once plain so
    # the agent still gets a sheet.
    if proc.returncode != 0 and use_overlay:
        use_overlay = False
        notes.append(
            f"Cell labelling failed and was disabled; retried without it. "
            f"({proc.stderr.strip()[:200]})"
        )
        vf = _build_vf(effective_fps, cell_width, cols, rows, None)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
        if win_start > 0:
            cmd += ["-ss", f"{win_start}"]
        cmd += ["-t", f"{window_dur}", "-vf", vf, "-frames:v", "1"]
        if ext in ("jpg", "jpeg"):
            cmd += ["-q:v", "3"]
        cmd += [str(sheet_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode != 0 or not sheet_path.is_file():
        print(
            f"Error: ffmpeg could not build the contact sheet.\n{proc.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Authoritative index -> timestamp map (row-major, matching the tile order).
    cell_map = []
    for i in range(cells):
        ts = round(win_start + i / effective_fps, 3)
        cell_map.append({
            "index": i,
            "timestamp": ts,
            "row": i // cols,
            "col": i % cols,
        })

    # Persist a copy of the source into the sheet folder (unless told not to),
    # so the pass folder is self-contained and no recording is left loose at
    # the session root. Same behaviour as extract_frames.
    stored_video = None
    if copy_video:
        stored_video = sheet_dir / f"source{video.suffix.lower() or '.mp4'}"
        try:
            shutil.copy2(video, stored_video)
            stored_video = str(stored_video)
        except OSError as exc:
            stored_video = None
            notes.append(f"Could not copy source video into the session ({exc}); left in place.")

    result = {
        "session": str(session_path),
        "sheet_dir": str(sheet_dir),
        "sheet": str(sheet_path),
        "cell_count": cells,
        "columns": cols,
        "rows": rows,
        "cell_width": cell_width,
        "reading_order": "left-to-right, top-to-bottom",
        "requested_fps": requested_fps,
        "effective_fps": round(effective_fps, 4),
        "interval_seconds": interval,
        "downsampled": fit["downsampled"],
        "labelled": use_overlay,
        "window": {"start": win_start, "end": round(win_end, 3), "duration": window_dur},
        "format": ext,
        "source": {"path": str(video), **probe},
        "stored_video": stored_video,
        "cells": cell_map,
        "notes": notes,
    }

    manifest_path = sheet_dir / "manifest.json"
    manifest_path.write_text(json.dumps(result, indent=2))
    result["manifest"] = str(manifest_path)

    metadata.setdefault("videos", []).append({
        "kind": "contact_sheet",
        "slug": slug,
        "time": time_str,
        "video_dir": str(sheet_dir),
        "source_path": str(video),
        "cell_count": cells,
        "effective_fps": round(effective_fps, 4),
        "interval_seconds": interval,
    })
    session_path.write_text(json.dumps(metadata, indent=2))

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Build a single contact-sheet (montage) image for a cheap "
                    "overview pass before drilling in with extract_frames.py."
    )
    parser.add_argument("--session", required=True, help="Path to session.json (from init_session.py)")
    parser.add_argument("--video", required=True, help="Path to the already-recorded video file")
    parser.add_argument(
        "--fps", type=_positive_float, default=_DEFAULT_FPS,
        help=f"Frames sampled per second (default {_DEFAULT_FPS}); thinned if the "
             f"count would exceed --max-cells.",
    )
    parser.add_argument("--start", type=_non_negative_float, default=0.0, help="Window start in seconds (default 0)")
    parser.add_argument("--end", type=_positive_float, default=None, help="Window end in seconds (default: end of video)")
    parser.add_argument(
        "--max-cells", type=_positive_int, default=_DEFAULT_MAX_CELLS,
        help=f"Cap on tiles in one sheet (default {_DEFAULT_MAX_CELLS}); sampling is "
             f"thinned to fit and reported.",
    )
    parser.add_argument("--columns", type=_positive_int, default=_DEFAULT_COLUMNS, help=f"Grid width in tiles (default {_DEFAULT_COLUMNS})")
    parser.add_argument(
        "--cell-width", type=_positive_int, default=_DEFAULT_CELL_WIDTH,
        help=f"Per-cell width in px, aspect preserved (default {_DEFAULT_CELL_WIDTH}). "
             f"Raise to read small text in thumbnails.",
    )
    parser.add_argument("--format", dest="fmt", choices=["jpg", "jpeg", "png", "webp"], default="jpg", help="Sheet image format (default jpg)")
    parser.add_argument("--label", default=None, help="Short label for the sheet subfolder (default: source filename)")
    parser.add_argument("--no-overlay", dest="overlay", action="store_false", help="Do not burn per-cell timestamps (the cells map still carries them)")
    parser.add_argument("--font", default=None, help="Font file (.ttf/.ttc) for cell labels (default: auto-detect)")
    parser.add_argument("--no-copy-video", dest="copy_video", action="store_false", help="Do not copy the source into the sheet folder (copied in by default so the pass folder is self-contained; skip for very large sources)")
    args = parser.parse_args()

    result = contact_sheet(
        session_path=Path(args.session),
        video=Path(args.video),
        fps=args.fps,
        start=args.start,
        end=args.end,
        max_cells=args.max_cells,
        columns=args.columns,
        cell_width=args.cell_width,
        fmt=args.fmt,
        label=args.label,
        overlay=args.overlay,
        font=args.font,
        copy_video=args.copy_video,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
