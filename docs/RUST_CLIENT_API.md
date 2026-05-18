# a2a Rust Client Library

The `src/lib.rs` module provides a Rust API for a2a messaging, enabling integration with Rust-based systems, CLI tools, and high-performance services.

## Installation

```bash
# Add to your Cargo.toml
[dependencies]
rusqlite = { version = "0.29", features = ["bundled"] }
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"

# Clone the a2a library
cargo new a2a-project
cp src/lib.rs a2a-project/src/
```

## Quick Start

```rust
use a2a::Client;

fn main() {
    // Initialize client
    let client = Client::new("my-project", "alice");

    // Send a message
    match client.send("bob", "Hello Bob!", None) {
        Ok(msg_id) => println!("Sent message {}", msg_id),
        Err(e) => eprintln!("Error: {}", e),
    }

    // Receive messages (blocks up to 10 seconds)
    match client.recv(10, true, false, None) {
        Ok(messages) => {
            for msg in messages {
                println!("{}: {}", msg.sender, msg.body);
            }
        }
        Err(e) => eprintln!("Error: {}", e),
    }

    // Broadcast
    let _ = client.send("all", "Hello everyone!", None);

    // Mark done
    let _ = client.set_status("done");
}
```

## API Reference

### Client::new(project, agent_id) -> Client

Create a new client.

```rust
let client = Client::new("my-project", "alice");
```

### send(to, message, ttl_seconds) -> Result<i64>

Send a message. Set `to` to "all", "*", or "broadcast" for broadcast messages.

```rust
let ttl = Some(3600i64);
match client.send("bob", "Hello", ttl) {
    Ok(msg_id) => println!("Sent: {}", msg_id),
    Err(e) => eprintln!("Error: {}", e),
}
```

### recv(wait, unread_only, include_self, limit) -> Result<Vec<Message>>

Receive messages. Returns after finding messages, or after `wait` seconds.

```rust
match client.recv(30, true, false, Some(10)) {
    Ok(messages) => println!("Received {} messages", messages.len()),
    Err(e) => eprintln!("Error: {}", e),
}
```

### peek(limit) -> Result<Vec<Message>>

View recent messages without marking as read.

```rust
match client.peek(50) {
    Ok(messages) => println!("Recent: {}", messages.len()),
    Err(e) => eprintln!("Error: {}", e),
}
```

### list_peers() -> Result<Vec<Peer>>

Get registered agents.

```rust
match client.list_peers() {
    Ok(peers) => {
        for p in peers {
            println!("{}: {}", p.id, p.status);
        }
    }
    Err(e) => eprintln!("Error: {}", e),
}
```

### set_status(status) -> Result<()>

Update agent status (active/idle/done/blocked).

```rust
client.set_status("done")?;
```

### get_status(agent_id) -> Result<Option<String>>

Check agent status.

```rust
match client.get_status(Some("bob")) {
    Ok(status) => println!("Bob: {:?}", status),
    Err(e) => eprintln!("Error: {}", e),
}
```

### search(query, limit) -> Result<Vec<Message>>

Search messages by substring (case-insensitive).

```rust
match client.search("important", 100) {
    Ok(results) => println!("Found {} messages", results.len()),
    Err(e) => eprintln!("Error: {}", e),
}
```

### thread(thread_id) -> Result<Vec<Message>>

Get all messages in a thread.

```rust
match client.thread("42") {
    Ok(messages) => println!("Thread: {} messages", messages.len()),
    Err(e) => eprintln!("Error: {}", e),
}
```

### stats() -> Result<Stats>

Get aggregated bus statistics.

```rust
match client.stats() {
    Ok(stats) => println!("Total messages: {}", stats.messages),
    Err(e) => eprintln!("Error: {}", e),
}
```

## Example: Task Worker

```rust
use a2a::Client;
use serde_json::{json, from_str};

#[derive(serde::Deserialize)]
struct Task {
    id: String,
    work: String,
}

fn main() {
    let client = Client::new("production", "worker-1");
    let _ = client.set_status("active");

    loop {
        // Wait for task (30 second timeout)
        match client.recv(30, true, false, Some(1)) {
            Ok(messages) => {
                if messages.is_empty() {
                    println!("No tasks, exiting");
                    break;
                }

                // Parse task
                if let Ok(task) = from_str::<Task>(&messages[0].body) {
                    println!("Processing task {}: {}", task.id, task.work);

                    // Do work
                    std::thread::sleep(std::time::Duration::from_secs(1));

                    // Report completion
                    let result = json!({
                        "task_id": task.id,
                        "status": "complete",
                        "time": chrono::Local::now().to_rfc3339()
                    });

                    let _ = client.send(
                        "coordinator",
                        &result.to_string(),
                        None
                    );
                }
            }
            Err(e) => eprintln!("Error: {}", e),
        }
    }

    let _ = client.set_status("done");
}
```

## Building and Testing

```bash
# Build the library
cargo build --release

# Run tests
cargo test

# Build examples
cargo build --examples

# Run example
cargo run --example task_worker
```

## Performance

Direct database access:
- send(): ~5ms
- recv(): ~10ms per poll
- search(): ~20ms for 1000 messages
- Thread-safe with SQLite WAL mode

## Deployment

### Docker

```dockerfile
FROM rust:1.75-alpine
WORKDIR /app
COPY . .
RUN cargo build --release
CMD ["./target/release/worker"]
```

### Systemd

```ini
[Unit]
Description=a2a Rust Worker
After=network.target

[Service]
Type=simple
User=a2a
ExecStart=/opt/a2a/worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## See Also

- [CLIENT_API.md](docs/CLIENT_API.md) — Python client
- [NODE_CLIENT_API.md](docs/NODE_CLIENT_API.md) — Node.js client
- [GO_CLIENT_API.md](docs/GO_CLIENT_API.md) — Go client
- [REST_API.md](docs/REST_API.md) — HTTP interface
