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
    pub priority: i64,
    pub requires_ack: bool,
    pub created_at: f64,
}

/// Task in the shared task queue
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub id: i64,
    pub title: String,
    pub description: Option<String>,
    pub assigned_to: Option<String>,
    pub status: String,
    pub priority: i64,
    pub dependencies: Option<String>,
    pub result: Option<String>,
    pub claimed_at: Option<f64>,
    pub completed_at: Option<f64>,
    pub created_at: f64,
    pub updated_at: f64,
}

/// Stale agent for heartbeat check
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StaleAgent {
    pub id: String,
    pub status: String,
    pub last_seen: f64,
}

/// Agent on the bus
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Peer {
    pub id: String,
    pub role: Option<String>,
    pub status: String,
    pub cli: Option<String>,
    pub pid: Option<i32>,
}

/// Project information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectInfo {
    pub project: String,
    pub db: String,
    pub exists: bool,
}

/// Priority distribution entry
#[derive(Debug, Serialize, Deserialize)]
pub struct PriorityCount {
    pub label: String,
    pub count: i64,
}

/// Bus statistics
#[derive(Debug, Serialize, Deserialize)]
pub struct Stats {
    pub messages: i64,
    pub direct_messages: i64,
    pub broadcasts: i64,
    pub threads: i64,
    pub priority_distribution: Vec<PriorityCount>,
    pub acks_required: i64,
    pub acks_sent: i64,
    pub pending_acks: i64,
    pub agents_active: i64,
    pub agents_done: i64,
    pub tasks_total: i64,
    pub tasks_done: i64,
    pub tasks_blocked: i64,
    pub tasks_by_status: std::collections::HashMap<String, i64>,
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

