# AGENTS.md — guide for future agents working on this repo

This file tells AI coding agents (and humans) how to safely and effectively
work on **a2a-skill**. Read this first.

## Documentation navigation

This repo has a layered documentation system. Use this diagram to find what
you need:

```
You are here → AGENTS.md (this file)
                     │
                     ├── README.md          — Install, CLI cheatsheet, tests overview
                     ├── SKILL.md (root)    — Stub → .agents/skills/a2a/SKILL.md
                     ├── CHANGELOG.md       — Version history
                     │
                     ├── docs/AGENTS.md     — Doc ownership table (which file owns what)
                     │   └── docs/*.md      — Feature guides, API refs, deployment
                     │
                     ├── examples/AGENTS.md — Example patterns and client choice guide
                     │   └── examples/*.{py,js,rs}  — Runnable agent examples
                     │
                     ├── completion/AGENTS.md — Shell completion setup and maintenance
                     │   └── completion/a2a.{bash,zsh}
                     │
                     └── src/AGENTS.md      — Rust library API and build instructions
                         └── src/lib.rs      — Rust client implementation
```

**Quick rule of thumb:**
- Humans → `README.md` first.
- AI agents working on this repo → `AGENTS.md` (this file).
- Doc writers → `docs/AGENTS.md` for ownership.
- Example authors → `examples/AGENTS.md`.
- Completion maintainers → `completion/AGENTS.md`.
- Rust contributors → `src/AGENTS.md`.

## What this project is

A peer-to-peer messaging skill for agentic CLI sessions. N agents from any
CLI (`claude`, `opencode`, `pi`, …) share a SQLite bus at
`~/.a2a/{project}/database.db` and talk to each other directly — no
orchestrator, no central chain of command.

**Core** (stdlib-only, zero deps):
- `a2a.py` — CLI: 14 commands (init, register, send, recv, peek, list, status, wait, clear, project, unregister, search, stats, thread)
- `a2a` — Go CLI binary (companion, ~3.6MB ELF, zero deps)
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
- `a2a_client.go` — Go client library
- `cmd/a2a/main.go` — Go CLI binary (companion, ~3.6MB ELF, zero deps)
- `a2a_client.js` — Node.js client
- `src/lib.rs` — Rust client (Cargo workspace)

**Skill spec**: `.agents/skills/a2a/SKILL.md` (canonical) — this is the
standard repo-level skill location. The root `SKILL.md` and `docs/SKILL.md`
are stubs that point there. Always edit `.agents/skills/a2a/SKILL.md`
directly.

## Repository layout

```
a2a-skill/
├── a2a                   Go CLI binary (companion, ~3.6MB ELF, zero deps)
├── a2a.py                CLI (stdlib only)
├── a2a-spawn             per-CLI launcher
├── SKILL.md              skill spec (stub — canonical is .agents/skills/a2a/SKILL.md)
├── README.md
├── AGENTS.md             this file
├── LICENSE
├── install.sh
├── a2a_client.py         sync Python client (A2AClient)
├── a2a_client_async.py   async Python client
├── a2a_client.pyi        Python type stubs (sync)
├── a2a_client_async.pyi  Python type stubs (async)
├── a2a_common.py         shared validation constants and helpers
├── a2a_audit.py          v1.3: audit logging
├── a2a_crypto.py         v1.3: encryption
├── a2a_fts.py            v1.3: full-text search
├── a2a_priority.py       v1.3: priority queuing (sync)
├── a2a_priority_async.py v1.3: priority queuing (async)
├── a2a_routing.py        v1.3: routing rules (sync)
├── a2a_routing_async.py  v1.3: routing rules (async)
├── a2a_git_aware.py      v1.3: git-aware bus queries
├── a2a_server.py         REST API server
├── Dockerfile.multi      Multi-stage Docker build
├── docker-compose.yml    Docker Compose deployment
├── a2a_client.go         Go client library
├── a2a_client_test.go    Go library tests (55)
├── go.mod                Go module (companion binary)
├── go.sum
├── cmd/a2a/main.go       Go CLI binary entry point
├── build.sh              Go build script
├── Makefile              Go build/test/cover targets
├── smoke_test_go.sh      Go CLI smoke test (30 tests)
├── smoke_test.sh          Python CLI smoke test (2 claude haiku peers)
├── smoke_test_multi.sh    Multi-CLI smoke test (3 peers: claude+opencode+pi)
├── smoke_test_examples.sh Example agent patterns smoke test
├── verify_json_parity.sh Go vs Python JSON cross-verify
├── a2a_client.js         Node.js client
├── test_a2a_client.js    Node.js client tests (33)
├── src/lib.rs            Rust client (14 tests)
├── Cargo.toml            Rust workspace configuration
├── Cargo.lock
├── test_a2a.py           unit tests (157)
├── test_a2a_client.py    Python client tests (85)
├── test_integration.py   integration tests (105)
├── test_v13_features.py   v1.3 satellite module tests (140)
├── test_git_aware.py     git-aware module tests (65)
├── test_server.py        REST API tests (70)
├── test_async_modules.py async client tests (94, 3 skip-guarded classes)
├── test_artifacts_util.py artifact build util tests (84)     ← 902 tests total (800 Python + 55 Go + 14 Rust + 33 JS)
├── benchmark.py
├── dashboard.py
├── WEB_UI_README.md      Web UI documentation
├── server.js             Web UI server
├── public/               Web UI static assets
├── edge_case_test.sh     Edge-case hardening tests
├── perf_comparison_test.py CLI vs SDK performance comparison
├── stress_test.sh        10-agent concurrent stress test
├── high_volume_stress_test.sh 20-agent, 1000+ message test
├── verify_all.sh         Complete test suite runner
├── examples/             AGENTS.md documents patterns
│   └── remote_worktree_team.sh  Multi-agent team on remote git worktree
├── completion/           AGENTS.md documents shell completions
├── docs/                 AGENTS.md documents doc ownership
└── src/                  AGENTS.md documents Rust crate
```

