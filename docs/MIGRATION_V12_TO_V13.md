# Migration Guide: v1.2 to v1.3

Step-by-step guide for upgrading existing a2a v1.2 deployments to v1.3.

## Overview

**Good news**: v1.3 is **100% backwards compatible** with v1.2.

- ✅ All v1.2 code continues to work unchanged
- ✅ Existing databases migrate automatically
- ✅ No downtime required (in-place upgrade)
- ✅ New features are opt-in

**Migration Path**:
1. Update code (pull/download v1.3)
2. Initialize new tables (one-time)
3. Start using new features (optional)

**Estimated Time**: 10-30 minutes depending on deployment size.

---

## Pre-Migration Checklist

- [ ] Review release notes: `docs/RELEASE_v1.3.0.md`
- [ ] Backup existing database: `~/.a2a/your-project/database.db`
- [ ] Plan rollback procedure (keep v1.2 available)
- [ ] Schedule migration (avoid peak usage)
- [ ] Notify users of brief changes
- [ ] Verify staging environment (if available)

---

## Step 1: Backup Database

**Important**: Always backup before upgrading.

```bash
# Create backup directory
mkdir -p ~/backups/a2a

# Backup database
cp ~/.a2a/your-project/database.db ~/backups/a2a/database_v12_backup.db

# Verify backup
sqlite3 ~/backups/a2a/database_v12_backup.db "SELECT COUNT(*) FROM messages;"
```

**Remote backup** (recommended):
```bash
# Encrypt and upload to S3
sqlite3 ~/.a2a/your-project/database.db ".backup /tmp/db.bak" && \
  gpg --symmetric --cipher-algo AES256 /tmp/db.bak && \
  aws s3 cp /tmp/db.bak.gpg s3://backups/a2a/database_v12_$(date +%Y%m%d).bak.gpg && \
  rm /tmp/db.bak /tmp/db.bak.gpg
```

---

## Step 2: Update Code

### Option A: Git (recommended)

```bash
cd ~/ai/a2a-skill
git fetch origin
git checkout main  # or v1.3.0 tag
git pull
```

### Option B: Download Release

```bash
# Download v1.3.0 release
cd ~/ai/a2a-skill
git tag -l | grep v1.3.0
git checkout v1.3.0
```

### Option C: Docker

```bash
# Update image
docker pull a2a:v1.3.0

# Or rebuild
docker build -t a2a:v1.3.0 .

# Update docker-compose.yml or K8s manifest
# Set image: a2a:v1.3.0
```

---

## Step 3: Initialize v1.3 Tables

Run this **once** to add new tables and columns:

```python
#!/usr/bin/env python3
"""Initialize v1.3 tables (safe to run multiple times)."""

from a2a_priority import PriorityClient
from a2a_routing import RoutingClient
from a2a_audit import AuditClient
from a2a_fts import FTSClient

PROJECT = 'your-project'

print("Initializing v1.3 tables...")

# 1. Priority column and index
priority = PriorityClient(PROJECT, 'migration')
priority.init_priority_table()
print("✓ Priority table initialized")

# 2. Routing rules table
routing = RoutingClient(PROJECT, 'migration')
routing.init_routing_table()
print("✓ Routing table initialized")

# 3. Audit logging table
audit = AuditClient(PROJECT)
audit.init_audit_table()
print("✓ Audit table initialized")

# 4. Full-text search index
fts = FTSClient(PROJECT, 'migration')
fts.init_fts_table()
print("✓ FTS table initialized")

print("\n✅ v1.3 migration complete!")
```

**Run**:
```bash
python3 migrate_to_v13.py
```

### What This Does

- **Priority column**: Adds `priority INTEGER DEFAULT 2` to messages table
- **Routing rules**: Creates new `routing_rules` table for persistent rules
- **Audit log**: Creates `audit_log` table for operation tracking
- **FTS index**: Creates virtual table `messages_fts` for full-text search

**Safety**: All operations are idempotent (safe to run multiple times).

---

## Step 4: Verify Migration

Check that migration was successful:

