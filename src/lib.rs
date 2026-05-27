use rusqlite::{Connection, params, Result as SqliteResult};
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH, Duration};
use serde::{Serialize, Deserialize};
use std::thread;

/// Error type for a2a client validation errors
#[derive(Debug, Clone)]
pub struct ValidationError(pub String);

impl std::fmt::Display for ValidationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for ValidationError {}

/// Message in the a2a bus
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub id: i64,
    pub sender: String,
    pub recipient: Option<String>,
    pub body: String,
    pub thread_id: Option<String>,
    pub created_at: f64,
}

/// Agent on the bus
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Peer {
    pub id: String,
    pub role: Option<String>,
    pub status: String,
    pub cli: Option<String>,
}

/// Project information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectInfo {
    pub project: String,
    pub db: String,
    pub exists: bool,
}

/// Bus statistics
#[derive(Debug, Serialize, Deserialize)]
pub struct Stats {
    pub messages: i64,
    pub direct_messages: i64,
    pub broadcasts: i64,
    pub threads: i64,
    pub agents_active: i64,
    pub agents_done: i64,
    pub top_senders: Vec<TopSender>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct TopSender {
    pub agent: String,
    pub count: i64,
}

/// a2a client for Rust
#[derive(Debug)]
pub struct Client {
    pub project: String,
    pub agent_id: String,
    db_path: PathBuf,
}

// Max length constants matching Python clients
const MAX_AGENT_ID_LENGTH: usize = 256;
const MAX_THREAD_ID_LENGTH: usize = 256;
const MAX_BODY_LENGTH: usize = 100_000;
const MAX_ROLE_LENGTH: usize = 512;

impl Client {
    /// Create new a2a client
    pub fn new(project: impl Into<String>, agent_id: impl Into<String>) -> Result<Self, ValidationError> {
        let project = project.into();
        let agent_id = agent_id.into();
        if project.trim().is_empty() {
            return Err(ValidationError("project must not be empty".to_string()));
        }
        if project.contains('/') || project.contains('\\') || project.starts_with('.') {
            return Err(ValidationError(
                "project must not contain path separators or start with dot".to_string(),
            ));
        }
        if agent_id.trim().is_empty() {
            return Err(ValidationError("agent_id must not be empty".to_string()));
        }
        if agent_id.len() > MAX_AGENT_ID_LENGTH {
            return Err(ValidationError(format!(
                "agent_id too long ({} chars, max {})",
                agent_id.len(),
                MAX_AGENT_ID_LENGTH
            )));
        }
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        let db_path = PathBuf::from(home)
            .join(".a2a")
            .join(&project)
            .join("database.db");

        Ok(Client {
            project,
            agent_id,
            db_path,
        })
    }

    /// Connect to database applying the WAL invariant.
    /// Creates the parent directory if it does not exist.
    fn connect(&self) -> SqliteResult<Connection> {
        if let Some(parent) = self.db_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let conn = Connection::open(&self.db_path)?;
        conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;")?;
        Ok(conn)
    }

    /// Get current timestamp
    fn now() -> f64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs_f64()
    }

