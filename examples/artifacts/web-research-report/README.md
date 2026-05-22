# Web Research Report — Collaborative Artifact

Three AI agents collaborate via the a2a bus to produce a markdown research
report on a real-world topic — using **ddgr** (DuckDuckGo CLI) for live web
research.

## How it works

| Agent | Role | Tool |
|-------|------|------|
| `researcher` | Searches the web and collects raw findings | `ddgr --json` |
| `analyst` | Categorizes findings, extracts patterns, builds structure | — |
| `writer` | Compiles a formatted markdown report with tables, sections, and citations | — |

**Communication flow:**

```
collector → [sends tasks to all three]
researcher → (ddgr search) → analyst → (categories & patterns) → writer → (broadcasts report) → collector
```

All messages flow through the a2a SQLite bus. No central orchestrator — each
agent reads, thinks, writes to the bus, and moves on.

## Requirements

- **a2a** and **a2a-spawn** on your PATH (or the repo root)
- **ddgr** installed (`pip install ddgr` or `brew install ddgr`)
- An AI CLI: `claude`, `opencode`, or `pi`

## Running

```bash
# From the repo root:
python3 examples/artifacts/web-research-report/build.py --cli opencode

# With a custom topic:
python3 examples/artifacts/web-research-report/build.py --cli opencode --topic "best open source databases 2026"

# With a custom project name:
python3 examples/artifacts/web-research-report/build.py --cli opencode --project my-research
```

## Output

- `output/report.md` — the produced research report (checked in)
- `output/bus-state.txt` — `a2a peek --limit 30` snapshot of the agent conversation

## What makes this different

Previous artifacts produce code, HTML, or configuration. This one produces
**knowledge** — a real web-researched document. It demonstrates that a2a
agent teams can wield external CLI tools (ddgr, sc) through the bus to
do research that is grounded in real internet data, not just what the model
already knows.
