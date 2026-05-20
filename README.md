# a2a-skill

Peer-to-peer messaging for agentic CLI sessions (claude, opencode, pi, …)
over a shared SQLite bus. No central chain of command — each agent decides
who to talk to.

## What this is

A small Python CLI (`a2a`) plus a Claude Code skill (`/a2a`) that lets you
spin up N agentic-CLI sessions and have them collaborate, debate, or divide
work as peers. The transport is a SQLite database at
`~/.a2a/{projectName}/database.db`.

## Three ways to use a2a — pick your pattern

a2a supports three fundamentally different usage patterns. All share the same
SQLite bus at `~/.a2a/{project}/database.db` — agents from one pattern can
even coexist with another.

| # | Pattern | Who drives | Best for |
|---|---------|------------|----------|
| **1** | **Human-drive CLI** — you open terminals and type `a2a send/recv` by hand | You (the human) | Learning the bus, testing, scripting one-off tasks |
| **2** | **Multi-terminal AI team** — you open N terminals, tell each AI agent to join the bus with a role, and they self-coordinate | AI agents (you instruct them) | Role-based teamwork (dev + architect + QA + PM), debates, multi-perspective analysis |
| **3** | **Auto-spawn** — one agent launches N background sessions via `/a2a spawn` | AI agents (spawned automatically) | Fire-and-forget collaboration from inside a coding session |

**Which one should I use?**
- New to a2a? Start with **Pattern 1** to understand the bus.
- Working on a complex problem with clear roles? **Pattern 2** gives you the most control — you hand-pick each agent's model and instructions, watch their reasoning live, and intervene freely.
- Inside an AI coding session and need to spawn a quick team? **Pattern 3** via `/a2a spawn`.

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for hands-on examples of Patterns 1 & 2,
and [`.agents/skills/a2a/SKILL.md`](.agents/skills/a2a/SKILL.md) for the Pattern 3 protocol.

## Layout

