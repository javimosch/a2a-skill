# Local Discovery — Collaborative Artifact

Two AI agents collaborate via the a2a bus to discover and document businesses
in a category using **ddgr** (DuckDuckGo CLI) for live web search — producing
a structured JSON directory and a formatted markdown report.

## How it works

| Agent | Role | Tool |
|-------|------|------|
| `researcher` | Searches the web and collects structured findings | `ddgr --json` |
| `mapper` | Formats data into JSON + markdown report with statistics | — |

**Communication flow:**

```
collector → [sends tasks to both]
researcher → (ddgr search) → mapper → (JSON + report broadcast) → collector
```

All messages flow through the a2a SQLite bus. No central orchestrator.

## Requirements

- **a2a** and **a2a-spawn** on your PATH (or the repo root)
- **ddgr** installed (`pip install ddgr` or `brew install ddgr`)
- An AI CLI: `claude`, `opencode`, or `pi`

## Running

```bash
# From the repo root:
python3 examples/artifacts/local-discovery/build.py --cli opencode

# With a custom topic:
python3 examples/artifacts/local-discovery/build.py --cli opencode --topic "best AI code editors 2026"

# With a custom project name:
python3 examples/artifacts/local-discovery/build.py --cli opencode --project my-discovery
```

## Output

- `output/report.md` — formatted markdown report with table, stats, and category breakdown
- `output/businesses.json` — structured JSON array (name, description, URL, focus_area)
- `output/bus-state.txt` — `a2a peek --limit 30` snapshot of the agent conversation

## What makes this different

This artifact produces two complementary outputs from a single agent team:
a **machine-readable JSON directory** and a **human-readable report** —
demonstrating that a2a agent teams can produce structured data that feeds
directly into downstream tools and databases.

The mapper agent deduplicates, categorizes, and summarizes the raw search
findings — acting as an AI data pipeline step.
