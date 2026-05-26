# a2a Python Client Library

The `a2a_client.py` module provides a Python object-oriented API for a2a messaging, eliminating the need to shell out to the `a2a` CLI.

## Installation

```bash
# Copy a2a_client.py to your project or install via pip (if published)
cp a2a_client.py /path/to/your/project/
```

## Quick Start

```python
from a2a_client import A2AClient

# Initialize client
client = A2AClient(project="my-project", agent_id="alice")

# Send a message
msg_id = client.send("bob", "Hello Bob!")

# Receive messages (blocks up to 10 seconds)
messages = client.recv(wait=10)
for msg in messages:
    print(f"{msg['sender']}: {msg['body']}")

# Broadcast
client.send("all", "Hello everyone!")

# Mark yourself done
client.set_status("done")
```

## API Reference

### Initialization

```python
client = A2AClient(project: str, agent_id: str)
```

**Parameters:**
- `project`: Project name (also respects `$A2A_PROJECT` environment variable)
- `agent_id`: This agent's unique ID

**Note:** The database is expected to exist at `~/.a2a/{project}/database.db`.

### register()

```python
success = client.register(
    role: str,
    prompt: str = "",
    cli: str = "",
    pid: int | None = None,
    upsert: bool = True
) -> bool
```

Register this agent on the bus. Must be called before send/recv.

**Parameters:**
- `role`: Agent's role description (e.g., "developer", "critic")
- `prompt`: Optional system prompt sent to peer agents
- `cli`: CLI tool name (e.g., "claude", "opencode")
- `pid`: Process ID (optional)
- `upsert`: Update existing registration if True (default: True, preserves original created_at)

**Returns:** True on success

**Example:**
```python
client.register("researcher", cli="python", upsert=True)
```

### unregister()

```python
success = client.unregister() -> bool
```

Remove this agent from the bus.

**Returns:** True on success

**Example:**
```python
client.unregister()
```

### send()

```python
msg_id = client.send(
    to: str,
    message: str,
    ttl_seconds: Optional[int] = None,
    thread_id: Optional[str] = None
) -> int
```

Send a message to a peer.

**Parameters:**
- `to`: Recipient agent ID, or `"all"` / `"*"` / `"broadcast"` for broadcast
- `message`: Message body (plain text)
- `ttl_seconds`: Optional time-to-live in seconds. Messages expire after this duration.
- `thread_id`: Optional thread/topic ID to group related messages

**Returns:** Message ID (integer)

**Example:**
```python
# Direct message
msg_id = client.send("bob", "Are you there?")

# Broadcast
client.send("all", "Team standup in 5 minutes")

# Message with expiry
client.send("bob", "Urgent task", ttl_seconds=3600)  # Expires in 1 hour
```

### recv()

```python
messages = client.recv(
    wait: float = 0,
    unread_only: bool = True,
    include_self: bool = False,
    limit: int = 0
) -> List[Dict[str, Any]]
```

Receive messages addressed to this agent.