```
a2a-skill/
├── a2a                  # bash wrapper that finds a python with sqlite3
├── a2a.py               # core CLI (stdlib only: argparse, sqlite3, json)
├── a2a_client.py        # Python client library (sync, no subprocess overhead)
├── a2a_client_async.py  # Python async client (asyncio-based, high concurrency)
├── a2a_git_aware.py     # Git-aware features (work-collision prevention)
├── a2a_client.go        # Go client library (direct DB access)
├── a2a_client.js        # Node.js client library (async/Promise)
├── src/lib.rs           # Rust client library (async, idiomatic)
├── a2a_server.py        # REST API server (HTTP interface)
├── a2a-spawn            # CLI-agnostic peer launcher (claude, opencode, pi, ...)
├── install.sh           # one-command installer (symlinks CLI + skill)

📚 Documentation
├── README.md                 # overview (this file)
├── AGENTS.md                 # guide for AI agents working on this repo
│
🚀 Getting Started
├── docs/QUICKSTART.md        # 5-minute quick start
├── docs/INSTALLATION.md      # setup & troubleshooting
├── docs/SKILL.md             # stub → points to .agents/skills/a2a/SKILL.md
│
📖 Core Guides
├── docs/CLIENT_API.md        # Python client library reference
├── docs/NODE_CLIENT_API.md   # Node.js client library reference
├── docs/GO_CLIENT_API.md     # Go client library reference
├── docs/RUST_CLIENT_API.md   # Rust client library reference
├── docs/REST_API.md          # HTTP REST interface reference
├── docs/ADVANCED_PATTERNS.md # optimization & patterns guide
├── docs/INTEGRATION_GUIDE.md # multi-interface coordination guide
├── docs/GIT_AWARE.md         # work-collision detection & prevention
│
🔐 v1.3 Features & Security
├── docs/ENCRYPTION.md        # end-to-end encryption (symmetric & asymmetric)
├── docs/PRIORITY.md          # 4-level priority queue ordering
├── docs/ROUTING.md           # rule-based message distribution
├── docs/AUDIT.md             # message lifecycle audit logging
├── docs/FTS_SEARCH.md        # full-text search with relevance ranking
├── docs/SECURITY_HARDENING.md # production security setup
├── docs/TROUBLESHOOTING.md   # common issues & solutions
│
🔧 Operations & Deployment
├── docs/DEPLOYMENT.md        # Docker, Kubernetes, systemd deployment
├── docs/OPERATIONS_GUIDE.md  # production monitoring & backup
│
🔐 v1.3 Quick Reference
├── docs/V13_QUICKREF.md      # v1.3 quick reference
│
🧪 Tests & Benchmarks
├── test_a2a.py          # unit tests (30 core tests)
├── test_a2a_client.py   # Python client tests (17 tests)
├── test_integration.py  # integration tests (18 tests)
├── test_a2a_client.js   # Node.js client tests (8 tests)
├── stress_test.sh       # 10-agent concurrent stress test
├── high_volume_stress_test.sh  # 20-agent, 1000+ message test
├── edge_case_test.sh    # edge-case hardening validation
├── perf_comparison_test.py  # CLI vs SDK benchmark
├── benchmark.py         # latency, throughput, TTL benchmarks
├── dashboard.py         # real-time bus visualization
├── verify_all.sh        # comprehensive test suite runner

🔨 Tools & Examples
├── examples/
│   ├── researcher_agent.py          # Broadcast + aggregation pattern
│   ├── code_reviewer_agent.py        # Async request-response pattern
│   ├── task_coordinator_agent.py     # Work distribution pattern
│   ├── critic_agent.py               # Debate and feedback loop
│   ├── debugger_agent.py             # Debugging and error investigation
│   ├── async_task_worker.py          # High-concurrency async agent
│   ├── collision_detector.py         # Work-collision prevention agent
│   ├── v13_integrated_agent.py       # All v1.3 features in action
│   ├── secure_team_agent.py          # Asymmetric encryption + routing + audit
│   ├── compliance_archival_agent.py  # Full-text search + audit + archival
│   └── task_worker.rs                # Rust agent example
├── smoke_test.sh            # 2-claude haiku peer dialog
├── smoke_test_multi.sh      # cross-CLI peer dialog (claude + opencode + pi)
├── smoke_test_examples.sh   # example agent smoke test

📋 Project
├── Cargo.toml           # Rust library configuration
├── LICENSE              # MIT (attribution required)
├── .gitignore
└── docs/                # ad-hoc reviews, notes
    └── review.md
```

## Install

Run the installer (symlinks CLI + skill to standard locations):

```bash
./install.sh
```

This links into `~/.local/bin/`, `~/.claude/skills/`, and `~/.agents/skills/` (cross-CLI).

Or manually:

```bash
ln -sf "$PWD/a2a"      ~/.local/bin/a2a            # or anywhere on PATH
ln -sf "$PWD/a2a-spawn" ~/.local/bin/a2a-spawn
ln -sf "$PWD"          ~/.claude/skills/a2a        # exposes /a2a in Claude Code
ln -sf "$PWD"          ~/.agents/skills/a2a        # cross-CLI global skills
```

Restart your CLI session so it picks up the new skill.

> **Prerequisite:** a Python 3 with `sqlite3` built-in. The `a2a` wrapper auto-detects
> one by probing common paths (python3.10, python3.12, etc.).

## Documentation

Comprehensive guides for different use cases:

- **[docs/QUICKSTART.md](docs/QUICKSTART.md)** — 5-minute introduction with examples
- **[docs/INSTALLATION.md](docs/INSTALLATION.md)** — Setup, prerequisites, platform-specific notes

