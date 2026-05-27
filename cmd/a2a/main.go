package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/javimosch/a2a-skill"
)

const Version = "1.3.5"

// Max length limits matching a2a.py constants — validated at Go CLI entry points
// before delegating to the client library.
const (
	maxCLIAgentIDLength  = 256
	maxCLIThreadIDLength = 256
	maxCLIBodyLength     = 100000
)

var _ = strconv.Itoa // ensure import

// hasFlag checks if a flag (--name) is present in os.Args[2:].
func hasFlag(name string) bool {
	for _, a := range os.Args[2:] {
		if a == name {
			return true
		}
	}
	return false
}

// getFlagValue returns the value after --name in os.Args[2:], or empty string.
func getFlagValue(name string) string {
	for i, a := range os.Args[2:] {
		if a == name && i+1 < len(os.Args[2:]) {
			return os.Args[2+i+1]
		}
	}
	return ""
}

// getFlagInt returns int value for --name.
// Exits with error if the value is present but not a valid integer.
func getFlagInt(name string) int {
	v := getFlagValue(name)
	if v == "" {
		return 0
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: --%s must be an integer\n", name)
		os.Exit(1)
	}
	return n
}

// getFlagFloat returns float64 for --name.
// Exits with error if the value is present but not a valid float.
func getFlagFloat(name string) float64 {
	v := getFlagValue(name)
	if v == "" {
		return 0
	}
	n, err := strconv.ParseFloat(v, 64)
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: --%s must be a number\n", name)
		os.Exit(1)
	}
	return n
}

// positionalArgs returns non-flag positional args from os.Args[2:],
// skipping known flag names and their values.
func positionalArgs() []string {
	var args []string
	skipNext := false
	for i := 2; i < len(os.Args); i++ {
		arg := os.Args[i]
		if skipNext {
			skipNext = false
			continue
		}
		if strings.HasPrefix(arg, "--") {
			// --flag value: skip both unless it's --bool-flag without value
			if i+1 < len(os.Args) && !strings.HasPrefix(os.Args[i+1], "--") {
				skipNext = true
			}
			continue
		}
		args = append(args, arg)
	}
	return args
}

func main() {
	if len(os.Args) < 2 {
		printHelp()
		os.Exit(1)
	}

	cmd := os.Args[1]
	switch cmd {
	case "init", "register", "unregister", "list", "status",
		"send", "recv", "peek", "thread", "search", "stats",
		"wait", "clear", "project", "version", "--version", "-v",
		"help", "--help", "-h":
	default:
		fmt.Fprintf(os.Stderr, "a2a: unknown command: %s\n", cmd)
		printHelp()
		os.Exit(1)
	}

	switch cmd {
	case "version", "--version", "-v":
		fmt.Printf("a2a v%s\n", Version)
	case "help", "--help", "-h":
		printHelp()
	case "init":
		cmdInit()
	case "register":
		cmdRegister()
	case "unregister":
		cmdUnregister()
	case "list":
		cmdList()
	case "status":
		cmdStatus()
	case "send":
		cmdSend()
	case "recv":
		cmdRecv()
	case "peek":
		cmdPeek()
	case "thread":
		cmdThread()
	case "search":
		cmdSearch()
	case "stats":
		cmdStats()
	case "wait":
		cmdWait()
	case "clear":
		cmdClear()
	case "project":
		cmdProject()
	}
}

func printHelp() {
	fmt.Println(`a2a — agent-to-agent peer messaging over SQLite

Usage:
  a2a <command> [options]

Commands:
  init                     create project database
  register <id>            register an agent
  unregister <id>          remove an agent
  list [--json]            list agents
  status <state> --as <id>  update agent status (active|idle|done|blocked)
  send <to> <body>         send a message (--from required)
  recv --as <id>           receive messages
  peek [--limit N]         show recent messages (no read-tracking)
  thread <id>              show all messages in a thread
  search <query>           search messages by content
  stats [--json]           show bus statistics
  wait --as <id>           block until N unread messages or timeout
  clear --yes              delete the project database
  project                  show resolved project info
  version                  show version information

Project resolution:
  --project NAME  >  $A2A_PROJECT  >  basename($PWD)`)
}

func resolveProject() string {
	for i, arg := range os.Args {
		if arg == "--project" && i+1 < len(os.Args) {
			return os.Args[i+1]
		}
	}
	if env := os.Getenv("A2A_PROJECT"); env != "" {
		return env
	}
	wd, err := os.Getwd()
	if err != nil {
		return "default"
	}
	return filepath.Base(wd)
}

