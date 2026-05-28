# a2a Full-Text Search (FTS5) — v1.3 Feature

Advanced message discovery with full-text search powered by SQLite FTS5.

## Overview

FTS5 enables:
- **Fast searching** — Indexed search across all message content
- **Phrase queries** — Find exact phrases
- **Boolean operators** — AND, OR, NOT combinations
- **Prefix matching** — Find terms starting with prefix
- **Relevance ranking** — Results ranked by relevance score
- **Advanced filters** — Search within sender/recipient/thread scope

## Quick Start

### Initialize FTS Index

```python
from a2a_fts import FTSClient

client = FTSClient("my-project", "alice")

# Initialize FTS5 virtual table (one-time setup)
client.init_fts_table()
```

### Simple Search

```python
# Search for messages containing "login"
results = client.search_fts("login")

for msg in results:
    print(f"{msg['sender']}: {msg['body'][:50]}")
    print(f"  Relevance: {msg.get('relevance_score', 'N/A')}")
```

### Phrase Search

```python
# Find exact phrase
results = client.search_fts('"user authentication failed"')

# Multiple phrases
results = client.search_fts('"login error" OR "auth failed"')
```

### Boolean Queries

```python
# AND operator (all terms required)
results = client.search_fts("authentication AND failed")

# OR operator (any term)
results = client.search_fts("error OR warning OR critical")

# NOT operator (exclude term)
results = client.search_fts("login -failed")

# Complex boolean
results = client.search_fts("(authentication OR login) AND failed")
```

### Prefix Matching

```python
# Find all terms starting with "auth"
results = client.search_fts("auth*")

# Matches: auth, authenticate, authentication, authorized, etc.
```

### Advanced Search with Filters

```python
# Search within sender
results = client.search_advanced(
    query="error",
    sender="alice",
    limit=50
)

# Search within thread
results = client.search_advanced(
    query="solution",
    thread_id="42",
    limit=20
)

# Search with multiple filters
results = client.search_advanced(
    query="bug report",
    sender="bob",
    recipient="alice",
    limit=100
)
```

## API Reference

### FTSClient

```python
class FTSClient:
    def init_fts_table(self) -> bool
    def search_fts(query: str, limit: int = 100, rank_by_relevance: bool = True) -> List[Dict]
    def search_advanced(query: str, sender=None, recipient=None, thread_id=None, limit=100) -> List[Dict]
    def get_search_suggestions(partial_query: str) -> List[str]
    def rebuild_fts_index(self) -> bool
    def get_search_stats(self) -> Dict[str, Any]
```

### Query Syntax

```
login                    # Simple term
"user login"             # Phrase (exact)
login AND password       # Both terms required
error OR warning         # Either term
login -failed            # Term required, excluded term
auth*                    # Prefix match
(login OR auth) AND fail # Grouped boolean
```

## Integration with A2AClient

```python
import asyncio
from a2a_client_async import A2AClientAsync
from a2a_fts import FTSClient

async def search_and_report():
    fts_client = FTSClient("myproject", "alice")
    
    # Initialize FTS once
    fts_client.init_fts_table()
    
    # Search
    results = fts_client.search_fts("critical error", limit=20)
    
    # Report findings
    async with A2AClientAsync("myproject", "alice") as a2a:
        report = {
            "type": "search_results",
            "query": "critical error",
            "count": len(results),
            "results": results[:5]  # Top 5 results
        }
        await a2a.send("coordinator", json.dumps(report))

asyncio.run(search_and_report())
```

## Search Examples

### Find All Errors

```python
results = client.search_fts("error")
```

### Find Failed Authentication Attempts

```python
results = client.search_fts('"authentication failed" OR "login failed"')
```

### Find Messages from Specific Agent About Topic

```python
results = client.search_advanced(
    query="database optimization",
    sender="engineer-1"
)
```

### Find Unresolved Issues

```python
results = client.search_fts("issue NOT resolved")
```

### Find Performance-Related Messages

```python
results = client.search_fts("(performance OR latency OR slow) AND (bug OR issue)")
```

## Performance

- **Index creation**: ~100ms for 1000 messages
- **Search time**: 5-20ms for typical queries
- **Memory overhead**: ~20% of message data size
- **Concurrent searches**: Fully supported (read-only)

## Best Practices

1. **Initialize once**: Call `init_fts_table()` at startup, not per-search
2. **Use phrases for exact matches**: `"exact phrase"` faster than boolean AND
3. **Prefix matching** is efficient: `search*` good for autocomplete
4. **Exclude before include**: Use `-term` to narrow results
5. **Limit results**: Use `limit` parameter to reduce memory usage
6. **Rebuild after bulk operations**: Call `rebuild_fts_index()` after large inserts

## Troubleshooting

### FTS table not working

```python
# Check status
stats = client.get_search_stats()
print(stats)

# Rebuild if needed
client.rebuild_fts_index()
```

### Search returning no results

- Check query syntax (use quotes for phrases)
- Try simpler query: `client.search_fts("term")`
- Verify messages exist: `client.get_search_stats()`

### Slow searches

- Ensure index is built: `rebuild_fts_index()`
- Use more specific queries
- Add filters (sender, recipient, thread_id)

## SearchQueryBuilder

Helper for building complex queries:

```python
from a2a_fts import SearchQueryBuilder

builder = SearchQueryBuilder()
query = (builder
    .add_term("error")
    .must_contain("critical")
    .must_not_contain("resolved")
    .build())

results = client.search_fts(query)
```

## Limitations

1. **No real-time updates**: FTS index updated via triggers (near-instant)
2. **No field-specific ranking**: All fields equally weighted
3. **Simple relevance**: Rank based on frequency, not position
4. **No stemming**: "run", "running", "ran" are different terms

## See Also

- [README.md](../README.md) — Project overview
- [CLIENT_API.md](CLIENT_API.md) — Python client reference
- [CHANGELOG.md](../CHANGELOG.md) — Release history and roadmap
