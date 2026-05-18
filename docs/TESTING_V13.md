# v1.3 Testing & Validation Guide

Comprehensive testing strategy for v1.3 features: encryption, full-text search, audit logging, prioritization, and routing.

## Table of Contents
1. [Unit Testing](#unit-testing)
2. [Feature Testing](#feature-testing)
3. [Integration Testing](#integration-testing)
4. [Performance Testing](#performance-testing)
5. [Edge Case Testing](#edge-case-testing)
6. [Security Testing](#security-testing)

---

## Unit Testing

### Running Tests

**All tests**:
```bash
python3 test_v13_features.py -v
```

**Specific test class**:
```bash
python3 -m unittest test_v13_features.TestEncryption -v
python3 -m unittest test_v13_features.TestMessagePriority -v
python3 -m unittest test_v13_features.TestMessageRouting -v
python3 -m unittest test_v13_features.TestAuditLogging -v
python3 -m unittest test_v13_features.TestFullTextSearch -v
```

**Specific test**:
```bash
python3 -m unittest test_v13_features.TestEncryption.test_symmetric_encrypt_decrypt -v
```

### Test Coverage Areas

#### Encryption Tests
- Symmetric encryption/decryption (Fernet)
- Asymmetric key generation (RSA-2048)
- Public/private key management
- Message wrapping and unwrapping
- Key file persistence
- Invalid key handling
- Large message encryption (>1MB)
- Empty message encryption

#### Priority Tests
- Priority enum values (LOW/NORMAL/HIGH/CRITICAL)
- Default priority assignment
- Priority-aware message ordering
- recv_by_priority() filtering
- recv_above_priority() threshold
- get_critical_messages() shortcut
- Priority statistics
- Mixed priority message handling

#### Routing Tests
- Rule creation and persistence
- Rule enable/disable
- Rule deletion
- Substring pattern matching
- Regex pattern matching
- Priority-based routing
- Sender/recipient matching
- Thread ID filtering
- recv_with_routing() evaluation
- apply_routing() execution
- Forward action with forwarding
- Discard action (mark as read)
- Queue action
- Escalate action

#### Audit Tests
- Operation logging
- Audit table creation
- Audit queries by agent
- Audit queries by operation type
- Date range filtering
- Result filtering (success/failure)
- Statistics aggregation
- Export to JSON
- Context manager with success
- Context manager with exception

#### Full-Text Search Tests
- Simple term search
- Phrase search
- Boolean operators (AND, OR)
- Negation (NOT)
- Prefix matching
- Case-insensitive search
- FTS table creation
- Search ranking/relevance
- Empty query handling
- Large result sets

---

## Feature Testing

### Encryption Feature Test

**Script** (`test_encryption_feature.py`):
```python
#!/usr/bin/env python3
from a2a_crypto import CryptoClient
from a2a_client import A2AClient

def test_encryption_workflow():
    """Test end-to-end encrypted messaging."""
    
    # Initialize clients
    alice_crypto = CryptoClient('test-project', 'alice')
    bob_crypto = CryptoClient('test-project', 'bob')
    a2a = A2AClient('test-project', 'alice')
    
    # Generate keypairs
    alice_pub, alice_priv = alice_crypto.generate_keypair()
    bob_pub, bob_priv = bob_crypto.generate_keypair()
    
    # Alice encrypts message for Bob
    message = "Secret meeting at 3pm"
    encrypted = alice_crypto.wrap_encrypted_message(message, bob_pub)
    assert encrypted != message
    
    # Send encrypted message
    msg_id = a2a.send('bob', encrypted)
    print(f"✓ Sent encrypted message {msg_id}")
    
    # Bob receives and decrypts
    messages = a2a.recv(unread_only=True)
    assert len(messages) > 0
    
    received = messages[0]['body']
    decrypted = bob_crypto.decrypt_message(received)
    assert decrypted == message
    
    print(f"✓ Decryption successful: {decrypted}")
    return True

if __name__ == '__main__':
    test_encryption_workflow()
    print("\n✅ Encryption feature test passed")
```

**Run**:
```bash
python3 test_encryption_feature.py
```

### Priority Feature Test

**Script** (`test_priority_feature.py`):
```python
#!/usr/bin/env python3
from a2a_priority import PriorityClient, Priority
import time

def test_priority_ordering():
    """Test priority-aware message ordering."""
    
    priority = PriorityClient('test-project', 'receiver')
    priority.init_priority_table()
    
    # Send messages in mixed order
    msgs = [
        ('low priority message', Priority.LOW),
        ('critical alert', Priority.CRITICAL),
        ('normal update', Priority.NORMAL),
        ('high priority request', Priority.HIGH),
    ]
    
    for body, pri in msgs:
        priority.send('receiver', body, priority=pri)
        time.sleep(0.1)  # Ensure different timestamps
    
    # Receive with priority ordering
    received = priority.recv(wait=1, priority_aware=True)
    
    # Should be ordered: CRITICAL, HIGH, NORMAL, LOW
    expected_order = [Priority.CRITICAL, Priority.HIGH, Priority.NORMAL, Priority.LOW]
    received_priorities = [msg['priority'] for msg in received]
    
    assert received_priorities == expected_order, \
        f"Expected {expected_order}, got {received_priorities}"
    
    print(f"✓ Messages ordered correctly by priority")
    return True

if __name__ == '__main__':
    test_priority_ordering()
    print("\n✅ Priority feature test passed")
```

### Routing Feature Test

**Script** (`test_routing_feature.py`):
```python
#!/usr/bin/env python3
from a2a_routing import RoutingClient, RoutingRule, RoutingAction
from a2a_priority import Priority
from a2a_client import A2AClient

def test_routing_rules():
    """Test message routing with rules."""
    
    router = RoutingClient('test-project', 'processor')
    router.init_routing_table()
    a2a = A2AClient('test-project', 'sender')
    
    # Add routing rules
    router.add_rule(RoutingRule(
        name='critical_escalate',
        action=RoutingAction.ESCALATE,
        match_priority=Priority.CRITICAL,
        forward_to='oncall'
    ))
    
    router.add_rule(RoutingRule(
        name='error_forward',
        action=RoutingAction.FORWARD,
        match_content='error',
        forward_to='support'
    ))
    
    # Send test messages
    a2a.send('processor', 'System error occurred', from_agent='sender')
    a2a.send('processor', 'Critical alert', from_agent='sender', priority=Priority.CRITICAL)
    
    # Get routed messages
    routed = router.recv_with_routing(wait=2)
    
    # Verify routing
    assert len(routed['escalate']) > 0, "Critical message not escalated"
    assert len(routed['forward']) > 0, "Error message not forwarded"
    
    print(f"✓ Routing rules working correctly")
    print(f"  - Escalated: {len(routed['escalate'])}")
    print(f"  - Forwarded: {len(routed['forward'])}")
    
    return True

if __name__ == '__main__':
    test_routing_rules()
    print("\n✅ Routing feature test passed")
```

### Audit Feature Test

**Script** (`test_audit_feature.py`):
```python
#!/usr/bin/env python3
from a2a_audit import AuditClient, AuditContextManager
from a2a_client import A2AClient

def test_audit_logging():
    """Test audit logging for compliance."""
    
    audit = AuditClient('test-project')
    audit.init_audit_table()
    a2a = A2AClient('test-project', 'alice')
    
    # Send messages with audit logging
    with AuditContextManager(audit, 'alice', 'send_message') as ctx:
        msg_id = a2a.send('bob', 'test message')
        ctx.details = {'recipient': 'bob', 'message_id': msg_id}
    
    # Query audit trail
    trail = audit.get_agent_audit_trail('alice', days=1)
    
    assert len(trail.get('operations', [])) > 0, "No audit entries found"
    
    # Check stats
    stats = audit.get_audit_stats(days=1)
    print(f"✓ Audit logging working:")
    print(f"  - Total operations: {stats.get('total_operations', 0)}")
    print(f"  - By operation: {stats.get('by_operation', {})}")
    
    return True

if __name__ == '__main__':
    test_audit_logging()
    print("\n✅ Audit feature test passed")
```

### Full-Text Search Feature Test

**Script** (`test_fts_feature.py`):
```python
#!/usr/bin/env python3
from a2a_fts import FTSClient
from a2a_client import A2AClient

def test_full_text_search():
    """Test full-text search capabilities."""
    
    fts = FTSClient('test-project', 'alice')
    fts.init_fts_table()
    a2a = A2AClient('test-project', 'alice')
    
    # Send searchable messages
    messages = [
        'Database connection timeout error',
        'Authentication failed for user',
        'Query optimization complete',
        'Error: Out of memory',
    ]
    
    for msg in messages:
        a2a.send('bob', msg)
    
    # Test searches
    tests = [
        ('error', 3),  # Should find 3 messages with 'error'
        ('authentication OR memory', 2),  # Boolean OR
        ('database AND connection', 1),  # Boolean AND
        ('error -timeout', 1),  # Negation (error but not timeout)
        ('error*', 3),  # Prefix matching
    ]
    
    for query, expected_count in tests:
        results = fts.search_fts(query)
        actual_count = len(results)
        assert actual_count >= expected_count - 1, \
            f"Query '{query}': expected ~{expected_count}, got {actual_count}"
        print(f"✓ Query '{query}': found {actual_count} messages")
    
    return True

if __name__ == '__main__':
    test_full_text_search()
    print("\n✅ Full-text search feature test passed")
```

---

## Integration Testing

### Multi-Feature Integration Test

**Script** (`test_integration_v13.py`):
```python
#!/usr/bin/env python3
"""
Test all v1.3 features working together:
1. Encrypt sensitive message
2. Send with high priority
3. Apply routing rule
4. Log to audit trail
5. Search in FTS
"""

from a2a_client import A2AClient
from a2a_crypto import CryptoClient
from a2a_priority import PriorityClient, Priority
from a2a_routing import RoutingClient, RoutingRule, RoutingAction
from a2a_audit import AuditClient
from a2a_fts import FTSClient

def test_integrated_workflow():
    """Test complete v1.3 workflow."""
    
    project = 'integration-test'
    
    # Initialize all components
    alice = A2AClient(project, 'alice')
    alice_crypto = CryptoClient(project, 'alice')
    alice_priority = PriorityClient(project, 'alice')
    alice_routing = RoutingClient(project, 'alice')
    alice_audit = AuditClient(project)
    alice_fts = FTSClient(project, 'alice')
    
    # Initialize tables
    alice_crypto.generate_keypair()
    alice_priority.init_priority_table()
    alice_routing.init_routing_table()
    alice_audit.init_audit_table()
    alice_fts.init_fts_table()
    
    # Setup routing rules
    alice_routing.add_rule(RoutingRule(
        name='security_escalate',
        action=RoutingAction.ESCALATE,
        match_content='security breach',
        match_priority=Priority.CRITICAL,
        forward_to='security-team'
    ))
    
    # Step 1: Prepare encrypted message
    message = "Security breach detected in production"
    bob_crypto = CryptoClient(project, 'bob')
    bob_crypto.generate_keypair()
    bob_public_key = bob_crypto.get_public_key()
    
    encrypted = alice_crypto.wrap_encrypted_message(message, bob_public_key)
    
    # Step 2: Send with high priority
    msg_id = alice_priority.send('bob', encrypted, priority=Priority.CRITICAL)
    print(f"✓ Sent encrypted critical message: {msg_id}")
    
    # Step 3: Route the message
    routed = alice_routing.recv_with_routing(wait=1)
    print(f"✓ Message routed: {routed}")
    
    # Step 4: Check audit trail
    stats = alice_audit.get_audit_stats(days=1)
    print(f"✓ Audit recorded: {stats}")
    
    # Step 5: Search for the message
    results = alice_fts.search_fts('security breach')
    print(f"✓ Found message in FTS: {len(results)} results")
    
    assert msg_id is not None
    assert len(results) > 0
    
    return True

if __name__ == '__main__':
    test_integrated_workflow()
    print("\n✅ Integration test passed - all v1.3 features working together")
```

---

## Performance Testing

### Throughput Test

**Script** (`test_performance_throughput.py`):
```python
#!/usr/bin/env python3
import time
from a2a_priority import PriorityClient, Priority
from a2a_priority_async import PriorityClientAsync

def test_sync_throughput(num_messages=1000):
    """Measure sync throughput."""
    print(f"Testing sync throughput ({num_messages} messages)...")
    
    client = PriorityClient('perf-test', 'sender')
    client.init_priority_table()
    
    start = time.time()
    for i in range(num_messages):
        client.send('receiver', f'Message {i}', priority=Priority.NORMAL)
    elapsed = time.time() - start
    
    throughput = num_messages / elapsed
    latency = (elapsed / num_messages) * 1000
    
    print(f"✓ Sync: {throughput:.1f} msg/sec ({latency:.2f}ms per message)")
    return throughput

def test_async_throughput(num_messages=1000):
    """Measure async throughput."""
    print(f"Testing async throughput ({num_messages} messages)...")
    
    import asyncio
    
    async def send_messages():
        client = PriorityClientAsync('perf-test', 'async_sender')
        
        start = time.time()
        tasks = [
            client.send('receiver', f'Message {i}', priority=Priority.NORMAL)
            for i in range(num_messages)
        ]
        await asyncio.gather(*tasks)
        elapsed = time.time() - start
        
        await client._connect().__aenter__()
        return elapsed
    
    elapsed = asyncio.run(send_messages())
    
    throughput = num_messages / elapsed
    latency = (elapsed / num_messages) * 1000
    
    print(f"✓ Async: {throughput:.1f} msg/sec ({latency:.2f}ms per message)")
    return throughput

if __name__ == '__main__':
    sync_throughput = test_sync_throughput(100)
    async_throughput = test_async_throughput(100)
    
    speedup = async_throughput / sync_throughput if sync_throughput > 0 else 0
    print(f"\nAsync speedup: {speedup:.1f}x")
```

### Latency Test

**Script** (`test_performance_latency.py`):
```python
#!/usr/bin/env python3
import time
import statistics
from a2a_priority import PriorityClient, Priority

def test_latency(num_iterations=100):
    """Measure send/recv latency percentiles."""
    print(f"Measuring latency ({num_iterations} iterations)...")
    
    client = PriorityClient('latency-test', 'agent')
    client.init_priority_table()
    
    latencies = []
    
    for i in range(num_iterations):
        start = time.time()
        client.send('other', f'Test message {i}', priority=Priority.NORMAL)
        elapsed = (time.time() - start) * 1000
        latencies.append(elapsed)
    
    # Calculate percentiles
    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.5)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    
    print(f"✓ Send latency:")
    print(f"  - p50: {p50:.2f}ms")
    print(f"  - p95: {p95:.2f}ms")
    print(f"  - p99: {p99:.2f}ms")
    print(f"  - avg: {statistics.mean(latencies):.2f}ms")
    print(f"  - max: {max(latencies):.2f}ms")

if __name__ == '__main__':
    test_latency(50)
```

---

## Edge Case Testing

### Edge Cases

**Large messages**:
```python
from a2a_crypto import CryptoClient
crypto = CryptoClient('test', 'agent')

# Test 10MB message
large_message = 'x' * (10 * 1024 * 1024)
encrypted = crypto.encrypt_message(large_message, crypto.generate_symmetric_key())
decrypted = crypto.decrypt_message(encrypted, crypto.generate_symmetric_key())
assert len(decrypted) == len(large_message)
```

**Empty messages**:
```python
client.send('agent', '', priority=Priority.NORMAL)
messages = client.recv()
assert any(msg['body'] == '' for msg in messages)
```

**Null/special characters**:
```python
special = '\x00\x01\x02\xff'
client.send('agent', special, priority=Priority.NORMAL)
```

**Concurrent access**:
```python
import threading

def send_messages():
    for i in range(100):
        client.send('agent', f'Message {i}')

threads = [threading.Thread(target=send_messages) for _ in range(10)]
for t in threads: t.start()
for t in threads: t.join()

messages = client.recv()
assert len(messages) >= 1000
```

---

## Security Testing

### Encryption Security

```python
# Verify keys are different
crypto1 = CryptoClient('test', 'alice')
crypto2 = CryptoClient('test', 'bob')

pub1 = crypto1.generate_keypair()[0]
pub2 = crypto2.generate_keypair()[0]

assert pub1 != pub2, "Keys should be unique per agent"

# Verify encrypted messages can't be decrypted without key
message = "secret"
encrypted = crypto1.wrap_encrypted_message(message, pub2)

# Should not be able to decrypt with wrong key
try:
    crypto2.decrypt_message(encrypted)  # Wrong private key
    assert False, "Should have raised error"
except:
    pass  # Expected
```

### Audit Log Security

```python
# Verify audit logs can't be modified
audit = AuditClient('test')
audit.init_audit_table()

# Log operation
audit.log_operation('agent', 'operation', {}, 'success')

# Try to modify (should create new audit entry, not modify)
# Audit logs are append-only
```

---

## Checklist for Release

- [ ] All unit tests pass (95+ tests)
- [ ] All feature tests pass (encryption, priority, routing, audit, FTS)
- [ ] Integration test passes (all features together)
- [ ] Performance meets targets (latency p99 < 50ms, throughput > 1K msg/sec)
- [ ] Edge cases handled (large messages, empty strings, concurrent access)
- [ ] Security tests pass (key uniqueness, audit immutability)
- [ ] Database integrity verified
- [ ] No memory leaks (valgrind/py-spy)
- [ ] Documentation complete and tested
- [ ] Examples work end-to-end
- [ ] Deployment guide validated

---

**v1.3 Testing Complete** ✅
