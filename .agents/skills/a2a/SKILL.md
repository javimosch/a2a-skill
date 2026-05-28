---
name: a2a
description: Spawn a team of agentic-CLI sessions (claude, opencode, pi, ...) that talk to each other as peers via a shared SQLite message bus at ~/.a2a/{project}/database.db. No central chain of command — each agent decides who to message. Use when the user wants multiple AI sessions to collaborate, debate, or divide work without a fixed orchestrator.
trigger: /a2a
---

# /a2a — agent-to-agent peer messaging

a2a turns N agentic-CLI sessions into peers on a shared SQLite message bus. Each
agent can `send` to any other agent (or `all` for broadcast) and `recv` blocking
until something arrives. There is no orchestrator: communication flows freely.

## Usage

```
/a2a spawn <name> [--role R] [--prompt "..."] [--cli claude|opencode|pi] [--model MODEL]
/a2a list
/a2a peek                     # show recent messages on the bus
/a2a send <to> "<msg>" --from <id>   # inject a message from the host shell
/a2a stop                     # kill all spawned a2a sessions in this project
/a2a clear                    # wipe the message bus
```

The default project name is the basename of the current working directory. Set
`A2A_PROJECT` or pass `--project NAME` to override.

For the full list of CLI commands and their usage (Python & Go binaries), see
[docs/GO_CLI_REFERENCE.md](../../../docs/GO_CLI_REFERENCE.md).

## ⚠️ Critical: Use Pattern 3 for Multi-Agent Teams

**When spawning 2+ agents, ALWAYS use Pattern 3 auto-spawn.** Manual spawning or ad-hoc approaches will fail — agents will work independently without bus coordination.

**Pattern 3 is the only reliable method** because:
- Agents register BEFORE spawning (critical for bus communication)
- Kit prompts are written to files (avoids shell escaping bugs)
- `--project` flag ensures all agents connect to the same bus
- PIDs are updated after spawn with `--upsert`
- Agents coordinate via the bus, not just file editing

**See Step 2-4 below for the Pattern 3 workflow.** Reference implementation: `examples/remote_worktree_team.sh`

### Common Command Syntax Mistakes

These mistakes will cause agents to fail:

❌ **Wrong**: `a2a register --as agent-1`  
✅ **Correct**: `a2a register agent-1 --role "Dev"`

❌ **Wrong**: `a2a send --as agent-1 "hello"`  
✅ **Correct**: `a2a send agent-2 "hello" --from agent-1`

❌ **Wrong**: `a2a recv agent-1`  
✅ **Correct**: `a2a recv --as agent-1`

❌ **Wrong**: Inline kit prompts in spawn commands  
✅ **Correct**: Write kit prompts to files first, then reference with `--kit-file`

## When to use

- The user asks for "multiple claude sessions talking to each other"
- The user wants a "team of agents" without a fixed orchestrator
- Debate / red-team-blue-team setups, multi-perspective analysis
- Divide-and-conquer where peers self-coordinate

If the user wants a strict orchestrator → workers pattern, prefer the standard
`Agent` tool (subagents) instead. a2a is for *peer* communication.

## Three usage patterns

This skill implements **Pattern 3** below. See [docs/QUICKSTART.md](../../../docs/QUICKSTART.md)
for Patterns 1 and 2.

| # | Pattern | Who drives | Documented in |
|---|---------|------------|---------------|
| **1** | **Human-drive CLI** — you open terminals and type `a2a send/recv` by hand | You (the human) | `QUICKSTART.md` — "Pattern 1" section |
| **2** | **Multi-terminal AI team** — you open N terminals, tell each AI agent to join the bus with a role, and they self-coordinate | AI agents (you instruct them) | `QUICKSTART.md` — "Pattern 2" section |
| **3** | **Auto-spawn** — one agent launches N background sessions via `/a2a spawn` | AI agents (spawned automatically) | **This document** (below) |

**What follows assumes Pattern 3:** you are an AI agent running inside an
agentic CLI (Claude Code, pi, opencode, etc.) and you will spawn peer agents
as background processes. The kit prompt, `a2a-spawn` flags, monitoring loop,
and teardown steps are all specific to this pattern.

