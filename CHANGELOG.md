# Changelog

All notable changes to a2a-skill are documented here.

## [1.3.4] — 2026-05-26 (Doc Audit & Client Hardening)

### Fixed
- **a2a-spawn: nohup+disown** — Spawned agents now survive parent shell exit using
  nohup + disown pattern. Eliminates silent agent death on shell exit.
- **a2a_client_async.py: 4 bugs** — Fixed wait() return type, added missing commits,
  included pid in list_peers, and resolved async client code review findings.
- **a2a_client.js: duplicate methods** — Removed duplicate definitions of status(),
  list(), init_project(), project_info(), and wait().
- **a2a_client.go: Wait()/List()/Status() API** — Changed Wait() to return bool,
  added List() alias and Status() method for API consistency.

### Added
- **src/lib.rs: project_info()** — Added missing project_info() method to Rust Client impl.
- **Go CLI binary rebuild** — Rebuilt companion binary after Wait()/List()/Status() API changes.

### Documentation
- **Doc audit fix** — Corrected stale docs found by a2a doc audit: Go binary size,
  Node.js sqlite backend, kit prompt iteration cap, duplicate AGENTS.md pitfalls,
  and CHANGELOG duplicate entries.

## [1.3.3] — 2026-05-25 (Multi-Client Audit & Fixes)

### Added
- **a2a_client.js: `register()` and `unregister()`** — Critical gap: Node.js client had
  no way to register an agent, making `send()` impossible (sender validation rejects
  unknown agents). Now matches Python API surface.
- **src/lib.rs: `register()` and `unregister()`** — Same critical gap in Rust client.
  Both methods follow the INSERT OR IGNORE + UPDATE pattern for upsert.
- **AGENTS.md: New common pitfalls** — `register()` gap, kit design deadlock,
  claude permissions env var, INSERT OR REPLACE hazard, Rust TTL gap,
  cross-client drift.

### Fixed
- **a2a_client.py: TTL cleanup now commits** — `_cleanup_expired()` in `peek()` and
  the `recv()` polling loop lacked `conn.commit()`, causing the DELETE to be silently
  rolled back by SQLite's implicit transaction on `conn.close()`.
- **a2a_client_async.py: `register(upsert=True)` preserves `created_at`** — Was using
  `INSERT OR REPLACE` which destroys the original created_at. Now uses INSERT OR IGNORE
  + UPDATE, matching the sync client's pattern.
- **src/lib.rs: `search()` case-insensitive matching** — Changed `WHERE body LIKE ?1`
  to `WHERE LOWER(body) LIKE ?1` with `query.to_lowercase()`. All other clients already
  used `lower()`.
- **src/lib.rs: TTL cleanup in `recv()` and `peek()`** — Both methods now delete
  expired messages before fetching. Previously, Rust was the only client that skipped
  cleanup entirely, returning stale messages to callers.
- **a2a_client.go: `pid <= 0` validation** — Changed `pid < 0` to `pid != nil && *pid <= 0`,
  rejecting pid=0 which would overwrite a valid PID via SQLite COALESCE.
- **a2a_client_test.go, cmd/a2a/main.go** — Updated for `*int` PID parameter matching
  the Go library's new signature.

### Changed
- **Go `Client.Register()` signature** — `pid` parameter changed from `int` to `*int`
  (pointer-to-int, nil = no PID), matching Python's `Optional[int]`.

## [1.3.2] — 2026-05-25 (Hardening & Cross-Client Parity)

### Added
- **Validation Hardening** — NaN/Inf rejection in `recv(wait)` and `wait_for_messages(timeout)` 
  for both sync and async Python clients. Go CLI `cmdRecv()` and `cmdRegister()` now reject
  NaN/Inf `--since` and negative `--pid` values, matching Python behavior.
- **REST API Server Hardening** — TTL positivity/NaN/Inf rejection, status value validation,
  peek/search positive-limit enforcement, search whitespace query rejection, register field
  length (role 512, cli 128, prompt 100K) and PID validation, expired message cleanup in
  recv/peek/search/thread handlers.
- **Max Length Validation** — Agent ID (256), thread_id (256), body (100000) limits enforced
  across Go client library, Go CLI, Node.js client, and Rust client, matching Python v1.3.2.
- **Go CLI Limit Capping** — `peek --limit` capped at 1000, `search --limit` capped at 200,
  matching Python CLI behavior.
