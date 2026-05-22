# News Briefing — Collaborative Artifact

Two AI agents collaborate via the a2a bus to produce a markdown news briefing
with top technology stories — using **ddgr** (DuckDuckGo CLI) for live web
search and real news aggregation.

## How it works

| Agent | Role | Tool |
|-------|------|------|
| `curator` | Searches for latest tech news, picks top 5-7 stories | `ddgr --json` |
| `narrator` | Writes a formatted briefing with headlines, summaries, and themes | — |

**Flow:** curator → (ddgr searches) → narrator → (produces briefing) → collector

## Requirements

- **a2a** and **a2a-spawn** on your PATH (or the repo root)
- **ddgr** installed (`pip install ddgr` or `brew install ddgr`)
- An AI CLI: `claude`, `opencode`, or `pi`

## Running

```bash
python3 examples/artifacts/news-briefing/build.py --cli opencode
```

## Output

- `output/briefing.md` — the produced news briefing (checked in)
- `output/bus-state.txt` — `a2a peek --limit 30` snapshot of the agent conversation
