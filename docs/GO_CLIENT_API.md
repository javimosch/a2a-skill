# a2a Go Client Library

The `a2a_client.go` module provides a Go API for a2a messaging, enabling integration with Go-based systems, microservices, and CLIs.

## Installation

```bash
# Add to your go.mod (root of this repo is the Go module)
go get github.com/javimosch/a2a-skill
```

## Quick Start

```go
package main

import (
	"fmt"
	"log"
	"a2a"  // import the local package
)

func main() {
	// Initialize client
	client := a2a.NewClient("my-project", "alice")

	// Send a message
	msgID, err := client.Send("bob", "Hello Bob!", "", nil)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("Sent message %d\n", msgID)

	// Receive messages (blocks up to 10 seconds)
	messages, err := client.Recv(a2a.RecvOpts{
		Wait:        10,
		UnreadOnly:  true,
		IncludeSelf: false,
	})
	if err != nil {
		log.Fatal(err)
	}
	for _, msg := range messages {
		fmt.Printf("%s: %s\n", msg.Sender, msg.Body)
	}

	// Broadcast
	client.Send("all", "Hello everyone!", "", nil)

	// Mark done
	client.SetStatus("done")
}
```

## API Reference

### NewClient(project, agentID string) *Client

Create a new client.

### Send(to, message, threadID string, ttlSeconds *int) (int64, error)

Send a message with optional thread ID and TTL. Set `to` to "all", "*", or "broadcast" for broadcast messages.
Pass thread ID as "" for no thread, or nil ttlSeconds for no expiry.

```go
ttl := 3600
msgID, err := client.Send("bob", "Hello", "thread-1", &ttl)
```

### SendSimple(to, message string) (int64, error)

Backward-compatible wrapper for `Send()` without thread or TTL.

```go
msgID, err := client.SendSimple("bob", "Hello")
```

### Recv(opts RecvOpts) ([]Message, error)

Receive messages with full options (struct-based API). Calls `CleanupExpired()`
and `Touch()` internally before fetching. Returns after finding messages, or
after `opts.Wait` seconds.

```go
import "time"

msgs, err := client.Recv(a2a.RecvOpts{
    Wait:        30,
    UnreadOnly:  true,
    IncludeSelf: false,
    Limit:       10,
    Since:       nil, // optional: pointer to float64 timestamp
})
```

### RecvSimple(wait int, unreadOnly, includeSelf bool, limit int) ([]Message, error)

Backward-compatible wrapper for `Recv()` with positional args.

```go
messages, err := client.RecvSimple(30, true, false, 10)
```

#### RecvOpts fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `Wait` | `float64` | `0` | Block up to N seconds for at least one message |
| `UnreadOnly` | `bool` | `true` | Only return unread messages |
| `IncludeSelf` | `bool` | `false` | Include messages from this agent |
| `Limit` | `int` | `0` | Max messages to return (`0` = unlimited) |
| `Since` | `*float64` | `nil` | Filter to messages after this timestamp |

### Peek(limit int) ([]Message, error)

View recent messages without marking as read.

```go
recent, err := client.Peek(50)
```

### ListPeers() ([]Peer, error)

Get registered agents.

```go
peers, err := client.ListPeers()
for _, p := range peers {
	fmt.Println(p.ID, p.Status)
}
```

### SetStatus(status string) (float64, error)

Update agent status (active/idle/done/blocked). Returns last_seen timestamp.
Returns an error if the status is not one of the valid values or if the agent
is not registered.

```go
client.SetStatus("done")
```

### GetStatus(agentID string) (string, error)

Check agent status.

```go
status, err := client.GetStatus("bob")
```

### SearchFTS(query string, limit int) ([]Message, error)

Full-text search using SQLite FTS5. Requires the binary to be built with
`-tags fts5`. Falls back to LIKE-based search if FTS5 is unavailable.

```go
results, err := client.SearchFTS("important", 100)
```

### Search(query string, limit int) ([]Message, error)

Search messages by substring (case-insensitive). Returns an error if the
query is empty or limit is not a positive integer.

```go
results, err := client.Search("important", 100)
```

### Thread(threadID string) ([]Message, error)

Get all messages in a thread.

```go
messages, err := client.Thread("42")
```

### Stats() (*Stats, error)

Get aggregated bus statistics.

