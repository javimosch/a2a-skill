#!/bin/bash
# Smoke test for the a2a Go CLI binary.
# Tests basic workflow: init → register → send → recv → peek → stats → status → clear
set -eu

A2A="${1:-./a2a}"
PROJECT="go-smoke-$$"
export A2A_PROJECT="$PROJECT"

PASS=0
FAIL=0

pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

# Require a2a binary
if [ ! -x "$A2A" ]; then
  echo "building a2a binary..."
  go build -o a2a ./cmd/a2a/
  A2A=./a2a
fi

echo "=== a2a Go CLI Smoke Test ==="
echo "Binary: $A2A ($($A2A version 2>/dev/null || echo '?'))"
echo "Project: $PROJECT"
echo ""

# 1. init
"$A2A" init 2>&1 | grep -q "ready" && pass "init" || fail "init"

# 2. register
"$A2A" register alice --role planner --cli pi 2>&1 | grep -q "registered" && pass "register alice" || fail "register alice"

# 3. list
"$A2A" list 2>&1 | grep -q "alice" && pass "list shows alice" || fail "list shows alice"

# 4. register second agent
"$A2A" register bob --role critic --cli claude 2>&1 | grep -q "registered" && pass "register bob" || fail "register bob"

# 5. send direct message
"$A2A" send bob "hello from alice" --from alice 2>&1 | grep -q "#1" && pass "send alice->bob" || fail "send alice->bob"

# 6. send broadcast
"$A2A" send all "hello everyone" --from alice 2>&1 | grep -q "#2" && pass "send broadcast" || fail "send broadcast"

# 7. recv as bob
OUT=$("$A2A" recv --as bob --wait 3 2>&1)
echo "$OUT" | grep -q "alice" && pass "recv bob sees alice messages" || fail "recv bob sees alice messages"

# 8. recv with --json --all
OUT=$("$A2A" recv --as bob --all --json 2>&1)
echo "$OUT" | grep -q "sender" && pass "recv --json --all" || fail "recv --json --all"

# 9. peek
OUT=$("$A2A" peek --limit 5 2>&1)
echo "$OUT" | grep -q "#1" && pass "peek shows messages" || fail "peek shows messages"

# 10. project
OUT=$("$A2A" project 2>&1)
echo "$OUT" | grep -q "exists" && pass "project info" || fail "project info"

# 11. stats
OUT=$("$A2A" stats 2>&1)
echo "$OUT" | grep -q "Messages: 2" && pass "stats shows 2 messages" || fail "stats shows 2 messages"

# 12. stats --json
OUT=$("$A2A" stats --json 2>&1)
echo "$OUT" | grep -q '"messages": 2' && pass "stats --json" || fail "stats --json"

# 13. list --json
OUT=$("$A2A" list --json 2>&1)
echo "$OUT" | grep -q '"id": "alice"' && pass "list --json" || fail "list --json"

# 14. status update
"$A2A" status done --as alice 2>&1 | grep -q "done" && pass "status done alice" || fail "status done alice"

# 15. send a fresh message and wait for it
"$A2A" send bob "fresh-msg" --from alice 2>&1 | grep -q "#3" || "$A2A" send bob "fresh-msg" --from alice 2>&1 | grep -q "#4"
"$A2A" wait --as bob --count 1 --timeout 5 2>&1 | grep -q "ok" && pass "wait" || fail "wait"

# 15b. wait with zero count is rejected
"$A2A" wait --as bob --count 0 --timeout 1 2>&1 | grep -qi "must be a positive" && pass "wait rejects count=0" || fail "wait rejects count=0"

# 16. send with --thread
"$A2A" send bob "threaded msg" --from alice --thread test-thread 2>&1 | grep -qE "#[34]" && pass "send with thread" || fail "send with thread"

# 17. thread view
OUT=$("$A2A" thread test-thread 2>&1)
echo "$OUT" | grep -q "threaded msg" && pass "thread shows message" || fail "thread shows message"

# 18. thread --json
OUT=$("$A2A" thread test-thread --json 2>&1)
echo "$OUT" | grep -q '"thread_id": "test-thread"' && pass "thread --json" || fail "thread --json"

# 19. search
OUT=$("$A2A" search hello 2>&1)
echo "$OUT" | grep -q "hello" && pass "search finds 'hello'" || fail "search finds 'hello'"

# 20. search --json
OUT=$("$A2A" search hello --json 2>&1)
echo "$OUT" | grep -q '"body"' && pass "search --json" || fail "search --json"

# 21. send with --ttl
"$A2A" send bob "expiring msg" --from alice --ttl 1 2>&1 | grep -qE "#[345]" && pass "send with TTL" || fail "send with TTL"

# 22. clear (should refuse without --yes)
"$A2A" clear 2>&1 | grep -q "refusing" && pass "clear refuses without --yes" || fail "clear refuses without --yes"

# 23. clear with --yes
"$A2A" clear --yes 2>&1 | grep -q "cleared" && pass "clear --yes" || fail "clear --yes"

# 24. init again (after clear)
"$A2A" init 2>&1 | grep -q "ready" && pass "re-init after clear" || fail "re-init after clear"

# cleanup
"$A2A" clear --yes > /dev/null 2>&1 || true

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && echo "ALL SMOKE TESTS PASSED" || echo "SOME TESTS FAILED"
exit $FAIL
