# shellcheck shell=sh
# Shared helpers for the 1Password approval alerts: the op-approval-blocked
# skill scripts and the approval watcher source this file.
#
# Usage:  . "$OPA_LIB_DIR/common.sh"    (POSIX sh, set -eu friendly)
#
# Provides (all prefixed opa_):
#   paths        OPA_CONFIG_FILE, OPA_RUNTIME_DIR, OPA_STATE_DIR, OPA_TOKEN_FILE
#   config       opa_config_load, opa_cfg KEY.PATH, opa_cfg_has_state LIST STATE,
#                opa_machine, opa_project_alias BASENAME
#   labels       opa_sanitise TEXT, opa_sanitise_location TEXT, opa_is_harness NAME
#   time         opa_now, opa_iso_now
#   presence     opa_presence_read
#   files/lock   opa_ensure_dir DIR, opa_write_atomic FILE TEXT, opa_random N,
#                opa_lock_acquire, opa_lock_release
#
# Machine-local configuration lives in
# ${XDG_CONFIG_HOME:-$HOME/.config}/op-approval/config.json. It has no defaults
# for the ntfy server: without one, nothing is ever published.

umask 077

: "${HOME:?HOME is not set}"

OPA_CONFIG_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/op-approval/config.json"
# shellcheck disable=SC2034 # used by the scripts that source this file
OPA_STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/op-approval"
# shellcheck disable=SC2034
OPA_TOKEN_FILE="${XDG_DATA_HOME:-$HOME/.local/share}/op-approval/secrets/ntfy-token"
if [ -n "${XDG_RUNTIME_DIR:-}" ]; then
  OPA_RUNTIME_DIR="$XDG_RUNTIME_DIR/op-approval"
else
  OPA_RUNTIME_DIR="${TMPDIR:-/tmp}"
  OPA_RUNTIME_DIR="${OPA_RUNTIME_DIR%/}/op-approval-$(id -u)"
fi

# Seconds after which the presence feed counts as stale.
OPA_PRESENCE_MAX_AGE=30
# Longest wait for the watcher to confirm or discard held activity.
OPA_PENDING_WAIT_SECONDS=7
# Lock: give up waiting for a live holder after this many 0.1 s attempts.
OPA_LOCK_ATTEMPTS=50


opa_warn() {
  printf 'op-approval: %s\n' "$*" >&2
}

# ---------------------------------------------------------------------------
# Labels

# Keep only [A-Za-z0-9 ._:/@+-], turn whitespace into single spaces, trim and
# cap at 40 bytes. Defeats control characters, quotes, shell metacharacters and
# Unicode look-alikes; the result is always plain ASCII.
opa_sanitise() {
  _opa_clean 'A-Za-z0-9 ._:/@+-' 40 "${1-}"
}

# A location joins several sanitised labels with ", ": the same allowlist plus
# the comma, capped at 160 bytes.
opa_sanitise_location() {
  _opa_clean 'A-Za-z0-9 ._:/@+,-' 160 "${1-}"
}

_opa_clean() {
  printf '%s' "$3" \
    | LC_ALL=C tr '\t\n\r' '   ' \
    | LC_ALL=C tr -cd "$1" \
    | LC_ALL=C tr -s ' ' \
    | LC_ALL=C sed 's/^ //' \
    | LC_ALL=C cut -c "1-$2" \
    | LC_ALL=C sed 's/ $//'
}

# True only for one exact harness name from the allowlist.
opa_is_harness() {
  case "${1-}" in
    claude | codex | pi | omp | opencode | grok) return 0 ;;
    *) return 1 ;;
  esac
}

# ---------------------------------------------------------------------------
# Time

opa_now() {
  date +%s
}

# ISO 8601 local time with a colon in the offset, e.g. 2026-10-07T14:03:09+10:00.
opa_iso_now() {
  date +%Y-%m-%dT%H:%M:%S%z | sed 's/\([+-][0-9][0-9]\)\([0-9][0-9]\)$/\1:\2/'
}

# ---------------------------------------------------------------------------
# Configuration

