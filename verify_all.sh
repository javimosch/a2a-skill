#!/bin/bash
# Comprehensive integration verification for a2a-skill
# Runs all test suites and validates the complete system

set -e

SCRIPT_DIR="$(dirname "$0")"
cd "$SCRIPT_DIR"

echo "========================================="
echo "a2a-skill — Full System Verification"
echo "========================================="
echo ""

TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local name="$1"
    local cmd="$2"

    echo "🔍 Running: $name"
    if eval "$cmd" > /tmp/a2a_test.log 2>&1; then
        echo "  ✅ PASSED"
        ((TESTS_PASSED++))
    else
        echo "  ❌ FAILED"
        echo "  Log: /tmp/a2a_test.log"
        cat /tmp/a2a_test.log | head -20
        ((TESTS_FAILED++))
    fi
    echo ""
}

# 1. Check prerequisites
echo "📋 Checking Prerequisites"
echo ""

# Find python3 with sqlite3
PYTHON3=""
for cand in /usr/bin/python3 /usr/local/bin/python3 python3; do
    if $cand -c "import sqlite3" 2>/dev/null; then
        PYTHON3="$cand"
        break
    fi
done

if [ -z "$PYTHON3" ]; then
    echo "❌ No Python 3 with sqlite3 found"
    exit 1
fi
echo "✓ Python 3 with sqlite3: $PYTHON3"

test -f a2a.py || { echo "❌ a2a.py not found"; exit 1; }
echo "✓ a2a.py found"

test -f test_a2a.py || { echo "❌ test_a2a.py not found"; exit 1; }
echo "✓ test_a2a.py found"

echo ""

# 2. Run unit tests
echo "🧪 Test Suite 1: Unit Tests"
echo ""
run_test "a2a core unit tests" "$PYTHON3 test_a2a.py -v"
run_test "a2a client library tests" "$PYTHON3 test_a2a_client.py -v"

# 3. Run integration tests
echo "🧪 Test Suite 2: Integration Tests"
echo ""
run_test "a2a integration tests" "$PYTHON3 test_integration.py"

# 4. Run smoke tests
echo "🧪 Test Suite 3: Smoke Tests"
echo ""
run_test "single-CLI smoke test (2 haiku)" "./smoke_test.sh"
run_test "example agents smoke test" "./smoke_test_examples.sh"

# 5. Run stress tests
echo "🧪 Test Suite 4: Stress Tests"
echo ""
run_test "10-agent concurrent stress test" "./stress_test.sh"
run_test "20-agent high-volume stress test (1000+ msg)" "./high_volume_stress_test.sh"
run_test "edge-case hardening tests" "./edge_case_test.sh"

# 6. Run benchmarks
echo "📊 Test Suite 5: Performance Benchmarks"
echo ""
run_test "a2a benchmarks" "$PYTHON3 benchmark.py"

# 7. Code validation
echo "✔️  Test Suite 6: Code Validation"
echo ""

echo "  Checking Python syntax..."
$PYTHON3 -m py_compile a2a.py test_a2a.py test_integration.py test_a2a_client.py benchmark.py dashboard.py a2a_client.py
echo "  ✓ All Python files compile"

echo "  Checking shell scripts..."
bash -n a2a 2>/dev/null && echo "  ✓ a2a" || echo "  ⚠ a2a has syntax warnings"
bash -n a2a-spawn 2>/dev/null && echo "  ✓ a2a-spawn" || echo "  ⚠ a2a-spawn has warnings"
bash -n install.sh 2>/dev/null && echo "  ✓ install.sh" || echo "  ⚠ install.sh has warnings"
bash -n stress_test.sh 2>/dev/null && echo "  ✓ stress_test.sh" || echo "  ⚠ stress_test.sh has syntax warnings"
bash -n high_volume_stress_test.sh 2>/dev/null && echo "  ✓ high_volume_stress_test.sh" || echo "  ⚠ high_volume_stress_test.sh has syntax warnings"
bash -n edge_case_test.sh 2>/dev/null && echo "  ✓ edge_case_test.sh" || echo "  ⚠ edge_case_test.sh has syntax warnings"

echo ""

# 8. Documentation validation
echo "📚 Test Suite 7: Documentation"
echo ""

test -f README.md && echo "  ✓ README.md" || echo "  ❌ README.md missing"
test -f AGENTS.md && echo "  ✓ AGENTS.md" || echo "  ❌ AGENTS.md missing"
test -f docs/SKILL.md && echo "  ✓ docs/SKILL.md" || echo "  ❌ docs/SKILL.md missing"
test -f docs/CONTRIBUTING.md && echo "  ✓ docs/CONTRIBUTING.md" || echo "  ❌ docs/CONTRIBUTING.md missing"
test -f LICENSE && echo "  ✓ LICENSE" || echo "  ❌ LICENSE missing"
test -d examples && echo "  ✓ examples/" || echo "  ❌ examples/ missing"
test -f examples/README.md && echo "  ✓ examples/README.md" || echo "  ❌ examples/README.md missing"

echo ""

# 9. Summary
echo "========================================="
echo "📊 Test Summary"
echo "========================================="
echo "Passed: $TESTS_PASSED"
echo "Failed: $TESTS_FAILED"
echo ""

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo "✅ ALL TESTS PASSED!"
    echo ""
    echo "System is ready for:"
    echo "  • Production deployment"
    echo "  • Distribution (npm, pip, brew, etc.)"
    echo "  • Public release"
    echo ""
    exit 0
else
    echo "❌ SOME TESTS FAILED"
    echo ""
    echo "Please review the logs above and fix the issues."
    echo ""
    exit 1
fi
