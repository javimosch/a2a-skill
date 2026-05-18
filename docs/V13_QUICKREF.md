# a2a v1.3 Quick Reference

Essential code snippets for all v1.3 features. Full docs in ENCRYPTION.md, FTS_SEARCH.md, AUDIT.md, PRIORITY.md, ROUTING.md.

## Encryption

### Symmetric (Shared Key)
```python
from a2a_crypto import CryptoClient

crypto = CryptoClient("myproject", "alice")

# Generate shared key
key = crypto.generate_symmetric_key()

# Encrypt/Decrypt
encrypted = crypto.encrypt_message("Secret", key)
decrypted = crypto.decrypt_message(encrypted, key)
```

### Asymmetric (Public/Private Keys)
```python
# Generate keypair
public_key, private_key = crypto.generate_keypair()

# Bob encrypts to Alice using her public key
encrypted = crypto.encrypt_with_public_key("Secret", alice_public_key)

# Alice decrypts
decrypted = crypto.decrypt_with_private_key(encrypted)
```

### Message Wrapping
```python
# Transparent encryption
wrapped = crypto.wrap_encrypted_message("Confidential", bob_public_key)
a2a.send("bob", wrapped)

# Unwrap & decrypt
decrypted = CryptoClient.unwrap_encrypted_message(msg["body"], crypto)
```

## Full-Text Search

```python
from a2a_fts import FTSClient, SearchQueryBuilder

fts = FTSClient("myproject", "alice")
fts.init_fts_table()

# Simple search
results = fts.search_fts("error")

# Phrase search
results = fts.search_fts('"authentication failed"')

# Boolean queries
results = fts.search_fts("(database OR sql) AND error")

# Prefix matching
results = fts.search_fts("auth*")

# Advanced with filters
results = fts.search_advanced(
    query="bug",
    sender="alice",
    thread_id="42",
    limit=20
)

# Query builder
query = (SearchQueryBuilder()
    .add_term("error")
    .must_contain("critical")
    .must_not_contain("resolved")
    .build())
results = fts.search_fts(query)
```

## Audit Logging

```python
from a2a_audit import AuditClient, AuditContextManager

audit = AuditClient("myproject")
audit.init_audit_table()

# Log operation
audit.log_operation(
    agent_id="alice",
    operation="send",
    message_id=42,
    details={"recipient": "bob"},
    result="success"
)

# Automatic logging with context manager
with AuditContextManager(audit, "alice", "send") as ctx:
    ctx.message_id = 42
    ctx.details = {"recipient": "bob"}
    # Logs automatically on exit

# Query audit trail
trail = audit.get_agent_audit_trail("alice", days=7)
lifecycle = audit.get_message_audit_trail(42)
results = audit.search_audit_logs(
    operation="send",
    agent_id="alice",
    result="success"
)

# Statistics
stats = audit.get_audit_stats(days=7)
# Stats: total_operations, operations_by_type, operations_by_agent, result_summary

# Export for analysis
audit.export_audit_log("audit_export.json")

# Cleanup old logs
deleted = audit.cleanup_old_logs(days=90)
```

## Message Prioritization

```python
from a2a_priority import PriorityClient, Priority, PriorityQueue

priority = PriorityClient("myproject", "alice")
priority.init_priority_table()

# Send with priority
priority.send("bob", "System outage!", priority=Priority.CRITICAL)
priority.send("bob", "Upgrade needed", priority=Priority.HIGH)
priority.send("bob", "Regular message")  # Defaults to NORMAL

# Receive ordered by priority
messages = priority.recv(wait=5)  # Ordered: CRITICAL, HIGH, NORMAL, LOW

# Receive without priority ordering
messages = priority.recv(priority_aware=False)

# Filter by priority
criticals = priority.recv_by_priority(Priority.CRITICAL)
urgent = priority.recv_above_priority(Priority.HIGH)

# Convenience methods
criticals = priority.get_critical_messages()
highs = priority.get_high_priority_messages()

# Statistics
stats = priority.get_priority_stats()
alice_stats = priority.get_priority_stats_by_agent("alice")

# Mark as read
priority.mark_read(message_id)

# Priority Queue helper
queue = PriorityQueue(priority, "alice")
messages = queue.poll(wait=1, limit=5)
```

## Message Routing

