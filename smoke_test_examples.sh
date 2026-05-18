#!/bin/bash
# Smoke test for example agents
# Runs researcher, reviewer, and coordinator agents concurrently and verifies completion

set -e

PROJECT="a2a-examples-smoke-$$"
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

echo "🧪 a2a Example Agents Smoke Test"
echo "Project: $PROJECT"
echo "a2a: $A2A"
echo ""

# Cleanup function
cleanup() {
    echo "Cleaning up..."
    "$A2A" clear --yes 2>/dev/null || true
    kill $(jobs -p) 2>/dev/null || true
}
trap cleanup EXIT

# Initialize project
"$A2A" init
echo "✓ Project initialized"

# Register example agents
"$A2A" register researcher --role "investigator" --cli python
"$A2A" register reviewer --role "code-reviewer" --cli python
"$A2A" register coordinator --role "task-manager" --cli python

echo "✓ Agents registered"
echo ""

# Spawn example agents
SCRIPT_DIR="$(dirname "$0")/examples"

echo "Spawning example agents..."
python3 "$SCRIPT_DIR/researcher_agent.py" > /tmp/researcher.log 2>&1 &
RESEARCHER_PID=$!
echo "  researcher (PID $RESEARCHER_PID)"

python3 "$SCRIPT_DIR/code_reviewer_agent.py" > /tmp/reviewer.log 2>&1 &
REVIEWER_PID=$!
echo "  reviewer (PID $REVIEWER_PID)"

python3 "$SCRIPT_DIR/task_coordinator_agent.py" > /tmp/coordinator.log 2>&1 &
COORDINATOR_PID=$!
echo "  coordinator (PID $COORDINATOR_PID)"

echo ""
echo "⏳ Waiting for agents to complete (up to 60s)..."

# Wait for agents with timeout
TIMEOUT=60
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    # Check if all PIDs still running
    if ! kill -0 $RESEARCHER_PID $REVIEWER_PID $COORDINATOR_PID 2>/dev/null; then
        echo "✓ All agents completed"
        break
    fi

    # Show progress
    AGENTS_DONE=$("$A2A" list --json | grep -o '"status":"done"' | wc -l)
    echo "  Status: $AGENTS_DONE/3 agents done, elapsed: ${ELAPSED}s"

    sleep 3
    ELAPSED=$((ELAPSED + 3))
done

# Check final state
echo ""
echo "📊 Final State:"
"$A2A" list

echo ""
echo "📨 Message Bus:"
"$A2A" peek --limit 30

# Verify all agents marked done
DONE_COUNT=$("$A2A" list --json | grep -o '"status": "done"' | wc -l)
if [ "$DONE_COUNT" -eq 3 ]; then
    echo ""
    echo "✅ SMOKE TEST PASSED: All 3 agents completed successfully"
    exit 0
else
    echo ""
    echo "❌ SMOKE TEST FAILED: Expected 3 agents done, got $DONE_COUNT"
    echo ""
    echo "Researcher log:"
    cat /tmp/researcher.log
    echo ""
    echo "Reviewer log:"
    cat /tmp/reviewer.log
    echo ""
    echo "Coordinator log:"
    cat /tmp/coordinator.log
    exit 1
fi
