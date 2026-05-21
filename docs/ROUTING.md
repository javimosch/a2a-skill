# a2a Message Routing (v1.3)

Smart message distribution with rule-based filtering and forwarding.

## Overview

Message routing enables:
- **Rule-based filtering** — Automatically route messages by sender, content, priority, thread
- **Pattern matching** — Substring and regex pattern support for flexible matching
- **Multiple actions** — Deliver, forward, discard, queue, or escalate
- **Persistence** — Rules stored in database for multi-session consistency
- **Advanced routing** — SmartRouter for custom matchers and conditional logic
- **Statistics** — Track routing rule distribution and status

## Quick Start

### Initialize Routing

```python
from a2a_routing import RoutingClient, RoutingRule, RoutingAction

client = RoutingClient("my-project", "alice")

# Initialize routing rules table
client.init_routing_table()
```

### Create Routing Rules

```python
# Route alerts from monitoring system
alert_rule = RoutingRule(
    name="route_alerts",
    action=RoutingAction.FORWARD,
    match_sender="monitoring",
    forward_to="oncall"
)
client.add_rule(alert_rule)

# Route high-priority messages to escalation handler
escalate_rule = RoutingRule(
    name="escalate_critical",
    action=RoutingAction.ESCALATE,
    match_priority=4  # CRITICAL
)
client.add_rule(escalate_rule)

# Discard low-priority notifications
discard_rule = RoutingRule(
    name="discard_spam",
    action=RoutingAction.DISCARD,
    match_content="spam|junk|low-value"
)
client.add_rule(discard_rule)
```

### Receive with Routing

```python
# Get messages grouped by routing action
routed = client.recv_with_routing(wait=5)

# Deliver messages
for item in routed['deliver']:
    msg = item['message']
    rule = item['rule']  # None if no rule matched
    print(f"Processing: {msg['body']}")

# Forward messages already handled by routing system
# Check routed['forward'] for forwarded messages

# Queue important items for later
for item in routed['queue']:
    priority_queue.put(item['message'])
```

## API Reference

### RoutingAction Enum

```python
class RoutingAction(Enum):
    DELIVER = "deliver"      # Deliver to this agent
    FORWARD = "forward"      # Forward to another agent
    DISCARD = "discard"      # Discard (mark as read)
    QUEUE = "queue"          # Queue for later processing
    ESCALATE = "escalate"    # Forward to escalation handler
```

### RoutingRule

```python
class RoutingRule:
    def __init__(
        self,
        name: str,
        action: RoutingAction,
        match_sender: Optional[str] = None,
        match_content: Optional[str] = None,
        match_priority: Optional[int] = None,
        match_thread: Optional[str] = None,
        forward_to: Optional[str] = None,
        enabled: bool = True
    )

    def matches(message: Dict[str, Any]) -> bool
```

### RoutingClient

```python
class RoutingClient(A2AClient):
    # Setup
    def __init__(self, project: str, agent_id: str)
    def init_routing_table(self) -> bool

    # Rule management
    def add_rule(rule: RoutingRule) -> bool
    def get_rules(self) -> List[RoutingRule]
    def disable_rule(rule_name: str) -> bool
    def enable_rule(rule_name: str) -> bool
    def delete_rule(rule_name: str) -> bool

    # Routing
    def recv_with_routing(
        wait: float = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: int = 0
    ) -> Dict[str, List[Dict]]

    def apply_routing(routed: Dict) -> bool

    # Statistics
    def get_routing_stats(self) -> Dict[str, Any]
```

### SmartRouter

```python
class SmartRouter:
    def __init__(self, client: RoutingClient)

    def add_custom_matcher(
        matcher: Callable[[Dict], bool],
        handler: Callable[[Dict], None]
    ) -> SmartRouter

    def add_handler(
        action: str,
        handler: Callable[[Dict], None]
    ) -> SmartRouter

    def route_message(message: Dict) -> bool
    def route_batch(messages: List[Dict]) -> Dict[str, int]
```

