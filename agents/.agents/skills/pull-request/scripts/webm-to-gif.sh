#!/usr/bin/env bash
# Convert a screen recording to a compact animated asset for inline PR embedding.
#
# Usage: webm-to-gif.sh <input.webm> [output.gif|output.webp]
#   Default output is <input>.gif. Pass a .webp name for a smaller file.
#   Env: FPS (default 12), WIDTH (default 960).
#
# Requires ffmpeg. If ffmpeg is missing, this prints per-OS install guidance and
# exits 3 WITHOUT installing anything - the caller should surface the guidance and
# ask the user for permission before installing.
set -euo pipefail

if ! command -v ffmpeg >/dev/null 2>&1; then
  cat >&2 <<'EOF'
ffmpeg is not installed, and it's required to convert the recording into an
inline GIF/WebP for the PR. This script will NOT install it automatically.

Install it, then re-run:
  macOS (Homebrew):      brew install ffmpeg
  Debian / Ubuntu:       sudo apt-get update && sudo apt-get install -y ffmpeg
  Fedora:                sudo dnf install -y ffmpeg
  Arch:                  sudo pacman -S ffmpeg
  Windows (winget):      winget install --id Gyan.FFmpeg -e
  Windows (Chocolatey):  choco install ffmpeg

Alternatively, skip the recording: attach before/after screenshots instead, or
embed the raw clip as a link in the PR body.
EOF
  exit 3
fi

in="${1:?usage: webm-to-gif.sh <input.webm> [output.gif|output.webp]}"
[ -f "$in" ] || { echo "not a file: $in" >&2; exit 1; }
out="${2:-${in%.*}.gif}"
fps="${FPS:-12}"
width="${WIDTH:-960}"

case "$out" in
  *.webp)
    ffmpeg -y -i "$in" \
      -vf "fps=${fps},scale=${width}:-1:flags=lanczos" \
      -c:v libwebp -lossless 0 -q:v 55 -loop 0 -an "$out" >/dev/null 2>&1
    ;;
  *)
    # Two-pass palette for a clean GIF at a reasonable size.
    palette="$(dirname "$out")/.pr-palette.png"
    ffmpeg -y -i "$in" \
      -vf "fps=${fps},scale=${width}:-1:flags=lanczos,palettegen" "$palette" >/dev/null 2>&1
    ffmpeg -y -i "$in" -i "$palette" \
      -lavfi "fps=${fps},scale=${width}:-1:flags=lanczos[x];[x][1:v]paletteuse" "$out" >/dev/null 2>&1
    rm -f "$palette"
    ;;
esac

echo "$out"
