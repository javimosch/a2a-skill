# Collaborative Artifact: SVG Banner

Two AI agents collaborate to produce an SVG banner through iterative
design and critique — demonstrating the peer-review pattern on the a2a bus.

## Agent team

| Agent | Role | Task |
|-------|------|------|
| `designer` | SVG designer | Creates the initial SVG banner for "FlowForge" |
| `reviewer` | SVG reviewer | Critiques and approves the design |

## Workflow

1. Build script registers and spawns both agents
2. Designer creates an SVG banner and sends it to the reviewer
3. Reviewer sends back constructive critique
4. Designer refines based on feedback (typography, spacing, layout)
5. After the review round, reviewer broadcasts the final approved SVG
6. Build script captures it and writes `output/banner.svg`

## Running

```bash
cd /root/projects/a2a-skill
python3 examples/artifacts/svg-banner/build.py --cli opencode
```

## Output

- `output/banner.svg` — 5,919 bytes, valid SVG XML
- 800×200 banner with dark indigo gradient, dot-grid pattern, node-link graph
- "FlowForge" title with warm amber glow accent, project management subtitle
- Two rounds: v1 → 5-point reviewer critique → v2 (approved with amber highlights)

## Bus transcript (from opencode build)

```
STATS:
  Messages: 7 total (6 direct + 1 broadcast)
  Agents: 1 collector + 2 worker agents
  Top senders: reviewer (3), designer (2), collector (2)

CONVERSATION:
  #1 collector -> designer: Your task: Create SVG banner (800x200, indigo gradient)
  #2 collector -> reviewer: Your task: Review for XML validity, color, typography
  #3 designer -> reviewer: SVG v1 — indigo monochrome with radial connectors
  #4 reviewer -> designer: 5-point critique: bottom balance, dot grids, icon scale, warm accent, connector opacity
  #5 designer -> reviewer: SVG v2 — amber glow hub, dot-grid pattern, bottom wave lines, bolder branding
  #6 reviewer -> designer: APPROVED — all 5 points addressed, "ready to ship"
  #7 reviewer -> ALL: FINAL_SVG: ... (final approved SVG with warm amber accents)
```

## What demonstrates a2a

- **Iterative collaboration**: agents go through multiple send/recv rounds
- **Adversarial review loop**: one agent creates, another critiques
- **Structured handoffs**: `FINAL_SVG:` prefix marks the deliverable on the bus
- **a2a-spawn integration**: both agents share the same bus non-interactively