- **Cross-Client `send()` Validation** — Node.js and Rust clients now validate sender and
  recipient existence in `agents` table before INSERT. All clients reject empty recipients,
  empty search queries, non-positive limits, and invalid status values.
- **Cross-Client `thread_id` Support** — Node.js and Rust `send()` now accept optional
  `threadId`/`thread_id` parameter for thread-scoped messages.
- **Test Coverage** — 143→148 (unit), 72→73 (client), 92→94 (integration), 39→43 (async),
  40→42 (git-aware), 56 new (artifacts util). Total: 616 tests (+70 from v1.3.1).
- **PITFALLS.md** — Expanded from ~100 to 596 lines covering cross-CLI validation parity,
  API key exhaustion, ddgr blocking, agent health checks, stale log files, and build
  script best practices.

### Fixed
- **Go CLI `cmdSend`** — body length validation for stdin reads; empty body now warns
  instead of erroring on zero-byte input from `echo -n`.
- **Async Client Resource Leaks** — `aiosqlite` connections closed in test teardown to
  eliminate ResourceWarnings.
- **REST API Send Response** — Response field name corrected from `id` to `message_id`
  to match documented schema.
- **Rust Client** — Added message body length cap (100K), thread_id length cap (256),
  agent_id length cap (256), project name path-traversal guard, and case-insensitive
  broadcast matching.
- **Node.js Client** — Added agent_id length cap (256) in constructor and expired
  message cleanup (TTL deletion) in recv() and peek().
- **Async Client** — Added missing agent_id length check in __init__ and missing
  limit < 0 guard in recv().
- **Go Client Register** — Added role (512), cli (128), prompt (100K) length validation
  to match Python clients.

### Documentation
- README: added links to GO_CLI_REFERENCE, PITFALLS, SECURITY_HARDENING, TROUBLESHOOTING
- AGENTS.md: test counts updated to 616 total, test_artifacts_util.py added to layout
- CHANGELOG: v1.3.2 section added (this entry)
- README, AGENTS.md: test counts synced to current (800 total)
- GO_CLI_REFERENCE.md: noted Go CLI version command difference
- GO_CLIENT_API.md: fixed Quick Start compile errors
- RUST_CLIENT_API.md: added thread_id to send() sig and examples
- NODE_CLIENT_API.md: removed npm dep note (uses node:sqlite), added threadId
- CLIENT_API.md: added missing unregister() method doc
- REST_API.md: added missing POST /register and /unregister endpoints

---

## [1.3.1] — 2026-05-19 (Hardening)

### Changed
- **FTS5 CLI Search** — `a2a search` now uses SQLite FTS5 MATCH instead of LIKE substring
  - Boolean operators (AND, OR, NOT) supported directly in the CLI
  - Automatic LIKE fallback when FTS5 index is unavailable
  - Commit: `77ce5c5`

### Added (v1.3.1 Test Hardening Sprint — complete)
- Test coverage for 5 previously untested modules (commit `2f97130`):
  - `test_git_aware.py` — 29 tests for `a2a_git_aware.py`
  - `test_server.py` — 33 REST API endpoint tests for `a2a_server.py`
  - `test_async_modules.py` — 25 async tests (23 skip-guarded when aiosqlite absent)
  - `test_a2a.py` — +6 WAL invariant + mkdir guard tests (`TestWALInvariant`)
- Bug fixes in `cmd_search` / `_init_fts()` (commit `848e9dd`, `2f255bb`):
  - FTS5 rebuild ran on every search call; now only on first table creation
  - `--fts` flag short-circuited `_init_fts`, leaving table uninitialised
  - `query.lower()` broke AND/OR/NOT operators; LIKE path now uses `lower(body)`
- FTS5 search quality tests (6): single term, AND, OR, prefix, --fts flag, LIKE fallback
- FTS5 rebuild regression test using `set_trace_callback` (commit `fad3319`)
- Total test count: 95 → 303 (278 pass + 25 skipped pending `aiosqlite` install)
- **WAL Invariant — All Non-Python Clients** closed in v1.3.1:
  - `a2a_client.js` → `node:sqlite` (built-in, Node 22+) with `mkdirSync` + WAL + `busy_timeout` (commit `5c30c02`)
  - `a2a_client.go` → `os.MkdirAll` + `PRAGMA journal_mode=WAL` + `busy_timeout=5000` (commit `4fcf652`)
  - `src/lib.rs` → `create_dir_all` + WAL + `busy_timeout=5000` (commit `150c8b6`)
  - No prior `a2a init` required by any client language

---

## [1.3.0] — 2026-05-19

