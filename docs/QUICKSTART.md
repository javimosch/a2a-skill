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

## Your First 2-Agent Conversation

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

See [CLIENT_API.md](CLIENT_API.md) for full documentation.

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

See [examples/README.md](examples/README.md) for details on each pattern.

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

1. **Write your own agent** — See [CONTRIBUTING.md](CONTRIBUTING.md) for development guide.
2. **Run example agents** — Try `./smoke_test_examples.sh` to see patterns in action.
3. **Use the Python client** — See [CLIENT_API.md](CLIENT_API.md) for direct API.
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

- **[README.md](README.md)** — Full project overview
- **[SKILL.md](SKILL.md)** — Technical deep dive (architecture, schema, protocol)
- **[CLIENT_API.md](CLIENT_API.md)** — Python client library reference
- **[examples/](examples/)** — Agent pattern examples (researcher, reviewer, coordinator)
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Developer guide for extending a2a

## Questions?

- Check the [README](README.md) FAQ
- Review [AGENTS.md](AGENTS.md) for architecture and design
- Look at [examples/README.md](examples/README.md) for patterns
- Run the tests: `python3 test_a2a.py -v`

Happy messaging! 🚀
