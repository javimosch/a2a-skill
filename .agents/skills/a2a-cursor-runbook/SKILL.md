---
name: a2a-cursor-runbook
description: Bootstrap flow for wiring the official Cursor Agent CLI (agent / cursor-agent) as an a2a peer. Covers install + auth, how a2a-spawn resolves the binary, and a solo smoke test. Prefer this over building a debri-style wrapper — Cursor already supports headless -p / stream-json / --trust / --force.
trigger: a2a cursor bootstrap
---

# a2a + Cursor Agent CLI — discovery & bootstrap runbook

**Who this is for:** you have the `a2a-skill` repo and want to spawn a Cursor
Agent peer via `a2a-spawn --cli cursor`. Unlike debri (which wraps Devin through
tmux), **no custom harness is required** — the official `agent` /
`cursor-agent` binary already exposes automation flags.

## Step 0 — Prerequisites

```bash
command -v agent || command -v cursor-agent || echo "MISSING: Cursor Agent CLI"
command -v a2a || echo "MISSING: a2a (run ./install.sh from a2a-skill)"
```

## Step 1 — Install and authenticate Cursor Agent CLI

Install via Cursor’s documented Agent CLI install (typically lands as
`~/.local/bin/agent` and `~/.local/bin/cursor-agent` symlinks). Then:

```bash
agent login          # or: CURSOR_API_KEY=... for non-interactive auth
agent status         # must show logged in
agent --version
```

Headless smoke (no a2a yet):

```bash
agent -p --trust --mode ask "Reply with exactly: ok"
```

## Step 2 — Point a2a-spawn at the binary

`a2a-spawn`'s cursor branch resolves in this order:

1. `$CURSOR_AGENT_BIN` env var (if set and executable)
2. `~/.local/bin/agent`
3. `~/.local/bin/cursor-agent`
4. `agent` or `cursor-agent` on `PATH`

Override only if needed:

```bash
export CURSOR_AGENT_BIN=/path/to/cursor-agent
# optional: pin workspace for the agent process
export CURSOR_WORKSPACE=/path/to/workdir
```

CLI aliases accepted by `a2a-spawn`: `cursor`, `agent`, `cursor-agent`.

## Step 3 — Get a2a-skill onto PATH (if needed)

```bash
git clone https://github.com/javimosch/a2a-skill.git
cd a2a-skill
./install.sh
a2a version
```

## Step 4 — Smoke test: one cursor agent, solo

```bash
PROJECT=cursor-smoke
export A2A_PROJECT=$PROJECT
a2a clear --yes 2>/dev/null; a2a init
a2a register solo --role dev --cli cursor

cat > /tmp/cursor-smoke.kit <<EOF
You are agent "solo" on an a2a peer bus, project $PROJECT.
Do EXACTLY this, then stop:
1. Run: a2a status active --as solo
2. Write the word "hello" to /tmp/cursor-smoke-output.txt
3. Run: a2a status done --as solo
EOF

PID=$(a2a-spawn --cli cursor --id solo --project $PROJECT \
    --log /tmp/cursor-smoke.log --kit-file /tmp/cursor-smoke.kit)
a2a register solo --pid "$PID" --upsert
echo "spawned pid=$PID"
# wait for completion (typically 30–90s depending on model/quota)
for i in $(seq 1 60); do
  st=$(A2A_PROJECT=$PROJECT a2a list --json 2>/dev/null | grep -o '"status": "[^"]*"' | head -1)
  echo "t=${i}0s $st"
  echo "$st" | grep -q done && break
  sleep 10
done
A2A_PROJECT=$PROJECT a2a list --json
cat /tmp/cursor-smoke-output.txt
```

Expect:

- `a2a list` shows `solo` with `status: "done"`
- `/tmp/cursor-smoke-output.txt` contains `hello`
- `/tmp/cursor-smoke.log` has stream-json events from `agent -p`

If it stalls, check the log for trust/auth/quota errors. Free-tier limits can
delay or fail runs — retry or set `--model` to an available model from
`agent models`.

## Step 5 — Join a real a2a team

Same Pattern 3 protocol as other CLIs (`--cli cursor`). Watchdog/lease apply
unchanged.

## Cursor-specific pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `a2a-spawn: cursor agent not found` | Binary not on PATH | Install Agent CLI or set `CURSOR_AGENT_BIN` |
| Immediate exit asking for workspace trust | Missing `--trust` | `a2a-spawn` already passes `--trust` in the cursor branch |
| Agent asks for shell approval and hangs | Missing `--force` | `a2a-spawn` already passes `--force` |
| Auth / quota errors in log | Not logged in or Free-tier limits | `agent login` / check `agent status` |
| `$A2A` in kits not found | Placeholder not expanded | `a2a-spawn` inlines `A2A_PROJECT=<proj> <a2a>` for `$A2A` |

## Why not a ~/ai/debri-style wrapper?

debri exists because Devin needs fresh tmux sessions, TUI stripping, and
structured JSONL. Cursor Agent CLI already provides `-p`, `--output-format
stream-json|json`, `--trust`, `--force`, and `--workspace`. Wire it in
`a2a-spawn` directly.

## References

- Cursor Agent CLI: `agent --help` / `agent about`
- a2a main skill: [`.agents/skills/a2a/SKILL.md`](../a2a/SKILL.md)
- debri runbook (contrast): [`.agents/skills/a2a-debri-runbook/SKILL.md`](../a2a-debri-runbook/SKILL.md)