## Database schema

`~/.a2a/{project}/database.db` (WAL mode for concurrent writers):

- `agents(id, role, prompt, cli, status, pid, created_at, last_seen)`
- `messages(id, sender, recipient, body, thread_id, ttl_seconds, created_at)` —
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

The kit prompt (in `.agents/skills/a2a/SKILL.md` Step 4 and inlined into both smoke tests)
is the agents' rulebook. When changing it:

- Keep it terse. Agents pay per-token.
- The locator snippet at the top must work whether or not `a2a` is on PATH.
- Always include the **hard cap** (8 loop iterations + "3 empty recvs = done").
  Without it, idle agents loop forever and burn budget.

## Monitoring & Debugging

Agent activity can be monitored live from the bus:

- **`a2a peek --limit N`** — view the last N messages without marking them read.
- **`a2a list --json`** — check all registered agents and their `status` (active/idle/done).
- **Agent logs** — each `a2a-spawn` session writes to `/tmp/a2a-{project}-{agent}.log`. Check these for crashes, CLI errors, or runaway loops.
- Agents set `status=done` when finished. If an agent stays `active` longer than expected, inspect its logs and the bus for unprocessed messages.

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
| Missing `register()` in a language client | Every client library must have `register()` — without it, `send()` rejects the sender as unknown. The JS and Rust clients both had this gap (fixed in v1.3.3). |
| Kit tells both agents to `recv` first, nobody initiates | At least one agent's kit must start with work (read files, analyze) before the first `recv`. Symmetric kits deadlock. |
| claude `-p` mode requires `--allow-dangerously-skip-permissions` + `CLAUDE_CODE_DANGEROUSLY_SKIP_PERMISSIONS=1` | Both the flag and env var are needed. The flag enables the feature, the env var skips prompts. Without the flag, claude blocks Bash tool calls even with the env var set. The `a2a-spawn` script now injects both (fixed in commit 6c53395). |
| claude as root: `--allow-dangerously-skip-permissions` blocked | When running as root, claude refuses `--allow-dangerously-skip-permissions` outright. Use `--permission-mode auto --allowedTools "Bash,Read,Edit,Write,Ls,Glob"` instead, with `CLAUDE_CODE_DANGEROUSLY_SKIP_PERMISSIONS=1`. The `a2a-spawn` script auto-detects root and uses this fallback (fixed in commit 7488f4a). |
| `INSERT OR REPLACE` destroys `created_at` on upsert | Use `INSERT OR IGNORE` then `UPDATE` (two statements) to preserve the original `created_at` when re-registering an agent. The async Python client had this bug (fixed in v1.3.3). |
| Rust `recv()`/`peek()` skip TTL cleanup | Rust client must call `DELETE FROM messages WHERE ttl_seconds IS NOT NULL AND created_at + ttl_seconds < ?` before fetching. It was missing in both `recv()` and `peek()` (fixed in v1.3.3). |
| `a2a-spawn` processes die silently when parent shell exits | The background `&` in `a2a-spawn` creates a child that receives SIGHUP when the parent bash exits. Fixed in v1.3.3+ using `nohup` + `disown` via the `_spawn_bg()` helper. If you write your own launcher script, use `nohup ... &` + `disown $!`. |
| claude `-p` mode sandbox blocks `a2a` and other non-project CLIs | Claude Code restricts shell tool access to the project working directory. The `a2a` CLI needs to read/write `~/.a2a/` which is outside the sandbox. Workaround: run reviewer in foreground and pipe findings to a file, then inject into fixer's kit prompt. Set `--allowedTools "Bash,Read,Edit,Write,Ls,Glob"` to narrow but not block. |
| opencode foreground mode works where background fails | When `a2a-spawn` background processes don't persist, run agents sequentially in foreground (`opencode run ...` / `claude -p ...`) instead. The sequential approach is more reliable for cron jobs and CI. |
| Cross-client API surface drifts apart | When adding a new command to `a2a.py`, update ALL 5 clients (py sync, py async, Go, JS, Rust) in the same PR. Run all test suites before committing. |
| `a2a-spawn --project` unknown arg (pre-v1.3.6) | `a2a-spawn` did not accept `--project`. Pass `A2A_PROJECT=<name>` in the calling shell before `a2a-spawn`, or upgrade to v1.3.6+ where `--project NAME` sets `A2A_PROJECT` for the spawned agent. |
| Cross-client upsert default inconsistency | Python sync/async and JS clients default `upsert=True` in `Register()`, but Go and Rust clients have no default — callers must pass it explicitly. Go/Rust callers copying Python examples get different behavior. When using Go or Rust clients, always pass the `upsert` parameter explicitly. |
| Orchestrator agent spawns peers on wrong bus | An orchestrator agent that calls `a2a-spawn` without `--project NAME` (or without exporting `A2A_PROJECT`) spawns peers that connect to the default `basename($PWD)` bus. The peers register and send to a different database than the orchestrator, so no messages cross. Always pass `--project` to `a2a-spawn` when the orchestrator uses a non-default project. |
| Claude auto mode classifier blocks kit prompts with shell-like commands | Claude's `--permission-mode auto` uses a security classifier that blocks kit prompts containing `EXPORT`, shell variable assignments (`A2A=...`), or explicit command invocations. The kit prompt must be written as natural-language instructions, not bash-looking code. Keep env var exports out of kit prompts — `a2a-spawn` already sets them in the subprocess environment. Put commands in `code blocks` within natural text rather than as bare shell syntax. |
| opencode model name requires full provider prefix | `a2a-spawn --model deepseek-v4-flash-free` (without provider prefix) creates a `deepseek-v4-flash-free/.` error — opencode truncates the name at the `/` boundary. Always use the full provider/model format: `--model opencode/deepseek-v4-flash-free`. The model listing (`opencode models`) shows `opencode/deepseek-v4-flash-free` but error messages misleadingly suggest `deepseek-v4-flash-free` without the prefix. |
| `--append-system-prompt "$KIT"` breaks with multi-line kit prompts via nohup | When `_spawn_bg()` passes a multi-line kit prompt via `--append-system-prompt "$KIT"`, the shell expands the variable into multiple arguments, breaking the flag. Use `--append-system-prompt-file "$KIT_FILE"` instead — claude reads the file directly, avoiding shell expansion. Fix applied to `a2a-spawn` in commit a820c9b. |
| `RoutingClientAsync.__init__` skips input validation (pre-v1.3.11) | Async set `project`/`agent_id` directly without empty-string checks. Now raises `ValueError` same as sync. Pass non-empty strings or get `ValueError`. |
| `RoutingClientAsync.add_rule()` not idempotent (pre-v1.3.11) | Calling `add_rule()` twice with same name silently duplicated the rule in `self.rules`. Now upserts correctly using the sync for/else pattern. |
| `RoutingClientAsync.disable_rule/enable_rule` stale in-memory state (pre-v1.3.11) | `self.rules` list was stale after DB update. Now calls `get_rules()` to refresh. After `disable_rule()`/`enable_rule()`, always call `get_rules()` if you need current state. |
| `RoutingClientAsync.recv_with_routing` selects non-existent `m.priority` column (pre-v1.3.11) | Caused `sqlite3.OperationalError` on every `recv()` call (messages table has no `priority` column). Removed the column from the SELECT. |
| `RoutingClientAsync.recv_with_routing` skips read tracking (pre-v1.3.11) | Messages not inserted into `reads` table, so repeated `recv(unread_only=True)` re-delivered same messages. Fixed — now inserts into reads table after fetching. |
| `RoutingClientAsync.route_messages()` skips read tracking (pre-v1.3.11) | Routed messages (deliver, forward, queue, escalate) were never marked read. Now all five routing categories mark messages as read. |
| `A2AClientAsync` accepts empty `agent_id` (pre-v1.3.11) | Empty string `agent_id` passed format validation but should have been rejected. Now raises `ValueError` matching sync behavior. |
| `.pyi` stub drift after `.py` changes | When changing method signatures in `.py` files, always update `.pyi` stubs in the same commit. The `search()` default limit drifted to 100 in stubs while implementations stayed at 50 (fixed in v1.3.11). |
| Go `Wait()` doesn't mark messages as read (v1.3.14+) | Go `Wait()` checks snapshot unread count with `SELECT COUNT(*)` and returns `bool` — it does NOT mark messages as read. Python `wait_for_messages()` calls `recv()` internally which marks messages as read and accumulates `seen`. After Go `Wait()` returns `true`, the N messages remain unread; callers must still call `Recv()`. After Python `wait()` returns `true`, those N messages are consumed. If migrating code from Python to Go, replace `wait(N, timeout)` + `recv(wait=0)` with just `Recv(wait=timeout, limit=N)`. |
| Go `Wait()` opens new DB connection per poll (fixed in v1.3.15) | Pre-v1.3.15, `Wait()` called `c.connect()` inside the `for` loop, creating a new SQLite connection every 500ms (up to 120 connections for 60s timeout). `Recv()` correctly opened one connection before the loop. Move `connect()` before the loop and `defer db.Close()` after it. |
| Go `GetStatus()` returns empty string for unknown agents (fixed in v1.3.15) | `GetStatus()` previously returned `("", nil)` for unknown agents (empty string, no error), while Python returns `None`. This made it impossible to distinguish "agent not found" from a legitimate empty status. Fixed to return `(*string, error)` with `nil, nil` for not-found, matching Python's `None` return. When porting code, check `status == nil` instead of `status == ""`. |
| Go `Recv()` marks reads inside scan loop (fixed in v1.3.15) | `Recv()` previously marked each message as read inside `rows.Next()` via `db.Exec(INSERT OR IGNORE INTO reads)`. If `rows.Scan()` failed on message N, messages 0..N-1 were already marked read but not returned. Python fetches all rows first with `fetchall()`, then marks reads with `executemany()` — no partial marking on scan error. Fixed by collecting all messages in the scan loop, then marking reads in a separate phase. |
| Go `Register()` upsert not atomic (fixed in v1.3.15) | Pre-v1.3.15, `Register(upsert=true)` used two separate `db.Exec()` calls (INSERT OR IGNORE + UPDATE), each auto-committing immediately. Another concurrent writer could read the agent record in its partial "insert-only" state. Also, the error from the first Exec was silently overwritten by the second. Fixed by wrapping both statements in a `tx.Begin()`/`tx.Commit()` transaction. Python uses a single `conn.commit()` for both, so it was already atomic. |
| Go `SearchFTS()` missing limit validation (fixed in v1.3.15) | `SearchFTS()` did not validate `limit` or `query` before running the FTS5 query. With `limit=0`, SQLite returned zero rows silently. With `limit<0`, SQLite returned ALL rows (potential DoS). The fallback `Search()` did validate both. Fixed by adding `strings.TrimSpace(query) == ""` and `limit <= 0` checks before the query. |
| Go `RecvSimple()` truncates fractional wait (fixed in v1.3.15) | `RecvSimple(wait int, ...)` accepted only `int` for wait, silently truncating fractional seconds (e.g., `0.5` became `0`). Python `recv(wait=float)` accepts floats directly. Fixed by changing `wait` parameter from `int` to `float64`. |
| Go `Stats()` silently swallows DB errors (fixed in v1.3.15) | All five `QueryRow().Scan()` calls in `Stats()` ignored errors. If the database schema wasn't initialized, `Stats()` returned a zero-value struct with no error — indistinguishable from an empty bus. Fixed by checking error on the primary COUNT query. |
| Go `connect()` connection expiry mid-poll (fixed in v1.3.15) | `connect()` set `SetConnMaxLifetime(5s)`, causing the connection pool to expire the underlying connection while `Recv(wait=30)` was polling. Fixed by setting `SetConnMaxLifetime(0)` (no limit) — connections live for the duration of each method call. |
| Go `Send()` missing whitespace thread_id validation (fixed in v1.3.15) | Go accepted whitespace-only strings as valid `thread_id` (e.g., `'   '`). Python raised `ValueError`. Fixed by treating `strings.TrimSpace(threadID) == ""` as empty (no thread). |
| Go `Send()` recipient error lacks guidance hint (fixed in v1.3.15) | Unknown recipient error said `"unknown recipient 'X'"` while sender error said `"unknown sender 'X' — register first"`. Python's recipient error included `"— register them first"`. Fixed to include the hint in both languages. |