func newClient(agentID string) *a2a.Client {
	c, err := a2a.NewClient(resolveProject(), agentID)
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: client error: %v\n", err)
		os.Exit(1)
	}
	return c
}

func printJSON(v interface{}) {
	b, _ := json.MarshalIndent(v, "", "  ")
	fmt.Println(string(b))
}

// ---------- commands ----------

// validateMaxLength checks that the given value does not exceed maxLen.
// Returns true if valid, false and prints error + exits if invalid.
func validateMaxLength(value string, maxLen int, name string) bool {
	if len(value) > maxLen {
		fmt.Fprintf(os.Stderr, "a2a: %s too long (%d chars, max %d)\n", name, len(value), maxLen)
		os.Exit(1)
	}
	return true
}

func cmdInit() {
	c := newClient("")
	if err := c.InitProject(); err != nil {
		fmt.Fprintf(os.Stderr, "a2a: init error: %v\n", err)
		os.Exit(1)
	}
	dbPath := filepath.Join(os.Getenv("HOME"), ".a2a", resolveProject(), "database.db")
	fmt.Printf("a2a project '%s' ready at %s\n", resolveProject(), dbPath)
}

func cmdRegister() {
	if len(os.Args) < 3 || strings.HasPrefix(os.Args[2], "-") {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a register <id> [--role R] [--prompt P] [--cli C] [--pid N] [--upsert]")
		os.Exit(1)
	}
	agentID := strings.TrimSpace(os.Args[2])
	if agentID == "" {
		fmt.Fprintln(os.Stderr, "a2a: agent id must not be empty — pass a valid registered agent id")
		os.Exit(1)
	}
	validateMaxLength(agentID, maxCLIAgentIDLength, "agent id")
	role := getFlagValue("--role")
	prompt := getFlagValue("--prompt")
	cli := getFlagValue("--cli")
	pid := getFlagInt("--pid")
	var pidPtr *int
	if hasFlag("--pid") {
		if pid <= 0 {
			fmt.Fprintln(os.Stderr, "a2a: --pid must be a positive integer")
			os.Exit(1)
		}
		pidPtr = &pid
	}
	if hasFlag("--role") && strings.TrimSpace(role) == "" {
		fmt.Fprintln(os.Stderr, "a2a: --role must not be whitespace-only")
		os.Exit(1)
	}
	if hasFlag("--cli") && strings.TrimSpace(cli) == "" {
		fmt.Fprintln(os.Stderr, "a2a: --cli must not be whitespace-only")
		os.Exit(1)
	}
	upsert := hasFlag("--upsert")

	c := newClient(agentID)
	if err := c.InitProject(); err != nil {
		fmt.Fprintf(os.Stderr, "a2a: register error: %v\n", err)
		os.Exit(1)
	}
	if _, err := c.Register(role, prompt, cli, pidPtr, upsert); err != nil {
		fmt.Fprintf(os.Stderr, "a2a: register error: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("registered agent '%s' in project '%s'\n", agentID, resolveProject())
}

func cmdUnregister() {
	args := positionalArgs()
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a unregister <id>")
		os.Exit(1)
	}
	agentID := strings.TrimSpace(args[0])
	if agentID == "" {
		fmt.Fprintln(os.Stderr, "a2a: agent id must not be empty — pass a valid registered agent id")
		os.Exit(1)
	}
	validateMaxLength(agentID, maxCLIAgentIDLength, "agent id")
	c := newClient(agentID)
	if err := c.Unregister(); err != nil {
		fmt.Fprintf(os.Stderr, "a2a: unregister error: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("removed agent '%s'\n", agentID)
}

func cmdList() {
	c := newClient("")
	peers, err := c.ListPeers()
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: list error: %v\n", err)
		os.Exit(1)
	}
	if hasFlag("--json") {
		printJSON(peers)
		return
	}
	if len(peers) == 0 {
		fmt.Println("(no agents registered)")
		return
	}
	fmt.Printf("%-20s %-20s %-10s %-10s\n", "ID", "ROLE", "CLI", "STATUS")
	for _, p := range peers {
		role := "-"
		if p.Role != nil {
			role = *p.Role
		}
		cli := "-"
		if p.CLI != nil {
			cli = *p.CLI
		}
		fmt.Printf("%-20s %-20s %-10s %-10s\n", p.ID, role, cli, p.Status)
	}
}

func cmdStatus() {
	agentID := getFlagValue("--as")
	jsonFlag := hasFlag("--json")
	args := positionalArgs()

	if len(args) < 1 || strings.TrimSpace(agentID) == "" {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a status <state> --as <id> [--json]")
		os.Exit(1)
	}
	validateMaxLength(agentID, maxCLIAgentIDLength, "--as agent id")
	state := args[0]

	c := newClient(agentID)
	lastSeen, err := c.SetStatus(state)
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: status error: %v\n", err)
		os.Exit(1)
	}

	if jsonFlag {
		printJSON(map[string]interface{}{
			"agent":     agentID,
			"status":    state,
			"last_seen": lastSeen,
		})
	} else {
		fmt.Printf("agent '%s' status -> %s\n", agentID, state)
	}
}

func cmdSend() {
	from := getFlagValue("--from")
	thread := getFlagValue("--thread")
	jsonFlag := hasFlag("--json")
	args := positionalArgs()

	if from == "" || len(args) < 2 {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a send <to> <body> --from <id> [--thread T] [--ttl N] [--json]")
		os.Exit(1)
	}
	if strings.TrimSpace(from) == "" {
		fmt.Fprintln(os.Stderr, "a2a: --from agent id must not be empty")
		os.Exit(1)
	}
	validateMaxLength(from, maxCLIAgentIDLength, "--from agent id")

	if thread != "" && strings.TrimSpace(thread) == "" {
		fmt.Fprintln(os.Stderr, "a2a: --thread must not be empty")
		os.Exit(1)
	}
	if thread != "" {
		validateMaxLength(thread, maxCLIThreadIDLength, "--thread")
	}

	to := args[0]
	body := args[1]
	if strings.TrimSpace(to) == "" {
		fmt.Fprintln(os.Stderr, "a2a: recipient must not be empty")
		os.Exit(1)
	}
	if to != "all" && to != "*" && to != "broadcast" {
		validateMaxLength(to, maxCLIAgentIDLength, "recipient")
	}
	if body == "-" {
		stdin, err := os.ReadFile(os.Stdin.Name())
		if err != nil {
			fmt.Fprintf(os.Stderr, "a2a: failed to read stdin: %v\n", err)
			os.Exit(1)
		}
		body = string(stdin)
	}
	validateMaxLength(body, maxCLIBodyLength, "message body")
	if strings.TrimSpace(body) == "" {
		fmt.Fprintln(os.Stderr, "a2a: warning: sending empty message body")
	}

	var ttlPtr *int
	if hasFlag("--ttl") {
		ttlVal := getFlagValue("--ttl")
		if ttlVal == "" {
			fmt.Fprintln(os.Stderr, "a2a: --ttl requires a numeric value")
			os.Exit(1)
		}
		t, err := strconv.Atoi(ttlVal)
		if err != nil {
			fmt.Fprintf(os.Stderr, "a2a: --ttl must be a positive number of seconds (got %q)\n", ttlVal)
			os.Exit(1)
		}
		if t <= 0 {
			fmt.Fprintln(os.Stderr, "a2a: --ttl must be a positive number of seconds")
			os.Exit(1)
		}
		ttlPtr = &t
	}

	c := newClient(from)
	mid, err := c.Send(to, body, thread, ttlPtr)
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: send error: %v\n", err)
		os.Exit(1)
	}

	target := to
	if to == "all" || to == "*" || to == "broadcast" {
		target = "ALL"
	}

	if jsonFlag {
		printJSON(map[string]interface{}{
			"id":        mid,
			"sender":    from,
			"recipient": target,
		})
	} else {
		fmt.Printf("#%d %s -> %s\n", mid, from, target)
	}
}

