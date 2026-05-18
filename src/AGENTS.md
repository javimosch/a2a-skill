# AGENTS.md — src/

Rust client library for the a2a bus. Single file: `lib.rs`.

## Purpose

`src/lib.rs` provides a `Client` struct for Rust agents to send, receive, and
manage messages on the same SQLite bus used by the Python CLI and all other
language clients. The Cargo workspace is defined in `../Cargo.toml`.

## Known gap: WAL mode and mkdir

`Client::connect()` currently calls `Connection::open()` without:
1. Creating the parent directory (`~/.a2a/{project}/`)
2. Setting `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`

**This means the Rust client requires `a2a init` to have run before first use.**
It will panic if the directory does not exist, and will use SQLite's default
`delete` journal mode (which breaks concurrent writes from multiple agents).

Fix before shipping Rust agents in production:

```rust
fn connect(&self) -> SqliteResult<Connection> {
    std::fs::create_dir_all(self.db_path.parent().unwrap()).ok();
    let conn = Connection::open(&self.db_path)?;
    conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;")?;
    Ok(conn)
}
```

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
They have the same WAL/mkdir gap as this Rust client. Apply the same fix
pattern when updating them.
