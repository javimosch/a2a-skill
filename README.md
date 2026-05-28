<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/python-3.8+-blue" alt="Python">
  <img src="https://img.shields.io/badge/transport-SQLite-lightgrey" alt="SQLite">
</p>

<h1 align="center">a2a ⎯ Peer-to-peer messaging for AI agent teams</h1>

<p align="center">
  No central orchestrator. No fixed topology.<br>
  Spin up N agentic CLI sessions and let them self-coordinate over a shared SQLite bus.
</p>

<p align="center">
  <a href="#-quick-start"><b>Quick Start →</b></a>
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <a href="#-three-patterns"><b>Usage Patterns →</b></a>
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <a href="#-for-ai-agents"><b>For AI Agents →</b></a>
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <a href="#-install"><b>Install →</b></a>
</p>

---

**The problem:** Getting multiple AI coding sessions to collaborate means manually copy-pasting context between terminals, or building a custom orchestration layer.

**a2a fixes this.** Register agents, send messages, let them drive. One SQLite database. Zero infra.

---

## ⚡ Quick Start

```bash
# 1. Create a project bus
a2a init

# 2. Register two agents
a2a register alice --role architect
a2a register bob   --role developer

# 3. Send messages
a2a send bob "review the auth module" --from alice
a2a recv --as bob --wait 30

# 4. Broadcast to everyone
a2a send all "standup in 5" --from alice

# 5. Check who's on the bus
a2a list
```

> **Prerequisite:** Python 3 with `sqlite3` built-in (standard on 3.8+).
> Install with `./install.sh` — see [Install →](#-install).

---

## 🔀 Three Patterns

All patterns share the same bus at `~/.a2a/{project}/database.db`.

| # | Pattern | Who drives | Best for |
|---|---------|------------|----------|
| **1** | **Human-driven CLI** — you type `a2a send/recv` by hand | You | Learning the bus, scripting, one-off tasks |
| **2** | **Multi-terminal AI team** — open N terminals, give each agent a role, they self-coordinate | AI agents (you instruct) | Role-based teamwork (dev + architect + QA + PM), debates |
| **3** | **Auto-spawn** — one agent spawns N peers via `/a2a spawn` | AI agents (spawned automatically) | Fire-and-forget collaboration from inside a coding session |

**Which one?**
- New to a2a? Start with Pattern 1.
- Complex problem with clear roles? Pattern 2 — you watch each agent's reasoning live.
- Inside a Claude Code session? Pattern 3 via `/a2a spawn`.

---

## 🛠️ CLI Cheatsheet

```bash
a2a init                                                        # create project bus
a2a register alice --role researcher --prompt "..." --cli pi    # add an addressable peer
a2a register bob   --role critic

a2a send bob "what about Y?" --from alice                       # direct
a2a send all "team sync at noon" --from alice                   # broadcast
a2a send alice "expiring msg" --from bob --ttl 3600             # expires in 1 hour

a2a recv --as bob --wait 30                                     # block-poll inbox (unread only)
a2a recv --as bob --all --include-self                          # all messages including self-sent
a2a recv --as bob --peek                                        # look without marking read
a2a recv --as bob --json                                        # machine-readable output

a2a search "keyword"                                            # full-text search messages
a2a thread <id>                                                 # view a message thread

a2a list                                                        # who's on the bus
a2a stats                                                       # bus statistics
a2a peek                                                        # last 20 messages (observer view)

a2a status done --as alice                                      # update presence
a2a wait --as bob --count 3 --timeout 30                        # block until 3 unread or 30s
a2a unregister alice                                            # remove agent
a2a clear --yes                                                 # wipe the bus
a2a project                                                     # show resolved project info
```

Project name resolves from `--project NAME`, then `$A2A_PROJECT`, then `basename($PWD)`.
One project = one database = one isolated bus.

---

## 🤖 For AI Agents

a2a was built for agents first.

Each agent gets a *peer kit* prompt telling it who it is, how to call `send/recv/list/status`, and the rules (no inventing peers, stay terse, mark `done` when finished). From there, agents drive themselves.

The `/a2a` Claude Code skill handles spawning automatically — just type `/a2a` in a session.

```bash
# Agent workflow inside a Claude Code session
/a2a spawn dev architect qa --project myapp
# → three background sessions registered on the bus, collaborating
```

**Cross-CLI support:** `a2a-spawn` handles flag differences for `claude`, `opencode`, and `pi` — every agent gets the same kit prompt regardless of CLI.

See [`.agents/skills/a2a/SKILL.md`](.agents/skills/a2a/SKILL.md) for the full skill architecture and spawn protocol.

---

## 📦 Install

```bash
./install.sh
```

Links `a2a` and `a2a-spawn` into `~/.local/bin/`, and the skill into `~/.claude/skills/` and `~/.agents/skills/`. Restart your CLI session afterwards.

Or manually:

```bash
ln -sf "$PWD/a2a"      ~/.local/bin/a2a
ln -sf "$PWD/a2a-spawn" ~/.local/bin/a2a-spawn
ln -sf "$PWD"          ~/.claude/skills/a2a    # exposes /a2a in Claude Code
ln -sf "$PWD"          ~/.agents/skills/a2a    # cross-CLI
```

---

## 📖 Docs

- **[docs/QUICKSTART.md](docs/QUICKSTART.md)** — 5-minute walkthrough with hands-on examples
- **[docs/INSTALLATION.md](docs/INSTALLATION.md)** — Setup, prerequisites, platform notes
- **[docs/CLIENT_API.md](docs/CLIENT_API.md)** — Python client library (sync + async)
- **[docs/REST_API.md](docs/REST_API.md)** — HTTP REST interface
- **[AGENTS.md](AGENTS.md)** — Guide for AI agents working on this repo
- **[CHANGELOG.md](CHANGELOG.md)** — Release history

Client libraries also available for [Go](docs/GO_CLIENT_API.md), [Node.js](docs/NODE_CLIENT_API.md), and [Rust](docs/RUST_CLIENT_API.md).

---

## 🔩 Design Notes

- **Stdlib only** — `a2a.py` runs on any Python 3 with a built-in `sqlite3`. No dependencies.
- **WAL mode** — multiple concurrent agents read/write safely.
- **Read-tracking is per-agent** — broadcasts are seen once by each peer.
- **No locking primitives** — coordination is by convention (the kit prompt), not the bus. Agents can step on each other; that's the point.
- **Persistent by default** — the database survives between runs. Use `a2a clear --yes` to reset.

---

## License

MIT — [Javier Leandro Arancibia](https://github.com/javimosch)
