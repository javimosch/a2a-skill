# a2a Node.js Client Library

The `a2a_client.js` module provides a Node.js object-oriented API for a2a messaging, eliminating the need to shell out to the `a2a` CLI.

## Installation

```bash
# Copy to your project
cp a2a_client.js /path/to/your/project/
```

Requires Node.js 22+ (uses built-in `node:sqlite` — no npm dependencies).

## Quick Start

```javascript
const A2AClient = require('./a2a_client');

// Initialize client
const client = new A2AClient('my-project', 'alice');

// Send a message
const msgId = await client.send('bob', 'Hello Bob!');

// Receive messages (blocks up to 10 seconds)
const messages = await client.recv(10);
messages.forEach(msg => {
  console.log(`${msg.sender}: ${msg.body}`);
});

// Broadcast
await client.send('all', 'Hello everyone!');

// Mark yourself done
await client.setStatus('done');
```

## API Reference

All methods are async (return Promises).

### register(role, prompt, cli, pid, upsert)

Register this agent on the bus. Must be called before send/recv.

```javascript
await client.register('researcher', 'Research things', 'node', null, true);
```

### unregister()

Remove this agent from the bus.

```javascript
await client.unregister();
```

### send(to, message, ttlSeconds, threadId)

Send a message to a peer. Returns the message ID. Raises an error if the
recipient is empty, ttlSeconds is not a positive number, or threadId is
empty/whitespace.

```javascript
const msgId = await client.send('bob', 'Hello', 3600);
const msgId2 = await client.send('bob', 'Follow-up', null, 'thread-1'); // with thread
```

### recv(wait, unreadOnly, includeSelf, limit)

Receive messages addressed to this agent.

```javascript
const messages = await client.recv(10);  // Wait up to 10 seconds
```

### peek(limit)

View recent messages without marking as read.

```javascript
const recent = await client.peek(50);
```

### listPeers()

Get roster of registered agents.

```javascript
const peers = await client.listPeers();
```

### setStatus(status)

Update this agent's status (active/idle/done/blocked).

```javascript
await client.setStatus('done');
```

### getStatus(agentId)

Check an agent's status.

```javascript
const status = await client.getStatus('bob');
```

### waitForMessages(count, timeout)

Block until N unread messages or timeout.

```javascript
const success = await client.waitForMessages(3, 30);
```

### search(query, limit)

Search messages by content (case-insensitive).

```javascript
const results = await client.search('important', 100);
```

### thread(threadId)

Get all messages in a thread.

```javascript
const threadMessages = await client.thread("42");
```

### stats()

Get aggregated bus statistics.

```javascript
const stats = await client.stats();
console.log(`Total messages: ${stats.messages}`);
```

## Example: Multi-Agent Coordination

```javascript
const A2AClient = require('./a2a_client');

async function main() {
  const client = new A2AClient('project', 'coordinator');
  
  // Broadcast task
  await client.send('all', 'Please review the proposal');
  
  // Wait for responses
  await client.waitForMessages(3, 30);
  
  // Collect reviews
  const reviews = await client.recv();
  console.log(`Got ${reviews.length} reviews`);
  
  // Summarize
  await client.send('all', 'Summary: All reviews received');
  await client.setStatus('done');
}

main().catch(err => console.error(err));
```

## Performance

Direct SQLite connections (no subprocess overhead):
- send(): ~5ms
- recv(): ~10ms per poll
- search(): ~20ms for 1000 messages

## See Also

- [CLIENT_API.md](CLIENT_API.md) — Python client
- [ADVANCED_PATTERNS.md](ADVANCED_PATTERNS.md) — Patterns and optimization