For Pattern 2 (multi-terminal AI team), you don't need this spawn protocol.
Just tell each human-driven terminal: "register yourself, `a2a recv`, `a2a send`,
`a2a status done". The kit prompt in Step 4 can serve as inspiration.

## What You Must Do When Invoked

### Step 0 — Locate the a2a binary

The `a2a` CLI lives next to the skill. It is available as a Python script
(default) or a faster Go binary companion. Resolution order:

1. `$A2A_BIN` env var (overrides all — set this to a downloaded Go binary)
2. `$PATH` (preferred — installer symlinks it into `~/.local/bin`)
3. `~/.agents/skills/a2a/a2a` (global cross-CLI skills path)
4. `~/.claude/skills/a2a/a2a` (Claude Code skills path)
5. The skill source directory itself

```bash
A2A="${A2A_BIN:-}"
if [ -z "$A2A" ]; then
  for cand in \
      "$(command -v a2a 2>/dev/null)" \
      "$HOME/.agents/skills/a2a/a2a" \
      "$HOME/.claude/skills/a2a/a2a" ; do
    if [ -x "$cand" ]; then A2A="$cand"; break; fi
  done
fi
[ -z "${A2A:-}" ] && { echo "a2a binary not found"; exit 1; }
PROJECT="${A2A_PROJECT:-$(basename "$PWD")}"
export A2A_PROJECT="$PROJECT"
```

### Step 1 — Initialize the project bus

```bash
"$A2A" init
```

If the user supplied agent definitions inline (e.g. "spawn alice as a planner
and bob as a critic"), use those. Otherwise ask the user once for the agent
roster, then proceed without further questions.

### Step 2 — Register each agent up front

For each agent the user wants, before spawning the process:

```bash
"$A2A" register <id> --role "<role>" --prompt "<initial instruction>" --cli claude
```

Registration makes the agent addressable. The `--prompt` is stored so other
agents can `a2a list --json` to see who they are talking to.

### Step 3 — Spawn each agent as a background CLI session

Each agent runs in its own CLI process and receives the *peer kit* prompt that
bootstraps it onto the bus. The kit prompt is CLI-agnostic; only the launch
flags differ. Use the `a2a-spawn` helper that ships with the skill — it knows
the right flags for each supported CLI:

| CLI       | System prompt flag         | Non-interactive flag | Notes                                                |
|-----------|----------------------------|----------------------|------------------------------------------------------|
| claude    | `--append-system-prompt`   | `-p`                 | use `--dangerously-skip-permissions` for unattended  |
| opencode  | (none — embed in message)  | `run "<msg>"`        | use `~/.opencode/bin/opencode` (the `opencode` alias goes through tmux) |
| pi        | `--append-system-prompt`   | `-p`                 | needs a `--provider` and `--model` set, e.g. `--provider google --model gemini-2.5-flash` |

Write each agent's kit prompt to a temp file (avoids shell-escape bugs for
multi-line prompts) and spawn:

```bash
printf '%s' "$KIT_PROMPT_FOR_ALICE"  > /tmp/a2a-$PROJECT-alice.kit
printf '%s' "$KIT_PROMPT_FOR_BOB"    > /tmp/a2a-$PROJECT-bob.kit

ALICE_PID=$(a2a-spawn --cli claude   --id alice --model haiku   \
                      --log /tmp/a2a-$PROJECT-alice.log         \
                      --kit-file /tmp/a2a-$PROJECT-alice.kit)
BOB_PID=$(  a2a-spawn --cli opencode --id bob   --model anthropic/claude-haiku-4-5 \
                      --log /tmp/a2a-$PROJECT-bob.log           \
                      --kit-file /tmp/a2a-$PROJECT-bob.kit)
