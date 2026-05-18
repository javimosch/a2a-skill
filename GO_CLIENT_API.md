# a2a Go Client Library

The `a2a_client.go` module provides a Go API for a2a messaging, enabling integration with Go-based systems, microservices, and CLIs.

## Installation

```bash
# Add to your go.mod
go get github.com/mattn/go-sqlite3
go get github.com/mattn/go-sqlite3

# Copy a2a_client.go to your project
cp a2a_client.go .
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
	msgID, err := client.Send("bob", "Hello Bob!", nil)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("Sent message %d\n", msgID)

	// Receive messages (blocks up to 10 seconds)
	messages, err := client.Recv(10, true, false, 0)
	if err != nil {
		log.Fatal(err)
	}
	for _, msg := range messages {
		fmt.Printf("%s: %s\n", msg.Sender, msg.Body)
	}

	// Broadcast
	client.Send("all", "Hello everyone!", nil)

	// Mark done
	client.SetStatus("done")
}
```

## API Reference

### NewClient(project, agentID string) *Client

Create a new client.

### Send(to, message string, ttlSeconds *int) (int64, error)

Send a message. Set `to` to "all", "*", or "broadcast" for broadcast messages.

```go
ttl := 3600
msgID, err := client.Send("bob", "Hello", &ttl)
```

### Recv(wait int, unreadOnly, includeSelf bool, limit int) ([]Message, error)

Receive messages. Returns after finding messages, or after `wait` seconds.

```go
messages, err := client.Recv(30, true, false, 10)
```

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

### SetStatus(status string) error

Update agent status (active/idle/done/blocked).

```go
client.SetStatus("done")
```

### GetStatus(agentID string) (string, error)

Check agent status.

```go
status, err := client.GetStatus("bob")
```

### Search(query string, limit int) ([]Message, error)

Search messages by substring (case-insensitive).

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
		messages, err := client.Recv(30, true, false, 1)
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
		client.Send("coordinator", string(resultJSON), nil)
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