func cmdRecv() {
	agentID := getFlagValue("--as")
	waitSec := getFlagFloat("--wait")
	limit := getFlagInt("--limit")
	includeAll := hasFlag("--all")
	includeSelf := hasFlag("--include-self")
	peekMode := hasFlag("--peek")
	jsonFlag := hasFlag("--json")
	sinceStr := getFlagValue("--since")

	if strings.TrimSpace(agentID) == "" {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a recv --as <id> [--wait N] [--limit N] [--all] [--include-self] [--peek] [--since TS] [--json]")
		os.Exit(1)
	}
	validateMaxLength(agentID, maxCLIAgentIDLength, "--as agent id")

	if hasFlag("--wait") && (math.IsInf(waitSec, 0) || math.IsNaN(waitSec)) {
		fmt.Fprintln(os.Stderr, "a2a: --wait must be a finite number")
		os.Exit(1)
	}

	if limit < 0 {
		fmt.Fprintln(os.Stderr, "a2a: --limit must be a non-negative integer")
		os.Exit(1)
	}
	if limit == 0 {
		limit = 100 // Python default
	}

	c := newClient(agentID)
	if exists, err := c.AgentExists(agentID); err != nil || !exists {
		fmt.Fprintf(os.Stderr, "a2a: unknown agent '%s' — register first\n", agentID)
		os.Exit(1)
	}
	unreadOnly := !includeAll

	var since *float64
	if sinceStr != "" {
		s, err := strconv.ParseFloat(sinceStr, 64)
		if err != nil {
			fmt.Fprintf(os.Stderr, "a2a: invalid --since value: %v\n", err)
			os.Exit(1)
		}
		if math.IsInf(s, 0) || math.IsNaN(s) {
			fmt.Fprintln(os.Stderr, "a2a: --since must be a finite number")
			os.Exit(1)
		}
		if s < 0 {
			fmt.Fprintln(os.Stderr, "a2a: --since must be a non-negative timestamp")
			os.Exit(1)
		}
		since = &s
	}

	deadline := time.Now().Add(time.Duration(waitSec * float64(time.Second)))
	pollInterval := 500 * time.Millisecond

	for {
		if peekMode {
			msgs, err := c.Peek(limit)
			if err != nil {
				fmt.Fprintf(os.Stderr, "a2a: recv error: %v\n", err)
				os.Exit(1)
			}
			if len(msgs) > 0 || waitSec == 0 {
				if jsonFlag {
					printJSON(msgs)
				} else {
					printMessages(msgs)
				}
				return
			}
		} else {
			msgs, err := c.Recv(a2a.RecvOpts{
				Wait:        waitSec,
				UnreadOnly:  unreadOnly,
				IncludeSelf: includeSelf,
				Limit:       limit,
				Since:       since,
			})
			if err != nil {
				fmt.Fprintf(os.Stderr, "a2a: recv error: %v\n", err)
				os.Exit(1)
			}
			if len(msgs) > 0 || waitSec == 0 {
				if jsonFlag {
					printJSON(msgs)
				} else {
					printMessages(msgs)
				}
				return
			}
		}

		if time.Now().After(deadline) {
			if jsonFlag {
				printJSON([]a2a.Message{})
			}
			return
		}
		time.Sleep(pollInterval)
	}
}

