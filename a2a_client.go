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
	ID       int       `json:"id"`
	Sender   string    `json:"sender"`
	Recipient *string  `json:"recipient"`
	Body     string    `json:"body"`
	ThreadID *string   `json:"thread_id"`
	CreatedAt float64  `json:"created_at"`
}

// Peer represents an agent on the bus
type Peer struct {
	ID     string  `json:"id"`
	Role   *string `json:"role"`
	CLI    *string `json:"cli"`
	Status string  `json:"status"`
	PID    *int    `json:"pid"`
}

// TopSender represents one entry in the top senders stats list.
type TopSender struct {
	Agent string `json:"agent"`
	Count int    `json:"count"`
}

// Stats represents bus statistics
type Stats struct {
	Messages       int         `json:"messages"`
	DirectMessages int         `json:"direct_messages"`
	Broadcasts     int         `json:"broadcasts"`
	Threads        int         `json:"threads"`
	AgentsActive   int         `json:"agents_active"`
	AgentsDone     int         `json:"agents_done"`
	TopSenders     []TopSender `json:"top_senders"`
}

// NewClient creates a new a2a client
func NewClient(project, agentID string) (*Client, error) {
	if strings.TrimSpace(project) == "" {
		return nil, fmt.Errorf("project must not be empty")
	}
	if strings.Contains(project, "/") || strings.Contains(project, "\\") || strings.HasPrefix(project, ".") {
		return nil, fmt.Errorf("project must not contain path separators or start with dot")
	}
	if strings.TrimSpace(agentID) == "" {
		return nil, fmt.Errorf("agent_id must not be empty")
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
// Matches Python/JS/Rust order: send(to, message, ttl_seconds, thread_id).
func (c *Client) Send(to, message string, ttlSeconds *int, threadID string) (int64, error) {
	if len(c.AgentID) > MaxAgentIDLength {
			return 0, fmt.Errorf("agent_id too long (%d chars, max %d)", len(c.AgentID), MaxAgentIDLength)
	}
	if strings.TrimSpace(to) == "" {
		return 0, fmt.Errorf("recipient must not be empty")
	}
	if ttlSeconds != nil && *ttlSeconds <= 0 {
		return 0, fmt.Errorf("ttl_seconds must be a positive number of seconds")
	}
	if strings.TrimSpace(message) == "" {
		return 0, fmt.Errorf("message body must not be empty")
	}
	if len(message) > MaxBodyLength {
		return 0, fmt.Errorf("message body too long (%d chars, max %d)", len(message), MaxBodyLength)
	}
	db, err := c.connect()
	if err != nil {
		return 0, err
	}
	defer db.Close()

	// Validate sender exists
	var count int
	if err := db.QueryRow("SELECT COUNT(1) FROM agents WHERE id=?", c.AgentID).Scan(&count); err != nil || count == 0 {
		return 0, fmt.Errorf("unknown sender '%s' — register first", c.AgentID)
	}

	var recip *string
	if toLower := strings.ToLower(to); toLower != "all" && toLower != "*" && toLower != "broadcast" {
		if len(to) > MaxAgentIDLength {
			return 0, fmt.Errorf("recipient agent_id too long (%d chars, max %d)", len(to), MaxAgentIDLength)
		}
		// Validate recipient exists
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

	result, err := db.Exec(
		"INSERT INTO messages(sender, recipient, body, thread_id, ttl_seconds, created_at) VALUES (?,?,?,?,?,?)",
		c.AgentID, recip, message, tid, ttlSeconds, nowSec(),
	)
	if err != nil {
		return 0, err
	}

	return result.LastInsertId()
}

// SendSimple sends a message without thread or TTL. Backward-compat wrapper for old 3-arg calls.
func (c *Client) SendSimple(to, message string) (int64, error) {
	return c.Send(to, message, nil, "")
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
		query := "SELECT id, sender, recipient, body, thread_id, created_at FROM messages WHERE (recipient = ? OR recipient IS NULL)"
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

		query += " ORDER BY created_at ASC"
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
			err := rows.Scan(&m.ID, &m.Sender, &m.Recipient, &m.Body, &m.ThreadID, &m.CreatedAt)
			if err != nil {
				rows.Close()
				return nil, err
			}
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
		"SELECT id, sender, recipient, body, thread_id, created_at FROM messages ORDER BY created_at DESC LIMIT ?",
		limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	messages := []Message{}
	for rows.Next() {
		var m Message
		err := rows.Scan(&m.ID, &m.Sender, &m.Recipient, &m.Body, &m.ThreadID, &m.CreatedAt)
		if err != nil {
			return nil, err
		}
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
		"SELECT id, sender, recipient, body, thread_id, created_at FROM messages WHERE lower(body) LIKE ? ORDER BY created_at DESC LIMIT ?",
		fmt.Sprintf("%%%s%%", strings.ToLower(query)), limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	messages := []Message{}
	for rows.Next() {
		var m Message
		err := rows.Scan(&m.ID, &m.Sender, &m.Recipient, &m.Body, &m.ThreadID, &m.CreatedAt)
		if err != nil {
			return nil, err
		}
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
		"SELECT id, sender, recipient, body, thread_id, created_at FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
		threadID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	messages := []Message{}
	for rows.Next() {
		var m Message
		err := rows.Scan(&m.ID, &m.Sender, &m.Recipient, &m.Body, &m.ThreadID, &m.CreatedAt)
		if err != nil {
			return nil, err
		}
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
		TopSenders: []TopSender{},
	}

	// Message counts
	if err := db.QueryRow("SELECT COUNT(*) FROM messages").Scan(&stats.Messages); err != nil {
		return nil, fmt.Errorf("stats query failed (is project initialized?): %w", err)
	}
	db.QueryRow("SELECT COUNT(*) FROM messages WHERE recipient IS NULL").Scan(&stats.Broadcasts)
	db.QueryRow("SELECT COUNT(DISTINCT thread_id) FROM messages WHERE thread_id IS NOT NULL").Scan(&stats.Threads)

	stats.DirectMessages = stats.Messages - stats.Broadcasts

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
CREATE INDEX IF NOT EXISTS idx_messages_created   ON messages(created_at);
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
	if timeout < 0 {
		return false, fmt.Errorf("timeout must be a non-negative number of seconds")
	}
	if math.IsInf(timeout, 0) || math.IsNaN(timeout) {
		return false, fmt.Errorf("timeout must be a finite number")
	}
	deadline := time.Now().Add(time.Duration(timeout * float64(time.Second)))
	seen := 0
	for {
		if time.Now().After(deadline) {
			return false, nil
		}
		need := count - seen
		if need <= 0 {
			return true, nil
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
