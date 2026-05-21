# Collaborative Artifact: Color Palette Preview

Two AI agents collaborate to propose a color palette and generate an HTML
preview page — demonstrating the spec-then-render pattern on the a2a bus.

## Agent team

| Agent | Role | Task |
|-------|------|------|
| `colorist` | Color palette designer | Proposes 5 harmonious colors (primary, secondary, accent, bg, text) |
| `generator` | HTML preview generator | Creates a self-contained HTML page showcasing the palette |

## Workflow

1. Build script registers and spawns both agents
2. Colorist designs a 5-color palette and sends it to the generator
3. Generator creates an HTML preview with color swatches and a mock UI card
4. Generator broadcasts the final HTML on the bus
5. Build script captures it and writes `output/index.html`

## Running

```bash
cd /root/projects/a2a-skill
python3 examples/artifacts/color-palette/build.py --cli opencode
```

## Output

- `output/index.html` — Self-contained HTML page with palette preview
- Color swatches with hex codes and descriptions
- Mock UI card showing colors applied to a real interface
- Responsive layout, inline CSS, valid HTML5

## Bus transcript

```
STATS:
  Messages: 4 total (3 direct + 1 broadcast)
  Agents: 1 collector + 2 worker agents
  Top senders: collector (2), generator (1), colorist (1)

CONVERSATION:
  #1 collector -> colorist: Propose a harmonious 5-color palette for FlowForge
  #2 collector -> generator: Wait for palette spec, then create HTML preview
  #3 colorist -> generator: Palette spec (5 colors with hex codes + descriptions)
  #4 generator -> ALL: <!DOCTYPE html>... (complete HTML preview page)
```

## What demonstrates a2a

- **Divided labor**: colorist handles creative design, generator handles rendering
- **Dependency ordering**: generator waits for palette spec before starting
- **Bus as source of truth**: the final HTML is broadcast and captured from the bus
- **a2a-spawn integration**: agents launched with role-specific kit prompts