func cmdPeek() {
	limit := 20
	if hasFlag("--limit") {
		limit = getFlagInt("--limit")
	}
	if limit <= 0 {
		fmt.Fprintln(os.Stderr, "a2a: --limit must be a positive integer")
		os.Exit(1)
	}
	if limit > 1000 {
		limit = 1000
	}
	jsonFlag := hasFlag("--json")

	c := newClient("")
	msgs, err := c.Peek(limit)
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: peek error: %v\n", err)
		os.Exit(1)
	}
	if jsonFlag {
		printJSON(msgs)
	} else {
		printMessages(msgs)
	}
}

func cmdThread() {
	jsonFlag := hasFlag("--json")
	args := positionalArgs()
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a thread <id> [--json]")
		os.Exit(1)
	}
	threadID := strings.TrimSpace(args[0])
	if threadID == "" {
		fmt.Fprintln(os.Stderr, "a2a: thread id must not be empty")
		os.Exit(1)
	}
	validateMaxLength(threadID, maxCLIThreadIDLength, "thread id")

	c := newClient("")
	msgs, err := c.Thread(threadID)
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: thread error: %v\n", err)
		os.Exit(1)
	}
	if jsonFlag {
		printJSON(msgs)
	} else if len(msgs) == 0 {
		fmt.Printf("(no messages in thread '%s')\n", threadID)
	} else {
		printMessages(msgs)
	}
}

