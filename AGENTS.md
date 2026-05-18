# AGENTS.md — guide for future agents working on this repo

This file tells AI coding agents (and humans) how to safely and effectively
work on **a2a-skill**. Read this first.

## What this project is

A peer-to-peer messaging skill for agentic CLI sessions. N agents from any
CLI (`claude`, `opencode`, `pi`, …) share a SQLite bus at
`~/.a2a/{project}/database.db` and talk to each other directly — no
orchestrator, no central chain of command. The skill provides:

- `a2a.py` — Python stdlib-only CLI (the actual program)
- `a2a` — bash wrapper that auto-locates a python3 with `sqlite3`
- `a2a-spawn` — launcher that hides per-CLI flag differences
- `SKILL.md` — Claude Code `/a2a` skill spec (also usable by any CLI that
  reads `~/.agents/skills`)
- `test_a2a.py` — unit tests (28)
- `test_integration.py` — integration tests (CLI workflows)
- `smoke_test.sh`, `smoke_test_multi.sh` — end-to-end tests
- `smoke_test_examples.sh` — example agent smoke test
- `benchmark.py` — performance benchmarks
- `dashboard.py` — real-time bus visualization

## Repository layout

```
a2a-skill/
├── a2a               bash wrapper — picks python+sqlite3, caches in .a2a_python
├── a2a.py            CLI implementation (stdlib only: argparse, sqlite3, json)
├── a2a-spawn         launches one agent per CLI with the right flags
├── SKILL.md          /a2a skill spec — kit prompt + spawn protocol
├── README.md         project overview + install + design notes
├── AGENTS.md         this file
├── LICENSE           MIT (attribution required)
├── install.sh        symlinks CLI+skill into ~/.local/bin, ~/.claude/skills, ~/.agents/skills
├── test_a2a.py       unit tests (28 tests, stdlib only)
├── smoke_test.sh     2-claude haiku peer dialog
├── smoke_test_multi.sh  claude + opencode + pi cross-CLI peer dialog
├── benchmark.py       performance benchmarks (latency, throughput, TTL overhead)
├── dashboard.py       real-time bus dashboard (agent stats, message flow)
├── examples/         example agent collaboration patterns (researcher, code review, coordinator)
└── docs/             ad-hoc reviews, notes
```

## Database schema

`~/.a2a/{project}/database.db` (WAL mode for concurrent writers):

- `agents(id, role, prompt, cli, status, pid, created_at, last_seen)`
- `messages(id, sender, recipient, body, thread_id, created_at)` —
  `recipient = NULL` means broadcast
- `reads(agent_id, message_id, read_at)` — per-agent unread tracking

Project name resolves from `--project NAME` > `$A2A_PROJECT` > `basename($PWD)`.

## Mental model

- The **bus is the source of truth**. Anything not on the bus did not happen.
- **Read-tracking is per-agent**. A broadcast is seen once by each peer.
- **No locking primitives**. Coordination is by convention — the kit prompt
  tells each agent how to behave. Agents *can* step on each other; the design
  is "free communication," not "consensus."
- The CLI is **stateless** between invocations. Every command opens the db,
  does its work, closes it.

## How to extend safely

### Adding a new CLI command

1. Add a `cmd_<name>(args)` function in `a2a.py`.
2. Wire it up in `build_parser()` (new subparser).
3. Cover the happy path in `smoke_test.sh` so regressions are visible.
4. Keep dependencies to **Python stdlib only** — no `pip install`. The whole
   point of the bash wrapper is that we run anywhere with sqlite3.

### Adding support for a new agentic CLI

Edit `a2a-spawn`:

1. Add a `case "$CLI"` branch.
2. Decide whether the CLI has an `--append-system-prompt`-style flag. If yes,
   pass `$KIT` there. If no, embed the kit in the first user message.
3. Don't forget `--dangerously-skip-permissions` or its equivalent so the
   agent can call `bash` non-interactively.
4. Verify the CLI can be invoked **without a TTY** (background-friendly).
   `opencode` itself is aliased to `opencode-tmux` which requires a real
   terminal — we resolve to `~/.opencode/bin/opencode` instead.

