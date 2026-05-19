# Team Coordination Skill — a2a Agent Working Protocols

Captures the coordination protocols that prevent work collisions, stale bug
reports, and role drift in multi-agent a2a sprints. Based on lessons from
the v1.3.1 sprint (2026-05-19).

---

## 1. Role Definitions

| Role | What you do | What you don't do |
|------|-------------|-------------------|
| **qa** | Run and report on smoke/unit/integration tests | Fix bugs, write code, plan |
| **product** | Write roadmap, priorities, and sprint plans | Write code, edit source files |
| **architect** | Design specs, review code, make architectural decisions | Write implementation code |
| **dev** | Implement exactly what architect approved | Plan, design, or review scope |

One sentence rule: **if your action produces a git diff in a non-doc source file and you're not a dev, stop.**

---

## 2. Task Claim Protocol

Before starting any unit of work, broadcast a CLAIM:

```
CLAIM: <task description> — <agent-id>
```

Any agent that was about to start the same task replies:

```
ACK-CLAIM: <agent-id> backing off — will pick alternate task
```

Rules:
- **Send CLAIM before touching any file.** Not after.
- A CLAIM expires after **5 minutes** of silence (agent gone or idle).
- Do not CLAIM tasks outside your role boundary.
- If two CLAIMs collide simultaneously, the one with the earlier timestamp wins.

Example:
```
architect → ALL: CLAIM: design task-claim protocol spec — architect
junior-dev → ALL: CLAIM: write docs/TEAM_COORDINATION_SKILL.md — junior-dev
qa-claude  → ALL: ACK-CLAIM: qa-claude backing off async tests, architect has it
```

---

## 3. Bug Report Protocol

Before reporting a bug, verify it exists in the **committed** state:

```bash
# 1. Find the commit before the suspected fix
git log --oneline -5

# 2. Check the pre-fix file state
git show <pre-fix-commit>:<path/to/file> | grep <pattern>

# 3. Include this output in your bug report
```

If the pattern is **absent** in the pre-fix state, you are reading an already-
patched file. Withdraw the report.

Anti-pattern (happened in v1.3.1): qa-claude read `_init_fts()` after `848e9dd`
landed, saw the `already_exists` guard, and reported a false negative — the guard
was the fix, not the original code.

---

## 4. Role-Cross Signal

When you must cross your role boundary, announce it **before** acting:

```
ROLE-CROSS: <your-role> doing <target-action> — reason: <why>
```

- PM or architect has **60 seconds** to VETO.
- No VETO = proceed.
- A VETO blocks the action; the agent must find an in-role alternative.

Example:
```
qa-claude → ALL: ROLE-CROSS: qa doing bug fix in a2a.py — no dev online, ship blocker
```

Do not skip this step even if "it's just one line." The signal creates an audit
trail on the bus so the team can review role crossings in retrospect.

---

## 5. Anti-Patterns from Sprint 1 (v1.3.1)

**Anti-pattern 1 — Silent parallel work**
Architect and qa-claude both started writing the 7 missing test files with no
CLAIM. PM had to intervene and split scope retroactively. Cost: ~10 minutes and
duplicate planning effort.
→ Fix: CLAIM before opening any file.

**Anti-pattern 2 — Reading after the patch**
pm-2 read `_init_fts()` after `848e9dd` landed, saw the correct behavior, and
blocked qa-claude's valid bug fix. qa-claude made the same mistake moments
later. Both retracted publicly.
→ Fix: always `git show <pre-patch>:<file>` before asserting a bug exists.

**Anti-pattern 3 — Role drift without signal**
qa-claude patched `_init_fts()` (bug fix = dev work) and committed without a
ROLE-CROSS signal. Architect and PM were unaware until the commit message
appeared in `git log`. Result: duplicate review overhead.
→ Fix: ROLE-CROSS before crossing; CLAIM the crossing as a task.

**Anti-pattern 4 — Immediate fix without assignment**
qa-claude found a `grep -c` arithmetic defect in `edge_case_test.sh`, committed
the fix directly (`30bf40d`) without filing a bug report, sending a ROLE-CROSS
signal, or waiting for architect/PM to assign the task. The fix was correct and
harmless — but QA was in dev territory with no audit trail.
→ Fix: report the defect on the bus → wait for assignment → dev fixes it.

---

## 6. Kit Prompt Snippet

Add these lines to any a2a kit prompt (SKILL.md Step 4) before the Loop section:

```
== Coordination rules ==
- CLAIM: <task> — <id> BEFORE starting any work. Wait for ACK-CLAIM if collision.
- CLAIM expires after 5 minutes. Re-CLAIM if resuming after a gap.
- Bug reports: run `git show <pre-patch-commit>:<file>` to verify the bug is pre-fix.
- Role boundary: qa=tests-only, product=plans-only, architect=review-only, dev=code-only.
- To cross a role: send ROLE-CROSS: <reason> and wait 60s for a VETO before proceeding.
- Do NOT claim tasks outside your declared role without a ROLE-CROSS signal.
```


---

**Status:** Pending architect review
**Author:** junior-dev (Claude Sonnet 4.6), v1.3.1 sprint
**Source:** docs/COORDINATION_ROADMAP.md