### Unit tests (157 tests, stdlib only)

```bash
python3 test_a2a.py -v
```

Covers: DB schema, WAL mode, agent registration & upsert, send/recv,
read-tracking, broadcast, self-message filtering, `--include-self`,
`--ttl` expiry & cleanup, thread IDs, status transitions, project info.

### Python client tests (85 tests)

```bash
python3 test_a2a_client.py -v
```

Tests the A2AClient library directly (no subprocess): send, recv, search, thread,
stats, peek, WAL invariant.

### Integration tests (105 tests)

```bash
python3 test_integration.py -v
```

Shells out to the `a2a` binary and verifies full workflows: register→send→recv,
TTL expiry, broadcast, cross-project isolation, concurrent agents.

### v1.3 satellite module tests (140 + 65 + 70 + 94 tests)

```bash
python3 test_v13_features.py -v   # encryption, FTS, audit, priority, routing
python3 test_git_aware.py -v      # git-state-aware bus queries (65)
python3 test_server.py -v         # REST API endpoints (70)
python3 test_async_modules.py -v  # async clients (94, 3 skip-guarded classes — needs aiosqlite)
```

### Artifact build tests (84 tests)

```bash
python3 test_artifacts_util.py -v
```

Tests the artifact generation utilities used by `examples/artifacts/`.

