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
├── a2a            # bash wrapper that finds a python with sqlite3 and runs a2a.py
├── a2a.py         # the actual CLI (stdlib only)
├── SKILL.md       # /a2a skill spec for Claude Code
└── README.md      # this file
```

## Install

Link the CLI onto your PATH and the skill into `~/.claude/skills/`:

```bash
ln -sf "$PWD/a2a"      ~/.local/bin/a2a            # or anywhere on PATH
ln -sf "$PWD"          ~/.claude/skills/a2a        # exposes /a2a in Claude Code
```

Restart your Claude Code session so it picks up the new skill.

## CLI cheatsheet

```bash
a2a init                                            # create project bus
a2a register alice --role researcher                # add an addressable peer
a2a register bob   --role critic
a2a send bob "what about Y?" --from alice           # direct
a2a send all "team sync at noon" --from alice       # broadcast
a2a recv --as bob --wait 30                         # block-poll inbox
a2a list                                            # who's on the bus
a2a peek                                            # last 20 messages
a2a status done --as alice                          # update presence
a2a clear --yes                                     # wipe the bus
```

Project name resolves from `--project NAME`, then `$A2A_PROJECT`, then
`basename($PWD)`. One project = one database = one isolated bus.

## How agents use it

Each spawned CLI session is given a *peer kit* prompt that tells it:

- who it is (`agent_id`, role, the user's instruction)
- how to call `a2a recv / send / list / status`
- the rules: no inventing peers, stay terse, mark `done` when finished

The skill spawns the sessions with `claude -p` (or any CLI), passing the kit
prompt via `--append-system-prompt`. From then on, agents drive themselves.
See `SKILL.md` for the exact kit prompt template.

## Smoke test

See the `Smoke test recipe` section at the bottom of `SKILL.md`. Two haiku
sessions (alice + bob) exchange a plan and a critique with no orchestrator
in the middle.

## Design notes

- **Stdlib only** — `a2a.py` runs on any Python 3 with a built-in `sqlite3`.
  The `a2a` wrapper probes for an interpreter that has it.
- **WAL mode** — multiple concurrent agents read/write safely.
- **Read-tracking is per-agent** — broadcasts are seen once by each peer.
- **No locking primitives** — coordination is by convention (the kit prompt),
  not by the bus. Agents can step on each other; that's the point.
- **Persistent by default** — the database survives between runs. Use
  `a2a clear --yes` to reset.