    /// Send a message
    pub fn send(&self, to: &str, message: &str, ttl_seconds: Option<i64>, thread_id: Option<&str>) -> SqliteResult<i64> {
        if to.trim().is_empty() {
            return Err(rusqlite::Error::InvalidParameterName(
                "recipient must not be empty".to_string(),
            ));
        }
        if message.len() > MAX_BODY_LENGTH {
            return Err(rusqlite::Error::InvalidParameterName(format!(
                "message body too long ({} chars, max {})",
                message.len(),
                MAX_BODY_LENGTH
            )));
        }
        if let Some(ttl) = ttl_seconds {
            if ttl <= 0 {
                return Err(rusqlite::Error::InvalidParameterName(
                    "ttl_seconds must be a positive number".to_string(),
                ));
            }
        }
        if let Some(tid) = thread_id {
            if tid.trim().is_empty() {
                return Err(rusqlite::Error::InvalidParameterName(
                    "thread_id must not be empty".to_string(),
                ));
            }
            if tid.len() > MAX_THREAD_ID_LENGTH {
                return Err(rusqlite::Error::InvalidParameterName(format!(
                    "thread_id too long ({} chars, max {})",
                    tid.len(),
                    MAX_THREAD_ID_LENGTH
                )));
            }
        }
        let conn = self.connect()?;

        // Validate sender exists
        let sender_exists: bool = conn.query_row(
            "SELECT COUNT(1) FROM agents WHERE id = ?1",
            params![&self.agent_id],
            |row| row.get::<_, i64>(0),
        ).map(|c| c > 0).unwrap_or(false);
        if !sender_exists {
            return Err(rusqlite::Error::InvalidParameterName(
                format!("unknown sender '{}' — register first", self.agent_id),
            ));
        }

        let recipient = match to.to_lowercase().as_str() {
            "all" | "*" | "broadcast" => None,
            other => Some(to.to_string()),
        };

        // Validate recipient exists (for non-broadcast)
        if let Some(ref recip) = recipient {
            let recip_exists: bool = conn.query_row(
                "SELECT COUNT(1) FROM agents WHERE id = ?1",
                params![recip],
                |row| row.get::<_, i64>(0),
            ).map(|c| c > 0).unwrap_or(false);
            if !recip_exists {
                return Err(rusqlite::Error::InvalidParameterName(
                    format!("unknown recipient '{}' — register them first", recip),
                ));
            }
        }

        conn.execute(
            "INSERT INTO messages(sender, recipient, body, thread_id, ttl_seconds, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![&self.agent_id, recipient, message, thread_id, ttl_seconds, Self::now()],
        )?;

        Ok(conn.last_insert_rowid())
    }

