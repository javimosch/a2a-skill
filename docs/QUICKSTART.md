# a2a Quickstart Guide

Get started with a2a peer-to-peer messaging in 5 minutes.

## What is a2a?

a2a lets multiple AI agents or programs collaborate over a shared message bus, with no central orchestrator. Each agent can send and receive messages independently.

Perfect for:
- Teams of AI agents (claude, opencode, pi) working together
- Async workflows where workers report back to a coordinator
- Debates or multi-perspective analysis
- Distributed task execution

## Installation

```bash
# Clone the repo
git clone https://github.com/javimosch/a2a-skill.git
cd a2a-skill

# Run installer (adds a2a to PATH and Claude Code)
./install.sh

# Verify
a2a --help
```

Or manually:
```bash
ln -sf "$PWD/a2a" ~/.local/bin/a2a
ln -sf "$PWD"     ~/.claude/skills/a2a
```

**Prerequisite:** Python 3 with `sqlite3` (most systems have this built-in).

## Choose your pattern

a2a supports three usage patterns. Pick the one that fits your workflow.

| # | Pattern | Who drives | When to use |
|---|---------|------------|-------------|
| **1** | **Human-drive CLI** — you open terminals and type `a2a send/recv` by hand | You (the human) | Learning the bus, testing, quick scripting |
| **2** | **Multi-terminal AI team** — you open N terminals, tell each AI agent to join the bus with a role, and they self-coordinate | AI agents (you instruct them) | Role-based teamwork, debates, complex multi-perspective analysis |
| **3** | **Auto-spawn** — one agent launches N background sessions via `/a2a spawn` | AI agents (spawned automatically) | Fire-and-forget collaboration from inside a coding session |

