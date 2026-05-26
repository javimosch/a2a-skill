# a2a Integration Guide: Multi-Interface Coordination

This guide shows how to integrate multiple access methods (CLI, Python SDK, Node.js SDK, REST API) in a single a2a project.

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│        a2a Messaging Bus (SQLite)               │
├─────────────────────────────────────────────────┤
│  CLI              Python SDK       Node.js SDK  │
│  (shell/scripts)  (programmatic)  (JavaScript)  │
│                                                  │
│  REST API Server (HTTP)                        │
│  (web services, microservices)                 │
└─────────────────────────────────────────────────┘
```

All interfaces operate on the same SQLite database, enabling seamless cross-method communication.

## Example: Multi-Stack Task Pipeline

Imagine a task processing pipeline using three different technologies:

### 1. CLI Agent (Bash/Shell)

```bash
#!/bin/bash
# task_monitor.sh — Monitor and route tasks

a2a register monitor --role supervisor

while true; do
  messages=$(a2a recv --as monitor --json)
  for msg in $(echo "$messages" | jq -r '.[] | @base64'); do
    decoded=$(echo "$msg" | base64 -d)
    type=$(echo "$decoded" | jq -r '.type // empty')
    
    if [ "$type" = "task_request" ]; then
      task=$(echo "$decoded" | jq -r '.task')
      echo "Assigning: $task"
      a2a send processor "$decoded" --from monitor
    fi
  done
  sleep 1
done
```

### 2. Python Worker (Python SDK)

```python
#!/usr/bin/env python3
# task_processor.py — Process tasks

from a2a_client import A2AClient
import json

client = A2AClient('my-project', 'processor')
await client.set_status('active')

while True:
    messages = await client.recv(wait=10)
    for msg in messages:
        try:
            task_data = json.loads(msg['body'])
            if task_data.get('type') == 'task_request':
                task = task_data.get('task')
                print(f'Processing: {task}')
                
                # Do work...
                result = f'Completed: {task}'
                
                await client.send('monitor', json.dumps({
                    'type': 'task_complete',
                    'task': task,
                    'result': result
                }))
        except json.JSONDecodeError:
            pass

await client.set_status('done')
```

### 3. Node.js Coordinator (Node.js SDK)

```javascript
// coordinator.js — Coordinate work across teams

const A2AClient = require('./a2a_client');

async function main() {
  const client = new A2AClient('my-project', 'coordinator');
  
  // Broadcast task to all workers
  await client.send('all', JSON.stringify({
    type: 'task_request',
    task: 'Analyze customer data',
    priority: 'high',
    deadline: new Date(Date.now() + 3600000).toISOString()
  }));
  
  // Wait for completions
  console.log('Waiting for task completions...');
  await client.waitForMessages(3, 300);
  
  // Gather results
  const results = await client.recv();
  console.log(`Received ${results.length} results`);
  
  // Final status
  const stats = await client.stats();
  console.log(`Pipeline: ${stats.messages} total messages`);
  
  await client.setStatus('done');
}

main().catch(console.error);
```

### 4. Web Service (REST API)

```bash
#!/bin/bash
# web_service.sh — Trigger jobs from HTTP requests

# Start REST API server in background
python3 a2a_server.py --project my-project &

