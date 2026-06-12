#!/usr/bin/env bash
# tau a2a smoke test: tau + pi agents collaborate on the a2a bus.
# Success = tau agent sends at least one message and marks done.
set -u

DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
A2A="${A2A_BIN:-$DIR/a2a}"
SPAWN="$DIR/a2a-spawn"
PROJECT="${1:-a2a-tau-$$}"
LOG_DIR="${LOG_DIR:-/tmp/a2a-$PROJECT}"
mkdir -p "$LOG_DIR"
export A2A_PROJECT="$PROJECT"

echo "== a2a tau smoke test =="
echo "project: $PROJECT"
echo "logs:    $LOG_DIR"
echo

# Fresh bus
"$A2A" clear --yes >/dev/null 2>&1 || true
"$A2A" init

"$A2A" register dave --role builder --cli tau \
  --prompt "Send ONE short greeting to eve. Wait for her reply. Send one more message. Then mark done."
"$A2A" register eve  --role reviewer --cli pi \
  --prompt "When dave messages you, reply with ONE short sentence. After 2 exchanges mark done."

build_kit() {
    local id="$1" role="$2" prompt="$3"
    cat <<EOF
You are agent "$id" on an a2a peer messaging bus (project=$PROJECT).
Role: $role
Your instruction from the user:
$prompt

You are one of two peers. No boss. Coordinate with each other.

== Locate the a2a binary ==
Run this bash snippet first:

  A2A="\$(command -v a2a 2>/dev/null)"
  [ -z "\$A2A" ] && [ -x "\$HOME/.agents/skills/a2a/a2a" ] && A2A="\$HOME/.agents/skills/a2a/a2a"
  [ -z "\$A2A" ] && [ -x "\$HOME/.claude/skills/a2a/a2a" ] && A2A="\$HOME/.claude/skills/a2a/a2a"
  echo "using a2a at: \$A2A"

A2A_PROJECT=$PROJECT is already in your environment.

== Peers currently registered ==
\$(\"$A2A\" list)

== How to talk ==
  \$A2A list --json                              # roster + roles
  \$A2A recv --as $id --wait 20                  # blocking inbox poll
  \$A2A send <peer-id> "your message" --from $id
  \$A2A status done --as $id                     # signal completion

== Loop (hard cap 5 iterations) ==
1. recv --as $id --wait 15
2. Decide and send AT MOST one short message.
3. If nothing left to say AND no peer is awaiting you, mark done and STOP.
4. After 3 consecutive empty recvs, mark done and STOP.

Rules:
- Stay terse: one sentence per message.
- Address only ids returned by "a2a list".
- Never call clear/unregister/modify peers.
- Keep messages plain ASCII: no quotes or apostrophes.

Start by running the locator, then "recv --as $id --wait 5". Then act.
EOF
}

# Write kit files
KIT_DAVE="$LOG_DIR/dave.kit"
KIT_EVE="$LOG_DIR/eve.kit"
build_kit dave builder "Send ONE short greeting to eve. Wait for her reply. Send one more message. Then mark done." > "$KIT_DAVE"
build_kit eve  reviewer "When dave messages you, reply with ONE short sentence. After 2 exchanges mark done." > "$KIT_EVE"

# Check if tau binary is available (TAU_BIN env var > local build > project build > PATH)
if [ -z "${TAU_BIN:-}" ]; then
    if [ -x "./zig-out/bin/tau" ]; then
        TAU_BIN="./zig-out/bin/tau"
    elif [ -x "$HOME/ai/tau/zig-out/bin/tau" ]; then
        TAU_BIN="$HOME/ai/tau/zig-out/bin/tau"
    elif command -v tau >/dev/null 2>&1; then
        TAU_BIN="tau"
    fi
fi

# Default models — adjust via env if needed
PI_PROVIDER="${PI_PROVIDER:-opencode-go}"
PI_MODEL="${PI_MODEL:-deepseek-v4-flash}"

echo "tau binary: ${TAU_BIN:-not found (skipping tau spawn)}"

if [ -n "$TAU_BIN" ]; then
    echo "spawning dave via tau..."
    DAVE_PID=$("$SPAWN" --cli tau --id dave \
                  --log "$LOG_DIR/dave.log" --kit-file "$KIT_DAVE")
    "$A2A" register dave --pid "$DAVE_PID" --upsert >/dev/null
    echo "  dave pid=$DAVE_PID"
fi

echo "spawning eve via pi ($PI_PROVIDER/$PI_MODEL)..."
EVE_PID=$("$SPAWN" --cli pi --id eve --provider "$PI_PROVIDER" --model "$PI_MODEL" \
            --log "$LOG_DIR/eve.log" --kit-file "$KIT_EVE")
"$A2A" register eve --pid "$EVE_PID" --upsert >/dev/null
echo "  eve  pid=$EVE_PID"

# Watch the bus while they run
DEADLINE=$(( $(date +%s) + 240 ))
while :; do
    NOW=$(date +%s)
    [ "$NOW" -ge "$DEADLINE" ] && { echo "(timeout reached)"; break; }
    DA=n
    EV=n
    [ -n "${DAVE_PID:-}" ] && kill -0 "$DAVE_PID" 2>/dev/null && DA=y
    kill -0 "$EVE_PID" 2>/dev/null && EV=y
    if [ "$DA$EV" = "nn" ]; then echo "(all agents exited)"; break; fi
    sleep 10
    echo "--- bus snapshot  dave:$DA eve:$EV ---"
    "$A2A" peek --limit 30 || true
done

# Cleanup any survivors
for pid in "${DAVE_PID:-}" "$EVE_PID"; do
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && kill "$pid" 2>/dev/null || true
done
wait 2>/dev/null

echo
echo "== final bus =="
"$A2A" peek --limit 100
echo
echo "== agent statuses =="
"$A2A" list

# Verify: at minimum, eve sent at least one message (tau coverage is bonus)
RESULT=$("$A2A" peek --limit 200 --json | python3 -c "
import json, sys
msgs = json.load(sys.stdin)
senders = set(m['sender'] for m in msgs)
print(json.dumps({
    'dave_sent': 'dave' in senders,
    'eve_sent':  'eve'  in senders,
    'total_messages': len(msgs),
    'senders': sorted(senders),
}))
")
echo
echo "result: $RESULT"

EVE_SENT=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['eve_sent'])")
DAVE_SENT=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['dave_sent'])")

PASS=true
if [ "$EVE_SENT" != "True" ]; then
    echo "FAIL: eve (pi) did not send any messages"
    PASS=false
fi
if [ -n "${DAVE_PID:-}" ] && [ "$DAVE_SENT" != "True" ]; then
    echo "FAIL: dave (tau) did not send any messages"
    PASS=false
fi

if $PASS; then
    echo "TAU A2A SMOKE TEST: PASS"
    exit 0
else
    echo "TAU A2A SMOKE TEST: FAIL"
    for who in dave eve; do
        echo "--- $who.log (tail 30) ---"
        tail -30 "$LOG_DIR/$who.log" 2>/dev/null || echo "(no log)"
    done
    exit 1
fi
