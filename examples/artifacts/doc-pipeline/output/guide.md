# a2a Quick Start Guide

A peer-to-peer messaging bus for agentic CLI sessions.

## What is a2a?

**a2a** is a lightweight, zero-dependency messaging bus that lets AI agents
communicate directly — no orchestrator, no central chain of command. Each agent
runs in its own CLI session and uses `a2a send` / `a2a recv` to exchange
messages through a shared SQLite database (the "bus").

## Installation

```bash
git clone https://github.com/javimosch/a2a-skill.git ~/a2a-skill
ln -sf ~/a2a-skill/a2a /usr/local/bin/a2a
ln -sf ~/a2a-skill/a2a-spawn /usr/local/bin/a2a-spawn
```

No `pip install` or npm required — a2a runs on Python 3 stdlib + sqlite3.

## Quick Start

### 1. Initialize the bus

```bash
a2a init --project my-project
```

### 2. Register agents

```bash
a2a register alice --role researcher --cli claude
a2a register bob --role writer --cli opencode
```

### 3. Send a message

```bash
a2a send bob "Research the latest AI trends" --from alice
```

### 4. Receive messages

```bash
a2a recv --as bob --wait 30
```

### 5. Broadcast to all agents

```bash
a2a send all "Meeting in 5 minutes" --from alice
```

### 6. Mark yourself done

```bash
a2a status done --as alice
```

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Bus** | Shared SQLite database (WAL mode) stored at `~/.a2a/{project}/database.db` |
| **Agent** | A registered participant with an ID, role, and optional prompt/cli metadata |
| **Message** | A text payload with sender, recipient (or `NULL` for broadcast), and timestamp |
| **Read tracking** | Per-agent `reads` table ensures each message is delivered exactly once |
| **Thread** | Group related messages with `--thread <id>` for multi-turn conversations |
| **TTL** | Optional expiry time via `--ttl <seconds>`; expired messages auto-clean |
| **Project** | Isolated bus namespace; agents on different projects can't see each other |
| **WAL mode** | Write-Ahead Logging enables concurrent writers without deadlocks |

## CLI Command Reference

| Command | Description |
|---------|-------------|
| `a2a init` | Initialize a new a2a project bus |
| `a2a register <id>` | Register an agent on the bus |
| `a2a unregister <id>` | Remove an agent from the bus |
| `a2a send <to> <body>` | Send a message (use `all` for broadcast) |
| `a2a recv --as <id>` | Receive unread messages (blocks up to `--wait` seconds) |
| `a2a peek` | View recent messages without marking them read |
| `a2a list` | List registered agents |
| `a2a search <query>` | Search message contents |
| `a2a thread <id>` | View all messages in a thread |
| `a2a stats` | Show bus statistics (message count, agent count) |
| `a2a status <state>` | Set agent status (idle, active, blocked, done) |
| `a2a clear --yes` | Delete the entire project database |
| `a2a wait <n>` | Block until N unread messages arrive |

## Multi-Agent Patterns

### Coordinator → Workers

A coordinator agent delegates subtasks to worker agents, then collects results:

```
coordinator ──send──> worker-1 ──send──> coordinator
           ──send──> worker-2 ──send──> coordinator
```

### Pipeline

Agents pass work sequentially down a chain:

```
writer ──send──> formatter ──send──> publisher ──send──> collector
```

### Broadcast

One agent sends to all agents simultaneously for announcements or questions.

## Best Practices

1. **Always call `a2a status done`** when finished — otherwise the bus shows the agent as active forever.
2. **Use `--wait` instead of sleep loops** — `--wait 30` blocks efficiently until a message arrives.
3. **Include the WAL invariant** in any new module that opens SQLite directly:
   ```python
   conn.execute("PRAGMA journal_mode=WAL")
   conn.execute("PRAGMA busy_timeout=5000")
   ```
4. **Hard-cap agent iterations** (5-10 turns) to prevent runaway budget consumption.
5. **Test with `a2a peek --limit 30`** after a multi-agent run to verify bus state.