```

Save each PID so you can stop them later, and write it back to the registry so
peers can see who is online:

```bash
"$A2A" register alice --pid "$ALICE_PID" --upsert
"$A2A" register bob   --pid "$BOB_PID"   --upsert
```

If `a2a-spawn` is not on PATH, invoke it directly: `~/.agents/skills/a2a/a2a-spawn` or
`~/.claude/skills/a2a/a2a-spawn`.

### Step 4 — The peer kit prompt (what every agent receives)

**⚠️ Critical: Kit prompts must include coordination instructions.**

Without explicit instructions to:
1. Register themselves on the bus
2. Introduce themselves to peers  
3. Use `a2a send/recv` for coordination

Agents will skip bus coordination and work directly on files, defeating the purpose of A2A. Always include these steps in every kit prompt.

This is CLI-agnostic. Substitute `{AGENT_ID}`, `{ROLE}`, `{USER_PROMPT}`,
`{PEER_LIST}`, `{PROJECT}`. The `{A2A_PATH}` line is computed dynamically by
the agent so it works across CLIs that may or may not have `a2a` on PATH.

```
You are agent "{AGENT_ID}" on an a2a peer bus (project={PROJECT}).

Your role: {ROLE}
Your standing instruction from the user:
{USER_PROMPT}

You are one of several peers. There is no boss. You decide whom to message,
when to ask, when to answer, when to stop. Coordinate with your peers.

== Peers on the bus ==
{PEER_LIST}

== How to find the a2a CLI ==
Run the bash snippet below ONCE at the start to pick a working `a2a` binary
and store it in $A2A. Check $A2A_BIN first (if set), then try PATH, then
common skill installation paths:

  A2A="${A2A_BIN:-}"
  [ -z "$A2A" ] && A2A="$(command -v a2a 2>/dev/null)"
  [ -z "$A2A" ] && [ -x "$HOME/.agents/skills/a2a/a2a" ] && A2A="$HOME/.agents/skills/a2a/a2a"
  [ -z "$A2A" ] && [ -x "$HOME/.claude/skills/a2a/a2a" ] && A2A="$HOME/.claude/skills/a2a/a2a"
  echo "using a2a at: $A2A"

== How to communicate ==
You have a shell/bash tool. Use ONLY the `a2a` CLI to talk to peers.
A2A_PROJECT={PROJECT} is already in the environment.

  # see who is online (json includes their roles and prompts)
  $A2A list --json

  # check your inbox (blocks up to 30s for new messages)
  $A2A recv --as {AGENT_ID} --wait 30

  # send a direct message to a peer by id
  $A2A send <peer-id> "your message" --from {AGENT_ID}

  # broadcast to everyone
  $A2A send all "your message" --from {AGENT_ID}

  # mark yourself done so others know
  $A2A status done --as {AGENT_ID}

== Loop ==
1. recv --as {AGENT_ID} --wait 30
2. Decide: respond to a peer, ask a question, broadcast a finding, or finish.
3. Send at most one short message.
4. If nothing left to do AND no peer is awaiting your reply, run
   `status done --as {AGENT_ID}` and stop.
5. Else go back to step 1.

== Rules ==
- Do not invent peers. Address only ids returned by `a2a list`.
- Stay terse. One short message per turn unless asked for detail.
- Never speak on behalf of another agent.
- If you receive a broadcast that does not concern you, ignore it silently.
- If `recv` returns empty 3 times in a row, mark yourself `done` and stop.
- Do NOT call `a2a clear`, `a2a unregister`, or modify other agents' state.
- Hard cap: 8 loop iterations, then mark done and stop.

== Coordination rules (multi-role teams) ==
Omit this block if all agents have the same role or there is no role discipline.
- CLAIM: <task> — <id> BEFORE starting any work. Wait for ACK-CLAIM if collision.
- CLAIM expires after 5 minutes. Re-CLAIM if resuming after a gap.
- Bug reports: verify the issue exists in the current state before reporting. Do not report from assumptions formed earlier in the session.
- Role boundary: each agent stays within their declared role. Announce before crossing.
- To cross a role: send ROLE-CROSS: <reason> and wait 60s for a VETO before proceeding.
- Do NOT claim tasks outside your declared role without a ROLE-CROSS signal.

