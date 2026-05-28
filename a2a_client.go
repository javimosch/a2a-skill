// Package a2a provides a Go client for the a2a peer-to-peer messaging bus.
//
// Every connect() call applies the WAL invariant: creates the parent directory
// if missing (no prior `a2a init` required), then sets PRAGMA journal_mode=WAL
// and PRAGMA busy_timeout=5000 for concurrent-writer safety.
//
// See src/AGENTS.md for the authoritative WAL invariant documentation.
package a2a

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

// Max length limits matching a2a.py's MAX_ID_LENGTH, MAX_THREAD_ID_LENGTH,
// and MAX_BODY_LENGTH. These prevent SQLite/text abuse and ensure parity
// between Go and Python validation.
const (
	MaxAgentIDLength   = 256
	MaxThreadIDLength  = 256
	MaxBodyLength      = 100000
	MaxRoleLength      = 512
)

// Client represents an a2a messaging client
type Client struct {
	Project  string
	AgentID  string
	dbPath   string
}

// Message represents a message in the bus
type Message struct {
	ID          int       `json:"id"`
	Sender      string    `json:"sender"`
	Recipient   *string   `json:"recipient"`
	Body        string    `json:"body"`
	ThreadID    *string   `json:"thread_id"`
	Priority    int       `json:"priority"`
	RequiresAck bool      `json:"requires_ack"`
	CreatedAt   float64   `json:"created_at"`
}

// Peer represents an agent on the bus
type Peer struct {
	ID     string  `json:"id"`
	Role   *string `json:"role"`
	CLI    *string `json:"cli"`
	Status string  `json:"status"`
	PID    *int    `json:"pid"`
}

// Task represents a task in the shared task queue
type Task struct {
	ID           int      `json:"id"`
	Title        string   `json:"title"`
	Description  *string  `json:"description"`
	AssignedTo   *string  `json:"assigned_to"`
	Status       string   `json:"status"`
	Priority     int      `json:"priority"`
	Dependencies *string  `json:"dependencies"`
	Result       *string  `json:"result"`
	ClaimedAt    *float64 `json:"claimed_at"`
	CompletedAt  *float64 `json:"completed_at"`
	CreatedAt    float64  `json:"created_at"`
	UpdatedAt    float64  `json:"updated_at"`
}

// TaskDep represents a dependency between tasks
type TaskDep struct {
	TaskID    int `json:"task_id"`
	DependsOn int `json:"depends_on"`
}

// TopSender represents one entry in the top senders stats list.
type TopSender struct {
	Agent string `json:"agent"`
	Count int    `json:"count"`
}

// PriorityCount represents one priority level's count in stats.
type PriorityCount struct {
	Label string `json:"label"`
	Count int    `json:"count"`
}

// Stats represents bus statistics
type Stats struct {
	Messages            int            `json:"messages"`
	DirectMessages      int            `json:"direct_messages"`
	Broadcasts          int            `json:"broadcasts"`
	Threads             int            `json:"threads"`
	PriorityDistribution []PriorityCount `json:"priority_distribution"`
	AcksRequired        int            `json:"acks_required"`
	AcksSent            int            `json:"acks_sent"`
	PendingAcks         int            `json:"pending_acks"`
	AgentsActive        int            `json:"agents_active"`
	AgentsDone          int            `json:"agents_done"`
	TasksTotal          int            `json:"tasks_total"`
	TasksDone           int            `json:"tasks_done"`
	TasksBlocked        int            `json:"tasks_blocked"`
	TasksByStatus       map[string]int `json:"tasks_by_status"`
	TopSenders          []TopSender    `json:"top_senders"`
}

// NewClient creates a new a2a client
func NewClient(project, agentID string) (*Client, error) {
	if strings.TrimSpace(project) == "" {
		return nil, fmt.Errorf("project must not be empty")
	}
	if strings.Contains(project, "/") || strings.Contains(project, "\\") || strings.HasPrefix(project, ".") {
		return nil, fmt.Errorf("project must not contain path separators or start with dot")
	}
	if len(agentID) > MaxAgentIDLength {
		return nil, fmt.Errorf("agent_id too long (%d chars, max %d)", len(agentID), MaxAgentIDLength)
	}
	dbDir := filepath.Join(os.Getenv("HOME"), ".a2a", project)
	dbPath := filepath.Join(dbDir, "database.db")
	return &Client{
		Project: project,
		AgentID: agentID,
		dbPath:  dbPath,
	}, nil
}

// connect opens the database connection, applying the WAL invariant.
// Creates the parent directory if it does not exist.
func (c *Client) connect() (*sql.DB, error) {
	if err := os.MkdirAll(filepath.Dir(c.dbPath), 0755); err != nil {
		return nil, err
	}
	db, err := sql.Open("sqlite3", c.dbPath)
	if err != nil {
		return nil, err
	}
	if _, err := db.Exec("PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;"); err != nil {
		db.Close()
		return nil, err
	}
	db.SetConnMaxLifetime(0)
	return db, nil
}