## Pattern Matching

### Matching Rules

Rules support **both substring and regex matching**:

```python
# Substring match (case-insensitive)
rule1 = RoutingRule(
    name="database_issues",
    action=RoutingAction.ESCALATE,
    match_content="database error"  # Matches "Database Error", "DATABASE ERROR", etc.
)

# Regex match
rule2 = RoutingRule(
    name="port_errors",
    action=RoutingAction.ESCALATE,
    match_content="port (\\d+) (in use|unavailable)"  # Matches "port 8080 in use"
)

# Sender patterns
rule3 = RoutingRule(
    name="external_alerts",
    action=RoutingAction.QUEUE,
    match_sender="monitoring-*"  # Glob-like pattern
)
```

### Matching Priority

When multiple rules could match, the **first rule wins**:

```python
# Rules are evaluated in order
client.add_rule(critical_rule)    # Checked first
client.add_rule(normal_rule)      # Checked second if critical doesn't match
client.add_rule(discard_rule)     # Fallback
```

## Common Patterns

### Alert Routing

```python
client = RoutingClient("myproject", "alert_manager")
client.init_routing_table()

# Critical alerts to oncall
client.add_rule(RoutingRule(
    name="critical_oncall",
    action=RoutingAction.FORWARD,
    match_priority=4,
    forward_to="oncall"
))

# Warnings to ops
client.add_rule(RoutingRule(
    name="warning_ops",
    action=RoutingAction.FORWARD,
    match_priority=3,
    forward_to="ops_team"
))

# Info to logs (discard)
client.add_rule(RoutingRule(
    name="info_discard",
    action=RoutingAction.DISCARD,
    match_priority=1
))
```

### Content-Based Routing

```python
# Route database errors to database team
client.add_rule(RoutingRule(
    name="database_errors",
    action=RoutingAction.FORWARD,
    match_content="database|sql|transaction",
    forward_to="database_team"
))

# Route auth failures to security
client.add_rule(RoutingRule(
    name="auth_failures",
    action=RoutingAction.FORWARD,
    match_content="authentication failed|unauthorized",
    forward_to="security_team"
))

# Route performance issues to platform
client.add_rule(RoutingRule(
    name="perf_issues",
    action=RoutingAction.FORWARD,
    match_content="latency|slow|timeout|performance",
    forward_to="platform_team"
))
```

### Sender-Based Routing

```python
# Automated systems to queue
client.add_rule(RoutingRule(
    name="system_messages",
    action=RoutingAction.QUEUE,
    match_sender="system|automation|ci-*"
))

# External partners to archive
client.add_rule(RoutingRule(
    name="partner_archive",
    action=RoutingAction.DISCARD,
    match_sender="partner-*"
))
```

### Smart Router Example

```python
from a2a_routing import SmartRouter

router = SmartRouter(client)

# Custom matcher for on-call hours
def is_business_hours(msg):
    import datetime
    hour = datetime.datetime.now().hour
    return 9 <= hour <= 17

# Handle business hours alerts
def handle_business_alert(msg):
    # Immediate processing
    process_critical(msg)

# Custom matcher for pattern
def has_payment_error(msg):
    return "payment" in msg['body'].lower() and "error" in msg['body'].lower()

def handle_payment_error(msg):
    # High priority handling
    forward_to_payments(msg)

# Register matchers
router.add_custom_matcher(is_business_hours, handle_business_alert)
router.add_custom_matcher(has_payment_error, handle_payment_error)

# Route messages
messages = client.recv()
for msg in messages:
    router.route_message(msg)
```

## Database Schema

### routing_rules Table

```sql
CREATE TABLE routing_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    action TEXT NOT NULL,
    match_sender TEXT,
    match_content TEXT,
    match_priority INTEGER,
    match_thread TEXT,
    forward_to TEXT,
    enabled BOOLEAN DEFAULT 1,
    created_at REAL NOT NULL,
    UNIQUE(agent_id, rule_name)
)
```

