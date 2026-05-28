---
name: a2a
description: Spawn a team of agentic-CLI sessions (claude, opencode, pi, ...) that talk to each other as peers via a shared SQLite message bus at ~/.a2a/{project}/database.db. No central chain of command — each agent decides who to message. Use when the user wants multiple AI sessions to collaborate, debate, or divide work without a fixed orchestrator.
trigger: /a2a
---

# a2a — Agent-to-Agent Messaging

> **This doc is a pointer.** The canonical skill document lives at
> [`.agents/skills/a2a/SKILL.md`](.agents/skills/a2a/SKILL.md).
> See [docs/AGENTS.md](docs/AGENTS.md) for ownership and maintenance rules.

That file contains: three usage patterns, the Pattern 3 spawn protocol,
kit prompt template, smoke test recipe, honesty rules, and common pitfalls
from smoke testing.

## Quick reference

```
a2a init                          # create project database
a2a register alice --role dev     # register an agent
a2a send bob "hello" --from alice # direct message
a2a send all "broadcast" --from a # broadcast
a2a recv --as bob --wait 30       # receive messages (blocks up to 30s)
a2a peek --json                   # observer view
a2a search <query> --json         # search messages
a2a thread <id>                   # view thread
a2a stats --json                  # bus statistics
a2a status done --as bob          # mark agent done
a2a clear --yes                   # wipe database
```

**Flags:** `--project NAME` (overrides `$A2A_PROJECT` > basename of cwd)

## Further reading by audience

| Audience | Start with |
|----------|------------|
| **AI agents** on this repo | [`AGENTS.md`](AGENTS.md) — full repo guide, common pitfalls, protocols |
| **Doc maintainers** | [`docs/AGENTS.md`](docs/AGENTS.md) — ownership table, adding/removing docs |
| **Example authors** | [`examples/AGENTS.md`](examples/AGENTS.md) — patterns, client choice, rules |
| **Shell completion** | [`completion/AGENTS.md`](completion/AGENTS.md) — Bash/Zsh setup and maintenance |
| **Rust developers** | [`src/AGENTS.md`](src/AGENTS.md) — library API, build instructions |
| **Human users** | [`README.md`](README.md) — install, CLI cheatsheet, test info |
