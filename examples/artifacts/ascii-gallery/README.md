# ASCII Art Gallery

Three agents (finder, artist, curator) collaborate via the a2a bus to produce an HTML gallery of ASCII art from famous landmark images.

## How it works

1. **Finder** — Uses `ddgr --json` to search for famous landmark images and their URLs
2. **Artist** — Downloads images and converts them to ASCII art via `ascii-image-converter` (60 chars wide)
3. **Curator** — Collects the ASCII art pieces and arranges them into a styled HTML gallery page

The build script also handles the mechanical parts (image download, ASCII conversion, HTML generation) so the agents can focus on collaboration and creative curation.

## Output

| File | Description |
|------|-------------|
| `output/gallery.html` | Full HTML gallery page with all ASCII art pieces |
| `output/gallery-agent.html` | Agent-curated gallery (if agents produced output) |
| `output/bus-state.txt` | Bus state at the time of collection |
| `output/agent-messages.log` | Agent collaboration log |
| `output/*.txt` | Individual ASCII art pieces for each landmark |

## Running

```bash
cd /root/projects/a2a-skill
python3 examples/artifacts/ascii-gallery/build.py --cli opencode --project artifact-ascii-gallery
```

## Requirements

- `a2a` and `a2a-spawn` on PATH
- `ddgr` for web search (DuckDuckGo CLI)
- `ascii-image-converter` for image-to-ASCII conversion
- `opencode`, `claude`, or `pi` AI CLI
- Python 3 with Pillow (for image handling)

## Agents

| Agent | Role | Tool |
|-------|------|------|
| finder | Web image researcher | `ddgr --json --num 10` |
| artist | ASCII art creator | `curl` + `ascii-image-converter -W 60` |
| curator | HTML gallery builder | a2a bus collaboration |