### Fields

| Field | Type | Purpose |
|-------|------|---------|
| agent_id | TEXT | Agent owning the rule |
| rule_name | TEXT | Unique rule identifier |
| action | TEXT | Action when matched (deliver, forward, etc) |
| match_sender | TEXT | Sender pattern to match |
| match_content | TEXT | Message body pattern |
| match_priority | INTEGER | Minimum priority level |
| match_thread | TEXT | Thread ID to match |
| forward_to | TEXT | Destination for forward action |
| enabled | BOOLEAN | Whether rule is active |
| created_at | REAL | Rule creation timestamp |

## Routing Flow

### recv_with_routing() Process

1. Get all active rules for agent
2. Fetch all recipient messages
3. For each message:
   - Evaluate rules in order
   - Apply first matching rule's action
   - If no rule matches, default to DELIVER
4. Return dict grouped by action

### apply_routing() Process

1. Process FORWARD items: Insert new messages to forward_to
2. Process DISCARD items: Mark messages as read (hides them)
3. Commit all changes

## Performance

- **Rule creation**: < 1ms
- **Rule matching**: 1-5ms per message (depends on pattern complexity)
- **recv_with_routing()**: 20-100ms for typical message set
- **apply_routing()**: 10-50ms
- **Pattern matching**: Regex slower than substring (~2-3x)

## Best Practices

1. **Order rules by specificity**: Most specific first, general catch-all last
2. **Keep patterns simple**: Avoid complex regex; use substring when possible
3. **Test pattern matching**: Verify rules match intended messages
4. **Monitor rule statistics**: Use `get_routing_stats()` to verify coverage
5. **Disable unused rules**: Set `enabled=False` instead of deleting
6. **Document rule purpose**: Use meaningful names like "escalate_critical"
7. **Implement handlers carefully**: Don't let handlers crash (try-except)

## Troubleshooting

### Rules not matching

```python
# Verify rule is enabled
stats = client.get_routing_stats()
print(f"Enabled: {stats['enabled_rules']}")

# Test pattern manually
from a2a_routing import RoutingRule
rule = RoutingRule(
    name="test",
    action=RoutingAction.DELIVER,
    match_content="test pattern"
)
test_msg = {"body": "This is a test pattern"}
if rule.matches(test_msg):
    print("Pattern matches!")
```

### Pattern matching confusion

```python
# Substring match (preferred for simple patterns)
match_content="error"  # Matches "error", "Error", "ERROR", "an error occurred"

# Regex match (for complex patterns)
match_content="error.*code (\\d+)"  # Matches "error code 500"

# Patterns are case-insensitive
```

### Performance issues

```python
# Too many rules slows down matching
# Check rule count
stats = client.get_routing_stats()
if stats['total_rules'] > 100:
    # Consider consolidating rules or using SmartRouter

# Complex regex patterns are slower
# Profile with timing
import time
start = time.time()
routed = client.recv_with_routing()
elapsed = time.time() - start
print(f"Routing took {elapsed:.3f}s")
```

## Limitations

1. **No rule ordering in FORWARD**: Multiple forward rules undefined behavior
2. **No conditional logic**: Rules don't support if-then chains
3. **No regex capture groups**: Matched groups aren't passed to handlers
4. **No message transformation**: Rules can't modify message content
5. **No rate limiting**: Rules can't rate-limit message forwarding

## See Also

- [README.md](../README.md) — Project overview
- [CLIENT_API.md](docs/CLIENT_API.md) — Base client reference
- [PRIORITY.md](docs/PRIORITY.md) — Message prioritization
- [AUDIT.md](docs/AUDIT.md) — Audit logging
- [CHANGELOG.md](CHANGELOG.md) — Release history and roadmap
