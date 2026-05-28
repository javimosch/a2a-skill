# a2a Example Agents

This directory contains example agent implementations demonstrating different collaboration patterns and use cases for the a2a peer messaging system.

## Overview

Each agent demonstrates core a2a concepts:
- **No central orchestrator** — agents make their own decisions
- **Async message-driven coordination** — agents don't block on responses
- **Decentralized work distribution** — peers self-organize
- **Status tracking** — agents mark themselves `done` when finished

## Example Agents

### 1. Researcher Agent (`researcher_agent.py`)

A researcher who investigates a topic by asking peers for information, aggregating responses, and broadcasting findings.

**Pattern demonstrated:**
- Broadcasting to all peers
- Waiting for and collecting async responses
- Aggregating results
- Marking completion

**Usage:**
```bash
# Terminal 1: start researcher (and other peers)
python3 examples/researcher_agent.py &
python3 examples/code_reviewer_agent.py &
python3 examples/task_coordinator_agent.py &

# Monitor messages on the bus
a2a peek --limit 50

# Wait for all to finish
a2a list  # check all have status='done'
```

**Key behaviors:**
1. Introduces self and broadcasts a question to all peers
2. Listens for responses (up to 30s)
3. Summarizes findings from all peers who responded
4. Marks `status=done` when complete

### 2. Code Reviewer Agent (`code_reviewer_agent.py`)

A reviewer who waits for code submissions from peers, provides feedback, and handles multiple reviews concurrently.

**Pattern demonstrated:**
- Async request-response without blocking
- Handling multiple concurrent requests
- Point-to-point replies to specific peers
- Early termination after sufficient work

**Usage:**
```bash
python3 examples/code_reviewer_agent.py &

# Other agents can send review requests
a2a send reviewer "Please review my code diff: ..." --from worker
```

**Key behaviors:**
1. Advertises availability to all peers
2. Listens for incoming code review requests
3. Responds directly to each requester with feedback
4. After a few iterations, marks `status=done`

### 3. Task Coordinator Agent (`task_coordinator_agent.py`)

A coordinator who distributes work to available peers and collects completion reports.

**Pattern demonstrated:**
- Work distribution without pre-coordination
- Tracking assigned tasks
- Listening for completion reports
- Broadcasting team progress

**Usage:**
```bash
python3 examples/task_coordinator_agent.py &

# Other agents receive task assignments and respond
```

**Key behaviors:**
1. Discovers available peers using `a2a list`
2. Assigns tasks to peers one-by-one
3. Waits for completion reports (up to 60s)
4. Broadcasts final sprint status
5. Marks `status=done`

### 4. Spawn Coordinator (`spawn_coordinator.py`)

An orchestrator harness that spawns worker agents as background AI CLI sessions
via `a2a-spawn`, assigns tasks on the bus, and collects results.

**Pattern demonstrated:**
- Pattern 3 (auto-spawn) using `a2a-spawn`
- Spawning agents as background processes via `subprocess`
- Assigning tasks on the bus and collecting results
- PID tracking and cleanup

**Usage:**
```bash
python3 examples/spawn_coordinator.py --project mytest --cli claude
```

**Key behaviors:**
1. Registers itself as coordinator plus two workers
2. Writes kit prompts to temp files and spawns workers via `a2a-spawn`
3. Sends task assignments to each worker via `a2a send`
4. Collects results via `a2a recv --wait`
5. Broadcasts a summary and cleans up spawned PIDs

**Requires:** The chosen AI CLI (`claude`, `opencode`, or `pi`) installed and configured.

### 5. Remote Worktree Team (`remote_worktree_team.sh`)

A complete shell script that spawns a 4-person multi-role team on a **remote
machine**, working in a fresh git worktree. Demonstrated by having 2 haiku +
2 sonnet Claude agents design, implement, and test a new feature from scratch.

**Pattern demonstrated:**
- Remote spawn over SSH (Pattern 3 on a remote host)
- Git worktree isolation (team works on a branch, main stays clean)
- Mixed-model teams (haiku for coordination/QA, sonnet for design/implementation)
- Goal mode — PM announces a GOAL, architect designs, dev implements, QA tests

**Usage:**
```bash
./examples/remote_worktree_team.sh [remote_host] [repo_path] [branch] [project]
# e.g.:
./examples/remote_worktree_team.sh rbm2 /root/projects/a2a-skill feature/my-feature my-feat
```

**What the team does:**
1. `pm` (haiku) picks a feature goal and broadcasts it
2. `architect` (sonnet) sends a detailed DESIGN spec to dev1 and a TESTPLAN to qa
3. `dev1` (sonnet) implements the feature in the worktree, signals IMPL-DONE
4. `architect` reviews the implementation and approves or requests fixes
5. `qa` (haiku) runs the full test suite and manual tests, issues QA-APPROVED
6. `pm` announces GOAL COMPLETE

**Monitor from your local machine:**
```bash
ssh rbm2 "A2A_PROJECT=my-feat a2a peek --limit 50"
ssh rbm2 "A2A_PROJECT=my-feat a2a list"
ssh rbm2 "tail -f /tmp/a2a-my-feat-dev1.log"
```

**Key caveats (see `docs/PITFALLS.md` → "Remote machine spawn"):**
- SSH will be unresponsive for 60–90s after spawning — agents are busy starting
- `claude` and `a2a-spawn` are often not on PATH in non-login SSH sessions
- Always pass `--project` explicitly; never rely on `basename($PWD)`
- Resolve stale rebases and diverged branches before creating the worktree

**Requires:** ssh access to remote host, claude CLI installed at `~/.local/bin/claude`.

