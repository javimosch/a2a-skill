package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/jarancibia/a2a-skill"
)

const Version = "1.0.0"

func main() {
	if len(os.Args) < 2 {
		printHelp()
		os.Exit(1)
	}

	cmd := os.Args[1]
	switch cmd {
	case "init", "register", "unregister", "list", "status",
		"send", "recv", "peek", "thread", "search", "stats",
		"wait", "clear", "project", "version", "--version", "-v", "help", "--help", "-h":
		// valid commands
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
	// Check --project flag first
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

func asJSON() bool {
	for _, arg := range os.Args {
		if arg == "--json" {
			return true
		}
	}
	return false
}

func printJSON(v interface{}) {
	b, _ := json.MarshalIndent(v, "", "  ")
	fmt.Println(string(b))
}

func cmdInit() {
	cli := newClient("")
	if err := cli.InitProject(); err != nil {
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

	var role, prompt, cli string
	var pid int
	upsert := false

	fs := flag.NewFlagSet("register", flag.ExitOnError)
	fs.StringVar(&role, "role", "", "")
	fs.StringVar(&prompt, "prompt", "", "")
	fs.StringVar(&cli, "cli", "", "")
	fs.IntVar(&pid, "pid", 0, "")
	fs.BoolVar(&upsert, "upsert", false, "")
	fs.Parse(os.Args[3:])

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
	if len(os.Args) < 3 {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a unregister <id>")
		os.Exit(1)
	}
	c := newClient(os.Args[2])
	if err := c.Unregister(); err != nil {
		fmt.Fprintf(os.Stderr, "a2a: unregister error: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("removed agent '%s'\n", os.Args[2])
}

func cmdList() {
	c := newClient("")
	peers, err := c.ListPeers()
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: list error: %v\n", err)
		os.Exit(1)
	}
	if asJSON() {
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
	fs := flag.NewFlagSet("status", flag.ExitOnError)
	agentID := fs.String("as", "", "")
	jsonFlag := fs.Bool("json", false, "")
	fs.Parse(os.Args[2:])

	if fs.NArg() < 1 || *agentID == "" {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a status <state> --as <id> [--json]")
		os.Exit(1)
	}
	state := fs.Arg(0)

	c := newClient(*agentID)
	if err := c.SetStatus(state); err != nil {
		fmt.Fprintf(os.Stderr, "a2a: status error: %v\n", err)
		os.Exit(1)
	}

	if *jsonFlag {
		printJSON(map[string]interface{}{
			"agent":   *agentID,
			"status":  state,
		})
	} else {
		fmt.Printf("agent '%s' status -> %s\n", *agentID, state)
	}
}

func cmdSend() {
	fs := flag.NewFlagSet("send", flag.ExitOnError)
	from := fs.String("from", "", "")
	thread := fs.String("thread", "", "")
	ttl := fs.Int("ttl", 0, "")
	jsonFlag := fs.Bool("json", false, "")
	fs.Parse(os.Args[2:])

	if *from == "" || fs.NArg() < 2 {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a send <to> <body> --from <id> [--thread T] [--ttl N] [--json]")
		os.Exit(1)
	}

	to := fs.Arg(0)
	body := fs.Arg(1)
	// Read body from stdin if "-"
	if body == "-" {
		stdin, _ := os.ReadFile(os.Stdin.Name())
		body = string(stdin)
	}

	var ttlPtr *int
	if ttl != nil && *ttl > 0 {
		ttlPtr = ttl
	}

	c := newClient(*from)
	mid, err := c.Send(to, body, *thread, ttlPtr)
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: send error: %v\n", err)
		os.Exit(1)
	}

	target := to
	if to == "all" || to == "*" || to == "broadcast" {
		target = "ALL"
	}

	if *jsonFlag {
		printJSON(map[string]interface{}{
			"id":        mid,
			"sender":    *from,
			"recipient": target,
		})
	} else {
		fmt.Printf("#%d %s -> %s\n", mid, *from, target)
	}
}

func cmdRecv() {
	fs := flag.NewFlagSet("recv", flag.ExitOnError)
	agentID := fs.String("as", "", "")
	wait := fs.Float64("wait", 0, "")
	limit := fs.Int("limit", 0, "")
	includeAll := fs.Bool("all", false, "")
	includeSelf := fs.Bool("include-self", false, "")
	peekMode := fs.Bool("peek", false, "")
	jsonFlag := fs.Bool("json", false, "")
	fs.Parse(os.Args[2:])

	if *agentID == "" {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a recv --as <id> [--wait N] [--limit N] [--all] [--include-self] [--peek] [--json]")
		os.Exit(1)
	}

	c := newClient(*agentID)
	unreadOnly := !*includeAll

	deadline := time.Now().Add(time.Duration(*wait) * time.Second)
	pollInterval := 500 * time.Millisecond

	for {
		msgs, err := c.Recv(0, unreadOnly, *includeSelf, *limit)
		if err != nil {
			fmt.Fprintf(os.Stderr, "a2a: recv error: %v\n", err)
			os.Exit(1)
		}

		// Filter out already-read if peeking
		if *peekMode {
			msgs = nil
			// re-fetch without marking read
			dbMsgs, err := c.Peek(*limit)
			if err == nil {
				msgs = dbMsgs
			}
		}

		if len(msgs) > 0 || *wait == 0 {
			c.Touch()
			if *jsonFlag {
				printJSON(msgs)
			} else {
				printMessages(msgs)
			}
			return
		}

		if time.Now().After(deadline) {
			if *jsonFlag {
				printJSON([]a2a.Message{})
			}
			return
		}

		time.Sleep(pollInterval)
	}
}

func cmdPeek() {
	fs := flag.NewFlagSet("peek", flag.ExitOnError)
	limit := fs.Int("limit", 20, "")
	jsonFlag := fs.Bool("json", false, "")
	fs.Parse(os.Args[2:])

	c := newClient("")
	msgs, err := c.Peek(*limit)
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: peek error: %v\n", err)
		os.Exit(1)
	}
	if *jsonFlag {
		printJSON(msgs)
	} else {
		printMessages(msgs)
	}
}

func cmdThread() {
	fs := flag.NewFlagSet("thread", flag.ExitOnError)
	jsonFlag := fs.Bool("json", false, "")
	fs.Parse(os.Args[2:])

	if fs.NArg() < 1 {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a thread <id> [--json]")
		os.Exit(1)
	}
	threadID := fs.Arg(0)

	c := newClient("")
	msgs, err := c.Thread(threadID)
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: thread error: %v\n", err)
		os.Exit(1)
	}
	if *jsonFlag {
		printJSON(msgs)
	} else if len(msgs) == 0 {
		fmt.Printf("(no messages in thread '%s')\n", threadID)
	} else {
		printMessages(msgs)
	}
}

func cmdSearch() {
	fs := flag.NewFlagSet("search", flag.ExitOnError)
	limit := fs.Int("limit", 50, "")
	jsonFlag := fs.Bool("json", false, "")
	fs.Parse(os.Args[2:])

	if fs.NArg() < 1 {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a search <query> [--limit N] [--json]")
		os.Exit(1)
	}
	query := fs.Arg(0)

	c := newClient("")
	msgs, err := c.Search(query, *limit)
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: search error: %v\n", err)
		os.Exit(1)
	}
	if *jsonFlag {
		printJSON(msgs)
	} else if len(msgs) == 0 {
		fmt.Printf("(no messages matching '%s')\n", query)
	} else {
		printMessages(msgs)
	}
}

func cmdStats() {
	jsonFlag := asJSON()

	c := newClient("")
	stats, err := c.Stats()
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: stats error: %v\n", err)
		os.Exit(1)
	}

	if jsonFlag {
		b, _ := json.MarshalIndent(stats, "", "  ")
		fmt.Println(string(b))
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
	fs := flag.NewFlagSet("wait", flag.ExitOnError)
	agentID := fs.String("as", "", "")
	count := fs.Int("count", 1, "")
	timeout := fs.Float64("timeout", 60, "")
	fs.Parse(os.Args[2:])

	if *agentID == "" {
		fmt.Fprintln(os.Stderr, "a2a: usage: a2a wait --as <id> [--count N] [--timeout N]")
		os.Exit(1)
	}

	c := newClient(*agentID)
	n, err := c.Wait(*count, *timeout)
	if err != nil {
		fmt.Fprintf(os.Stderr, "a2a: wait error: %v\n", err)
		os.Exit(1)
	}
	if n >= *count {
		fmt.Printf("ok: %d unread\n", n)
	} else {
		fmt.Fprintf(os.Stderr, "a2a: timeout: only %d unread (wanted %d)\n", n, *count)
		os.Exit(2)
	}
}

func cmdClear() {
	yes := false
	for _, arg := range os.Args {
		if arg == "--yes" {
			yes = true
			break
		}
	}
	if !yes {
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
	// Also include exists in human-readable
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
		ts := time.Unix(int64(m.CreatedAt), 0).Format("15:04:05")
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


