# shellcheck shell=sh disable=SC2154 # chain and start_pid are set by locate
# macOS parts of `locate`, sourced by it. Read-only, and no privacy
# permission is needed: process facts come from ps and lsof.
#
#   opa_proc_cwd PID          working directory of PID
#   opa_proc_env PID NAME     exits 2: another process's environment is not
#                             readable on macOS
#   opa_app_part              the app the agent runs in, from the ancestry of
#                             $start_pid, or past a multiplexer server (the
#                             last process in $chain) from an attached
#                             client's ancestry

opa_proc_cwd() {
  [ -n "$1" ] || return 1
  lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | sed -n 1p | grep .
}

opa_proc_env() {
  return 2
}

# Display name of the first .app bundle in PID's ancestry, or nothing.
# Bundles inside frameworks (Homebrew's Python.app) are runtimes, not apps.
_opa_app_of_ancestry() {
  _opa_p=$1
  _opa_depth=0
  while [ "$_opa_p" -gt 1 ] 2>/dev/null && [ "$_opa_depth" -lt 64 ]; do
    _opa_exe=$(ps -o comm= -p "$_opa_p" 2>/dev/null) || return 1
    case "$_opa_exe" in
      *.framework/*) ;;
      *.app/*)
        _opa_bundle=${_opa_exe%%.app/*}.app
        _opa_plist=$_opa_bundle/Contents/Info.plist
        _opa_name=$(plutil -extract CFBundleDisplayName raw -o - "$_opa_plist" 2>/dev/null) \
          || _opa_name=$(plutil -extract CFBundleName raw -o - "$_opa_plist" 2>/dev/null) \
          || _opa_name=${_opa_bundle##*/}
        printf '%s\n' "${_opa_name%.app}"
        return 0
        ;;
    esac
    _opa_p=$(ps -o ppid= -p "$_opa_p" 2>/dev/null | tr -d ' ') || return 1
    _opa_depth=$((_opa_depth + 1))
  done
  return 1
}

# PIDs of processes connected to a Unix socket that PID holds: a client's
# peer address equals the address of the server's end.
_opa_socket_clients() {
  lsof -U -F pdn 2>/dev/null | awk -v server="$1" '
    /^p/ { pid = substr($0, 2); next }
    /^d/ { dev = substr($0, 2); next }
    /^n/ {
      name = substr($0, 2)
      if (pid == server) own[dev] = 1
      else if (name ~ /^->0x/) peer[pid] = peer[pid] " " substr(name, 3)
    }
    END {
      for (p in peer) {
        n = split(peer[p], list, " ")
        for (i = 1; i <= n; i++) if (list[i] in own) { print p; break }
      }
    }'
}

opa_app_part() {
  if _opa_found=$(_opa_app_of_ancestry "$start_pid"); then
    printf '%s\n' "$_opa_found"
    return 0
  fi
  _opa_top=$(printf '%s' "$chain" | sed -n '$p')
  _opa_top_pid=${_opa_top%% *}
  # Multiplexer servers are re-parented to launchd, so the ancestry ends at
  # the server: use an attached client's app instead.
  case "${_opa_top#* }" in
    tmux*) _opa_clients=$(tmux list-clients -F '#{client_pid}' 2>/dev/null) || _opa_clients='' ;;
    herdr) _opa_clients=$(_opa_socket_clients "$_opa_top_pid") ;;
    *) return 0 ;;
  esac
  for _opa_client in $_opa_clients; do
    case "$_opa_client" in
      '' | *[!0-9]*) continue ;;
    esac
    if _opa_found=$(_opa_app_of_ancestry "$_opa_client"); then
      printf '%s\n' "$_opa_found"
      return 0
    fi
  done
  return 0
}
