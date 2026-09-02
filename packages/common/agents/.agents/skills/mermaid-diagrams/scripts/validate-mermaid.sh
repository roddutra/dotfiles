#!/usr/bin/env bash
# Validate Mermaid diagrams by rendering them with mermaid-cli (mmdc).
#
# Renders every ```mermaid fence in the given Markdown files (or raw .mmd
# files) through the real Mermaid engine. A diagram that fails to parse or
# render exits non-zero with the engine's error, so this catches the syntax
# mistakes that otherwise only surface in a Markdown preview.
#
# Usage:  validate-mermaid.sh <file.md|file.mmd> [more files...]
#
# Exit codes:
#   0  all diagrams rendered successfully
#   1  one or more diagrams failed to render (see printed errors)
#   2  mmdc is not installed  -> ask the user before installing (see below)
#   3  no working browser for the renderer -> see remediation printed below
#   4  bad usage / no files given
#
# Source files are never modified: output is written to a throwaway temp dir.

set -uo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: validate-mermaid.sh <file.md|file.mmd> [more files...]" >&2
  exit 4
fi

# 1. Is mmdc available?
if ! command -v mmdc >/dev/null 2>&1; then
  cat >&2 <<'EOF'
mmdc (mermaid-cli) is not installed, so diagrams cannot be validated.

Don't silently skip validation. Get it available per your own environment's
rules for installing software - if your harness authorises you to install
packages, do so; otherwise ask the user. Options:
  npm install -g @mermaid-js/mermaid-cli      # persistent
  npx -y @mermaid-js/mermaid-cli -i <file>    # one-off, downloads on first use
EOF
  exit 2
fi

# 2. Resolve a browser for the renderer. Honour an explicit override first,
#    otherwise probe common locations. mmdc's bundled puppeteer often points
#    at a Chrome build that was never extracted, so we pick a known-good one.
resolve_browser() {
  if [ -n "${PUPPETEER_EXECUTABLE_PATH:-}" ] && [ -x "$PUPPETEER_EXECUTABLE_PATH" ]; then
    printf '%s' "$PUPPETEER_EXECUTABLE_PATH"; return 0
  fi
  local c
  for c in \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    "/Applications/Chromium.app/Contents/MacOS/Chromium" \
    "$(command -v google-chrome-stable 2>/dev/null)" \
    "$(command -v google-chrome 2>/dev/null)" \
    "$(command -v chromium 2>/dev/null)"; do
    [ -n "$c" ] && [ -x "$c" ] && { printf '%s' "$c"; return 0; }
  done
  # Newest extracted puppeteer chrome-headless-shell, then chrome-for-testing.
  local f
  f=$(find "${HOME}/.cache/puppeteer/chrome-headless-shell" -name chrome-headless-shell -type f 2>/dev/null | sort -V | tail -1)
  [ -n "$f" ] && { printf '%s' "$f"; return 0; }
  f=$(find "${HOME}/.cache/puppeteer/chrome" -name 'Google Chrome for Testing' -type f 2>/dev/null | sort -V | tail -1)
  [ -n "$f" ] && { printf '%s' "$f"; return 0; }
  return 1
}

BROWSER=$(resolve_browser || true)
[ -n "$BROWSER" ] && export PUPPETEER_EXECUTABLE_PATH="$BROWSER"

TMPDIR_V=$(mktemp -d)
trap 'rm -rf "$TMPDIR_V"' EXIT

failed=0
browser_error=0
for f in "$@"; do
  if [ ! -f "$f" ]; then
    echo "SKIP  $f (not a file)" >&2
    failed=1
    continue
  fi
  case "$f" in
    *.md|*.markdown) out="$TMPDIR_V/out.md" ;;
    *)               out="$TMPDIR_V/out.svg" ;;
  esac
  log=$(mmdc --quiet -i "$f" -o "$out" 2>&1)
  status=$?
  if [ "$status" -eq 0 ]; then
    echo "OK    $f"
  else
    echo "FAIL  $f"
    echo "$log" | grep -iE 'error|expecting|parse' | head -6 | sed 's/^/      /'
    if echo "$log" | grep -qiE 'could not find chrome|failed to launch|dlopen'; then
      browser_error=1
    fi
    failed=1
  fi
done

if [ "$browser_error" -eq 1 ]; then
  cat >&2 <<'EOF'

The Mermaid renderer could not start a browser. Install one for puppeteer:
  npx puppeteer browsers install chrome-headless-shell
or point it at an existing browser:
  export PUPPETEER_EXECUTABLE_PATH="/path/to/chrome"
EOF
  exit 3
fi

exit "$failed"
