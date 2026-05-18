# a2a Security Hardening Guide

Complete guide for securing a2a deployments in production.

## Table of Contents
1. [Encryption Setup](#encryption-setup)
2. [Key Management](#key-management)
3. [Access Control](#access-control)
4. [Network Security](#network-security)
5. [Database Security](#database-security)
6. [Audit & Logging](#audit--logging)
7. [Compliance](#compliance)
8. [Security Checklist](#security-checklist)

---

## Encryption Setup

### Symmetric Encryption (Shared Key)

**Use Case**: Small teams with secure key distribution (internal communication).

**Setup**:
```python
from a2a_crypto import CryptoClient

crypto = CryptoClient('secure-project', 'team-agent')

# Generate and use shared key
key = crypto.generate_symmetric_key()

# Encrypt message
message = "Team meeting agenda: budget review"
encrypted = crypto.encrypt_message(message, key)

# Distribute key securely (not in code!)
# Options:
#  - Use environment variable: $TEAM_ENCRYPTION_KEY
#  - Use secrets management: HashiCorp Vault, AWS Secrets Manager
#  - Use HSM (Hardware Security Module)
```

**Security Properties**:
- ✅ Fast encryption/decryption (< 1ms)
- ✅ Small key size (256 bits)
- ✅ Standard algorithm (Fernet/AES-128-CBC + HMAC)
- ⚠️ Requires secure key distribution
- ⚠️ Key compromise affects all messages

### Asymmetric Encryption (Public/Private Keys)

**Use Case**: Large teams without shared key (each agent has unique keypair).

**Setup**:
```python
from a2a_crypto import CryptoClient

# Each agent generates their keypair
alice_crypto = CryptoClient('secure-project', 'alice')
alice_pub, alice_priv = alice_crypto.generate_keypair()

bob_crypto = CryptoClient('secure-project', 'bob')
bob_pub, bob_priv = bob_crypto.generate_keypair()

# Alice encrypts message for Bob using Bob's public key
message = "Incident report: data loss on prod-db-2"
encrypted = alice_crypto.wrap_encrypted_message(message, bob_pub)

# Bob decrypts using his private key
decrypted = bob_crypto.decrypt_message(encrypted)
assert decrypted == message
```

**Security Properties**:
- ✅ No shared key needed
- ✅ Scales to many agents
- ✅ Each compromised key affects only that agent
- ⚠️ Slower (10-50ms per operation)
- ⚠️ Larger keys (2048 bits)

**Generate Keys for All Agents**:
```python
from a2a_crypto import CryptoClient

agents = ['alice', 'bob', 'charlie', 'security-lead', 'oncall']
project = 'secure-project'

for agent_id in agents:
    crypto = CryptoClient(project, agent_id)
    if not crypto.public_key_path.exists():
        public_key, private_key = crypto.generate_keypair()
        print(f"✓ Generated keypair for {agent_id}")
```

---

## Key Management

### Key Storage

**Recommended**:
```
~/.a2a/project-name/keys/
├── agent-id_public.pem          # Public key (shareable)
└── agent-id_private.pem         # Private key (KEEP SECURE)
```

**File Permissions**:
```bash
# Private keys must be readable only by owner
chmod 600 ~/.a2a/project-name/keys/*_private.pem

# Public keys can be shared
chmod 644 ~/.a2a/project-name/keys/*_public.pem
```

**Verify Permissions**:
```bash
# Check that private keys are protected
stat -c '%A %n' ~/.a2a/project-name/keys/*

# Should show: -rw------- ... *_private.pem
```

### Key Backup

**Secure Backup**:
```bash
#!/bin/bash
# Backup encryption keys to encrypted archive

BACKUP_DIR="/secure/backup/a2a-keys"
PROJECT="secure-project"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Create backup
tar czf /tmp/keys_$DATE.tar.gz ~/.a2a/$PROJECT/keys/

# Encrypt backup
gpg --symmetric \
    --cipher-algo AES256 \
    --output $BACKUP_DIR/keys_$DATE.tar.gz.gpg \
    /tmp/keys_$DATE.tar.gz

# Delete unencrypted backup
rm /tmp/keys_$DATE.tar.gz

# Verify backup
gpg --decrypt $BACKUP_DIR/keys_$DATE.tar.gz.gpg | tar tzf - > /dev/null

echo "✓ Keys backed up to $BACKUP_DIR/keys_$DATE.tar.gz.gpg"
```

### Key Rotation

**Rotate Compromised Keys**:
```python
from a2a_crypto import CryptoClient

crypto = CryptoClient('secure-project', 'alice')

# Generate new keypair
new_pub, new_priv = crypto.generate_keypair(force=True)

# Announce new key to all peers
message = json.dumps({
    'type': 'key_update',
    'agent_id': 'alice',
    'new_public_key': new_pub,
    'timestamp': datetime.now().isoformat(),
    'reason': 'Routine rotation'
})

# Broadcast to all agents
a2a = A2AClient('secure-project', 'alice')
a2a.send('all', message)

print("✓ New keypair generated and announced")
print("✓ Old key can be safely deleted after rotation confirmed by all peers")
```

---

## Access Control

### Agent Authentication

**By Convention** (not cryptographic):
- Each agent has a unique `agent_id`
- Agent identifies itself in messages via `sender` field
- No authentication protocol (assumes trusted network)

**For Untrusted Networks**: Use JWT or TLS client certs (v1.4+).

### Role-Based Access Control (RBAC)

**Define Roles**:
```python
ROLES = {
    'admin': {
        'can_create_rules': True,
        'can_delete_messages': True,
        'can_export_audit': True,
    },
    'dev': {
        'can_create_rules': True,
        'can_delete_messages': False,
        'can_export_audit': False,
    },
    'viewer': {
        'can_create_rules': False,
        'can_delete_messages': False,
        'can_export_audit': False,
    },
}
```

**Enforce in Routing**:
```python
from a2a_routing import RoutingClient, RoutingRule, RoutingAction

routing = RoutingClient('secure-project', 'admin-agent')

# Only admins can delete
routing.add_rule(RoutingRule(
    name='admin_only_delete',
    action=RoutingAction.DISCARD,  # Reject non-admin delete requests
    match_content='DELETE.*',
    match_sender='(?!admin-.*)',  # Negative lookahead: not admin-*
))
```

### Database File Permissions

**Restrict Database Access**:
```bash
# Database file should only be readable/writable by service user
chmod 600 ~/.a2a/project-name/database.db
chmod 600 ~/.a2a/project-name/database.db-wal
chmod 600 ~/.a2a/project-name/database.db-shm

# Directory permissions
chmod 700 ~/.a2a/project-name/

# Service should run as dedicated user
chown -R a2a:a2a ~/.a2a/project-name/
```

---

## Network Security

### Local SQLite (v1.3)

**Current Architecture**: SQLite file-based, no network.

**Security**: 
- ✅ No network exposure
- ✅ Local file permissions sufficient
- ✅ No authentication needed

### Network API (v1.4+)

**gRPC API** (planned):
```
Recommended Security:
- TLS 1.3 for transport security
- mTLS (mutual TLS) for client authentication
- Rate limiting to prevent DoS
- API key or JWT tokens
```

**WebSocket API** (planned):
```
Recommended Security:
- WSS (WebSocket Secure / TLS)
- JWT authentication
- Connection rate limiting
- Message size limits
```

### Firewall Rules

**Single-Instance Deployment**:
```bash
# Block external access to a2a ports
sudo ufw default deny incoming
sudo ufw allow ssh
sudo ufw allow 22/tcp
# a2a runs locally, no external ports needed
```

**Multi-Instance Deployment** (v2.0+):
```bash
# gRPC API port (5000) — internal only
sudo ufw allow from 10.0.0.0/8 to any port 5000

# Metrics port (9090) — restricted
sudo ufw allow from 10.0.1.0/24 to any port 9090

# WebSocket (8000) — through load balancer
# Don't expose directly; use reverse proxy
```

---

## Database Security

### SQL Injection Prevention

**Parameterized Queries** (already implemented):
```python
# ✅ Safe — SQLite parameter binding
conn.execute(
    "INSERT INTO messages(sender, body) VALUES(?, ?)",
    (sender, body)  # Parameters bound safely
)

# ❌ Unsafe — string concatenation (never do this)
query = f"INSERT INTO messages VALUES('{sender}', '{body}')"  # SQL injection!
```

### Encryption at Rest

**SQLite Encryption Extensions** (future consideration for v1.5+):

```python
# Not currently used, but available for future:
# - SQLCipher (encrypted SQLite)
# - Built-in encryption pragma (if available)
```

**Alternative: Filesystem Encryption**:
```bash
# Enable encryption for .a2a directory
sudo cryptsetup create --type luks a2a-crypt /dev/sdX
sudo mount /dev/mapper/a2a-crypt ~/.a2a

# Database is now encrypted at rest
```

### Backup Encryption

**Always encrypt backups**:
```bash
# ✅ Encrypted backup
sqlite3 database.db ".backup backup.db" && \
  gpg --symmetric backup.db

# ❌ Unencrypted backup (avoid)
# cp database.db database.db.backup
```

---

## Audit & Logging

### Audit Logging

**Log All Operations** (v1.3):
```python
from a2a_audit import AuditClient, AuditContextManager

audit = AuditClient('secure-project')
audit.init_audit_table()

# All operations logged automatically
with AuditContextManager(audit, 'alice', 'send_encrypted') as ctx:
    # Send sensitive message
    msg_id = a2a.send('bob', encrypted_message)
    ctx.details = {'recipient': 'bob', 'msg_id': msg_id}
    # Automatically logged to audit_log table
```

**Query Audit Logs**:
```python
# Get all operations by an agent
trail = audit.get_agent_audit_trail('alice', days=30)

# Get operations of a specific type
ops = audit.query_audit_log(
    operation='send_encrypted',
    days=7
)

# Get failed operations
failures = audit.query_audit_log(
    result='failure',
    days=1
)
```

### Security Logging

**Log Security Events**:
```python
audit.log_operation(
    agent_id='alice',
    operation='key_rotation',
    details={
        'old_key_hash': hash_key(old_key),
        'new_key_hash': hash_key(new_key),
        'reason': 'Routine rotation',
    },
    result='success'
)

audit.log_operation(
    agent_id='eve',
    operation='decrypt_failed',
    details={
        'error': 'Invalid authentication tag',
        'sender': 'alice',
    },
    result='failure'
)
```

### Export for SIEM Integration

**Export Audit Logs**:
```python
# Export to JSON for external SIEM
audit.export_audit_log('audit_export.json', days=30)

# SIEM can then ingest:
# - Splunk
# - ELK Stack
# - Sumologic
# - Datadog
```

---

## Compliance

### GDPR Compliance

**Data Minimization**:
- Only store necessary messages
- Archive/delete old messages regularly
- Limit audit log retention (30-90 days)

**Data Export**:
```python
# User can request export of their data
audit.export_audit_log(filename, agent_id='alice', days=365)

# User can request deletion
# Run archival and deletion process
```

### HIPAA Compliance

**Required for Healthcare**:
- ✅ Encryption (symmetric or asymmetric)
- ✅ Audit logging of all access
- ✅ Access controls with RBAC
- ✅ Regular backups with encryption
- ❓ Need additional controls:
  - Integrity verification (digital signatures) — v1.4+
  - User authentication — v1.4+
  - Session management — v1.4+

### SOC 2 Compliance

**Required Controls**:
- ✅ Encryption in transit and at rest
- ✅ Access control and authentication
- ✅ Audit logging and monitoring
- ✅ Backup and disaster recovery
- ✅ Incident response procedures
- ❓ Additional needed:
  - Penetration testing — user responsibility
  - Security training — user responsibility
  - Incident response plan — user responsibility

### PCI DSS Compliance

**Not Required** (unless processing payment cards):
- a2a doesn't handle payment data
- If used with payment data, apply standard PCI DSS controls

---

## Security Checklist

### Pre-Deployment

- [ ] Generate keypairs for all agents
- [ ] Backup keys encrypted with GPG
- [ ] Set file permissions (600 for private keys)
- [ ] Database file permissions (600)
- [ ] Database directory permissions (700)
- [ ] Review encryption algorithm (Fernet/RSA)
- [ ] Plan key rotation schedule
- [ ] Create incident response plan
- [ ] Document RBAC roles
- [ ] Set up audit log retention policy
- [ ] Plan for compliance (GDPR/HIPAA/SOC2)

### Deployment

- [ ] Run with least privilege (dedicated user)
- [ ] Enable SELinux or AppArmor if available
- [ ] Configure firewall rules (deny all, allow specific)
- [ ] Enable disk encryption (if available)
- [ ] Verify TLS 1.3 (for v1.4+ gRPC)
- [ ] Configure mTLS (for v1.4+ if needed)
- [ ] Set up monitoring and alerting
- [ ] Configure backup encryption
- [ ] Test disaster recovery
- [ ] Document security procedures

### Ongoing

- [ ] Review audit logs weekly
- [ ] Rotate keys annually (or after compromise)
- [ ] Test backups monthly
- [ ] Run security scans quarterly
- [ ] Update dependencies for security patches
- [ ] Monitor for suspicious activity
- [ ] Track encryption/decryption failures
- [ ] Audit rule changes
- [ ] Review access patterns

### Incident Response

- [ ] Key compromise: rotate immediately
- [ ] Unauthorized access: check audit logs
- [ ] Message tampering: verify signatures (v1.4+)
- [ ] DoS attack: enable rate limiting
- [ ] Data breach: export audit trail for investigation

---

## Security Best Practices

### 1. Defense in Depth

Use multiple layers:
- Encryption (messages)
- Access control (RBAC)
- Audit logging (compliance)
- Network controls (firewall)
- File permissions (OS)

### 2. Least Privilege

- Run as dedicated user (not root)
- Grant minimum necessary permissions
- Use RBAC for message operations
- Restrict audit log access

### 3. Key Hygiene

- Generate keys once, use many times
- Never share private keys
- Rotate keys regularly
- Backup encrypted keys
- Use HSM for high-security deployments

### 4. Audit Everything

- Log all send/recv operations
- Log encryption/decryption events
- Log access to sensitive data
- Monitor for suspicious patterns
- Export logs regularly

### 5. Secure by Default

- Encryption recommended (not optional)
- Audit logging enabled
- WAL mode for concurrency safety
- File permissions restrictive
- RBAC roles defined

---

## Example: Securing a Deployment

```python
#!/usr/bin/env python3
"""
Complete security setup for a2a deployment.
"""

import os
import subprocess
from pathlib import Path
from a2a_crypto import CryptoClient
from a2a_audit import AuditClient
from a2a_routing import RoutingClient, RoutingRule, RoutingAction
from a2a_priority import Priority

def setup_secure_deployment(project: str, agents: list):
    """Setup secure a2a deployment."""
    
    print(f"Setting up secure deployment for {project}...")
    
    # 1. Create directory with restricted permissions
    a2a_dir = Path.home() / ".a2a" / project
    a2a_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. Set restrictive permissions
    os.chmod(a2a_dir, 0o700)  # drwx------
    
    # 3. Generate keypairs for all agents
    print("Generating keypairs...")
    for agent_id in agents:
        crypto = CryptoClient(project, agent_id)
        if not crypto.public_key_path.exists():
            crypto.generate_keypair()
            print(f"  ✓ {agent_id}")
        
        # Set key file permissions
        os.chmod(crypto.private_key_path, 0o600)  # -rw-------
        os.chmod(crypto.public_key_path, 0o644)   # -rw-r--r--
    
    # 4. Setup audit logging
    print("Configuring audit logging...")
    audit = AuditClient(project)
    audit.init_audit_table()
    
    # 5. Setup routing rules
    print("Setting up routing rules...")
    routing = RoutingClient(project, 'admin')
    routing.init_routing_table()
    
    # Security rule: escalate critical to security team
    routing.add_rule(RoutingRule(
        name='security_escalate',
        action=RoutingAction.ESCALATE,
        match_priority=Priority.CRITICAL,
        forward_to='security-team'
    ))
    
    # 6. Backup keys
    print("Backing up keys...")
    backup_dir = Path("/secure/backup/a2a")
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    subprocess.run([
        'bash', '-c',
        f'tar czf /tmp/keys.tar.gz ~/.a2a/{project}/keys/ && '
        f'gpg --symmetric --cipher-algo AES256 '
        f'--output {backup_dir}/keys_$(date +%Y%m%d).tar.gz.gpg '
        f'/tmp/keys.tar.gz && rm /tmp/keys.tar.gz'
    ], check=True)
    
    print(f"✓ Keys backed up to {backup_dir}")
    
    # 7. Verify setup
    print("\nVerifying setup...")
    print(f"  ✓ Project directory: {a2a_dir}")
    print(f"  ✓ Keys generated for: {', '.join(agents)}")
    print(f"  ✓ Audit logging enabled")
    print(f"  ✓ Routing rules configured")
    print(f"  ✓ Keys backed up")
    
    print("\n✅ Secure deployment setup complete!")

if __name__ == '__main__':
    setup_secure_deployment(
        'production-project',
        ['alice', 'bob', 'security-team', 'oncall']
    )
```

---

**Last Updated**: 2026-05-19  
**Applies to**: v1.3.0 and later
