# a2a REST API Server

The `a2a_server.py` provides an HTTP REST interface to a2a messaging, enabling integration with web services, microservices, and non-CLI clients.

## Quick Start

```bash
# Start server (listens on localhost:5000)
python3 a2a_server.py --project my-project

# In another terminal, test it:
curl http://localhost:5000/health
# Output: {"status": "ok"}
```

## Endpoints

### Health Check

```
GET /health
```

Response: `{"status": "ok"}`

### List Peers

```
GET /peers
```

Response:
```json
{
  "peers": [
    {"id": "alice", "role": "worker", "status": "active"},
    {"id": "bob", "role": "worker", "status": "done"}
  ]
}
```

### Send Message

```
POST /send
Content-Type: application/json

{
  "to": "bob",
  "message": "Hello Bob!",
  "from": "alice",
  "ttl_seconds": 3600,
  "thread_id": "my-thread"
}
```

Fields:
- `to`: Recipient agent ID, or a broadcast target (`"all"`, `"*"`)
- `message`: Message body text
- `from` (optional): Sender ID (defaults to `"http-client"`)
- `ttl_seconds` (optional): Message TTL in seconds
- `thread_id` (optional): Thread grouping ID

Response: `{"message_id": 42, "status": "sent"}`

### Receive Messages

```
POST /recv
Content-Type: application/json

{
  "agent": "my-agent",
  "wait": 10,
  "limit": 20
}
```

Response:
```json
{
  "messages": [
    {"id": 1, "sender": "alice", "body": "Hello", "created_at": 1234567890.5}
  ]
}
```

### Peek Messages

```
GET /messages?limit=50
```

Returns recent messages without marking as read.

### Search Messages

```
GET /search?q=important&limit=100
```

Search messages by substring (case-insensitive).

### Get Thread

```
GET /thread?id=42
```

Retrieve all messages in a thread.

### Get Statistics

```
GET /stats
```

Response:
```json
{
  "messages": 100,
  "broadcasts": 20,
  "direct": 80,
  "threads": 5,
  "agents": 3
}
```

### Get Agent Status

```
GET /agent?id=alice
```

Response: `{"agent": "alice", "status": "active"}`

### Set Agent Status

```
POST /status
Content-Type: application/json

{
  "agent": "my-agent",
  "status": "done"
}
```

### Register Agent

```
POST /register
Content-Type: application/json

{
  "id": "my-agent",
  "role": "worker",
  "prompt": "Do the dishes",
  "cli": "python"
}
```

Response: `{"status": "registered"}`

### Unregister Agent

```
POST /unregister
Content-Type: application/json

{
  "id": "my-agent"
}
```

Response: `{"status": "unregistered"}`

## Configuration

```bash
python3 a2a_server.py \
  --project my-project \
  --host 0.0.0.0 \
  --port 8000
```

## Example: Web Service Integration

```bash
# Send message from web service
curl -X POST http://localhost:5000/send \
  -H 'Content-Type: application/json' \
  -d '{"to": "worker", "message": "Process order #123"}'

# Check worker status
curl http://localhost:5000/agent?id=worker

# Receive updates
curl -X POST http://localhost:5000/recv \
  -H 'Content-Type: application/json' \
  -d '{"agent": "web-service", "wait": 30}'
```

## CORS Support

All endpoints support CORS (Access-Control-Allow-Origin: *) for browser-based access.

## Error Responses

Bad request:
```json
{"error": "Missing to or message"}
```

Not found:
```json
{"error": "Agent not found"}
```

Server error:
```json
{"error": "Database error"}
```

## Performance Notes

- Direct database access (no subprocess overhead)
- ~10-50ms latency per request
- Suitable for HTTP clients, web services, microservices
- No authentication (use firewall/reverse-proxy for security)

## Deployment

For production, run behind a reverse proxy:

```bash
# nginx configuration example
upstream a2a {
  server localhost:5000;
}

server {
  listen 80;
  server_name a2a.example.com;

  location / {
    proxy_pass http://a2a;
    proxy_set_header Host $host;
  }
}
```

Or use systemd:

```ini
[Unit]
Description=a2a REST API Server
After=network.target

[Service]
Type=simple
User=a2a
ExecStart=/usr/bin/python3 /opt/a2a/a2a_server.py --project production --host 0.0.0.0 --port 5000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## See Also

- [README.md](../README.md) — Project overview
- [CLIENT_API.md](docs/CLIENT_API.md) — Python client
- [NODE_CLIENT_API.md](docs/NODE_CLIENT_API.md) — Node.js client
