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

## When to use

- The user asks for "multiple claude sessions talking to each other"
- The user wants a "team of agents" without a fixed orchestrator
- Debate / red-team-blue-team setups, multi-perspective analysis
- Divide-and-conquer where peers self-coordinate

If the user wants a strict orchestrator → workers pattern, prefer the standard
`Agent` tool (subagents) instead. a2a is for *peer* communication.

## The CLI

`a2a` is available as a Python script (stdlib only) or a Go binary
(zero dependencies, ~1.3MB). Both share the same commands and JSON output.
See [GO_CLI_REFERENCE.md](GO_CLI_REFERENCE.md) for the Go binary.

### Python (reference)

`a2a` is a small Python script. It is CLI-agnostic — anything that can shell out
can use it. Requires python3 + sqlite3 (both stdlib, always available on modern systems).

### Go (companion binary)

The Go binary is a drop-in replacement with faster startup (~5ms vs ~80ms)
and zero runtime dependencies. Download or build:

```bash
# Download latest release
curl -sL "https://github.com/jarancibia/a2a-skill/releases/latest/download/a2a-$(uname -s)-$(uname -m)" -o /tmp/a2a
chmod +x /tmp/a2a

# Or build from source
cd a2a-skill && go build -tags fts5 -o a2a ./cmd/a2a/
```

```
a2a init                                       # create ~/.a2a/{project}/database.db
a2a register <id> [--role R] [--prompt P]      # register an agent
a2a register <id> --upsert                     # update existing agent
a2a list [--json]                              # list agents
a2a send <to> "<body>" --from <id>             # to: agent-id, or 'all' for broadcast
a2a send <to> "<body>" --from <id> --ttl 300   # message expires in 5 minutes
a2a recv --as <id> [--wait 30]                 # unread inbox (blocks up to 30s)
a2a recv --as <id> --all                       # include already-read messages
a2a recv --as <id> --peek                      # look without marking read
a2a recv --as <id> --include-self              # include own messages
a2a recv --as <id> --since 1700000000          # messages after timestamp
a2a recv --as <id> --json                      # machine-readable output
a2a search <query> [--json] [--limit N]         # search messages by content (substring)
a2a thread <id> [--json]                        # show all messages in a thread
a2a stats [--json]                              # bus statistics (msgs, agents, senders)
a2a peek [--limit 20] [--json]                  # observer view of the bus
a2a status active|idle|done|blocked --as <id>   # update agent status (supports --json)
a2a wait --as <id> --count 1 --timeout 60       # block until N unread
a2a clear --yes                                 # delete the project db
a2a project                                     # show resolved project info
```

`recv` returns *unread* messages addressed to the agent (or broadcast). On a
successful read, messages are marked read for that agent. `--wait N` blocks up
to N seconds for at least one new message.

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
and store it in $A2A. Try in this order:
  1. Whatever `command -v a2a` resolves to
  2. ~/.agents/skills/a2a/a2a    (cross-CLI global skills path)
  3. ~/.claude/skills/a2a/a2a    (Claude Code skills path)

  A2A="$(command -v a2a 2>/dev/null)"
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

## Smoke test recipe (haiku, non-interactive)

This is the canonical end-to-end check. Drop it into a scratch dir and run.

```bash
# Auto-locate a2a (resolves from PATH or common locations)
A2A="$(command -v a2a 2>/dev/null)"
[ -z "$A2A" ] && [ -x "$HOME/.agents/skills/a2a/a2a" ] && A2A="$HOME/.agents/skills/a2a/a2a"
[ -z "$A2A" ] && [ -x "$HOME/.claude/skills/a2a/a2a" ] && A2A="$HOME/.claude/skills/a2a/a2a"
[ -z "$A2A" ] && { echo "a2a not found"; exit 1; }

PROJECT=a2a-smoke-$$
export A2A_PROJECT=$PROJECT

"$A2A" init
"$A2A" register alice --role planner \
  --prompt "Propose a one-line plan for greeting the team, then ask bob to critique."
"$A2A" register bob   --role critic  \
  --prompt "Critique alice's plan in one sentence. Then mark yourself done."

KIT() {  # build kit prompt for a given id/role/prompt
  cat <<EOF
You are agent "$1" on an a2a peer bus (project=$PROJECT).
Role: $2
Instruction: $3
Use: $A2A --project $PROJECT recv --as $1 --wait 15
     $A2A --project $PROJECT send <peer> "msg" --from $1
     $A2A --project $PROJECT status done --as $1
Peers: $($A2A list --json)
Stay terse. After 2 empty recvs, mark done and exit.
EOF
}

claude -p --model haiku --dangerously-skip-permissions \
  --append-system-prompt "$(KIT alice planner 'introduce yourself and ask bob to critique your one-line plan')" \
  "Begin." > /tmp/$PROJECT-alice.log 2>&1 &
ALICE_PID=$!

claude -p --model haiku --dangerously-skip-permissions \
  --append-system-prompt "$(KIT bob critic 'wait for alice, critique in one sentence, then status done')" \
  "Begin." > /tmp/$PROJECT-bob.log 2>&1 &
BOB_PID=$!

# tail the bus
for i in 1 2 3 4 5 6; do sleep 5; "$A2A" peek --limit 20; echo "---"; done
wait $ALICE_PID $BOB_PID 2>/dev/null
"$A2A" peek --limit 50
```

Success = there are messages from `alice` to `bob` *and* from `bob` to `alice`
on the bus, and both agents end with `status='done'`.

## Honesty rules

- Agents only know what's on the bus. If they invent peers, that's a bug.
- The database is the source of truth — never claim a message was sent without
  checking it appears in `peek`.
- If a spawned CLI never produces messages within ~60s, dump its log
  (`/tmp/a2a-$PROJECT-<id>.log`) and tell the user what went wrong.
- Do not run a2a in production-touching projects without an explicit user ok —
  agents can run shell commands.
