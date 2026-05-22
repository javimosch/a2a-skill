# GitHub Trending Report — Weekly

A **3-agent collaborative artifact** that searches, enriches, and compiles a weekly GitHub trending repositories report — all via the a2a peer-to-peer bus.

## Agents

| Agent | Role | Tools |
|-------|------|-------|
| **searcher** | Searches for trending GitHub repos | `ddgr --json` web search |
| **describer** | Enriches each repo with categories, popularity, descriptions | `a2a` bus communication |
| **compiler** | Writes the final formatted markdown report | `a2a` bus communication |

## How it works

1. `build.py` clears the bus, registers all agents, and spawns them via `a2a-spawn`
2. **searcher** uses `ddgr` to find trending repos, sends the list to describer
3. **describer** enriches each repo with category, popularity rating, and descriptions, sends to compiler
4. **compiler** assembles a polished markdown report with tables, categories, and key takeaways
5. The report is captured from the bus and written to `output/trending.md`

## Output

- `output/trending.md` — the formatted weekly GitHub trending report
- `output/bus-state.txt` — the full message log from the collaboration

## Run

```bash
python3 examples/artifacts/github-trending-report/build.py --cli opencode
```

## API Key Note

This artifact requires a working AI CLI (opencode, claude, or pi) with API quota.
When the API key is rate-limited (as happened on May 22, 2026 during testing),
the build script falls back to a bus-state capture and the reporting data is
generated via direct `ddgr` web search as a manual fallback. The agent
collaboration path requires the AI CLI to be available.
