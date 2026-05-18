# a2a Deployment Guide

Complete deployment guide for a2a messaging bus across multiple environments and language bindings.

## Quick Start with Docker Compose

Deploy a multi-language agent cluster with a single command:

```bash
docker-compose up
```

This starts:
- REST API server on port 5000
- Python worker agent
- Node.js worker agent
- PostgreSQL database (optional persistence)
- Redis cache (optional)

## Docker Container Images

Build containers for each language binding:

### Python Agent
```bash
docker build -f Dockerfile.multi --target python-agent -t a2a-python:latest .
docker run -v ~/.a2a:/root/.a2a -e A2A_PROJECT=prod a2a-python:latest
```

### Node.js Agent
```bash
docker build -f Dockerfile.multi --target nodejs-agent -t a2a-nodejs:latest .
docker run -v ~/.a2a:/root/.a2a -e A2A_PROJECT=prod a2a-nodejs:latest
```

### Go Agent
```bash
docker build -f Dockerfile.multi --target go-agent -t a2a-go:latest .
docker run -v ~/.a2a:/root/.a2a -e A2A_PROJECT=prod a2a-go:latest
```

### Rust Agent
```bash
docker build -f Dockerfile.multi --target rust-agent -t a2a-rust:latest .
docker run -v ~/.a2a:/root/.a2a -e A2A_PROJECT=prod a2a-rust:latest
```

### CLI Container
```bash
docker build -f Dockerfile.multi --target cli -t a2a-cli:latest .
docker run -v ~/.a2a:/root/.a2a a2a-cli:latest list
```

## Kubernetes Deployment

### Namespace and ConfigMap
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: a2a
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: a2a-config
  namespace: a2a
data:
  project: "kubernetes"
  host: "0.0.0.0"
  port: "5000"
```

### REST API Server Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: a2a-api
  namespace: a2a
spec:
  replicas: 2
  selector:
    matchLabels:
      app: a2a-api
  template:
    metadata:
      labels:
        app: a2a-api
    spec:
      containers:
      - name: api
        image: a2a-python:latest
        ports:
        - containerPort: 5000
        env:
        - name: A2A_PROJECT
          valueFrom:
            configMapKeyRef:
              name: a2a-config
              key: project
        volumeMounts:
        - name: a2a-storage
          mountPath: /.a2a
      volumes:
      - name: a2a-storage
        persistentVolumeClaim:
          claimName: a2a-storage
---
apiVersion: v1
kind: Service
metadata:
  name: a2a-api
  namespace: a2a
spec:
  selector:
    app: a2a-api
  ports:
  - protocol: TCP
    port: 5000
    targetPort: 5000
  type: LoadBalancer
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: a2a-storage
  namespace: a2a
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 10Gi
```

### Worker Agents Deployment
```yaml
apiVersion: batch/v1
kind: Deployment
metadata:
  name: a2a-workers
  namespace: a2a
spec:
  replicas: 3
  selector:
    matchLabels:
      app: a2a-worker
  template:
    metadata:
      labels:
        app: a2a-worker
    spec:
      containers:
      - name: python-worker
        image: a2a-python:latest
        env:
        - name: A2A_PROJECT
          valueFrom:
            configMapKeyRef:
              name: a2a-config
              key: project
        volumeMounts:
        - name: a2a-storage
          mountPath: /.a2a
      - name: nodejs-worker
        image: a2a-nodejs:latest
        env:
        - name: A2A_PROJECT
          valueFrom:
            configMapKeyRef:
              name: a2a-config
              key: project
        volumeMounts:
        - name: a2a-storage
          mountPath: /.a2a
      volumes:
      - name: a2a-storage
        persistentVolumeClaim:
          claimName: a2a-storage
```

## Systemd Service

Run a2a as a systemd service:

```ini
[Unit]
Description=a2a REST API Server
Documentation=https://github.com/anthropics/a2a
After=network.target
Wants=a2a-workers.service

[Service]
Type=simple
User=a2a
WorkingDirectory=/opt/a2a
ExecStart=/usr/bin/python3 /opt/a2a/a2a_server.py --project production --host 0.0.0.0 --port 5000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Worker service:
```ini
[Unit]
Description=a2a Worker Agents
After=network.target a2a.service

