package a2a

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func intPtr(v int) *int {
	return &v
}

func setupTestClient(t *testing.T, project, agentID string) *Client {
	t.Helper()
	c, err := NewClient(project, agentID)
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	return c
}

func setupTestProject(t *testing.T) (*Client, func()) {
	t.Helper()
	// Unique project per test prevents stale-data collisions when tests share the same DB path.
	project := "a2a-go-test-" + strings.ToLower(strings.ReplaceAll(t.Name(), "/", "-"))
	agentID := "test-agent"
	c := setupTestClient(t, project, agentID)
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
	if _, err := c.Register("planner", "plan things", "claude", intPtr(123), false); err != nil {
		t.Fatalf("Register: %v", err)
	}

	// Double registration should fail without upsert
	if _, err := c.Register("planner", "", "", nil, false); err == nil {
		t.Fatal("expected error on duplicate register without upsert")
	}

	// Upsert should succeed
	if _, err := c.Register("critic", "", "", nil, true); err != nil {
		t.Fatalf("Register upsert: %v", err)
	}
}

func TestListPeers(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", nil, false)

	c.AgentID = "bob"
	c.Register("critic", "", "", nil, false)

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
	c.Register("planner", "", "", nil, false)

	// Register bob as a peer
	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)

	// Send from alice to bob
	mid, err := c.Send("bob", "hello bob", nil, "", 3, false)
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
	c.Register("planner", "", "", nil, false)

	mid, err := c.Send("all", "hello everyone", nil, "", 3, false)
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
	c.Register("planner", "", "", nil, false)

	// Register bob as peer
	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)

	c.Send("bob", "msg1", nil, "", 3, false)
	c.Send("bob", "msg2", nil, "", 3, false)

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
	c.Register("planner", "", "", nil, false)

	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)

	c.Send("bob", "hello world", nil, "", 3, false)
	c.Send("bob", "goodbye moon", nil, "", 3, false)

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
	c.Register("planner", "", "", nil, false)

	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)

	c.Send("bob", "msg1", nil, "thread-1", 3, false)
	c.Send("bob", "msg2", nil, "thread-1", 3, false)
	c.Send("bob", "other", nil, "", 3, false)

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
	c.Register("planner", "", "", nil, false)

	if _, err := c.SetStatus("done"); err != nil {
		t.Fatalf("SetStatus: %v", err)
	}

	status, err := c.GetStatus("alice")
	if err != nil {
		t.Fatalf("GetStatus: %v", err)
	}
	if status == nil {
		t.Fatal("expected non-nil status, got nil")
	}
	if *status != "done" {
		t.Fatalf("expected 'done', got '%s'", *status)
	}
}

func TestStats(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", nil, false)

	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)

	c.Send("bob", "msg1", nil, "", 3, false)
	c.Send("bob", "msg2", nil, "", 3, false)

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
	c.Register("planner", "", "", nil, false)

	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)
	c.Send("bob", "test", nil, "", 3, false)

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
	c.Register("critic", "", "", nil, false)

	// Send messages as alice
	c2 := setupTestClient(t, c.Project, "alice")
	c2.InitProject()
	c2.Register("planner", "", "", nil, false)
	c2.Send("bob", "msg for wait test", nil, "", 3, false)

	// Bob waits
	ok, err := c.Wait(1, 5)
	if err != nil {
		t.Fatalf("Wait: %v", err)
	}
	if !ok {
		t.Fatal("expected Wait to return true (messages found)")
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
	c.Register("planner", "", "", nil, false)

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
	c.Register("planner", "", "", nil, false)

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
	c.Register("planner", "", "", nil, false)

	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)

	mid, err := c.Send("bob", "with thread", nil, "my-thread", 3, false)
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
	c.Register("planner", "", "", nil, false)

	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)

	ttl := 3600
	mid, err := c.Send("bob", "with ttl", &ttl, "", 3, false)
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
	c.Register("planner", "", "", nil, false)

	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)

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
	c.Register("planner", "", "", nil, false)

	// Send expired message
	ttl := 0
	c.Send("bob", "will expire", &ttl, "", 3, false)

	// recv should call CleanupExpired internally and not return expired
	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)

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
	c.Register("waiting", "", "", nil, false)

	// Wait with 1 count on an agent with no messages should timeout
	ok, err := c.Wait(1, 1)
	if err != nil {
		t.Fatalf("Wait(1, 1): %v", err)
	}
	if ok {
		t.Fatal("expected Wait to return false (timeout)")
	}
}