**Start here ↓** Pattern 1 is the simplest way to learn the bus.
Skip to [Pattern 2](#pattern-2-multi-terminal-ai-team) if you already know the basics,
or [Pattern 3](#pattern-3-auto-spawn-from-another-agent) for the auto-spawn flow.

---

## Pattern 1: Human-drive CLI — you type commands

In this pattern, **you** are the agent. You open terminals, register peers,
type `a2a send` / `a2a recv` yourself. The AI isn't involved — this is you
learning the bus.

### Terminal 1: Agent Alice

```bash
# Create a new project
a2a init --project hello-world

# Register Alice
a2a register alice --role "greeter"

# Wait for Bob's response (up to 10 seconds)
a2a recv --as alice --wait 10
```

Now Alice is listening. Leave this running.

### Terminal 2: Agent Bob

```bash
# Register Bob
a2a register bob --role "responder" --project hello-world

# Send message to Alice
a2a send alice "Hello Alice! How are you?" --from bob

# Wait for her reply
a2a recv --as bob --wait 10
```

### Back to Terminal 1: Alice Replies

```bash
# You should see Bob's message. Now send a reply
a2a send bob "I'm great, thanks for asking!" --from alice
```

### Terminal 2: Bob Reads It

```bash
# Refresh with C-c and re-run recv
a2a recv --as bob --wait 5
```

**🎉 You just had your first peer-to-peer conversation!**

## Broadcast Messages

One agent can message everyone at once:

```bash
# Terminal 1
a2a send all "Team standup in 5 min!" --from alice
```

Everyone will receive it:
```bash
# Terminal 2
a2a recv --as bob --wait 5
```

## 3+ Agents: A Simple Workflow

Let's build a coordinator + 2 workers scenario.

### Setup

```bash
a2a init --project workflow-demo

# Register agents
a2a register coordinator --role "manager"
a2a register worker1 --role "developer"
a2a register worker2 --role "tester"
```

### Terminal 1: Coordinator

```bash
# Assign tasks
a2a send worker1 "Please implement the login form" --from coordinator
a2a send worker2 "Please test the login form" --from coordinator

# Wait for completion reports
sleep 2
a2a recv --as coordinator --wait 20
```

### Terminal 2: Worker 1

```bash
# Receive task
a2a recv --as worker1 --wait 5

# Do work and report back
a2a send coordinator "Login form complete, ready for testing" --from worker1
```

### Terminal 3: Worker 2

```bash
# Receive task
a2a recv --as worker2 --wait 5

# Wait for worker1, then test
sleep 3
a2a send coordinator "All tests pass! Ready to ship" --from worker2
```

### Back to Terminal 1

```bash
# You should now see both completion reports
a2a recv --as coordinator --wait 20
```

---

## Pattern 2: Multi-terminal AI team — you instruct agents, they drive

In this pattern, **you open N terminals and tell each AI agent about the bus.**
You give them roles (e.g. developer, architect, QA, product manager) and a
shared project name. The agents then self-coordinate — they `recv`, `send`,
and `status done` on their own, just like peers in a messaging app.

This is the most flexible pattern: you hand-pick each agent's model, watch
their reasoning in real-time, and intervene by injecting messages as a
"human" agent on the bus.

### Example: 4-role team

```bash
# Terminal 0 — one-time setup (any project name works)
a2a init --project my-app
a2a register dev        --role developer
a2a register architect  --role architect
a2a register qa         --role tester
a2a register pm         --role "product manager"
```

Now open **four terminals**, one per agent. In each terminal, launch an AI
CLI (claude, pi, opencode, etc.) and give it instructions like this:

> You are agent `dev` on the a2a peer bus (project=my-app).
> Your role: developer.
> Known peers: architect, qa, pm.
>
> Use `a2a recv --as dev --wait 15` to check your inbox.
> Use `a2a send <peer> "message" --from dev` to talk to peers.
> Use `a2a list --json` to see who is online.
> Coordinate with your team. When done, `a2a status done --as dev`.

Each agent gets the same structure but a different `{agent_id}` and `{role}`.
They discover each other via `a2a list --json` and start collaborating
without any central orchestrator.

### Tips for running Pattern 2

- **Export A2A_PROJECT** in each terminal so you don't need `--project`:
  ```bash
  export A2A_PROJECT=my-app
  ```
- **Register yourself as a human peer** to inject messages mid-work:
  ```bash
  a2a register human --role user --upsert
  a2a send all "Change of plan: focus on auth first" --from human
  ```
- **Watch the bus** from a 5th terminal:
  ```bash
  watch -n 5 "a2a peek --limit 20"
  ```
- **Each agent** needs the `a2a` binary on PATH and shell access (standard
  for claude, pi, opencode).
- Agents self-regulate via the kit prompt conventions (iteration cap, "3 empty
  recvs = done"). You can also stop them by closing their terminal.

---

## Pattern 3: Auto-spawn from another agent

In this pattern, an AI agent (inside Claude Code, pi, or opencode) launches
N background peer sessions automatically using the `/a2a` skill. The spawning
agent handles registration, kit prompt generation, PID tracking, and teardown.

This is a fire-and-forget pattern — you don't watch each terminal. The agents
run in background and log output to files.

```bash
# Inside Claude Code:
/a2a spawn alice --role planner --cli claude --model haiku
/a2a spawn bob   --role critic  --cli claude --model haiku
/a2a list
/a2a peek
/a2a stop
```

See [`.agents/skills/a2a/SKILL.md`](../.agents/skills/a2a/SKILL.md) for the full protocol, kit prompt template,
and cross-CLI spawn flags.

---

## Commands Reference

```bash
# Initialization
a2a init                                    # Create fresh project

# Agents
a2a register alice --role "assistant"       # Add an agent
a2a list                                    # Who's online?

# Messaging
a2a send bob "hello" --from alice           # Direct message
a2a send all "hello team" --from alice      # Broadcast
a2a send bob "urgent!" --from alice --ttl 3600  # Expires in 1 hour

a2a recv --as bob --wait 10                 # Wait up to 10s for messages
a2a recv --as bob --all                     # See all messages (including read)
a2a recv --as bob --json                    # Machine-readable output

# Search & Threads
a2a search "keyword"                        # Search messages by content
a2a search "keyword" --json                 # Search as JSON
a2a thread <id>                             # View all messages in a thread

# Monitoring
a2a stats                                   # Bus statistics (messages, agents, senders)
a2a stats --json                            # Stats as JSON
a2a peek                                    # Last 20 messages
a2a peek --limit 50                         # Last 50
a2a list --json                             # Agent roster as JSON

# Status
a2a status done --as alice                  # Mark alice as done
a2a status active --as alice                # Mark alice as active

# Cleanup
a2a clear --yes                             # Delete project (be careful!)
```

## Using the Python API

For Python programs, use the direct API instead of shelling out:

```python
from a2a_client import A2AClient

client = A2AClient(project="hello-world", agent_id="alice")

# Send
client.send("bob", "Hello Bob!")

# Receive (waits 10 seconds)
messages = client.recv(wait=10)
for msg in messages:
    print(f"{msg['sender']}: {msg['body']}")

# Broadcast
client.send("all", "Team message!")

# Mark done
client.set_status("done")
```

See [docs/CLIENT_API.md](docs/CLIENT_API.md) for full documentation.

## Try Example Agents

a2a comes with three example agents showing different patterns:

```bash
# Run all three in parallel (auto-cleanup after ~60s)
./smoke_test_examples.sh
```

Or run individually:
```bash
# Terminal 1
python3 examples/researcher_agent.py &

# Terminal 2
python3 examples/code_reviewer_agent.py &

# Terminal 3
python3 examples/task_coordinator_agent.py &

# Monitor
a2a peek --limit 50
```

See [examples/README.md](../examples/README.md) for details on each pattern.

## Data Storage

All messages are stored locally in SQLite:

```bash
~/.a2a/{project}/database.db
```

No cloud, no auth required. Perfect for local testing and prototyping.

To inspect the database directly:

```bash
sqlite3 ~/.a2a/hello-world/database.db
sqlite> SELECT sender, body FROM messages LIMIT 5;
```

## Key Concepts

- **Project**: Isolated message bus. Each project = one database.
- **Agent**: An actor on the bus (AI, script, human, etc.). Must be registered.
- **Message**: Text from one agent to another (or broadcast to all).
- **Unread**: By default, `recv` shows only messages you haven't read yet.
- **Broadcast**: `recipient=NULL` in the database. Everyone receives once.
- **TTL**: Messages can expire after N seconds. Useful for transient tasks.
- **Status**: Agents track their state (active/idle/done/blocked) for visibility.

## What's Next?

1. **Write your own agent** — See the [examples/README.md](examples/README.md) for pattern guides and the [CLIENT_API.md](CLIENT_API.md) for Python client reference.
2. **Run example agents** — Try `./smoke_test_examples.sh` to see patterns in action.
3. **Use the Python client** — See [docs/CLIENT_API.md](docs/CLIENT_API.md) for direct API.
4. **Use in Claude Code** — Type `/a2a` to spawn peer teams from Claude Code.
5. **Cross-CLI collaboration** — Mix claude, opencode, pi agents on the same bus.

## Troubleshooting

**"a2a: command not found"**
- Run `./install.sh` to install a2a to PATH
- Or use the full path: `./a2a` from the repo directory

**"no a2a project at ~/.a2a/my-project/database.db"**
- Run `a2a init --project my-project` first to create the database

**"agent 'alice' already registered"**
- Either unregister it (`a2a unregister alice`) or use `--upsert` to update

**Database locked**
- Multiple processes trying to write at once. Retry after a moment.
- a2a uses WAL mode, so this is rare.

**No messages received**
- Verify sender used correct recipient: `a2a peek`
- Check agent is registered: `a2a list`
- Make sure you `recv` from the right agent ID

## Common Patterns

### Pattern: Broadcast → Aggregate

```bash
# Sender broadcasts to all
a2a send all "Question for the team" --from alice

# Multiple agents respond
a2a send alice "Response 1" --from bob
a2a send alice "Response 2" --from carol

# Sender collects all responses
a2a recv --as alice --wait 30
```

### Pattern: Task Distribution

```bash
# Coordinator assigns work
a2a send worker1 "Task A" --from coordinator
a2a send worker2 "Task B" --from coordinator

# Workers report completion
a2a send coordinator "Task A done" --from worker1
a2a send coordinator "Task B done" --from worker2

# Coordinator checks in
a2a recv --as coordinator --wait 30
```

### Pattern: Async Request-Response

```bash
# Alice asks Bob
a2a send bob "Can you review this?" --from alice

# Bob is busy, but eventually responds
# (no blocking needed)
a2a send alice "Reviewed! Looks good." --from bob

# Alice checks later
a2a recv --as alice --wait 5
```

## Resources

- **[README.md](../README.md)** — Full project overview
- **[`.agents/skills/a2a/SKILL.md`](../.agents/skills/a2a/SKILL.md)** — Technical deep dive (architecture, schema, protocol, spawn flow)
- **[CLIENT_API.md](docs/CLIENT_API.md)** — Python client library reference
- **[examples/](../examples/)** — Agent pattern examples (researcher, reviewer, coordinator)
- **[CONTRIBUTING.md](docs/CONTRIBUTING.md)** — Developer guide for extending a2a

## Questions?

- Check the [README](../README.md) FAQ
- Review [AGENTS.md](../AGENTS.md) for architecture and design
- Look at [examples/README.md](../examples/README.md) for patterns
- Run the tests: `python3 test_a2a.py -v`

Happy messaging! 🚀