**Client Libraries:**
- **[docs/CLIENT_API.md](docs/CLIENT_API.md)** — Python client library reference
- **[docs/NODE_CLIENT_API.md](docs/NODE_CLIENT_API.md)** — Node.js client library reference
- **[docs/GO_CLIENT_API.md](docs/GO_CLIENT_API.md)** — Go client library reference
- **[docs/RUST_CLIENT_API.md](docs/RUST_CLIENT_API.md)** — Rust client library reference
- **[docs/REST_API.md](docs/REST_API.md)** — HTTP REST interface for microservices
- **[docs/INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md)** — Multi-interface coordination examples

**v1.3 Feature Guides:**
- **[docs/V13_QUICKREF.md](docs/V13_QUICKREF.md)** — Quick copy-paste examples for all v1.3 features
- **[docs/ENCRYPTION.md](docs/ENCRYPTION.md)** — End-to-end encryption (symmetric & asymmetric)
- **[docs/FTS_SEARCH.md](docs/FTS_SEARCH.md)** — Full-text search with phrase & boolean queries
- **[docs/AUDIT.md](docs/AUDIT.md)** — Message lifecycle audit logging for compliance
- **[docs/PRIORITY.md](docs/PRIORITY.md)** — 4-level priority queue ordering
- **[docs/ROUTING.md](docs/ROUTING.md)** — Rule-based message distribution with pattern matching

**Advanced Topics:**
- **[docs/ADVANCED_PATTERNS.md](docs/ADVANCED_PATTERNS.md)** — Performance optimization, monitoring, error recovery
- **[docs/GIT_AWARE.md](docs/GIT_AWARE.md)** — Work-collision prevention with git state tracking
- **[docs/OPERATIONS_GUIDE.md](docs/OPERATIONS_GUIDE.md)** — Production deployment, monitoring, backup, troubleshooting
- **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** — Docker, Kubernetes, systemd, and security
- **[docs/V14_ARCHITECTURE.md](docs/V14_ARCHITECTURE.md)** — v1.4 roadmap: gRPC, WebSocket, Jaeger tracing, Prometheus
- **[`.agents/skills/a2a/SKILL.md`](.agents/skills/a2a/SKILL.md)** — `/a2a` skill architecture and spawn protocol (canonical)
- **[AGENTS.md](AGENTS.md)** — Guide for AI agents and agent development
- **[CHANGELOG.md](CHANGELOG.md)** — Complete release history and versioning

## CLI cheatsheet

```bash
a2a init                                                        # create project bus
a2a register alice --role researcher --prompt "..." --cli pi    # add an addressable peer
a2a register bob   --role critic

a2a send bob "what about Y?" --from alice                       # direct
a2a send all "team sync at noon" --from alice                   # broadcast
a2a send alice "expiring msg" --from bob --ttl 3600             # message expires in 1 hour

a2a recv --as bob --wait 30                                     # block-poll inbox (unread only)
a2a recv --as bob --all --include-self                          # all messages including self-sent
a2a recv --as bob --peek                                        # look without marking read
a2a recv --as bob --json                                        # machine-readable output
a2a recv --as bob --since 1700000000                            # messages after timestamp

a2a search "keyword"                                             # search messages by content
a2a search "keyword" --json --limit 10                           # search with JSON output

a2a thread <id>                                                  # view all messages in a thread
a2a thread <id> --json                                           # thread contents as JSON

a2a list                                                        # who's on the bus
a2a list --json                                                 # machine-readable

a2a stats                                                       # bus statistics
a2a stats --json                                                # stats as JSON

a2a peek                                                        # last 20 messages (observer view)
a2a peek --limit 50 --json                                      # last 50 in JSON

a2a status done --as alice                                      # update presence (supports --json)
a2a wait --as bob --count 3 --timeout 30                        # block until 3 unread or 30s
a2a clear --yes                                                 # wipe the bus
a2a project                                                     # show resolved project info
```

Project name resolves from `--project NAME`, then `$A2A_PROJECT`, then
`basename($PWD)`. One project = one database = one isolated bus.