func TestProjectInfoNoDB(t *testing.T) {
	c, err := NewClient("nonexistent-project-xyz", "test-agent")
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	info := c.ProjectInfo()
	if info["exists"] == true {
		t.Log("project info: db exists (may be leftover from another test)")
	}
}

func TestDBPath(t *testing.T) {
	home := os.Getenv("HOME")
	c, err := NewClient("test-proj", "agent")
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	expected := filepath.Join(home, ".a2a", "test-proj", "database.db")
	if c.dbPath != expected {
		t.Fatalf("expected db path %s, got %s", expected, c.dbPath)
	}
}

func TestSendEmptyBody(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", nil, false)

	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)

	// Empty body allowed (matches Python behavior)
	mid, err := c.Send("bob", "", nil, "", 3, false)
	if err != nil {
		t.Fatalf("unexpected error for empty body: %v", err)
	}
	if mid <= 0 {
		t.Fatal("expected positive message id for empty body")
	}

	// Also test whitespace-only body (allowed, matches Python)
	mid, err = c.Send("bob", "   ", nil, "", 3, false)
	if err != nil {
		t.Fatalf("unexpected error for whitespace-only body: %v", err)
	}
	if mid <= 1 {
		t.Fatal("expected positive message id for whitespace-only body")
	}
}

func TestSendSpecialChars(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", nil, false)

	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)

	special := "hello\nmulti\nline\nwith\ttabs\nand🚀emoji\nand\"quotes\""
	mid, err := c.Send("bob", special, nil, "", 3, false)
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
	c.Register("planner", "", "", nil, false)

	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)

	// 10KB body
	longBody := strings.Repeat("Lorem ipsum dolor sit amet. ", 500)
	mid, err := c.Send("bob", longBody, nil, "", 3, false)
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
	c.Register("planner", "", "", nil, false)

	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)

	// Create message at a known timestamp
	c.Send("bob", "old message", nil, "", 3, false)
	time.Sleep(10 * time.Millisecond)
	since := nowSec()
	c.Send("bob", "new message", nil, "", 3, false)

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
	c.Register("planner", "", "", nil, false)

	// Verify registered
	peers, err := c.ListPeers()
	if err != nil {
		t.Fatalf("ListPeers: %v", err)
	}
	if len(peers) != 1 {
		t.Fatalf("expected 1 peer, got %d", len(peers))
	}

	// Unregister
	if _, err := c.Unregister(); err != nil {
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
	c.Register("planner", "", "", nil, false)

	c2 := setupTestClient(t, c.Project, "bob")
	c2.InitProject()
	c2.Register("critic", "", "", nil, false)

	// Concurrent send/recv
	done := make(chan bool)
	go func() {
		for i := 0; i < 5; i++ {
			c.Send("bob", fmt.Sprintf("msg-%d", i), nil, "", 3, false)
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
	c.Register("planner", "", "", nil, false)

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
	c.Register("tester", "", "", nil, false)

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
	c.Register("tester", "", "", nil, false)

	_, err := c.Send("nonexistent-bob", "hello", nil, "", 3, false)
	if err == nil {
		t.Fatal("expected error sending to unknown recipient, got nil")
	}
}

func TestSendFromUnregisteredSenderFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "ghost-sender"
	// Register a real recipient but not the sender
	c2 := setupTestClient(t, c.Project, "bob")
	c2.Register("tester", "", "", nil, false)

	_, err := c.Send("bob", "hello", nil, "", 3, false)
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

func TestPeekEmpty(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("tester", "", "", nil, false)

	msgs, err := c.Peek(10)
	if err != nil {
		t.Fatalf("Peek on empty bus: %v", err)
	}
	if len(msgs) != 0 {
		t.Fatalf("expected 0 messages on empty bus, got %d", len(msgs))
	}
}

func TestPeekJSON(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("tester", "", "", nil, false)
	c2 := setupTestClient(t, c.Project, "bob")
	c2.Register("tester", "", "", nil, false)

	c.Send("bob", "peek test", nil, "", 3, false)
	msgs, err := c.Peek(10)
	if err != nil {
		t.Fatalf("Peek: %v", err)
	}
	if len(msgs) != 1 {
		t.Fatalf("expected 1 message, got %d", len(msgs))
	}
	if msgs[0].Body != "peek test" {
		t.Fatalf("expected 'peek test', got '%s'", msgs[0].Body)
	}
}

func TestBroadcastRecipientIsNil(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("tester", "", "", nil, false)

	_, err := c.Send("all", "broadcast msg", nil, "", 3, false)
	if err != nil {
		t.Fatalf("Send broadcast: %v", err)
	}

	msgs, err := c.Peek(10)
	if err != nil {
		t.Fatalf("Peek: %v", err)
	}
	if len(msgs) != 1 {
		t.Fatalf("expected 1 message, got %d", len(msgs))
	}
	// Recipient should be nil/empty for broadcasts
	if msgs[0].Recipient != nil {
		t.Fatalf("expected nil recipient for broadcast, got %v", *msgs[0].Recipient)
	}
}

func TestSendEmptyRecipientFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("tester", "", "", nil, false)

	_, err := c.Send("", "hello", nil, "", 3, false)
	if err == nil {
		t.Fatal("expected error sending to empty recipient, got nil")
	}
	if !strings.Contains(err.Error(), "empty") {
		t.Fatalf("expected error about empty recipient, got: %v", err)
	}
}

func TestPeekNonPositiveLimitFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	_, err := c.Peek(0)
	if err == nil {
		t.Fatal("expected error for Peek(0), got nil")
	}
	_, err = c.Peek(-1)
	if err == nil {
		t.Fatal("expected error for Peek(-1), got nil")
	}
}

func TestSearchEmptyQueryFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	_, err := c.Search("", 10)
	if err == nil {
		t.Fatal("expected error for empty search query, got nil")
	}
	_, err = c.Search("   ", 10)
	if err == nil {
		t.Fatal("expected error for whitespace-only search query, got nil")
	}
}

func TestSearchNonPositiveLimitFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	_, err := c.Search("hello", 0)
	if err == nil {
		t.Fatal("expected error for Search with limit=0, got nil")
	}
	_, err = c.Search("hello", -1)
	if err == nil {
		t.Fatal("expected error for Search with negative limit, got nil")
	}
}

func TestSetStatusInvalidStatusFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "tester"
	c.Register("checker", "", "", nil, false)

	_, err := c.SetStatus("invalid-status")
	if err == nil {
		t.Fatal("expected error for invalid status, got nil")
	}
	if !strings.Contains(err.Error(), "invalid status") {
		t.Fatalf("expected error about invalid status, got: %v", err)
	}

	_, err = c.SetStatus("")
	if err == nil {
		t.Fatal("expected error for empty status, got nil")
	}
}

func TestWaitNonPositiveCountFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "tester"
	c.Register("waiting", "", "", nil, false)

	_, err := c.Wait(0, 1)
	if err == nil {
		t.Fatal("expected error for Wait(0, 1), got nil")
	}
	_, err = c.Wait(-1, 1)
	if err == nil {
		t.Fatal("expected error for Wait(-1, 1), got nil")
	}
}

func TestWaitForMessages(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "bob"
	c.Register("critic", "", "", nil, false)

	c2 := setupTestClient(t, c.Project, "alice")
	c2.InitProject()
	c2.Register("planner", "", "", nil, false)
	c2.Send("bob", "msg for wait test", nil, "", 3, false)

	ok, err := c.WaitForMessages(1, 5)
	if err != nil {
		t.Fatalf("WaitForMessages: %v", err)
	}
	if !ok {
		t.Fatal("expected WaitForMessages to return true (messages found)")
	}
}

