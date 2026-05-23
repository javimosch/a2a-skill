# ASCII Art Gallery

A collaborative a2a artifact that generates an HTML gallery of ASCII art from famous landmark images.

## How It Works

Three agents collaborate via the a2a bus:

1. **Finder** — Uses `ddgr` to search for famous landmark image URLs
2. **Artist** — Downloads images and converts them to ASCII via `ascii-image-converter`
3. **Curator** — Arranges ASCII art pieces into a dark-themed HTML gallery page

The build script also performs an offline fallback: it fetches landmark thumbnail URLs from the Wikipedia API, downloads the images, converts them to ASCII using `ascii-image-converter`, and builds the HTML gallery directly. This ensures output is generated even when agent collaboration is interrupted.

## Agents

| Agent | Role | Tool |
|-------|------|------|
| finder | Searches for landmark image URLs | `ddgr --json --num 5 "famous world landmarks"` |
| artist | Downloads & converts to ASCII | `curl` + `ascii-image-converter -W 60` |
| curator | Assembles HTML gallery | Builds dark-themed gallery page |

## Output

| File | Description |
|------|-------------|
| `output/gallery.html` | Full HTML gallery with all 5 landmarks |
| `output/gallery-agent.html` | Agent-curated gallery version (if agents produced output) |
| `output/eiffel-tower.txt` | ASCII art of the Eiffel Tower |
| `output/taj-mahal.txt` | ASCII art of the Taj Mahal |
| `output/great-pyramid-of-giza.txt` | ASCII art of the Great Pyramid of Giza |
| `output/statue-of-liberty.txt` | ASCII art of the Statue of Liberty |
| `output/sydney-opera-house.txt` | ASCII art of the Sydney Opera House |
| `output/bus-state.txt` | Snapshot of the a2a bus after collaboration |

## Prerequisites

- `a2a` and `a2a-spawn` on PATH
- `ascii-image-converter` — `sc plugins install ascii-image-converter`
- `ddgr` — `sc plugins install ddgr` (already installed)
- An AI CLI: `opencode`, `claude`, or `pi`

## Usage

```bash
# With agent collaboration
python3 examples/artifacts/ascii-gallery/build.py

# Offline mode (download + convert + build gallery, no agents)
python3 examples/artifacts/ascii-gallery/build.py --offline

# Specify project name
python3 examples/artifacts/ascii-gallery/build.py --project my-gallery

# Use a specific CLI
python3 examples/artifacts/ascii-gallery/build.py --cli opencode
```

## Landmarks

- **Eiffel Tower** — Paris, France — wrought-iron lattice tower built 1887-1889
- **Taj Mahal** — Agra, India — ivory-white marble mausoleum built 1631-1648
- **Great Pyramid of Giza** — Giza, Egypt — oldest and largest ancient Egyptian pyramid
- **Statue of Liberty** — New York, USA — colossal copper statue gifted by France in 1886
- **Sydney Opera House** — Sydney, Australia — iconic expressionist performing arts venue