```python
from a2a_routing import (
    RoutingClient,
    RoutingRule,
    RoutingAction,
    SmartRouter
)

routing = RoutingClient("myproject", "alice")
routing.init_routing_table()

# Create routing rules
rule1 = RoutingRule(
    name="escalate_critical",
    action=RoutingAction.ESCALATE,
    match_priority=4  # CRITICAL
)

rule2 = RoutingRule(
    name="database_forward",
    action=RoutingAction.FORWARD,
    match_content="database|sql",
    forward_to="database_team"
)

rule3 = RoutingRule(
    name="spam_discard",
    action=RoutingAction.DISCARD,
    match_content="spam|junk"
)

# Add rules
routing.add_rule(rule1)
routing.add_rule(rule2)
routing.add_rule(rule3)

# Receive with routing (groups by action)
routed = routing.recv_with_routing(wait=5)
# routed = {
#   'deliver': [...],    # No rule matched
#   'forward': [...],    # Match forward rules
#   'discard': [...],    # Match discard rules
#   'queue': [...],      # Match queue rules
#   'escalate': [...]    # Match escalate rules
# }

# Apply routing (execute forwards, discards)
routing.apply_routing(routed)

# Rule management
rules = routing.get_rules()
routing.disable_rule("spam_discard")
routing.enable_rule("spam_discard")
routing.delete_rule("spam_discard")

# Statistics
stats = routing.get_routing_stats()
# stats: {total_rules, enabled_rules, disabled_rules, by_action}

# Smart routing with custom matchers
router = SmartRouter(routing)

def is_urgent(msg):
    return msg.get("priority", 2) >= 3

def handle_urgent(msg):
    print(f"URGENT: {msg['body']}")

router.add_custom_matcher(is_urgent, handle_urgent)
router.route_message(message)
```

## Async Versions (High Concurrency)

```python
import asyncio
from a2a_priority_async import PriorityClientAsync
from a2a_routing_async import RoutingClientAsync

async def main():
    # Async priority client
    priority = PriorityClientAsync("myproject", "alice")
    await priority.init_priority_table()
    
    msg_id = await priority.send("bob", "Urgent", priority=4)
    messages = await priority.recv(wait=5)
    stats = await priority.get_priority_stats()
    
    # Async routing client
    routing = RoutingClientAsync("myproject", "alice")
    await routing.init_routing_table()
    
    routed = await routing.recv_with_routing(wait=5)
    await routing.apply_routing(routed)
    
    # Run multiple agents concurrently
    results = await asyncio.gather(
        priority.recv(wait=5),
        routing.recv_with_routing(wait=5)
    )

asyncio.run(main())
```

## Common Patterns

### Alert Routing to Oncall
```python
routing.add_rule(RoutingRule(
    name="critical_oncall",
    action=RoutingAction.FORWARD,
    match_priority=Priority.CRITICAL,
    forward_to="oncall"
))

# Also log the escalation
audit.log_operation(
    agent_id="dispatcher",
    operation="escalate",
    message_id=msg["id"],
    details={"target": "oncall"}
)
```

### Encrypted Priority Messaging
```python
# Encrypt message
encrypted = crypto.wrap_encrypted_message(secret, recipient_public_key)

# Send with priority
msg_id = priority.send("bob", encrypted, priority=Priority.HIGH)

# Recipient decrypts
decrypted = crypto.unwrap_encrypted_message(msg["body"], crypto)

# Audit the full lifecycle
audit.log_operation("alice", "encrypt", msg_id, result="success")
audit.log_operation("bob", "recv", msg_id)
audit.log_operation("bob", "decrypt", msg_id, result="success")
```

### Search with Audit
```python
# Search for errors
results = fts.search_fts("error", limit=100)

# Log the search
audit.log_operation(
    agent_id="alice",
    operation="search",
    details={"query": "error", "results": len(results)}
)

# Export results
export_data = {
    "query": "error",
    "timestamp": time.time(),
    "results": results
}
json.dump(export_data, open("error_search_export.json", "w"))
```

### Priority-Based Routing
```python
routing.add_rule(RoutingRule(
    name="high_priority_queue",
    action=RoutingAction.QUEUE,
    match_priority=Priority.HIGH
))

routed = routing.recv_with_routing()

# Process high-priority in dedicated queue
for item in routed["queue"]:
    msg = item["message"]
    if msg["priority"] == Priority.CRITICAL:
        priority_queue.put(msg, priority=0)
    else:
        priority_queue.put(msg, priority=1)
```

## Testing v1.3

```bash
# Run comprehensive v1.3 test suite
python3 test_v13_features.py

# Run specific test class
python3 -m unittest test_v13_features.TestEncryption
python3 -m unittest test_v13_features.TestMessagePriority
python3 -m unittest test_v13_features.TestMessageRouting
```

## Performance Tips

- **Encryption**: RSA keypair generation takes 100-500ms; do once at startup
- **FTS Search**: Rebuild index after bulk operations with `rebuild_fts_index()`
- **Async**: Use `PriorityClientAsync` and `RoutingClientAsync` for 10x+ throughput
- **Routing**: Simple substring match faster than regex; put patterns in order of specificity
- **Audit**: Cleanup old logs regularly to keep database size manageable

## See Also

- [ENCRYPTION.md](docs/ENCRYPTION.md) — Full encryption guide
- [FTS_SEARCH.md](docs/FTS_SEARCH.md) — Search API reference
- [AUDIT.md](docs/AUDIT.md) — Audit logging details
- [PRIORITY.md](docs/PRIORITY.md) — Priority queue patterns
- [ROUTING.md](docs/ROUTING.md) — Routing rules and examples
- [test_v13_features.py](test_v13_features.py) — Comprehensive test suite