    /// Send a message with priority and acknowledgment support
    pub fn send(&self, to: &str, message: &str, ttl_seconds: Option<i64>, thread_id: Option<&str>, priority: i64, require_ack: bool) -> SqliteResult<i64> {
        if to.trim().is_empty() {
            return Err(rusqlite::Error::InvalidParameterName(
                "recipient must not be empty".to_string(),
            ));
        }
        if message.trim().is_empty() {
            return Err(rusqlite::Error::InvalidParameterName(
                "message body must not be empty".to_string(),
            ));
        }
        if message.len() > MAX_BODY_LENGTH {
            return Err(rusqlite::Error::InvalidParameterName(format!(
                "message body too long ({} chars, max {})",
                message.len(),
                MAX_BODY_LENGTH
            )));
        }
        if priority < 1 || priority > 4 {
            return Err(rusqlite::Error::InvalidParameterName(
                "priority must be 1-4 (1=URGENT, 2=HIGH, 3=NORMAL, 4=LOW)".to_string(),
            ));
        }
        if let Some(ttl) = ttl_seconds {
            if ttl <= 0 {
                return Err(rusqlite::Error::InvalidParameterName(
                    "ttl_seconds must be a positive number of seconds".to_string(),
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
            _ => Some(to.to_string()),
        };

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

        let ack_val: i64 = if require_ack { 1 } else { 0 };

        conn.execute(
            "INSERT INTO messages(sender, recipient, body, thread_id, ttl_seconds, priority, requires_ack, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            params![&self.agent_id, recipient, message, thread_id, ttl_seconds, priority, ack_val, Self::now()],
        )?;

        Ok(conn.last_insert_rowid())
    }

    /// Receive messages with priority and priority_min support
    pub fn recv(
        &self,
        wait: f64,
        unread_only: bool,
        include_self: bool,
        limit: Option<i64>,
        priority_min: Option<i64>,
    ) -> SqliteResult<Vec<Message>> {
        if wait < 0.0 {
            return Err(rusqlite::Error::InvalidParameterName(
                "wait must be a non-negative number of seconds".to_string(),
            ));
        }
        if !wait.is_finite() {
            return Err(rusqlite::Error::InvalidParameterName(
                "wait must be a finite number".to_string(),
            ));
        }
        if let Some(l) = limit {
            if l < 0 {
                return Err(rusqlite::Error::InvalidParameterName(
                    "limit must be a non-negative integer".to_string(),
                ));
            }
        }
        if let Some(pm) = priority_min {
            if pm < 1 || pm > 4 {
                return Err(rusqlite::Error::InvalidParameterName(
                    "priority_min must be 1-4".to_string(),
                ));
            }
        }
        let deadline = if wait > 0.0 {
            Some(SystemTime::now() + Duration::from_secs_f64(wait))
        } else {
            None
        };

        let conn = self.connect()?;
        let pm_val: Option<i64> = priority_min;

        loop {
            let now = SystemTime::now()
                .duration_since(SystemTime::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs_f64();
            conn.execute(
                "DELETE FROM messages WHERE ttl_seconds IS NOT NULL AND created_at + ttl_seconds < ?",
                params![now],
            )?;

            let _ = conn.execute(
                "UPDATE agents SET last_seen = ?1 WHERE id = ?2",
                params![now, &self.agent_id],
            );

            let mut params: Vec<&dyn rusqlite::ToSql> = vec![&self.agent_id];

            let filter_self = if !include_self {
                format!(" AND sender != ?{}", params.len() + 1)
            } else {
                String::new()
            };

            let filter_unread = if unread_only {
                format!(
                    " AND NOT EXISTS (SELECT 1 FROM reads WHERE agent_id = ?{} AND message_id = messages.id)",
                    params.len() + 1
                )
            } else {
                String::new()
            };

            let filter_priority = if pm_val.is_some() {
                format!(" AND priority <= ?{}", params.len() + 1)
            } else {
                String::new()
            };

            let mut query = format!(
                "SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at FROM messages \
                 WHERE (recipient = ?1 OR recipient IS NULL){}{}{}",
                filter_self, filter_unread, filter_priority
            );

            if !include_self {
                params.push(&self.agent_id);
            }
            if unread_only {
                params.push(&self.agent_id);
            }
            if let Some(ref pm) = pm_val {
                params.push(pm);
            }

            query.push_str(" ORDER BY priority ASC, created_at ASC");
            if let Some(l) = limit {
                query.push_str(&format!(" LIMIT {}", l));
            }

            let mut stmt = conn.prepare(&query)?;
            let messages = stmt.query_map(&params[..], |row| {
                let requires_ack_int: i64 = row.get(6)?;
                Ok(Message {
                    id: row.get(0)?,
                    sender: row.get(1)?,
                    recipient: row.get(2)?,
                    body: row.get(3)?,
                    thread_id: row.get(4)?,
                    priority: row.get(5)?,
                    requires_ack: requires_ack_int != 0,
                    created_at: row.get(7)?,
                })
            })?
            .collect::<SqliteResult<Vec<_>>>()?;

            if !messages.is_empty() {
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

        let now = Self::now();
        conn.execute(
            "DELETE FROM messages WHERE ttl_seconds IS NOT NULL AND created_at + ttl_seconds < ?1",
            params![now],
        )?;

        let mut stmt = conn.prepare(
            "SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at FROM messages \
             ORDER BY created_at DESC LIMIT ?1",
        )?;

        let messages = stmt
            .query_map(params![limit], |row| {
                let requires_ack_int: i64 = row.get(6)?;
                Ok(Message {
                    id: row.get(0)?,
                    sender: row.get(1)?,
                    recipient: row.get(2)?,
                    body: row.get(3)?,
                    thread_id: row.get(4)?,
                    priority: row.get(5)?,
                    requires_ack: requires_ack_int != 0,
                    created_at: row.get(7)?,
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
            "SELECT id, role, cli, status, pid FROM agents ORDER BY created_at",
        )?;

        let peers = stmt.query_map([], |row| {
            Ok(Peer {
                id: row.get(0)?,
                role: row.get(1)?,
                cli: row.get(2)?,
                status: row.get(3)?,
                pid: row.get(4)?,
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
        if let Some(p) = pid {
            if p <= 0 {
                return Err(rusqlite::Error::InvalidParameterName(
                    "pid must be a positive integer".to_string(),
                ));
            }
        }
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
            "SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at FROM messages \
             WHERE LOWER(body) LIKE ?1 ORDER BY created_at DESC LIMIT ?2",
        )?;

        let messages = stmt.query_map(params![format!("%{}%", query.to_lowercase()), limit], |row| {
            let requires_ack_int: i64 = row.get(6)?;
            Ok(Message {
                id: row.get(0)?,
                sender: row.get(1)?,
                recipient: row.get(2)?,
                body: row.get(3)?,
                thread_id: row.get(4)?,
                priority: row.get(5)?,
                requires_ack: requires_ack_int != 0,
                created_at: row.get(7)?,
            })
        })?
        .collect::<SqliteResult<Vec<_>>>()?;

        Ok(messages)
    }

    /// Get thread
    pub fn thread(&self, thread_id: &str) -> SqliteResult<Vec<Message>> {
        if thread_id.trim().is_empty() {
            return Err(rusqlite::Error::InvalidParameterName(
                "thread_id must not be empty".to_string(),
            ));
        }
        if thread_id.len() > MAX_THREAD_ID_LENGTH {
            return Err(rusqlite::Error::InvalidParameterName(format!(
                "thread_id too long ({} chars, max {})",
                thread_id.len(),
                MAX_THREAD_ID_LENGTH
            )));
        }
        let conn = self.connect()?;
        let mut stmt = conn.prepare(
            "SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at FROM messages \
             WHERE thread_id = ?1 ORDER BY created_at ASC",
        )?;

        let messages = stmt.query_map(params![thread_id], |row| {
            let requires_ack_int: i64 = row.get(6)?;
            Ok(Message {
                id: row.get(0)?,
                sender: row.get(1)?,
                recipient: row.get(2)?,
                body: row.get(3)?,
                thread_id: row.get(4)?,
                priority: row.get(5)?,
                requires_ack: requires_ack_int != 0,
                created_at: row.get(7)?,
            })
        })?
        .collect::<SqliteResult<Vec<_>>>()?;

        Ok(messages)
    }

    /// Get statistics with priority distribution, ack stats, and task stats
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

        let mut priority_distribution = Vec::new();
        let mut prio_stmt = conn.prepare(
            "SELECT priority, COUNT(*) FROM messages WHERE priority IS NOT NULL GROUP BY priority ORDER BY priority"
        )?;
        if let Ok(rows) = prio_stmt.query_map([], |row| {
            let prio: i64 = row.get(0)?;
            let count: i64 = row.get(1)?;
            Ok((prio, count))
        }) {
            for row in rows {
                if let Ok((prio, count)) = row {
                        let label = match prio { 1 => "URGENT", 2 => "HIGH", 3 => "NORMAL", 4 => "LOW", _ => "OTHER" }.to_string();
                    priority_distribution.push(PriorityCount { label, count });
                }
            }
        }

        let acks_required: i64 = conn.query_row(
            "SELECT COUNT(*) FROM messages WHERE requires_ack = 1",
            [],
            |row| row.get(0),
        ).unwrap_or(0);

        let acks_sent: i64 = conn.query_row(
            "SELECT COUNT(*) FROM acknowledgments",
            [],
            |row| row.get(0),
        ).unwrap_or(0);

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

        let tasks_total: i64 = conn.query_row(
            "SELECT COUNT(*) FROM tasks",
            [],
            |row| row.get(0),
        ).unwrap_or(0);

        let tasks_done: i64 = conn.query_row(
            "SELECT COUNT(*) FROM tasks WHERE status = 'done'",
            [],
            |row| row.get(0),
        ).unwrap_or(0);

        let tasks_blocked: i64 = conn.query_row(
            "SELECT COUNT(*) FROM tasks WHERE status = 'blocked'",
            [],
            |row| row.get(0),
        ).unwrap_or(0);

        let mut tasks_by_status = std::collections::HashMap::new();
        let mut task_stmt = conn.prepare(
            "SELECT status, COUNT(*) FROM tasks GROUP BY status"
        )?;
        if let Ok(rows) = task_stmt.query_map([], |row| {
            let status: String = row.get(0)?;
            let count: i64 = row.get(1)?;
            Ok((status, count))
        }) {
            for row in rows {
                if let Ok((status, count)) = row {
                    tasks_by_status.insert(status, count);
                }
            }
        }

        Ok(Stats {
            messages,
            direct_messages: messages - broadcasts,
            broadcasts,
            threads,
            priority_distribution,
            acks_required,
            acks_sent,
            pending_acks: if acks_required > acks_sent { acks_required - acks_sent } else { 0 },
            agents_active,
            agents_done,
            tasks_total,
            tasks_done,
            tasks_blocked,
            tasks_by_status,
            top_senders,
        })
    }

    /// Acknowledge receipt of a message
    pub fn ack(&self, message_id: i64) -> SqliteResult<bool> {
        if message_id <= 0 {
            return Err(rusqlite::Error::InvalidParameterName(
                "message_id must be a positive integer".to_string(),
            ));
        }
        let conn = self.connect()?;
        let exists: bool = conn.query_row(
            "SELECT COUNT(1) FROM messages WHERE id = ?1",
            params![message_id],
            |row| row.get::<_, i64>(0),
        ).map(|c| c > 0).unwrap_or(false);
        if !exists {
            return Err(rusqlite::Error::InvalidParameterName(
                format!("message #{} not found", message_id),
            ));
        }
        conn.execute(
            "INSERT OR IGNORE INTO acknowledgments(message_id, agent_id, acked_at) VALUES (?1, ?2, ?3)",
            params![message_id, &self.agent_id, Self::now()],
        )?;
        Ok(true)
    }

    /// Get messages requesting acknowledgment but not yet acked
    pub fn pending_acks(&self) -> SqliteResult<Vec<Message>> {
        let conn = self.connect()?;
        let mut stmt = conn.prepare(
            "SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, m.priority, m.requires_ack, m.created_at \
             FROM messages m WHERE m.requires_ack = 1 AND m.recipient = ?1 \
             AND NOT EXISTS (SELECT 1 FROM acknowledgments a WHERE a.message_id = m.id AND a.agent_id = ?2) \
             ORDER BY m.created_at ASC"
        )?;
        let messages = stmt.query_map(params![&self.agent_id, &self.agent_id], |row| {
            let requires_ack_int: i64 = row.get(6)?;
            Ok(Message {
                id: row.get(0)?,
                sender: row.get(1)?,
                recipient: row.get(2)?,
                body: row.get(3)?,
                thread_id: row.get(4)?,
                priority: row.get(5)?,
                requires_ack: requires_ack_int != 0,
                created_at: row.get(7)?,
            })
        })?.collect::<SqliteResult<Vec<_>>>()?;
        Ok(messages)
    }

    /// Send a heartbeat to keep agent registration alive
    pub fn heartbeat(&self, status: &str) -> SqliteResult<()> {
        let valid = ["active", "working", "idle", "error"];
        if !valid.contains(&status) {
            return Err(rusqlite::Error::InvalidParameterName(
                format!("status must be one of: {:?}", valid),
            ));
        }
        let conn = self.connect()?;
        conn.execute(
            "UPDATE agents SET last_seen = ?1, status = ?2 WHERE id = ?3",
            params![Self::now(), status, &self.agent_id],
        )?;
        Ok(())
    }

    /// Check for agents that missed too many heartbeats
    pub fn heartbeat_check(&self, grace: f64) -> SqliteResult<Vec<StaleAgent>> {
        if grace <= 0.0 {
            return Err(rusqlite::Error::InvalidParameterName(
                "grace must be a positive number of seconds".to_string(),
            ));
        }
        let conn = self.connect()?;
        let threshold = Self::now() - grace;
        let mut stmt = conn.prepare(
            "SELECT id, status, last_seen FROM agents WHERE last_seen < ?1 ORDER BY last_seen"
        )?;
        let stale = stmt.query_map(params![threshold], |row| {
            Ok(StaleAgent {
                id: row.get(0)?,
                status: row.get(1)?,
                last_seen: row.get(2)?,
            })
        })?.collect::<SqliteResult<Vec<_>>>()?;
        Ok(stale)
    }

    /// Create a new task in the shared task queue
    pub fn create_task(&self, title: &str, description: Option<&str>, assigned_to: Option<&str>, priority: i64, depends_on: Option<&[i64]>) -> SqliteResult<i64> {
        if title.trim().is_empty() {
            return Err(rusqlite::Error::InvalidParameterName(
                "task title must not be empty".to_string(),
            ));
        }
        if priority < 1 || priority > 4 {
            return Err(rusqlite::Error::InvalidParameterName(
                "priority must be 1-4".to_string(),
            ));
        }
        let conn = self.connect()?;
        let ts = Self::now();
        let deps_json = depends_on.map(|d| serde_json::to_string(d).unwrap_or_default());
        let deps_ref = deps_json.as_deref();
        conn.execute(
            "INSERT INTO tasks(title, description, assigned_to, status, priority, dependencies, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            params![title, description, assigned_to, "planned", priority, deps_ref, ts, ts],
        )?;
        let task_id = conn.last_insert_rowid();
        if let Some(deps) = depends_on {
            for dep_id in deps {
                conn.execute(
                    "INSERT OR IGNORE INTO task_deps(task_id, depends_on) VALUES (?1, ?2)",
                    params![task_id, dep_id],
                )?;
            }
        }
        Ok(task_id)
    }

    /// List tasks with optional filters
    pub fn list_tasks(&self, status: Option<&str>, assigned_to: Option<&str>) -> SqliteResult<Vec<Task>> {
        let valid_statuses = ["planned", "in_progress", "review_pending", "approved", "done", "blocked"];
        let conn = self.connect()?;
        let mut query = String::from("SELECT id, title, description, assigned_to, status, priority, dependencies, result, claimed_at, completed_at, created_at, updated_at FROM tasks");
        let mut conditions: Vec<String> = Vec::new();
        if let Some(s) = status {
            if !valid_statuses.contains(&s) {
                return Err(rusqlite::Error::InvalidParameterName(
                    format!("invalid status '{}'", s),
                ));
            }
            conditions.push(format!("status = '{}'", s.replace('\'', "''")));
        }
        if let Some(a) = assigned_to {
            conditions.push(format!("assigned_to = '{}'", a.replace('\'', "''")));
        }
        if !conditions.is_empty() {
            query.push_str(" WHERE ");
            query.push_str(&conditions.join(" AND "));
        }
        query.push_str(" ORDER BY priority ASC, created_at DESC");
        let mut stmt = conn.prepare(&query)?;
        let tasks = stmt.query_map([], |row| {
            Ok(Task {
                id: row.get(0)?,
                title: row.get(1)?,
                description: row.get(2)?,
                assigned_to: row.get(3)?,
                status: row.get(4)?,
                priority: row.get(5)?,
                dependencies: row.get(6)?,
                result: row.get(7)?,
                claimed_at: row.get(8)?,
                completed_at: row.get(9)?,
                created_at: row.get(10)?,
                updated_at: row.get(11)?,
            })
        })?.collect::<SqliteResult<Vec<_>>>()?;
        Ok(tasks)
    }

    /// Update task status with state machine validation
    pub fn update_task_status(&self, task_id: i64, new_status: &str) -> SqliteResult<()> {
        let valid_statuses = ["planned", "in_progress", "review_pending", "approved", "done", "blocked"];
        let transitions: std::collections::HashMap<&str, &[&str]> = [
            ("planned", &["in_progress"] as &[&str]),
            ("in_progress", &["review_pending", "blocked", "done"]),
            ("review_pending", &["approved", "in_progress", "blocked"]),
            ("approved", &["done", "in_progress"]),
            ("done", &[]),
            ("blocked", &["in_progress"]),
        ].iter().cloned().collect();

        if task_id <= 0 {
            return Err(rusqlite::Error::InvalidParameterName(
                "task_id must be a positive integer".to_string(),
            ));
        }
        if !valid_statuses.contains(&new_status) {
            return Err(rusqlite::Error::InvalidParameterName(
                format!("invalid status '{}'", new_status),
            ));
        }
        let conn = self.connect()?;
        let current: String = conn.query_row(
            "SELECT status FROM tasks WHERE id = ?1",
            params![task_id],
            |row| row.get(0),
        ).map_err(|_| rusqlite::Error::InvalidParameterName(format!("task #{} not found", task_id)))?;

        if !transitions.get(current.as_str()).map(|v| v.contains(&new_status)).unwrap_or(false) {
            return Err(rusqlite::Error::InvalidParameterName(
                format!("invalid transition from '{}' to '{}'", current, new_status),
            ));
        }

        let ts = Self::now();
        if new_status == "done" {
            conn.execute("UPDATE tasks SET status = ?1, completed_at = ?2, updated_at = ?3 WHERE id = ?4",
                params![new_status, ts, ts, task_id])?;
        } else if new_status == "in_progress" && current != "in_progress" {
            conn.execute("UPDATE tasks SET status = ?1, claimed_at = ?2, updated_at = ?3 WHERE id = ?4",
                params![new_status, ts, ts, task_id])?;
        } else {
            conn.execute("UPDATE tasks SET status = ?1, updated_at = ?2 WHERE id = ?3",
                params![new_status, ts, task_id])?;
        }
        Ok(())
    }

    /// Claim a task by assigning self and setting to in_progress
    pub fn claim_task(&self, task_id: i64) -> SqliteResult<()> {
        if task_id <= 0 {
            return Err(rusqlite::Error::InvalidParameterName(
                "task_id must be a positive integer".to_string(),
            ));
        }
        let conn = self.connect()?;
        let (current_status, assigned_to): (String, Option<String>) = conn.query_row(
            "SELECT status, assigned_to FROM tasks WHERE id = ?1",
            params![task_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        ).map_err(|_| rusqlite::Error::InvalidParameterName(format!("task #{} not found", task_id)))?;

        if current_status == "done" {
            return Err(rusqlite::Error::InvalidParameterName(
                format!("task #{} is already done", task_id),
            ));
        }
        if let Some(ref assigned) = assigned_to {
            if !assigned.is_empty() && assigned != &self.agent_id {
                return Err(rusqlite::Error::InvalidParameterName(
                    format!("task #{} already assigned to '{}'", task_id, assigned),
                ));
            }
        }
        let ts = Self::now();
        conn.execute(
            "UPDATE tasks SET status = 'in_progress', assigned_to = ?1, claimed_at = ?2, updated_at = ?3 WHERE id = ?4",
            params![&self.agent_id, ts, ts, task_id],
        )?;
        Ok(())
    }

    /// Complete a task with optional result
    pub fn complete_task(&self, task_id: i64, result: Option<&str>) -> SqliteResult<()> {
        if task_id <= 0 {
            return Err(rusqlite::Error::InvalidParameterName(
                "task_id must be a positive integer".to_string(),
            ));
        }
        let conn = self.connect()?;
        let row = conn.query_row(
            "SELECT status, assigned_to FROM tasks WHERE id = ?1",
            params![task_id],
            |row| Ok((row.get::<_, String>(0)?, row.get::<_, Option<String>>(1)?)),
        ).map_err(|_| rusqlite::Error::InvalidParameterName(format!("task #{} not found", task_id)))?;
        let (current_status, assigned_to) = row;
        if let Some(ref assigned) = assigned_to {
            if !assigned.is_empty() && assigned != &self.agent_id {
                return Err(rusqlite::Error::InvalidParameterName(
                    format!("task #{} is assigned to '{}', not '{}'", task_id, assigned, self.agent_id),
                ));
            }
        }
        let valid_transition = match current_status.as_str() {
            "planned" | "in_progress" | "review_pending" | "approved" | "blocked" => true,
            "done" => false,
            _ => true,
        };
        if !valid_transition {
            return Err(rusqlite::Error::InvalidParameterName(
                format!("cannot complete task #{} from terminal state '{}'", task_id, current_status),
            ));
        }
        let ts = Self::now();
        conn.execute(
            "UPDATE tasks SET status = 'done', result = ?1, completed_at = ?2, updated_at = ?3 WHERE id = ?4",
            params![result, ts, ts, task_id],
        )?;
        Ok(())
    }

    /// Wait for N unread messages with timeout.
    ///
    /// Blocks up to `timeout_secs` seconds, polling the bus every 200ms,
    /// until `count` unread messages arrive. Returns true if the required
    /// count was reached before timeout.
    pub fn wait(&self, count: i64, timeout_secs: f64) -> SqliteResult<bool> {
        self.wait_for_messages(count, timeout_secs)
    }

    /// Block until N unread messages arrive or timeout elapses.
    ///
    /// Accumulates messages across polls so count > 1 works even when
    /// messages arrive one at a time. Messages are marked as read as
    /// they arrive via `recv(unread_only=true)`.
    /// Matches Python a2a_client.py wait_for_messages() behavior.
    pub fn wait_for_messages(&self, count: i64, timeout: f64) -> SqliteResult<bool> {
        if count <= 0 {
            return Err(rusqlite::Error::InvalidParameterName(
                "count must be a positive integer".to_string(),
            ));
        }
        if timeout < 0.0 {
            return Err(rusqlite::Error::InvalidParameterName(
                "timeout must be a non-negative number of seconds".to_string(),
            ));
        }
        if !timeout.is_finite() {
            return Err(rusqlite::Error::InvalidParameterName(
                "timeout must be a finite number".to_string(),
            ));
        }
        let deadline = SystemTime::now() + Duration::from_secs_f64(timeout);
        let mut seen: i64 = 0;
        loop {
            let need = count - seen;
            if need <= 0 {
                return Ok(true);
            }
            if SystemTime::now() >= deadline {
                return Ok(false);
            }
            let msgs = self.recv(0.0, true, false, Some(need), None)?;
            seen += msgs.len() as i64;
            if seen >= count {
                return Ok(true);
            }
            if msgs.is_empty() {
                thread::sleep(Duration::from_millis(500));
            }
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
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                sender          TEXT NOT NULL,
                recipient       TEXT,
                body            TEXT NOT NULL,
                thread_id       TEXT,
                ttl_seconds     INTEGER,
                priority        INTEGER DEFAULT 3,
                requires_ack    INTEGER DEFAULT 0,
                created_at      REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reads (
                agent_id    TEXT NOT NULL,
                message_id  INTEGER NOT NULL,
                read_at     REAL NOT NULL,
                PRIMARY KEY (agent_id, message_id)
            );
            CREATE TABLE IF NOT EXISTS acknowledgments (
                message_id  INTEGER NOT NULL,
                agent_id    TEXT NOT NULL,
                acked_at    REAL NOT NULL,
                PRIMARY KEY (message_id, agent_id)
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                title           TEXT NOT NULL,
                description     TEXT,
                assigned_to     TEXT,
                status          TEXT NOT NULL DEFAULT 'planned',
                priority        INTEGER DEFAULT 3,
                dependencies    TEXT,
                result          TEXT,
                claimed_at      REAL,
                completed_at    REAL,
                created_at      REAL NOT NULL,
                updated_at      REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS task_deps (
                task_id     INTEGER NOT NULL,
                depends_on  INTEGER NOT NULL,
                PRIMARY KEY (task_id, depends_on)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient);
            CREATE INDEX IF NOT EXISTS idx_messages_thread    ON messages(thread_id);
            CREATE INDEX IF NOT EXISTS idx_messages_created   ON messages(created_at);
            CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_to);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_task_deps_task ON task_deps(task_id);",
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

    /// Update last_seen timestamp for this agent.
    pub fn touch(&self) -> SqliteResult<()> {
        let conn = self.connect()?;
        conn.execute(
            "UPDATE agents SET last_seen = ?1 WHERE id = ?2",
            params![Self::now(), &self.agent_id],
        )?;
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
            priority: 3,
            requires_ack: false,
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
            pid: Some(12345),
        };
        assert_eq!(peer.id, "alice");
        assert_eq!(peer.status, "active");
        assert_eq!(peer.pid, Some(12345));
    }

    #[test]
    fn test_stats_struct() {
        use std::collections::HashMap;
        let stats = Stats {
            messages: 100,
            direct_messages: 80,
            broadcasts: 20,
            threads: 5,
            priority_distribution: vec![],
            acks_required: 0,
            acks_sent: 0,
            pending_acks: 0,
            agents_active: 2,
            agents_done: 1,
            tasks_total: 0,
            tasks_done: 0,
            tasks_blocked: 0,
            tasks_by_status: HashMap::new(),
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
        let result = client.send("", "hello", None, None, 3, false);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("recipient must not be empty"));
    }

    #[test]
    fn test_send_rejects_whitespace_recipient() {
        let client = Client::new("test_send_ws_recip", "tester").unwrap();
        let result = client.send("   ", "hello", None, None, 3, false);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("recipient must not be empty"));
    }

    #[test]
    fn test_send_rejects_non_positive_ttl() {
        let client = Client::new("test_send_ttl", "tester").unwrap();
        for ttl in &[Some(0), Some(-1), Some(-100)] {
            let result = client.send("bob", "hello", *ttl, None, 3, false);
            assert!(result.is_err());
            assert!(result.unwrap_err().to_string().contains("ttl_seconds must be a positive number"));
        }
    }

    #[test]
    fn test_send_rejects_empty_thread_id() {
        let client = Client::new("test_send_thread", "tester").unwrap();
        let result = client.send("bob", "hello", None, Some(""), 3, false);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("thread_id must not be empty"));

        let result = client.send("bob", "hello", None, Some("   "), 3, false);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("thread_id must not be empty"));
    }

    #[test]
    fn test_wait_for_messages_validation() {
        let client = Client::new("test_wfm_validate", "tester").unwrap();
        let result = client.wait_for_messages(0, 1.0);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("count must be a positive integer"));

        let result = client.wait_for_messages(-1, 1.0);
        assert!(result.is_err());

        let result = client.wait_for_messages(1, -1.0);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("timeout must be a non-negative"));

        let result = client.wait_for_messages(1, f64::NAN);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("finite"));
    }

    // ---- task tests (phase 2) ----

    #[test]
    fn test_create_task_returns_positive_id() {
        let client = Client::new("test_rust_task_create", "tester").unwrap();
        let _ = client.clear();
        client.init_project().unwrap();
        let tid = client.create_task("Test task", None, None, 3, None).unwrap();
        assert!(tid > 0);
    }

    #[test]
    fn test_create_task_with_description_and_assignee() {
        let client = Client::new("test_rust_task_desc", "tester").unwrap();
        let _ = client.clear();
        client.init_project().unwrap();
        let tid = client.create_task("Build feature", Some("Implement X"), Some("bob"), 1, None).unwrap();
        assert!(tid > 0);
        let tasks = client.list_tasks(None, None).unwrap();
        assert_eq!(tasks.len(), 1);
        assert_eq!(tasks[0].title, "Build feature");
        assert_eq!(tasks[0].description.as_deref(), Some("Implement X"));
        assert_eq!(tasks[0].assigned_to.as_deref(), Some("bob"));
        assert_eq!(tasks[0].priority, 1);
        assert_eq!(tasks[0].status, "planned");
    }

    #[test]
    fn test_create_task_empty_title_raises_error() {
        let client = Client::new("test_rust_task_empty", "tester").unwrap();
        let _ = client.clear();
        client.init_project().unwrap();
        let result = client.create_task("", None, None, 3, None);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("task title must not be empty"));
    }

    #[test]
    fn test_create_task_invalid_priority_raises_error() {
        let client = Client::new("test_rust_task_prio", "tester").unwrap();
        let _ = client.clear();
        client.init_project().unwrap();
        let result = client.create_task("test", None, None, 5, None);
        assert!(result.is_err());
        let result = client.create_task("test", None, None, 0, None);
        assert!(result.is_err());
    }

    #[test]
    fn test_list_tasks_empty_returns_empty() {
        let client = Client::new("test_rust_list_empty", "tester").unwrap();
        let _ = client.clear();
        client.init_project().unwrap();
        let tasks = client.list_tasks(None, None).unwrap();
        assert!(tasks.is_empty());
    }

    #[test]
    fn test_list_tasks_filter_by_status() {
        let client = Client::new("test_rust_list_status", "tester").unwrap();
        let _ = client.clear();
        client.init_project().unwrap();
        client.create_task("Task A", None, None, 3, None).unwrap();
        client.create_task("Task B", None, None, 3, None).unwrap();
        let tasks = client.list_tasks(Some("planned"), None).unwrap();
        assert_eq!(tasks.len(), 2);
        let tasks = client.list_tasks(Some("done"), None).unwrap();
        assert_eq!(tasks.len(), 0);
    }

    #[test]
    fn test_update_task_status_transitions() {
        let client = Client::new("test_rust_task_trans", "tester").unwrap();
        let _ = client.clear();
        client.init_project().unwrap();
        let tid = client.create_task("Workflow test", None, None, 3, None).unwrap();

        client.update_task_status(tid, "in_progress").unwrap();
        let tasks = client.list_tasks(None, None).unwrap();
        assert_eq!(tasks[0].status, "in_progress");

        client.update_task_status(tid, "review_pending").unwrap();
        let tasks = client.list_tasks(None, None).unwrap();
        assert_eq!(tasks[0].status, "review_pending");

        client.update_task_status(tid, "approved").unwrap();
        let tasks = client.list_tasks(None, None).unwrap();
        assert_eq!(tasks[0].status, "approved");

        client.update_task_status(tid, "done").unwrap();
        let tasks = client.list_tasks(None, None).unwrap();
        assert_eq!(tasks[0].status, "done");
    }

    #[test]
    fn test_update_task_status_invalid_transition_raises_error() {
        let client = Client::new("test_rust_task_badtrans", "tester").unwrap();
        let _ = client.clear();
        client.init_project().unwrap();
        let tid = client.create_task("Test", None, None, 3, None).unwrap();

        let result = client.update_task_status(tid, "done");
        assert!(result.is_err());

        let result = client.update_task_status(tid, "blocked");
        assert!(result.is_err());

        let result = client.update_task_status(tid, "invalid_status");
        assert!(result.is_err());
    }

    #[test]
    fn test_update_task_status_done_is_terminal() {
        let client = Client::new("test_rust_task_terminal", "tester").unwrap();
        let _ = client.clear();
        client.init_project().unwrap();
        let tid = client.create_task("Test", None, None, 3, None).unwrap();
        client.update_task_status(tid, "in_progress").unwrap();
        client.update_task_status(tid, "done").unwrap();
        let result = client.update_task_status(tid, "in_progress");
        assert!(result.is_err());
    }

    #[test]
    fn test_claim_task_changes_status_and_assigns() {
        let client = Client::new("test_rust_claim", "tester").unwrap();
        let _ = client.clear();
        client.init_project().unwrap();
        let tid = client.create_task("Claim test", None, None, 3, None).unwrap();
        client.claim_task(tid).unwrap();
        let tasks = client.list_tasks(None, None).unwrap();
        assert_eq!(tasks[0].status, "in_progress");
        assert_eq!(tasks[0].assigned_to.as_deref(), Some("tester"));
    }

    #[test]
    fn test_claim_task_already_done_raises_error() {
        let client = Client::new("test_rust_claim_done", "tester").unwrap();
        let _ = client.clear();
        client.init_project().unwrap();
        let tid = client.create_task("Done task", None, None, 3, None).unwrap();
        client.update_task_status(tid, "in_progress").unwrap();
        client.complete_task(tid, Some("done")).unwrap();
        let result = client.claim_task(tid);
        assert!(result.is_err());
    }

    #[test]
    fn test_claim_task_assigned_to_other_raises_error() {
        let client = Client::new("test_rust_claim_other", "alice").unwrap();
        let _ = client.clear();
        client.init_project().unwrap();
        let tid = client.create_task("Assigned task", None, Some("bob"), 3, None).unwrap();
        let result = client.claim_task(tid);
        assert!(result.is_err());
    }

    #[test]
    fn test_complete_task_sets_done_and_result() {
        let client = Client::new("test_rust_complete", "tester").unwrap();
        let _ = client.clear();
        client.init_project().unwrap();
        let tid = client.create_task("Complete test", None, Some("tester"), 3, None).unwrap();
        client.claim_task(tid).unwrap();
        client.complete_task(tid, Some("All done!")).unwrap();
        let tasks = client.list_tasks(None, None).unwrap();
        assert_eq!(tasks[0].status, "done");
        assert_eq!(tasks[0].result.as_deref(), Some("All done!"));
    }

    #[test]
    fn test_complete_task_not_found_raises_error() {
        let client = Client::new("test_rust_complete_missing", "tester").unwrap();
        let result = client.complete_task(999, Some("result"));
        assert!(result.is_err());
    }

    #[test]
    fn test_task_struct_defaults() {
        let task = Task {
            id: 1,
            title: "test".to_string(),
            description: None,
            assigned_to: None,
            status: "planned".to_string(),
            priority: 3,
            dependencies: None,
            result: None,
            claimed_at: None,
            completed_at: None,
            created_at: 1000.0,
            updated_at: 1000.0,
        };
        assert_eq!(task.status, "planned");
        assert!(task.claimed_at.is_none());
        assert!(task.completed_at.is_none());
    }

    #[test]
    fn test_complete_task_wrong_assignee_raises_error() {
        let client = Client::new("test_rust_complete_wrong", "alice").unwrap();
        let _ = client.clear();
        client.init_project().unwrap();
        let tid = client.create_task("Wrong assignee", None, Some("bob"), 3, None).unwrap();
        client.update_task_status(tid, "in_progress").unwrap();
        let result = client.complete_task(tid, Some("result"));
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("assigned to"));
    }
}