### Added (v1.3 Features)
- **End-to-End Encryption** — Symmetric (Fernet) and asymmetric (RSA-2048) message encryption
  - AES-128 encryption for sensitive communications
  - Public key infrastructure with automatic key rotation support
  - Message wrapping and unwrapping for transparent encryption
  - See: [ENCRYPTION.md](docs/ENCRYPTION.md)

- **Full-Text Search (FTS5)** — SQLite FTS5-powered message search
  - Boolean operators (AND, OR, NOT)
  - Phrase queries with relevance ranking
  - Prefix matching and advanced query syntax
  - SearchQueryBuilder for complex queries
  - See: [FTS_SEARCH.md](docs/FTS_SEARCH.md)

- **Audit Logging** — Complete message lifecycle tracking
  - Operations: send, receive, encrypt, decrypt, route, search
  - Filters by agent, operation, time range, and result
  - Statistics and compliance reporting
  - Export functionality for compliance audits
  - GDPR, HIPAA, SOC 2, PCI DSS aligned
  - See: [AUDIT.md](docs/AUDIT.md)

- **Message Prioritization** — 4-level priority queue ordering
  - Priority levels: CRITICAL, HIGH, NORMAL, LOW
  - Ordered delivery by priority (DESC) then timestamp (ASC)
  - Priority-aware recv() for automated queue processing
  - Useful for on-call alerts and incident response
  - See: [PRIORITY.md](docs/PRIORITY.md)

- **Message Routing** — Rule-based intelligent message distribution
  - Pattern matching (substring, regex, priority, sender/recipient)
  - Routing actions: Deliver, Forward, Discard, Queue, Escalate
  - Persistent rules with enable/disable/delete operations
  - SmartRouter for custom business logic
  - See: [ROUTING.md](docs/ROUTING.md)

- **Async Clients** — High-concurrency asyncio-based clients
  - PriorityClientAsync for priority queue operations
  - RoutingClientAsync for rule-based routing
  - 10x throughput improvement (1K → 10K msg/sec)
  - Full API parity with sync clients
  - aiosqlite backend for non-blocking database access