# Validates every known key; an invalid value falls back to its default with a
# warning. Unknown keys are ignored.
# shellcheck disable=SC2016 # a jq program, not shell
OPA_CONFIG_JQ='
def field($p; f; $d):
  (try getpath($p) catch {"__opa_invalid__": true}) as $v
  | if $v == null then {path: $p, value: $d}
    elif ($v | f) then {path: $p, value: $v}
    else {path: $p, value: $d, warning: ("invalid " + ($p | join(".")) + " in config.json, using the default")}
    end;
def posint: type == "number" and . == floor and . >= 1;
def nonneg: type == "number" and . == floor and . >= 0;
def state: . == "present" or . == "idle" or . == "away" or . == "locked" or . == "unknown";
(if length == 0 then {raw: {}, warning: null}
 elif length > 1 then {raw: {}, warning: "config.json holds more than one JSON value, using the defaults"}
 elif (.[0] | type) != "object" then {raw: {}, warning: "config.json is not a JSON object, using the defaults"}
 else {raw: .[0], warning: null} end) as $in
| $in.raw
| [ field(["machine"]; type == "string" and length > 0; null),
    field(["ntfy", "url"]; type == "string" and test("^https?://[A-Za-z0-9.-]+(:[0-9]+)?(/[A-Za-z0-9._~/-]*)?$"); null),
    field(["ntfy", "topic"]; type == "string" and test("^[A-Za-z0-9_-]{1,64}$"); null),
    field(["project_aliases"]; type == "object" and all(.[]; type == "string"); {}),
    field(["alerts", "when"]; . == "expired" or . == "stopped"; "expired"),
    field(["alerts", "presence_states"]; type == "array" and all(.[]; state); ["idle", "away", "locked", "unknown"]),
    field(["alerts", "once_per_absence"]; type == "boolean"; true),
    field(["alerts", "rate_limit_seconds"]; nonneg; 300),
    field(["presence", "present_seconds"]; posint; 60),
    field(["presence", "away_seconds"]; posint; 300),
    field(["watcher", "fallback"]; type == "boolean"; true),
    field(["watcher", "fallback_grace_seconds"]; nonneg; 120),
    field(["watcher", "expired_min_seconds"]; posint; 59),
    field(["watcher", "confirm_seconds"]; type == "number" and . > 0; 1)
  ] as $fields