// Send sends a message to a peer (or broadcast if recipient is "all"/"*"/"broadcast").
// threadID may be empty string for no thread. ttlSeconds may be nil for no expiry.
// priority should be 1-4 (1=URGENT, 2=HIGH, 3=NORMAL, 4=LOW, default 3).
// requireAck marks the message as requiring acknowledgment.
// Matches Python/JS/Rust order: send(to, message, ttl_seconds, thread_id, priority, require_ack).
func (c *Client) Send(to, message string, ttlSeconds *int, threadID string, priority int, requireAck bool) (int64, error) {
	if len(c.AgentID) > MaxAgentIDLength {
			return 0, fmt.Errorf("agent_id too long (%d chars, max %d)", len(c.AgentID), MaxAgentIDLength)
	}
	if strings.TrimSpace(to) == "" {
		return 0, fmt.Errorf("recipient must not be empty")
	}
	if ttlSeconds != nil && *ttlSeconds <= 0 {
		return 0, fmt.Errorf("ttl_seconds must be a positive number of seconds")
	}
	if len(message) > MaxBodyLength {
		return 0, fmt.Errorf("message body too long (%d chars, max %d)", len(message), MaxBodyLength)
	}
	if priority < 1 || priority > 4 {
		return 0, fmt.Errorf("priority must be 1-4 (1=URGENT, 2=HIGH, 3=NORMAL, 4=LOW)")
	}
	db, err := c.connect()
	if err != nil {
		return 0, err
	}
	defer db.Close()

	var count int
	if err := db.QueryRow("SELECT COUNT(1) FROM agents WHERE id=?", c.AgentID).Scan(&count); err != nil || count == 0 {
		return 0, fmt.Errorf("unknown sender '%s' — register first", c.AgentID)
	}

	var recip *string
	if toLower := strings.ToLower(to); toLower != "all" && toLower != "*" && toLower != "broadcast" {
		if len(to) > MaxAgentIDLength {
			return 0, fmt.Errorf("recipient agent_id too long (%d chars, max %d)", len(to), MaxAgentIDLength)
		}
		if err := db.QueryRow("SELECT COUNT(1) FROM agents WHERE id=?", to).Scan(&count); err != nil || count == 0 {
			return 0, fmt.Errorf("unknown recipient '%s' — register them first", to)
		}
		r := to
		recip = &r
	}

	var tid *string
	if strings.TrimSpace(threadID) == "" {
		threadID = ""
	}
	if threadID != "" {
		if len(threadID) > MaxThreadIDLength {
			return 0, fmt.Errorf("thread_id too long (%d chars, max %d)", len(threadID), MaxThreadIDLength)
		}
		tid = &threadID
	}

	ackVal := 0
	if requireAck {
		ackVal = 1
	}

	result, err := db.Exec(
		"INSERT INTO messages(sender, recipient, body, thread_id, ttl_seconds, priority, requires_ack, created_at) VALUES (?,?,?,?,?,?,?,?)",
		c.AgentID, recip, message, tid, ttlSeconds, priority, ackVal, nowSec(),
	)
	if err != nil {
		return 0, err
	}

	return result.LastInsertId()
}

// SendSimple sends a message without thread, TTL, priority options. Backward-compat wrapper.
func (c *Client) SendSimple(to, message string) (int64, error) {
	return c.Send(to, message, nil, "", 3, false)
}



// RecvOpts configures the Recv call
var DefaultRecvOpts = RecvOpts{
	Wait:        0,
	UnreadOnly:  true,
	IncludeSelf: false,
	Limit:       0,
	Since:       nil, // no timestamp filter
}

// RecvOpts holds optional parameters for Recv
type RecvOpts struct {
	// Wait blocks up to N seconds for at least one message (0 = no wait)
	Wait float64
	// UnreadOnly filters to messages not yet read by this agent
	UnreadOnly bool
	// IncludeSelf includes messages sent by this agent
	IncludeSelf bool
	// Limit caps the number of returned messages (0 = unlimited)
	Limit int
	// Since filters to messages created after this timestamp (nil = no filter)
	Since *float64
	// PriorityMin filters to messages at this priority level or higher (1=URGENT, 4=LOW)
	PriorityMin *int
}

