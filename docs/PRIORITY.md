# a2a Message Prioritization (v1.3)

Priority-aware message queuing and smart delivery based on importance levels.

## Overview

Message prioritization enables:
- **Four priority levels** — CRITICAL, HIGH, NORMAL, LOW
- **Automatic queue ordering** — Receive high-priority messages first
- **Priority filtering** — Query messages by priority threshold
- **Statistics tracking** — Analyze priority distribution by agent
- **Backward compatibility** — Works with existing A2AClient databases

## Quick Start

### Initialize Priority Support

```python
from a2a_priority import PriorityClient, Priority

# Create priority-aware client
client = PriorityClient("my-project", "alice")

# Initialize priority column (adds to existing table)
client.init_priority_table()
```

### Send with Priority

```python
# Send critical message
client.send("bob", "System outage!", priority=Priority.CRITICAL)

# Send high-priority alert
client.send("all", "Upgrade required", priority=Priority.HIGH)

# Send normal message (default)
client.send("bob", "Meeting at 3pm")

# Send low-priority info
client.send("team", "FYI: new docs posted", priority=Priority.LOW)
```

### Receive with Priority Ordering

```python
# Default: priority ordering (highest first)
messages = client.recv(wait=5)
for msg in messages:
    priority = msg.get("priority", 2)
    print(f"[{priority}] {msg['sender']}: {msg['body']}")

# Receive without priority ordering
messages = client.recv(priority_aware=False)
```

### Filter by Priority

```python
# Get only critical messages
criticals = client.get_critical_messages()

# Get high and critical messages
high_plus = client.get_high_priority_messages()

# Get messages of exact priority
highs = client.recv_by_priority(Priority.HIGH)

# Get messages above threshold
urgent = client.recv_above_priority(Priority.HIGH)
```

### Priority Statistics

```python
# Get distribution across all messages
stats = client.get_priority_stats()
print(f"Critical: {stats.get('CRITICAL', 0)}")
print(f"High: {stats.get('HIGH', 0)}")
print(f"Normal: {stats.get('NORMAL', 0)}")
print(f"Low: {stats.get('LOW', 0)}")

# Get distribution for specific agent
alice_stats = client.get_priority_stats_by_agent("alice")
```

## Priority Levels

### Levels and Values

```python
Priority.CRITICAL = 4  # System-critical, immediate action required
Priority.HIGH = 3      # Important, should be handled soon
Priority.NORMAL = 2    # Regular messages (default)
Priority.LOW = 1       # Informational, can wait
```

### Use Cases

**CRITICAL (4)**
- System failures
- Security breaches
- Data corruption
- Immediate outages
- Emergency alerts

**HIGH (3)**
- Urgent requests
- Time-sensitive tasks
- Important updates
- Escalations
- SLA violations

**NORMAL (2)**
- Regular messages
- Standard communications
- Task assignments
- Default for all sends

**LOW (1)**
- FYI announcements
- Informational updates
- Non-urgent info
- Background notices
- Archival data

## API Reference

### PriorityClient

```python
class PriorityClient(A2AClient):
    # Initialization & setup
    def __init__(self, project: str, agent_id: str)
    def init_priority_table(self) -> bool

    # Sending with priority
    def send(
        to: str,
        message: str,
        priority: int = Priority.NORMAL,
        ttl_seconds: Optional[int] = None
    ) -> int

    # Receiving with priority
    def recv(
        wait: float = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: int = 0,
        priority_aware: bool = True
    ) -> List[Dict[str, Any]]

    def recv_by_priority(
        priority: int,
        wait: float = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: int = 0
    ) -> List[Dict[str, Any]]

    def recv_above_priority(
        min_priority: int,
        wait: float = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: int = 0
    ) -> List[Dict[str, Any]]

    # Convenience methods
    def get_critical_messages(
        unread_only: bool = True,
        include_self: bool = False
    ) -> List[Dict[str, Any]]

    def get_high_priority_messages(
        unread_only: bool = True,
        include_self: bool = False
    ) -> List[Dict[str, Any]]

    # Statistics
    def get_priority_stats(self) -> Dict[str, Any]
    def get_priority_stats_by_agent(agent_id: str) -> Dict[str, Any]

    # Message management
    def mark_read(message_id: int) -> bool
```

### Priority Enum

```python
class Priority(IntEnum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def from_string(value: str) -> Priority
```

### PriorityQueue Helper

```python
class PriorityQueue:
    def __init__(self, client: PriorityClient, agent_id: str)
    def poll(wait: float = 0, limit: int = 0) -> List[Dict]
    def peek_critical(limit: int = 10) -> List[Dict]
```

## Integration with A2AClient

```python
from a2a_priority import PriorityClient, Priority
from a2a_client_async import A2AClientAsync

async def priority_messaging():
    # Use PriorityClient for priority awareness
    priority_client = PriorityClient("myproject", "alice")
    priority_client.init_priority_table()
    
    # Send critical alert
    priority_client.send(
        "bob",
        "Database failure detected",
        priority=Priority.CRITICAL
    )
    
    # Receive messages ordered by priority
    messages = priority_client.recv(wait=5)
    
    # Process critical messages first
    for msg in messages:
        if msg['priority'] >= Priority.HIGH:
            print(f"URGENT: {msg['body']}")
            priority_client.mark_read(msg['id'])
```