### 6. Spawn Debate (`spawn_debate.py`)

An adversarial debate harness that spawns proposer and critic agents as
background AI CLI sessions via `a2a-spawn`, then monitors their exchange.

**Pattern demonstrated:**
- Pattern 3 (auto-spawn) with adversarial peers
- Bus monitoring loop
- Auto-detection when all agents complete

**Usage:**
```bash
python3 examples/spawn_debate.py --project mydebate --cli claude
```

**Key behaviors:**
1. Registers proposer, critic, and a bus-monitor agent
2. Spawns both agents via `a2a-spawn`
3. Monitors the bus in a polling loop, printing each new message
4. Detects when both agents mark themselves done and exits
5. Shows final bus state and cleans up spawned PIDs

**Requires:** The chosen AI CLI (`claude`, `opencode`, or `pi`) installed and configured.

## Common Patterns

### Pattern 1: Request-Response (Async)
```bash
# Agent A asks Agent B
a2a send B "question?" --from A

# Agent B listens (non-blocking)
a2a recv --as B --wait 30

# Agent B responds directly to A
a2a send A "answer" --from B
```

### Pattern 2: Broadcast & Aggregate
```bash
# Agent A broadcasts to all
a2a send all "need help with X" --from A

# Multiple agents listen and respond
a2a recv --as A --wait 30
a2a send A "we can help" --from B
a2a send A "available to help" --from C
```

### Pattern 3: Work Distribution
```bash
# Coordinator assigns work
a2a send worker "task description" --from coordinator

# Worker reports back
a2a send coordinator "task completed" --from worker

# Coordinator tracks progress
a2a recv --as coordinator --wait 30
```

## Running a Multi-Agent Scenario

**Step 1: Initialize the project**
```bash
export A2A_PROJECT=my-agents
a2a init
```

**Step 2: Register agents**
```bash
a2a register researcher --role "investigator" --cli python
a2a register reviewer --role "code-reviewer" --cli python
a2a register coordinator --role "task-manager" --cli python
```

**Step 3: Spawn agents**
```bash
# Run in separate terminals or background
python3 examples/researcher_agent.py &
python3 examples/code_reviewer_agent.py &
python3 examples/task_coordinator_agent.py &
```

**Step 4: Monitor the bus**
```bash
# In a separate terminal, watch messages flow
while true; do
  echo "=== Bus State $(date) ==="
  a2a peek --limit 20
  sleep 5
done
```

**Step 5: Verify completion**
```bash
# All agents should eventually mark status='done'
a2a list
```

## Extending the Examples

### Create Your Own Agent

```python
import os
import subprocess
import json

def run(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def main():
    agent_id = "my-agent"
    a2a = "a2a"  # or find it dynamically

    # Introduce yourself
    run(f'{a2a} send all "Hello, I am {agent_id}" --from {agent_id}')

    # Listen for messages
    messages = json.loads(run(f"{a2a} recv --as {agent_id} --json --wait 30") or "[]")
    for msg in messages:
        print(f"Got message from {msg['sender']}: {msg['body']}")

    # Do your work...

    # Mark done
    run(f"{a2a} status done --as {agent_id}")

if __name__ == "__main__":
    main()
```

### Key Functions

- `a2a register <id>` — Register before you can send/recv
- `a2a send <to> "<msg>" --from <id>` — Send message (to agent id or "all")
- `a2a recv --as <id> --wait N` — Receive unread messages (block up to N seconds)
- `a2a list --json` — List all registered agents
- `a2a status done --as <id>` — Mark yourself done
- `a2a peek --limit N` — View recent messages (observer mode)

## Tips for Writing a2a Agents

1. **No assumptions about peers** — Use `a2a list --json` to discover who's online
2. **Don't invent peers** — Only send to agents that exist
3. **Stay asynchronous** — Don't wait forever for responses, use `--wait 30` or similar
4. **Keep messages short** — The a2a bus is for coordination, not bulk data transfer
5. **Mark yourself done** — When your work is complete, call `a2a status done --as <id>`
6. **Handle empty responses** — Peers may not answer; plan for `recv` to timeout gracefully
7. **Use threads for parallel work** — If you need to do multiple things, spawn threads within your agent

## Testing Your Agent

```bash
# Start fresh
a2a clear --yes
a2a init

# Register your agent + a test peer
a2a register my-agent --role tester --cli python
a2a register test-peer --role assistant --cli python

# Spawn your agent
python3 my_agent.py > /tmp/my_agent.log 2>&1 &
MY_AGENT_PID=$!

# Simulate test peer responses
a2a send my-agent "test response" --from test-peer

# Check your agent's messages
a2a recv --as my-agent --all

# Monitor progress
a2a peek
a2a list

# Cleanup
kill $MY_AGENT_PID
a2a clear --yes
```

## Troubleshooting

**Agent hangs:**
- Check that it's registered: `a2a list`
- Check that it's receiving messages: `a2a recv --as <agent-id> --all`
- Add logging to see where it's stuck

**No messages exchanged:**
- Verify both agents are registered: `a2a list`
- Check sender/recipient spelling matches `a2a list` output
- Use `a2a peek` to verify messages are on the bus

**Messages not appearing:**
- Ensure `a2a send` completed successfully (check exit code)
- Check project name: `export A2A_PROJECT=...` before running agents

## See Also

- [docs/SKILL.md](../docs/SKILL.md) — Full a2a skill specification
- [README.md](../README.md) — Project overview
- [AGENTS.md](../AGENTS.md) — Guide for extending a2a
- [test_a2a.py](../test_a2a.py) — Unit tests showing all features
