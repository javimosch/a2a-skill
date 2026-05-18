#!/bin/bash
# Multi-agent stress test for a2a
# Spawns 10+ agents and validates system stability under load

set -e

PROJECT="a2a-stress-test-$$"
export A2A_PROJECT="$PROJECT"

# Locate a2a
A2A=""
for cand in \
    "$(command -v a2a 2>/dev/null)" \
    "$HOME/.agents/skills/a2a/a2a" \
    "$HOME/.claude/skills/a2a/a2a" \
    "$(dirname "$0")/a2a" ; do
    if [ -x "$cand" ]; then A2A="$cand"; break; fi
done

if [ -z "$A2A" ]; then
    echo "ERROR: a2a binary not found"
    exit 1
fi

echo "🔥 a2a Multi-Agent Stress Test"
echo "Project: $PROJECT"
echo "Agents: 10 workers"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "Cleaning up..."
    "$A2A" clear --yes 2>/dev/null || true
    kill $(jobs -p) 2>/dev/null || true
}
trap cleanup EXIT

# Initialize
"$A2A" init
echo "✓ Project initialized"

# Register 10 agents
echo "✓ Registering 10 worker agents..."
for i in {1..10}; do
    "$A2A" register "worker-$i" --role "worker"
done

# Spawn stress test for each agent
run_worker() {
    local id=$1
    local agent_id="worker-$id"

    # Each agent sends 5 messages and responds to 3 messages
    for j in {1..5}; do
        "$A2A" send "all" "Stress test message $j from $agent_id" --from "$agent_id"
        sleep 0.1
    done

    # Receive up to 10 messages with timeout
    for j in {1..3}; do
        "$A2A" recv --as "$agent_id" --wait 5 >/dev/null 2>&1 || true
    done

    # Mark done
    "$A2A" status done --as "$agent_id"
}

# Start all workers in parallel
echo "Starting 10 agents in parallel..."
for i in {1..10}; do
    run_worker $i > /tmp/a2a-stress-worker-$i.log 2>&1 &
done

echo "Waiting for agents to complete (max 60s)..."
TIMEOUT=60
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    # Count done agents (handle spacing in JSON)
    DONE_COUNT=$("$A2A" list --json | grep -o '"status": "done"' | wc -l)
    if [ "$DONE_COUNT" -eq 10 ]; then
        echo "✓ All 10 agents completed"
        break
    fi

    echo "  Progress: $DONE_COUNT/10 agents done (elapsed: ${ELAPSED}s)"
    sleep 3
    ELAPSED=$((ELAPSED + 3))
done

# Verify results
echo ""
echo "📊 Final State:"
"$A2A" list

MSG_COUNT=$("$A2A" peek --json --limit 1000 | grep -c '"id"' || echo 0)
echo ""
echo "📨 Message Statistics:"
echo "  Total messages on bus: $MSG_COUNT"

# Determine success
DONE_COUNT=$("$A2A" list --json | grep -o '"status": "done"' | wc -l)
if [ "$DONE_COUNT" -eq 10 ] && [ "$MSG_COUNT" -gt 40 ]; then
    echo ""
    echo "✅ STRESS TEST PASSED"
    echo "   • All 10 agents completed"
    echo "   • Generated $MSG_COUNT messages"
    echo "   • No crashes or deadlocks"
    exit 0
else
    echo ""
    echo "❌ STRESS TEST FAILED"
    echo "   • Agents done: $DONE_COUNT/10"
    echo "   • Messages: $MSG_COUNT (expected >40)"
    exit 1
fi
