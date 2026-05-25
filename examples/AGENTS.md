# AGENTS.md — examples/

Agent-facing collaboration patterns. Each file here is a runnable example
that demonstrates one integration style. Read before adding or modifying.

## What belongs here

A file belongs in `examples/` if it:
- Demonstrates a specific pattern (coordinator, worker, reviewer, etc.)
- Can be run standalone against a live bus
- Has a docstring listing exactly what it demonstrates

Do **not** put tests here. Tests live in `test_*.py` at the project root.

## Existing examples

| File | Pattern | Client used |
|------|---------|-------------|
| `researcher_agent.py` | Ask → aggregate → broadcast | `subprocess` (CLI) |
| `code_reviewer_agent.py` | Request/response with structured output | `subprocess` |
| `critic_agent.py` | Adversarial review loop | `subprocess` |
| `debugger_agent.py` | Tool-call style with structured JSON body | `subprocess` |
| `task_coordinator_agent.py` | Divide-and-conquer with workers | `a2a_client.py` |
| `async_task_worker.py` | Async worker pool | `a2a_client_async.py` |
| `collision_detector.py` | Work-collision detection via git+bus | `a2a_client.py` |
| `compliance_archival_agent.py` | Audit + FTS + archival pipeline | `a2a_audit.py` + `a2a_fts.py` |
| `secure_team_agent.py` | Encrypted peer messaging + routing + audit | `a2a_crypto.py` + `a2a_routing.py` + `a2a_audit.py` |
| `spawn_coordinator.py` | Orchestrator spawning workers via a2a-spawn | `subprocess` + `a2a-spawn` |
| `spawn_debate.py` | Adversarial debate via a2a-spawn | `subprocess` + `a2a-spawn` |
| `v13_integrated_agent.py` | All v1.3 features together (async) | `a2a_client_async.py` + all modules |
| `nodejs_coordinator.js` | Coordinator in Node.js | `a2a_client.js` |
| `task_worker.rs` | Worker in Rust | `src/lib.rs` |

## Rules for adding a new example

1. **One pattern per file.** Don't combine coordinator + worker + reviewer in one file.
2. **Self-contained.** The file must run with `python3 examples/foo.py --project mytest`.
3. **Document imports clearly.** State which client module it uses and why.
4. **No hardcoded project names.** Accept `--project` arg or default to `basename(PWD)`.
5. **Always call `status done` before exit.** Without it the bus shows the agent as active forever.
6. **No sleep loops.** Use `recv --wait 30` (blocking) not `time.sleep(1)` in a loop.
7. **Add a smoke test entry** if the pattern is non-trivial. See `smoke_test_examples.sh`.

## Choosing the right client

| Need | Use |
|------|-----|
| Zero deps, any system | `subprocess` + `a2a` CLI |
| Pythonic API, sync | `a2a_client.py` |
| High concurrency, async | `a2a_client_async.py` |
| Priority queuing | `a2a_priority.py` / `a2a_priority_async.py` |
| Rule-based routing | `a2a_routing.py` / `a2a_routing_async.py` |
| Audit trail | `a2a_audit.py` |
| Encrypted channels | `a2a_crypto.py` (requires `pip install cryptography`) |
| Full-text search | `a2a_fts.py` (uses SQLite FTS5) |
| Git-aware work detection | `a2a_git_aware.py` |
| Go agents (library) | `a2a_client.go` (Go module) |
| Go agents (binary) | `cmd/a2a/main.go` (standalone CLI) |
| Node.js agents | `a2a_client.js` (copy to project) |
| Rust agents | `src/lib.rs` (Cargo workspace) |

## WAL invariant

Every client module now self-bootstraps WAL mode in `_connect()`. Examples
that use `subprocess` inherit this via the CLI. If you write an example that
opens SQLite directly (bypassing all clients), you **must** run:

```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")
```

immediately after `sqlite3.connect()`. All clients (Python sync/async,
Node.js, Go, Rust) now self-bootstrap WAL mode on every connection
— no prior `a2a init` required.

## Artifacts directory

The `examples/artifacts/` directory contains generated outputs from example
agent runs and smoke tests (not source code). Each sub-directory maps to a
specific example or test scenario. Code in `examples/artifacts/_util.py`
provides shared utilities for artifact generation. See `PITFALLS.md` for
lessons learned from artifact smoke testing.

## README.md

`examples/README.md` is the human-facing guide with detailed walkthroughs.
Keep it in sync when adding or removing examples. It lists each file with
usage instructions, patterns demonstrated, and key behaviors.

## See also

- [`../docs/AGENTS.md`](../docs/AGENTS.md) — Doc ownership and maintenance
- [`../docs/PITFALLS.md`](../docs/PITFALLS.md) — Artifact smoke testing lessons
- [`../completion/AGENTS.md`](../completion/AGENTS.md) — Shell completions
- [`../AGENTS.md`](../AGENTS.md) — Full repo guide for AI agents
