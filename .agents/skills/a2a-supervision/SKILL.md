---
name: a2a-supervision
description: Lessons, pitfalls, and caveats from supervising the live a2a-skill implementation across multiple multi-agent collaboration sprints (23:04-00:20, 2026-05-18). Useful for any agent working on or with the a2a peer-messaging system.
---

# a2a-supervision — Lessons from the a2a-skill Live Build

## Overview

This skill captures what I (pi-qa) learned while supervising the a2a-skill
implementation over ~70 minutes of live multi-agent collaboration on the a2a
bus itself. It covers the project's architecture, the collaboration patterns
that worked, the bugs we hit, and the design decisions worth remembering.

---

## Repository Layout

```
a2a-skill/
├── a2a                    [bash]   Shell wrapper — finds python+sqlite3, caches to .a2a_python
├── a2a.py                 [python] Core CLI — 593 lines (this is the heart)
├── a2a_client.py          [python] Python client library (missing search/thread/stats — v1.1.1 gap)
├── a2a-spawn              [bash]   CLI-agnostic peer launcher (claude/opencode/pi)
├── install.sh             [bash]   Symlinks to PATH + ~/.claude/skills/ + ~/.agents/skills/
├── SKILL.md               [doc]    The /a2a skill spec for Claude Code
├── README.md              [doc]    Overview, install cheatsheet
├── AGENTS.md              [doc]    Agent collaboration guide
├── docs/review.md         [doc]    Live supervision log (this review)
├── test_a2a.py                    30 unit tests
├── test_integration.py            18 CLI-level integration tests
├── test_a2a_client.py             12 client library tests
├── stress_test.sh                 10-agent stress test
├── smoke_test.sh / smoke_test_multi.sh  End-to-end smoke tests
├── examples/                      5 example agents (researcher, reviewer, coordinator, critic, debugger)
├── a2a_client.py / a2a_client.py  Python + Rust + Go client libraries
├── benchmark.py / dashboard.py    Performance tools
└── src/lib.rs + Cargo.toml        Rust client library
```

---

## Architecture

### Storage
- **SQLite** at `~/.a2a/{project}/database.db` — WAL mode, busy_timeout=5000ms
- **3 tables:** `agents`, `messages`, `reads`
- **Broadcast** via `recipient IS NULL`
- **Read tracking** per agent via `reads` table (agent_id, message_id)

### Schema (messages table)
```sql
CREATE TABLE messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sender      TEXT NOT NULL,
    recipient   TEXT,                  -- NULL = broadcast
    body        TEXT NOT NULL,
    thread_id   TEXT,
    ttl_seconds INTEGER,               -- NULL = never expire
    created_at  REAL NOT NULL
);
```

### CLI Commands (v1.1)
| Command | Purpose |
|---|---|
| `a2a init` | Create project database |
| `a2a register` | Register an agent on the bus |
| `a2a unregister` | Remove an agent |
| `a2a list` | List agents (--json) |
| `a2a status` | Update agent state |
| `a2a send` | Send message (--ttl, --thread, --from) |
| `a2a recv` | Receive messages (--wait, --all, --peek, --include-self, --since) |
| `a2a peek` | Observer view (--limit, --json) |
| `a2a search` | Substring search (--json, --limit) |
| `a2a thread` | View thread by id (--json) |
| `a2a stats` | Bus statistics (--json) |
| `a2a wait` | Block until N unread messages |
| `a2a project` | Show project info |
| `a2a clear` | Wipe database (--yes) |

---

## Collaboration Patterns That Worked

### 1. Peer Kit Prompt
Every spawned agent receives a kit prompt that bootstraps it onto the bus:

```
You are agent "{AGENT_ID}" on an a2a peer bus.
Role: {ROLE}
Instruction: {USER_PROMPT}

== Peers ==
{PEER_LIST}

== Commands ==
  a2a list --json
  a2a recv --as {AGENT_ID} --wait 30
  a2a send <peer-id> "msg" --from {AGENT_ID}
  a2a status done --as {AGENT_ID}

== Loop ==
1. recv --as {AGENT_ID} --wait 30
2. Decide: respond / ask / broadcast / finish
3. Send if needed
4. If done → status done + exit
5. Repeat
```

### 2. Broadcast for Announcements
Agents use `a2a send all "..." --from <id>` for:
- Joining the bus (welcome message)
- Feature delivery notifications
- Sprint completion signals
- Status updates visible to all peers

### 3. Direct Messages for Tasking
Agents use `a2a send <peer-id> "..." --from <id>` for:
- Task assignments
- Code review requests
- QA reports
- Bug fix coordination

### 4. QA Sprint Pattern
```
main-dev: "I shipped X, ready for QA"
pi-qa:    "Reviewing... PASS ✅ (or: found issue Y)"
main-dev: "Fixed Y, re-pushed"
pi-qa:    "Re-verified, PASS ✅"
```

### 5. Product Manager Role
A `product-manager` agent that:
- Assesses overall project state
- Identifies gaps
- Prioritizes a sprint backlog
- Assigns work to agents
- Produces milestone docs

---

## Pitfalls Encountered

### 1. `cmd_peek` Not Committing After Cleanup
**Bug:** `cmd_peek` called `cleanup_expired()` but never called
`conn.commit()`. The deletes were lost on connection close.
Stale messages continued appearing despite being past TTL.

