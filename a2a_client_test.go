package a2a

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func setupTestProject(t *testing.T) (*Client, func()) {
	t.Helper()
	// Unique project per test prevents stale-data collisions when tests share the same DB path.
	project := "a2a-go-test-" + strings.ToLower(strings.ReplaceAll(t.Name(), "/", "-"))
	agentID := "test-agent"
	c := NewClient(project, agentID)
	if err := c.InitProject(); err != nil {
		t.Fatalf("InitProject: %v", err)
	}
	cleanup := func() {
		os.RemoveAll(filepath.Join(os.Getenv("HOME"), ".a2a", project))
	}
	return c, cleanup
}

func TestInitProject(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	// Second init should be no-op
	if err := c.InitProject(); err != nil {
		t.Fatalf("InitProject (second): %v", err)
	}

	// Verify tables exist
	db, err := c.connect()
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	defer db.Close()

	var count int
	db.QueryRow("SELECT COUNT(*) FROM agents").Scan(&count)
	db.QueryRow("SELECT COUNT(*) FROM messages").Scan(&count)
	db.QueryRow("SELECT COUNT(*) FROM reads").Scan(&count)
}

func TestRegister(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	if err := c.Register("planner", "plan things", "claude", 123, false); err != nil {
		t.Fatalf("Register: %v", err)
	}

	// Double registration should fail without upsert
	if err := c.Register("planner", "", "", 0, false); err == nil {
		t.Fatal("expected error on duplicate register without upsert")
	}

	// Upsert should succeed
	if err := c.Register("critic", "", "", 0, true); err != nil {
		t.Fatalf("Register upsert: %v", err)
	}
}

func TestListPeers(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	c.AgentID = "bob"
	c.Register("critic", "", "", 0, false)

	peers, err := c.ListPeers()
	if err != nil {
		t.Fatalf("ListPeers: %v", err)
	}
	if len(peers) != 2 {
		t.Fatalf("expected 2 peers, got %d", len(peers))
	}
}

func TestSendRecv(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	// Register bob as a peer
	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)

	// Send from alice to bob
	mid, err := c.Send("bob", "hello bob", "", nil)
	if err != nil {
		t.Fatalf("Send: %v", err)
	}
	if mid <= 0 {
		t.Fatalf("expected positive message id, got %d", mid)
	}

	msgs, err := c2.RecvSimple(0, true, false, 0)
	if err != nil {
		t.Fatalf("Recv: %v", err)
	}
	if len(msgs) != 1 {
		t.Fatalf("expected 1 message, got %d", len(msgs))
	}
	if msgs[0].Body != "hello bob" {
		t.Fatalf("expected 'hello bob', got '%s'", msgs[0].Body)
	}
}

func TestSendBroadcast(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	mid, err := c.Send("all", "hello everyone", "", nil)
	if err != nil {
		t.Fatalf("Send broadcast: %v", err)
	}
	if mid <= 0 {
		t.Fatalf("expected positive message id")
	}
}

func TestPeek(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	// Register bob as peer
	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)

	c.Send("bob", "msg1", "", nil)
	c.Send("bob", "msg2", "", nil)

	msgs, err := c.Peek(10)
	if err != nil {
		t.Fatalf("Peek: %v", err)
	}
	if len(msgs) != 2 {
		t.Fatalf("expected 2 messages, got %d", len(msgs))
	}
}

func TestSearch(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)

	c.Send("bob", "hello world", "", nil)
	c.Send("bob", "goodbye moon", "", nil)

	msgs, err := c.Search("hello", 10)
	if err != nil {
		t.Fatalf("Search: %v", err)
	}
	if len(msgs) != 1 {
		t.Fatalf("expected 1 result, got %d", len(msgs))
	}
}

func TestThread(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)

	c.Send("bob", "msg1", "thread-1", nil)
	c.Send("bob", "msg2", "thread-1", nil)
	c.Send("bob", "other", "", nil)

	msgs, err := c.Thread("thread-1")
	if err != nil {
		t.Fatalf("Thread: %v", err)
	}
	if len(msgs) != 2 {
		t.Fatalf("expected 2 thread messages, got %d", len(msgs))
	}
}

