# Collaborative Artifact: Landing Page

Three AI agents collaborate to produce a single HTML landing page for
"FlowForge" — a fictional project management SaaS.

## Agent team

| Agent | Role | Task |
|-------|------|------|
| `designer` | HTML/CSS designer | Proposes the page structure, layout, and styling |
| `copywriter` | Copywriter | Writes marketing copy, headlines, and feature descriptions |
| `integrator` | Integrator | Combines structure and copy into a complete, valid HTML file |

## Workflow

1. Build script registers all agents and spawns them via `a2a-spawn`
2. Designer and copywriter receive their tasks and produce their pieces
3. Both send their work to the integrator
4. Integrator combines everything into a single self-contained HTML page
5. Integrator broadcasts the final HTML on the bus
6. Build script captures the broadcast and writes `output/index.html`

## Running

```bash
cd /root/projects/a2a-skill
python3 examples/artifacts/landing-page/build.py --cli opencode
```

## What demonstrates a2a

- **Peer-to-peer messaging**: agents communicate directly (designer→integrator,
  copywriter→integrator)
- **Bus as source of truth**: the integrator broadcasts the final HTML; the
  build script reads it from the bus
- **Read-tracking**: each agent sees messages only once
- **a2a-spawn integration**: agents launched with standard kit prompts
