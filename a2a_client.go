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
	ID        string  `json:"id"`
	Role      *string `json:"role"`
	Prompt    *string `json:"prompt"`
	CLI       *string `json:"cli"`
	Status    string  `json:"status"`
	PID       *int    `json:"pid"`
	CreatedAt float64 `json:"created_at"`
	LastSeen  float64 `json:"last_seen"`
}

// TopSender represents one entry in the top senders stats list.
type TopSender struct {
	Agent string `json:"agent"`
	Count int    `json:"count"`
}

// Stats represents bus statistics
type Stats struct {
	Project        string      `json:"project"`
	Messages       int         `json:"messages"`
	DirectMessages int         `json:"direct_messages"`
	Broadcasts     int         `json:"broadcasts"`
	Threads        int         `json:"threads"`
	AgentsActive   int         `json:"agents_active"`
	AgentsDone     int         `json:"agents_done"`
	TopSenders     []TopSender `json:"top_senders"`
}

// NewClient creates a new a2a client
func NewClient(project, agentID string) *Client {
	dbDir := filepath.Join(os.Getenv("HOME"), ".a2a", project)
	dbPath := filepath.Join(dbDir, "database.db")
	return &Client{
		Project: project,
		AgentID: agentID,
		dbPath:  dbPath,
	}
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
	db.SetConnMaxLifetime(time.Second * 5)
	return db, nil
}

