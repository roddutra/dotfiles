#!/usr/bin/env bash
# Render a Slidev deck to PNGs for visual review.
#
#   review.sh <deck.md> [extra slidev export options]
#
# Writes PNGs to exports/review/<deck>/ beside the deck, numbered by slide
# (and by click step with --with-clicks), and, when ImageMagick is installed,
# labelled contact sheets of up to nine images each (sheet-0.png, ...).
# Pass --range 3-5 to render part of the deck.
set -euo pipefail

deck=${1:?usage: review.sh <deck.md> [extra slidev export options]}
shift
[[ -f "$deck" ]] || { printf 'No such deck: %s\n' "$deck" >&2; exit 1; }

cd "$(dirname "$deck")"
name=$(basename "$deck" .md)
out=exports/review/$name
[[ -d node_modules/@slidev/cli ]] || { printf 'Dependencies are missing. Install them in %s first.\n' "$PWD" >&2; exit 1; }

# The browser download is skipped by pnpm's build-script policy; this is a
# no-op once the matching browser is in the Playwright cache.
npx --no-install playwright install chromium-headless-shell > /dev/null

# Drop headless Chrome noise that does not affect the output: FloatingVue and
# Wake Lock errors, with their stack traces.
quiet() {
  awk '/Failed to patch FloatingVue|Wake Lock permission/ { skip = 1; next }
       skip && /^[[:space:]]+at / { next }
       { skip = 0; print }'
}

rm -rf "$out"
npx --no-install slidev export "$name.md" --format png --output "$out" "$@" 2>&1 | quiet

if command -v magick > /dev/null; then
  magick montage -label '%t' "$out"/*.png -tile 3x3 -geometry 640x360+8+8 \
    -background '#808080' "$out/sheet-%d.png"
fi

ls "$out"