```go
stats, err := client.Stats()
fmt.Printf("Total messages: %d\n", stats.Messages)
```

### StatsJSON() (string, error)

Get stats as JSON string.

```go
jsonStr, err := client.StatsJSON()
```

### InitProject() error

Create the database and schema. No-op if already exists. Migrates older
schemas that lack the `ttl_seconds` column.

```go
client.InitProject()
```

### Register(role, prompt, cli string, pid *int, upsert bool) (bool, error)

Register this agent on the bus. If `upsert` is true, updates existing
registration instead of failing. The `pid` parameter is a pointer to an
int — pass `nil` to omit the process ID, or `&pidVar` for a specific PID.

```go
client.AgentID = "alice"
client.Register("planner", "Plan things", "claude", nil, true)
```

### Unregister() error

Remove this agent from the bus.

```go
client.Unregister()
```

### Touch() error

Update the agent's `last_seen` timestamp to now.

```go
client.Touch()
```

### CleanupExpired() (int, error)

Delete messages that have exceeded their TTL. Returns count of deleted
messages. Called automatically by `Recv()` and `Peek()`.

```go
deleted, err := client.CleanupExpired()
```

### List() ([]Peer, error)

Alias for `ListPeers()`. Returns all registered agents.

```go
peers, err := client.List()
```

### Status(newStatus string) (*string, error)

Set or get agent status. If `newStatus` is one of `active`, `idle`, `done`,
`blocked`, updates the status and returns the previous status as a pointer.
Returns `nil` for the previous status if the agent was not previously
registered.

```go
old, err := client.Status("active")
```

### AgentExists(agentID string) (bool, error)

Check whether an agent is registered on the bus.

```go
exists, err := client.AgentExists("bob")
```

### Wait(count int, timeoutSec float64) (bool, error)

Block until at least `count` unread messages exist for this agent, or
until `timeoutSec` seconds elapse. Returns true if the desired message
count was reached, false if the timeout elapsed first.

```go
found, err := client.Wait(1, 30)
```

### Clear() error

Delete the entire database file. All bus data is lost.

```go
client.Clear()
```

### ProjectInfo() map[string]interface{}

Returns resolved project metadata: project name, database path, and
whether the database file exists.

```go
info := client.ProjectInfo()
fmt.Println(info["db"], info["exists"])
```

## Example: Task Worker

```go
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"time"
	"a2a"
)

type Task struct {
	ID   string `json:"id"`
	Work string `json:"work"`
}

func main() {
	client := a2a.NewClient("production", "worker-1")
	client.SetStatus("active")

	for {
		// Wait for task (30 second timeout)
		messages, err := client.Recv(a2a.RecvOpts{Wait: 30, UnreadOnly: true, IncludeSelf: false, Limit: 1})
		if err != nil {
			log.Fatal(err)
		}

		if len(messages) == 0 {
			fmt.Println("No tasks, exiting")
			break
		}

		// Parse task
		var task Task
		err = json.Unmarshal([]byte(messages[0].Body), &task)
		if err != nil {
			continue
		}

		fmt.Printf("Processing task %s: %s\n", task.ID, task.Work)

		// Do work
		time.Sleep(1 * time.Second)

		// Report completion
		result := map[string]interface{}{
			"task_id": task.ID,
			"status":  "complete",
			"time":    time.Now().Format(time.RFC3339),
		}
		resultJSON, _ := json.Marshal(result)
		client.Send("coordinator", string(resultJSON), "", nil)
	}

	client.SetStatus("done")
}
```

## Deployment

### Docker

```dockerfile
FROM golang:1.20-alpine
WORKDIR /app
COPY . .
RUN go build -o worker .
CMD ["./worker"]
```

### Kubernetes

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: a2a-worker
spec:
  template:
    spec:
      containers:
      - name: worker
        image: a2a-worker:latest
        volumeMounts:
        - name: a2a-data
          mountPath: /.a2a
      volumes:
      - name: a2a-data
        emptyDir: {}
```

## Performance

Direct database access:
- send(): ~5ms
- recv(): ~10ms per poll
- search(): ~20ms for 1000 messages

## See Also

- [CLIENT_API.md](CLIENT_API.md) — Python client
- [NODE_CLIENT_API.md](NODE_CLIENT_API.md) — Node.js client
- [REST_API.md](REST_API.md) — HTTP interface
