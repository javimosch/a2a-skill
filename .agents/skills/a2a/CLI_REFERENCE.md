# CLI Reference

`a2a` is available as a Python script (stdlib only) or a Go binary
(zero dependencies, ~1.3MB). Both share the same commands and JSON output.

## Python (reference)

`a2a` is a small Python script. It is CLI-agnostic — anything that can shell out
can use it. Requires python3 + sqlite3 (both stdlib, always available on modern systems).

## Go (companion binary)

The Go binary is a drop-in replacement with faster startup (~5ms vs ~80ms)
and zero runtime dependencies. Download or build:

```bash
# Download latest release
curl -sL "https://github.com/jarancibia/a2a-skill/releases/latest/download/a2a-$(uname -s)-$(uname -m)" -o /tmp/a2a
chmod +x /tmp/a2a

# Or build from source
cd a2a-skill && go build -tags fts5 -o a2a ./cmd/a2a/
```

```
a2a init                                       # create ~/.a2a/{project}/database.db
a2a register <id> [--role R] [--prompt P] [--cli C]  # register an agent
a2a register <id> --upsert                     # update existing agent
a2a unregister <id>                            # remove an agent
a2a list [--json]                              # list agents
a2a send <to> "<body>" --from <id>             # to: agent-id, or 'all' for broadcast
a2a send <to> "<body>" --from <id> --ttl 300   # message expires in 5 minutes
a2a recv --as <id> [--wait 30] [--limit N]     # unread inbox (blocks up to 30s, cap at N)
a2a recv --as <id> --all                       # include already-read messages
a2a recv --as <id> --peek                      # look without marking read
a2a recv --as <id> --include-self              # include own messages
a2a recv --as <id> --since 1700000000          # messages after timestamp
a2a recv --as <id> --json                      # machine-readable output
a2a search <query> [--json] [--limit N]         # search messages by content (substring)
a2a thread <id> [--json]                        # show all messages in a thread
a2a stats [--json]                              # bus statistics (msgs, agents, senders)
a2a peek [--limit 20] [--json]                  # observer view of the bus
a2a status active|idle|done|blocked --as <id>   # update agent status (supports --json)
a2a wait --as <id> --count 1 --timeout 60       # block until N unread
a2a clear --yes                                 # delete the project db
a2a project                                     # show resolved project info
```

`recv` returns *unread* messages addressed to the agent (or broadcast). On a
successful read, messages are marked read for that agent. `--wait N` blocks up
to N seconds for at least one new message.
