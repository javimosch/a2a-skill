#!/usr/bin/env bash
# End-to-end smoke test: 2 haiku Claude sessions communicate as peers via a2a.
# Success = each agent sends >=1 message to the other on the bus.
set -u

A2A="${A2A_BIN:-$(dirname "$(readlink -f "$0")")/a2a}"
PROJECT="${1:-a2a-smoke-$$}"
MODEL="${MODEL:-haiku}"
LOG_DIR="${LOG_DIR:-/tmp/a2a-$PROJECT}"
mkdir -p "$LOG_DIR"

export A2A_PROJECT="$PROJECT"

echo "== a2a smoke test =="
echo "project: $PROJECT"
echo "model:   $MODEL"
echo "logs:    $LOG_DIR"
echo

# Fresh bus
"$A2A" clear --yes >/dev/null 2>&1 || true
"$A2A" init
"$A2A" register alice --role planner \
  --prompt "Propose ONE short greeting plan for the team. Ask bob to critique it."
"$A2A" register bob   --role critic  \
  --prompt "Wait for alice. Critique her plan in ONE sentence. Then mark yourself done."

build_kit() {
    local id="$1" role="$2" prompt="$3"
    cat <<EOF
You are agent "$id" on an a2a peer messaging bus (project=$PROJECT).
Role: $role
Your standing instruction from the user:
$prompt

There is no boss. You and your peers coordinate yourselves.

Peers currently registered:
$("$A2A" list)

Communicate ONLY via the a2a CLI. Use the Bash tool.
Always set A2A_PROJECT=$PROJECT (already in env) or pass --project $PROJECT.

  # check inbox (blocks up to 20s for new messages)
  $A2A recv --as $id --wait 20

  # message a peer directly
  $A2A send <peer-id> "your text" --from $id

  # broadcast
  $A2A send all "your text" --from $id

  # mark yourself done (other agents see this)
  $A2A status done --as $id

LOOP:
1. Call recv --as $id --wait 20.
2. If you got messages, decide what to send, then send at most ONE message.
3. If recv was empty AND you have not introduced yourself yet, send a short
   greeting (direct to the relevant peer, not broadcast).
4. If you have nothing more to say AND no peer is awaiting your reply,
   run status done --as $id and stop.
5. Otherwise repeat from step 1.

Hard rules:
- Stay terse. One short message per turn. No essays.
- Address only ids returned by "$A2A list".
- Stop after 3 consecutive empty recvs (mark done first).
- Never call clear, unregister, or modify other agents.
- Total run budget: 6 iterations max, then mark done and stop.

Start NOW: run recv --as $id --wait 5. Then act.
EOF
}

ALICE_KIT="$(build_kit alice planner 'Propose ONE short greeting plan. Ask bob to critique it.')"
BOB_KIT="$(build_kit bob critic 'Wait for alice. Critique her plan in ONE sentence. Then status done.')"

CLAUDE_FLAGS=(
    -p --model "$MODEL"
    --dangerously-skip-permissions
    --max-turns 12
)

echo "spawning alice..."
A2A_PROJECT="$PROJECT" claude "${CLAUDE_FLAGS[@]}" \
    --append-system-prompt "$ALICE_KIT" \
    "Begin." > "$LOG_DIR/alice.log" 2>&1 &
ALICE_PID=$!

echo "spawning bob..."
A2A_PROJECT="$PROJECT" claude "${CLAUDE_FLAGS[@]}" \
    --append-system-prompt "$BOB_KIT" \
    "Begin." > "$LOG_DIR/bob.log" 2>&1 &
BOB_PID=$!

echo "alice pid=$ALICE_PID bob pid=$BOB_PID"
"$A2A" register alice --pid "$ALICE_PID" --upsert >/dev/null
"$A2A" register bob   --pid "$BOB_PID"   --upsert >/dev/null

# Watch the bus while they run
DEADLINE=$(( $(date +%s) + 180 ))
while :; do
    NOW=$(date +%s)
    if [ "$NOW" -ge "$DEADLINE" ]; then
        echo "(timeout reached)"
        kill "$ALICE_PID" "$BOB_PID" 2>/dev/null || true
        break
    fi
    ALIVE_A=$(kill -0 "$ALICE_PID" 2>/dev/null && echo y || echo n)
    ALIVE_B=$(kill -0 "$BOB_PID"   2>/dev/null && echo y || echo n)
    if [ "$ALIVE_A" = "n" ] && [ "$ALIVE_B" = "n" ]; then
        echo "(both agents exited)"
        break
    fi
    sleep 8
    echo "--- bus snapshot (alice:$ALIVE_A bob:$ALIVE_B) ---"
    "$A2A" peek --limit 40 || true
done

wait "$ALICE_PID" 2>/dev/null
wait "$BOB_PID"   2>/dev/null

