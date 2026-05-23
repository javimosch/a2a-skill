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
pub struct Client {
    pub project: String,
    pub agent_id: String,
    db_path: PathBuf,
}

impl Client {
    /// Create new a2a client
    pub fn new(project: impl Into<String>, agent_id: impl Into<String>) -> Result<Self, ValidationError> {
        let project = project.into();
        let agent_id = agent_id.into();
        if project.trim().is_empty() {
            return Err(ValidationError("project must not be empty".to_string()));
        }
        if agent_id.trim().is_empty() {
            return Err(ValidationError("agent_id must not be empty".to_string()));
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
    pub fn send(&self, to: &str, message: &str, ttl_seconds: Option<i64>) -> SqliteResult<i64> {
        if to.trim().is_empty() {
            return Err(rusqlite::Error::InvalidParameterName(
                "recipient must not be empty".to_string(),
            ));
        }
        if let Some(ttl) = ttl_seconds {
            if ttl <= 0 {
                return Err(rusqlite::Error::InvalidParameterName(
                    "ttl_seconds must be a positive number".to_string(),
                ));
            }
        }
        let conn = self.connect()?;
        let recipient = match to {
            "all" | "*" | "broadcast" => None,
            other => Some(other.to_string()),
        };

        conn.execute(
            "INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![&self.agent_id, recipient, message, ttl_seconds, Self::now()],
        )?;

        Ok(conn.last_insert_rowid())
    }

    /// Receive messages
    pub fn recv(
        &self,
        wait: u64,
        unread_only: bool,
        include_self: bool,
        limit: Option<i64>,
    ) -> SqliteResult<Vec<Message>> {
        let deadline = if wait > 0 {
            Some(SystemTime::now() + Duration::from_secs(wait))
        } else {
            None
        };

        loop {
            let conn = self.connect()?;
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
             WHERE body LIKE ?1 ORDER BY created_at DESC LIMIT ?2",
        )?;

        let messages = stmt.query_map(params![format!("%{}%", query), limit], |row| {
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
}
