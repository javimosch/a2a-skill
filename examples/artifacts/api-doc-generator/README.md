# API Documentation Generator

A **3-agent collaborative artifact** that researches, organizes, and writes API documentation for the GitHub REST API — all via the a2a peer-to-peer bus.

## Agents

| Agent | Role | Tools |
|-------|------|-------|
| **searcher** | Researches GitHub REST API documentation | `ddgr --json` web search |
| **describer** | Extracts key endpoints, auth methods, rate limits | `a2a` bus communication |
| **docsmith** | Writes formatted markdown docs + HTML via pandoc | `a2a` bus, `pandoc` |

## How it works

1. `build.py` clears the bus, registers all agents, and spawns them via `a2a-spawn`
2. **searcher** uses `ddgr` to find GitHub API docs, sends structured data to describer
3. **describer** organizes findings into sections (overview, auth, rate limits, endpoints, best practices), sends to docsmith
4. **docsmith** writes a comprehensive markdown document and converts to HTML via pandoc
5. The docs are captured from the bus and written to `output/api-docs.md` and `output/api-docs.html`

## Output

- `output/api-docs.md` — the formatted GitHub REST API reference guide
- `output/api-docs.html` — HTML version converted via pandoc
- `output/bus-state.txt` — the full message log from the collaboration

## Run

```bash
python3 examples/artifacts/api-doc-generator/build.py --cli opencode
```

## API Key Note

This artifact requires a working AI CLI (opencode, claude, or pi) with API quota.
When the API key is rate-limited, the build script falls back to generating docs
directly via ddgr web search and pandoc conversion. The agent collaboration path
requires the AI CLI to be available.
