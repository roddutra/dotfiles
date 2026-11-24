#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Open Omarchy Screens
# @raycast.mode silent
# @raycast.packageName screen-relay
# @raycast.icon 🖥️
# @raycast.description Open a screen-relay viewer tab for each Omarchy monitor that is on.

# The links come from Omarchy over SSH (the `omarchy` host in ~/.ssh/config,
# so 1Password may ask to approve the key) and only sessions that are running
# are returned. See docs/screen-relay.md.
set -uo pipefail

if ! output=$("$HOME/.local/bin/screen-relay-open" --print --all omarchy 2>&1); then
  echo "Omarchy screens: ${output##*$'\n'}"
  exit 1
fi

count=0
while IFS= read -r link; do
  [[ $link == http* ]] || continue
  open "$link"
  count=$((count + 1))
done <<<"$output"

if ((count == 0)); then
  echo "Omarchy screens: no monitor is on"
  exit 1
fi
echo "Opened $count Omarchy screen$([[ $count == 1 ]] || echo s)"
