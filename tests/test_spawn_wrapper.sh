#!/usr/bin/env bash
# A2A_SPAWN_WRAPPER must wrap every launch. Uses fake CLIs: no model is called.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/home/.local/bin" "$T/bin"
fake() { printf '#!/bin/sh\nprintf "%%s\\n" "%s" "$@" >"%s/ran"\n' "$2" "$T" >"$1"; chmod +x "$1"; }
fake "$T/home/.local/bin/claude" claude
fake "$T/bin/pi" pi
fake "$T/bin/opencode-bin" opencode
printf '#!/bin/sh\necho "$@" >>"%s/wrapped"\nshift 2\nexec "$@"\n' "$T" >"$T/bin/wrap"; chmod +x "$T/bin/wrap"
echo "kit with  spaces; \$(not run) 'quotes'" >"$T/kit"
fails=0
check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fails=$((fails+1)); fi; }
settle() { for _ in $(seq 100); do [ -s "$T/ran" ] && break; sleep 0.05; done; sleep 0.1; }
run() { env -i HOME="$T/home" PATH="$T/bin:/usr/bin:/bin" "$@"; }

for cli in claude pi opencode; do
    rm -f "$T/ran" "$T/wrapped"
    pid=$(run A2A_SPAWN_WRAPPER="$T/bin/wrap harness-exec --" "$HERE/a2a-spawn" --cli $cli --id t --kit-file "$T/kit" --log "$T/log"); settle
    check "$cli: prints a PID" '[[ "$pid" =~ ^[0-9]+$ ]]'
    check "$cli: launched through the wrapper" 'grep -q "^harness-exec -- " "$T/wrapped" 2>/dev/null'
    check "$cli: agent ran with the kit intact" 'grep -qF "kit with  spaces; \$(not run) '"'"'quotes'"'"'" "$T/ran"'

    rm -f "$T/ran" "$T/wrapped"
    run "$HERE/a2a-spawn" --cli $cli --id t --kit-file "$T/kit" --log "$T/log" >/dev/null; settle
    check "$cli: no wrapper when unset" '[ -s "$T/ran" ] && [ ! -e "$T/wrapped" ]'

    rm -f "$T/ran"
    run A2A_SPAWN_WRAPPER="$T/bin/missing harness-exec --" "$HERE/a2a-spawn" --cli $cli --id t --kit-file "$T/kit" --log "$T/log" >/dev/null; sleep 0.5
    check "$cli: a broken wrapper never falls back to a bare launch" '[ ! -e "$T/ran" ]'
done
check "help advertises the variable" '"$HERE/a2a-spawn" --help | grep -q A2A_SPAWN_WRAPPER'
direct=$(grep -cE '^\s*(A2A_PROJECT="\$PROJECT" |CURSOR_API_KEY="\$CURSOR_API_KEY" )?nohup ' "$HERE/a2a-spawn")
check "only _spawn_bg uses nohup" '[ "$direct" = 2 ]'
[ $fails = 0 ] && echo "all passed" || { echo "$fails failed"; exit 1; }
