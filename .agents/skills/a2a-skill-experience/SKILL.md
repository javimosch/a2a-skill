---
name: a2a-skill-experience
description: Hard-won lessons, collaboration patterns, pitfalls, and operational knowledge from the a2a-skill multi-agent sprint (2026-05-18, 23:00–00:25 Paris time). 7 agents, 52+ bus messages, 18 commits, 65 tests. For any agent joining future a2a-skill development.
---

# a2a-skill-experience — Multi-Agent Collaboration Learnings

## Sprint Overview

| Metric | Value |
|---|---|
| Duration | ~85 minutes (23:00–00:25) |
| Agents | pi-qa, main-dev, mario-developer, junior-dev, coordinator, product-manager, work-collision-reviewer |
| Bus messages | 84 |
| Commits | 21 on top of v1.0-alpha |
| Tests | 19 → 65 |
| LOC | 453 → 593 (a2a.py core only) |
| v1.1 features | Search, thread view, stats, JSON consistency |
| Multi-language clients | Python, Go, JavaScript |
| Features added | REST API server, dashboard, benchmarks, 5 example agents, CI/CD, stress tests, git-aware features |

---

## Team Roles That Worked

| Role | Agent | Effect |
|---|---|---|
| **Implementer** (main-dev) | claude | Ships features fast, pushes code, responds to QA |
| **QA Engineer** (pi-qa) | pi | Reviews every PR, runs smoke tests, validates edge cases, reports bugs with reproduction steps |
| **Junior Dev** (junior-dev) | pi | Picks up unglamorous tasks (CI/CD, integration tests, docs polish) — great for overflow work |
| **Coordinator** | — | Tracks the sprint plan, assigns tasks, pushes blockers, broadcasts milestones |
| **Product Manager** (product-manager) | opencode | Audits completeness, identifies gaps, prioritizes backlog, locks milestones |
| **Architecture Reviewer** (work-collision-reviewer) | pi | Steps back, identifies cross-cutting design smells, suggests process improvements |
| **Documentation Agent** (mario-developer) | pi | Handles README, AGENTS.md, SKILL.md updates — frees implementers to code |

---

## Collaboration Patterns That Worked

### 1. Broadcast for Awareness
When joining, delivering, or wrapping up — use `a2a send all "..."` so every
agent on the bus sees the state change. Direct messages (`send <peer>`) are
for tasking only.

### 2. QA Sprint Pattern
```
main-dev: "I shipped X, ready for QA"           (broadcast)
pi-qa:    "Reviewing... PASS ✅"                 (direct to dev)
pi-qa:    "15/15 tests, all features verified"   (broadcast summary)
```
This gives both accountability and visibility.

### 3. Product-Manager-Led Sprint
1. PM audits current state (tests, features, docs)
2. PM publishes a gap list with priority (HIGH/MEDIUM/LOW)
3. Coordinator assigns tasks or agents pick them
4. PM validates at sprint end, locks milestone

### 4. "Check Git Before Acting" Protocol
After the work-collision-reviewer's finding, the team adopted:
> "When a gap is flagged, verify git log first, then act."
This prevents re-doing work already committed.

### 5. Commit-Fix-Announce Workflow
```
# Before (broken — silent fix):
git commit -m "fix search bug"
# Bus is silent → agents think bug still exists

# After (fixed — announce):
git commit -m "fix search bug"
a2a send all "Fixed: search now handles empty queries" --from agent-x
```
Always broadcast after fixing a flagged issue.

---

## Pitfalls & Anti-Patterns

### P1. Bus-vs-Git State Divergence
**The problem:** The bus carries conversation, not code state. Agents read
the bus to know what's happening, but the bus doesn't track git history.
Result: agents flag gaps that were already fixed.

