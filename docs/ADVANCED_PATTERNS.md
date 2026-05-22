# Advanced a2a Patterns and Recipes

This guide covers advanced usage patterns, optimization techniques, and real-world scenarios.

## Table of Contents

1. [High-Performance Messaging](#high-performance-messaging)
2. [Distributed Workflows](#distributed-workflows)
3. [Error Recovery](#error-recovery)
4. [Advanced Search](#advanced-search)
5. [Monitoring & Observability](#monitoring--observability)
6. [Performance Tuning](#performance-tuning)
7. [Collaborative Artifact Smoke Tests](#collaborative-artifact-smoke-tests)

## Collaborative Artifact Smoke Tests

The `examples/artifacts/` directory contains self-contained build scripts that
demonstrate a2a's peer-to-peer messaging by having teams of AI agents produce
real output files (HTML pages, SVG images, Python tools).

Each artifact build script:

1. **Initializes an a2a bus** for a dedicated project
2. **Registers agents** with role-specific metadata
3. **Spawns agents** via `a2a-spawn` with kit prompts
4. **Coordinates** via the bus (send tasks, collect results)
5. **Writes output** to `examples/artifacts/<name>/output/`
6. **Cleans up** spawned agent processes

### Available artifacts

| Artifact | Agents | Output | Pattern |
|----------|--------|--------|---------|
| `landing-page/` | designer, copywriter, integrator | `index.html` | Divide-and-conquer (3 peers) |
| `svg-banner/` | designer, reviewer | `banner.svg` | Adversarial review loop |
| `mini-cli/` | architect, implementer | `tasky.py` | Spec-then-implement |
| `config-generator/` | architect, implementer | `docker-compose.yml`, `nginx.conf`, `.env.example` | Infrastructure-as-code generation |
| `color-palette/` | colorist, generator | `index.html` | Spec-then-render (color palette → HTML preview) |
| `quiz-generator/` | researcher, checker, formatter | `index.html` | Producer→checker→renderer pipeline (3 peers) |
| `docker-compose-generator/` | specifier, writer | `docker-compose.yml`, `README.md` | 5-service Docker stack generation (spec→implement) |
| `web-research-report/` | searcher, analyst, writer | `report.md`, `bus-state.txt` | Web research pipeline via ddgr (3 peers) |
| `news-briefing/` | curator, narrator | `briefing.md`, `bus-state.txt` | Tech news curation pipeline |
| `competitive-analysis/` | searcher, analyst, writer | `competitive-analysis.md`, `bus-state.txt` | Competitive research with comparison table |
| `a2a-landscape/` | searcher, analyst, writer | `a2a-landscape.md`, `bus-state.txt` | Multi-agent framework positioning |
| `weekly-digest/` | scout, curator, editor | `weekly-digest.md`, `bus-state.txt` | Multi-topic news digest |
| `data-to-chart/` | fetcher, analyst, plotter | `charts.txt`, `analysis.md`, `bus-state.txt` | Data fetcher→analyst→plotter pipeline |
| `doc-pipeline/` | writer, formatter, publisher | `guide.md`, `guide.html`, `bundle.zip`, `bus-state.txt` | Document writing→formatting→bundling pipeline |
| `tech-stack-advisor/` | researcher, recommender | `tech-stack-guide.md`, `bus-state.txt` | Technology stack research and recommendation |
| `ascii-gallery/` | finder, artist, curator | `gallery.html`, `*.txt`, `bus-state.txt` | Image search→ASCII→HTML gallery pipeline |
| `brand-assets/` | designer, reviewer, converter | `brand/banner.svg`, `brand/palette.html`, `brand/logo.txt`, `bus-state.txt` | Brand identity design→review→asset generation pipeline |
| `github-trending-report/` | searcher, describer, compiler | `trending.md`, `bus-state.txt` | GitHub trending repo research report |
| `api-doc-generator/` | searcher, describer, docsmith | `api-docs.md`, `api-docs.html`, `bus-state.txt` | API documentation from web research |
| `dependency-check/` | fetcher, reporter | `advisory.md`, `bus-state.txt` | Dependency CVE scanning pipeline |
| `security-audit/` | scanner, reporter | `report.md`, `raw-findings.json`, `bus-state.txt` | Security posture assessment pipeline |

### Running an artifact

```bash
# From the repo root:
python3 examples/artifacts/landing-page/build.py --cli opencode
python3 examples/artifacts/svg-banner/build.py --cli claude --model haiku
python3 examples/artifacts/mini-cli/build.py --cli pi
python3 examples/artifacts/config-generator/build.py --cli opencode --project artifact-config
```

### Key patterns demonstrated

- **Peer-to-peer coordination**: agents communicate directly without a central
  orchestrator. The build script only sends initial tasks and reads results.
- **Iterative refinement**: svg-banner uses multiple send/recv rounds between
  designer and reviewer for structured critique.
- **Dependency ordering**: mini-cli's implementer waits for the architect's
  spec before starting implementation.
- **Result delivery via broadcast**: agents broadcast their outputs with
  prefixed markers (FINAL_SVG:, FINAL_CODE:) so the build script can
  capture them from the bus.
- **Role-specific kit prompts**: each agent's kit prompt describes its role
  and task, using `make_kit()` from `examples/artifacts/_util.py`.

### Creating a new artifact

1. Create `examples/artifacts/<name>/build.py` (keep under 200 lines)
2. Use `examples/artifacts/_util.py` for shared utilities including
   `strip_html_preamble()` for cleaning up raw HTML output from agents
3. Write a kit prompt with `make_kit()` following the standard pattern
4. Agents communicate via `a2a send` / `a2a recv` — no side channels
5. Output goes to `examples/artifacts/<name>/output/` (checked in: artifacts are committed as reproducible build evidence)

See `examples/artifacts/README.md` for full documentation.

## High-Performance Messaging

### Use Python Client for Throughput

For high-frequency messaging, always use the Python client library instead of CLI:

```python
from a2a_client import A2AClient
import time

client = A2AClient("perf-test", "sender")

# Benchmark: 100 messages
start = time.time()
for i in range(100):
    client.send("receiver", f"Message {i}")
elapsed = time.time() - start

print(f"Throughput: {100/elapsed:.0f} msg/sec")  # ~100 msg/sec
```

**Why?** CLI subprocess overhead is 6-7x slower (~15 msg/sec vs 100 msg/sec).

### Batch Operations

Combine related messages to reduce overhead:

```python
client = A2AClient("myproject", "alice")

# Bad: 10 individual messages
for i in range(10):
    client.send("bob", f"Item {i}")

# Better: 1 message with batch data
import json
batch = {"items": [f"Item {i}" for i in range(10)]}
client.send("bob", json.dumps(batch))
```

### Message Size Considerations

Large messages work fine but consider splitting:

```python
# Single large message (okay, but slow to process)
large_data = "x" * 1_000_000  # 1MB
client.send("receiver", large_data)

# Better: Split into chunks
chunk_size = 100_000
for i in range(0, len(large_data), chunk_size):
    chunk = large_data[i:i+chunk_size]
    client.send("receiver", json.dumps({
        "chunk": i // chunk_size,
        "total_chunks": (len(large_data) + chunk_size - 1) // chunk_size,
        "data": chunk
    }))
```

## Distributed Workflows

### Request-Response Pattern

Implement synchronous RPC-style communication:

```python
import uuid
import time

class RPCClient:
    def __init__(self, project, agent_id, peer):
        self.client = A2AClient(project, agent_id)
        self.peer = peer
    
    def call(self, method, args, timeout=10):
        request_id = str(uuid.uuid4())
        message = {
            "type": "request",
            "id": request_id,
            "method": method,
            "args": args
        }
        
        self.client.send(self.peer, json.dumps(message))
        
        # Wait for response
        deadline = time.time() + timeout
        while time.time() < deadline:
            messages = self.client.recv(wait=1)
            for msg in messages:
                resp = json.loads(msg["body"])
                if resp.get("id") == request_id:
                    return resp.get("result")
        
        raise TimeoutError(f"RPC call to {method} timed out")
```

### Broadcast Aggregation

Gather responses from multiple agents:

```python
def broadcast_and_aggregate(query, timeout=30):
    client = A2AClient("myproject", "coordinator")
    
    # Broadcast question
    client.send("all", f"Question: {query}")
    
    # Collect responses
    responses = {}
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        messages = client.recv(wait=1, include_self=False)
        for msg in messages:
            responses[msg["sender"]] = msg["body"]
        
        if len(responses) >= 3:  # Got 3+ responses
            break
    
    return responses
```

## Error Recovery

### Retry Pattern with Exponential Backoff

```python
import time

def send_with_retry(client, to, message, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.send(to, message)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            
            wait_time = 2 ** attempt  # 1s, 2s, 4s
            print(f"Retry {attempt+1}/{max_retries} after {wait_time}s: {e}")
            time.sleep(wait_time)
```

### Graceful Degradation

```python
def send_or_log(client, to, message):
    try:
        return client.send(to, message)
    except Exception as e:
        # Fall back to logging instead of crashing
        print(f"Failed to send to {to}: {e}")
        with open("/var/log/a2a-failures.log", "a") as f:
            f.write(f"{to}: {message}\n")
        return None
```

## Advanced Search

### Full-Text Search Simulation

Since a2a uses LIKE for search, implement case-insensitive patterns:

```python
def search_advanced(query, agent_status=None):
    client = A2AClient("myproject", "searcher")
    
    # Search with LIKE (case-sensitive on some DBs, insensitive on others)
    results = client.search(query.lower())
    
    # Filter by sender if needed
    if agent_status:
        all_agents = {a["id"]: a["status"] for a in client.list_peers()}
        results = [r for r in results if all_agents.get(r["sender"]) == agent_status]
    
    return results
```

### Thread Analysis

```python
def analyze_conversation(thread_id):
    client = A2AClient("myproject", "analyzer")
    
    messages = client.thread(thread_id)
    
    # Who spoke?
    speakers = set(m["sender"] for m in messages)
    
    # Message flow
    flow = [f"{m['sender']} -> {m['recipient'] or 'ALL'}" for m in messages]
    
    # Total words exchanged
    word_count = sum(len(m["body"].split()) for m in messages)
    
    return {
        "speakers": list(speakers),
        "message_count": len(messages),
        "word_count": word_count,
        "flow": flow
    }
```

## Monitoring & Observability

### Bus Health Check

```python
def check_bus_health():
    client = A2AClient("myproject", "monitor")
    
    stats = client.stats()
    
    health = {
        "status": "healthy",
        "issues": []
    }
    
    # Check message backlog
    if stats["messages"] > 10000:
        health["issues"].append(f"High message count: {stats['messages']}")
    
    # Check stuck agents
    peers = client.list_peers()
    blocked = [p["id"] for p in peers if p["status"] == "blocked"]
    if blocked:
        health["issues"].append(f"Blocked agents: {blocked}")
    
    # Check dead agents (no recent activity)
    import time
    now = time.time()
    dead = []
    for p in peers:
        if p.get("last_seen") and (now - p["last_seen"]) > 300:
            dead.append(p["id"])
    if dead:
        health["issues"].append(f"Inactive agents: {dead}")
    
    if health["issues"]:
        health["status"] = "degraded"
    
    return health
```

### Message Rate Monitoring

```python
def monitor_message_rate(interval=10, duration=60):
    client = A2AClient("myproject", "monitor")
    
    rates = []
    start = time.time()
    prev_count = client.stats()["messages"]
    
    while time.time() - start < duration:
        time.sleep(interval)
        curr_count = client.stats()["messages"]
        rate = (curr_count - prev_count) / interval
        rates.append(rate)
        prev_count = curr_count
    
    return {
        "avg_rate": sum(rates) / len(rates),
        "peak_rate": max(rates),
        "min_rate": min(rates),
        "measurements": len(rates)
    }
```

## Performance Tuning

### Connection Pooling Pattern

For many short-lived operations, cache connections:

```python
class PooledA2AClient:
    def __init__(self, project, agent_id, pool_size=1):
        self.project = project
        self.agent_id = agent_id
        self.pool = [A2AClient(project, agent_id) for _ in range(pool_size)]
        self.current = 0
    
    def get_client(self):
        client = self.pool[self.current]
        self.current = (self.current + 1) % len(self.pool)
        return client
    
    def send(self, to, message):
        return self.get_client().send(to, message)
    
    def recv(self, **kwargs):
        return self.get_client().recv(**kwargs)
```

### Lazy Message Processing

Don't load all messages, process as you go:

```python
def process_messages_streaming():
    client = A2AClient("myproject", "processor")
    
    while True:
        messages = client.recv(wait=5, limit=10)  # Get up to 10 at a time
        
        if not messages:
            break
        
        for msg in messages:
            # Process one at a time instead of loading all
            result = expensive_operation(msg["body"])
            client.send(msg["sender"], json.dumps({"result": result}))
```

### Database Query Optimization

For custom analysis, write efficient SQL:

```python
import sqlite3
from pathlib import Path

def custom_analytics():
    db_path = Path.home() / ".a2a" / "myproject" / "database.db"
    conn = sqlite3.connect(str(db_path))
    
    # Fast: Use INDEX, GROUP BY intelligently
    top_senders = conn.execute("""
        SELECT sender, COUNT(*) as count
        FROM messages
        WHERE created_at > datetime('now', '-1 hour')
        GROUP BY sender
        ORDER BY count DESC
        LIMIT 10
    """).fetchall()
    
    conn.close()
    return top_senders
```

## Security Considerations

### Validating Message Sources

```python
def recv_from_trusted_only(trusted_agents):
    client = A2AClient("myproject", "secure")
    
    messages = client.recv()
    
    # Filter to trusted senders only
    trusted = [m for m in messages if m["sender"] in trusted_agents]
    
    return trusted
```

### Rate Limiting

```python
from collections import defaultdict
import time

class RateLimiter:
    def __init__(self, max_messages=10, window=60):
        self.max = max_messages
        self.window = window
        self.counts = defaultdict(list)
    
    def allow(self, agent_id):
        now = time.time()
        # Remove old entries
        self.counts[agent_id] = [t for t in self.counts[agent_id] 
                                 if now - t < self.window]
        
        if len(self.counts[agent_id]) < self.max:
            self.counts[agent_id].append(now)
            return True
        return False

limiter = RateLimiter(max_messages=5, window=60)
if limiter.allow("bob"):
    client.send("bob", "message")
else:
    print("Rate limited")
```

---

For more examples, see the `examples/` directory.
