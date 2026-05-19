# AGENTS.md — guide for future agents working on this repo

This file tells AI coding agents (and humans) how to safely and effectively
work on **a2a-skill**. Read this first.

## What this project is

A peer-to-peer messaging skill for agentic CLI sessions. N agents from any
CLI (`claude`, `opencode`, `pi`, …) share a SQLite bus at
`~/.a2a/{project}/database.db` and talk to each other directly — no
orchestrator, no central chain of command.

**Core** (stdlib-only, zero deps):
- `a2a.py` — CLI: 14 commands (init, register, send, recv, peek, list, status, wait, clear, project, unregister, search, stats, thread)
- `a2a` — bash wrapper that auto-locates python3+sqlite3
- `a2a-spawn` — per-CLI launcher that hides flag differences

**Python client library** (v1.1+):
- `a2a_client.py` — sync client (A2AClient base class)
- `a2a_client_async.py` — async client (aiosqlite)

**v1.3 satellite modules** (optional, extend the base client):
- `a2a_audit.py` — audit logging (AuditClient, AuditContextManager)
- `a2a_crypto.py` — end-to-end encryption (CryptoClient; requires `cryptography`)
- `a2a_fts.py` — full-text search (FTSClient; uses SQLite FTS5)
- `a2a_priority.py` / `a2a_priority_async.py` — priority queuing (PriorityClient)
- `a2a_routing.py` / `a2a_routing_async.py` — rule-based routing (RoutingClient)
- `a2a_git_aware.py` — git-state-aware bus queries

**Multi-language clients** (v1.2+):
- `a2a_client.go` — Go client
- `a2a_client.js` — Node.js client
- `src/lib.rs` — Rust client (Cargo workspace)

**Skill spec**: `SKILL.md` (root) and `docs/SKILL.md` (canonical) — Claude Code
reads the root copy; always edit docs/ then `cp docs/SKILL.md ./SKILL.md`.

## Repository layout

```
a2a-skill/
├── a2a                   bash wrapper
├── a2a.py                CLI (stdlib only)
├── a2a-spawn             per-CLI launcher
├── SKILL.md              skill spec (copy of docs/SKILL.md — do not edit directly)
├── README.md
├── AGENTS.md             this file
├── LICENSE
├── install.sh
├── a2a_client.py         sync Python client (A2AClient)
├── a2a_client_async.py   async Python client
├── a2a_audit.py          v1.3: audit logging
├── a2a_crypto.py         v1.3: encryption
├── a2a_fts.py            v1.3: full-text search
├── a2a_priority.py       v1.3: priority queuing (sync)
├── a2a_priority_async.py v1.3: priority queuing (async)
├── a2a_routing.py        v1.3: routing rules (sync)
├── a2a_routing_async.py  v1.3: routing rules (async)
├── a2a_git_aware.py      v1.3: git-aware bus queries
├── a2a_server.py         REST API server
├── a2a_client.go         Go client
├── a2a_client.js         Node.js client
├── src/lib.rs            Rust client
├── test_a2a.py           unit tests (47)
├── test_a2a_client.py    Python client tests (12)
├── test_integration.py   integration tests (18)
├── test_v13_features.py  v1.3 satellite module tests (30)  ← 95 tests total
├── benchmark.py
├── dashboard.py
├── examples/             AGENTS.md documents patterns
├── completion/           AGENTS.md documents shell completions
├── docs/                 AGENTS.md documents doc ownership
└── src/                  AGENTS.md documents Rust crate
```

## Database schema

`~/.a2a/{project}/database.db` (WAL mode for concurrent writers):

- `agents(id, role, prompt, cli, status, pid, created_at, last_seen)`
- `messages(id, sender, recipient, body, thread_id, created_at)` —
  `recipient = NULL` means broadcast
- `reads(agent_id, message_id, read_at)` — per-agent unread tracking

Project name resolves from `--project NAME` > `$A2A_PROJECT` > `basename($PWD)`.

## Mental model

- The **bus is the source of truth**. Anything not on the bus did not happen.
- **Read-tracking is per-agent**. A broadcast is seen once by each peer.
- **No locking primitives**. Coordination is by convention — the kit prompt
  tells each agent how to behave. Agents *can* step on each other; the design
  is "free communication," not "consensus."
- The CLI is **stateless** between invocations. Every command opens the db,
  does its work, closes it.

## The WAL invariant (mandatory for every new db entry point)

Every place that calls `sqlite3.connect()` or `aiosqlite.connect()` **must**:

1. Create the parent directory before connecting.
2. Set WAL journal mode and busy timeout immediately after connecting.

**Python sync pattern** (copy verbatim):
```python
def _connect(self):
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(self.db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn
```

**Python async pattern** (for cached-connection clients):
```python
async def _connect(self):
    if self._conn is None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path), timeout=10.0)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
    return self._conn
```

**Why**: Without this, any module that opens the database before `a2a init`
runs will land in SQLite's default `delete` journal mode. Concurrent writers
will deadlock. This was the root cause of the v1.3 WAL gap fixed in commits
17f30d7, 09361ec, and 49d7093.

All language clients (Python sync/async, Node.js, Go, Rust) were upgraded
in v1.3.1 to apply mkdir + WAL + busy_timeout=5000 on every connection.
No prior `a2a init` is required by any client.

## How to extend safely

### Adding a new CLI command

1. Add a `cmd_<name>(args)` function in `a2a.py`.
2. Wire it up in `build_parser()` (new subparser).
3. Cover the happy path in `smoke_test.sh` so regressions are visible.
4. Keep dependencies to **Python stdlib only** — no `pip install`. The whole
   point of the bash wrapper is that we run anywhere with sqlite3.