func cmdSearch() {
	limit := 50
	if hasFlag("--limit") {
		limit = getFlagInt("--limit")
	}
	if limit <= 0 {
		fmt.Fprintln(os.Stderr, "a2a: --limit must be a positive integer")
		os.Exit(1)
	}
	if limit > 200 {
		limit = 200
	}
	jsonFlag := hasFlag("--json")
	args := positionalArgs()
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a search <query> [--limit N] [--json] [--fts]")
		os.Exit(1)
	}
	query := args[0]
	if strings.TrimSpace(query) == "" {
		fmt.Fprintln(os.Stderr, "a2a: search query is empty — provide a keyword to search for")
		os.Exit(1)
	}
	c := newClient("")
	var msgs []a2a.Message
	var err error
	if hasFlag("--fts") {
		msgs, err = c.SearchFTS(query, limit)
	} else {
		msgs, err = c.Search(query, limit)
	}
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: search error: %v\n", err)
		os.Exit(1)
	}
	if jsonFlag {
		printJSON(msgs)
	} else if len(msgs) == 0 {
		fmt.Printf("(no messages matching '%s')\n", query)
	} else {
		printMessages(msgs)
	}
}

func cmdStats() {
	jsonFlag := hasFlag("--json")

	c := newClient("")
	stats, err := c.Stats()
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: stats error: %v\n", err)
		os.Exit(1)
	}

	if jsonFlag {
		printJSON(stats)
		return
	}

	fmt.Printf("Project: %s\n", resolveProject())
	fmt.Printf("  Messages: %d total (%d direct + %d broadcast)\n", stats.Messages, stats.DirectMessages, stats.Broadcasts)
	fmt.Printf("  Threads: %d\n", stats.Threads)
	fmt.Printf("  Agents: %d active, %d done\n", stats.AgentsActive, stats.AgentsDone)
	if len(stats.TopSenders) > 0 {
		fmt.Println("  Top senders:")
		for _, s := range stats.TopSenders {
			fmt.Printf("    %s: %d messages\n", s.Agent, s.Count)
		}
	}
}

func cmdWait() {
	agentID := getFlagValue("--as")
	count := 1 // default
	if hasFlag("--count") {
		count = getFlagInt("--count")
	}
	timeout := 60.0 // default
	if hasFlag("--timeout") {
		timeout = getFlagFloat("--timeout")
	}

	if strings.TrimSpace(agentID) == "" {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a wait --as <id> [--count N] [--timeout N]")
		os.Exit(1)
	}
	validateMaxLength(agentID, maxCLIAgentIDLength, "--as agent id")

	if count <= 0 {
		fmt.Fprintln(os.Stderr, "a2a: --count must be a positive integer")
		os.Exit(1)
	}

	if math.IsInf(timeout, 0) || math.IsNaN(timeout) {
		fmt.Fprintln(os.Stderr, "a2a: --timeout must be a finite number")
		os.Exit(1)
	}
	if timeout < 0 {
		fmt.Fprintln(os.Stderr, "a2a: --timeout must be a non-negative number")
		os.Exit(1)
	}

	c := newClient(agentID)
	ok, err := c.Wait(count, timeout)
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: wait error: %v\n", err)
		os.Exit(1)
	}
	if ok {
		fmt.Println("ok: unread messages found")
	} else {
		fmt.Fprintf(os.Stderr, "a2a: timeout: no messages after %.0fs\n", timeout)
		os.Exit(2)
	}
}

func cmdClear() {
	if !hasFlag("--yes") {
		fmt.Fprintln(os.Stderr, "a2a: refusing without --yes: this deletes the entire project database and all messages. pass --yes to confirm")
		os.Exit(1)
	}
	c := newClient("")
	if err := c.Clear(); err != nil {
		if os.IsNotExist(err) {
			fmt.Println("(nothing to clear)")
			return
		}
		fmt.Fprintf(os.Stderr, "a2a: clear error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("cleared project database")
}

func cmdProject() {
	c := newClient("")
	info := c.ProjectInfo()
	printJSON(info)
}

func printMessages(msgs []a2a.Message) {
	for _, m := range msgs {
		target := "ALL"
		if m.Recipient != nil {
			target = *m.Recipient
		}
		ts := time.Unix(int64(m.CreatedAt), int64((m.CreatedAt-float64(int64(m.CreatedAt)))*1e9)).Format("15:04:05")
		thread := ""
		if m.ThreadID != nil {
			thread = fmt.Sprintf(" [thread:%s]", *m.ThreadID)
		}
		fmt.Printf("[%s] #%d %s -> %s%s\n", ts, m.ID, m.Sender, target, thread)
		for _, line := range strings.Split(m.Body, "\n") {
			fmt.Printf("    %s\n", line)
		}
	}
}
