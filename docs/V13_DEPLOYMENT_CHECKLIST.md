# v1.3.0 Deployment Checklist

Quick reference for deploying v1.3.0 to production.

## Pre-Deployment (1-2 hours before)

- [ ] **Review Release Notes** — Read RELEASE_v1.3.0.md
- [ ] **Review Security** — Understand encryption, audit logging implications
- [ ] **Test in Staging** — Run test_v13_features.py in staging environment
- [ ] **Backup Production Database** — `~/.a2a/*/database.db`
- [ ] **Notify Stakeholders** — Alert teams of deployment window
- [ ] **Prepare Rollback Plan** — Know how to revert if issues arise

## Deployment Steps (15 minutes)

### 1. Database Migration (1 minute)
```bash
# Initialize new v1.3 tables (non-destructive, safe to run multiple times)
python3 -c "
from a2a_priority import PriorityClient
from a2a_routing import RoutingClient
from a2a_audit import AuditClient
from a2a_fts import FTSClient

# Initialize priority column and index
priority = PriorityClient('your-project', 'setup')
priority.init_priority_table()

# Initialize routing rules table
routing = RoutingClient('your-project', 'setup')
routing.init_routing_table()

# Initialize audit logging
audit = AuditClient('your-project')
audit.init_audit_table()

# Initialize full-text search
fts = FTSClient('your-project', 'setup')
fts.init_fts_table()

print('✅ v1.3 tables initialized successfully')
"
```

### 2. Verify Installation (2 minutes)
```bash
# Check imports
python3 -c "
from a2a_crypto import CryptoClient
from a2a_fts import FTSClient
from a2a_audit import AuditClient
from a2a_priority import PriorityClient, Priority
from a2a_routing import RoutingClient, RoutingRule, RoutingAction
from a2a_priority_async import PriorityClientAsync
from a2a_routing_async import RoutingClientAsync
print('✅ All v1.3 modules imported successfully')
"

# Run quick tests
python3 test_v13_features.py 2>&1 | head -20
```

### 3. Generate Encryption Keys (3 minutes)
```bash
# For each agent that needs encryption, generate keypair
python3 -c "
from a2a_crypto import CryptoClient

for agent_id in ['alice', 'bob', 'charlie']:  # Your agent IDs
    crypto = CryptoClient('your-project', agent_id)
    public_key, private_key = crypto.generate_keypair()
    print(f'✅ Generated keypair for {agent_id}')
"

# Verify keys are stored in ~/.a2a/your-project/keys/
ls -la ~/.a2a/your-project/keys/
```

### 4. Configure Audit Logging (2 minutes)
```bash
# Optional: Set up audit log cleanup schedule
python3 -c "
from a2a_audit import AuditClient

audit = AuditClient('your-project')

# Test audit logging
audit.log_operation(
    agent_id='system',
    operation='deployment',
    details={'version': '1.3.0', 'timestamp': 'now'},
    result='success'
)

# Check it worked
stats = audit.get_audit_stats(days=1)
print(f'✅ Audit logging working: {stats}')
"
```

### 5. Test Core Features (5 minutes)
```bash
# Test encryption
python3 -c "
from a2a_crypto import CryptoClient
crypto = CryptoClient('your-project', 'test')
key = crypto.generate_symmetric_key()
encrypted = crypto.encrypt_message('Test', key)
decrypted = crypto.decrypt_message(encrypted, key)
assert decrypted == 'Test'
print('✅ Encryption working')
"

# Test full-text search
python3 -c "
from a2a_fts import FTSClient
fts = FTSClient('your-project', 'test')
results = fts.search_fts('test')
print(f'✅ Full-text search working ({len(results)} results)')
"

# Test prioritization
python3 -c "
from a2a_priority import PriorityClient, Priority
priority = PriorityClient('your-project', 'test')
stats = priority.get_priority_stats()
print(f'✅ Message prioritization working: {stats}')
"

# Test routing
python3 -c "
from a2a_routing import RoutingClient
routing = RoutingClient('your-project', 'test')
stats = routing.get_routing_stats()
print(f'✅ Message routing working: {stats}')
"
```

### 6. Deploy Code (1 minute)
```bash
# Update to latest version
git pull origin main

# Verify version
python3 -c "
import os
if os.path.exists('RELEASE_v1.3.0.md'):
    print('✅ v1.3.0 code deployed')
"
```

## Post-Deployment Verification (10 minutes)

### Health Checks
```bash
# Check database is accessible
python3 -c "
import sqlite3
from pathlib import Path
db = Path.home() / '.a2a' / 'your-project' / 'database.db'
conn = sqlite3.connect(str(db))
cursor = conn.cursor()
cursor.execute('SELECT name FROM sqlite_master WHERE type=\"table\"')
tables = cursor.fetchall()
print(f'✅ Database accessible with {len(tables)} tables')
"

# Verify new tables exist
python3 -c "
import sqlite3
from pathlib import Path
db = Path.home() / '.a2a' / 'your-project' / 'database.db'
conn = sqlite3.connect(str(db))
cursor = conn.cursor()

required_tables = ['messages', 'audit_log', 'routing_rules', 'messages_fts']
for table in required_tables:
    cursor.execute(f'SELECT COUNT(*) FROM {table}')
    count = cursor.fetchone()[0]
    print(f'✅ {table}: {count} rows')
"

# Check audit logs are being created
python3 -c "
from a2a_audit import AuditClient
audit = AuditClient('your-project')
stats = audit.get_audit_stats(days=1)
print(f'Audit stats: {stats}')
if stats['total_operations'] > 0:
    print('✅ Audit logging is active')
"
```