// Recv receives messages with full options. Run TTL cleanup and Touch on same connection.
func (c *Client) Recv(opts RecvOpts) ([]Message, error) {
	if opts.Limit < 0 {
		return nil, fmt.Errorf("limit must be a non-negative integer")
	}
	if opts.Wait < 0 {
		return nil, fmt.Errorf("wait must be a non-negative number of seconds")
	}
	if math.IsInf(opts.Wait, 0) || math.IsNaN(opts.Wait) {
		return nil, fmt.Errorf("wait must be a finite number")
	}
	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	deadline := time.Now().Add(time.Duration(opts.Wait * float64(time.Second)))
	pollInterval := 100 * time.Millisecond

	for {
		db.Exec("DELETE FROM messages WHERE ttl_seconds IS NOT NULL AND created_at + ttl_seconds < ?", nowSec())
		query := "SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at FROM messages WHERE (recipient = ? OR recipient IS NULL)"
		args := []interface{}{c.AgentID}

		if !opts.IncludeSelf {
			query += " AND sender != ?"
			args = append(args, c.AgentID)
		}

		if opts.UnreadOnly {
			query += " AND NOT EXISTS (SELECT 1 FROM reads WHERE agent_id = ? AND message_id = messages.id)"
			args = append(args, c.AgentID)
		}

		if opts.Since != nil {
			query += " AND created_at > ?"
			args = append(args, *opts.Since)
		}

	if opts.PriorityMin != nil {
		query += " AND priority <= ?"
		args = append(args, *opts.PriorityMin)
	}

	query += " ORDER BY priority ASC, created_at ASC"
	if opts.Limit > 0 {
		query += " LIMIT ?"
		args = append(args, opts.Limit)
	}

		rows, err := db.Query(query, args...)
		if err != nil {
			return nil, err
		}

		messages := []Message{}

		for rows.Next() {
			var m Message
			var priority, requiresAck int
			err := rows.Scan(&m.ID, &m.Sender, &m.Recipient, &m.Body, &m.ThreadID, &priority, &requiresAck, &m.CreatedAt)
			if err != nil {
				rows.Close()
				return nil, err
			}
			m.Priority = priority
			m.RequiresAck = requiresAck == 1
			messages = append(messages, m)
		}
		rows.Close()

		// Mark all fetched messages as read (separate phase to avoid partial read-marking on scan error)
		ts := nowSec()
		for _, m := range messages {
			db.Exec("INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) VALUES (?,?,?)",
				c.AgentID, m.ID, ts)
		}

		if len(messages) > 0 {
			return messages, nil
		}

		if opts.Wait == 0 || time.Now().After(deadline) {
			return messages, nil
		}

		time.Sleep(pollInterval)
	}
}

// RecvSimple is a backward-compatible wrapper for Recv with positional args.
func (c *Client) RecvSimple(wait float64, unreadOnly, includeSelf bool, limit int) ([]Message, error) {
	return c.Recv(RecvOpts{
		Wait:        wait,
		UnreadOnly:  unreadOnly,
		IncludeSelf: includeSelf,
		Limit:       limit,
	})
}