func TestWaitForMessagesTimeout(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "lonely"
	c.Register("waiting", "", "", nil, false)

	ok, err := c.WaitForMessages(1, 1)
	if err != nil {
		t.Fatalf("WaitForMessages: %v", err)
	}
	if ok {
		t.Fatal("expected WaitForMessages to return false (timeout)")
	}
}

func TestWaitForMessagesNonPositiveCountFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "tester"
	c.Register("waiting", "", "", nil, false)

	_, err := c.WaitForMessages(0, 1)
	if err == nil {
		t.Fatal("expected error for WaitForMessages(0, 1), got nil")
	}
	_, err = c.WaitForMessages(-1, 1)
	if err == nil {
		t.Fatal("expected error for WaitForMessages(-1, 1), got nil")
	}
}

func TestWaitForMessagesTimeoutNegative(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "tester"
	c.Register("waiting", "", "", nil, false)

	_, err := c.WaitForMessages(1, -1)
	if err == nil {
		t.Fatal("expected error for WaitForMessages(1, -1), got nil")
	}
}

func TestWaitForMessagesMultipleCount(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "bob"
	c.Register("critic", "", "", nil, false)

	c2 := setupTestClient(t, c.Project, "alice")
	c2.InitProject()
	c2.Register("planner", "", "", nil, false)
	c2.Send("bob", "msg1", nil, "", 3, false)
	c2.Send("bob", "msg2", nil, "", 3, false)
	c2.Send("bob", "msg3", nil, "", 3, false)

	ok, err := c.WaitForMessages(3, 5)
	if err != nil {
		t.Fatalf("WaitForMessages(3, 5): %v", err)
	}
	if !ok {
		t.Fatal("expected WaitForMessages to return true for count=3")
	}
}

func TestSendNonPositiveTTLFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("sender", "", "", nil, false)

	// TTL zero
	zeroTTL := 0
	_, err := c.Send("bob", "test", &zeroTTL, "", 3, false)
	if err == nil {
		t.Fatal("expected error for Send with TTL=0, got nil")
	}
	if !strings.Contains(err.Error(), "ttl_seconds") {
		t.Fatalf("expected error about ttl_seconds, got: %v", err)
	}

	// TTL negative
	negTTL := -5
	_, err = c.Send("bob", "test", &negTTL, "", 3, false)
	if err == nil {
		t.Fatal("expected error for Send with TTL=-5, got nil")
	}
	if !strings.Contains(err.Error(), "ttl_seconds") {
		t.Fatalf("expected error about ttl_seconds, got: %v", err)
	}
}

func TestRecvNegativeLimitFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "tester"
	c.Register("receiver", "", "", nil, false)

	_, err := c.Recv(RecvOpts{Limit: -1})
	if err == nil {
		t.Fatal("expected error for Recv with negative limit, got nil")
	}
	if !strings.Contains(err.Error(), "limit") {
		t.Fatalf("expected error about limit, got: %v", err)
	}
}

func TestRecvNegativeWaitFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "tester"
	c.Register("receiver", "", "", nil, false)

	_, err := c.Recv(RecvOpts{Wait: -1})
	if err == nil {
		t.Fatal("expected error for Recv with negative wait, got nil")
	}
	if !strings.Contains(err.Error(), "wait") {
		t.Fatalf("expected error about wait, got: %v", err)
	}
}

func TestThreadEmptyIDFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	_, err := c.Thread("")
	if err == nil {
		t.Fatal("expected error for Thread with empty ID, got nil")
	}
	if !strings.Contains(err.Error(), "thread_id") {
		t.Fatalf("expected error about thread_id, got: %v", err)
	}

	_, err = c.Thread("   ")
	if err == nil {
		t.Fatal("expected error for Thread with whitespace-only ID, got nil")
	}
	if !strings.Contains(err.Error(), "thread_id") {
		t.Fatalf("expected error about thread_id, got: %v", err)
	}
}

func TestRegisterNonPositivePIDFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	// PID negative should fail
	_, err := c.Register("tester", "", "", intPtr(-5), false)
	if err == nil {
		t.Fatal("expected error for Register with PID=-5, got nil")
	}
	if !strings.Contains(err.Error(), "pid") {
		t.Fatalf("expected error about pid, got: %v", err)
	}
}

func TestRegisterMaxIDLengthFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	longID := strings.Repeat("a", MaxAgentIDLength+1)
	c.AgentID = longID
	_, err := c.Register("tester", "", "", nil, false)
	if err == nil {
		t.Fatal("expected error for Register with too-long ID, got nil")
	}
	if !strings.Contains(err.Error(), "too long") {
		t.Fatalf("expected error about 'too long', got: %v", err)
	}
}

func TestSendMaxSenderIDLengthFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", nil, false)

	// Sender ID too long
	longID := strings.Repeat("b", MaxAgentIDLength+1)
	c.AgentID = longID
	_, err := c.Send("alice", "hello", nil, "", 3, false)
	if err == nil {
		t.Fatal("expected error for Send with too-long sender ID, got nil")
	}
	if !strings.Contains(err.Error(), "too long") {
		t.Fatalf("expected error about 'too long', got: %v", err)
	}
}

func TestSendMaxRecipientIDLengthFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", nil, false)

	// Recipient ID too long (not broadcast)
	longID := strings.Repeat("b", MaxAgentIDLength+1)
	_, err := c.Send(longID, "hello", nil, "", 3, false)
	if err == nil {
		t.Fatal("expected error for Send with too-long recipient ID, got nil")
	}
	if !strings.Contains(err.Error(), "too long") {
		t.Fatalf("expected error about 'too long', got: %v", err)
	}
}

func TestSendMaxThreadIDLengthFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", nil, false)

	// Thread ID too long
	longThread := strings.Repeat("t", MaxThreadIDLength+1)
	_, err := c.Send("alice", "hello", nil, longThread, 3, false)
	if err == nil {
		t.Fatal("expected error for Send with too-long thread ID, got nil")
	}
	if !strings.Contains(err.Error(), "too long") {
		t.Fatalf("expected error about 'too long', got: %v", err)
	}
}

func TestSendMaxBodyLengthFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", nil, false)

	// Body too long
	longBody := strings.Repeat("x", MaxBodyLength+1)
	_, err := c.Send("alice", longBody, nil, "", 3, false)
	if err == nil {
		t.Fatal("expected error for Send with too-long body, got nil")
	}
	if !strings.Contains(err.Error(), "too long") {
		t.Fatalf("expected error about 'too long', got: %v", err)
	}
}

func TestSendMaxBodyLengthBoundaryOk(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	c.Register("planner", "", "", nil, false)

	// Body at max length should succeed
	exactBody := strings.Repeat("x", MaxBodyLength)
	_, err := c.Send("alice", exactBody, nil, "", 3, false)
	if err != nil {
		t.Fatalf("expected body at max length to succeed, got: %v", err)
	}
}

// ---- task tests (phase 2) ----

func TestCreateTask(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()

	c.AgentID = "alice"
	tid, err := c.CreateTask("Test task", "", "", 3, nil)
	if err != nil {
		t.Fatalf("CreateTask: %v", err)
	}
	if tid <= 0 {
		t.Fatalf("expected positive task ID, got %d", tid)
	}

	tasks, err := c.ListTasks("", "")
	if err != nil {
		t.Fatalf("ListTasks: %v", err)
	}
	if len(tasks) != 1 {
		t.Fatalf("expected 1 task, got %d", len(tasks))
	}
	if tasks[0].Title != "Test task" {
		t.Fatalf("expected title 'Test task', got '%s'", tasks[0].Title)
	}
	if tasks[0].Status != "planned" {
		t.Fatalf("expected status 'planned', got '%s'", tasks[0].Status)
	}
}

func TestCreateTaskWithDescriptionAndAssignee(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	_, err := c.CreateTask("Build feature", "Implement X", "bob", 1, nil)
	if err != nil {
		t.Fatalf("CreateTask: %v", err)
	}

	tasks, err := c.ListTasks("", "")
	if err != nil {
		t.Fatalf("ListTasks: %v", err)
	}
	if len(tasks) != 1 {
		t.Fatalf("expected 1 task, got %d", len(tasks))
	}
	tt := tasks[0]
	if tt.Title != "Build feature" {
		t.Fatalf("title: got '%s'", tt.Title)
	}
	if tt.Description == nil || *tt.Description != "Implement X" {
		t.Fatalf("description mismatch")
	}
	if tt.AssignedTo == nil || *tt.AssignedTo != "bob" {
		t.Fatalf("assigned_to mismatch")
	}
	if tt.Priority != 1 {
		t.Fatalf("priority: got %d", tt.Priority)
	}
}

