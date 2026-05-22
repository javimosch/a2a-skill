# Brand Assets — Collaborative Artifact

Three AI agents (designer, reviewer, converter) collaborate via the a2a bus to produce a complete brand identity package.

## Agents

| Agent | Role | Description |
|-------|------|-------------|
| **designer** | Brand designer | Proposes a brand name, color palette (4-6 hex colors with rationale), and logo concept. Responds to reviewer feedback with refinements. |
| **reviewer** | Brand reviewer | Examines the design for color harmony, logo clarity, and scalability. Suggests concrete improvements, then authorizes the converter. |
| **converter** | Asset converter | Generates the final output files: SVG banner (800x200), ASCII art logo, and an HTML color palette gallery page. |

## Output

```
output/brand/
├── banner.svg       # 800x200 SVG logo banner with gradient and brand name
├── palette.html     # HTML color palette gallery with brand guidelines
├── logo.txt         # ASCII art version of the logo
└── bus-state.txt    # Snapshot of the a2a bus state
```

## Workflow

1. **Designer** proposes a brand identity (name, palette, logo concept) to the reviewer
2. **Reviewer** critiques and suggests improvements
3. **Designer** refines based on feedback
4. **Reviewer** authorizes the converter to proceed
5. **Converter** generates SVG banner, ASCII art logo, and HTML palette gallery
6. **Converter** broadcasts the asset paths on the bus

## Running

```bash
cd /root/projects/a2a-skill
python3 examples/artifacts/brand-assets/build.py --cli opencode
```

## Requirements

- a2a and a2a-spawn (in repo root or PATH)
- An AI CLI (opencode, claude, or pi)
- ascii-image-converter (used by the converter agent for ASCII art)

## Fallback

If agents encounter API errors, the build script generates fallback assets directly — a gradient SVG banner, an ASCII logo, and a color palette HTML page — ensuring output is always produced.