```bash
# 1. Verify database integrity
sqlite3 ~/.a2a/your-project/database.db "PRAGMA integrity_check;"
# Should print: ok

# 2. Check new tables exist
sqlite3 ~/.a2a/your-project/database.db "
  SELECT name FROM sqlite_master 
  WHERE type='table' 
  ORDER BY name;
"
# Should include: messages, audit_log, routing_rules, messages_fts (virtual)

# 3. Check priority column exists
sqlite3 ~/.a2a/your-project/database.db "
  SELECT sql FROM sqlite_master 
  WHERE type='table' AND name='messages';
"
# Should show priority column

# 4. Check message count unchanged
sqlite3 ~/.a2a/your-project/database.db "
  SELECT COUNT(*) FROM messages;
"
# Should match pre-migration count
```

**Python verification**:
```python
from a2a_client import A2AClient
from a2a_priority import PriorityClient
from a2a_audit import AuditClient
from a2a_fts import FTSClient

project = 'your-project'

# Test v1.3 features work
try:
    # Test send/receive
    client = A2AClient(project, 'test-agent')
    msg_id = client.send('other', 'test')
    print(f"✓ Basic send/recv: {msg_id}")
    
    # Test priority
    priority = PriorityClient(project, 'test-agent')
    messages = priority.recv(wait=1)
    print(f"✓ Priority recv: {len(messages)} messages")
    
    # Test audit
    audit = AuditClient(project)
    stats = audit.get_audit_stats()
    print(f"✓ Audit logging: {stats.get('total_operations', 0)} operations")
    
    # Test FTS
    fts = FTSClient(project, 'test-agent')
    results = fts.search_fts('test')
    print(f"✓ Full-text search: {len(results)} results")
    
    print("\n✅ All v1.3 features working!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    raise
```

---

## Step 5: Start Using v1.3 Features

Now you can use new features. They're **opt-in** — existing code works unchanged.

### Example: Add Encryption

```python
from a2a_crypto import CryptoClient
from a2a_client import A2AClient

# Generate keypairs (one-time setup per agent)
crypto = CryptoClient('your-project', 'agent-1')
crypto.generate_keypair()

# Send encrypted message
crypto2 = CryptoClient('your-project', 'agent-2')
agent2_public_key = crypto2.get_public_key()

encrypted = crypto.wrap_encrypted_message('secret', agent2_public_key)
a2a = A2AClient('your-project', 'agent-1')
a2a.send('agent-2', encrypted)

# Receive and decrypt
messages = a2a.recv()
decrypted = crypto2.decrypt_message(messages[0]['body'])
```

### Example: Use Priority Queue

```python
from a2a_priority import PriorityClient, Priority

priority = PriorityClient('your-project', 'agent')

# Send with priority
priority.send('other', 'Urgent alert!', priority=Priority.CRITICAL)
priority.send('other', 'FYI message', priority=Priority.LOW)

# Receive ordered by priority (CRITICAL first)
messages = priority.recv(wait=5, priority_aware=True)
for msg in messages:
    print(f"[{msg['priority']}] {msg['body']}")
```

### Example: Set Up Routing Rules

```python
from a2a_routing import RoutingClient, RoutingRule, RoutingAction
from a2a_priority import Priority

routing = RoutingClient('your-project', 'agent')

# Route critical messages to on-call
routing.add_rule(RoutingRule(
    name='critical_to_oncall',
    action=RoutingAction.FORWARD,
    match_priority=Priority.CRITICAL,
    forward_to='oncall-engineer'
))

# Route errors to support
routing.add_rule(RoutingRule(
    name='errors_to_support',
    action=RoutingAction.FORWARD,
    match_content='error',
    forward_to='support-team'
))

# Use routing
routed = routing.recv_with_routing(wait=5)
routing.apply_routing(routed)
```

### Example: Enable Audit Logging

```python
from a2a_audit import AuditClient, AuditContextManager

audit = AuditClient('your-project')

# Log operations automatically
with AuditContextManager(audit, 'agent-1', 'send_message') as ctx:
    msg_id = a2a.send('agent-2', 'Hello')
    ctx.details = {'recipient': 'agent-2', 'msg_id': msg_id}
    # Auto-logged to audit_log table

# Query audit trail
trail = audit.get_agent_audit_trail('agent-1', days=7)
print(f"Last 7 days: {len(trail['operations'])} operations")

# Export for compliance
audit.export_audit_log('audit_export.json', days=30)
```

### Example: Full-Text Search

