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

- `output/banner.svg` — 3,502 bytes, valid SVG XML
- 800×200 banner with dark indigo gradient, node-link graph decoration
- "FlowForge" title with soft glow, "PROJECT MANAGEMENT" subtitle
- Two iterations: v1 → reviewer feedback → v2 (approved)

## Bus transcript

```
STATS:
  Messages: 7 total (6 direct + 1 broadcast)
  Agents: 1 collector + 2 worker agents
  Top senders: reviewer (3), designer (2), collector (2)

CONVERSATION:
  #1 collector -> designer: Your task: Create SVG banner, modern tech aesthetic
  #2 collector -> reviewer: Your task: Review banner for valid XML, color, typography
  #3 designer -> reviewer: SVG v1 — first draft (800x200, indigo palette)
  #4 reviewer -> designer: CRITIQUE — approve structure, suggest typography
  #5 designer -> reviewer: SVG v2 — all refinements applied
  #6 reviewer -> designer: APPROVED — "production-ready banner"
  #7 reviewer -> ALL: FINAL_SVG: ... (final approved SVG)
```

## What demonstrates a2a

- **Iterative collaboration**: agents go through multiple send/recv rounds
- **Adversarial review loop**: one agent creates, another critiques
- **Structured handoffs**: `FINAL_SVG:` prefix marks the deliverable on the bus
- **a2a-spawn integration**: both agents share the same bus non-interactively
