# a2a Go CLI Reference

The `a2a` Go CLI binary is a companion to the Python `a2a.py` — same 14 commands
(plus a `version` subcommand that's Go-specific), same flags, same JSON output
— but ships as a single ~1.3MB static binary with zero runtime dependencies. No
python3+sqlite3 required.

## Quick Start

```bash
# Download the binary (or build from source)
curl -sL "https://github.com/jarancibia/a2a-skill/releases/latest/download/a2a-$(uname -s)-$(uname -m)" -o /tmp/a2a
chmod +x /tmp/a2a
/tmp/a2a version

# Initialize and go
/tmp/a2a init
/tmp/a2a register alice --role planner
/tmp/a2a register bob --role critic
/tmp/a2a send bob "hello" --from alice
/tmp/a2a recv --as bob --wait 10
/tmp/a2a status done --as bob
/tmp/a2a clear --yes
```

## Building from Source

```bash
git clone https://github.com/jarancibia/a2a-skill.git
cd a2a-skill
go build -ldflags "-s -w" -tags fts5 -o a2a ./cmd/a2a/
./a2a version
```

## Commands

| Command | Description | Flags |
|---------|-------------|-------|
| `init` | Create project database | `--project NAME` |
| `register <id>` | Register an agent | `--role`, `--prompt`, `--cli`, `--pid`, `--upsert` |
| `unregister <id>` | Remove an agent | |
| `list` | List agents | `--json` |
| `status <state>` | Update agent status | `--as <id>`, `--json` |
| `send <to> <body>` | Send a message | `--from <id>`, `--thread`, `--ttl`, `--json` |
| `recv` | Receive messages | `--as <id>`, `--wait`, `--limit`, `--all`, `--include-self`, `--peek`, `--since <ts>`, `--json` |
| `peek` | Show recent messages | `--limit N`, `--json` |
| `thread <id>` | Show messages in thread | `--json` |
| `search <query>` | Search messages | `--limit N`, `--json`, `--fts` (full-text search) |
| `stats` | Bus statistics | `--json` |
| `wait` | Block for messages | `--as <id>`, `--count N`, `--timeout N` |
| `clear` | Delete database | `--yes` |
| `project` | Show project info | |
| `version` | Show version | |

## Project Resolution

The project name is resolved in this order (same as Python CLI):

1. `--project NAME` flag
2. `$A2A_PROJECT` environment variable
3. `basename($PWD)` (current directory name)

## JSON Output

Every command that supports `--json` outputs the same format as the Python CLI.
This allows seamless switching between the Python and Go implementations
without changing bus consumers.

## Differences from Python CLI

| Aspect | Go Binary | Python CLI |
|--------|-----------|------------|
| Dependencies | None (static binary) | python3 + sqlite3 |
| Startup time | ~5ms | ~80ms |
| Binary size | ~1.3MB | ~15KB (script) |
| FTS5 search | Via build tag `-tags fts5` | Built-in (stdlib sqlite3 may lack) |
| Cross-platform | 4 pre-built binaries | Any platform with Python |

## Agent Bootstrap (Kit Prompt)

The recommended agent bootstrap for maximum reliability uses a fallback chain:

```bash
# Try Go binary first, fall back to Python CLI
A2A="${A2A_BIN:-/tmp/a2a}"
if [ ! -x "$A2A" ]; then
  # Try to download Go binary
  curl -sLf "https://github.com/jarancibia/a2a-skill/releases/latest/download/a2a-$(uname -s)-$(uname -m)" -o "$A2A" 2>/dev/null && chmod +x "$A2A" || {
    # Fall back to Python CLI (a2a.py via wrapper)
    for cand in "$(command -v a2a 2>/dev/null)" "$HOME/.agents/skills/a2a/a2a" "$HOME/.claude/skills/a2a/a2a"; do
      [ -x "$cand" ] && { A2A="$cand"; break; }
    done
  }
fi
echo "using a2a at: $A2A"
```

## See Also

- [GO_CLIENT_API.md](GO_CLIENT_API.md) — Go library reference
- [CLIENT_API.md](CLIENT_API.md) — Python client API
- [QUICKSTART.md](QUICKSTART.md) — Getting started
- [AGENTS.md](../AGENTS.md) — Agent development guide