// Send sends a message to a peer (or broadcast if recipient is "all"/"*"/"broadcast").
// threadID may be empty string for no thread. ttlSeconds may be nil for no expiry.
func (c *Client) Send(to, message, threadID string, ttlSeconds *int) (int64, error) {
	if strings.TrimSpace(to) == "" {
		return 0, fmt.Errorf("recipient must not be empty")
	}
	if ttlSeconds != nil && *ttlSeconds <= 0 {
		return 0, fmt.Errorf("ttl_seconds must be a positive number of seconds")
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
	if to != "all" && to != "*" && to != "broadcast" {
		// Validate recipient exists
		if err := db.QueryRow("SELECT COUNT(1) FROM agents WHERE id=?", to).Scan(&count); err != nil || count == 0 {
			return 0, fmt.Errorf("unknown recipient '%s'", to)
		}
		r := to
		recip = &r
	}

	var tid *string
	if threadID != "" {
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
	return c.Send(to, message, "", nil)
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

// Recv receives messages with full options. Calls CleanupExpired and Touch at start.
func (c *Client) Recv(opts RecvOpts) ([]Message, error) {
	if opts.Limit < 0 {
		return nil, fmt.Errorf("limit must be a non-negative integer")
	}
	c.CleanupExpired()
	c.Touch()

	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	deadline := time.Now().Add(time.Duration(opts.Wait * float64(time.Second)))
	pollInterval := 100 * time.Millisecond

	for {
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
		ts := nowSec()

		for rows.Next() {
			var m Message
			err := rows.Scan(&m.ID, &m.Sender, &m.Recipient, &m.Body, &m.ThreadID, &m.CreatedAt)
			if err != nil {
				rows.Close()
				return nil, err
			}
			messages = append(messages, m)

			// Mark as read
			db.Exec("INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) VALUES (?,?,?)",
				c.AgentID, m.ID, ts)
		}
		rows.Close()

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
func (c *Client) RecvSimple(wait int, unreadOnly, includeSelf bool, limit int) ([]Message, error) {
	return c.Recv(RecvOpts{
		Wait:        float64(wait),
		UnreadOnly:  unreadOnly,
		IncludeSelf: includeSelf,
		Limit:       limit,
	})
}

// Peek views recent messages without marking read. Calls CleanupExpired first.
func (c *Client) Peek(limit int) ([]Message, error) {
	if limit <= 0 {
		return nil, fmt.Errorf("limit must be a positive integer")
	}
	c.CleanupExpired()

	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

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

	rows, err := db.Query("SELECT id, role, prompt, cli, status, pid, created_at, last_seen FROM agents ORDER BY created_at")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	peers := []Peer{}
	for rows.Next() {
		var p Peer
		var role, prompt, cli sql.NullString
		var pid sql.NullInt64
		err := rows.Scan(&p.ID, &role, &prompt, &cli, &p.Status, &pid, &p.CreatedAt, &p.LastSeen)
		if err != nil {
			return nil, err
		}
		if role.Valid {
			p.Role = &role.String
		}
		if prompt.Valid {
			p.Prompt = &prompt.String
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

// GetStatus gets agent status
func (c *Client) GetStatus(agentID string) (string, error) {
	if agentID == "" {
		agentID = c.AgentID
	}

	db, err := c.connect()
	if err != nil {
		return "", err
	}
	defer db.Close()

	var status string
	err = db.QueryRow("SELECT status FROM agents WHERE id=?", agentID).Scan(&status)
	if err == sql.ErrNoRows {
		return "", nil
	}
	return status, err
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
		return nil, fmt.Errorf("thread id must not be empty")
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
		Project:    c.Project,
		TopSenders: []TopSender{},
	}

	// Message counts
	db.QueryRow("SELECT COUNT(*) FROM messages").Scan(&stats.Messages)
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
func (c *Client) Register(role, prompt, cli string, pid int, upsert bool) error {
	db, err := c.connect()
	if err != nil {
		return err
	}
	defer db.Close()

	ts := nowSec()
	_, err = db.Exec(
		`INSERT INTO agents(id, role, prompt, cli, status, pid, created_at, last_seen)
		 VALUES (?,?,?,?,?,?,?,?)`,
		c.AgentID, role, prompt, cli, "active", pid, ts, ts,
	)
	if err != nil {
		if upsert {
			_, err = db.Exec(
				`UPDATE agents SET role=COALESCE(?,role), prompt=COALESCE(?,prompt),
				 cli=COALESCE(?,cli), pid=COALESCE(?,pid), status='active', last_seen=?
				 WHERE id=?`,
				role, prompt, cli, pid, ts, c.AgentID,
			)
			return err
		}
		return fmt.Errorf("agent '%s' already registered (use upsert=true to update): %w", c.AgentID, err)
	}
	return nil
}

// Unregister removes an agent from the bus.
func (c *Client) Unregister() error {
	db, err := c.connect()
	if err != nil {
		return err
	}
	defer db.Close()
	_, err = db.Exec("DELETE FROM agents WHERE id=?", c.AgentID)
	return err
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
	return os.Remove(c.dbPath)
}

// Wait blocks until at least count unread messages exist for this agent,
// or until timeout seconds elapse. Returns the number of unread messages found.
func (c *Client) Wait(count int, timeoutSec float64) (int, error) {
	if count <= 0 {
		return 0, fmt.Errorf("count must be a positive integer")
	}
	if math.IsInf(timeoutSec, 0) || math.IsNaN(timeoutSec) {
		return 0, fmt.Errorf("timeout must be a finite number")
	}
	if timeoutSec < 0 {
		return 0, fmt.Errorf("timeout must be a non-negative number")
	}
	deadline := time.Now().Add(time.Duration(timeoutSec * float64(time.Second)))
	pollInterval := 500 * time.Millisecond
	for {
		db, err := c.connect()
		if err != nil {
			return 0, err
		}
		var unread int
		err = db.QueryRow(
			`SELECT COUNT(*) FROM messages m
			 WHERE (m.recipient = ? OR m.recipient IS NULL)
			 AND m.sender != ?
			 AND NOT EXISTS (SELECT 1 FROM reads r WHERE r.agent_id = ? AND r.message_id = m.id)`,
			c.AgentID, c.AgentID, c.AgentID,
		).Scan(&unread)
		db.Close()
		if err != nil {
			return 0, err
		}
		if unread >= count {
			return unread, nil
		}
		if time.Now().After(deadline) {
			return unread, nil
		}
		time.Sleep(pollInterval)
	}
}
