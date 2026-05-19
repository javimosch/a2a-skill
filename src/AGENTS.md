# AGENTS.md — src/

Rust client library for the a2a bus. Single file: `lib.rs`.

## Purpose

`src/lib.rs` provides a `Client` struct for Rust agents to send, receive, and
manage messages on the same SQLite bus used by the Python CLI and all other
language clients. The Cargo workspace is defined in `../Cargo.toml`.

## WAL invariant (fixed in v1.3.1)

`Client::connect()` creates the parent directory and applies the WAL invariant:

```rust
fn connect(&self) -> SqliteResult<Connection> {
    if let Some(parent) = self.db_path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let conn = Connection::open(&self.db_path)?;
    conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;")?;
    Ok(conn)
}
```

No prior `a2a init` required. All language clients (Python, JS, Go, Rust) now
apply this pattern consistently.

## Public API

| Method | Description |
|--------|-------------|
| `Client::new(project, agent_id)` | Create client |
| `send(to, message, ttl_seconds)` | Send direct or broadcast (`"all"`) |
| `recv(wait_seconds)` | Poll inbox, blocks up to N seconds |
| `peek(limit)` | Observer view — does not mark read |
| `list()` | Return all registered agents |
| `register(role, prompt)` | Register this agent |
| `status(status_str)` | Update own status |
| `stats()` | Return bus statistics |

## Adding new methods

Mirror the Python `a2a_client.py` API surface. When `a2a.py` adds a new
command, add the corresponding method here. Method names should match the
Python client's snake_case convention.

## Dependencies (`Cargo.toml`)

- `rusqlite` — SQLite bindings (bundled feature preferred for portability)
- `serde`, `serde_json` — serialization
- `chrono` or `std::time` — timestamps

Do not add async runtime dependencies (tokio, async-std) to `lib.rs`. If
async Rust support is needed, create `lib_async.rs` following the same
pattern as `a2a_client.py` → `a2a_client_async.py`.

## Building

```bash
cargo build            # from project root
cargo test             # Rust unit tests (if any)
```

The `examples/task_worker.rs` example includes `lib.rs` directly via `#[path]`
for portability outside the Cargo workspace. Standalone copies should
carry their own Cargo.toml.

## Go and Node clients

`a2a_client.go` and `a2a_client.js` live at the project root, not in `src/`.
All three were upgraded in v1.3.1 to apply the WAL invariant on every connection.
