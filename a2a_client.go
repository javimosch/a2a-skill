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
	"os"
	"path/filepath"
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
	ID     string `json:"id"`
	Role   string `json:"role"`
	Status string `json:"status"`
	CLI    string `json:"cli"`
}

// Stats represents bus statistics
type Stats struct {
	Messages       int `json:"messages"`
	DirectMessages int `json:"direct_messages"`
	Broadcasts     int `json:"broadcasts"`
	Threads        int `json:"threads"`
	AgentsActive   int `json:"agents_active"`
	AgentsDone     int `json:"agents_done"`
	TopSenders     []struct {
		Agent string `json:"agent"`
		Count int    `json:"count"`
	} `json:"top_senders"`
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

// Send sends a message
func (c *Client) Send(to, message string, ttlSeconds *int) (int64, error) {
	db, err := c.connect()
	if err != nil {
		return 0, err
	}
	defer db.Close()

	recipient := to
	if to == "all" || to == "*" || to == "broadcast" {
		recipient = ""
	}

	result, err := db.Exec(
		"INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) VALUES (?,?,?,?,?)",
		c.AgentID, recipient, message, ttlSeconds, time.Now().Unix(),
	)
	if err != nil {
		return 0, err
	}

	return result.LastInsertId()
}

// Recv receives messages
func (c *Client) Recv(wait int, unreadOnly bool, includeSelf bool, limit int) ([]Message, error) {
	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	deadline := time.Now().Add(time.Duration(wait) * time.Second)
	pollInterval := 100 * time.Millisecond

	for {
		query := "SELECT id, sender, recipient, body, thread_id, created_at FROM messages WHERE (recipient = ? OR recipient IS NULL)"
		args := []interface{}{c.AgentID}

		if !includeSelf {
			query += " AND sender != ?"
			args = append(args, c.AgentID)
		}

		if unreadOnly {
			query += " AND NOT EXISTS (SELECT 1 FROM reads WHERE agent_id = ? AND message_id = messages.id)"
			args = append(args, c.AgentID)
		}

		query += " ORDER BY created_at ASC"
		if limit > 0 {
			query += " LIMIT ?"
			args = append(args, limit)
		}

		rows, err := db.Query(query, args...)
		if err != nil {
			return nil, err
		}

		var messages []Message
		ts := time.Now().Unix()

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

		if wait == 0 || time.Now().After(deadline) {
			return messages, nil
		}

		time.Sleep(pollInterval)
	}
}

// Peek views recent messages without marking read
func (c *Client) Peek(limit int) ([]Message, error) {
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

	var messages []Message
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

	rows, err := db.Query("SELECT id, role, cli, status FROM agents ORDER BY created_at")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var peers []Peer
	for rows.Next() {
		var p Peer
		err := rows.Scan(&p.ID, &p.Role, &p.CLI, &p.Status)
		if err != nil {
			return nil, err
		}
		peers = append(peers, p)
	}

	return peers, nil
}

// SetStatus updates agent status
func (c *Client) SetStatus(status string) error {
	db, err := c.connect()
	if err != nil {
		return err
	}
	defer db.Close()

	_, err = db.Exec(
		"UPDATE agents SET status=?, last_seen=? WHERE id=?",
		status, time.Now().Unix(), c.AgentID,
	)
	return err
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

// Search searches messages by content
func (c *Client) Search(query string, limit int) ([]Message, error) {
	db, err := c.connect()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	rows, err := db.Query(
		"SELECT id, sender, recipient, body, thread_id, created_at FROM messages WHERE body LIKE ? ORDER BY created_at DESC LIMIT ?",
		fmt.Sprintf("%%%s%%", query), limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var messages []Message
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

// Thread gets all messages in a thread
func (c *Client) Thread(threadID string) ([]Message, error) {
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

	var messages []Message
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

	stats := &Stats{}

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
				stats.TopSenders = append(stats.TopSenders, struct {
					Agent string `json:"agent"`
					Count int    `json:"count"`
				}{sender, count})
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