```python
from a2a_fts import FTSClient

fts = FTSClient('your-project', 'agent')

# Search with boolean operators
results = fts.search_fts('error AND database', limit=50)
print(f"Found {len(results)} messages")

# Phrase search
results = fts.search_fts('"authentication failed"')

# Prefix matching
results = fts.search_fts('error*')
```

---

## Step 6: Configure for Production

### Enable Audit Logging

```python
# All operations automatically logged with AuditContextManager
# See examples above
```

### Set Up Backup Schedule

```bash
# Daily encrypted backup (add to crontab)
0 2 * * * /opt/a2a/backup.sh

# See OPERATIONS_GUIDE.md for complete backup script
```

### Configure Monitoring

```bash
# Health check endpoint
curl http://localhost:8080/health

# Metrics (v1.4+)
curl http://localhost:9090/metrics

# See OPERATIONS_GUIDE.md for monitoring setup
```

### Apply Security Hardening

```python
# Run security setup
from pathlib import Path
import os

# Restrict database permissions
db = Path.home() / '.a2a' / 'your-project' / 'database.db'
os.chmod(db, 0o600)  # -rw-------

# See SECURITY_HARDENING.md for complete setup
```

---

## Rollback Procedure (If Needed)

If you encounter issues during migration:

```bash
# 1. Stop service
sudo systemctl stop a2a

# 2. Restore backup
cp ~/backups/a2a/database_v12_backup.db ~/.a2a/your-project/database.db

# 3. Revert code
cd ~/ai/a2a-skill
git checkout v1.2  # or previous version tag

# 4. Restart service
sudo systemctl start a2a

# 5. Verify
./a2a send test "Rolled back to v1.2" --from system
```

---

## Troubleshooting

### Issue: "no such column: priority"

```
sqlite3.OperationalError: no such column: priority
```

**Solution**: Migration wasn't run. Execute Step 3 above.

### Issue: "no such table: routing_rules"

```
sqlite3.OperationalError: no such table: routing_rules
```

**Solution**: Run `routing.init_routing_table()` to create the table.

### Issue: FTS search returns no results

```
fts.search_fts('test') returns []
```

**Solution**: Run `fts.init_fts_table()` to build the FTS index.

### Issue: Database file size increased significantly

**Normal behavior**: New tables and indices use disk space.

**Options**:
- Ignore (only ~10-20% increase for typical usage)
- Archive old messages (see OPERATIONS_GUIDE.md)
- Accept larger database as cost of new features

---

## Performance Impact

**Before v1.3** (typical):
- Send latency: 15-20ms
- Receive latency: 50-100ms
- Database size: 100MB-1GB

**After v1.3** (same):
- Send latency: 15-20ms (unchanged)
- Receive latency: 50-100ms (unchanged)
- Database size: 110MB-1.1GB (+10% for indices)

**With new features enabled** (optional):
- Encrypted send: 25-50ms (10-50ms for RSA)
- Priority ordering: +5ms
- Audit logging: +2ms
- FTS search: 5-20ms (new feature)

---

## Migration Checklist

- [ ] Reviewed release notes
- [ ] Created database backup
- [ ] Backed up to remote storage
- [ ] Updated code to v1.3
- [ ] Ran initialization script
- [ ] Verified migration succeeded
- [ ] Tested v1.3 features
- [ ] Updated deployment config (if needed)
- [ ] Configured backups
- [ ] Enabled monitoring
- [ ] Applied security hardening
- [ ] Notified team of changes
- [ ] Documented any customizations

---

## Next Steps

1. **Read quick reference**: `docs/V13_QUICKREF.md` (5 min)
2. **Review features**: `docs/ENCRYPTION.md`, `docs/PRIORITY.md`, `docs/ROUTING.md`
3. **Set up security**: Follow `docs/SECURITY_HARDENING.md`
4. **Configure ops**: Review `docs/OPERATIONS_GUIDE.md`
5. **Plan v1.4**: See `docs/V14_ARCHITECTURE.md` for roadmap

---

## Support

- **Issues**: Check `docs/TROUBLESHOOTING.md`
- **Questions**: See `docs/CONTRIBUTING.md` for support channels
- **Rollback**: See "Rollback Procedure" above
- **Detailed Guides**: See docs/ directory

---

**v1.3.0 Migration Guide**  
Last Updated: 2026-05-19  
Status: Production-Ready
