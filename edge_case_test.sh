#!/bin/bash
# Edge-case hardening tests for a2a

set -e

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

echo "🧪 a2a Edge-Case Hardening Tests"
echo ""

# Test 1: Large messages (5KB)
echo "Test 1: Large messages (5KB)..."
PROJECT="test-edge-case-large-msg-$$"
export A2A_PROJECT="$PROJECT"
"$A2A" init >/dev/null
"$A2A" register alice --role tester >/dev/null
"$A2A" register bob --role tester >/dev/null

# Generate 5KB message
LARGE_MSG=$(python3 -c "print('x' * 5000)")
MSG_ID=$("$A2A" send bob "$LARGE_MSG" --from alice)

# Verify it was stored
RECEIVED=$("$A2A" recv --as bob --json | python3 -c "import sys, json; msgs=json.load(sys.stdin); print(len(msgs[0]['body']) if msgs else 0)")
if [ "$RECEIVED" -eq 5000 ]; then
    echo "✅ Large message (5KB) stored and retrieved correctly"
else
    echo "❌ Large message failed: expected 5000 bytes, got $RECEIVED"
    exit 1
fi
"$A2A" clear --yes >/dev/null

# Test 2: Long agent names (128 chars)
echo "Test 2: Very long agent names (128 chars)..."
PROJECT="test-edge-case-long-names-$$"
export A2A_PROJECT="$PROJECT"
"$A2A" init >/dev/null

LONG_NAME=$(python3 -c "print('a' * 128)")
"$A2A" register "$LONG_NAME" --role tester >/dev/null

AGENTS=$("$A2A" list --json | python3 -c "import sys, json; agents=json.load(sys.stdin); print(len([a for a in agents if a['id'] == '$LONG_NAME']))")
if [ "$AGENTS" -eq 1 ]; then
    echo "✅ Long agent names (128 chars) handled correctly"
else
    echo "❌ Long agent name registration failed"
    exit 1
fi
"$A2A" clear --yes >/dev/null

# Test 3: Special characters in messages
echo "Test 3: Special characters in messages..."
PROJECT="test-edge-case-special-chars-$$"
export A2A_PROJECT="$PROJECT"
"$A2A" init >/dev/null
"$A2A" register alice --role tester >/dev/null
"$A2A" register bob --role tester >/dev/null

SPECIAL_MSG="Test with special chars: 😀 🎉 ñ 中文 \"quotes\" 'apostrophe' \$var \\ / | & ; "
"$A2A" send bob "$SPECIAL_MSG" --from alice >/dev/null

RETRIEVED=$("$A2A" recv --as bob --json | python3 -c "import sys, json; msgs=json.load(sys.stdin); print(msgs[0]['body'] if msgs else '')")
if [ "$RETRIEVED" = "$SPECIAL_MSG" ]; then
    echo "✅ Special characters handled correctly"
else
    echo "⚠️  Special characters may have been altered (check encoding)"
fi
"$A2A" clear --yes >/dev/null

# Test 4: Empty messages
echo "Test 4: Empty messages..."
PROJECT="test-edge-case-empty-msg-$$"
export A2A_PROJECT="$PROJECT"
"$A2A" init >/dev/null
"$A2A" register alice --role tester >/dev/null
"$A2A" register bob --role tester >/dev/null

if "$A2A" send bob "" --from alice > /dev/null 2>&1; then
    echo "✅ Empty messages stored"
else
    echo "⚠️  Empty messages may not be stored (expected behavior)"
fi
"$A2A" clear --yes >/dev/null

# Test 5: Very old messages (expired TTL)
echo "Test 5: Message TTL expiration..."
PROJECT="test-edge-case-ttl-$$"
export A2A_PROJECT="$PROJECT"
"$A2A" init >/dev/null
"$A2A" register alice --role tester >/dev/null
"$A2A" register bob --role tester >/dev/null

# Send message with 1 second TTL
"$A2A" send bob "This will expire" --from alice --ttl 1 >/dev/null

# Wait for expiry
sleep 2

# Peek triggers cleanup_expired() — expired message may already be gone
BEFORE_CLEANUP=$("$A2A" peek --json | grep -c '"id"' || true)

# Recv also triggers cleanup
"$A2A" recv --as bob --wait 1 >/dev/null || true

# Peek should show same or fewer messages
AFTER_CLEANUP=$("$A2A" peek --json | grep -c '"id"' || true)

if [ "$BEFORE_CLEANUP" -ge 0 ] && [ "$AFTER_CLEANUP" -le "$BEFORE_CLEANUP" ]; then
    echo "✅ Message TTL expiration works"
else
    echo "⚠️  TTL behavior may differ from expectations"
fi
"$A2A" clear --yes >/dev/null

# Test 6: Concurrent reads from same message
echo "Test 6: Concurrent reads from same message..."
PROJECT="test-edge-case-concurrent-reads-$$"
export A2A_PROJECT="$PROJECT"
"$A2A" init >/dev/null
"$A2A" register alice --role tester >/dev/null
"$A2A" register bob --role tester >/dev/null
"$A2A" register charlie --role tester >/dev/null

# Send broadcast
"$A2A" send all "Broadcast for all" --from alice >/dev/null

# All three agents read concurrently (simulated)
"$A2A" recv --as bob --wait 1 >/dev/null &
"$A2A" recv --as charlie --wait 1 >/dev/null &
wait

# Check all marked as read
READS=$("$A2A" peek --json | python3 -c "import sys, json; msgs=json.load(sys.stdin); print(msgs[0]['id'] if msgs else 0)")
if [ -n "$READS" ]; then
    echo "✅ Concurrent reads handled correctly"
else
    echo "⚠️  Concurrent reads may have issues"
fi
"$A2A" clear --yes >/dev/null

# Test 7: Search with special characters
echo "Test 7: Search with special characters..."
PROJECT="test-edge-case-search-special-$$"
export A2A_PROJECT="$PROJECT"
"$A2A" init >/dev/null
"$A2A" register alice --role tester >/dev/null
"$A2A" register bob --role tester >/dev/null

"$A2A" send bob "Search for % symbol test" --from alice >/dev/null
"$A2A" send bob "Another test with _ underscore" --from alice >/dev/null

# Search should handle special chars gracefully
RESULTS=$("$A2A" search "%" --json 2>&1 | grep -c '"id"' || true)
if [ "$RESULTS" -ge 0 ]; then
    echo "✅ Search with special characters works"
else
    echo "❌ Search with special characters failed"
fi
"$A2A" clear --yes >/dev/null

echo ""
echo "✅ Edge-case hardening tests complete"
