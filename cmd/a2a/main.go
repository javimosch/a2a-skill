package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/jarancibia/a2a-skill"
)

const Version = "1.0.0"

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
func getFlagInt(name string) int {
	v := getFlagValue(name)
	if v == "" {
		return 0
	}
	n, _ := strconv.Atoi(v)
	return n
}

// getFlagFloat returns float64 for --name.
func getFlagFloat(name string) float64 {
	v := getFlagValue(name)
	if v == "" {
		return 0
	}
	n, _ := strconv.ParseFloat(v, 64)
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
	return a2a.NewClient(resolveProject(), agentID)
}

func printJSON(v interface{}) {
	b, _ := json.MarshalIndent(v, "", "  ")
	fmt.Println(string(b))
}

// ---------- commands ----------

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
	agentID := os.Args[2]
	role := getFlagValue("--role")
	prompt := getFlagValue("--prompt")
	cli := getFlagValue("--cli")
	pid := getFlagInt("--pid")
	upsert := hasFlag("--upsert")

	c := newClient(agentID)
	if err := c.InitProject(); err != nil {
		fmt.Fprintf(os.Stderr, "a2a: register error: %v\n", err)
		os.Exit(1)
	}
	if err := c.Register(role, prompt, cli, pid, upsert); err != nil {
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
	c := newClient(args[0])
	if err := c.Unregister(); err != nil {
		fmt.Fprintf(os.Stderr, "a2a: unregister error: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("removed agent '%s'\n", args[0])
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
		role := p.Role
		if role == "" {
			role = "-"
		}
		cli := p.CLI
		if cli == "" {
			cli = "-"
		}
		fmt.Printf("%-20s %-20s %-10s %-10s\n", p.ID, role, cli, p.Status)
	}
}

func cmdStatus() {
	agentID := getFlagValue("--as")
	jsonFlag := hasFlag("--json")
	args := positionalArgs()

	if len(args) < 1 || agentID == "" {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a status <state> --as <id> [--json]")
		os.Exit(1)
	}
	state := args[0]

	c := newClient(agentID)
	if err := c.SetStatus(state); err != nil {
		fmt.Fprintf(os.Stderr, "a2a: status error: %v\n", err)
		os.Exit(1)
	}

	if jsonFlag {
		printJSON(map[string]interface{}{
			"agent":  agentID,
			"status": state,
		})
	} else {
		fmt.Printf("agent '%s' status -> %s\n", agentID, state)
	}
}

func cmdSend() {
	from := getFlagValue("--from")
	thread := getFlagValue("--thread")
	ttl := getFlagInt("--ttl")
	jsonFlag := hasFlag("--json")
	args := positionalArgs()

	if from == "" || len(args) < 2 {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a send <to> <body> --from <id> [--thread T] [--ttl N] [--json]")
		os.Exit(1)
	}

	to := args[0]
	body := args[1]
	if body == "-" {
		stdin, _ := os.ReadFile(os.Stdin.Name())
		body = strings.TrimSpace(string(stdin))
	}

	var ttlPtr *int
	if ttl > 0 {
		ttlPtr = &ttl
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

	if agentID == "" {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a recv --as <id> [--wait N] [--limit N] [--all] [--include-self] [--peek] [--json]")
		os.Exit(1)
	}

	c := newClient(agentID)
	unreadOnly := !includeAll
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
			msgs, err := c.Recv(0, unreadOnly, includeSelf, limit)
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
	limit := getFlagInt("--limit")
	if limit == 0 {
		limit = 20
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
	threadID := args[0]

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
	limit := getFlagInt("--limit")
	if limit == 0 {
		limit = 50
	}
	jsonFlag := hasFlag("--json")
	args := positionalArgs()
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a search <query> [--limit N] [--json]")
		os.Exit(1)
	}
	query := args[0]

	c := newClient("")
	msgs, err := c.Search(query, limit)
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
	count := getFlagInt("--count")
	if count == 0 {
		count = 1
	}
	timeout := getFlagFloat("--timeout")
	if timeout == 0 {
		timeout = 60
	}

	if agentID == "" {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a wait --as <id> [--count N] [--timeout N]")
		os.Exit(1)
	}

	c := newClient(agentID)
	n, err := c.Wait(count, timeout)
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: wait error: %v\n", err)
		os.Exit(1)
	}
	if n >= count {
		fmt.Printf("ok: %d unread\n", n)
	} else {
		fmt.Fprintf(os.Stderr, "a2a: timeout: only %d unread (wanted %d)\n", n, count)
		os.Exit(2)
	}
}

func cmdClear() {
	if !hasFlag("--yes") {
		fmt.Fprintln(os.Stderr, "a2a: refusing without --yes")
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
	if info["exists"].(bool) {
		fmt.Printf("project '%s' exists at %s\n", info["project"], info["db"])
	} else {
		fmt.Printf("project '%s' — database does not exist at %s\n", info["project"], info["db"])
	}
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