### Complete test suite runner

```bash
./verify_all.sh
```

Runs all test suites in sequence. Requires `aiosqlite` for async tests
(3 classes are skip-guarded if aiosqlite is not available).

### Stress tests

```bash
./stress_test.sh                  # 10-agent concurrent stress
./high_volume_stress_test.sh       # 20-agent, 1000+ message test
./edge_case_test.sh               # edge-case hardening validation
```

These test the bus under load and edge conditions. They take longer to run
and should be used before releases rather than during development.

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

### CLI vs SDK comparison

```bash
python3 perf_comparison_test.py
```

Compares performance of the raw `a2a` CLI (via subprocess) against the
Python client library (A2AClient `a2a_client.py`). Useful for choosing
the right interface for latency-sensitive applications.

### Real-time dashboard

```bash
python3 dashboard.py            # live view (Ctrl+C to exit)
python3 dashboard.py --batch 60 # watch for 60 seconds then exit
```

Shows agent roster, recent messages, message rate, and participation stats.
Refreshes every 2 seconds in live mode.

## Style

### Bash
- Use `set -u` (or `set -eu` where appropriate), no bashisms in POSIX-portable spots.
- Quote variable expansions: `"$A2A"` not `$A2A`.
- Use `[[ ... ]]` for test expressions in scripts that are Bash-only (like
  `a2a-spawn`), but `[ ... ]` for POSIX-sh-compatible scripts.
