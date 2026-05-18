#!/usr/bin/env bash
# Cross-CLI smoke test: claude + opencode + pi agents collaborate on the a2a bus.
# Success = at least one message from each agent appears on the bus and each
# agent ends with status='done' (or at minimum exits cleanly).
set -u

DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
A2A="${A2A_BIN:-$DIR/a2a}"
SPAWN="$DIR/a2a-spawn"
PROJECT="${1:-a2a-multi-$$}"
LOG_DIR="${LOG_DIR:-/tmp/a2a-$PROJECT}"
mkdir -p "$LOG_DIR"
export A2A_PROJECT="$PROJECT"

echo "== a2a multi-CLI smoke test =="
echo "project: $PROJECT"
echo "logs:    $LOG_DIR"
echo

# Fresh bus
"$A2A" clear --yes >/dev/null 2>&1 || true
"$A2A" init

"$A2A" register alice --role planner --cli claude \
  --prompt "Open with ONE short greeting + one concrete subtask for bob and carol. Stop after 2 turns."
"$A2A" register bob   --role critic --cli opencode \
  --prompt "Critique alice's plan in ONE short sentence. Then mark done."
"$A2A" register carol --role synthesizer --cli pi \
  --prompt "After reading alice's plan and bob's critique, write ONE-sentence synthesis. Then mark done."

build_kit() {
    local id="$1" role="$2" prompt="$3"
    cat <<EOF
You are agent "$id" on an a2a peer messaging bus (project=$PROJECT).
Role: $role
Your instruction from the user:
$prompt

You are one of three peers. No boss. Coordinate amongst yourselves.

== Locate the a2a binary ==
Run this bash snippet first:

  A2A="\$(command -v a2a 2>/dev/null)"
  [ -z "\$A2A" ] && [ -x "\$HOME/.agents/skills/a2a/a2a" ] && A2A="\$HOME/.agents/skills/a2a/a2a"
  [ -z "\$A2A" ] && [ -x "\$HOME/.claude/skills/a2a/a2a" ] && A2A="\$HOME/.claude/skills/a2a/a2a"
  echo "using a2a at: \$A2A"

A2A_PROJECT=$PROJECT is already in your environment.

== Peers currently registered ==
$("$A2A" list)

== How to talk ==
  \$A2A list --json                              # roster + roles
  \$A2A recv --as $id --wait 20                  # blocking inbox poll
  \$A2A send <peer-id> "your message" --from $id
  \$A2A send all "your message" --from $id       # broadcast
  \$A2A status done --as $id                     # signal completion

== Loop (hard cap 5 iterations) ==
1. recv --as $id --wait 15
2. Decide and send AT MOST one short message.
3. If nothing left to say AND no peer is awaiting you, mark done and STOP.
4. After 3 consecutive empty recvs, mark done and STOP.

Rules:
- Stay terse: one sentence per message.
- Address only ids returned by 'a2a list'.
- Never call clear/unregister/modify peers.

Start by running the locator, then 'recv --as $id --wait 5'. Then act.
EOF
}

# Write kit files
KIT_ALICE="$LOG_DIR/alice.kit"
KIT_BOB="$LOG_DIR/bob.kit"
KIT_CAROL="$LOG_DIR/carol.kit"
build_kit alice planner     "$($A2A list --json | head -1; echo)
Open with ONE short greeting + one concrete subtask for bob and carol. After 2 turns mark done." > "$KIT_ALICE"
build_kit bob   critic       "Critique alice's plan in ONE short sentence. Then mark done." > "$KIT_BOB"
build_kit carol synthesizer  "After alice's plan and bob's critique, write ONE-sentence synthesis. Then mark done." > "$KIT_CAROL"

# Pick available CLIs, abort gracefully if a CLI is missing
have() { command -v "$1" >/dev/null 2>&1; }