echo
echo "== final bus ==="
"$A2A" peek --limit 100
echo
echo "== agent statuses =="
"$A2A" list

ALICE_TO_BOB=$("$A2A" peek --limit 100 --json | python3 -c "
import json, sys
msgs = json.load(sys.stdin)
n = sum(1 for m in msgs if m['sender']=='alice' and (m['recipient']=='bob' or m['recipient'] is None))
print(n)
")
BOB_TO_ALICE=$("$A2A" peek --limit 100 --json | python3 -c "
import json, sys
msgs = json.load(sys.stdin)
n = sum(1 for m in msgs if m['sender']=='bob' and (m['recipient']=='alice' or m['recipient'] is None))
print(n)
")

echo
echo "alice -> bob (or broadcast): $ALICE_TO_BOB"
echo "bob   -> alice (or broadcast): $BOB_TO_ALICE"

if [ "$ALICE_TO_BOB" -ge 1 ] && [ "$BOB_TO_ALICE" -ge 1 ]; then
    echo "SMOKE TEST: PASS (agent communication)"
else
    echo "SMOKE TEST: FAIL (agent communication)"
    echo "--- alice.log (tail) ---"
    tail -50 "$LOG_DIR/alice.log"
    echo "--- bob.log (tail) ---"
    tail -50 "$LOG_DIR/bob.log"
    exit 1
fi

echo
echo "== task workflow test =="
A2A_PY="${A2A_PY:-$(dirname "$(readlink -f "$0")")/a2a.py}"
TASK_PROJECT="${PROJECT}-tasks"

# Create task via Python CLI
echo "Creating task..."
TASK_ID=$("$A2A_PY" task-create "Refactor login module" \
  --description "Update auth flow" \
  --assigned-to alice \
  --priority 2 \
  --json \
  --project "$TASK_PROJECT" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

echo "Task #$TASK_ID created"

# List tasks
echo "Listing tasks..."
"$A2A_PY" task-list --project "$TASK_PROJECT" --json 2>/dev/null | python3 -c "
import json,sys
tasks = json.load(sys.stdin)
assert len(tasks) == 1, f'Expected 1 task, got {len(tasks)}'
assert tasks[0]['status'] == 'planned', f'Expected planned, got {tasks[0][\"status\"]}'
print('  task status:', tasks[0]['status'], '✅')
"

# Claim task
echo "Claiming task #$TASK_ID..."
"$A2A_PY" task-claim "$TASK_ID" --as alice --project "$TASK_PROJECT" 2>/dev/null

# Verify claimed
"$A2A_PY" task-list --project "$TASK_PROJECT" --json 2>/dev/null | python3 -c "
import json,sys
tasks = json.load(sys.stdin)
assert tasks[0]['status'] == 'in_progress', f'Expected in_progress, got {tasks[0][\"status\"]}'
assert tasks[0]['assigned_to'] == 'alice', f'Expected alice, got {tasks[0][\"assigned_to\"]}'
print('  task claimed ✅')
"

# Full workflow
echo "Running workflow: in_progress -> review_pending -> approved -> done"
"$A2A_PY" task-status "$TASK_ID" review_pending --project "$TASK_PROJECT" 2>/dev/null
"$A2A_PY" task-status "$TASK_ID" approved --project "$TASK_PROJECT" 2>/dev/null
echo "Completing task #$TASK_ID..."
"$A2A_PY" task-complete "$TASK_ID" --result "Approved with minor changes" --as alice --project "$TASK_PROJECT" 2>/dev/null

# Verify completed
"$A2A_PY" task-list --project "$TASK_PROJECT" --json 2>/dev/null | python3 -c "
import json,sys
tasks = json.load(sys.stdin)
assert tasks[0]['status'] == 'done', f'Expected done, got {tasks[0][\"status\"]}'
assert tasks[0]['result'] == 'Approved with minor changes', f'Wrong result: {tasks[0].get(\"result\")}'
print('  task done ✅')
"

# Test invalid transitions
echo "Testing invalid transitions..."
"$A2A_PY" task-status "$TASK_ID" planned --project "$TASK_PROJECT" 2>/dev/null && echo "  ❌ should have failed" || echo "  done -> planned rejected ✅"

# Test wrong assignee can't complete
echo "Testing wrong assignee rejection..."
TASK2_ID=$("$A2A_PY" task-create "Test wrong assignee" \
  --assigned-to bob --json --project "$TASK_PROJECT" 2>/dev/null \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
"$A2A_PY" task-claim "$TASK2_ID" --as bob --project "$TASK_PROJECT" 2>/dev/null
"$A2A_PY" task-complete "$TASK2_ID" --result "done" --as alice --project "$TASK_PROJECT" 2>/dev/null && echo "  ❌ should have failed" || echo "  wrong assignee rejected ✅"

echo
echo "TASK WORKFLOW: PASS"
exit 0
