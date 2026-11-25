#!/usr/bin/env bash
# Parse a TLA+ spec with SANY, then model-check it with TLC, and print one RESULT line.
#
# Usage: tlc.sh <Spec.tla> [--config <file.cfg>] [--only <Rule> | --each]
#               [--simulate <traces>] [-- <extra TLC flags>]
#
# The config defaults to <Spec>.cfg next to the spec.
# --only <Rule>  check one invariant or property from the config and ignore the others.
# --each         check every invariant and property on its own, so each gets its own
#                shortest counterexample. TLC otherwise stops at the first rule that breaks.
# --simulate     run random behaviours instead of an exhaustive search, for models too big to finish.
#
# Environment:
#   TLA2TOOLS_JAR  use this jar instead of downloading the pinned release
#   JAVA_HOME      use this JDK instead of java on PATH
#
# Exit status is TLC's own: 0 pass, 10 assumption failed, 11 deadlock, 12 invariant violation,
# 13 temporal property violation (an action property or liveness), 150 and above a spec,
# config or tool error. With --each: 0 when every rule holds, 1 otherwise.
# 2 means this script could not run.

set -u

TLA_VERSION="1.7.4"
TLA_SHA256="936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88"
TLA_URL="https://github.com/tlaplus/tlaplus/releases/download/v${TLA_VERSION}/tla2tools.jar"

die() {
  echo "tlc.sh: $*" >&2
  echo "RESULT: not-run (exit 2)"
  exit 2
}

spec=""
config=""
simulate=""
only=""
each=false
extra=()
while [ $# -gt 0 ]; do
  case "$1" in
    --config) [ $# -ge 2 ] || die "--config needs a file"; config="$2"; shift 2 ;;
    --simulate) [ $# -ge 2 ] || die "--simulate needs a trace count"; simulate="$2"; shift 2 ;;
    --only) [ $# -ge 2 ] || die "--only needs a rule name"; only="$2"; shift 2 ;;
    --each) each=true; shift ;;
    --) shift; extra=("$@"); break ;;
    -h|--help) sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) die "unknown option $1 (pass TLC flags after --)" ;;
    *) [ -z "$spec" ] || die "only one spec per run"; spec="$1"; shift ;;
  esac
done

[ -n "$spec" ] || die "no spec given"
[ -f "$spec" ] || die "spec not found: $spec"
case "$spec" in *.tla) ;; *) die "spec must end in .tla" ;; esac
if $each && [ -n "$only" ]; then die "use --only or --each, not both"; fi

spec_dir="$(cd "$(dirname "$spec")" && pwd)"
spec_file="$(basename "$spec")"
module="${spec_file%.tla}"

if [ -z "$config" ]; then
  config="$spec_dir/$module.cfg"
else
  config="$(cd "$(dirname "$config")" && pwd)/$(basename "$config")"
fi
[ -f "$config" ] || die "config not found: $config"

if [ -n "${JAVA_HOME:-}" ] && [ -x "$JAVA_HOME/bin/java" ]; then
  java_bin="$JAVA_HOME/bin/java"
elif command -v java >/dev/null 2>&1; then
  java_bin="$(command -v java)"
else
  die "no Java found. TLC needs Java 11 or newer on PATH or in JAVA_HOME. Ask the user before installing one."
fi

java_major="$("$java_bin" -version 2>&1 | sed -n 's/.*version "\([0-9]*\).*/\1/p' | head -n 1)"
if [ -z "$java_major" ] || [ "$java_major" -lt 11 ]; then
  die "Java 11 or newer is required, found: $("$java_bin" -version 2>&1 | head -n 1)"
fi

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

jar="${TLA2TOOLS_JAR:-}"
if [ -n "$jar" ]; then
  [ -f "$jar" ] || die "TLA2TOOLS_JAR does not exist: $jar"
else
  cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/tlaplus"
  jar="$cache_dir/tla2tools-$TLA_VERSION.jar"
  if [ ! -f "$jar" ]; then
    mkdir -p "$cache_dir" || die "cannot create $cache_dir"
    echo "tlc.sh: downloading tla2tools.jar $TLA_VERSION to $jar" >&2
    curl -fsSL -o "$jar.part" "$TLA_URL" || { rm -f "$jar.part"; die "download failed: $TLA_URL"; }
    if [ "$(sha256_of "$jar.part")" != "$TLA_SHA256" ]; then
      rm -f "$jar.part"
      die "checksum mismatch for the downloaded tla2tools.jar, nothing was installed"
    fi
    mv "$jar.part" "$jar"
  fi
fi

work="$(mktemp -d "${TMPDIR:-/tmp}/tlc-run.XXXXXX")" || die "cannot create a temp directory"
trap 'rm -rf "$work"' EXIT

