# weekly-digest — Collaborative Tech News Digest

Three agents (scout → curator → editor) collaborate via the a2a bus to produce
a formatted weekly digest of the latest tech news.

## How it works

1. **scout** — Searches 4 topics (AI, DevOps, Security, Startups) using `ddgr`
   with time-filtered queries (past month). Sends structured findings to curator.
2. **curator** — Reviews all stories across topics, selects the 8-10 most
   interesting ones, and sends a curated list to the editor.
3. **editor** — Compiles a well-formatted markdown digest with per-topic
   sections, bullet-point summaries with source links, and a key takeaways
   conclusion section.

## Output

| File | Description |
|------|-------------|
| `output/weekly-digest.md` | The formatted weekly digest |
| `output/bus-state.txt` | Raw bus message log for debugging |

## Running

```bash
python3 examples/artifacts/weekly-digest/build.py --cli opencode --project my-digest
```

With a specific model:
```bash
python3 examples/artifacts/weekly-digest/build.py --cli opencode --model opencode/deepseek-v4-flash-free
```

## Requirements

- `a2a` and `a2a-spawn` on PATH
- `opencode`, `claude`, or `pi` AI CLI
- `ddgr` installed for web search (via `sc plugins install ddgr`)

## Resilience

The build script detects API key limits and ddgr failures. If agents cannot
produce output, the script falls back to generating a digest from ddgr
search results directly. This ensures the `output/` directory is always
populated, even under degraded conditions.
