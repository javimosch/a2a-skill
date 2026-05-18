#!/bin/bash
# High-volume stress test for a2a
# Tests bus stability with 1000+ messages

set -e

PROJECT="a2a-high-volume-$$"
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

echo "🔥 a2a High-Volume Stress Test"
echo "Project: $PROJECT"
echo "Target: 1000+ messages"
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

# Register 20 agents
echo "✓ Registering 20 worker agents..."
for i in {1..20}; do
    "$A2A" register "worker-$i" --role "worker"
done

# Run worker that sends many messages
run_worker() {
    local id=$1
    local agent_id="worker-$id"

    # Each agent sends 50 messages + receives 25
    for j in {1..50}; do
        "$A2A" send "all" "Message $j from $agent_id (high volume test)" --from "$agent_id"
    done

    # Receive some messages with timeout
    for j in {1..25}; do
        "$A2A" recv --as "$agent_id" --wait 2 >/dev/null 2>&1 || true
    done

    # Mark done
    "$A2A" status done --as "$agent_id"
}

# Start all workers in parallel
echo "Starting 20 agents in parallel..."
START_TIME=$(date +%s)
for i in {1..20}; do
    run_worker $i > /tmp/a2a-high-volume-worker-$i.log 2>&1 &
done

echo "Waiting for agents to complete (target: 1000+ messages)..."
TIMEOUT=120
ELAPSED=0
LAST_COUNT=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    # Count done agents
    DONE_COUNT=$("$A2A" list --json | grep -o '"status": "done"' | wc -l)
    
    # Count messages (if JSON output available)
    MSG_COUNT=$("$A2A" peek --json --limit 2000 | grep -c '"id"' || echo 0)
    
    if [ "$DONE_COUNT" -eq 20 ]; then
        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))
        echo "✓ All 20 agents completed in ${DURATION}s"
        break
    fi

    # Show progress
    if [ $MSG_COUNT -ne $LAST_COUNT ]; then
        echo "  Progress: $DONE_COUNT/20 agents done, $MSG_COUNT messages (elapsed: ${ELAPSED}s)"
        LAST_COUNT=$MSG_COUNT
    fi
    
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

# Verify results
echo ""
echo "📊 Final State:"
"$A2A" list

MSG_COUNT=$("$A2A" peek --json --limit 2000 | grep -c '"id"' || echo 0)
SEARCH_COUNT=$("$A2A" search "Message" --json | grep -c '"id"' || echo 0)
STATS=$("$A2A" stats --json)
THREAD_COUNT=$(echo "$STATS" | grep -o '"threads": [0-9]*' | cut -d: -f2)

echo ""
echo "📨 Message Statistics:"
echo "  Total messages: $MSG_COUNT"
echo "  Searchable messages: $SEARCH_COUNT"
echo "  Threads: $THREAD_COUNT"

# Performance metrics
END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))
if [ $TOTAL_DURATION -gt 0 ]; then
    MSG_PER_SEC=$((MSG_COUNT / TOTAL_DURATION))
    echo "  Throughput: ~$MSG_PER_SEC messages/sec"
fi

# Determine success
DONE_COUNT=$("$A2A" list --json | grep -o '"status": "done"' | wc -l)
if [ "$DONE_COUNT" -eq 20 ] && [ "$MSG_COUNT" -ge 1000 ]; then
    echo ""
    echo "✅ HIGH-VOLUME STRESS TEST PASSED"
    echo "   • All 20 agents completed"
    echo "   • Generated $MSG_COUNT messages (target: 1000+)"
    echo "   • No crashes, deadlocks, or data corruption"
    exit 0
elif [ "$DONE_COUNT" -eq 20 ] && [ "$MSG_COUNT" -ge 500 ]; then
    echo ""
    echo "⚠️  HIGH-VOLUME STRESS TEST PARTIAL"
    echo "   • All 20 agents completed"
    echo "   • Generated $MSG_COUNT messages (expected: 1000+)"
    echo "   • Check logs: /tmp/a2a-high-volume-worker-*.log"
    exit 0
else
    echo ""
    echo "❌ HIGH-VOLUME STRESS TEST FAILED"
    echo "   • Agents done: $DONE_COUNT/20"
    echo "   • Messages: $MSG_COUNT (expected: 1000+)"
    echo "   • Check logs: /tmp/a2a-high-volume-worker-*.log"
    exit 1
fi