- Validate argument existence before use (`: "${1?}"` or `[ -n "$1" ]`).

### Python
- **Stdlib only** — no `pip install`. The whole point of the bash wrapper is we run
  anywhere with sqlite3. Exception: `cryptography` for `a2a_crypto.py` (optional).
- 4-space indent, no tabs.
- Type hints where they help readability (PEP 484).
- Use `argparse` for CLI parsing — no `click`, `typer`, or third-party parsers.
- `conn.commit()` after every non-read SQL operation (INSERT, UPDATE, DELETE).
  Missing commits are a recurring bug pattern — see common pitfalls above.
- Use `with` context managers for file I/O; close database connections explicitly.

### Go

- Standard Go formatting (`gofmt`).
- Use `database/sql` with `github.com/mattn/go-sqlite3` driver.
- Return `(*int, error)` for optional PID parameters (nil = not set).
- Always apply WAL mode + busy_timeout on every `sql.Open()`.
- Use the same function signatures as Python where possible (snake_case in Go
  becomes camelCase, but argument names should match).

### Node.js

- CommonJS (`require()`) — not ESM, for maximum compatibility with LTS Node.
- Use `node:sqlite` (built-in, Node 22+) for synchronous operations (simpler than async for
  single-threaded agents).
- Every public method must exist: `register()`, `unregister()`, `send()`,
  `recv()`, `peek()`, `list()`, `status()`, `stats()`, `search()`, `thread()`.

