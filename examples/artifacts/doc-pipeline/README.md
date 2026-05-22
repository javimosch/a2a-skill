# Doc Pipeline Artifact

Three agents collaborate to produce a complete documentation bundle:

| Agent | Role | Activity |
|-------|------|----------|
| **Writer** | Document author | Writes a markdown quick-start guide for a2a on the bus |
| **Formatter** | HTML converter | Converts markdown to HTML via pandoc with dark theme styling |
| **Publisher** | Bundle creator | Packages both formats into a zip archive |

## Output

- `output/guide.md` — Markdown version of the quick-start guide
- `output/guide.html` — HTML version with dark theme styling (via pandoc)
- `output/bus-state.txt` — a2a bus message log showing collaboration

## How it works

1. The build script initializes the a2a bus and registers all agents
2. Each agent receives its task via `a2a send` from the collector
3. Agents communicate only through the bus (send/recv)
4. The collector waits for the publisher to confirm completion
5. Output is written to `output/` and checked into version control

## Running

```bash
python3 examples/artifacts/doc-pipeline/build.py --cli opencode
```

## Requirements

- `a2a` and `a2a-spawn` on PATH
- `pandoc` for markdown-to-HTML conversion
- One of: `claude`, `opencode`, or `pi`