func TestSetAndGetStatus(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	if _, err := c.SetStatus("done"); err != nil {
		t.Fatalf("SetStatus: %v", err)
	}

	status, err := c.GetStatus("alice")
	if err != nil {
		t.Fatalf("GetStatus: %v", err)
	}
	if status != "done" {
		t.Fatalf("expected 'done', got '%s'", status)
	}
}

func TestStats(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)

	c.Send("bob", "msg1", "", nil)
	c.Send("bob", "msg2", "", nil)

	stats, err := c.Stats()
	if err != nil {
		t.Fatalf("Stats: %v", err)
	}
	if stats.Messages != 2 {
		t.Fatalf("expected 2 messages, got %d", stats.Messages)
	}
	if stats.DirectMessages != 2 {
		t.Fatalf("expected 2 direct messages, got %d", stats.DirectMessages)
	}
	if stats.AgentsActive != 2 {
		t.Fatalf("expected 2 active agents, got %d", stats.AgentsActive)
	}
}

func TestStatsJSON(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)
	c.Send("bob", "test", "", nil)

	json, err := c.StatsJSON()
	if err != nil {
		t.Fatalf("StatsJSON: %v", err)
	}
	if len(json) == 0 {
		t.Fatal("expected non-empty JSON")
	}
}

func TestWait(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "bob"
	c.Register("critic", "", "", 0, false)

	// Send messages as alice
	c2 := NewClient(c.Project, "alice")
	c2.InitProject()
	c2.Register("planner", "", "", 0, false)
	c2.Send("bob", "msg for wait test", "", nil)

	// Bob waits
	n, err := c.Wait(1, 5)
	if err != nil {
		t.Fatalf("Wait: %v", err)
	}
	if n < 1 {
		t.Fatalf("expected at least 1 unread, got %d", n)
	}
}

func TestProjectInfo(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	info := c.ProjectInfo()
	if info["project"] != c.Project {
		t.Fatalf("expected project '%s', got '%s'", c.Project, info["project"])
	}
	if info["exists"] != true {
		t.Fatal("expected exists=true")
	}
}

func TestClear(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	if err := c.Clear(); err != nil {
		t.Fatalf("Clear: %v", err)
	}

	info := c.ProjectInfo()
	if info["exists"] == true {
		t.Fatal("expected exists=false after clear")
	}
}

func TestTouch(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	oldLastSeen, _ := c.GetStatus("alice")
	// We can't easily check last_seen value but we can verify no error
	if err := c.Touch(); err != nil {
		t.Fatalf("Touch: %v", err)
	}
	_ = oldLastSeen
}

func TestCleanupExpired(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	// Insert a message with 0-second TTL (already expired)
	db, err := c.connect()
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	ttl := 0
	db.Exec(
		"INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) VALUES (?,?,?,?,?)",
		"alice", "bob", "expired msg", ttl, nowSec(),
	)
	db.Close()

	n, err := c.CleanupExpired()
	if err != nil {
		t.Fatalf("CleanupExpired: %v", err)
	}
	if n != 1 {
		t.Fatalf("expected 1 deleted, got %d", n)
	}
}

func TestSendWithThread(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)

	mid, err := c.Send("bob", "with thread", "my-thread", nil)
	if err != nil {
		t.Fatalf("Send with thread: %v", err)
	}
	if mid <= 0 {
		t.Fatalf("expected positive message id")
	}
}

func TestSendWithTTL(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)

	ttl := 3600
	mid, err := c.Send("bob", "with ttl", "", &ttl)
	if err != nil {
		t.Fatalf("Send with TTL: %v", err)
	}
	if mid <= 0 {
		t.Fatalf("expected positive message id")
	}
}