# Default models — adjust via env if needed
CLAUDE_MODEL="${CLAUDE_MODEL:-haiku}"
OPENCODE_MODEL="${OPENCODE_MODEL:-opencode-go/deepseek-v4-flash}"
PI_PROVIDER="${PI_PROVIDER:-opencode-go}"
PI_MODEL="${PI_MODEL:-deepseek-v4-flash}"

echo "spawning alice via claude ($CLAUDE_MODEL)..."
ALICE_PID=$("$SPAWN" --cli claude --id alice --model "$CLAUDE_MODEL" \
              --log "$LOG_DIR/alice.log" --kit-file "$KIT_ALICE")
"$A2A" register alice --pid "$ALICE_PID" --upsert >/dev/null
echo "  alice pid=$ALICE_PID"

echo "spawning bob via opencode ($OPENCODE_MODEL)..."
BOB_PID=$("$SPAWN" --cli opencode --id bob --model "$OPENCODE_MODEL" \
            --log "$LOG_DIR/bob.log" --kit-file "$KIT_BOB")
"$A2A" register bob --pid "$BOB_PID" --upsert >/dev/null
echo "  bob   pid=$BOB_PID"

echo "spawning carol via pi ($PI_PROVIDER/$PI_MODEL)..."
CAROL_PID=$("$SPAWN" --cli pi --id carol --provider "$PI_PROVIDER" --model "$PI_MODEL" \
              --log "$LOG_DIR/carol.log" --kit-file "$KIT_CAROL")
"$A2A" register carol --pid "$CAROL_PID" --upsert >/dev/null
echo "  carol pid=$CAROL_PID"

# Watch the bus while they run
DEADLINE=$(( $(date +%s) + 240 ))
while :; do
    NOW=$(date +%s)
    [ "$NOW" -ge "$DEADLINE" ] && { echo "(timeout reached)"; break; }
    AL=$(kill -0 "$ALICE_PID" 2>/dev/null && echo y || echo n)
    BO=$(kill -0 "$BOB_PID"   2>/dev/null && echo y || echo n)
    CA=$(kill -0 "$CAROL_PID" 2>/dev/null && echo y || echo n)
    if [ "$AL$BO$CA" = "nnn" ]; then echo "(all agents exited)"; break; fi
    sleep 10
    echo "--- bus snapshot  alice:$AL bob:$BO carol:$CA ---"
    "$A2A" peek --limit 30 || true
done

# Cleanup any survivors
for pid in "$ALICE_PID" "$BOB_PID" "$CAROL_PID"; do
    kill -0 "$pid" 2>/dev/null && kill "$pid" 2>/dev/null || true
done
wait 2>/dev/null

echo
echo "== final bus =="
"$A2A" peek --limit 100
echo
echo "== agent statuses =="
"$A2A" list

# Verify each agent sent at least one message
RESULT=$("$A2A" peek --limit 200 --json | python3 -c "
import json, sys
msgs = json.load(sys.stdin)
senders = set(m['sender'] for m in msgs)
print(json.dumps({
    'alice_sent': 'alice' in senders,
    'bob_sent':   'bob'   in senders,
    'carol_sent': 'carol' in senders,
    'total_messages': len(msgs),
    'senders': sorted(senders),
}))
")
echo
echo "result: $RESULT"

ALICE_SENT=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['alice_sent'])")
BOB_SENT=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['bob_sent'])")
CAROL_SENT=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin)['carol_sent'])")

if [ "$ALICE_SENT" = "True" ] && [ "$BOB_SENT" = "True" ] && [ "$CAROL_SENT" = "True" ]; then
    echo "CROSS-CLI SMOKE TEST: PASS"
    exit 0
else
    echo "CROSS-CLI SMOKE TEST: FAIL"
    for who in alice bob carol; do
        echo "--- $who.log (tail 30) ---"
        tail -30 "$LOG_DIR/$who.log" 2>/dev/null || echo "(no log)"
    done
    exit 1
fi