## Database Schema

### Messages Table Extension

The priority column is added to existing messages table:

```sql
ALTER TABLE messages ADD COLUMN priority INTEGER DEFAULT 2;
CREATE INDEX idx_messages_priority ON messages(priority);
```

### Default Values

- **New messages**: Default to `Priority.NORMAL` (2) if not specified
- **Existing messages**: Set to `Priority.NORMAL` (2) via migration
- **NULL values**: Treated as NORMAL (2) in queries

## Ordering Semantics

### Priority Ordering

When `priority_aware=True`, messages are ordered:
1. **By priority** — DESC (highest first: 4, 3, 2, 1)
2. **By timestamp** — ASC (oldest within priority first)

This ensures:
- Critical messages appear before high-priority
- High-priority appears before normal
- Older messages within same priority appear first (FIFO fairness)

### Example Ordering

```
Message 1: priority=4, created_at=1000  ← first (critical, oldest)
Message 2: priority=4, created_at=1100  ← second (critical, newer)
Message 3: priority=3, created_at=900   ← third (high priority)
Message 4: priority=2, created_at=1200  ← fourth (normal)
Message 5: priority=1, created_at=800   ← fifth (low priority)
```

## Common Patterns

### Alert Handler

```python
def alert_handler(client: PriorityClient):
    while True:
        # Check critical messages every 10 seconds
        criticals = client.get_critical_messages()
        for alert in criticals:
            handle_alert(alert)
            client.mark_read(alert['id'])
        
        # Check high-priority every minute
        highs = client.get_high_priority_messages()
        for msg in highs[:10]:  # Process top 10
            handle_important(msg)
            client.mark_read(msg['id'])
        
        time.sleep(10)
```

### Task Queue with Priority

```python
def task_worker(client: PriorityClient):
    queue = PriorityQueue(client, client.agent_id)
    
    while True:
        # Get up to 5 high-priority messages
        tasks = queue.poll(wait=1, limit=5)
        
        for task in tasks:
            if task['priority'] == Priority.CRITICAL:
                execute_task(task, retry_count=3)
            else:
                execute_task(task, retry_count=1)
```

### Priority-Based Routing

```python
def route_by_priority(client: PriorityClient, message):
    """Route message to appropriate handler."""
    
    if message['priority'] == Priority.CRITICAL:
        # Escalate immediately
        escalate(message)
    elif message['priority'] == Priority.HIGH:
        # Fast track processing
        priority_queue.put(message, priority=True)
    else:
        # Regular processing
        normal_queue.put(message)
```

### Mixed Priority Communication

```python
async def manager_agent():
    client = PriorityClient("org", "manager")
    client.init_priority_table()
    
    # Send status update (normal)
    client.send("team", "Weekly standup at 2pm")
    
    # Send escalation (high)
    if system_issue_detected():
        client.send("oncall", "System degraded", priority=Priority.HIGH)
    
    # Send critical alert (critical)
    if critical_error():
        client.send(
            "all",
            "Critical: Data replication failed",
            priority=Priority.CRITICAL
        )
```

## Performance

- **Send with priority**: < 1ms (same as regular send)
- **Priority-aware recv**: 10-30ms (priority ordering adds ~5-10ms)
- **Filter by priority**: 5-20ms
- **Statistics**: 10-50ms
- **Index lookup**: O(log n) on priority column

## Migration from A2AClient

```python
# Existing code using A2AClient
client = A2AClient("myproject", "alice")
messages = client.recv()

# Migrate to PriorityClient
priority_client = PriorityClient("myproject", "alice")
priority_client.init_priority_table()  # One-time setup

# Use priority-aware operations
messages = priority_client.recv(priority_aware=True)

# Old send() calls still work (default to NORMAL priority)
priority_client.send("bob", "Hello")  # priority=2
```

## Best Practices

1. **Initialize once**: Call `init_priority_table()` at startup
2. **Use Priority enum**: Avoid magic numbers; use `Priority.CRITICAL` not `4`
3. **Set priority appropriately**: Don't mark everything as critical
4. **Monitor distribution**: Use `get_priority_stats()` to detect priority inflation
5. **Filter not sort**: Use `recv_above_priority()` for thresholds, not post-filtering
6. **Handle all levels**: Don't ignore low-priority messages indefinitely
7. **TTL with priority**: Consider shorter TTL for high-priority to ensure delivery

## Limitations

1. **No priority modification**: Priority set at send time, cannot be changed
2. **No sub-priorities**: Only 4 levels; no fine-grained sorting within level
3. **No priority guarantees**: High-priority doesn't bypass processing limits
4. **No priority inheritance**: Replies don't inherit sender's priority

## See Also

- [README.md](../README.md) — Project overview
- [CLIENT_API.md](CLIENT_API.md) — Base client reference
- [AUDIT.md](AUDIT.md) — Audit logging for compliance
- [FTS_SEARCH.md](FTS_SEARCH.md) — Full-text search
- [CHANGELOG.md](CHANGELOG.md) — Release history and roadmap