**Example:** PM flagged missing client methods (#69). Fix was committed
30s later (#70 bus message? No — just a commit). PM's knowledge stayed
stale until another agent replied.

**Root cause:** The kit prompt says "the bus is the source of truth" —
but it's only the source of *conversation* truth, not *code* truth.

**Mitigations implemented:**
1. `git log`-aware features: `a2a git-log` shows recent commits alongside bus activity
2. Kit prompt rule: "After a gap is flagged, run `git log --oneline -5` before acting"
3. Broadcast fix announcements on the bus

### P2. `cmd_peek` Not Committing After Cleanup
`cmd_peek` called `cleanup_expired()` but never `conn.commit()`. The
deletes were silently rolled back on connection close. Stale TTL-expired
messages reappeared.

**Detection:** mario-developer noticed while testing TTL — peek showed
expired messages still present. Root cause: missing commit after mutation.

**Fix:** Added `conn.commit()` after `cleanup_expired()` in `cmd_peek`.

### P3. Schema Migrations Not Handled
When `ttl_seconds` column was added to the schema, `CREATE TABLE IF NOT EXISTS`
in `connect()` didn't alter existing tables. The `cleanup_expired()` function
crashed on any existing database with `no such column: ttl_seconds`.

**Detection:** junior-dev ran `a2a peek` on an existing bus and got
`sqlite3.OperationalError`.

**Fix:** Added an ALTER TABLE migration in `connect()`:
```python
try:
    conn.execute("SELECT ttl_seconds FROM messages WHERE 1=0")
except sqlite3.OperationalError:
    conn.execute("ALTER TABLE messages ADD COLUMN ttl_seconds INTEGER")
```

### P4. Manual Namespace Tests Are Brittle
Tests hand-construct `argparse.Namespace` objects. Adding a new CLI flag
means every test constructing that command's Namespace must be updated.
Miss one → `AttributeError`.

**Safer approach:** Use a helper that builds Namespace from the real parser
with sensible defaults, then override only what the test needs.

### P5. Python sqlite3 Module Fragility
System Python 3.11.2 may lack `_sqlite3`. The `a2a` bash wrapper probes
multiple Python versions at startup and caches the working one.

**Lesson:** Always probe for stdlib modules at entry. Don't hardcode paths.

### P6. Overlapping Work on the Same Feature
Multiple agents independently implementing the same thing (e.g., both
coordinator and junior-dev wrote integration tests). Mitigated by
broadcasting before starting a task: "Taking integration tests — anyone
already working on this?"

---

## Operational Know-How

### Working Directory
```bash
cd ~/ai/a2a-skill
# The bus is at ~/.a2a/a2a-skill-dev-team/database.db
# Separate from the default project bus at ~/.a2a/a2a-skill/database.db
```

### Key Command Cheatsheet (for agents)
```bash
# Join the bus
export A2A_PROJECT=a2a-skill-dev-team
./a2a register junior-dev --role "junior-dev" --cli pi
./a2a send all "Joining the team!" --from junior-dev

# Work loop
./a2a recv --as junior-dev --wait 30    # check for messages
./a2a send peer-id "msg" --from junior-dev  # respond
./a2a status done --as junior-dev       # sign off

# Observe
./a2a peek --json                       # all recent messages
./a2a search "keyword" --json           # find in history
./a2a stats --json                      # bus statistics
./a2a list --json                       # who's online

# Code
git add -A && git commit -m "msg"
git push                                # share work
```

### Running Tests
```bash
# Full suite (65 tests)
python3.10 -m pytest test_*.py -v

# Individual files
python3.10 test_a2a.py          # 30 unit tests
python3.10 test_integration.py  # 18 integration tests
python3.10 test_a2a_client.py   # 12 client lib tests

# Smoke tests
echo "y" | bash smoke_test.sh
A2A_PROJECT=test bash smoke_test_multi.sh
```

### When Something Is Blocked
1. Check the bus: `./a2a peek --json | python3 -m json.tool`
2. Check git log: `git log --oneline -10`
3. Check test status: `python3.10 -m pytest test_*.py -q`
4. Broadcast the blocker: `./a2a send all "Blocked on X — anyone?" --from my-id`

---

## v1.1 Feature Reference

| Feature | Command | Added By | Notes |
|---|---|---|---|
| Substring search | `a2a search <q> [--json] [--limit N]` | coordinator | LIKE-based, not FTS5 |
| Thread view | `a2a thread <id> [--json]` | junior-dev | Queries thread_id column |
| Bus stats | `a2a stats [--json]` | coordinator | msg count, top senders, etc. |
| JSON consistency | `--json` on status, send | junior-dev | Machine-readable output |
| CI/CD | `.github/workflows/ci.yml` | junior-dev | Python 3.10/3.11/3.12 matrix |
| Integration tests | 18 CLI-level tests | junior-dev | End-to-end workflows |
| Multi-language clients | Python, Go, JS | main-dev + coordinator | v1.2 preview |

---

## Resolved Bugs

| Bug | Fix | Commit | Discovered By |
|---|---|---|---|
| `cmd_peek` not committing after cleanup | Added `conn.commit()` after `cleanup_expired()` | mario-developer | mario-developer |
| Missing `ttl_seconds` column on existing DBs | ALTER TABLE migration in `connect()` | junior-dev | junior-dev |
| `send --json` missing | Added `--json` flag to `cmd_send` | junior-dev | product-manager |
| `--json` help text missing on search/thread/stats | Added `help="output as JSON"` | junior-dev | junior-dev |
| `--help` quick start missing v1.1 commands | Updated epilog | junior-dev | junior-dev |
| Python client missing search/thread/stats | Added methods to `a2a_client.py` | coordinator | product-manager (#69) |

---

## Files to Read (New Agents)

| File | Why |
|---|---|
| `./AGENTS.md` | Project conventions for agents working on the codebase |
| `./SKILL.md` | The /a2a kit prompt and spawn protocol |
| `./a2a.py` | Core CLI — 593 lines, stdlib only |
| `./a2a_client.py` | Python client library |
| `./.agents/skills/a2a-supervision/SKILL.md` | pi-qa's supervision log |
| `./.agents/skills/a2a-skill-experience/SKILL.md` | This file — team learnings |
| `./docs/review.md` | Live supervision timeline |
| `./benchmark.py` | Performance benchmarking suite |
| `./dashboard.py` | Real-time bus dashboard |
| `./examples/` | 5 example agents |
| `./test_a2a.py` | Unit tests — see edge case patterns |
| `./test_integration.py` | Integration tests — CLI workflow patterns |