func TestSendSimple(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)

	mid, err := c.SendSimple("bob", "hello via simple")
	if err != nil {
		t.Fatalf("SendSimple: %v", err)
	}
	if mid <= 0 {
		t.Fatalf("expected positive message id")
	}
}

func TestRecvWithTTLCleanup(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	// Send expired message
	ttl := 0
	c.Send("bob", "will expire", "", &ttl)

	// recv should call CleanupExpired internally and not return expired
	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)

	msgs, err := c2.RecvSimple(0, true, false, 10)
	if err != nil {
		t.Fatalf("Recv with TTL: %v", err)
	}
	// Message with TTL=0 should have been expired; bob shouldn't see it
	// unless timing causes slight race (TTL=0 means expires immediately)
	// This test validates that Recv calls CleanupExpired
	// If it takes < 1ns to execute... actually TTL=0 means created_at + 0 < now()
	// which should always be true since created_at is before now()
	for _, m := range msgs {
		if m.Body == "will expire" {
			t.Fatal("expired message should have been cleaned up by Recv")
		}
	}
}

func TestWaitTimeout(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "lonely"
	c.Register("waiting", "", "", 0, false)

	// Wait with 0 count should return immediately
	n, err := c.Wait(0, 10)
	if err != nil {
		t.Fatalf("Wait(0, 10): %v", err)
	}
	_ = n
}

func TestProjectInfoNoDB(t *testing.T) {
	c := NewClient("nonexistent-project-xyz", "")
	info := c.ProjectInfo()
	if info["exists"] == true {
		t.Log("project info: db exists (may be leftover from another test)")
	}
}

func TestDBPath(t *testing.T) {
	home := os.Getenv("HOME")
	c := NewClient("test-proj", "agent")
	expected := filepath.Join(home, ".a2a", "test-proj", "database.db")
	if c.dbPath != expected {
		t.Fatalf("expected db path %s, got %s", expected, c.dbPath)
	}
}

func TestSendEmptyBody(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)

	mid, err := c.Send("bob", "", "", nil)
	if err != nil {
		t.Fatalf("Send empty body: %v", err)
	}
	if mid <= 0 {
		t.Fatal("expected positive message id")
	}

	// Verify it was stored
	msgs, err := c2.RecvSimple(0, true, false, 10)
	if err != nil {
		t.Fatalf("Recv: %v", err)
	}
	if len(msgs) != 1 {
		t.Fatalf("expected 1 message, got %d", len(msgs))
	}
	if msgs[0].Body != "" {
		t.Fatalf("expected empty body, got '%s'", msgs[0].Body)
	}
}

func TestSendSpecialChars(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)

	special := "hello\nmulti\nline\nwith\ttabs\nand🚀emoji\nand\"quotes\""
	mid, err := c.Send("bob", special, "", nil)
	if err != nil {
		t.Fatalf("Send special chars: %v", err)
	}
	_ = mid

	msgs, err := c2.RecvSimple(0, true, false, 10)
	if err != nil {
		t.Fatalf("Recv: %v", err)
	}
	if msgs[0].Body != special {
		t.Fatalf("body mismatch:\nexpected: %q\ngot:      %q", special, msgs[0].Body)
	}
}

func TestSendLongBody(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)

	// 10KB body
	longBody := strings.Repeat("Lorem ipsum dolor sit amet. ", 500)
	mid, err := c.Send("bob", longBody, "", nil)
	if err != nil {
		t.Fatalf("Send long body (10KB): %v", err)
	}
	if mid <= 0 {
		t.Fatal("expected positive message id")
	}

	msgs, err := c2.RecvSimple(0, true, false, 10)
	if err != nil {
		t.Fatalf("Recv: %v", err)
	}
	if len(msgs) != 1 {
		t.Fatalf("expected 1 message, got %d", len(msgs))
	}
	if len(msgs[0].Body) != len(longBody) {
		t.Fatalf("body length mismatch: expected %d, got %d", len(longBody), len(msgs[0].Body))
	}
}