    /// Receive messages
    pub fn recv(
        &self,
        wait: f64,
        unread_only: bool,
        include_self: bool,
        limit: Option<i64>,
    ) -> SqliteResult<Vec<Message>> {
        let deadline = if wait > 0.0 {
            Some(SystemTime::now() + Duration::from_secs_f64(wait))
        } else {
            None
        };

        loop {
            let conn = self.connect()?;

            // Clean up expired TTL messages using float epoch (matches Go/Python)
            let now = SystemTime::now()
                .duration_since(SystemTime::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs_f64();
            conn.execute(
                "DELETE FROM messages WHERE ttl_seconds IS NOT NULL AND created_at + ttl_seconds < ?",
                params![now],
            )?;

            let mut params: Vec<&dyn rusqlite::ToSql> = vec![&self.agent_id];

            // Filter out self if requested
            let filter_self = if !include_self {
                format!(" AND sender != ?{}", params.len() + 1)
            } else {
                String::new()
            };

            // Filter unread if requested
            let filter_unread = if unread_only {
                format!(
                    " AND NOT EXISTS (SELECT 1 FROM reads WHERE agent_id = ?{} AND message_id = messages.id)",
                    params.len() + 1
                )
            } else {
                String::new()
            };

            let mut query = format!(
                "SELECT id, sender, recipient, body, thread_id, created_at FROM messages \
                 WHERE (recipient = ?1 OR recipient IS NULL){}{}",
                filter_self, filter_unread
            );

            if !include_self {
                params.push(&self.agent_id);
            }
            if unread_only {
                params.push(&self.agent_id);
            }

            query.push_str(" ORDER BY created_at ASC");
            if let Some(l) = limit {
                query.push_str(&format!(" LIMIT {}", l));
            }

            let mut stmt = conn.prepare(&query)?;
            let messages = stmt.query_map(&params[..], |row| {
                Ok(Message {
                    id: row.get(0)?,
                    sender: row.get(1)?,
                    recipient: row.get(2)?,
                    body: row.get(3)?,
                    thread_id: row.get(4)?,
                    created_at: row.get(5)?,
                })
            })?
            .collect::<SqliteResult<Vec<_>>>()?;

            if !messages.is_empty() {
                // Mark as read
                let ts = Self::now();
                for msg in &messages {
                    let _ = conn.execute(
                        "INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) VALUES (?1, ?2, ?3)",
                        params![&self.agent_id, msg.id, ts],
                    );
                }
                return Ok(messages);
            }

            if let Some(deadline) = deadline {
                if SystemTime::now() >= deadline {
                    return Ok(Vec::new());
                }
                thread::sleep(Duration::from_millis(100));
            } else {
                return Ok(Vec::new());
            }
        }
    }

    /// Peek at recent messages without marking read
    pub fn peek(&self, limit: i64) -> SqliteResult<Vec<Message>> {
        if limit <= 0 {
            return Err(rusqlite::Error::InvalidParameterName(
                "limit must be a positive integer".to_string(),
            ));
        }
        let conn = self.connect()?;

        // Clean up expired TTL messages using float epoch (matches recv())
        let now = Self::now();
        conn.execute(
            "DELETE FROM messages WHERE ttl_seconds IS NOT NULL AND created_at + ttl_seconds < ?1",
            params![now],
        )?;

        let mut stmt = conn.prepare(
            "SELECT id, sender, recipient, body, thread_id, created_at FROM messages \
             ORDER BY created_at DESC LIMIT ?1",
        )?;

        let messages = stmt
            .query_map(params![limit], |row| {
                Ok(Message {
                    id: row.get(0)?,
                    sender: row.get(1)?,
                    recipient: row.get(2)?,
                    body: row.get(3)?,
                    thread_id: row.get(4)?,
                    created_at: row.get(5)?,
                })
            })?
            .collect::<SqliteResult<Vec<_>>>()?;

        Ok(messages.into_iter().rev().collect())
    }

    /// List agents — alias for list_peers
    pub fn list(&self) -> SqliteResult<Vec<Peer>> {
        self.list_peers()
    }

    /// List agents
    pub fn list_peers(&self) -> SqliteResult<Vec<Peer>> {
        let conn = self.connect()?;
        let mut stmt = conn.prepare(
            "SELECT id, role, cli, status FROM agents ORDER BY created_at",
        )?;

        let peers = stmt.query_map([], |row| {
            Ok(Peer {
                id: row.get(0)?,
                role: row.get(1)?,
                cli: row.get(2)?,
                status: row.get(3)?,
            })
        })?
        .collect::<SqliteResult<Vec<_>>>()?;

        Ok(peers)
    }

    /// Get or set this agent's status.
    ///
    /// If `new_status` is Some, sets the status and returns Ok(None).
    /// If `new_status` is None, returns the current status.
    pub fn status(&self, new_status: Option<&str>) -> SqliteResult<Option<String>> {
        match new_status {
            Some(s) => self.set_status(s).map(|_| None),
            None => self.get_status(None),
        }
    }

    /// Set agent status
    pub fn set_status(&self, status: &str) -> SqliteResult<()> {
        let valid_statuses = ["active", "idle", "done", "blocked"];
        if !valid_statuses.contains(&status) {
            return Err(rusqlite::Error::InvalidParameterName(
                format!("invalid status '{}' — must be one of: active, idle, done, blocked", status),
            ));
        }
        let conn = self.connect()?;
        conn.execute(
            "UPDATE agents SET status = ?1, last_seen = ?2 WHERE id = ?3",
            params![status, Self::now(), &self.agent_id],
        )?;
        Ok(())
    }

    /// Get agent status
    pub fn get_status(&self, agent_id: Option<&str>) -> SqliteResult<Option<String>> {
        let agent = agent_id.unwrap_or(&self.agent_id);
        let conn = self.connect()?;
        let mut stmt = conn.prepare("SELECT status FROM agents WHERE id = ?1")?;

        let status = stmt.query_row(params![agent], |row| row.get(0)).ok();
        Ok(status)
    }

    /// Register this agent on the bus
    pub fn register(&self, role: &str, prompt: &str, cli: &str, pid: Option<i32>, upsert: bool) -> SqliteResult<bool> {
        if role.len() > MAX_ROLE_LENGTH {
            return Err(rusqlite::Error::InvalidParameterName(format!(
                "role too long ({} chars, max {MAX_ROLE_LENGTH})",
                role.len()
            )));
        }
        if cli.len() > 128 {
            return Err(rusqlite::Error::InvalidParameterName(format!(
                "cli too long ({} chars, max 128)",
                cli.len()
            )));
        }
        if prompt.len() > MAX_BODY_LENGTH {
            return Err(rusqlite::Error::InvalidParameterName(format!(
                "prompt too long ({} chars, max {})",
                prompt.len(),
                MAX_BODY_LENGTH
            )));
        }
        let conn = self.connect()?;
        let now = Self::now();
        if upsert {
            conn.execute(
                "INSERT OR IGNORE INTO agents(id, role, prompt, cli, status, pid, last_seen, created_at) VALUES (?1, ?2, ?3, ?4, 'active', ?5, ?6, ?6)",
                params![&self.agent_id, role, prompt, cli, pid, now],
            )?;
            conn.execute(
                "UPDATE agents SET role=COALESCE(NULLIF(?1,''),role), prompt=COALESCE(NULLIF(?2,''),prompt), cli=COALESCE(NULLIF(?3,''),cli), status='active', pid=COALESCE(?4,pid), last_seen=?5 WHERE id=?6",
                params![role, prompt, cli, pid, now, &self.agent_id],
            )?;
        } else {
            conn.execute(
                "INSERT INTO agents(id, role, prompt, cli, status, pid, last_seen, created_at) VALUES (?1, ?2, ?3, ?4, 'active', ?5, ?6, ?6)",
                params![&self.agent_id, role, prompt, cli, pid, now],
            )?;
        }
        Ok(true)
    }

    /// Unregister this agent from the bus
    pub fn unregister(&self) -> SqliteResult<bool> {
        let conn = self.connect()?;
        conn.execute("DELETE FROM agents WHERE id = ?1", params![&self.agent_id])?;
        Ok(true)
    }

    /// Search messages
    pub fn search(&self, query: &str, limit: i64) -> SqliteResult<Vec<Message>> {
        if query.trim().is_empty() {
            return Err(rusqlite::Error::InvalidParameterName(
                "search query must not be empty".to_string(),
            ));
        }
        if limit <= 0 {
            return Err(rusqlite::Error::InvalidParameterName(
                "limit must be a positive integer".to_string(),
            ));
        }
        let conn = self.connect()?;
        let mut stmt = conn.prepare(
            "SELECT id, sender, recipient, body, thread_id, created_at FROM messages \
             WHERE LOWER(body) LIKE ?1 ORDER BY created_at DESC LIMIT ?2",
        )?;

        let messages = stmt.query_map(params![format!("%{}%", query.to_lowercase()), limit], |row| {
            Ok(Message {
                id: row.get(0)?,
                sender: row.get(1)?,
                recipient: row.get(2)?,
                body: row.get(3)?,
                thread_id: row.get(4)?,
                created_at: row.get(5)?,
            })
        })?
        .collect::<SqliteResult<Vec<_>>>()?;

        Ok(messages)
    }

    /// Get thread
    pub fn thread(&self, thread_id: &str) -> SqliteResult<Vec<Message>> {
        if thread_id.trim().is_empty() {
            return Err(rusqlite::Error::InvalidParameterName(
                "thread id must not be empty".to_string(),
            ));
        }
        let conn = self.connect()?;
        let mut stmt = conn.prepare(
            "SELECT id, sender, recipient, body, thread_id, created_at FROM messages \
             WHERE thread_id = ?1 ORDER BY created_at ASC",
        )?;

        let messages = stmt.query_map(params![thread_id], |row| {
            Ok(Message {
                id: row.get(0)?,
                sender: row.get(1)?,
                recipient: row.get(2)?,
                body: row.get(3)?,
                thread_id: row.get(4)?,
                created_at: row.get(5)?,
            })
        })?
        .collect::<SqliteResult<Vec<_>>>()?;

        Ok(messages)
    }

    /// Get statistics
    pub fn stats(&self) -> SqliteResult<Stats> {
        let conn = self.connect()?;

        let messages: i64 = conn.query_row(
            "SELECT COUNT(*) FROM messages",
            [],
            |row| row.get(0),
        )?;

        let broadcasts: i64 = conn.query_row(
            "SELECT COUNT(*) FROM messages WHERE recipient IS NULL",
            [],
            |row| row.get(0),
        )?;

        let threads: i64 = conn.query_row(
            "SELECT COUNT(DISTINCT thread_id) FROM messages WHERE thread_id IS NOT NULL",
            [],
            |row| row.get(0),
        )?;

        let agents_active: i64 = conn.query_row(
            "SELECT COUNT(*) FROM agents WHERE status = 'active'",
            [],
            |row| row.get(0),
        ).unwrap_or(0);

        let agents_done: i64 = conn.query_row(
            "SELECT COUNT(*) FROM agents WHERE status = 'done'",
            [],
            |row| row.get(0),
        ).unwrap_or(0);

        let mut stmt = conn.prepare(
            "SELECT sender, COUNT(*) as count FROM messages \
             GROUP BY sender ORDER BY count DESC LIMIT 5",
        )?;

        let top_senders = stmt
            .query_map([], |row| {
                Ok(TopSender {
                    agent: row.get(0)?,
                    count: row.get(1)?,
                })
            })?
            .collect::<SqliteResult<Vec<_>>>()?;

        Ok(Stats {
            messages,
            direct_messages: messages - broadcasts,
            broadcasts,
            threads,
            agents_active,
            agents_done,
            top_senders,
        })
    }

    /// Wait for N unread messages with timeout.
    ///
    /// Blocks up to `timeout_secs` seconds, polling the bus every 200ms,
    /// until `count` unread messages arrive. Returns true if the required
    /// count was reached before timeout.
    pub fn wait(&self, count: i64, timeout_secs: f64) -> SqliteResult<bool> {
        let deadline = SystemTime::now() + Duration::from_secs_f64(timeout_secs);
        let mut remaining = count;
        loop {
            if remaining <= 0 {
                return Ok(true);
            }
            if SystemTime::now() >= deadline {
                return Ok(false);
            }
            let msgs = self.recv(1.0, true, false, Some(remaining))?;
            remaining -= msgs.len() as i64;
            if remaining <= 0 {
                return Ok(true);
            }
            thread::sleep(Duration::from_millis(200));
        }
    }

    /// Initialize the project database, creating tables if they don't exist.
    ///
    /// Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS.
    pub fn init_project(&self) -> SqliteResult<()> {
        let conn = self.connect()?;
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS agents (
                id          TEXT PRIMARY KEY,
                role        TEXT,
                prompt      TEXT,
                cli         TEXT,
                status      TEXT NOT NULL DEFAULT 'active',
                pid         INTEGER,
                created_at  REAL NOT NULL,
                last_seen   REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sender      TEXT NOT NULL,
                recipient   TEXT,
                body        TEXT NOT NULL,
                thread_id   TEXT,
                ttl_seconds INTEGER,
                created_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reads (
                agent_id    TEXT NOT NULL,
                message_id  INTEGER NOT NULL,
                read_at     REAL NOT NULL,
                PRIMARY KEY (agent_id, message_id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient);
            CREATE INDEX IF NOT EXISTS idx_messages_thread    ON messages(thread_id);
            CREATE INDEX IF NOT EXISTS idx_messages_created   ON messages(created_at);",
        )?;
        Ok(())
    }

    /// Delete the project database and all WAL-related files.
    ///
    /// Warning: This permanently deletes all messages and agent registrations.
    pub fn clear(&self) -> SqliteResult<()> {
        for suffix in &["", "-wal", "-shm"] {
            let actual = if suffix.is_empty() {
                self.db_path.clone()
            } else {
                let mut s = self.db_path.to_string_lossy().to_string();
                s.push_str(suffix);
                std::path::PathBuf::from(s)
            };
            let _ = std::fs::remove_file(&actual);
        }
        Ok(())
    }

    /// Get resolved project information.
    pub fn project_info(&self) -> ProjectInfo {
        ProjectInfo {
            project: self.project.clone(),
            db: self.db_path.to_string_lossy().to_string(),
            exists: self.db_path.exists(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_client_creation() {
        let client = Client::new("test", "alice").unwrap();
        assert_eq!(client.project, "test");
        assert_eq!(client.agent_id, "alice");
    }

    #[test]
    fn test_client_empty_project_rejected() {
        let result = Client::new("", "alice");
        assert!(result.is_err());
        assert!(result.unwrap_err().0.contains("project must not be empty"));
    }

    #[test]
    fn test_client_empty_agent_id_rejected() {
        let result = Client::new("test", "");
        assert!(result.is_err());
        assert!(result.unwrap_err().0.contains("agent_id must not be empty"));
    }

    #[test]
    fn test_client_db_path() {
        let client = Client::new("myproject", "bob").unwrap();
        assert!(client.db_path.to_string_lossy().contains(".a2a"));
        assert!(client.db_path.to_string_lossy().contains("myproject"));
    }

    #[test]
    fn test_now_timestamp() {
        let ts1 = Client::now();
        let ts2 = Client::now();
        assert!(ts1 > 0.0);
        assert!(ts2 >= ts1);
    }

    #[test]
    fn test_message_struct() {
        let msg = Message {
            id: 1,
            sender: "alice".to_string(),
            recipient: Some("bob".to_string()),
            body: "Hello".to_string(),
            thread_id: None,
            created_at: 1234567890.5,
        };
        assert_eq!(msg.id, 1);
        assert_eq!(msg.sender, "alice");
        assert_eq!(msg.body, "Hello");
    }

    #[test]
    fn test_peer_struct() {
        let peer = Peer {
            id: "alice".to_string(),
            role: Some("worker".to_string()),
            status: "active".to_string(),
            cli: Some("a2a".to_string()),
        };
        assert_eq!(peer.id, "alice");
        assert_eq!(peer.status, "active");
    }

    #[test]
    fn test_stats_struct() {
        let stats = Stats {
            messages: 100,
            direct_messages: 80,
            broadcasts: 20,
            threads: 5,
            agents_active: 2,
            agents_done: 1,
            top_senders: vec![],
        };
        assert_eq!(stats.messages, 100);
        assert_eq!(stats.direct_messages, 80);
        assert_eq!(stats.broadcasts, 20);
    }

    #[test]
    fn test_search_rejects_empty_query() {
        let client = Client::new("test_search_query", "tester").unwrap();
        let result = client.search("", 10);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("query must not be empty"));
    }

    #[test]
    fn test_search_rejects_non_positive_limit() {
        let client = Client::new("test_search_limit", "tester").unwrap();
        let result = client.search("hello", 0);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("limit must be a positive integer"));

        let result = client.search("hello", -1);
        assert!(result.is_err());
    }

    #[test]
    fn test_send_rejects_empty_recipient() {
        let client = Client::new("test_send_recipient", "tester").unwrap();
        let result = client.send("", "hello", None, None);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("recipient must not be empty"));
    }

    #[test]
    fn test_send_rejects_whitespace_recipient() {
        let client = Client::new("test_send_ws_recip", "tester").unwrap();
        let result = client.send("   ", "hello", None, None);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("recipient must not be empty"));
    }

    #[test]
    fn test_send_rejects_non_positive_ttl() {
        let client = Client::new("test_send_ttl", "tester").unwrap();
        for ttl in &[Some(0), Some(-1), Some(-100)] {
            let result = client.send("bob", "hello", *ttl, None);
            assert!(result.is_err());
            assert!(result.unwrap_err().to_string().contains("ttl_seconds must be a positive number"));
        }
    }

    #[test]
    fn test_send_rejects_empty_thread_id() {
        let client = Client::new("test_send_thread", "tester").unwrap();
        let result = client.send("bob", "hello", None, Some(""));
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("thread_id must not be empty"));

        let result = client.send("bob", "hello", None, Some("   "));
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("thread_id must not be empty"));
    }
}
