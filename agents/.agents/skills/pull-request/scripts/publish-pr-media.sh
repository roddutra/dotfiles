#!/usr/bin/env bash
# Publish local media files as GitHub release assets and print inline-ready URLs
# for embedding in a pull request body.
#
# Usage: publish-pr-media.sh <file> [<file> ...]
#   Env: PR_MEDIA_TAG (default "pr-assets") - the holding prerelease tag.
#
# Requires an authenticated gh CLI and a git repo with a GitHub remote. Uploads
# each file to a dedicated prerelease (created once if missing), namespaced by
# branch so concurrent PRs don't collide, and prints one embeddable URL per file.
# Re-running clobbers the same asset name, so it is safe to iterate.
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: $0 <file> [<file> ...]" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  cat >&2 <<'EOF'
gh (GitHub CLI) is not installed, and it's required to host PR media as release
assets. This script will NOT install it automatically.

Install it, then re-run:
  macOS (Homebrew):      brew install gh
  Debian / Ubuntu:       sudo apt-get install -y gh   # see cli.github.com for the apt repo
  Fedora:                sudo dnf install -y gh
  Arch:                  sudo pacman -S github-cli
  Windows (winget):      winget install --id GitHub.cli -e
Then authenticate: gh auth login
EOF
  exit 3
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "gh is installed but not authenticated. Run: gh auth login" >&2
  exit 4
fi

TAG="${PR_MEDIA_TAG:-pr-assets}"
repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
branch="$(git rev-parse --abbrev-ref HEAD | tr '/ ' '__')"

# Create the holding prerelease once. Prerelease (not draft) so asset URLs resolve
# for anyone who can view the repo.
if ! gh release view "$TAG" >/dev/null 2>&1; then
  gh release create "$TAG" \
    --title "PR media assets" \
    --notes "Auto-uploaded screenshots and clips referenced in pull request descriptions." \
    --prerelease >/dev/null
fi

for f in "$@"; do
  [ -f "$f" ] || { echo "not a file: $f" >&2; exit 1; }
  base="$(basename "$f")"
  asset="${branch}__${base}"

  # gh uses the on-disk filename as the asset name, so stage a namespaced copy.
  tmp="$(dirname "$f")/$asset"
  if [ "$tmp" != "$f" ]; then cp "$f" "$tmp"; fi
  gh release upload "$TAG" "$tmp" --clobber >/dev/null
  [ "$tmp" != "$f" ] && rm -f "$tmp"

  echo "https://github.com/${repo}/releases/download/${TAG}/${asset}"
done
