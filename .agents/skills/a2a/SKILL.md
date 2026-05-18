---
name: a2a
description: Peer-to-peer messaging for agentic CLI sessions over a shared SQLite bus. Spawn N agents across any CLI (claude, opencode, pi, ...) — no central orchestrator.
trigger: /a2a
---

# a2a — Agent-to-Agent Messaging

This skill lives at the repo root (`./SKILL.md`). This folder is a local
convenience pointer.

**See the canonical skill file at:** [`./SKILL.md`](../../SKILL.md)
(relative to `./.agents/skills/a2a/SKILL.md`, that's `../../SKILL.md`)

Or the global install: `~/.agents/skills/a2a/SKILL.md`

## Quick reference

```
a2a init                          # create project database
a2a register alice --role dev     # register an agent
a2a send bob "hello" --from alice # direct message
a2a send all "broadcast" --from a # broadcast
a2a recv --as bob --wait 30       # receive messages (blocks)
a2a peek --json                   # observer view
a2a search <query> --json         # search messages (v1.1)
a2a thread <id>                   # view thread (v1.1)
a2a stats --json                  # bus statistics (v1.1)
a2a status done --as bob          # mark agent done
a2a clear --yes                   # wipe database
```

**Flags:** `--project NAME` (overrides `$A2A_PROJECT` > basename of cwd)