**Fix:** Add `conn.commit()` after `cleanup_expired(conn)`.

**Lesson:** Any mutation on a SQLite connection must be committed.
Don't assume cleanup functions commit — check.

### 2. Schema Changes Require DB Rebuild
When `ttl_seconds` was added to the messages table, existing databases
lacked the column. The `CREATE TABLE IF NOT EXISTS` in `connect()` doesn't
ALTER existing tables.

**Fix:** `a2a clear --yes && a2a init` (all agents must re-register).

**Lesson:** Schema migrations need a plan. For v1, clear+reinit is
acceptable. For production, add ALTER TABLE migration.

### 3. New CLI Flags Break Manual Namespace Tests
When `--include-self` was added, all existing tests that constructed
`argparse.Namespace` objects manually started failing with
`AttributeError: 'Namespace' object has no attribute 'include_self'`.

**Fix:** Every Namespace needed `include_self` added.

**Lesson:** Tests using manual Namespace construction are brittle.
Consider a helper that builds defaults from the real argparse parser,
or use `unittest.mock.patch` to inject args.

### 4. Python sqlite3 Module Not Everywhere
The system Python 3.11.2 on this machine lacks `_sqlite3`. The `a2a`
bash wrapper probes multiple Python versions and caches the working one
in `.a2a_python`.

**Fix:** `a2a` wrapper (`pick_python()` function).

**Lesson:** Never assume `python3` has stdlib modules. Always probe
at install/startup time.

### 5. Bus-vs-Git State Gap (Architecture)
> "The bus carries conversation, not code state."

Agents flag gaps that were already fixed because they read the bus
(messages) but not `git log` (code reality). Example: a client library
gap was flagged 60s after the fix was committed, because no bus message
announced the fix.

**Mitigations:**
1. After fixing a flagged gap, always send a bus message:
   `a2a send all "Fixed: added search/thread/stats to client lib"`
2. Kit prompt: "After a gap is flagged, verify by checking git before acting"
3. Consider a bot agent that monitors commits and broadcasts summaries

### 6. Read Tracking Filters Self-Sent Messages
By default, `recv` filters out messages where `sender == agent_id`.
This prevents agents from seeing their own messages — useful for
production but confusing during debugging.

**Fix:** `--include-self` flag on `recv`.

**Lesson:** Default behavior should be safe for production. Add flags
for debugging.

---

## Caveats & Known Gaps

### Feature Gaps
| Gap | Impact | Planned Fix |
|---|---|---|
| No FTS5 (LIKE-based search only) | Slow on 1000s of messages | v1.2 with SQLite FTS5 |
| No message editing/withdrawal | Agents can't correct mistakes | v1.2 |
| Python client missing search/thread/stats | Can't use these via client lib | v1.1.1 patch |
| No encryption (cleartext SQLite) | Not for untrusted networks | v1.2 (encryption layer) |
| Graceful SIGTERM in a2a-spawn | Background processes may orphan | v1.2 |
| No --include-self in test assertions | Tests only check "no crash" not output content | Backlog |

### Design Trade-offs
| Decision | Why | Cost |
|---|---|---|
| SQLite (not Redis/Postgres) | Zero deps, file-based, WAL for concurrency | No network bus, single host |
| LIKE search (not FTS5) | Simpler, no schema change | Slower at scale |
| Manual Namespace tests | Direct function calls, no CLI overhead | Brittle to new flags |
| WAL mode | Concurrent writers | Slightly larger DB files |
| No daemon process | Keep it simple, agents poll | Latency vs push |

### Testing
- **30 unit tests** — DB schema, agent registry, messaging, edge cases, TTL, search, stats
- **18 integration tests** — CLI-level workflows (send/recv/peek/status/ttl/unregister)
- **12 client tests** — Python client library API coverage
- **1 stress test** — 10 concurrent agents
- **Total: 65 tests passing**

---

## Operations Notes

### Quick Start on a Fresh Bus
```bash
export A2A_PROJECT=my-project
a2a init
a2a register my-agent --role helper --cli pi
a2a list
a2a recv --as my-agent --wait 30
```

### Reading This Skill
If you are an agent reading this file at runtime, you can use the
a2a-skill itself to collaborate. The bus at `~/.a2a/{project}/database.db`
is persistent across sessions.

### Key Files to Read
| File | Why |
|---|---|
| `a2a.py` | Core CLI — read this to understand the protocol |
| `SKILL.md` | The /a2a skill spec — read this to understand agent spawning |
| `test_a2a.py` | Unit tests — read this to understand edge cases |
| `a2a_client.py` | Python client library — read this for programmatic use |

---

## Timeline (2026-05-18)

| Time | Event |
|---|---|
| 23:04 | Supervision starts, `a2a.py` appears |
| 23:06 | SKILL.md + README |
| 23:07 | install.sh + smoke_test.sh |
| 23:15–23:22 | Session 2: a2a-spawn, cross-CLI smoke test |
| 23:25–23:34 | Session 3: --include-self, TTL, QA sprint with main-dev |
| 23:34–23:50 | Session 4: mario joins, peek commit bug, docs pass |
| 23:50–00:10 | Session 5: v1.1 features (search, thread, stats), stress test |
| 00:10–00:20 | Session 6: Rust/Go clients, REST API, work-collision-reviewer |
