#!/usr/bin/env bash
# Smoke test for the agent groups (@groupname) feature.
# Spawns 3 PL, 2 QA (in a @qa group), and 1 PO agent on the a2a bus.
# PLs send to @qa, QA receives as members, PO only peeks the hub.
set -u

A2A="${A2A_BIN:-$(dirname "$(readlink -f "$0")")/a2a.py}"
PROJECT="${1:-a2a-group-smoke-$$}"
LOG_DIR="${LOG_DIR:-/tmp/a2a-$PROJECT}"
mkdir -p "$LOG_DIR"

export A2A_PROJECT="$PROJECT"

echo "== a2a group smoke test =="
echo "project: $PROJECT"
echo "logs:    $LOG_DIR"
echo

# ---- Fresh bus ----
"$A2A" clear --yes >/dev/null 2>&1 || true
"$A2A" init

# ---- Register 6 agents ----
echo "--- registering agents ---"
for id in pl-01 pl-02 pl-03 qa-01 qa-02 po-01; do
    "$A2A" register "$id" --role "agent" --upsert
done
"$A2A" list
echo

# ---- Create groups ----
echo "--- creating group @qa ---"
"$A2A" group create qa
"$A2A" group add qa qa-01 qa-02
"$A2A" group show qa
echo

# ---- Test: PL sends to @qa group ----
echo "--- PLs send to @qa group ---"
"$A2A" send --from pl-01 @qa "PL-01: group messaging feature looks solid — fan-out is clean"
"$A2A" send --from pl-02 @qa "PL-02: reviewed the create_group persistence fix, LGTM"
"$A2A" send --from pl-03 @qa "PL-03: docstrings still need work, let's track that"
echo

# ---- Test: QA receives as group members ----
echo "--- QA receives (as individual members) ---"
echo "=== qa-01 inbox ==="
"$A2A" recv --as qa-01
echo "=== qa-02 inbox ==="
"$A2A" recv --as qa-02
echo

# ---- Test: QA replies individually ----
echo "--- QA replies directly to PLs ---"
"$A2A" send --from qa-01 pl-01 "ACK from QA-01 — fan-out verified, got all 3 messages"
"$A2A" send --from qa-02 pl-02 "ACK from QA-02 — group membership confirmed"
echo

# ---- Test: PL sends to PO directly ----
echo "--- PLs send to PO ---"
"$A2A" send --from pl-01 po-01 "PO: feature complete, PR #2 on feat-group"
"$A2A" send --from pl-02 po-01 "PO: CI fixes pushed — lint and smoke test guards"
echo

# ---- Test: PO peeks the hub (reads everything) ----
echo "--- PO peeks the entire bus ---"
"$A2A" recv --as po-01
echo

# ---- Test: group list ----
echo "--- group list ---"
"$A2A" group list
echo

# ---- Test: remove from group ----
echo "--- remove qa-02 from @qa, verify ---"
"$A2A" group remove qa qa-02
"$A2A" group show qa
echo

# ---- Test: add back ----
echo "--- add qa-02 back ---"
"$A2A" group add qa qa-02
"$A2A" group show qa
echo

# ---- Test: send to empty group (should fail gracefully) ----
echo "--- create empty group, send should fail ---"
"$A2A" group create empty-group
if "$A2A" send --from pl-01 @empty-group "hello" 2>&1; then
    echo "ERROR: send to empty group should have failed"
    exit 1
else
    echo "OK: send to empty group correctly rejected"
fi
echo

# ---- Test: invalid group names ----
echo "--- invalid group names ---"
if "$A2A" group create "spaces are bad" 2>&1; then
    echo "ERROR: spaces should be rejected"
    exit 1
else
    echo "OK: spaces in group name rejected"
fi
if "$A2A" group create "" 2>&1; then
    echo "ERROR: empty name should be rejected"
    exit 1
else
    echo "OK: empty group name rejected"
fi
echo

# ---- Test: @ prefix is stripped ----
echo "--- @ prefix handling ---"
"$A2A" group create "@with-at"
"$A2A" group show "with-at"
echo

# ---- Test: group delete ----
echo "--- delete @empty-group ---"
"$A2A" group delete empty-group
"$A2A" group list
echo

# ---- Final bus dump ----
echo "== final bus =="
"$A2A" peek --limit 50
echo

# ---- Verify counts ----
echo "== verification =="
TOTAL_MSGS=$("$A2A" peek --limit 100 --json | python3 -c "
import json, sys
msgs = json.load(sys.stdin)
print(len(msgs))
")
echo "total bus messages: $TOTAL_MSGS"

# PL->@qa messages should be 3 (each PL sent to @qa, which fans out to 2 members = 6 messages)
# PL->PO messages: 2
# QA replies: 2
# Total expected: at least 10
if [ "$TOTAL_MSGS" -ge 10 ]; then
    echo "SMOKE TEST: PASS"
    exit 0
else
    echo "SMOKE TEST: FAIL (expected >=10 messages, got $TOTAL_MSGS)"
    exit 1
fi