[Service]
Type=simple
User=a2a
WorkingDirectory=/opt/a2a
ExecStart=/usr/bin/python3 /opt/a2a/examples/task_coordinator_agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable services:
```bash
sudo systemctl daemon-reload
sudo systemctl enable a2a a2a-workers
sudo systemctl start a2a a2a-workers
```

## Nginx Reverse Proxy

```nginx
upstream a2a_backend {
    least_conn;
    server localhost:5000 max_fails=3 fail_timeout=30s;
    server localhost:5001 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name a2a.example.com;
    
    location / {
        proxy_pass http://a2a_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Health check endpoint
    location /health {
        proxy_pass http://a2a_backend;
        access_log off;
    }
}
```

## Environment Variables

Configure a2a via environment variables:

```bash
# Project name (required)
export A2A_PROJECT=production

# REST API server
export A2A_HOST=0.0.0.0
export A2A_PORT=5000

# Database path (defaults to ~/.a2a/{project}/database.db)
export A2A_DB_PATH=/var/lib/a2a/database.db

# Agent configuration
export A2A_AGENT_ID=worker-1
export A2A_AGENT_ROLE=worker
export A2A_STATUS=active
```

## Database Backup

Backup the a2a database:

```bash
# Single database
sqlite3 ~/.a2a/production/database.db ".backup '/backups/a2a-production.db'"

# Automated daily backup
0 2 * * * sqlite3 ~/.a2a/production/database.db ".backup '/backups/a2a-production-$(date +\%Y\%m\%d).db'"
```

## Monitoring and Logging

### Prometheus Metrics
```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'a2a'
    static_configs:
      - targets: ['localhost:5000']
    metrics_path: '/metrics'
```

### Log Aggregation
```bash
# Collect logs from all a2a services
journalctl -u a2a -u a2a-workers -f

# Send to log aggregation service
journalctl -u a2a -o json | curl -X POST -d @- http://logs.example.com/api/logs
```

## Performance Tuning

### SQLite Configuration
```bash
# Enable WAL mode for concurrent access
sqlite3 ~/.a2a/production/database.db "PRAGMA journal_mode=WAL;"

# Increase cache size
sqlite3 ~/.a2a/production/database.db "PRAGMA cache_size=10000;"

# Optimize query performance
sqlite3 ~/.a2a/production/database.db "PRAGMA query_only=OFF; CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient); CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);"
```

### Resource Limits
```yaml
# Kubernetes resource limits
resources:
  requests:
    memory: "256Mi"
    cpu: "250m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

## Security

### TLS/SSL
```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365

# Update REST API to use HTTPS
python a2a_server.py --cert cert.pem --key key.pem
```

### Authentication
```python
# Add authentication middleware
from functools import wraps
import hmac
import hashlib

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or not verify_api_key(api_key):
            return {'error': 'Unauthorized'}, 401
        return f(*args, **kwargs)
    return decorated
```

### Database Encryption
```bash
# Use SQLite with encryption extension (sqlcipher)
pip install sqlcipher3
# Connection with password:
sqlite3.connect('file:database.db?key=mypassword', uri=True)
```

## Troubleshooting

### Connection Issues
```bash
# Test REST API
curl http://localhost:5000/health

# Check database connectivity
sqlite3 ~/.a2a/production/database.db "SELECT COUNT(*) FROM agents;"

# Monitor network traffic
tcpdump -i lo port 5000
```

### Performance Debugging
```bash
# Profile agent memory usage
python -m memory_profiler examples/task_coordinator_agent.py

# Trace database queries
sqlite3 ~/.a2a/production/database.db "PRAGMA query_only=ON;" "SELECT * FROM messages LIMIT 10;"
```

## See Also

- [README.md](README.md) — Project overview
- [REST_API.md](REST_API.md) — HTTP interface reference
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) — Multi-interface coordination
