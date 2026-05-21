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

- `output/index.html` — 6,507 bytes, valid HTML5 with inline CSS
- Uses `<!DOCTYPE html>`, responsive design, blue/indigo color scheme
- Sections: nav with CTA, hero with headline + subheadline, feature cards (Kanban, Gantt, Chat), footer with 4-column grid
- Copywriter sends structured text spec, designer sends HTML structure, integrator combines both

## Bus transcript (from opencode build)

```
STATS:
  Messages: 6 total (5 direct + 1 broadcast)
  Agents: 1 collector + 3 worker agents
  Top senders: collector (3), integrator (1), designer (1), copywriter (1)

CONVERSATION:
  #1 collector -> designer: Your task: Propose HTML+CSS structure (nav, hero, features, footer)
  #2 collector -> copywriter: Your task: Write marketing copy (headline, 3 features, CTA)
  #3 collector -> integrator: Your task: Wait for both, combine into complete HTML
  #4 designer -> integrator: <html>... HTML structure + CSS for nav, hero, features, footer
  #5 copywriter -> integrator: MARKETING COPY — "Build Without the Chaos." hero, 3 feature descriptions, CTA
  #6 integrator -> ALL: <!DOCTYPE html>... (complete landing page combining structure + copy)
```

## What demonstrates a2a

- **Peer-to-peer messaging**: agents communicate directly (designer→integrator,
  copywriter→integrator)
- **Bus as source of truth**: the integrator broadcasts the final HTML; the
  build script reads it from the bus
- **Read-tracking**: each agent sees messages only once
- **a2a-spawn integration**: agents launched with standard kit prompts
- **Dependency ordering**: integrator waits for both inputs before producing output
