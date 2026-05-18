# a2a-skill

Peer-to-peer messaging for agentic CLI sessions (claude, opencode, pi, …)
over a shared SQLite bus. No central chain of command — each agent decides
who to talk to.

## What this is

A small Python CLI (`a2a`) plus a Claude Code skill (`/a2a`) that lets you
spin up N agentic-CLI sessions and have them collaborate, debate, or divide
work as peers. The transport is a SQLite database at
`~/.a2a/{projectName}/database.db`.

## Layout

```
a2a-skill/
├── a2a                  # bash wrapper that finds a python with sqlite3
├── a2a.py               # core CLI (stdlib only: argparse, sqlite3, json)
├── a2a-spawn            # CLI-agnostic peer launcher (claude, opencode, pi, ...)
├── SKILL.md             # /a2a skill spec — 7-step spawn protocol + kit prompt
├── README.md            # this file
├── AGENTS.md            # guide for AI agents working on this repo
├── install.sh           # one-command installer (symlinks CLI + skill)
├── test_a2a.py          # unit tests (28 tests, stdlib only)
├── test_integration.py  # integration tests (full CLI workflows)
├── benchmark.py         # performance benchmarks (latency, throughput)
├── dashboard.py         # real-time bus visualization
├── smoke_test.sh        # 2-claude haiku peer dialog
├── smoke_test_multi.sh  # cross-CLI peer dialog (claude + opencode + pi)
├── smoke_test_examples.sh # example agent smoke test
├── examples/            # agent collaboration pattern examples
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
agents drive themselves. See `SKILL.md` for the exact kit prompt template.

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