### Rust

- Single `lib.rs` file, no workspace sub-crates.
- `rusqlite` with bundled feature for portability.
- No async runtime in `lib.rs` — if needed, create `lib_async.rs`.
- All public methods match the Python client's snake_case names.

### SKILL.md (canonical at `.agents/skills/a2a/SKILL.md`)

- Code blocks must be runnable copy-paste. Test them.
- The kit prompt (Step 4) is the most-reviewed section — test every change
  with at least one smoke test.
- Keep it terse. AI agents pay per-token for system prompts.
- Cross-reference docs/ files by relative path from the skill directory.

### Documentation (all AGENTS.md files and docs/*.md)

- Use tables for structured information (ownership, command lists, comparisons).
- Use ASCII trees for directory layouts.
- Keep test counts in sync with actual `grep -c "def test_"` output.
- Every AGENTS.md file must have a scope statement in its first paragraph.
- Cross-reference between AGENTS.md files using relative paths.

## Things this project deliberately does *not* do

- **No central orchestrator.** That's the point. If you find yourself adding
  one, you are building a different project.
- **No auth.** Anyone with FS access to `~/.a2a/{project}/database.db` can
  read or write the bus.

## Contributor Resources

Development resources for agents working on the a2a-skill codebase live **outside** the repo
at `~/ai/a2a-dev/`. They do not ship to users who clone this repo.

Access them via the global skill:
```
~/.agents/skills/a2a-dev/SKILL.md   ← hub; indexes all contributor sub-skills
~/ai/a2a-dev/skills/team-coordination/SKILL.md   ← CLAIM/ROLE-CROSS protocols
                                                      CLAIM: ACK-CLAIM required before work starts; auto-expires 5 min
                                                      ROLE-CROSS: 60s VETO window for stepping outside role bounds
~/ai/a2a-dev/skills/a2a-roadmap/SKILL.md         ← v1.4 priorities
~/ai/a2a-dev/skills/a2a-enhancements/SKILL.md    ← integration opportunities
~/ai/a2a-dev/skills/a2a-skill-experience/SKILL.md ← sprint learnings
~/ai/a2a-dev/skills/a2a-supervision/SKILL.md     ← supervision lessons
```

**Boundary rule:** `docs/` is for users of a2a. `~/ai/a2a-dev/` is for contributors.
Nothing development-process-related goes in `docs/` or `.agents/skills/` (except `.agents/skills/a2a/`).

## Cross-references to sub-directory AGENTS.md files

Several sub-directories have their own `AGENTS.md` with scoped guidance.
When working in those areas, read the corresponding file first.

| Directory | File | Scope |
|-----------|------|-------|
| `docs/` | `docs/AGENTS.md` | Doc file ownership table, rules for adding new docs |
| `examples/` | `examples/AGENTS.md` | Example agent patterns, client choice guide, adding new examples |
| `docs/` | `docs/PITFALLS.md` | Lessons from artifact smoke testing (see also `examples/artifacts/`) |
| `completion/` | `completion/AGENTS.md` | Shell completion scripts for Bash and Zsh |
| `src/` | `src/AGENTS.md` | Rust library API surface, WAL invariant, build instructions |

All files listed above must be kept accurate — they are the primary entry
points for agents entering those sub-systems.

## When you ship a change

1. Run **both** smoke tests on a clean bus (`./a2a clear --yes`).
2. Update `README.md` if the public surface changed.
3. Update relevant files in `docs/` if documentation changed.
4. Update `SKILL.md` if agent-facing behavior changed.
5. Add a row to "Common pitfalls" if you hit (and fixed) a new one.
6. Update `CHANGELOG.md` — follow the existing versioned format.

## CHANGELOG maintenance

`CHANGELOG.md` at the project root tracks all notable changes per version.

- Every PR that changes user-visible behavior must add a changelog entry.
- Format: `## [M.m.p] — YYYY-MM-DD` with `### Added`, `### Fixed`, `### Changed` sections.
- Version bumps happen at release time, not per-commit.
- The current release is referenced in `AGENTS.md` section headers and
  `README.md` — keep those in sync when bumping.

## Author & license

Author: **Javier Leandro Arancibia**.
License: **MIT** — keep the copyright notice in derivative works.
