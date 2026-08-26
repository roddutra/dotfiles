#!/usr/bin/env python3
"""ffmpeg / ffprobe helpers for the video-inspector skill.

Keeps all the media-tool interaction in one place so the command scripts
stay thin and the invoking agent never has to hand-build ffmpeg commands.
"""

import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Candidate fonts for the (optional) burned-in timestamp overlay, in order
# of preference. drawtext needs a real font file; these cover macOS and the
# common Linux distributions. Override with --font.
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]


# Per-OS install commands. The first entry for each OS is the recommended
# one; alternatives are listed so the agent can adapt to what the user has.
_INSTALL_COMMANDS = {
    "macos": [
        ("Homebrew", "brew install ffmpeg"),
        ("MacPorts", "sudo port install ffmpeg"),
    ],
    "linux": [
        ("Debian/Ubuntu", "sudo apt-get update && sudo apt-get install -y ffmpeg"),
        ("Fedora", "sudo dnf install -y ffmpeg"),
        ("Arch", "sudo pacman -S ffmpeg"),
    ],
    "windows": [
        ("winget", "winget install --id Gyan.FFmpeg -e"),
        ("Chocolatey", "choco install ffmpeg"),
        ("Scoop", "scoop install ffmpeg"),
    ],
}


def detect_os() -> str:
    """Return a normalized OS key: 'macos', 'linux', 'windows', or 'unknown'."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "linux":
        return "linux"
    if system == "windows":
        return "windows"
    return "unknown"


def install_commands(os_key: str | None = None) -> list[tuple[str, str]]:
    """Install command options (manager, command) for the given/detected OS."""
    return _INSTALL_COMMANDS.get(os_key or detect_os(), [])


def _install_hint_text(os_key: str) -> str:
    options = install_commands(os_key)
    if not options:
        return (
            "Install ffmpeg using your platform's package manager, then ensure "
            "it is on PATH. See https://ffmpeg.org/download.html"
        )
    lines = [f"  {manager}: {cmd}" for manager, cmd in options]
    return "Install ffmpeg with one of:\n" + "\n".join(lines)


def require_ffmpeg() -> None:
    """Exit with OS-aware install guidance if ffmpeg/ffprobe are missing.

    Both binaries ship together, but we check each so the error names the
    exact one that's absent. The message leads with the command for the
    detected OS so the agent can surface it to the user and ask permission
    to install, rather than guessing across platforms.
    """
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        os_key = detect_os()
        print(
            f"Error: required tool(s) not found on PATH: {', '.join(missing)}.\n"
            f"This skill shells out to ffmpeg/ffprobe to read and sample the "
            f"video.\n\n"
            f"Detected OS: {os_key}\n"
            f"{_install_hint_text(os_key)}\n\n"
            f"Ask the user before installing (it changes their system), then "
            f"re-run. If ffmpeg is already installed but not found, ensure its "
            f"directory is on PATH for the shell running this script.",
            file=sys.stderr,
        )
        sys.exit(1)


def _tool_version(tool: str) -> str | None:
    """Return the first line of `<tool> -version`, or None if unavailable."""
    if shutil.which(tool) is None:
        return None
    try:
        result = subprocess.run([tool, "-version"], capture_output=True, text=True)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    first = result.stdout.splitlines()[0] if result.stdout else ""
    return first.strip() or None


def check_dependencies() -> dict:
    """Structured report of the local media environment for preflight.

    Returns platform info, whether ffmpeg/ffprobe are present (with versions
    and paths), overlay capability (drawtext + a usable font), and the
    OS-appropriate install options. Never exits -- callers decide what to do.
    """
    os_key = detect_os()
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    ready = bool(ffmpeg_path and ffprobe_path)
    font = find_font() if ready else None
    return {
        "os": os_key,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "ffmpeg": {"present": bool(ffmpeg_path), "path": ffmpeg_path, "version": _tool_version("ffmpeg")},
        "ffprobe": {"present": bool(ffprobe_path), "path": ffprobe_path, "version": _tool_version("ffprobe")},
        "ready": ready,
        "overlay": {
            "drawtext": drawtext_available() if ready else False,
            "font": font,
            "available": bool(ready and font and drawtext_available()),
        },
        "install_options": [
            {"manager": manager, "command": cmd} for manager, cmd in install_commands(os_key)
        ],
    }


def probe_video(video_path: Path) -> dict:
    """Return basic properties of the first video stream via ffprobe.

    Keys: duration (float seconds), width, height, fps (float), codec.
    Duration falls back across format -> stream because some containers
    populate only one. Exits with a clear message if neither is present
    (the caller can then require an explicit --end).
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name,duration",
        "-show_entries", "format=duration",
        "-of", "json",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(
            f"Error: ffprobe could not read the video: {video_path}\n"
            f"{result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Error: could not parse ffprobe output for {video_path}", file=sys.stderr)
        sys.exit(1)

    streams = data.get("streams") or []
    if not streams:
        print(
            f"Error: no video stream found in {video_path}. Is this an "
            f"audio-only or non-video file?",
            file=sys.stderr,
        )
        sys.exit(1)
    stream = streams[0]

    # Duration: prefer format-level, fall back to stream-level.
    duration = None
    for candidate in (data.get("format", {}).get("duration"), stream.get("duration")):
        try:
            duration = float(candidate)
            break
        except (TypeError, ValueError):
            continue
    if duration is None or duration <= 0:
        print(
            f"Error: could not determine the duration of {video_path}. "
            f"Pass --end <seconds> explicitly to bound the extraction window.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Source fps from r_frame_rate like "30/1".
    fps = None
    rate = stream.get("r_frame_rate", "")
    if "/" in rate:
        num, _, den = rate.partition("/")
        try:
            den_f = float(den)
            if den_f:
                fps = float(num) / den_f
        except ValueError:
            fps = None

    return {
        "duration": round(duration, 3),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "fps": round(fps, 3) if fps else None,
        "codec": stream.get("codec_name"),
    }


def drawtext_available() -> bool:
    """True if this ffmpeg build includes the drawtext filter."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and any(
        line.split()[1:2] == ["drawtext"]
        for line in result.stdout.splitlines()
        if len(line.split()) >= 2
    )


def find_font(explicit: str | None = None) -> str | None:
    """Return a usable font file path for the overlay, or None."""
    if explicit:
        return explicit if Path(explicit).is_file() else None
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def fit_sampling(window_dur: float, fps: float, max_frames: int) -> dict:
    """Fit a requested sample rate under a frame cap.

    Shared by extract_frames and contact_sheet so the "how many frames will
    this actually produce, and did we have to thin it" decision lives in one
    place. If the requested rate over the window would exceed max_frames, the
    rate is lowered so it fits. Returns the requested and effective fps, the
    resulting interval, an estimated frame count, and whether thinning
    happened -- callers turn that into user-facing notes.
    """
    requested = fps
    est = max(1, round(window_dur * fps))
    downsampled = False
    if est > max_frames:
        fps = max_frames / window_dur
        downsampled = True
        est = max(1, int(window_dur * fps))
    return {
        "requested_fps": requested,
        "fps": fps,
        "interval_seconds": round(1.0 / fps, 3),
        "est_frames": est,
        "downsampled": downsampled,
    }