### Changing the kit prompt

The kit prompt (in `SKILL.md` Step 4 and inlined into both smoke tests)
is the agents' rulebook. When changing it:

- Keep it terse. Agents pay per-token.
- The locator snippet at the top must work whether or not `a2a` is on PATH.
- Always include the **hard cap** (5-8 iterations + "3 empty recvs = done").
  Without it, idle agents loop forever and burn budget.

## Common pitfalls (and how to avoid them)

| Pitfall | Fix |
|---|---|
| `python3` doesn't have `sqlite3` (custom-compiled Python) | The wrapper probes `/usr/bin/python3`, `/usr/local/bin/python3`, etc. Don't hardcode a path. |
| Agents invent peers that don't exist | Kit prompt tells them to read `a2a list --json` first. Verify by inspecting `peek` after a run. |
| Smoke test "hangs" | Each kit prompt has a hard iteration cap and `--max-turns` on the CLI. If a CLI ignores `--max-turns`, add `timeout N` in the spawn. |
| Cross-CLI: model id format differs per CLI | `claude -p --model haiku` works; opencode wants `provider/model` (e.g. `opencode-go/deepseek-v4-flash`); pi wants `--provider X --model Y` split. Surfaced via `a2a-spawn` flags. |
| `opencode run` printing to stdout instead of acting | Make sure `--dangerously-skip-permissions` is set, otherwise it asks for shell-tool approval and just prints. |
| Many concurrent writers corrupt SQLite | We use WAL + 5s busy timeout. Don't switch off WAL. |
| `cmd_peek` calls `cleanup_expired()` but deletes vanish | Any non-read operation (DELETE, INSERT, etc.) must be followed by `conn.commit()`. `cleanup_expired` deletes rows but doesn't commit — the caller must. |

## Running the tests

### Unit tests (28 tests, stdlib only)

```bash
python3 test_a2a.py -v
```

Covers: DB schema, WAL mode, agent registration & upsert, send/recv,
read-tracking, broadcast, self-message filtering, `--include-self`,
`--ttl` expiry & cleanup, thread IDs, status transitions, project info.

### Integration tests

```bash
python3 test_integration.py -v
```

Shells out to the `a2a` binary and verifies full workflows: register→send→recv,
TTL expiry, broadcast, cross-project isolation, concurrent agents.

### Smoke tests

```bash
# 2 claude haiku peers
./smoke_test.sh

# 3 peers across claude + opencode + pi
./smoke_test_multi.sh

# Example agent patterns
./smoke_test_examples.sh

# Custom project name
./smoke_test_multi.sh my-test
```

The tests `clear --yes` the bus at start, then assert each peer sent at least
one message and that everyone ended with `status='done'`.

### Performance benchmarks

```bash
python3 benchmark.py
```

Measures message latency (~82ms), throughput (~14 msg/s), broadcast latency,
TTL overhead, and blocking recv timeout behavior.

## Style

- Bash scripts: `set -u` (or `set -eu` where appropriate), no bashisms in
  POSIX-portable spots.
- Python: stdlib only, 4-space indent, type hints where they help readability.
- SKILL.md: code blocks must be runnable copy-paste. Test them.

## Things this project deliberately does *not* do

- **No encryption.** The bus is cleartext on the local FS. Trust model: a
  shared local environment. Add encryption if remoting the db.
- **No central orchestrator.** That's the point. If you find yourself adding
  one, you are building a different project.
- **No TTL/expiry on messages.** The db grows. `a2a clear --yes` resets.
- **No auth.** Anyone with FS access to `~/.a2a/{project}/database.db` can
  read or write the bus.

## When you ship a change

1. Run **both** smoke tests on a clean bus (`./a2a clear --yes`).
2. Update `README.md` if the public surface changed.
3. Update `SKILL.md` if agent-facing behavior changed.
4. Add a row to "Common pitfalls" if you hit (and fixed) a new one.

## Author & license

Author: **Javier Leandro Arancibia**.
License: **MIT** — keep the copyright notice in derivative works.