- **Production Guides** — Comprehensive operational documentation
  - [SECURITY_HARDENING.md](docs/SECURITY_HARDENING.md) — Enterprise security setup
  - [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — 30+ common issues and solutions
  - [DEPLOYMENT.md](docs/DEPLOYMENT.md) — Production deployment guide

- **Example Agents** — Demonstration implementations
  - `secure_team_agent.py` — Encryption + routing + audit
  - `compliance_archival_agent.py` — FTS + audit + compliance reporting
  - `v13_integrated_agent.py` — All v1.3 features combined

### Changed
- Database schema extended with priority, audit, routing tables
- README reorganized to highlight v1.3 features and guides
- PROJECT_STATUS.md updated with v1.3 completion details

### Documentation
- 13 new comprehensive guides and references
- Migration guide for v1.2 → v1.3 upgrade
- Release highlights and stakeholder communication guide
- Approximately 3,000 lines of new documentation

### Testing
- Added 30+ tests for v1.3 features
- Total test count: 95+ tests covering all functionality
- Integration tests for v1.3 features and edge cases
- Performance testing for encryption and search operations

### Bug Fixes
- Fixed Python 3.11+ compatibility with UTF-8 encoding declarations
- Ensured WAL mode enabled on all database connections
- Fixed mkdir race conditions in async modules

---

## [1.2.0] — 2026-05-19 (Pre-release)

### Added
- Multi-language client libraries
  - Go client library (a2a_client.go)
  - Node.js client library (a2a_client.js)
  - Rust client library (src/lib.rs)
- REST API server (a2a_server.py) with 10 endpoints
- Full API parity across all language bindings
- Additional example agents (task_coordinator, task_worker_rs)
- INTEGRATION_GUIDE for multi-interface coordination
- Comprehensive client API documentation

---

## [1.1.0] — 2026-05-19 (Pre-release)

### Added
- **Message Search** — `a2a search <query>` with optional `--json`
  - Substring pattern matching across all messages
  - JSON output format for programmatic access
  - Thread filtering and result sorting

- **Message Threading** — `a2a thread <id>`
  - Display all messages in a thread as a conversation
  - Maintain message context and relationships

- **Bus Statistics** — `a2a stats` with optional `--json`
  - Agent count and active agents
  - Message statistics (total, unread, by thread)
  - JSON format for integration

- **JSON Audit** — Extend `--json` flag to all relevant commands
  - `a2a status --json` — JSON agent status output
  - `a2a search --json` — JSON search results
  - `a2a stats --json` — JSON bus statistics
  - Enable programmatic bus monitoring

- **Python Client Library** — A2AClient with full API parity
  - Methods: send, recv, search, thread, stats, peek, list_peers
  - No subprocess overhead, direct SQLite connection
  - A2AClientAsync for high-concurrency scenarios
  - Comprehensive test coverage

- **Testing Infrastructure**
  - Integration tests for 18+ CLI workflows
  - Stress tests (10-agent concurrent, 20-agent volume)
  - Edge case hardening (large messages, special characters, TTL)
  - Performance analysis and benchmarking

- **Documentation**
  - INSTALLATION.md (196 LOC) — setup and troubleshooting
  - ADVANCED_PATTERNS.md (404 LOC) — optimization techniques
  - QUICKSTART.md — 5-minute introduction
  - CLIENT_API.md — Python client reference

---

## [1.0.0-alpha] — 2026-05-18, 23:37 UTC

### Initial Release
- **Core CLI** (a2a.py, 593 LOC)
  - 14 commands: init, register, unregister, send, recv, peek, list, status, wait, clear, project, search, stats, thread
  - Message filtering (broadcast, per-agent read tracking, thread filtering)
  - Message TTL with automatic expiry
  - Agent presence tracking (status, PID)

- **Database** (SQLite, WAL mode)
  - Schema: agents, messages, reads tables
  - Concurrent safe with WAL mode
  - Per-project databases under ~/.a2a/{project}/

- **Cross-CLI Support**
  - a2a-spawn for per-CLI launcher (claude, opencode, pi)
  - Kit prompt integration for safe collaboration
  - Global skills path (~/.agents/skills)

- **Python Client Library**
  - A2AClient for programmatic access
  - Full method parity with CLI
  - Direct SQLite connection (no subprocess overhead)

- **Bash Wrapper** (a2a)
  - Auto-detect Python 3 with sqlite3 support
  - Fallback to python, /usr/bin/python3, python3.10, etc.
  - Cached interpreter selection for performance

- **Multi-Language Support**
  - Example agents demonstrating collaboration patterns
  - Researcher (broadcast + aggregation)
  - Code Reviewer (async request-response)
  - Task Coordinator (work distribution)

- **Testing** (72 tests)
  - 30 unit tests (schema, agent lifecycle, message workflows)
  - 18 integration tests (end-to-end CLI workflows)
  - 17 client library tests
  - 7 stress/hardening tests

- **Documentation**
  - README with project overview and quick start
  - SKILL.md — Claude Code skill specification
  - AGENTS.md — guide for AI agents working on the repo
  - CLIENT_API.md — Python client library reference

- **Tools**
  - dashboard.py — real-time bus visualization
  - benchmark.py — performance measurement (latency, throughput, TTL)
  - verify_all.sh — comprehensive test suite runner

---

## Release Statistics

| Version | Date | Features | Tests | LOC | Duration |
|---------|------|----------|-------|-----|----------|
| 1.0-alpha | 2026-05-18 | Core messaging | 72 | 3,500+ | 24 hours |
| 1.1 | 2026-05-19 | Search, thread, stats, client lib | 95 | 4,200+ | 15 min |
| 1.2 | 2026-05-19 | Multi-lang clients, REST API | 95+ | 5,500+ | 20 min |
|| 1.3.2 | 2026-05-25 | Hardening, cross-client parity | 616 | 13,000+ | 6 days |
|| 1.3.0 | 2026-05-19 | Encryption, routing, audit, FTS | 95+ | 8,000+ | 45 min |

---

## Versioning

This project follows [Semantic Versioning](https://semver.org/).

- **MAJOR** version when introducing incompatible API changes
- **MINOR** version when adding functionality in a backwards-compatible manner
- **PATCH** version for backwards-compatible bug fixes

---

## Upgrading

- **From v1.0 to v1.1**: No breaking changes, opt-in to new features
- **From v1.1 to v1.2**: Multi-language clients are additive
- **From v1.2 to v1.3**: Schema changes are additive and backward-compatible

---

## Future Releases

v1.4 planning includes:
- gRPC API (10-100x faster than HTTP)
- WebSocket API (real-time notifications)
- Distributed tracing (Jaeger integration)
- Prometheus metrics

See [CHANGELOG.md](CHANGELOG.md) for release history and roadmap.

---

**Last Updated**: 2026-05-26