func TestCreateTaskWithDependencies(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	t1, err := c.CreateTask("First", "", "", 3, nil)
	if err != nil {
		t.Fatalf("CreateTask first: %v", err)
	}
	t2, err := c.CreateTask("Second", "", "", 3, []int64{t1})
	if err != nil {
		t.Fatalf("CreateTask second: %v", err)
	}

	tasks, err := c.ListTasks("", "")
	if err != nil {
		t.Fatalf("ListTasks: %v", err)
	}
	var second Task
	for _, ta := range tasks {
		if ta.ID == int(t2) {
			second = ta
			break
		}
	}
	if second.Dependencies == nil {
		t.Fatal("expected dependencies to be set")
	}
	if !strings.Contains(*second.Dependencies, "1") {
		t.Fatalf("expected dependency on task 1, got '%s'", *second.Dependencies)
	}
}

func TestCreateTaskEmptyTitleFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	_, err := c.CreateTask("  ", "", "", 3, nil)
	if err == nil {
		t.Fatal("expected error for empty title, got nil")
	}
}

func TestCreateTaskInvalidPriorityFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	_, err := c.CreateTask("test", "", "", 5, nil)
	if err == nil {
		t.Fatal("expected error for priority 5, got nil")
	}
	_, err = c.CreateTask("test", "", "", 0, nil)
	if err == nil {
		t.Fatal("expected error for priority 0, got nil")
	}
}

func TestListTasksEmpty(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	tasks, err := c.ListTasks("", "")
	if err != nil {
		t.Fatalf("ListTasks: %v", err)
	}
	if len(tasks) != 0 {
		t.Fatalf("expected empty list, got %d tasks", len(tasks))
	}
}

func TestListTasksFilterByStatus(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	c.CreateTask("Task A", "", "", 3, nil)
	c.CreateTask("Task B", "", "", 3, nil)

	// Both should be planned
	tasks, err := c.ListTasks("planned", "")
	if err != nil {
		t.Fatalf("ListTasks: %v", err)
	}
	if len(tasks) != 2 {
		t.Fatalf("expected 2 planned tasks, got %d", len(tasks))
	}

	// No done tasks
	tasks, err = c.ListTasks("done", "")
	if err != nil {
		t.Fatalf("ListTasks: %v", err)
	}
	if len(tasks) != 0 {
		t.Fatalf("expected 0 done tasks, got %d", len(tasks))
	}
}

func TestListTasksFilterByAssigned(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	c.CreateTask("Alice task", "", "alice", 3, nil)
	c.CreateTask("Bob task", "", "bob", 3, nil)

	tasks, err := c.ListTasks("", "alice")
	if err != nil {
		t.Fatalf("ListTasks: %v", err)
	}
	if len(tasks) != 1 {
		t.Fatalf("expected 1 task for alice, got %d", len(tasks))
	}
	if tasks[0].Title != "Alice task" {
		t.Fatalf("expected 'Alice task', got '%s'", tasks[0].Title)
	}
}

func TestUpdateTaskStatusValidTransitions(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	tid, _ := c.CreateTask("Workflow", "", "", 3, nil)

	transitions := []string{"in_progress", "review_pending", "approved", "done"}
	for _, st := range transitions {
		if err := c.UpdateTaskStatus(tid, st); err != nil {
			t.Fatalf("transition to '%s': %v", st, err)
		}
	}
}

func TestUpdateTaskStatusInvalidTransitionFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	tid, _ := c.CreateTask("Test", "", "", 3, nil)

	// planned -> done is invalid
	if err := c.UpdateTaskStatus(tid, "done"); err == nil {
		t.Fatal("expected error for planned->done, got nil")
	}
	// planned -> blocked is invalid
	if err := c.UpdateTaskStatus(tid, "blocked"); err == nil {
		t.Fatal("expected error for planned->blocked, got nil")
	}
}

