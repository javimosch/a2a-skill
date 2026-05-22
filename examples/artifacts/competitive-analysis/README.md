# Competitive Analysis — Collaborative Artifact

Three AI agents collaborate via the a2a bus to produce a markdown competitive
analysis report with a comparison table, market positioning, and
recommendations — using **ddgr** (DuckDuckGo CLI) for live web research.

## How it works

| Agent | Role | Tool |
|-------|------|------|
| `searcher` | Searches the web for competitors in a space | `ddgr --json` |
| `analyst` | Builds a comparison table with features, licenses, and positioning | — |
| `writer` | Compiles a formatted report with market analysis and recommendations | — |

**Flow:** searcher → (ddgr) → analyst → (comparison table) → writer → (broadcasts report) → collector

## Requirements

- **a2a** and **a2a-spawn** on PATH (or repo root)
- **ddgr** installed
- An AI CLI: `claude`, `opencode`, or `pi`

## Running

```bash
# Default topic: open source AI agent frameworks 2026
python3 examples/artifacts/competitive-analysis/build.py --cli opencode

# Custom topic:
python3 examples/artifacts/competitive-analysis/build.py --cli opencode --topic "open source MCP servers 2026"
```

## Output

- `output/competitive-analysis.md` — the produced competitive analysis (checked in)
- `output/bus-state.txt` — `a2a peek --limit 30` snapshot of the agent conversation