### Feature Smoke Tests
```bash
# Create test messages and verify features work end-to-end
python3 << 'PYTHON'
from a2a_priority import PriorityClient, Priority
from a2a_routing import RoutingClient, RoutingRule, RoutingAction
from a2a_audit import AuditClient

project = 'your-project'

# Test priority
priority = PriorityClient(project, 'test')
msg_id = priority.send('all', 'Test message', priority=Priority.HIGH)
print(f'✅ Sent priority message {msg_id}')

# Test routing rule
routing = RoutingClient(project, 'test')
routing.add_rule(RoutingRule(
    name='test_rule',
    action=RoutingAction.QUEUE,
    match_content='test'
))
print('✅ Created routing rule')

# Test audit
audit = AuditClient(project)
audit.log_operation('test', 'deployment_check', msg_id)
print('✅ Logged audit entry')

print('\n✅ All v1.3 features verified!')
PYTHON
```

### Team Communication
```bash
# Send deployment completion message
python3 << 'PYTHON'
from a2a_client import A2AClient

a2a = A2AClient('your-project', 'system')
a2a.send('all', '''
✅ v1.3.0 Deployment Complete!

New Features Available:
- 🔐 Message Encryption (symmetric & asymmetric)
- 🔍 Full-Text Search (FTS5)
- 📊 Audit Logging (compliance & debugging)
- 📈 Message Prioritization (4-level queue)
- 🚦 Message Routing (rule-based distribution)

Documentation: See RELEASE_v1.3.0.md and V13_QUICKREF.md
Questions? Check the feature guides in docs/

All changes are backward compatible. Existing code works unchanged.
''')

print('✅ Deployment announcement sent to all agents')
PYTHON
```

## Rollback Plan (if needed)

If critical issues occur and rollback is necessary:

```bash
# 1. Stop all agents
# (kill or restart services)

# 2. Restore database from backup
cp ~/.a2a/your-project/database.db.backup ~/.a2a/your-project/database.db

# 3. Revert code to v1.2
git checkout <v1.2-commit-hash>

# 4. Restart agents
# (restart services)

# 5. Notify team
python3 -c "
from a2a_client import A2AClient
a2a = A2AClient('your-project', 'system')
a2a.send('all', '⚠️ Rolled back to v1.2 due to issues. Investigating...')
"
```

## Monitoring Post-Deployment (24 hours)

### Daily Checks
- [ ] No error logs related to encryption/audit/routing/priority
- [ ] Message delivery latency within expected range
- [ ] Database size growth is normal
- [ ] Audit logs are being created
- [ ] Routing rules are functioning

### Weekly Checks
- [ ] Full-text search index is healthy
- [ ] Encryption operations are successful
- [ ] Priority queue is ordering correctly
- [ ] Audit log retention policy working (cleanup)
- [ ] Team is using new features effectively

### Commands for Monitoring
```bash
# Check audit logs
python3 -c "
from a2a_audit import AuditClient
audit = AuditClient('your-project')
stats = audit.get_audit_stats(days=1)
print(f'Yesterday operations: {stats}')
"

# Check FTS health
python3 -c "
from a2a_fts import FTSClient
fts = FTSClient('your-project', 'monitor')
stats = fts.get_search_stats()
print(f'FTS health: {stats}')
"

# Check routing rules
python3 -c "
from a2a_routing import RoutingClient
routing = RoutingClient('your-project', 'monitor')
stats = routing.get_routing_stats()
print(f'Routing rules: {stats}')
"
```

## Team Training (Schedule before deployment)

Before deploying v1.3.0, ensure teams understand:

1. **Encryption Basics** — When to use symmetric vs asymmetric (15 min)
   - See ENCRYPTION.md for examples

2. **Priority Queues** — How priority ordering affects message delivery (10 min)
   - See PRIORITY.md and V13_QUICKREF.md

3. **Message Routing** — Setting up rules for intelligent distribution (15 min)
   - See ROUTING.md for patterns

4. **Audit Logging** — Using audit trails for compliance (10 min)
   - See AUDIT.md for queries and export

5. **Full-Text Search** — Advanced message discovery (10 min)
   - See FTS_SEARCH.md for query syntax

## Success Criteria

✅ **Deployment is successful when:**

- [x] All v1.3 modules import without errors
- [x] Database tables initialized successfully
- [x] Encryption keys generated for all agents
- [x] Test suite passes (50+ tests)
- [x] Feature smoke tests all pass
- [x] Audit logs being created
- [x] Routing rules evaluating correctly
- [x] Team aware of new features
- [x] No new error logs in 1 hour post-deployment
- [x] Message latency within expected range

## Support

If issues arise:

1. **Check logs** — Review error messages in application logs
2. **Verify database** — Check database integrity: `sqlite3 database.db ".tables"`
3. **Run tests** — Execute test_v13_features.py to isolate issues
4. **Consult docs** — RELEASE_v1.3.0.md has troubleshooting
5. **Reach out** — See CONTRIBUTING.md for support channels

## Sign-Off

- **DevOps Lead**: __________________ Date: __________
- **Security Lead**: _________________ Date: __________
- **Product Manager**: ______________ Date: __________

---

**v1.3.0 Deployment Checklist**
Reference: RELEASE_v1.3.0.md
Last Updated: May 19, 2026