### Adding support for a new agentic CLI

Edit `a2a-spawn`:

1. Add a `case "$CLI"` branch.
2. Decide whether the CLI has an `--append-system-prompt`-style flag. If yes,
   pass `$KIT` there. If no, embed the kit in the first user message.
3. Don't forget `--dangerously-skip-permissions` or its equivalent so the
   agent can call `bash` non-interactively.
4. Verify the CLI can be invoked **without a TTY** (background-friendly).
   `opencode` itself is aliased to `opencode-tmux` which requires a real
   terminal — we resolve to `~/.opencode/bin/opencode` instead.

### Changing the kit prompt

The kit prompt (in `SKILL.md` Step 4 and inlined into both smoke tests)
is the agents' rulebook. When changing it:

- Keep it terse. Agents pay per-token.
- The locator snippet at the top must work whether or not `a2a` is on PATH.
- Always include the **hard cap** (5-8 iterations + "3 empty recvs = done").
  Without it, idle agents loop forever and burn budget.

## Common pitfalls (and how to avoid them)

| Pitfall | Fix |
|---|---|
| `python3` doesn't have `sqlite3` (custom-compiled Python) | The wrapper probes `/usr/bin/python3`, `/usr/local/bin/python3`, etc. Don't hardcode a path. |
| Agents invent peers that don't exist | Kit prompt tells them to read `a2a list --json` first. Verify by inspecting `peek` after a run. |
| Smoke test "hangs" | Each kit prompt has a hard iteration cap and `--max-turns` on the CLI. If a CLI ignores `--max-turns`, add `timeout N` in the spawn. |
| Cross-CLI: model id format differs per CLI | `claude -p --model haiku` works; opencode wants `provider/model` (e.g. `opencode-go/deepseek-v4-flash`); pi wants `--provider X --model Y` split. Surfaced via `a2a-spawn` flags. |
| `opencode run` printing to stdout instead of acting | Make sure `--dangerously-skip-permissions` is set, otherwise it asks for shell-tool approval and just prints. |
| Many concurrent writers corrupt SQLite | We use WAL + 5s busy timeout. Don't switch off WAL. |
| `cmd_peek` calls `cleanup_expired()` but deletes vanish | Any non-read operation (DELETE, INSERT, etc.) must be followed by `conn.commit()`. `cleanup_expired` deletes rows but doesn't commit — the caller must. |

## Running the tests

### Unit tests (28 tests, stdlib only)

```bash
python3 test_a2a.py -v
```

Covers: DB schema, WAL mode, agent registration & upsert, send/recv,
read-tracking, broadcast, self-message filtering, `--include-self`,
`--ttl` expiry & cleanup, thread IDs, status transitions, project info.

### Integration tests

```bash
python3 test_integration.py -v
```

Shells out to the `a2a` binary and verifies full workflows: register→send→recv,
TTL expiry, broadcast, cross-project isolation, concurrent agents.

### Smoke tests

```bash
# 2 claude haiku peers
./smoke_test.sh

# 3 peers across claude + opencode + pi
./smoke_test_multi.sh

# Example agent patterns
./smoke_test_examples.sh

# Custom project name
./smoke_test_multi.sh my-test
```

The tests `clear --yes` the bus at start, then assert each peer sent at least
one message and that everyone ended with `status='done'`.

### Performance benchmarks

```bash
python3 benchmark.py
```

Measures message latency (~82ms), throughput (~14 msg/s), broadcast latency,
TTL overhead, and blocking recv timeout behavior.

## Style

- Bash scripts: `set -u` (or `set -eu` where appropriate), no bashisms in
  POSIX-portable spots.
- Python: stdlib only, 4-space indent, type hints where they help readability.
- SKILL.md: code blocks must be runnable copy-paste. Test them.

## Things this project deliberately does *not* do

- **No encryption.** The bus is cleartext on the local FS. Trust model: a
  shared local environment. Add encryption if remoting the db.
- **No central orchestrator.** That's the point. If you find yourself adding
  one, you are building a different project.
- **No TTL/expiry on messages.** The db grows. `a2a clear --yes` resets.
- **No auth.** Anyone with FS access to `~/.a2a/{project}/database.db` can
  read or write the bus.

## Contributor Resources

Development resources for agents working on the a2a-skill codebase live **outside** the repo
at `~/ai/a2a-dev/`. They do not ship to users who clone this repo.

Access them via the global skill:
```
~/.agents/skills/a2a-dev/SKILL.md   ← hub; indexes all contributor sub-skills
~/ai/a2a-dev/skills/team-coordination/SKILL.md   ← CLAIM/ROLE-CROSS protocols
~/ai/a2a-dev/skills/a2a-roadmap/SKILL.md         ← v1.4 priorities
~/ai/a2a-dev/skills/a2a-enhancements/SKILL.md    ← integration opportunities
~/ai/a2a-dev/skills/a2a-skill-experience/SKILL.md ← sprint learnings
~/ai/a2a-dev/skills/a2a-supervision/SKILL.md     ← supervision lessons
```

**Boundary rule:** `docs/` is for users of a2a. `~/ai/a2a-dev/` is for contributors.
Nothing development-process-related goes in `docs/` or `.agents/skills/` (except `.agents/skills/a2a/`).

## When you ship a change

1. Run **both** smoke tests on a clean bus (`./a2a clear --yes`).
2. Update `README.md` if the public surface changed.
3. Update relevant files in `docs/` if documentation changed.
4. Update `SKILL.md` if agent-facing behavior changed.
5. Add a row to "Common pitfalls" if you hit (and fixed) a new one.

## Author & license

Author: **Javier Leandro Arancibia**.
License: **MIT** — keep the copyright notice in derivative works.
