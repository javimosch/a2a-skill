# a2a Audit Logging (v1.3)

Comprehensive message lifecycle tracking for compliance and debugging.

## Overview

Audit logging enables:
- **Complete lifecycle tracking** — Track all message operations: created, sent, received, read, encrypted, decrypted
- **Compliance reporting** — Export audit logs for regulatory requirements
- **Debugging support** — Trace message flow and identify issues
- **Performance analysis** — Statistics on operation types and agent activity
- **Selective retention** — Delete old logs while keeping recent history

## Quick Start

### Initialize Audit Logging

```python
from a2a_audit import AuditClient

audit = AuditClient("my-project")

# Initialize audit table (one-time setup)
audit.init_audit_table()
```

### Log Operations

```python
# Log a send operation
audit.log_operation(
    agent_id="alice",
    operation="send",
    message_id=42,
    details={"recipient": "bob", "size_bytes": 256},
    result="success"
)

# Log a failure
audit.log_operation(
    agent_id="bob",
    operation="decrypt",
    message_id=42,
    details={"algorithm": "RSA-2048"},
    result="failure"
)
```

### Query Audit Logs

```python
# Get all operations by an agent in last 7 days
trail = audit.get_agent_audit_trail("alice", limit=100, days=7)
for entry in trail:
    print(f"{entry['timestamp']}: {entry['operation']} — {entry['result']}")

# Get complete lifecycle of a message
lifecycle = audit.get_message_audit_trail(42)
for entry in lifecycle:
    print(f"{entry['agent_id']}: {entry['operation']} at {entry['timestamp']}")
```

### Advanced Search

```python
# Search with filters
results = audit.search_audit_logs(
    operation="send",
    agent_id="alice",
    result="success",
    start_time=1715000000.0,
    end_time=1715100000.0,
    limit=50
)

# Get statistics
stats = audit.get_audit_stats(days=7)
print(f"Total operations: {stats['total_operations']}")
print(f"By type: {stats['operations_by_type']}")
print(f"By agent: {stats['operations_by_agent']}")
print(f"Results: {stats['result_summary']}")
```

### Export for Analysis

```python
# Export all logs
audit.export_audit_log("audit_export.json")

# Export time range
audit.export_audit_log(
    "audit_export.json",
    start_time=1715000000.0,
    end_time=1715100000.0
)
```

### Automatic Logging with Context Manager

```python
from a2a_audit import AuditContextManager

with AuditContextManager(audit, "alice", "send") as ctx:
    ctx.message_id = 42
    ctx.details = {"recipient": "bob"}
    # Operation logged automatically on exit with success or failure
    result = send_message("bob", "Hello")
```

## API Reference

### AuditClient

```python
class AuditClient:
    # Initialization
    def __init__(self, project: str)
    def init_audit_table(self) -> bool

    # Logging
    def log_operation(
        agent_id: str,
        operation: str,
        message_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        result: str = "success"
    ) -> bool

    # Query methods
    def get_agent_audit_trail(
        agent_id: str,
        limit: int = 100,
        days: int = 7
    ) -> List[Dict[str, Any]]

    def get_message_audit_trail(
        message_id: int
    ) -> List[Dict[str, Any]]

    def search_audit_logs(
        operation: Optional[str] = None,
        agent_id: Optional[str] = None,
        result: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]

    # Analytics
    def get_audit_stats(days: int = 7) -> Dict[str, Any]

    # Export & maintenance
    def export_audit_log(
        filepath: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> bool

    def cleanup_old_logs(days: int = 90) -> int
```

### AuditContextManager

```python
class AuditContextManager:
    def __init__(
        self,
        audit_client: AuditClient,
        agent_id: str,
        operation: str
    )
    
    # Set these before exiting context
    message_id: Optional[int]
    details: Dict[str, Any]
    
    # Automatically logs operation on exit with success/failure
```

## Audit Log Schema

### Columns

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PRIMARY KEY | Unique log entry ID |
| timestamp | REAL | Unix timestamp (seconds) |
| agent_id | TEXT | Agent performing operation |
| operation | TEXT | Operation type (send, recv, read, encrypt, etc.) |
| message_id | INTEGER | Associated message ID (nullable) |
| details | TEXT | JSON with extra details |
| result | TEXT | "success" or "failure" |
| created_at | TIMESTAMP | Database creation timestamp |

### Indexes

- `idx_audit_agent` on agent_id
- `idx_audit_operation` on operation
- `idx_audit_message` on message_id
- `idx_audit_timestamp` on timestamp

## Integration with A2AClient

```python
from a2a_client_async import A2AClientAsync
from a2a_audit import AuditClient, AuditContextManager

async def secure_send():
    audit = AuditClient("myproject")
    audit.init_audit_table()
    
    async with A2AClientAsync("myproject", "alice") as a2a:
        with AuditContextManager(audit, "alice", "send") as ctx:
            ctx.details = {"recipient": "bob"}
            msg = await a2a.send("bob", "Secret message")
            ctx.message_id = msg.get("id")
```