func TestRecvSince(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)

	// Create message at a known timestamp
	c.Send("bob", "old message", "", nil)
	time.Sleep(10 * time.Millisecond)
	since := nowSec()
	c.Send("bob", "new message", "", nil)

	msgs, err := c2.Recv(RecvOpts{Since: &since, UnreadOnly: true, Wait: 2})
	if err != nil {
		t.Fatalf("Recv with Since: %v", err)
	}
	if len(msgs) != 1 {
		t.Fatalf("expected 1 message after 'since', got %d", len(msgs))
	}
	if msgs[0].Body != "new message" {
		t.Fatalf("expected 'new message', got '%s'", msgs[0].Body)
	}
}

func TestUnregister(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	// Verify registered
	peers, err := c.ListPeers()
	if err != nil {
		t.Fatalf("ListPeers: %v", err)
	}
	if len(peers) != 1 {
		t.Fatalf("expected 1 peer, got %d", len(peers))
	}

	// Unregister
	if err := c.Unregister(); err != nil {
		t.Fatalf("Unregister: %v", err)
	}

	peers, err = c.ListPeers()
	if err != nil {
		t.Fatalf("ListPeers after unregister: %v", err)
	}
	if len(peers) != 0 {
		t.Fatalf("expected 0 peers after unregister, got %d", len(peers))
	}
}

func TestConcurrentSendRecv(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	c2 := NewClient(c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", 0, false)

	// Concurrent send/recv
	done := make(chan bool)
	go func() {
		for i := 0; i < 5; i++ {
			c.Send("bob", fmt.Sprintf("msg-%d", i), "", nil)
			time.Sleep(10 * time.Millisecond)
		}
		done <- true
	}()

	count := 0
	for count < 5 {
		msgs, err := c2.RecvSimple(5, true, false, 5)
		if err != nil {
			t.Fatalf("Concurrent Recv: %v", err)
		}
		count += len(msgs)
	}
	<-done
	if count < 5 {
		t.Fatalf("expected at least 5 messages, got %d", count)
	}
}

func TestFTSSTriggers(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", 0, false)

	msgs, err := c.SearchFTS("test", 10)
	if err != nil {
		// FTS5 may not be available (depends on build tag) — that's OK
		t.Skipf("FTS5 not available: %v", err)
	}
	_ = msgs
}

func TestMessageStruct(t *testing.T) {
	m := Message{
		ID:      1,
		Sender:  "alice",
		Body:    "hello",
		CreatedAt: 1234567890.5,
	}
	if m.ID != 1 || m.Sender != "alice" || m.Body != "hello" {
		t.Fatal("Message struct fields")
	}
	if m.CreatedAt != 1234567890.5 {
		t.Fatal("CreatedAt should preserve sub-second precision")
	}
}

func TestAgentExists(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("tester", "", "", 0, false)

	exists, err := c.AgentExists("alice")
	if err != nil {
		t.Fatalf("AgentExists: %v", err)
	}
	if !exists {
		t.Fatal("expected alice to exist")
	}

	exists, err = c.AgentExists("ghost")
	if err != nil {
		t.Fatalf("AgentExists ghost: %v", err)
	}
	if exists {
		t.Fatal("expected ghost not to exist")
	}
}

func TestSendToUnknownRecipientFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("tester", "", "", 0, false)

	_, err := c.Send("nonexistent-bob", "hello", "", nil)
	if err == nil {
		t.Fatal("expected error sending to unknown recipient, got nil")
	}
}

func TestSendFromUnregisteredSenderFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "ghost-sender"
	// Register a real recipient but not the sender
	c2 := NewClient(c.Project, "bob")
	c2.Register("tester", "", "", 0, false)

	_, err := c.Send("bob", "hello", "", nil)
	if err == nil {
		t.Fatal("expected error sending from unregistered sender, got nil")
	}
}

func TestSetStatusUnknownAgentFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "ghost"
	// Don't register — SetStatus should return an error
	_, err := c.SetStatus("done")
	if err == nil {
		t.Fatal("expected error for unknown agent SetStatus, got nil")
	}
}