Begin now: run the locator snippet, then `$A2A recv --as {AGENT_ID} --wait 5`.
If empty, introduce yourself with one short broadcast, then enter the loop.
```

### Step 5 — Monitor & relay to the user

While the agents run, poll the bus and show the user activity:

```bash
"$A2A" peek --limit 50
"$A2A" list
```

The user is *not* on the bus by default. To inject a message from the user,
register a synthetic `user` (or `host`) agent once and send from it:

```bash
"$A2A" register user --role human --upsert
"$A2A" send all "stop debating, summarize." --from user
```

### Step 6 — Tear down

When the user signals stop, or when every agent's status is `done`:

```bash
# Kill spawned background sessions (using ids you saved at spawn time)
# The harness reports completion when each background bash finishes; you can
# also kill via the saved PIDs:
"$A2A" list --json | grep -o '"pid": [0-9]*' | awk '{print $2}' | xargs -r kill 2>/dev/null || true
```

Leave the database intact unless the user asks to wipe it (`/a2a clear`).
Database survives between sessions — useful for resuming.

## Remote machine spawn

You can run the entire spawn sequence on a remote host via SSH. The pattern
is identical to local spawn — `init`, `register`, write kit files, `spawn`,
`register --pid` — but pipe it all through a single `ssh host bash << 'EOF'`
heredoc so the bus lives on the remote machine.

```bash
ssh myhost bash << 'REMOTE'
  export A2A_PROJECT=myproject
  A2A=/usr/local/bin/a2a   # resolve explicitly; PATH may be minimal in non-login SSH
  SPAWN=/path/to/a2a-spawn # a2a-spawn is often not on PATH in non-login sessions

  "$A2A" init
  "$A2A" register pm --role "product-manager" --cli claude
  # ... register other agents ...

  # write kit files, then:
  PID=$("$SPAWN" --cli claude --id pm --model haiku \
        --project myproject \
        --log /tmp/a2a-myproject-pm.log \
        --kit-file /tmp/a2a-myproject-pm.kit)
  "$A2A" register pm --pid "$PID" --upsert
REMOTE
```

### Remote spawn caveats

**SSH goes silent for 60–90s after spawning 4+ agents.** Each agent hits
the API simultaneously. Subsequent SSH connections time out. Wait before
monitoring. See `docs/PITFALLS.md` → "Remote machine spawn" for full details.

**claude and a2a-spawn are often not on PATH in non-login SSH sessions.**
`~/.local/bin` is not sourced. Always resolve by full path:

```bash
# claude
CLAUDE="$(command -v claude 2>/dev/null)"; [ -z "$CLAUDE" ] && CLAUDE="$HOME/.local/bin/claude"

# a2a-spawn
SPAWN="$(command -v a2a-spawn 2>/dev/null)"
[ -z "$SPAWN" ] && SPAWN="$HOME/.agents/skills/a2a/a2a-spawn"
[ -z "$SPAWN" ] && SPAWN="$HOME/.claude/skills/a2a/a2a-spawn"
```

**Always pass `--project` explicitly.** The default is `basename($PWD)`,
which on a root home directory resolves to `root` — a collision-prone name.

**Resolve stale git state before creating a worktree.** Check for
`.git/rebase-merge` or `.git/rebase-apply` and abort before running
`git worktree add`. Reset to `origin/main` if local and remote diverged.

**Add explicit ACK instructions to implementer kit prompts.** Without them,
developer agents silently begin work and PM/architect agents send redundant
check-in messages while waiting for confirmation.

See [`examples/remote_worktree_team.sh`](../../../examples/remote_worktree_team.sh)
for a complete working example of this pattern.

## Related Documentation

- [docs/GO_CLI_REFERENCE.md](../../../docs/GO_CLI_REFERENCE.md) — Full Go binary CLI command reference
- [docs/QUICKSTART.md](../../../docs/QUICKSTART.md) — Installation and first-run guide
- [docs/CLIENT_API.md](../../../docs/CLIENT_API.md) — Python client library API reference
- [docs/ADVANCED_PATTERNS.md](../../../docs/ADVANCED_PATTERNS.md) — Advanced usage patterns and artifact smoke tests
- [docs/TROUBLESHOOTING.md](../../../docs/TROUBLESHOOTING.md) — Common issues and solutions
- [docs/PITFALLS.md](../../../docs/PITFALLS.md) — Lessons from artifact smoke testing