// Peek views recent messages without marking read. Cleans up expired TTL first.
func (c *Client) Peek(limit int) ([]Message, error) {
	if limit <= 0 {
		return nil, fmt.Errorf("limit must be a positive integer")
	}

	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	// Clean up expired TTL messages
	db.Exec("DELETE FROM messages WHERE ttl_seconds IS NOT NULL AND created_at + ttl_seconds < ?", nowSec())

	rows, err := db.Query(
		"SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at FROM messages ORDER BY created_at DESC LIMIT ?",
		limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	messages := []Message{}
	for rows.Next() {
		var m Message
		var priority, requiresAck int
		err := rows.Scan(&m.ID, &m.Sender, &m.Recipient, &m.Body, &m.ThreadID, &priority, &requiresAck, &m.CreatedAt)
		if err != nil {
			return nil, err
		}
		m.Priority = priority
		m.RequiresAck = requiresAck == 1
		messages = append(messages, m)
	}

	// Reverse to get oldest first
	for i, j := 0, len(messages)-1; i < j; i, j = i+1, j-1 {
		messages[i], messages[j] = messages[j], messages[i]
	}

	return messages, nil
}

// ListPeers returns list of registered agents
func (c *Client) ListPeers() ([]Peer, error) {
	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	rows, err := db.Query("SELECT id, role, cli, status, pid FROM agents ORDER BY created_at")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	peers := []Peer{}
	for rows.Next() {
		var p Peer
		var role, cli sql.NullString
		var pid sql.NullInt64
		err := rows.Scan(&p.ID, &role, &cli, &p.Status, &pid)
		if err != nil {
			return nil, err
		}
		if role.Valid {
			p.Role = &role.String
		}
		if cli.Valid {
			p.CLI = &cli.String
		}
		if pid.Valid {
			pidInt := int(pid.Int64)
			p.PID = &pidInt
		}
		peers = append(peers, p)
	}

	return peers, nil
}

// List returns all registered agents (alias for ListPeers).
func (c *Client) List() ([]Peer, error) {
	return c.ListPeers()
}

// Status gets or sets this agent's status.
// If newStatus is provided, sets the status and returns nil.
// If newStatus is empty, returns the current status.
func (c *Client) Status(newStatus string) (*string, error) {
	if newStatus != "" {
		_, err := c.SetStatus(newStatus)
		if err != nil {
			return nil, err
		}
		return nil, nil
	}
	return c.GetStatus(c.AgentID)
}

// AgentExists returns true if the agent is registered in the project.
func (c *Client) AgentExists(agentID string) (bool, error) {
	db, err := c.connect()
	if err != nil {
		return false, err
	}
	defer db.Close()
	var count int
	err = db.QueryRow("SELECT COUNT(1) FROM agents WHERE id=?", agentID).Scan(&count)
	return count > 0, err
}

// SetStatus updates agent status. Returns (lastSeen, error). Errors if agent doesn't exist.
func (c *Client) SetStatus(status string) (float64, error) {
	validStatuses := map[string]bool{"active": true, "idle": true, "done": true, "blocked": true}
	if !validStatuses[status] {
		return 0, fmt.Errorf("invalid status '%s' — must be one of active, idle, done, blocked", status)
	}
	db, err := c.connect()
	if err != nil {
		return 0, err
	}
	defer db.Close()

	ts := nowSec()
	result, err := db.Exec(
		"UPDATE agents SET status=?, last_seen=? WHERE id=?",
		status, ts, c.AgentID,
	)
	if err != nil {
		return 0, err
	}
	n, _ := result.RowsAffected()
	if n == 0 {
		return 0, fmt.Errorf("unknown agent '%s' — register first", c.AgentID)
	}
	return ts, nil
}

// GetStatus gets agent status. Returns nil if agent not found (matching Python returning None).
func (c *Client) GetStatus(agentID string) (*string, error) {
	if agentID == "" {
		agentID = c.AgentID
	}

	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	var status string
	err = db.QueryRow("SELECT status FROM agents WHERE id=?", agentID).Scan(&status)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &status, nil
}

// Search searches messages by content (LIKE-based substring search).
func (c *Client) Search(query string, limit int) ([]Message, error) {
	if strings.TrimSpace(query) == "" {
		return nil, fmt.Errorf("search query must not be empty")
	}
	if limit <= 0 {
		return nil, fmt.Errorf("limit must be a positive integer")
	}
	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	rows, err := db.Query(
		"SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at FROM messages WHERE lower(body) LIKE ? ORDER BY created_at DESC LIMIT ?",
		fmt.Sprintf("%%%s%%", strings.ToLower(query)), limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	messages := []Message{}
	for rows.Next() {
		var m Message
		var priority, requiresAck int
		err := rows.Scan(&m.ID, &m.Sender, &m.Recipient, &m.Body, &m.ThreadID, &priority, &requiresAck, &m.CreatedAt)
		if err != nil {
			return nil, err
		}
		m.Priority = priority
		m.RequiresAck = requiresAck == 1
		messages = append(messages, m)
	}

	return messages, nil
}

// SearchFTS performs full-text search using SQLite FTS5.
// Requires the binary to be built with -tags fts5.
// Falls back to LIKE search if FTS5 is unavailable.
func (c *Client) SearchFTS(query string, limit int) ([]Message, error) {
	if strings.TrimSpace(query) == "" {
		return nil, fmt.Errorf("search query must not be empty")
	}
	if limit <= 0 {
		return nil, fmt.Errorf("limit must be a positive integer")
	}
	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	// Try to create FTS5 virtual table (no-op if exists)
	_, ftsErr := db.Exec(`CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
		id, sender, recipient, body, thread_id, created_at,
		content=messages, content_rowid=id
	)`)

	if ftsErr == nil {
		// Try to sync via triggers
		db.Exec(`CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
		  INSERT INTO messages_fts(rowid, id, sender, recipient, body, thread_id, created_at)
		  VALUES (new.rowid, new.id, new.sender, new.recipient, new.body, new.thread_id, new.created_at); END`)
		db.Exec(`CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
		  DELETE FROM messages_fts WHERE rowid = old.id; END`)
		db.Exec(`CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN
		  DELETE FROM messages_fts WHERE rowid = old.id;
		  INSERT INTO messages_fts(rowid, id, sender, recipient, body, thread_id, created_at)
		  VALUES (new.rowid, new.id, new.sender, new.recipient, new.body, new.thread_id, new.created_at); END`)
		db.Exec("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")

		rows, err := db.Query(
			`SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, m.created_at
			 FROM messages_fts JOIN messages m ON messages_fts.rowid = m.rowid
			 WHERE messages_fts MATCH ? ORDER BY rank LIMIT ?`,
			query, limit,
		)
		if err == nil {
			defer rows.Close()
			messages := []Message{}
			for rows.Next() {
				var m Message
				if err := rows.Scan(&m.ID, &m.Sender, &m.Recipient, &m.Body, &m.ThreadID, &m.CreatedAt); err != nil {
					return nil, err
				}
				messages = append(messages, m)
			}
			return messages, nil
		}
	}

	// Fall back to LIKE search
	return c.Search(query, limit)
}

// Thread gets all messages in a thread
func (c *Client) Thread(threadID string) ([]Message, error) {
	if strings.TrimSpace(threadID) == "" {
		return nil, fmt.Errorf("thread_id must not be empty")
	}
	if len(threadID) > MaxThreadIDLength {
		return nil, fmt.Errorf("thread_id too long (%d chars, max %d)", len(threadID), MaxThreadIDLength)
	}
	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	rows, err := db.Query(
		"SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
		threadID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	messages := []Message{}
	for rows.Next() {
		var m Message
		var priority, requiresAck int
		err := rows.Scan(&m.ID, &m.Sender, &m.Recipient, &m.Body, &m.ThreadID, &priority, &requiresAck, &m.CreatedAt)
		if err != nil {
			return nil, err
		}
		m.Priority = priority
		m.RequiresAck = requiresAck == 1
		messages = append(messages, m)
	}

	return messages, nil
}

// Stats returns bus statistics
func (c *Client) Stats() (*Stats, error) {
	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	stats := &Stats{
		TopSenders:    []TopSender{},
		TasksByStatus: map[string]int{},
	}

	// Message counts
	if err := db.QueryRow("SELECT COUNT(*) FROM messages").Scan(&stats.Messages); err != nil {
		return nil, fmt.Errorf("stats query failed (is project initialized?): %w", err)
	}
	db.QueryRow("SELECT COUNT(*) FROM messages WHERE recipient IS NULL").Scan(&stats.Broadcasts)
	db.QueryRow("SELECT COUNT(DISTINCT thread_id) FROM messages WHERE thread_id IS NOT NULL").Scan(&stats.Threads)

	stats.DirectMessages = stats.Messages - stats.Broadcasts

	// Priority distribution
	prioRows, err := db.Query("SELECT priority, COUNT(*) FROM messages WHERE priority IS NOT NULL GROUP BY priority ORDER BY priority")
	if err == nil {
		defer prioRows.Close()
		prioLabels := map[int]string{1: "URGENT", 2: "HIGH", 3: "NORMAL", 4: "LOW"}
		for prioRows.Next() {
			var prio, count int
			if err := prioRows.Scan(&prio, &count); err == nil {
				label := prioLabels[prio]
				stats.PriorityDistribution = append(stats.PriorityDistribution, PriorityCount{Label: label, Count: count})
			}
		}
	}

	// Ack stats
	db.QueryRow("SELECT COUNT(*) FROM messages WHERE requires_ack = 1").Scan(&stats.AcksRequired)
	db.QueryRow("SELECT COUNT(*) FROM acknowledgments").Scan(&stats.AcksSent)
	stats.PendingAcks = stats.AcksRequired - stats.AcksSent
	if stats.PendingAcks < 0 {
		stats.PendingAcks = 0
	}

	// Agent counts
	db.QueryRow("SELECT COUNT(*) FROM agents WHERE status='active'").Scan(&stats.AgentsActive)
	db.QueryRow("SELECT COUNT(*) FROM agents WHERE status='done'").Scan(&stats.AgentsDone)

	// Top senders
	rows, err := db.Query(
		"SELECT sender, COUNT(*) as count FROM messages GROUP BY sender ORDER BY count DESC LIMIT 5",
	)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var sender string
			var count int
			if err := rows.Scan(&sender, &count); err == nil {
				stats.TopSenders = append(stats.TopSenders, TopSender{sender, count})
			}
		}
	}

	// Task stats
	db.QueryRow("SELECT COUNT(*) FROM tasks").Scan(&stats.TasksTotal)
	db.QueryRow("SELECT COUNT(*) FROM tasks WHERE status='done'").Scan(&stats.TasksDone)
	db.QueryRow("SELECT COUNT(*) FROM tasks WHERE status='blocked'").Scan(&stats.TasksBlocked)

	taskRows, err := db.Query("SELECT status, COUNT(*) FROM tasks GROUP BY status")
	if err == nil {
		defer taskRows.Close()
		for taskRows.Next() {
			var status string
			var count int
			if err := taskRows.Scan(&status, &count); err == nil {
				stats.TasksByStatus[status] = count
			}
		}
	}

	return stats, nil
}

// StatsJSON returns stats as JSON
func (c *Client) StatsJSON() (string, error) {
	stats, err := c.Stats()
	if err != nil {
		return "", err
	}
	b, err := json.MarshalIndent(stats, "", "  ")
	return string(b), err
}

// SchemaDDL matches a2a.py SCHEMA exactly
const SchemaDDL = `
CREATE TABLE IF NOT EXISTS agents (
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
CREATE INDEX IF NOT EXISTS idx_task_deps_task ON task_deps(task_id);
`

// nowSec returns sub-second precision timestamp matching Python's time.time()
func nowSec() float64 {
	return float64(time.Now().UnixNano()) / 1e9
}

// InitProject creates the database and schema. No-op if already exists.
func (c *Client) InitProject() error {
	db, err := c.connect()
	if err != nil {
		return err
	}
	defer db.Close()
	if _, err := db.Exec(SchemaDDL); err != nil {
		return err
	}
	// migrate: add ttl_seconds if missing (older dbs)
	var hasTTL bool
	_ = db.QueryRow("SELECT COUNT(*) FROM pragma_table_info('messages') WHERE name='ttl_seconds'").Scan(&hasTTL)
	if !hasTTL {
		db.Exec("ALTER TABLE messages ADD COLUMN ttl_seconds INTEGER")
	}
	return nil
}

// Register registers an agent. If upsert is true, updates existing.
// If pid is nil, no PID is stored; otherwise must be a positive integer.
func (c *Client) Register(role, prompt, cli string, pid *int, upsert bool) (bool, error) {
	if len(c.AgentID) > MaxAgentIDLength {
		return false, fmt.Errorf("agent_id too long (%d chars, max %d)", len(c.AgentID), MaxAgentIDLength)
	}
	if pid != nil && *pid <= 0 {
		return false, fmt.Errorf("pid must be a positive integer")
	}
	if len(role) > MaxRoleLength {
		return false, fmt.Errorf("role too long (%d chars, max %d)", len(role), MaxRoleLength)
	}
	if len(cli) > 128 {
		return false, fmt.Errorf("cli too long (%d chars, max 128)", len(cli))
	}
	if len(prompt) > MaxBodyLength {
		return false, fmt.Errorf("prompt too long (%d chars, max %d)", len(prompt), MaxBodyLength)
	}
	db, err := c.connect()
	if err != nil {
		return false, err
	}
	defer db.Close()

	ts := nowSec()
	if upsert {
		tx, err := db.Begin()
		if err != nil {
			return false, err
		}
		defer tx.Rollback()
		if _, err = tx.Exec(
			`INSERT OR IGNORE INTO agents(id, role, prompt, cli, status, pid, created_at, last_seen)
			 VALUES (?,?,?,?,?,?,?,?)`,
			c.AgentID, role, prompt, cli, "active", pid, ts, ts,
		); err != nil {
			return false, err
		}
		if _, err = tx.Exec(
			`UPDATE agents SET role=COALESCE(NULLIF(?,''),role), prompt=COALESCE(NULLIF(?,''),prompt),
			 cli=COALESCE(NULLIF(?,''),cli), pid=COALESCE(?,pid), status='active', last_seen=?
			 WHERE id=?`,
			role, prompt, cli, pid, ts, c.AgentID,
		); err != nil {
			return false, err
		}
		return true, tx.Commit()
	}
	_, err = db.Exec(
		`INSERT INTO agents(id, role, prompt, cli, status, pid, created_at, last_seen)
		 VALUES (?,?,?,?,?,?,?,?)`,
		c.AgentID, role, prompt, cli, "active", pid, ts, ts,
	)
	if err != nil {
		return false, fmt.Errorf("agent '%s' already registered (use upsert=true to update): %w", c.AgentID, err)
	}
	return true, nil
}

// Unregister removes an agent from the bus. Returns true on success.
func (c *Client) Unregister() (bool, error) {
	db, err := c.connect()
	if err != nil {
		return false, err
	}
	defer db.Close()
	_, err = db.Exec("DELETE FROM agents WHERE id=?", c.AgentID)
	if err != nil {
		return false, err
	}
	return true, nil
}

// Touch updates last_seen for the agent.
func (c *Client) Touch() error {
	db, err := c.connect()
	if err != nil {
		return err
	}
	defer db.Close()
	_, err = db.Exec("UPDATE agents SET last_seen=? WHERE id=?", nowSec(), c.AgentID)
	return err
}

// Ack acknowledges receipt of a message.
func (c *Client) Ack(messageID int64) (bool, error) {
	if messageID <= 0 {
		return false, fmt.Errorf("message_id must be a positive integer")
	}
	db, err := c.connect()
	if err != nil {
		return false, err
	}
	defer db.Close()

	var count int
	if err := db.QueryRow("SELECT COUNT(1) FROM messages WHERE id=?", messageID).Scan(&count); err != nil || count == 0 {
		return false, fmt.Errorf("message #%d not found", messageID)
	}
	_, err = db.Exec("INSERT OR IGNORE INTO acknowledgments(message_id, agent_id, acked_at) VALUES (?,?,?)",
		messageID, c.AgentID, nowSec())
	return err == nil, err
}

// PendingAcks returns messages sent to this agent that require acknowledgment but haven't been acked.
func (c *Client) PendingAcks() ([]Message, error) {
	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	rows, err := db.Query(
		"SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, m.priority, m.requires_ack, m.created_at "+
			"FROM messages m WHERE m.requires_ack = 1 AND m.recipient = ? "+
			"AND NOT EXISTS (SELECT 1 FROM acknowledgments a WHERE a.message_id = m.id AND a.agent_id = ?) "+
			"ORDER BY m.created_at ASC",
		c.AgentID, c.AgentID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	messages := []Message{}
	for rows.Next() {
		var m Message
		var priority, requiresAck int
		if err := rows.Scan(&m.ID, &m.Sender, &m.Recipient, &m.Body, &m.ThreadID, &priority, &requiresAck, &m.CreatedAt); err != nil {
			return nil, err
		}
		m.Priority = priority
		m.RequiresAck = requiresAck == 1
		messages = append(messages, m)
	}
	return messages, nil
}

// Heartbeat updates agent's last_seen and optionally status.
// Valid statuses: "active", "working", "idle", "error".
func (c *Client) Heartbeat(status string) error {
	valid := map[string]bool{"active": true, "working": true, "idle": true, "error": true}
	if !valid[status] {
		return fmt.Errorf("status must be one of: active, working, idle, error")
	}
	db, err := c.connect()
	if err != nil {
		return err
	}
	defer db.Close()
	_, err = db.Exec("UPDATE agents SET last_seen=?, status=? WHERE id=?", nowSec(), status, c.AgentID)
	return err
}

// StaleAgent represents an agent that has missed heartbeats.
type StaleAgent struct {
	ID       string  `json:"id"`
	Status   string  `json:"status"`
	LastSeen float64 `json:"last_seen"`
}

// HeartbeatCheck returns agents that missed too many heartbeats.
func (c *Client) HeartbeatCheck(grace float64) ([]StaleAgent, error) {
	if grace <= 0 {
		return nil, fmt.Errorf("grace must be a positive number of seconds")
	}
	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	threshold := nowSec() - grace
	rows, err := db.Query("SELECT id, status, last_seen FROM agents WHERE last_seen < ? ORDER BY last_seen", threshold)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	stale := []StaleAgent{}
	for rows.Next() {
		var s StaleAgent
		if err := rows.Scan(&s.ID, &s.Status, &s.LastSeen); err != nil {
			return nil, err
		}
		stale = append(stale, s)
	}
	return stale, nil
}

// CreateTask creates a new task in the shared task queue.
// dependsOn may be nil for no dependencies.
func (c *Client) CreateTask(title, description, assignedTo string, priority int, dependsOn []int64) (int64, error) {
	if strings.TrimSpace(title) == "" {
		return 0, fmt.Errorf("task title must not be empty")
	}
	if priority < 1 || priority > 4 {
		return 0, fmt.Errorf("priority must be 1-4")
	}
	db, err := c.connect()
	if err != nil {
		return 0, err
	}
	defer db.Close()

	ts := nowSec()
	var depsJSON *string
	if len(dependsOn) > 0 {
		b, _ := json.Marshal(dependsOn)
		s := string(b)
		depsJSON = &s
	}

	var assigned *string
	if assignedTo != "" {
		assigned = &assignedTo
	}

	var desc *string
	if description != "" {
		desc = &description
	}

	result, err := db.Exec(
		"INSERT INTO tasks(title, description, assigned_to, status, priority, dependencies, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
		title, desc, assigned, "planned", priority, depsJSON, ts, ts,
	)
	if err != nil {
		return 0, err
	}

	taskID, err := result.LastInsertId()
	if err != nil {
		return 0, err
	}

	for _, depID := range dependsOn {
		db.Exec("INSERT OR IGNORE INTO task_deps(task_id, depends_on) VALUES (?,?)", taskID, depID)
	}

	return taskID, nil
}

// ListTasks returns tasks with optional status and assigned_to filters.
// status and assignedTo may be empty to skip filtering.
func (c *Client) ListTasks(status, assignedTo string) ([]Task, error) {
	validStatuses := map[string]bool{"planned": true, "in_progress": true, "review_pending": true, "approved": true, "done": true, "blocked": true}
	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	query := "SELECT id, title, description, assigned_to, status, priority, dependencies, result, claimed_at, completed_at, created_at, updated_at FROM tasks"
	var args []interface{}
	var conditions []string

	if status != "" {
		if !validStatuses[status] {
			return nil, fmt.Errorf("invalid status '%s'", status)
		}
		conditions = append(conditions, "status = ?")
		args = append(args, status)
	}
	if assignedTo != "" {
		conditions = append(conditions, "assigned_to = ?")
		args = append(args, assignedTo)
	}
	if len(conditions) > 0 {
		query += " WHERE " + strings.Join(conditions, " AND ")
	}
	query += " ORDER BY priority ASC, created_at DESC"

	rows, err := db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	tasks := []Task{}
	for rows.Next() {
		var t Task
		var description, assigned, deps, result sql.NullString
		var claimedAt, completedAt sql.NullFloat64
		err := rows.Scan(&t.ID, &t.Title, &description, &assigned, &t.Status, &t.Priority, &deps, &result, &claimedAt, &completedAt, &t.CreatedAt, &t.UpdatedAt)
		if err != nil {
			return nil, err
		}
		if description.Valid {
			t.Description = &description.String
		}
		if assigned.Valid {
			t.AssignedTo = &assigned.String
		}
		if deps.Valid {
			t.Dependencies = &deps.String
		}
		if result.Valid {
			t.Result = &result.String
		}
		if claimedAt.Valid {
			t.ClaimedAt = &claimedAt.Float64
		}
		if completedAt.Valid {
			t.CompletedAt = &completedAt.Float64
		}
		tasks = append(tasks, t)
	}
	return tasks, nil
}

// UpdateTaskStatus updates task status with state machine validation.
func (c *Client) UpdateTaskStatus(taskID int64, newStatus string) error {
	validStatuses := map[string]bool{"planned": true, "in_progress": true, "review_pending": true, "approved": true, "done": true, "blocked": true}
	transitions := map[string]map[string]bool{
		"planned":       {"in_progress": true},
		"in_progress":   {"review_pending": true, "blocked": true, "done": true},
		"review_pending": {"approved": true, "in_progress": true, "blocked": true},
		"approved":      {"done": true, "in_progress": true},
		"done":          {},
		"blocked":       {"in_progress": true},
	}
	if taskID <= 0 {
		return fmt.Errorf("task_id must be a positive integer")
	}
	if !validStatuses[newStatus] {
		return fmt.Errorf("invalid status '%s'", newStatus)
	}
	db, err := c.connect()
	if err != nil {
		return err
	}
	defer db.Close()

	var currentStatus string
	if err := db.QueryRow("SELECT status FROM tasks WHERE id=?", taskID).Scan(&currentStatus); err != nil {
		return fmt.Errorf("task #%d not found", taskID)
	}
	if !transitions[currentStatus][newStatus] {
		return fmt.Errorf("invalid transition from '%s' to '%s'", currentStatus, newStatus)
	}

	ts := nowSec()
	if newStatus == "done" {
		_, err = db.Exec("UPDATE tasks SET status=?, completed_at=?, updated_at=? WHERE id=?",
			newStatus, ts, ts, taskID)
	} else if newStatus == "in_progress" && currentStatus != "in_progress" {
		_, err = db.Exec("UPDATE tasks SET status=?, claimed_at=?, updated_at=? WHERE id=?",
			newStatus, ts, ts, taskID)
	} else {
		_, err = db.Exec("UPDATE tasks SET status=?, updated_at=? WHERE id=?", newStatus, ts, taskID)
	}
	return err
}

// ClaimTask claims a task by assigning self and setting to in_progress.
func (c *Client) ClaimTask(taskID int64) error {
	if taskID <= 0 {
		return fmt.Errorf("task_id must be a positive integer")
	}
	db, err := c.connect()
	if err != nil {
		return err
	}
	defer db.Close()

	var currentStatus string
	var assignedTo *string
	if err := db.QueryRow("SELECT status, assigned_to FROM tasks WHERE id=?", taskID).Scan(&currentStatus, &assignedTo); err != nil {
		return fmt.Errorf("task #%d not found", taskID)
	}
	if currentStatus == "done" {
		return fmt.Errorf("task #%d is already done", taskID)
	}
	if assignedTo != nil && *assignedTo != "" && *assignedTo != c.AgentID {
		return fmt.Errorf("task #%d already assigned to '%s'", taskID, *assignedTo)
	}
	ts := nowSec()
	_, err = db.Exec("UPDATE tasks SET status='in_progress', assigned_to=?, claimed_at=?, updated_at=? WHERE id=?",
		c.AgentID, ts, ts, taskID)
	return err
}

// CompleteTask completes a task with an optional result description.
func (c *Client) CompleteTask(taskID int64, result string) error {
	if taskID <= 0 {
		return fmt.Errorf("task_id must be a positive integer")
	}
	db, err := c.connect()
	if err != nil {
		return err
	}
	defer db.Close()

	var count int
	if err := db.QueryRow("SELECT COUNT(1) FROM tasks WHERE id=?", taskID).Scan(&count); err != nil || count == 0 {
		return fmt.Errorf("task #%d not found", taskID)
	}
	ts := nowSec()
	var resultPtr *string
	if result != "" {
		resultPtr = &result
	}
	_, err = db.Exec("UPDATE tasks SET status='done', result=?, completed_at=?, updated_at=? WHERE id=?",
		resultPtr, ts, ts, taskID)
	return err
}

// CleanupExpired deletes messages past their TTL. Returns count deleted.
func (c *Client) CleanupExpired() (int, error) {
	db, err := c.connect()
	if err != nil {
		return 0, err
	}
	defer db.Close()
	res, err := db.Exec(
		"DELETE FROM messages WHERE ttl_seconds IS NOT NULL AND created_at + ttl_seconds < ?",
		nowSec(),
	)
	if err != nil {
		return 0, err
	}
	n, _ := res.RowsAffected()
	return int(n), nil
}

// ProjectInfo returns resolved project information.
func (c *Client) ProjectInfo() map[string]interface{} {
	_, err := os.Stat(c.dbPath)
	return map[string]interface{}{
		"project": c.Project,
		"db":      c.dbPath,
		"exists":  err == nil,
	}
}

// Clear deletes the database file entirely.
func (c *Client) Clear() error {
	for _, suffix := range []string{"", "-wal", "-shm"} {
		if err := os.Remove(c.dbPath + suffix); err != nil && !os.IsNotExist(err) {
			return err
		}
	}
	return nil
}

// Wait blocks until at least count unread messages exist for this agent,
// or until timeout seconds elapse. Returns true if the required count was reached.
// Messages are marked as read as they arrive (matching Python/JS/Rust behavior).
func (c *Client) Wait(count int, timeoutSec float64) (bool, error) {
	return c.WaitForMessages(count, timeoutSec)
}

// WaitForMessages blocks until N unread messages arrive or timeout elapses.
// Accumulates messages across polls so count > 1 works even when messages
// arrive one at a time. Messages are marked as read as they arrive.
// Matches Python a2a_client.py wait_for_messages() behavior.
func (c *Client) WaitForMessages(count int, timeout float64) (bool, error) {
	if count <= 0 {
		return false, fmt.Errorf("count must be a positive integer")
	}
	if timeout < 0 {
		return false, fmt.Errorf("timeout must be a non-negative number of seconds")
	}
	if math.IsInf(timeout, 0) || math.IsNaN(timeout) {
		return false, fmt.Errorf("timeout must be a finite number")
	}
	deadline := time.Now().Add(time.Duration(timeout * float64(time.Second)))
	seen := 0
	for {
		need := count - seen
		if need <= 0 {
			return true, nil
		}
		if time.Now().After(deadline) {
			return false, nil
		}
		msgs, err := c.Recv(RecvOpts{Wait: 0, UnreadOnly: true, IncludeSelf: false, Limit: need})
		if err != nil {
			return false, err
		}
		seen += len(msgs)
		if seen >= count {
			return true, nil
		}
		if len(msgs) == 0 {
			time.Sleep(500 * time.Millisecond)
		}
	}
}
