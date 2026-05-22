#!/bin/bash
# Cross-verify JSON output between Go CLI and Python CLI.
# Requires both binaries and a clean project.
set -eu

GO_A2A="${1:-./a2a}"
PY_A2A="${2:-$(command -v a2a 2>/dev/null || echo './a2a.py')}"
PROJECT="json-verify-$$"
export A2A_PROJECT="$PROJECT"

PASS=0
FAIL=0

pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

# Check both binaries exist
for b in "$GO_A2A" "$PY_A2A"; do
  if [ ! -x "$b" ]; then
    echo "ERROR: $b not found or not executable"
    exit 1
  fi
done

echo "=== JSON Cross-Verification ==="
echo "Go CLI:   $GO_A2A ($($GO_A2A version 2>/dev/null))"
echo "Py CLI:   $PY_A2A"
echo "Project:  $PROJECT"
echo ""

# Set up test bus
"$GO_A2A" init
"$GO_A2A" register alice --role planner --cli pi
"$GO_A2A" register bob --role critic --cli claude
"$GO_A2A" send bob "hello from alice" --from alice --thread test-thread
"$GO_A2A" send bob "second message" --from alice --thread test-thread
"$GO_A2A" send all "broadcast message" --from bob
"$GO_A2A" status done --as bob

echo ""

# Compare JSON outputs
compare() {
  local cmd="$1"
  local label="$2"
  
  local go_out go_exit py_out py_exit
  
  go_out=$(A2A_PROJECT="$PROJECT" "$GO_A2A" $cmd --json 2>/dev/null) && go_exit=0 || go_exit=$?
  py_out=$(A2A_PROJECT="$PROJECT" "$PY_A2A" $cmd --json 2>/dev/null) && py_exit=0 || py_exit=$?
  
  if [ "$go_exit" != "$py_exit" ]; then
    fail "$label — exit codes differ (Go=$go_exit Py=$py_exit)"
    return
  fi
  
  if [ "$go_out" != "$py_out" ]; then
    fail "$label — JSON output differs"
    echo "    Go: $(echo "$go_out" | head -3)"
    echo "    Py: $(echo "$py_out" | head -3)"
  else
    pass "$label — JSON matches"
  fi
}

compare "list" "list --json"
compare "stats" "stats --json"
compare "peek --limit 10" "peek --limit 10"
compare "thread test-thread" "thread test-thread --json"
compare "search hello" "search hello --json"

# Compare non-JSON output (important for agent parity)
compare_output() {
  local cmd="$1"
  local label="$2"
  
  local go_out py_out
  
  go_out=$(A2A_PROJECT="$PROJECT" "$GO_A2A" $cmd 2>&1)
  py_out=$(A2A_PROJECT="$PROJECT" "$PY_A2A" $cmd 2>&1)
  
  # Normalize whitespace for comparison
  go_norm=$(echo "$go_out" | sed 's/[[:space:]]\+/ /g' | sed 's/^ *//')
  py_norm=$(echo "$py_out" | sed 's/[[:space:]]\+/ /g' | sed 's/^ *//')
  
  # Stats output differs in project name (both contain the name)
  if echo "$go_norm" | grep -q "$PROJECT" && echo "$py_norm" | grep -q "$PROJECT"; then
    pass "$label — both contain project name"
  else
    fail "$label — output mismatch"
    echo "    Go: $go_norm"
    echo "    Py: $py_norm"
  fi
}

compare_output "stats" "stats (text)"

# Cleanup
"$GO_A2A" clear --yes > /dev/null 2>&1 || true

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && echo "ALL JSON OUTPUT VERIFIED" || echo "SOME MISMATCHES FOUND"
exit $FAIL
