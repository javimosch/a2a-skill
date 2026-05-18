# a2a Troubleshooting Guide

Quick solutions for common issues in v1.3 deployments.

## Table of Contents
1. [Installation Issues](#installation-issues)
2. [Database Issues](#database-issues)
3. [Encryption Issues](#encryption-issues)
4. [Performance Issues](#performance-issues)
5. [Routing/Priority Issues](#routingpriority-issues)
6. [Audit/Search Issues](#auditsearch-issues)
7. [Deployment Issues](#deployment-issues)

---

## Installation Issues

### Issue: Python SQLite3 Not Found

```
Error: sqlite3 module not found
```

**Diagnosis**:
```bash
python3 -c "import sqlite3"
# If error, sqlite3 not available
```

**Solutions**:

1. **Find Python with SQLite**:
```bash
# The a2a bash wrapper auto-detects this
# Check which Python has sqlite3:
for py in python3.{10,11,12} python3 python; do
  $py -c "import sqlite3" 2>/dev/null && echo "Found: $py"
done
```

2. **Install SQLite dev package**:
```bash
# Ubuntu/Debian
sudo apt-get install python3-dev libsqlite3-dev
sudo apt-get install python3-tk  # For tkinter

# macOS
brew install python@3.12
# or use pyenv to install a version with sqlite3

# Fedora/RHEL
sudo dnf install python3-devel sqlite-devel
```

3. **Use system Python**:
```bash
# If you have a system Python with sqlite3:
/usr/bin/python3 -c "import sqlite3" && echo "System Python OK"
```

---

## Database Issues

### Issue: "database is locked"

```
sqlite3.OperationalError: database is locked
```

**Diagnosis**:
```bash
# Check for stale processes
ps aux | grep a2a | grep -v grep

# Check for lock files
ls -la ~/.a2a/your-project/database.db*
```

**Solutions**:

1. **Kill stale processes**:
```bash
# Kill all a2a processes
pkill -f "python.*a2a"

# Or kill specific process
kill -9 <PID>
```

2. **Remove stale lock files** (if you're sure no process is using the DB):
```bash
# ONLY do this if no other process is accessing the DB
rm ~/.a2a/your-project/database.db-wal
rm ~/.a2a/your-project/database.db-shm
```

3. **Restart the service**:
```bash
sudo systemctl restart a2a
# or
docker-compose restart a2a
```

### Issue: "no such table: messages"

```
sqlite3.OperationalError: no such table: messages
```

**Cause**: Database not initialized.

**Solution**:
```python
from a2a_client import A2AClient

client = A2AClient('your-project', 'agent-id')
client.send('other', 'test')  # This creates tables

# Or explicitly initialize:
import sqlite3
db_path = f"{Path.home()}/.a2a/your-project/database.db"
conn = sqlite3.connect(str(db_path))
conn.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        recipient TEXT,
        body TEXT,
        thread_id INTEGER,
        priority INTEGER DEFAULT 2,
        created_at REAL,
        ttl_seconds INTEGER,
        UNIQUE(id)
    )
""")
conn.commit()
conn.close()
```

### Issue: "no such column: priority"

```
sqlite3.OperationalError: no such column: priority
```

**Cause**: Old database created with v1.2, missing v1.3 columns.

**Solution**:
```python
from a2a_priority import PriorityClient

# Initialize priority table (migrates if needed)
priority = PriorityClient('your-project', 'migration-agent')
priority.init_priority_table()

# Check if migration worked
import sqlite3
conn = sqlite3.connect("~/.a2a/your-project/database.db")
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(messages)")
columns = {row[1] for row in cursor.fetchall()}
print(f"Columns: {columns}")
# Should include: id, sender, recipient, body, priority, created_at, ttl_seconds, thread_id
```

### Issue: "database disk image is malformed"

```
sqlite3.DatabaseError: database disk image is malformed
```

**Diagnosis**:
```bash
sqlite3 ~/.a2a/your-project/database.db "PRAGMA integrity_check;"
# If output is NOT "ok", database is corrupted
```

**Solutions**:

1. **Recover from backup** (if available):
```bash
# Restore database from backup
cp backups/database_2024-01-15.db ~/.a2a/your-project/database.db

# Verify
sqlite3 ~/.a2a/your-project/database.db "PRAGMA integrity_check;"
```

2. **Dump and restore** (if backup corrupted too):
```bash
# Dump all data from corrupted DB
sqlite3 ~/.a2a/your-project/database.db ".dump" > dump.sql

# Delete corrupted DB
rm ~/.a2a/your-project/database.db*

# Create new DB and restore
sqlite3 ~/.a2a/your-project/database.db < dump.sql

# Verify
sqlite3 ~/.a2a/your-project/database.db "PRAGMA integrity_check;"
```

3. **Rebuild from scratch** (last resort):
```bash
# Remove all DB files
rm -rf ~/.a2a/your-project/database.db*

# Recreate from scratch (all messages lost)
python3 -c "
from a2a_client import A2AClient
client = A2AClient('your-project', 'new-agent')
print('✓ Database recreated')
"
```

---

## Encryption Issues

### Issue: "No public key found"

```
FileNotFoundError: Public key not found for bob
```

**Diagnosis**:
```python
from a2a_crypto import CryptoClient

crypto = CryptoClient('project', 'bob')
print(f"Public key path: {crypto.public_key_path}")
print(f"Exists: {crypto.public_key_path.exists()}")
```

**Solutions**:

1. **Generate keypair for agent**:
```python
from a2a_crypto import CryptoClient

crypto = CryptoClient('project', 'bob')
pub, priv = crypto.generate_keypair()
print(f"✓ Keypair generated for bob")
```

2. **Share public keys** (before encrypted communication):
```python
# Each agent should generate and announce their public key
from a2a_client import A2AClient
import json

crypto = CryptoClient('project', 'alice')
pub = crypto.get_public_key()

a2a = A2AClient('project', 'alice')
a2a.send('all', json.dumps({
    'type': 'public_key',
    'agent_id': 'alice',
    'public_key': pub
}))
```

### Issue: "decryption failed" or "Bad decrypt"

```
cryptography.fernet.InvalidToken: Incorrect padding
```

**Causes**:
1. Wrong key used for decryption
2. Message was corrupted in transit
3. Encrypted with different key than attempting to decrypt with

**Solutions**:

1. **Verify message wasn't corrupted**:
```bash
# Check message size is reasonable
sqlite3 ~/.a2a/your-project/database.db "
  SELECT id, sender, length(body) FROM messages 
  ORDER BY created_at DESC LIMIT 5;
"
```

2. **Use correct key**:
```python
from a2a_crypto import CryptoClient

# Make sure you're using the sender's public key (to encrypt)
# and your own private key (to decrypt)
crypto = CryptoClient('project', 'bob')

# This is correct:
encrypted = crypto.wrap_encrypted_message(msg, alice_public_key)  # Alice's key
decrypted = crypto.decrypt_message(encrypted)  # Bob's private key

# This is wrong:
encrypted = crypto.wrap_encrypted_message(msg, bob_public_key)    # Own key?
decrypted = crypto.decrypt_message(encrypted)  # Will fail
```

3. **Re-exchange keys**:
```python
# Announce new public key
from a2a_client import A2AClient
crypto = CryptoClient('project', 'bob')
crypto.generate_keypair(force=True)

a2a = A2AClient('project', 'bob')
a2a.send('all', f"New public key: {crypto.get_public_key()}")
```

---

## Performance Issues

### Issue: Slow message send/receive

**Diagnosis**:
```python
import time
from a2a_client import A2AClient

client = A2AClient('project', 'agent')

# Measure send latency
start = time.time()
for i in range(10):
    client.send('other', 'test')
latency = (time.time() - start) / 10 * 1000
print(f"Send latency: {latency:.1f}ms per message")

# Measure recv latency
start = time.time()
messages = client.recv(wait=5)
latency = (time.time() - start) * 1000
print(f"Recv latency: {latency:.1f}ms")
```

**Solutions**:

1. **Use async client for concurrency**:
```python
import asyncio
from a2a_priority_async import PriorityClientAsync

async def send_many():
    client = PriorityClientAsync('project', 'agent')
    # Send 100 messages concurrently
    await asyncio.gather(*[
        client.send('other', f'Message {i}')
        for i in range(100)
    ])

asyncio.run(send_many())
```

2. **Optimize SQLite**:
```python
import sqlite3
db_path = "~/.a2a/your-project/database.db"
conn = sqlite3.connect(str(db_path))

# Apply optimizations
conn.execute("PRAGMA synchronous=NORMAL")      # Async writes
conn.execute("PRAGMA cache_size=10000")        # 40MB cache
conn.execute("PRAGMA temp_store=MEMORY")       # RAM for temp tables
conn.execute("PRAGMA busy_timeout=5000")       # 5s retry

print("✓ SQLite optimizations applied")
```

3. **Check database size** (large DB is slow):
```bash
du -sh ~/.a2a/your-project/database.db

# If > 1GB, consider archival
# See OPERATIONS_GUIDE.md for archival procedures
```

### Issue: High memory usage

**Diagnosis**:
```bash
# Check process memory
ps aux | grep a2a | grep -v grep

# Check database size
du -sh ~/.a2a/*/database.db

# Check if WAL files are growing
du -sh ~/.a2a/*/database.db-wal
```

**Solutions**:

1. **Clear WAL files** (if stuck):
```bash
# Stop service first
sudo systemctl stop a2a

# Clear WAL
rm ~/.a2a/your-project/database.db-wal
rm ~/.a2a/your-project/database.db-shm

# Restart
sudo systemctl start a2a
```

2. **Reduce cache**:
```python
conn.execute("PRAGMA cache_size=1000")  # 4MB instead of 40MB
```

3. **Archive old messages**:
```python
# See OPERATIONS_GUIDE.md for archival procedures
```

---

## Routing/Priority Issues

### Issue: Messages not being routed

**Diagnosis**:
```python
from a2a_routing import RoutingClient

routing = RoutingClient('project', 'agent')
rules = routing.get_rules()
print(f"Rules configured: {len(rules)}")
for rule in rules:
    print(f"  - {rule.name}: {rule.action.value}")
```

**Solutions**:

1. **Check rules are enabled**:
```python
# Rules must be enabled
rules = routing.get_rules()
for rule in rules:
    print(f"{rule.name}: enabled={rule.enabled}")

# If disabled, enable them
routing.enable_rule('rule_name')
```

2. **Verify pattern matching**:
```python
# Test rule pattern matching
rule = routing.get_rules()[0]
test_message = {
    'sender': 'alice',
    'body': 'test error message',
    'priority': 3
}

if rule.matches(test_message):
    print(f"✓ Message matches rule {rule.name}")
else:
    print(f"✗ Message does NOT match rule {rule.name}")
```

3. **Add rules correctly**:
```python
from a2a_routing import RoutingRule, RoutingAction
from a2a_priority import Priority

routing.add_rule(RoutingRule(
    name='test_rule',
    action=RoutingAction.FORWARD,
    match_content='error',           # Pattern to match
    match_priority=Priority.HIGH,    # Optional: only HIGH+ priority
    forward_to='support',            # Where to forward
))
print("✓ Rule added")
```

### Issue: Priority ordering not working

**Diagnosis**:
```python
from a2a_priority import PriorityClient

priority = PriorityClient('project', 'agent')
messages = priority.recv(wait=5, priority_aware=True)

for msg in messages:
    print(f"Priority: {msg['priority']}, Body: {msg['body'][:30]}")
```

**Solution**:
```python
# Ensure priority is specified when sending
from a2a_priority import Priority

# Send with priority
priority.send('other', 'Urgent!', priority=Priority.CRITICAL)
priority.send('other', 'FYI', priority=Priority.LOW)

# Receive in priority order (highest first)
messages = priority.recv(priority_aware=True)
```

---

## Audit/Search Issues

### Issue: No audit entries being created

**Diagnosis**:
```python
from a2a_audit import AuditClient

audit = AuditClient('project')
stats = audit.get_audit_stats(days=1)
print(f"Audit entries: {stats['total_operations']}")
```

**Solutions**:

1. **Initialize audit table**:
```python
audit = AuditClient('project')
audit.init_audit_table()
print("✓ Audit table initialized")
```

2. **Log operations**:
```python
from a2a_audit import AuditContextManager

with AuditContextManager(audit, 'alice', 'send') as ctx:
    msg_id = client.send('bob', 'message')
    ctx.details = {'recipient': 'bob', 'msg_id': msg_id}
    # Automatically logged
```

### Issue: Search returns no results

**Diagnosis**:
```python
from a2a_fts import FTSClient

fts = FTSClient('project', 'agent')

# Check if FTS table exists
import sqlite3
conn = sqlite3.connect("~/.a2a/project/database.db")
cursor = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'"
)
if cursor.fetchone():
    print("✓ FTS table exists")
else:
    print("✗ FTS table not found")
```

**Solutions**:

1. **Initialize FTS**:
```python
fts = FTSClient('project', 'agent')
fts.init_fts_table()
print("✓ FTS table initialized")
```

2. **Check search query syntax**:
```python
# Test different query formats
test_queries = [
    'error',                    # Simple term
    '"critical error"',         # Phrase
    'error OR warning',         # Boolean OR
    '(database OR sql) AND error',  # Complex
    'error -timeout',           # Negation
]

for query in test_queries:
    results = fts.search_fts(query)
    print(f"'{query}': {len(results)} results")
```

3. **Re-index if necessary**:
```python
# Rebuild FTS index
fts.init_fts_table()  # Rebuilds if exists

# Or manually rebuild
import sqlite3
conn = sqlite3.connect("~/.a2a/project/database.db")
conn.execute("DROP TABLE IF EXISTS messages_fts")
conn.execute("""
    CREATE VIRTUAL TABLE messages_fts USING fts5(
        id, sender, recipient, body, thread_id, created_at,
        content=messages, content_rowid=id
    )
""")
conn.commit()
```

---

## Deployment Issues

### Issue: Cannot import a2a modules

```
ModuleNotFoundError: No module named 'a2a_client'
```

**Solutions**:

1. **Set PYTHONPATH**:
```bash
export PYTHONPATH=$PYTHONPATH:~/ai/a2a-skill
python3 script.py
```

2. **Add to path in code**:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / 'ai' / 'a2a-skill'))

from a2a_client import A2AClient
```

3. **Install in development mode**:
```bash
cd ~/ai/a2a-skill
pip install -e .
```

### Issue: Docker container fails to start

```
ConnectionRefusedError: [Errno 111] Connection refused
```

**Solutions**:

1. **Check database directory**:
```bash
docker exec a2a-server mkdir -p /root/.a2a
docker restart a2a-server
```

2. **Check logs**:
```bash
docker logs a2a-server
docker logs -f a2a-server  # Follow
```

3. **Verify mount**:
```bash
docker run -v ~/.a2a:/root/.a2a a2a:v1.3.0 \
  ls -la /root/.a2a
```

### Issue: Port already in use

```
Address already in use: ('0.0.0.0', 5000)
```

**Solutions**:

1. **Find process using port**:
```bash
lsof -i :5000
# or
netstat -tulpn | grep :5000
```

2. **Kill process**:
```bash
kill -9 <PID>
```

3. **Use different port**:
```bash
a2a_server.py --port 5001
```

---

## Getting Help

If your issue isn't listed here:

1. **Check logs**:
```bash
journalctl -u a2a -n 100
# or
docker logs a2a-server
```

2. **Check database integrity**:
```bash
sqlite3 ~/.a2a/your-project/database.db "PRAGMA integrity_check;"
```

3. **Run tests**:
```bash
python3 test_v13_features.py -v
```

4. **Read documentation**:
- OPERATIONS_GUIDE.md — Production deployment
- SECURITY_HARDENING.md — Security setup
- TESTING_V13.md — Testing procedures
- RELEASE_v1.3.0.md — Feature documentation

5. **Check git history**:
```bash
git log --oneline | head -20
git show <commit>
```

---

**Last Updated**: 2026-05-19