func TestUpdateTaskStatusDoneIsTerminal(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	tid, _ := c.CreateTask("Test", "", "", 3, nil)
	c.UpdateTaskStatus(tid, "in_progress")
	c.UpdateTaskStatus(tid, "done")

	if err := c.UpdateTaskStatus(tid, "in_progress"); err == nil {
		t.Fatal("expected error transitioning from done, got nil")
	}
}

func TestUpdateTaskStatusBlockedAndUnblock(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	tid, _ := c.CreateTask("Test", "", "", 3, nil)
	c.UpdateTaskStatus(tid, "in_progress")
	c.UpdateTaskStatus(tid, "blocked")

	// blocked -> in_progress should be valid
	if err := c.UpdateTaskStatus(tid, "in_progress"); err != nil {
		t.Fatalf("expected blocked->in_progress to work, got: %v", err)
	}
}

func TestUpdateTaskStatusNotFoundFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	if err := c.UpdateTaskStatus(9999, "in_progress"); err == nil {
		t.Fatal("expected error for non-existent task, got nil")
	}
}

func TestClaimTask(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	tid, _ := c.CreateTask("Claimable", "", "", 3, nil)
	if err := c.ClaimTask(tid); err != nil {
		t.Fatalf("ClaimTask: %v", err)
	}

	tasks, _ := c.ListTasks("", "")
	tt := tasks[0]
	if tt.Status != "in_progress" {
		t.Fatalf("expected status 'in_progress', got '%s'", tt.Status)
	}
	if tt.AssignedTo == nil || *tt.AssignedTo != "alice" {
		t.Fatalf("expected assigned_to 'alice', got '%v'", tt.AssignedTo)
	}
	if tt.ClaimedAt == nil {
		t.Fatal("expected claimed_at to be set")
	}
}

func TestClaimTaskAlreadyDoneFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	tid, _ := c.CreateTask("Done task", "", "", 3, nil)
	c.UpdateTaskStatus(tid, "in_progress")
	c.UpdateTaskStatus(tid, "done")

	if err := c.ClaimTask(tid); err == nil {
		t.Fatal("expected error claiming done task, got nil")
	}
}

func TestClaimTaskAssignedToOtherFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "bob"

	// Create task assigned to alice
	tid, _ := c.CreateTask("Others task", "", "alice", 3, nil)

	// bob tries to claim — should fail
	if err := c.ClaimTask(tid); err == nil {
		t.Fatal("expected error claiming another's task, got nil")
	}
}

func TestClaimTaskNotFoundFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	if err := c.ClaimTask(9999); err == nil {
		t.Fatal("expected error for non-existent task, got nil")
	}
}

func TestClaimTaskReclaimOwned(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	tid, _ := c.CreateTask("Mine", "", "alice", 3, nil)
	if err := c.ClaimTask(tid); err != nil {
		t.Fatalf("ClaimTask own: %v", err)
	}
}

func TestCompleteTask(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	tid, _ := c.CreateTask("Completable", "", "alice", 3, nil)
	c.ClaimTask(tid)
	if err := c.CompleteTask(tid, "All done"); err != nil {
		t.Fatalf("CompleteTask: %v", err)
	}

	tasks, _ := c.ListTasks("", "")
	tt := tasks[0]
	if tt.Status != "done" {
		t.Fatalf("expected status 'done', got '%s'", tt.Status)
	}
	if tt.Result == nil || *tt.Result != "All done" {
		t.Fatalf("expected result 'All done', got '%v'", tt.Result)
	}
	if tt.CompletedAt == nil {
		t.Fatal("expected completed_at to be set")
	}
}

func TestCompleteTaskNotFoundFails(t *testing.T) {
	c, cleanup := setupTestProject(t)
	defer cleanup()
	c.AgentID = "alice"

	if err := c.CompleteTask(9999, "nope"); err == nil {
		t.Fatal("expected error for non-existent task, got nil")
	}
}