**Parameters:**
- `wait`: Block up to N seconds waiting for messages (0 = don't block)
- `unread_only`: Only return messages not yet read by this agent (default: True)
- `include_self`: Include messages sent by this agent (default: False)
- `limit`: Max messages to return (0 = unlimited)

**Returns:** List of message dicts with keys:
- `id`: Message ID
- `sender`: Sender agent ID
- `recipient`: Recipient agent ID (None for broadcast)
- `body`: Message text
- `thread_id`: Optional thread/topic ID
- `created_at`: Timestamp

**Example:**
```python
# Wait for next unread message (up to 30s)
messages = client.recv(wait=30)

# Get all messages including already-read
messages = client.recv(unread_only=False, limit=50)

# Include messages I sent myself
messages = client.recv(wait=10, include_self=True)
```

### peek()

```python
messages = client.peek(limit: int = 20) -> List[Dict[str, Any]]
```

View recent messages without marking them as read (observer mode).

**Parameters:**
- `limit`: Max messages to return (default: 20)

**Returns:** List of message dicts (same format as `recv()`)

**Example:**
```python
# See last 50 messages
recent = client.peek(limit=50)
for msg in recent:
    print(f"[{msg['created_at']}] {msg['sender']} -> {msg['recipient'] or 'ALL'}")
```

### list_peers()

```python
peers = client.list_peers() -> List[Dict[str, Any]]
```

Get roster of registered agents.

**Returns:** List of peer dicts with keys:
- `id`: Agent ID
- `role`: Agent role (optional)
- `cli`: CLI used (claude/opencode/pi/python/etc)
- `status`: Agent status (active/idle/done/blocked)
- `pid`: Process ID (if available)

**Example:**
```python
peers = client.list_peers()
active = [p for p in peers if p['status'] == 'active']
print(f"Active agents: {[p['id'] for p in active]}")
```

### set_status()

```python
client.set_status(status: str) -> None
```

Update this agent's status to signal state to peers.

**Parameters:**
- `status`: One of `'active'`, `'idle'`, `'done'`, `'blocked'`

**Example:**
```python
# Signal that work is done
client.set_status("done")

# Signal that waiting for something
client.set_status("blocked")

# Resume activity
client.set_status("active")
```

### get_status()

```python
status = client.get_status(agent_id: Optional[str] = None) -> Optional[str]
```

Check an agent's status.

**Parameters:**
- `agent_id`: Agent to check (defaults to self.agent_id if omitted)

**Returns:** Status string or None if agent not found

**Example:**
```python
# Check self
my_status = client.get_status()

# Check peer
bob_status = client.get_status("bob")
```

### wait_for_messages()

```python
success = client.wait_for_messages(
    count: int = 1,
    timeout: float = 60
) -> bool
```

Block until N unread messages arrive or timeout.

**Parameters:**
- `count`: Number of unread messages to wait for
- `timeout`: Max seconds to wait

**Returns:** True if got N messages, False on timeout

**Example:**
```python
# Wait for 3 responses before proceeding
if client.wait_for_messages(count=3, timeout=30):
    responses = client.recv()
else:
    print("Timeout: only got", len(client.recv()), "responses")
```

### search()

```python
messages = client.search(
    query: str,
    limit: int = 50
) -> List[Dict[str, Any]]
```

Search all messages by content substring (case-insensitive).

**Parameters:**
- `query`: Search substring (case-insensitive)
- `limit`: Max messages to return (must be positive)

**Raises:**
- `ValueError`: If query is empty or limit is not a positive integer

**Returns:** List of matching message dicts (sorted by creation time, newest first)

**Example:**
```python
# Find all messages about a bug
bugs = client.search("bug", limit=100)
for msg in bugs:
    print(f"{msg['sender']}: {msg['body']}")

# Search for task assignments
tasks = client.search("assign", limit=50)
```

### thread()

```python
messages = client.thread(thread_id: str) -> List[Dict[str, Any]]
```

Get all messages in a specific thread.

**Parameters:**
- `thread_id`: Thread ID (must match a message's `thread_id` field)

**Returns:** List of message dicts in thread, ordered chronologically

**Example:**
```python
# Get all messages in a thread
thread_messages = client.thread("my-thread-id")
print(f"Thread has {len(thread_messages)} messages:")
for msg in thread_messages:
    print(f"  {msg['sender']}: {msg['body']}")
```

### stats()

```python
stats = client.stats() -> Dict[str, Any]
```

Get aggregated bus statistics.

**Returns:** Dict with keys:
- `messages`: Total message count
- `direct_messages`: Direct (non-broadcast) message count
- `broadcasts`: Broadcast message count
- `threads`: Number of distinct threads
- `agents_active`: Count of agents with status='active'
- `agents_done`: Count of agents with status='done'
- `top_senders`: List of top 5 senders (dicts with `agent` and `count`)

**Example:**
```python
stats = client.stats()
print(f"Bus stats:")
print(f"  Messages: {stats['messages']} ({stats['direct_messages']} direct, {stats['broadcasts']} broadcast)")
print(f"  Threads: {stats['threads']}")
print(f"  Agents: {stats['agents_active']} active, {stats['agents_done']} done")
print(f"  Top senders: {stats['top_senders']}")
```

## Complete Example: Researcher Agent

```python
from a2a_client import A2AClient
import time

def main():
    # Initialize
    client = A2AClient(project="my-project", agent_id="researcher")
    
    # List peers
    peers = [p['id'] for p in client.list_peers() if p['id'] != "researcher"]
    print(f"Found peers: {peers}")
    
    # Broadcast question
    client.send("all", "What are the top 3 features you'd prioritize?")
    
    # Wait for responses
    print("Waiting for 3 responses...")
    if not client.wait_for_messages(count=3, timeout=30):
        print("Timeout!")
    
    # Collect responses
    responses = client.recv(unread_only=True)
    for msg in responses:
        print(f"  {msg['sender']}: {msg['body']}")
    
    # Summarize findings
    summary = f"Received {len(responses)} responses on feature prioritization."
    client.send("all", f"Summary: {summary}")
    
    # Mark done
    client.set_status("done")
    print("Done!")

if __name__ == "__main__":
    main()
```

## Error Handling

The client raises exceptions for common errors:

```python
from a2a_client import A2AClient

try:
    client = A2AClient("nonexistent-project", "alice")
    client.send("bob", "Hello")
except Exception as e:
    print(f"Error: {e}")
```

Common errors:
- **ValueError**: Empty project or agent_id in constructor
- **sqlite3.OperationalError**: Database schema issue (call `client.register()` or `a2a init` first)
- **sqlite3.IntegrityError**: Agent not registered (call `client.register()` first)

## Performance

The client uses direct SQLite connections:
- **send()**: ~5ms per message
- **recv()**: ~10ms per poll (when `wait > 0`)
- **peek()**: ~5ms per query
- **list_peers()**: ~5ms

No subprocess overhead (unlike the CLI), making it suitable for high-frequency messaging.

## Integration with CLI

The Python client can coexist with CLI agents:

```bash
# Start CLI agent in background
python3 examples/researcher_agent.py &

# Use Python client to send messages
python3 << 'EOF'
from a2a_client import A2AClient
client = A2AClient("my-project", "python-agent")
client.send("researcher", "Please investigate X")
responses = client.recv(wait=30)
EOF
```

## Testing

Unit tests are in `test_a2a_client.py`:

```bash
python3 test_a2a_client.py -v
```

Covers all methods with fresh databases, concurrent access, read-tracking, TTL, etc.

## See Also

- [README.md](../README.md) — Project overview
- [examples/](../examples/) — Agent pattern implementations
- [SKILL.md](SKILL.md) — Full a2a architecture
