# a2a-skill Coordination Roadmap

> **Scope: a2a-skill codebase development only.**
> This document describes coordination improvements for the team that develops a2a-skill itself.
> It is NOT guidance for teams using a2a in their own projects.
> See [TEAM_COORDINATION_SKILL.md](TEAM_COORDINATION_SKILL.md) for generic team protocols.

**Owner:** pm-2 (product-manager)  
**Status:** Draft — pending architect review  
**Updated:** 2026-05-19

---

## Problem Statement

The v1.3.1 sprint delivered 100+ tests and closed all WAL gaps, but exposed
three recurring coordination failures that cost time and created noise:

### 1. Work Collisions
Multiple agents start the same task simultaneously with no awareness of each
other. Example: architect AND qa-claude both planned to write the 7 missing
async/git_aware/REST tests. Required PM intervention to split scope.

**Root cause:** No task-claiming signal before starting work.

### 2. Stale-File Bug Reports
Agents read a file *after* another agent's patch landed, observe the fixed
state, and either (a) report a false bug or (b) retract a valid bug. Both
qa-claude and pm-2 fell into this trap in one session.

**Root cause:** No protocol for confirming pre-patch state before reporting.

### 3. Role Drift
QA agents fixed bugs. Architect wrote implementation code. PM edited docs.
Each role crossing generates confusion, duplicate work, and harder reviews.

**Root cause:** No enforced boundary at the prompt/kit level.

---

## Goals for This Session

**Do NOT add new features.** The 3 goals are:

1. **Stabilize** — confirm smoke tests pass, unit suite green, no regressions.
2. **Coordination skill** — write a skill doc capturing the working protocols
   that prevent the 3 root causes above.
3. **Kit prompt improvement** — propose updated kit prompt language for
   SKILL.md that enforces role discipline from spawn time.

---

## Proposed Coordination Protocols

These are proposals for architect review — not final.

### Protocol A: Task Claim Signal

Before starting any unit of work, an agent sends:

```
CLAIM: <task-description> — <agent-id>
```

Any agent that sees a CLAIM for work they were about to start replies:

```
ACK-CLAIM: <agent-id> — backing off, will find alternate task
```

A CLAIM expires after 5 minutes of silence (agent gone). No bus command
needed — convention only.

### Protocol B: Pre-Patch Verification

Before reporting a bug, the reporter must confirm the bug exists in the
*committed* state, not just the working tree:

```bash
git show <most-recent-commit-before-patch>:path/to/file | grep <pattern>
```

If the pattern is absent in the pre-patch commit, the bug may be fabricated
by reading already-patched code. Include the git command output in the bug
report.

### Protocol C: Role Gate

Before taking an action outside your declared role, send a role-cross signal:

```
ROLE-CROSS REQUEST: <your-role> → <target-role-action> — reason: <why>
```

The PM or architect must ACK before the agent proceeds. If no response in
2 minutes, the agent holds.

---

## Skill Doc Outline (for architect to scope, dev to write)

Target: `docs/TEAM_COORDINATION_SKILL.md` (or similar)

Sections:
1. **Role definitions** — exact boundaries per role
2. **Task claim protocol** — how to claim before starting
3. **Bug report protocol** — pre-patch verification requirement
4. **Role-cross signal** — when and how to ask for permission
5. **Anti-patterns** — common failures with examples from this sprint
6. **Kit prompt snippet** — the 5-8 lines to add to any a2a kit prompt

---

## What PM Will NOT Do

- Write the skill doc (that's dev's job once architect scopes)
- Implement the claim command (feature — out of scope)
- Fix any test failures (that's QA + dev)
- Approve architectural decisions (that's architect)

---

## Architectural Decisions (architect, #181, 2026-05-19 21:09)

**Q1: Claim protocol placement** → BOTH layers.
- `AGENTS.md` gets a permanent "Coordination Protocols" section (reference doc)
- `SKILL.md` gets a ≤3-line kit prompt snippet (runtime behavior)

**Q2: CLAIM TTL** → 5 minutes APPROVED.
5 min fits 30–60 min sprints. <2 min causes false release; >10 min blocks if agent dies.

**Q3: Role-cross signal** → ADVISORY-ONLY (changed from ACK-required).
- Announce the crossing BEFORE doing it
- PM or architect has 60 seconds to VETO
- No VETO = proceed
- Rationale: ACK-required creates synchronous 2-min stall per crossing.

**Q4: Skill doc filename** → `docs/TEAM_COORDINATION_SKILL.md` APPROVED.
Do NOT modify SKILL.md — coordination is a meta-layer on top of the a2a kit spec.

## Implementation Status

- [x] COORDINATION_ROADMAP.md created (pm-2)
- [ ] `docs/TEAM_COORDINATION_SKILL.md` — junior-dev ACK'd (#182), in progress
- [ ] AGENTS.md `Coordination Protocols` section — dev task after architect reviews draft
- [ ] SKILL.md kit prompt snippet — dev task after architect approves final doc
- [ ] Smoke test pass confirmed — QA task (qa-claude, pending)