## Common Operations

### Operation Types

```
send      — Message sent
recv      — Message received
read      — Message marked as read
peek      — Message peeked (not marked as read)
encrypt   — Encryption operation
decrypt   — Decryption operation
search    — Full-text search
thread    — Thread operations
sync      — Database sync
list      — List operations
```

### Result Values

```
success   — Operation completed successfully
failure   — Operation failed with error
```

## Use Cases

### Compliance Reporting

```python
# Export month's logs for audit
start = datetime(2026, 5, 1).timestamp()
end = datetime(2026, 5, 31).timestamp()
audit.export_audit_log("may_2026_audit.json", start, end)
```

### Security Investigation

```python
# Find all decrypt operations by agent
decrypts = audit.search_audit_logs(
    operation="decrypt",
    agent_id="alice"
)

# Find failures
failures = audit.search_audit_logs(
    result="failure",
    days=1
)
```

### Performance Monitoring

```python
# Get operation statistics
stats = audit.get_audit_stats(days=7)
total_ops = stats['total_operations']
by_type = stats['operations_by_type']

print(f"Total ops in 7 days: {total_ops}")
print(f"Most common: {max(by_type, key=by_type.get)}")
```

### Agent Activity Tracking

```python
# Which agents are most active?
stats = audit.get_audit_stats(days=7)
by_agent = stats['operations_by_agent']

for agent, count in sorted(by_agent.items(), key=lambda x: x[1], reverse=True):
    print(f"{agent}: {count} operations")
```

### Message Lifecycle Tracing

```python
# Trace a message through entire system
lifecycle = audit.get_message_audit_trail(42)

for entry in lifecycle:
    agent = entry['agent_id']
    op = entry['operation']
    result = entry['result']
    print(f"{agent} {op} → {result}")
    if entry['details']:
        print(f"  Details: {entry['details']}")
```

## Cleanup and Maintenance

### Delete Old Logs

```python
# Delete logs older than 90 days
deleted = audit.cleanup_old_logs(days=90)
print(f"Deleted {deleted} entries")
```

### Scheduled Cleanup

```python
# Run daily cleanup (example with APScheduler)
from apscheduler.schedulers.background import BackgroundScheduler

def cleanup_job():
    audit = AuditClient("myproject")
    deleted = audit.cleanup_old_logs(days=90)
    print(f"Cleanup: {deleted} entries deleted")

scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_job, 'cron', hour=2, minute=0)  # Daily at 2am
scheduler.start()
```

## Performance

- **Index creation**: < 10ms
- **Log insertion**: < 1ms per operation
- **Query time**: 5-20ms for typical queries
- **Search with filters**: 10-50ms
- **Statistics**: 20-100ms
- **Export 10K entries**: 100-500ms

## Best Practices

1. **Initialize once**: Call `init_audit_table()` at startup
2. **Use context managers**: Automatic logging with exception capture
3. **Set message_id when known**: Enables complete lifecycle tracing
4. **Include details**: Helps with debugging and compliance
5. **Regular cleanup**: Delete old logs quarterly or semi-annually
6. **Export periodically**: Backup logs for long-term compliance
7. **Monitor result ratios**: Track success/failure rates
8. **Aggregate by agent**: Identify problematic agents

## Troubleshooting

### "database locked" error

```python
# Increase timeout in _connect()
# Already set to 10.0 seconds by default
# If still failing, reduce concurrent writes
```

### Missing audit entries

```python
# Verify initialization
audit.init_audit_table()

# Check stats
stats = audit.get_audit_stats()
if stats.get('index_status') == 'needs_rebuild':
    # Manual rebuild not available - recreate table
    pass
```

### Large database file

```python
# Run cleanup more frequently
deleted = audit.cleanup_old_logs(days=30)

# Or export and rotate
audit.export_audit_log("archive.json", end_time=cutoff)
audit.cleanup_old_logs(days=1)
```

## Limitations

1. **No real-time alerts**: Logs are written synchronously but queries are point-in-time
2. **No distributed tracing**: Audit logs are per-project; no cross-project tracing
3. **Local storage only**: Logs stored in SQLite; consider exporting for central aggregation
4. **No compression**: JSON details stored as-is; large details can use disk space

## See Also

- [README.md](../README.md) — Project overview
- [CLIENT_API.md](docs/CLIENT_API.md) — Python client reference
- [ENCRYPTION.md](docs/ENCRYPTION.md) — End-to-end encryption
- [FTS_SEARCH.md](docs/FTS_SEARCH.md) — Full-text search
- [PROJECT_STATUS.md](docs/PROJECT_STATUS.md) — v1.3 roadmap