# Reads a cfg. mode=list prints "<inv|prop> <Name>" for each rule.
# mode=strip prints the cfg without its INVARIANT and PROPERTY sections.
cfg_awk='
function kind_of(tok) {
  if (tok ~ /^INVARIANTS?$/) return "inv"
  if (tok ~ /^(PROPERTY|PROPERTIES)$/) return "prop"
  if (tok ~ /^(SPECIFICATION|INIT|NEXT|CONSTANTS?|CONSTRAINTS?|ACTION_CONSTRAINTS?|SYMMETRY|VIEW|ALIAS|CHECK_DEADLOCK|POSTCONDITION)$/) return "other"
  return ""
}
{
  line = $0
  sub(/\\\*.*/, "", line)
  n = split(line, t, /[ \t,]+/)
  start = 1
  while (start <= n && t[start] == "") start++
  if (start <= n) {
    k = kind_of(t[start])
    if (k != "") { section = k; start++ }
  }
  if (section == "inv" || section == "prop") {
    if (mode == "list") for (i = start; i <= n; i++) if (t[i] != "") print section, t[i]
    next
  }
  if (mode == "strip") print $0
}'

rules="$(awk -v mode=list "$cfg_awk" "$config")"

# Writes a cfg that checks only the named rule. Prints its path.
cfg_for_rule() {
  local rule="$1" kind out
  kind="$(printf '%s\n' "$rules" | awk -v r="$rule" '$2 == r { print $1; exit }')"
  [ -n "$kind" ] || return 1
  out="$work/only-$rule.cfg"
  awk -v mode=strip "$cfg_awk" "$config" > "$out"
  if [ "$kind" = "inv" ]; then
    printf '\nINVARIANT %s\n' "$rule" >> "$out"
  else
    printf '\nPROPERTY %s\n' "$rule" >> "$out"
  fi
  printf '%s\n' "$out"
}

verdict_of() {
  case "$1" in
    0) if [ -n "$simulate" ]; then echo "pass-simulation-only"; else echo "pass"; fi ;;
    10) echo "assumption-failed" ;;
    11) echo "deadlock" ;;
    12) echo "invariant-violation" ;;
    13) echo "property-violation" ;;
    150) echo "parse-error" ;;
    151) echo "config-error" ;;
    *) echo "error" ;;
  esac
}

cd "$spec_dir" || die "cannot enter $spec_dir"

echo "== SANY: $spec_file"
sany_out="$("$java_bin" -cp "$jar" tla2sany.SANY "$spec_file" 2>&1)"
sany_status=$?
if [ $sany_status -ne 0 ] || printf '%s\n' "$sany_out" | grep -Eq '^(\*\*\* (Errors|Abort)|Parse Error|Fatal errors|Lexical error|Semantic errors)'; then
  printf '%s\n' "$sany_out"
  echo "RESULT: parse-error (exit 150)"
  exit 150
fi

base_flags=(-workers auto)
if "$java_bin" -cp "$jar" tlc2.TLC -help 2>&1 | grep -q -- '-noGenerateSpecTE'; then
  base_flags+=(-noGenerateSpecTE)
fi
if [ -n "$simulate" ]; then
  base_flags+=(-simulate "num=$simulate")
fi

run_no=0
run_tlc() {
  run_no=$((run_no + 1))
  "$java_bin" -XX:+UseParallelGC -cp "$jar" tlc2.TLC "${base_flags[@]}" \
    -metadir "$work/meta-$run_no" -config "$1" ${extra[@]+"${extra[@]}"} "$spec_file"
}

if $each; then
  [ -n "$rules" ] || die "the config lists no invariants or properties"
  total=0
  broken=0
  summary=""
  while read -r kind rule; do
    total=$((total + 1))
    cfg="$(cfg_for_rule "$rule")" || die "cannot build a config for $rule"
    out="$(run_tlc "$cfg" 2>&1)"
    status=$?
    verdict="$(verdict_of $status)"
    echo "== $rule: $verdict"
    if [ $status -ne 0 ]; then
      broken=$((broken + 1))
      printf '%s\n' "$out" | sed -n '/^Error:/,$p' | grep -Ev '^(The average outdegree|Finished in)'
    else
      printf '%s\n' "$out" | grep -E 'distinct states found' | tail -n 1
    fi
    summary="$summary$(printf '%-22s %s' "$verdict" "$rule")
"
  done <<EOF
$rules
EOF
  echo "== Summary"
  printf '%s' "$summary"
  if [ $broken -eq 0 ]; then
    echo "RESULT: all $total rules hold (exit 0)"
    exit 0
  fi
  echo "RESULT: $broken of $total rules do not hold (exit 1)"
  exit 1
fi

run_config="$config"
label="$(basename "$config")"
if [ -n "$only" ]; then
  run_config="$(cfg_for_rule "$only")" || die "$only is not an invariant or property in $(basename "$config")"
  label="$label, only $only"
fi

echo "== TLC: $spec_file with $label"
run_tlc "$run_config"
status=$?
echo "RESULT: $(verdict_of $status) (exit $status)"
exit $status