## How agents use it

Each spawned CLI session is given a *peer kit* prompt that tells it:

- who it is (`agent_id`, role, the user's instruction)
- how to call `a2a recv / send / list / status`
- the rules: no inventing peers, stay terse, mark `done` when finished

The `a2a-spawn` launcher handles CLI-specific flags for **claude**, **opencode**, and
**pi** — each agent receives the same kit prompt regardless of CLI. From then on,
agents drive themselves. See `.agents/skills/a2a/SKILL.md` for the exact kit prompt template.

### Cross-CLI support

| CLI | Flag for kit prompt | Non-interactive mode |
|-----|-------------------|---------------------|
| claude | `--append-system-prompt` | `-p` + `--dangerously-skip-permissions` |
| opencode | embedded in first message | `run "Begin."` |
| pi | `--append-system-prompt` | `-p` + `--provider` + `--model` |

## Tests

### Unit tests (19 tests, stdlib only)

```bash
python3 test_a2a.py -v
```

Covers: schema init, WAL mode, agent registration & upsert, send/recv,
read-tracking, broadcast, self-message filtering, `--include-self`,
message TTL expiry & cleanup, thread IDs, status transitions,
project info, unknown-agent errors, concurrent writes.

### Smoke tests

```bash
# Two Claude haiku peers (alice + bob)
./smoke_test.sh

# Three peers across claude + opencode + pi
./smoke_test_multi.sh [project-name]
```

Both clear the bus at start and assert each peer sent messages and ended
with `status='done'`.

### Integration tests

```bash
python3 test_integration.py -v
```

Shells out to the `a2a` binary and exercises full workflows: register→send→recv,
TTL expiry, broadcast, cross-project isolation, concurrent agents.

### Performance benchmarks

```bash
python3 benchmark.py
```

Measures message latency (~82ms), throughput (~14 msg/s), broadcast latency,
TTL overhead, and blocking recv timeout behavior.

### Real-time dashboard

```bash
python3 dashboard.py     # watch agent activity live
python3 dashboard.py --batch 60  # watch for 60 seconds then exit
```

Shows agent roster, recent messages, message rate, and participation stats.

### Example agents

The `examples/` directory contains pattern implementations showing how to write
a2a agents:

```bash
# Run all three example agents in parallel (smoke test)
./smoke_test_examples.sh

# Or run individual agents
python3 examples/researcher_agent.py &
python3 examples/code_reviewer_agent.py &
python3 examples/task_coordinator_agent.py &

# Monitor the bus
a2a peek --limit 50
```

See `examples/README.md` for detailed walkthroughs of each pattern:
- **Researcher**: Broadcast + aggregation (ask all, collect responses)
- **Code Reviewer**: Async request-response (handle multiple reviews)
- **Task Coordinator**: Work distribution (assign, track, report)

## CI/CD

GitHub Actions automatically runs tests on every push:

- **Unit tests**: `test_a2a.py` on Python 3.10, 3.11, 3.12
- **Integration tests**: `test_integration.py` (18 CLI-level workflows)
- **Smoke tests**: Single-CLI and cross-CLI peer collaboration
- **Performance benchmarks**: Latency, throughput, TTL overhead
- **Code validation**: Python syntax, shell script validation, docs checks

See `.github/workflows/test.yml` for the full workflow.

## Design notes

- **Stdlib only** — `a2a.py` runs on any Python 3 with a built-in `sqlite3`.
  The `a2a` wrapper probes for an interpreter that has it.
- **WAL mode** — multiple concurrent agents read/write safely.
- **Read-tracking is per-agent** — broadcasts are seen once by each peer.
- **No locking primitives** — coordination is by convention (the kit prompt),
  not by the bus. Agents can step on each other; that's the point.
- **Persistent by default** — the database survives between runs. Use
  `a2a clear --yes` to reset.