| { config: (reduce $fields[] as $f ({}; setpath($f.path; $f.value))),
    warnings: ([$in.warning // empty] + [$fields[] | .warning // empty]) }
'

OPA_CFG=''

# Loads and validates the config once per process. Warnings go to stderr,
# unless OPA_CONFIG_WARNED is set (a parent script already printed them).
opa_config_load() {
  [ -z "$OPA_CFG" ] || return 0
  _opa_loaded=''
  if [ -f "$OPA_CONFIG_FILE" ]; then
    if ! _opa_loaded=$(jq -cs "$OPA_CONFIG_JQ" "$OPA_CONFIG_FILE" 2>/dev/null); then
      _opa_loaded=''
      [ -n "${OPA_CONFIG_WARNED:-}" ] || opa_warn "config.json is not valid JSON, using the defaults"
    fi
  fi
  [ -n "$_opa_loaded" ] || _opa_loaded=$(printf '' | jq -cs "$OPA_CONFIG_JQ")
  if [ -z "${OPA_CONFIG_WARNED:-}" ]; then
    printf '%s\n' "$_opa_loaded" | jq -r '.warnings[]' | while IFS= read -r _opa_w; do
      opa_warn "$_opa_w"
    done
  fi
  OPA_CFG=$(printf '%s\n' "$_opa_loaded" | jq -c '.config')
}

# Prints a config value by dotted path: strings raw, arrays and objects as
# compact JSON, nothing for null.
opa_cfg() {
  opa_config_load
  printf '%s\n' "$OPA_CFG" | jq -r --arg p "$1" '
    getpath($p | split("."))
    | if . == null then empty
      elif type == "array" or type == "object" then tojson
      else tostring end'
}

# True when STATE is in the configured list at dotted path LIST.
opa_cfg_has_state() {
  opa_config_load
  printf '%s\n' "$OPA_CFG" | jq -e --arg p "$1" --arg s "$2" \
    'getpath($p | split(".")) | index([$s]) != null' >/dev/null
}

# Machine label: config "machine", else the hostname. Always sanitised.
opa_machine() {
  _opa_m=$(opa_sanitise "$(opa_cfg machine)")
  if [ -z "$_opa_m" ]; then
    _opa_m=$(opa_sanitise "$(hostname 2>/dev/null || uname -n)")
  fi
  printf '%s\n' "${_opa_m:-unknown}"
}

# Project label: the configured alias for BASENAME, else BASENAME. Sanitised.
opa_project_alias() {
  opa_config_load
  _opa_alias=$(printf '%s\n' "$OPA_CFG" | jq -r --arg b "$1" '.project_aliases[$b] // empty')
  if [ -n "$_opa_alias" ]; then
    opa_sanitise "$_opa_alias"
  else
    opa_sanitise "$1"
  fi
}

# ---------------------------------------------------------------------------
# Presence feed

# Reads ${OPA_RUNTIME_DIR}/presence.json, written by the watcher, and prints
# {"fresh":bool,"state":..,"reason":..|null,"last_present_at":N,
#  "activity_pending_until":N|null}. The feed is fresh when it is one JSON
# object with a known state and a timestamp (updated_epoch, else updated_at as
# epoch or ISO 8601 with an offset) no more than OPA_PRESENCE_MAX_AGE seconds
# old and not in the future.
#
# activity_pending_until (optional, epoch seconds) is present while the watcher
# holds input it has not yet confirmed as Rod's (activity right after a window
# closes can be synthetic); the watcher removes it once it decides, which can
# be shortly after that time. While the marker is present the state may still
# turn to present, whatever its value, so readers about to alert wait for it
# to go (opa_presence_wait_settled) and the claim refuses while it is there.
# shellcheck disable=SC2016 # a jq program, not shell
OPA_PRESENCE_JQ='
def iso_epoch:
  (capture("^(?<b>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?<f>[.][0-9]+)?(?<z>Z|[+-][0-9]{2}:?[0-9]{2})$") // null) as $m
  | if $m == null then null
    else
      (try (($m.b + "Z") | fromdateiso8601) catch null) as $base
      | if $base == null then null
        elif $m.z == "Z" then $base
        else
          ($m.z[1:3] | tonumber) as $hh
          | ($m.z[-2:] | tonumber) as $mm
          | (if $m.z[0:1] == "-" then -1 else 1 end) as $sign
          | $base - $sign * ($hh * 3600 + $mm * 60)
        end
    end;
def epoch_of:
  if type == "number" then floor
  elif type == "string" then (if test("^[0-9]+$") then tonumber else iso_epoch end)
  else null end;
def known: . == "present" or . == "idle" or . == "away" or . == "locked" or . == "unknown";
def unknown($r): {fresh: false, state: "unknown", reason: $r, last_present_at: 0, activity_pending_until: null};
if length != 1 or (.[0] | type) != "object" then unknown("presence feed is malformed")
else
  .[0] as $p
  | (if ($p.updated_epoch | type) == "number" then ($p.updated_epoch | floor) else ($p.updated_at | epoch_of) end) as $u
  | if $u == null then unknown("presence feed has no valid timestamp")
    elif $u > $now then unknown("presence feed timestamp is in the future")
    elif ($now - $u) > $max then unknown("presence feed is stale")
    elif ($p.state | known | not) then unknown("presence feed has an invalid state")
    else
      { fresh: true,
        state: $p.state,
        reason: (if $p.state == "unknown" then "watcher reports unknown" else null end),
        last_present_at: (if ($p.last_present_at | type) == "number"
                          then ([($p.last_present_at | floor), $now] | min) else 0 end),
        activity_pending_until: (if ($p.activity_pending_until | type) == "number"
                                 then ($p.activity_pending_until | ceil) else null end) }
    end
end
'

opa_presence_read() {
  _opa_feed="$OPA_RUNTIME_DIR/presence.json"
  _opa_now=$(opa_now)
  if [ ! -e "$_opa_feed" ]; then
    if [ -n "${XDG_RUNTIME_DIR:-}" ]; then
      _opa_reason="no presence feed (watcher not running)"
    else
      _opa_reason="no presence feed (XDG_RUNTIME_DIR is not set)"
    fi
    jq -nc --arg r "$_opa_reason" '{fresh: false, state: "unknown", reason: $r, last_present_at: 0, activity_pending_until: null}'
    return 0
  fi
  if [ ! -r "$_opa_feed" ] || ! _opa_out=$(jq -cs --argjson now "$_opa_now" \
      --argjson max "$OPA_PRESENCE_MAX_AGE" "$OPA_PRESENCE_JQ" "$_opa_feed" 2>/dev/null); then
    _opa_out=$(jq -nc '{fresh: false, state: "unknown", reason: "presence feed is unreadable or malformed", last_present_at: 0, activity_pending_until: null}')
  fi
  printf '%s\n' "$_opa_out"
}

# True when PRESENCE (output of opa_presence_read) is fresh and still carries
# the activity_pending_until marker, even if its time has passed: only the
# watcher removing it means the held activity was decided.
opa_presence_pending() {
  printf '%s\n' "$1" | jq -e '.fresh and (.activity_pending_until | type) == "number"' >/dev/null
}

# Waits, for at most OPA_PENDING_WAIT_SECONDS, until the fresh feed no longer
# carries the activity_pending_until marker, then prints the presence read
# last. Never call it while holding the lock.
opa_presence_wait_settled() {
  _opa_waited=0
  _opa_p=$(opa_presence_read)
  while opa_presence_pending "$_opa_p" && [ "$_opa_waited" -lt "$OPA_PENDING_WAIT_SECONDS" ]; do
    sleep 1
    _opa_waited=$((_opa_waited + 1))
    _opa_p=$(opa_presence_read)
  done
  printf '%s\n' "$_opa_p"
}

# ---------------------------------------------------------------------------
# Files and lock

# Creates DIR (and parents) with mode 700, refusing a symlink or a directory
# owned by someone else (the /tmp fallback is shared).
opa_ensure_dir() {
  if [ -L "$1" ]; then
    opa_warn "refusing to use $1: it is a symlink"
    return 1
  fi
  if [ ! -d "$1" ]; then
    { mkdir -p -- "$(dirname -- "$1")" && mkdir -m 700 -- "$1"; } 2>/dev/null || [ -d "$1" ] || {
      opa_warn "cannot create $1"
      return 1
    }
  fi
  # POSIX test has no -O; ls -n prints the numeric owner.
  # shellcheck disable=SC2012
  if [ "$(ls -ldn -- "$1" | awk '{ print $3 }')" != "$(id -u)" ]; then
    opa_warn "refusing to use $1: owned by another user"
    return 1
  fi
  chmod 700 "$1" 2>/dev/null || true
}

# Writes TEXT and a newline to FILE through a temporary file and rename.
opa_write_atomic() {
  _opa_tmp="$1.tmp.$$"
  if printf '%s\n' "$2" >"$_opa_tmp" && mv -f "$_opa_tmp" "$1"; then
    return 0
  fi
  rm -f "$_opa_tmp"
  return 1
}

# The lock is a symlink whose target is the holder's owner record,
# "PID NONCE START" (START: the holder's process start time). Creating a
# symlink is atomic and fails if it exists, so the record exists from the
# instant the lock does. lock.d from an earlier version is ignored.
OPA_LOCK="$OPA_RUNTIME_DIR/lock"
OPA_LOCK_BREAKER="$OPA_RUNTIME_DIR/lock.break"
OPA_LOCK_RECORD=''

# Prints N random characters from [a-z0-9].
opa_random() {
  LC_ALL=C tr -dc 'a-z0-9' </dev/urandom 2>/dev/null | dd bs=1 count="$1" 2>/dev/null || true
}

_opa_sleep_briefly() {
  sleep 0.1 2>/dev/null || sleep 1
}

# Prints when process PID started (clock ticks since boot from /proc, else
# ps lstart), or nothing if that cannot be found. Tells a reused PID apart.
_opa_proc_start() {
  if [ -r "/proc/$1/stat" ]; then
    sed 's/^.*) //' "/proc/$1/stat" 2>/dev/null | awk '{ print $20 }'
  else
    ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ' | sed 's/^ //; s/ $//'
  fi
}

# Prints the current owner record, or nothing if there is no lock.
_opa_lock_owner() {
  [ -L "$OPA_LOCK" ] || return 0
  if command -v readlink >/dev/null 2>&1; then
    readlink "$OPA_LOCK" 2>/dev/null || true
  else
    # shellcheck disable=SC2012 # no readlink: ls -l prints "lock -> target"
    ls -l "$OPA_LOCK" 2>/dev/null | sed 's/^.* -> //'
  fi
}

# A live holder is never evicted, however long it holds the lock: a record
# is stale only when its PID is not running, or is running with a different
# start time (the PID was reused). A record that cannot be parsed is never
# stale.
_opa_lock_is_stale() {
  _opa_r_pid=''
  _opa_r_nonce=''
  _opa_r_start=''
  read -r _opa_r_pid _opa_r_nonce _opa_r_start <<EOF
$1
EOF
  case "$_opa_r_pid" in
    '' | *[!0-9]*) return 1 ;;
  esac
  [ -n "$_opa_r_nonce" ] || return 1
  kill -0 "$_opa_r_pid" 2>/dev/null || return 0
  [ -n "$_opa_r_start" ] || return 1
  _opa_r_now=$(_opa_proc_start "$_opa_r_pid")
  [ -n "$_opa_r_now" ] && [ "$_opa_r_now" != "$_opa_r_start" ]
}

# Removes the lock if it still carries RECORD, the record judged stale, and
# that record is still stale. The breaker directory keeps recoverers out of
# each other's way, and a dead holder cannot release, so nobody can replace
# the lock between this check and the removal.
_opa_lock_break() {
  mkdir "$OPA_LOCK_BREAKER" 2>/dev/null || return 0
  _opa_current=$(_opa_lock_owner)
  if [ -n "$_opa_current" ] && [ "$_opa_current" = "$1" ] && _opa_lock_is_stale "$_opa_current"; then
    rm -f "$OPA_LOCK"
  fi
  rmdir "$OPA_LOCK_BREAKER" 2>/dev/null || true
}

# Takes the per-user lock. Waits up to about 5 s for a live holder, recovers
# a stale lock, and releases it on exit or on a signal. Returns 1 with a
# warning if it cannot; the caller must then not alert.
opa_lock_acquire() {
  opa_ensure_dir "$OPA_RUNTIME_DIR" || return 1
  if [ -e "$OPA_LOCK" ] && [ ! -L "$OPA_LOCK" ]; then
    opa_warn "$OPA_LOCK is not a symlink; remove it if no op-approval script is running"
    return 1
  fi
  _opa_nonce=$(opa_random 8)
  [ -n "$_opa_nonce" ] || _opa_nonce=$$
  _opa_record="$$ $_opa_nonce"
  _opa_start=$(_opa_proc_start "$$")
  [ -z "$_opa_start" ] || _opa_record="$_opa_record $_opa_start"
  _opa_tries=0
  while ! ln -s "$_opa_record" "$OPA_LOCK" 2>/dev/null; do
    _opa_seen=$(_opa_lock_owner)
    if [ -n "$_opa_seen" ] && _opa_lock_is_stale "$_opa_seen"; then
      _opa_lock_break "$_opa_seen"
      [ -L "$OPA_LOCK" ] || continue
    fi
    _opa_tries=$((_opa_tries + 1))
    if [ "$_opa_tries" -ge "$OPA_LOCK_ATTEMPTS" ]; then
      if [ -d "$OPA_LOCK_BREAKER" ]; then
        opa_warn "stale lock recovery is blocked by $OPA_LOCK_BREAKER; remove it if no op-approval script is running"
      else
        opa_warn "timed out waiting for the lock $OPA_LOCK, held by another process"
      fi
      return 1
    fi
    _opa_sleep_briefly
  done
  OPA_LOCK_RECORD=$_opa_record
  trap 'opa_lock_release' EXIT
  trap 'opa_lock_release; exit 129' HUP
  trap 'opa_lock_release; exit 130' INT
  trap 'opa_lock_release; exit 143' TERM
}

# Releases the lock only if it still carries this process's owner record.
opa_lock_release() {
  [ -n "$OPA_LOCK_RECORD" ] || return 0
  if [ "$(_opa_lock_owner)" = "$OPA_LOCK_RECORD" ]; then
    rm -f "$OPA_LOCK"
  fi
  OPA_LOCK_RECORD=''
}
