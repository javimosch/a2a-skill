# a2a-skill v1.4 Roadmap

**Owner:** pm-2  
**Status:** Draft — for architect review  
**Updated:** 2026-05-19

---

## Guiding Principle

v1.4 is a **coordination release**, not a feature release. The theme is:
*make a2a teams work better by default, not just when they read the docs.*

---

## What's Already Done (update existing lists)

These items previously marked as future work are now shipped:

| Item | Status | Commit |
|------|--------|--------|
| FTS5 full-text search | ✅ Done | 77ce5c5, 848e9dd, 2f255bb |
| REST API (HTTP server) | ✅ Done | a2a_server.py |
| Git-aware bus queries | ✅ Done | a2a_git_aware.py |
| Async clients | ✅ Done | a2a_priority_async, a2a_routing_async |
| WAL invariant (all 4 languages) | ✅ Done | 4fcf652, 150c8b6, 5c30c02 |

---

## v1.4 Scope (coordination focus)

### Priority 1 — Kit prompt with coordination rules built-in

**What:** Add the `TEAM_COORDINATION_SKILL.md` kit prompt snippet to the
default kit template in `SKILL.md` Step 4 — so every spawned team gets it
automatically. Teams that don't want it can strip the `== Coordination rules ==`
block.

**Why:** The protocols only work if every agent gets them at spawn time. A
separate doc no one reads doesn't prevent collisions.

**Scope:** 6-line addition to SKILL.md. Architect must review the exact
insertion point. **No new commands.**

**Owner:** dev (once architect approves insertion point)

---

### Priority 2 — `a2a list --status done` filter + `a2a list --available`

**What:** Two new list filters:
- `a2a list --status done` — show only done agents (for replacement scanning)
- `a2a list --available` — show done agents whose roles aren't currently held
  by an active agent (the "who can I replace?" query)

**Why:** Agents joining a team currently list all agents and manually identify
done slots. This is slow and error-prone. A direct query reduces friction.

**Scope:** 2 new flags on the existing `list` command. No schema changes.
Architect must approve implementation approach.

**Owner:** dev (architect must spec the query logic first)

---

### Priority 3 — `a2a claim <task-id>` as a first-class bus message type

**What:** A lightweight convention for CLAIM messages that can be verified
programmatically. Implementation: `a2a send ALL "CLAIM: <task>" --tag claim`
using a new `--tag` flag, or simply a message body prefix convention that
`a2a search "CLAIM:"` can surface quickly.

**Note:** The coordination skill doc already defines CLAIM as a text
convention. This would make it searchable without a new CLI command.

**Why:** As teams grow (5+ agents), text CLAIMs are hard to search and easy
to miss. A tagged search makes collision detection practical.

**Scope:** `--tag` flag on `send`, tag filtering on `search`. One schema
column addition (`tags TEXT`). Architect must evaluate complexity vs benefit.

**Status:** Lower priority — only if Priority 1+2 are done first.

**Owner:** architect to evaluate; dev to implement if approved

---

### Priority 4 — Async test runtime (aiosqlite install)

**What:** 23 async tests are skip-guarded due to missing aiosqlite.
Install aiosqlite so the async suite runs in CI.

**Why:** The skip guard was added because the environment lacks aiosqlite,
not because the tests are wrong. 23 tests that never run provide no value.

**Scope:** `pip install aiosqlite` in CI config (docker-compose, GitHub
Actions). No code changes.

**Owner:** dev (trivial — pipeline config only)

---

## What v1.4 Is NOT

- New protocol modules (v1.3 already has crypto, audit, priority, routing)
- WebSocket API (v1.5 or later)
- gRPC (v2.0)
- Connection pooling (premature — throughput is already 14 msg/s which is fine)
- Message compression (premature)

---

## Open Questions for Architect

1. **Priority 1 (Kit prompt injection):** Which line in SKILL.md Step 4?
   Before or after the hard-cap rule? The snippet must not push the total
   kit over the token budget for haiku-class models.

2. **Priority 2 (list filters):** Should `--available` be a separate command
   or a flag? Is "available" = `status='done' AND role NOT IN (SELECT role FROM
   agents WHERE status='active')`? Confirm the query.

3. **Priority 3 (CLAIM tagging):** Is the complexity of a `tags` column worth
   it, or is `a2a search "CLAIM:"` sufficient? If the latter, no schema change
   needed — Priority 3 collapses to a docs note.

---

## Success Criteria for v1.4

- [ ] Every `a2a-spawn` invocation injects CLAIM + role discipline rules
- [ ] `a2a list --available` returns replacement-candidate agents in <100ms
- [ ] 0 skipped async tests in CI (aiosqlite installed)
- [ ] Smoke tests still pass with updated kit prompt

---

**Next step:** architect reviews this doc and posts decisions on the bus.
pm-2 will update this roadmap with decisions, then assign to dev.
