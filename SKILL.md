---
name: a2a
description: Spawn a team of agentic-CLI sessions (claude, opencode, pi, tau, ...) that talk to each other as peers via a shared SQLite message bus at ~/.a2a/{project}/database.db. No central chain of command — each agent decides who to message. Use when the user wants multiple AI sessions to collaborate, debate, or divide work without a fixed orchestrator.
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

## Field Learnings & Pitfalls

### Model availability breaks teams

Teams can't start if the model is unavailable. OpenRouter rate-limits killed the first spawn attempt silently. **Always have a fallback provider** (Xiaomi, local Ollama) configured in opencode.json. Test your model before spawning:

```bash
opencode run -m <provider/model> "echo ok" --dangerously-skip-permissions 2>&1 | head -5
```

If the fallback is weaker, keep kit prompts simpler — shorter context, fewer steps.

### Kit prompts must be self-contained

Agents have **no shared context** outside what you put in the kit file. Each kit must include:

- Full project paths (`/home/user/project/...`), not relative ones
- Exact binary locations (`/home/user/.local/bin/a2a`)
- All environment assumptions (which tools are installed, aliases available)
- The other agent's name and role (so they know who to message)
- Timeout values for `a2a recv --wait N` (60-120s is safe)

Missing any of these causes agents to stall waiting for information that was never given.

### The two-agent pattern (tester/fixer) is reliable

Lead-tester does the work, fixer waits for a report. This prevents both agents from stepping on each other. After the handoff, both should mark `status done`.

```
lead-tester → runs tests → reports → fixer → analyzes → responds → both done
```

### Monitor via logs, not just the bus

Agents write stdout to `/tmp/a2a-{agent-name}.log`. This is essential for debugging stalled agents:

```bash
tail -f /tmp/a2a-lead-tester.log
tail -f /tmp/a2a-fixer.log
```

The bus only shows final messages, not the agent's internal reasoning or intermediate failures.

### PID management is fragile

`a2a-spawn` returns a PID, but the process can die silently (model error, timeout, crash). Always verify:

```bash
kill -0 $PID 2>/dev/null || echo "Agent died"
a2a list --project <name>  # shows active/done status
```

If an agent dies before spawning, `a2a-spawn` won't tell you — you have to check the log file.

### Register first, then spawn, then upsert

Pattern 3 requires:

1. `a2a register agent-name --role X --project Y` — creates the bus identity
2. `a2a-spawn --id agent-name --project Y ...` — starts the process
3. `a2a register agent-name --pid $PID --upsert --project Y` — links process to identity

If you skip step 3, the agent shows as `active` but has no PID — you can't tell if it's alive.

### Clear the bus between runs

Old messages confuse new agents. Always `a2a clear --project <name> --yes` before a fresh team spawn.

### One-way communication is enough

For task-execution teams, agents don't need to debate. lead-tester sends a report, fixer acknowledges. No back-and-forth required. Keep it linear.

## Further reading by audience

| Audience | Start with |
|----------|------------|
| **AI agents** on this repo | [`AGENTS.md`](AGENTS.md) — full repo guide, common pitfalls, protocols |
| **Doc maintainers** | [`docs/AGENTS.md`](docs/AGENTS.md) — ownership table, adding/removing docs |
| **Example authors** | [`examples/AGENTS.md`](examples/AGENTS.md) — patterns, client choice, rules |
| **Shell completion** | [`completion/AGENTS.md`](completion/AGENTS.md) — Bash/Zsh setup and maintenance |
| **Rust developers** | [`src/AGENTS.md`](src/AGENTS.md) — library API, build instructions |
| **Human users** | [`README.md`](README.md) — install, CLI cheatsheet, test info |
