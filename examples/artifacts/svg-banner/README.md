# Collaborative Artifact: SVG Banner

Two AI agents collaborate to produce an SVG banner through iterative
design and critique — demonstrating the peer-review pattern on the a2a bus.

## Agent team

| Agent | Role | Task |
|-------|------|------|
| `designer` | SVG designer | Creates the initial SVG banner |
| `reviewer` | SVG reviewer | Critiques and approves the design |

## Workflow

1. Build script registers and spawns both agents
2. Designer creates an SVG banner and sends it to the reviewer
3. Reviewer sends back constructive critique
4. Designer refines based on feedback
5. After 2 rounds, reviewer broadcasts the final approved SVG
6. Build script captures it and writes `output/banner.svg`

## Running

```bash
cd /root/projects/a2a-skill
python3 examples/artifacts/svg-banner/build.py --cli opencode
```

## What demonstrates a2a

- **Iterative collaboration**: agents go through multiple send/recv rounds
- **Adversarial review loop**: one agent creates, another critiques
- **Structured handoffs**: FINAL_SVG: prefix marks the deliverable on the bus
- **a2a-spawn integration**: both agents share the same bus non-interactively
