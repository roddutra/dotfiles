#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash). Denies direct `codex` CLI invocations so
# Codex can only run through the codex-reviewer skill's wrapper scripts.
#
# Matches `codex` in command position: start of line/command, or after
# ; & | $( or backtick, optionally path-prefixed (e.g. /opt/homebrew/bin/codex).
# Does NOT match paths like ~/.codex-reviews/... or the word Codex in prose.

cmd=$(jq -r '.tool_input.command // ""')

if printf '%s\n' "$cmd" | grep -qE '(^|[;&|]|\$\(|`)[[:space:]]*([A-Za-z0-9_./~-]*/)?codex([[:space:]]|$)'; then
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Direct codex CLI invocations are blocked. Load the codex-reviewer skill and use its wrapper scripts to run Codex."}}
JSON
fi

exit 0
