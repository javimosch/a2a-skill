---
name: a2a
description: Peer-to-peer messaging for agentic CLI sessions over a shared SQLite bus. Spawn N agents across any CLI (claude, opencode, pi, ...) — no central orchestrator.
trigger: /a2a
---

# a2a — Agent-to-Agent Messaging

> **This doc is a pointer.** The canonical skill document lives at
> [`.agents/skills/a2a/SKILL.md`](../.agents/skills/a2a/SKILL.md).

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