# Listen for incoming HTTP requests
while read -r request; do
  # Example: curl http://localhost:5000/send with job data
  
  # Send job to coordinator via REST
  curl -X POST http://localhost:5000/send \
    -H 'Content-Type: application/json' \
    -d '{"to": "coordinator", "message": "Process this job"}'
  
  # Check job status
  status=$(curl http://localhost:5000/agent?id=processor)
  echo "Processor status: $status"
done
```

## Communication Flow

1. **Web Service** (REST) sends job → REST API Server → SQLite
2. **Coordinator** (Node.js) receives job, delegates to workers → SQLite
3. **Monitor** (CLI) watches for tasks, routes to processor → SQLite
4. **Processor** (Python) executes task, reports results → SQLite
5. **Coordinator** aggregates results, responds via REST → Web Service

## Deployment Patterns

### Local Development

```bash
# Terminal 1: Start REST server
python3 a2a_server.py --project dev

# Terminal 2: Run monitor agent
./task_monitor.sh

# Terminal 3: Run processor agent
python3 task_processor.py

# Terminal 4: Run coordinator
node coordinator.js

# Terminal 5: Test via curl
curl http://localhost:5000/health
curl http://localhost:5000/peers
```

### Docker Compose

```yaml
version: '3'
services:
  rest-api:
    image: python:3.11
    volumes:
      - .:/app
    working_dir: /app
    command: python3 a2a_server.py --project docker --host 0.0.0.0
    ports:
      - "5000:5000"

  monitor:
    image: ubuntu:22.04
    volumes:
      - .:/app
      - ~/.a2a:/root/.a2a
    working_dir: /app
    command: bash task_monitor.sh

  processor:
    image: python:3.11
    volumes:
      - .:/app
      - ~/.a2a:/root/.a2a
    working_dir: /app
    command: python3 task_processor.py

  coordinator:
    image: node:18
    volumes:
      - .:/app
      - ~/.a2a:/root/.a2a
    working_dir: /app
    command: node coordinator.js
```

### Kubernetes

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: a2a-config
data:
  project: "kubernetes"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: a2a-rest-api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: a2a-rest-api
  template:
    metadata:
      labels:
        app: a2a-rest-api
    spec:
      containers:
      - name: api
        image: python:3.11
        command:
        - python3
        - a2a_server.py
        - --project
        - kubernetes
        - --host
        - 0.0.0.0
        ports:
        - containerPort: 5000
        volumeMounts:
        - name: a2a-data
          mountPath: /.a2a
      volumes:
      - name: a2a-data
        persistentVolumeClaim:
          claimName: a2a-storage
```

## Best Practices

1. **Use the right tool for the job**
   - CLI for scripts and one-liners
   - Python SDK for data processing and complex logic
   - Node.js SDK for event-driven and async workflows
   - REST API for web services and HTTP clients

2. **Keep messages JSON for interoperability**
   ```python
   # Good: Structured, parseable across all interfaces
   client.send("other-agent", json.dumps({"type": "task", "data": ...}))

   # Avoid: Unstructured text, harder to parse
   client.send("other-agent", "Process this thing")
   ```

3. **Use agent roles and status for coordination**
   ```python
   await client.set_status('processing')
   # ... do work ...
   await client.set_status('done')
   ```

4. **Monitor via stats() or /stats endpoint**
   ```python
   stats = await client.stats()
   if stats['agents_done'] >= stats['agents_active']:
       print("All agents finished!")
   ```

5. **Handle JSON parsing gracefully**
   ```python
   try:
       data = json.loads(msg['body'])
   except json.JSONDecodeError:
       continue  # Skip non-JSON messages
   ```

## Troubleshooting

**Messages not appearing across interfaces?**
- Verify agents are registered: `a2a list` or `GET /peers`
- Check database path: `~/.a2a/{project}/database.db`
- Ensure same project name across all interfaces

**REST server not responding?**
- Start with: `python3 a2a_server.py --project <name>`
- Test: `curl http://localhost:5000/health`
- Check logs for port conflicts

**Messages stuck in queue?**
- Check agent status: `a2a recv --as <agent>`
- Verify TTL hasn't expired: `a2a stats | grep TTL`
- Monitor bus: `a2a peek --limit 50`

## Performance Considerations

- **CLI**: ~15 msg/sec (subprocess overhead)
- **Python SDK**: ~100 msg/sec (direct DB)
- **Node.js SDK**: ~100 msg/sec (direct DB)
- **REST API**: ~50-100 msg/sec (HTTP overhead)

For high throughput, use Python or Node.js SDKs directly.

## See Also

- [README.md](../README.md) — Project overview
- [CLIENT_API.md](CLIENT_API.md) — Python SDK details
- [NODE_CLIENT_API.md](NODE_CLIENT_API.md) — Node.js SDK details
- [REST_API.md](REST_API.md) — REST API reference
- [examples/](../examples/) — Complete working examples
