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
3. Both send their work to the integrator via direct messages
4. Integrator combines everything into a single self-contained HTML page
5. Integrator broadcasts the final HTML on the bus
6. Build script captures the broadcast and writes `output/index.html`

## Running

```bash
cd /root/projects/a2a-skill
python3 examples/artifacts/landing-page/build.py --cli opencode
```

## Output

- `output/index.html` — 13,274 bytes, valid HTML5 with inline CSS
- Uses `<!DOCTYPE html>`, responsive design, blue/indigo color scheme
- Sections: nav, hero with CTA, feature cards (3 items), CTA, footer

## Bus transcript

```
STATS:
  Messages: 6 total (5 direct + 1 broadcast)
  Agents: 1 collector + 3 worker agents
  Top senders: collector (3), integrator (1), designer (1), copywriter (1)

CONVERSATION:
  #1 collector -> designer: Your task: Propose a complete HTML+CSS structure
  #2 collector -> copywriter: Your task: Write compelling marketing copy
  #3 collector -> integrator: Your task: Wait for both, combine into HTML
  #4 copywriter -> integrator: MARKETING COPY — FlowForge (hero, features, CTA)
  #5 designer -> integrator: <!DOCTYPE html>... (HTML structure + CSS)
  #6 integrator -> ALL: <!DOCTYPE html>... (FINAL HTML complete page)
```

## What demonstrates a2a

- **Peer-to-peer messaging**: agents communicate directly (designer→integrator,
  copywriter→integrator)
- **Bus as source of truth**: the integrator broadcasts the final HTML; the
  build script reads it from the bus
- **Read-tracking**: each agent sees messages only once
- **a2a-spawn integration**: agents launched with standard kit prompts
- **Dependency ordering**: integrator waits for both inputs before producing output
