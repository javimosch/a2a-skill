# a2a Operations Guide

Comprehensive guide for operating a2a messaging infrastructure in production.

## Table of Contents
1. [Deployment & Infrastructure](#deployment--infrastructure)
2. [Monitoring & Alerting](#monitoring--alerting)
3. [Backup & Recovery](#backup--recovery)
4. [Troubleshooting](#troubleshooting)
5. [Performance Tuning](#performance-tuning)
6. [Security Operations](#security-operations)

---

## Deployment & Infrastructure

### System Requirements

**Minimum (dev/test)**:
- CPU: 2 cores
- RAM: 512 MB
- Disk: 1 GB
- Python: 3.10+
- SQLite: 3.35+

**Recommended (production)**:
- CPU: 4+ cores
- RAM: 2+ GB
- Disk: 10+ GB (depends on message volume)
- Python: 3.12 (latest stable)
- SQLite: 3.40+ (WAL mode optimizations)
- OS: Linux (Ubuntu 22.04 LTS) or macOS

### Docker Deployment

**Dockerfile** (save as `Dockerfile`):
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY a2a*.py a2a_server.py ./

# Create .a2a directory for databases
RUN mkdir -p /root/.a2a

# Expose ports
EXPOSE 5000 8080 9090

# Run server
CMD ["python3", "a2a_server.py", "--host", "0.0.0.0", "--port", "5000"]
```

**requirements.txt**:
```
aiosqlite==0.19.0
cryptography==41.0.7
```

**Build and run**:
```bash
# Build image
docker build -t a2a:v1.3.0 .

# Run container
docker run -d \
  -p 5000:5000 \
  -p 8080:8080 \
  -p 9090:9090 \
  -v ~/.a2a:/root/.a2a \
  --name a2a-server \
  a2a:v1.3.0
```

### Kubernetes Deployment

**deployment.yaml**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: a2a-server
  namespace: default
spec:
  replicas: 1  # v1.3 single-instance; multi-instance in v2.0
  selector:
    matchLabels:
      app: a2a-server
  template:
    metadata:
      labels:
        app: a2a-server
    spec:
      containers:
      - name: a2a-server
        image: a2a:v1.3.0
        ports:
        - containerPort: 5000
          name: grpc
        - containerPort: 8080
          name: http
        - containerPort: 9090
          name: metrics
        
        # Liveness check
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 30
        
        # Readiness check
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
        
        # Resource limits
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 1Gi
        
        # Volume for persistent database
        volumeMounts:
        - name: a2a-data
          mountPath: /root/.a2a
      
      volumes:
      - name: a2a-data
        persistentVolumeClaim:
          claimName: a2a-pvc

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: a2a-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
```

**Deploy**:
```bash
kubectl apply -f deployment.yaml
```

### Systemd Service

**Save as** `/etc/systemd/system/a2a.service`:
```ini
[Unit]
Description=a2a Messaging Server
After=network.target

[Service]
Type=simple
User=a2a
WorkingDirectory=/opt/a2a
ExecStart=/usr/bin/python3 /opt/a2a/a2a_server.py
Restart=on-failure
RestartSec=5

# Logging
StandardOutput=journal
StandardError=journal

# Security
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

**Enable and start**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable a2a
sudo systemctl start a2a
sudo systemctl status a2a
```

---

## Monitoring & Alerting

### Health Checks

**Endpoint**: `GET /health`
```bash
curl http://localhost:8080/health
# Response: {"status": "ok"}
```

**Script to monitor**:
```python
#!/usr/bin/env python3
import urllib.request
import json
import time

def health_check():
    try:
        response = urllib.request.urlopen('http://localhost:8080/health', timeout=5)
        data = json.loads(response.read())
        return data.get('status') == 'ok'
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

# Retry with backoff
backoff = 1
while not health_check():
    print(f"Waiting {backoff}s before retry...")
    time.sleep(backoff)
    backoff = min(backoff * 2, 60)
```

### Key Metrics to Monitor

**Database Health**:
```bash
# Check database file size
du -sh ~/.a2a/*/database.db

# Check database integrity
sqlite3 ~/.a2a/your-project/database.db "PRAGMA integrity_check;"

# Monitor WAL file growth
ls -lh ~/.a2a/*/database.db-wal
```

**Message Flow**:
```bash
# Message count
python3 -c "
import sqlite3
db = sqlite3.connect('~/.a2a/your-project/database.db')
c = db.cursor()
c.execute('SELECT COUNT(*) FROM messages')
print(f'Total messages: {c.fetchone()[0]}')
"

# Messages per agent
python3 -c "
import sqlite3
db = sqlite3.connect('~/.a2a/your-project/database.db')
c = db.cursor()
c.execute('SELECT sender, COUNT(*) FROM messages GROUP BY sender')
for row in c.fetchall():
    print(f'{row[0]}: {row[1]} messages')
"

# Unread message count
python3 -c "
import sqlite3
db = sqlite3.connect('~/.a2a/your-project/database.db')
c = db.cursor()
c.execute('''
  SELECT m.recipient, COUNT(*) 
  FROM messages m
  WHERE NOT EXISTS (SELECT 1 FROM reads r WHERE r.message_id = m.id)
  GROUP BY m.recipient
''')
for row in c.fetchall():
    print(f'{row[0]}: {row[1]} unread')
"
```

**Performance Metrics**:
```python
# Measure send/recv latency
import time
import a2a_client

client = a2a_client.A2AClient('test-project', 'perf-test')

# Measure send
start = time.time()
msg_id = client.send('agent-2', 'test message')
send_latency = (time.time() - start) * 1000
print(f"Send latency: {send_latency:.2f}ms")

# Measure recv
start = time.time()
messages = client.recv(wait=5)
recv_latency = (time.time() - start) * 1000
print(f"Recv latency: {recv_latency:.2f}ms (got {len(messages)} msgs)")
```

### Prometheus Integration (v1.4+)

**Metrics endpoint**: `GET /metrics`
```bash
curl http://localhost:9090/metrics
```

**Prometheus config** (`prometheus.yml`):
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'a2a'
    static_configs:
      - targets: ['localhost:9090']
```

**Alert rules** (`alerts.yml`):
```yaml
groups:
- name: a2a_alerts
  interval: 30s
  rules:
  - alert: A2AHighMessageLatency
    expr: a2a_message_latency_ms{quantile="0.99"} > 50
    for: 5m
    annotations:
      summary: "a2a message latency high ({{ $value }}ms)"

  - alert: A2ADatabaseGrowth
    expr: rate(sqlite_database_size_bytes[1h]) > 1000000
    for: 10m
    annotations:
      summary: "a2a database growing rapidly"

  - alert: A2AHighErrorRate
    expr: rate(a2a_errors_total[5m]) > 0.01
    for: 2m
    annotations:
      summary: "a2a error rate > 1%"
```

---

## Backup & Recovery

### Backup Strategy

**Database backup** (manual):
```bash
# Create backup directory
mkdir -p backups

# Backup database
cp ~/.a2a/your-project/database.db backups/database.db.$(date +%Y%m%d_%H%M%S)

# Backup with SQLite backup command (safer while running)
sqlite3 ~/.a2a/your-project/database.db ".backup backups/database.backup"
```

**Automated backup** (daily via cron):
```bash
# Save as /opt/a2a/backup.sh
#!/bin/bash
BACKUP_DIR="/var/backups/a2a"
DB_PATH="$HOME/.a2a/your-project/database.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
sqlite3 $DB_PATH ".backup $BACKUP_DIR/database_$TIMESTAMP.db"

# Keep only 7 days of backups
find $BACKUP_DIR -name "database_*.db" -mtime +7 -delete

# Log backup
echo "$(date): Backup completed" >> $BACKUP_DIR/backup.log
```

**Add to crontab**:
```bash
# Backup daily at 2 AM
0 2 * * * /opt/a2a/backup.sh
```

**Remote backup** (S3):
```bash
#!/bin/bash
DB_PATH="$HOME/.a2a/your-project/database.db"
S3_BUCKET="s3://company-backups/a2a"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create local backup
BACKUP_FILE="/tmp/database_$TIMESTAMP.db"
sqlite3 $DB_PATH ".backup $BACKUP_FILE"

# Upload to S3
aws s3 cp $BACKUP_FILE $S3_BUCKET/database_$TIMESTAMP.db

# Clean local backup
rm $BACKUP_FILE
```

### Recovery Procedure

**Step 1: Stop the service**:
```bash
sudo systemctl stop a2a
# or
docker stop a2a-server
```

**Step 2: Restore from backup**:
```bash
# Find the backup you want
ls -lh backups/database_*.db

# Restore
cp backups/database_2024-01-15_020000.db ~/.a2a/your-project/database.db
```

**Step 3: Verify integrity**:
```bash
sqlite3 ~/.a2a/your-project/database.db "PRAGMA integrity_check;"
# Should print: ok
```

**Step 4: Restart the service**:
```bash
sudo systemctl start a2a
```

**Step 5: Verify restoration**:
```bash
# Check message count
sqlite3 ~/.a2a/your-project/database.db "SELECT COUNT(*) FROM messages;"

# Test send/recv
./a2a send test-agent "Recovery test" --from recovery-check
```

---

## Troubleshooting

### Common Issues

#### Issue: "database is locked"
```
Error: sqlite3.OperationalError: database is locked
```

**Causes**:
- Multiple processes accessing database simultaneously
- Previous process crashed without closing connection
- Filesystem lock (network FS issues)

**Solutions**:
```bash
# Check for lingering processes
ps aux | grep a2a

# Kill any stale processes
pkill -f "python.*a2a"

# Check WAL files
ls -la ~/.a2a/*/database.db*

# Remove stale WAL files (if sure no other process is using)
rm ~/.a2a/your-project/database.db-wal
rm ~/.a2a/your-project/database.db-shm

# Restart service
sudo systemctl restart a2a
```

#### Issue: "no such column: priority"
```
Error: sqlite3.OperationalError: no such column: priority
```

**Cause**: Existing database created with v1.2, missing v1.3 schema

**Solution**: Run migration
```python
from a2a_priority import PriorityClient

# Initialize priority table
priority = PriorityClient('your-project', 'migration')
priority.init_priority_table()

print("✅ Priority table initialized")
```

#### Issue: High disk usage
```
Database file size: 5GB+
```

**Diagnosis**:
```bash
# Check message count
sqlite3 ~/.a2a/your-project/database.db "SELECT COUNT(*) FROM messages;"

# Check TTL expired messages
sqlite3 ~/.a2a/your-project/database.db "
  SELECT COUNT(*) FROM messages 
  WHERE created_at + (ttl_seconds ?: 0) < strftime('%s', 'now');
"
```

**Solutions**:
1. **Clean up expired messages**:
```python
import sqlite3
import time

db = sqlite3.connect('~/.a2a/your-project/database.db')
c = db.cursor()

# Delete expired messages
c.execute("""
  DELETE FROM messages 
  WHERE created_at + COALESCE(ttl_seconds, 86400) < ?
""", (time.time(),))

db.commit()
print(f"Deleted {c.rowcount} expired messages")
```

2. **Archive old messages** (for compliance):
```bash
# Export messages older than 30 days
python3 -c "
import sqlite3
import json
import time

db = sqlite3.connect('~/.a2a/your-project/database.db')
c = db.cursor()

cutoff = time.time() - (30 * 86400)
c.execute('SELECT * FROM messages WHERE created_at < ?', (cutoff,))

messages = []
for row in c.fetchall():
    messages.append({
        'id': row[0],
        'sender': row[1],
        'body': row[2],
        # ... other fields
    })

# Save to JSON
with open('archived_messages.json', 'w') as f:
    json.dump(messages, f, indent=2)

# Delete from database
c.execute('DELETE FROM messages WHERE created_at < ?', (cutoff,))
db.commit()
print(f'Archived and deleted {len(messages)} messages')
"
```

### Log Analysis

**Find errors in logs**:
```bash
# systemd journal
journalctl -u a2a -n 100  # Last 100 lines
journalctl -u a2a -f     # Follow (tail -f style)
journalctl -u a2a -S "1 hour ago"  # Last hour

# Docker logs
docker logs a2a-server
docker logs -f a2a-server  # Follow

# Application logs (if using logging)
tail -f ~/.a2a/your-project/a2a.log
grep ERROR ~/.a2a/your-project/a2a.log
```

---

## Performance Tuning

### SQLite Optimization

**Pragmas for performance** (in a2a.py or a2a_server.py):
```python
conn.execute("PRAGMA journal_mode=WAL")          # Write-ahead logging
conn.execute("PRAGMA synchronous=NORMAL")        # Async writes (safer than FULL, faster)
conn.execute("PRAGMA cache_size=10000")          # 10K pages (~40MB)
conn.execute("PRAGMA temp_store=MEMORY")         # Temp tables in RAM
conn.execute("PRAGMA busy_timeout=5000")         # 5s retry timeout
```

### Connection Pooling

**For high-concurrency scenarios** (python):
```python
from queue import Queue
import sqlite3

class ConnectionPool:
    def __init__(self, db_path, pool_size=10):
        self.pool = Queue(maxsize=pool_size)
        self.db_path = db_path
        
        for _ in range(pool_size):
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            self.pool.put(conn)
    
    def get_connection(self):
        return self.pool.get()
    
    def return_connection(self, conn):
        self.pool.put(conn)
    
    def __del__(self):
        while not self.pool.empty():
            conn = self.pool.get()
            conn.close()
```

### Message Archival

**Archive old messages monthly**:
```bash
#!/bin/bash
# Save as /opt/a2a/archive_old_messages.sh

DB_PATH="$HOME/.a2a/your-project/database.db"
ARCHIVE_DIR="/var/archive/a2a"

mkdir -p $ARCHIVE_DIR

# Archive messages older than 90 days
python3 << 'PYTHON'
import sqlite3
import json
import time
import gzip

db = sqlite3.connect("$DB_PATH")
c = db.cursor()

# 90 days ago
cutoff = time.time() - (90 * 86400)

# Export to JSON
c.execute("SELECT * FROM messages WHERE created_at < ?", (cutoff,))
messages = c.fetchall()

if messages:
    filename = f"/var/archive/a2a/messages_{int(time.time())}.json.gz"
    with gzip.open(filename, 'wt') as f:
        json.dump([dict(m) for m in messages], f)
    
    # Delete from DB
    c.execute("DELETE FROM messages WHERE created_at < ?", (cutoff,))
    db.commit()
    
    print(f"Archived {len(messages)} messages to {filename}")
PYTHON
```

**Add to crontab** (monthly):
```bash
# First day of month at 3 AM
0 3 1 * * /opt/a2a/archive_old_messages.sh
```

---

## Security Operations

### Encryption Key Management

**Backup encryption keys**:
```bash
# Keys are stored at ~/.a2a/your-project/keys/
ls -la ~/.a2a/your-project/keys/

# Backup securely
tar czf keys_backup_$(date +%Y%m%d).tar.gz ~/.a2a/your-project/keys/

# Encrypt backup
gpg --symmetric --cipher-algo AES256 keys_backup_*.tar.gz

# Store encrypted backup securely
# Move to: secure storage / HSM / key vault
```

**Key rotation** (for v1.4+):
```python
from a2a_crypto import CryptoClient

crypto = CryptoClient('your-project', 'agent-id')

# Generate new keypair
public_key, private_key = crypto.generate_keypair()

# Update in key store
crypto.save_keypair(public_key, private_key)

# Distribute new public key to all peers
broadcast_new_public_key(public_key)
```

### Audit Log Export

**Export audit logs for compliance**:
```python
from a2a_audit import AuditClient

audit = AuditClient('your-project')

# Export last 30 days
audit.export_audit_log(
    'audit_export_30days.json',
    days=30
)

# Get stats
stats = audit.get_audit_stats(days=30)
print(f"Operations in last 30 days: {stats['total_operations']}")
print(f"By type: {stats['by_operation']}")
```

### Access Control

**Recommended**:
1. Database file permissions: `600` (owner read/write only)
2. Service runs as dedicated user (not root)
3. Encrypt keys at rest
4. Require authentication for all endpoints
5. Log all administrative actions
6. Regular security audit (quarterly)

---

## Support & Escalation

**When to escalate**:
- Database corruption (`PRAGMA integrity_check` fails)
- Unrecoverable connection issues
- Data loss or loss of access
- Security incidents

**Before escalating**:
1. Check logs: `journalctl -u a2a -n 50`
2. Run health check: `curl http://localhost:8080/health`
3. Verify database: `sqlite3 ~/.a2a/your-project/database.db "SELECT COUNT(*) FROM messages;"`
4. Review recent commits: `git log --oneline -10`

**Emergency contacts**:
- See CONTRIBUTING.md for support channels

---

**Last Updated**: 2026-05-19  
**Applies to**: v1.3.0 and later
