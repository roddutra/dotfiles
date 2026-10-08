# shellcheck shell=sh disable=SC2154 # chain and start_pid are set by locate
# Linux parts of `locate`, sourced by it. Read-only: process facts come from
# /proc, the window from Hyprland.
#
#   opa_proc_cwd PID          working directory of PID
#   opa_proc_env PID NAME     NAME from PID's environment; exits 2 when the
#                             environment is not readable
#   opa_app_part              the Hyprland window of the first process in
#                             $chain that owns a client ("ws 2 Ghostty")

opa_proc_cwd() {
  [ -n "$1" ] && readlink "/proc/$1/cwd" 2>/dev/null
}

opa_proc_env() {
  [ -r "/proc/$1/environ" ] || return 2
  tr '\0' '\n' <"/proc/$1/environ" 2>/dev/null | sed -n "s/^$2=//p" | sed -n 1p
}

opa_app_part() {
  command -v hyprctl >/dev/null 2>&1 || return 0
  _opa_clients=$(hyprctl clients -j 2>/dev/null) || return 0
  _opa_pids=$(printf '%s' "$chain" | jq -Rsc '[split("\n")[] | split(" ")[0] | tonumber? ]') || return 0
  _opa_found=$(printf '%s\n' "$_opa_clients" | jq -r --argjson pids "$_opa_pids" '
    def short:
      if . == "com.mitchellh.ghostty" then "Ghostty"
      elif . == "com.anthropic.Claude" then "Claude Desktop"
      else (split(".") | map(select(length > 0)) | last // "") end;
    def line: tostring | gsub("[\\r\\n]"; " ");
    if type != "array" then empty else
      . as $c
      | (first($pids[] as $p | [$c[] | select(type == "object" and .pid == $p)] | select(length > 0)) // null) as $own
      | if $own == null then empty
        else
          (if ($own | length) == 1 then ($own[0].workspace.name // "" | line) else "" end),
          ($own[0].class // "" | line | short)
        end
    end' 2>/dev/null) || return 0
  [ -n "$_opa_found" ] || return 0
  _opa_ws=$(printf '%s\n' "$_opa_found" | sed -n 1p)
  _opa_cls=$(printf '%s\n' "$_opa_found" | sed -n 2p)
  _opa_ws=$(opa_sanitise "$_opa_ws")
  _opa_cls=$(opa_sanitise "$_opa_cls")
  if [ -n "$_opa_ws" ] && [ -n "$_opa_cls" ]; then
    printf 'ws %s %s\n' "$_opa_ws" "$_opa_cls"
  elif [ -n "$_opa_cls" ]; then
    printf '%s\n' "$_opa_cls"
  elif [ -n "$_opa_ws" ]; then
    printf 'ws %s\n' "$_opa_ws"
  fi
}
