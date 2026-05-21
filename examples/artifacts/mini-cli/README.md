# Collaborative Artifact: Mini CLI Tool (tasky)

Two AI agents collaborate to design and implement a small Python CLI tool
— demonstrating the spec-then-implement pattern on the a2a bus.

## Agent team

| Agent | Role | Task |
|-------|------|------|
| `architect` | CLI architect | Designs the tool's spec (commands, API, data format) |
| `implementer` | CLI implementer | Writes the complete implementation from the spec |

## The tool: tasky

`tasky` is a minimal task tracker with zero external dependencies:

```bash
python3 tasky.py add "Write docs"
python3 tasky.py list
python3 tasky.py done 1
python3 tasky.py clear --yes
```

Tasks are stored in `~/.tasky/tasks.json`. Uses only Python stdlib (`json`,
`argparse`, `sys`, `pathlib`).

## Workflow

1. Build script registers and spawns both agents
2. Architect designs the spec and sends it to the implementer
3. Implementer writes the code and broadcasts the final source
4. Build script captures it and writes `output/tasky.py`

## Running

```bash
cd /root/projects/a2a-skill
python3 examples/artifacts/mini-cli/build.py --cli opencode
```

## Output

- `output/tasky.py` — 2,491 bytes, single-file Python CLI
- Valid Python (compiles clean), executable with `#!/usr/bin/env python3`
- Commands: `add`, `list`, `done`, `clear` (no confirmation needed)

## Bus transcript (from opencode build)

```
STATS:
  Messages: 4 total (3 direct + 1 broadcast)
  Agents: 1 collector + 2 worker agents
  Top senders: collector (2), implementer (1), architect (1)

CONVERSATION:
  #1 collector -> architect: Task: Design tasky CLI spec (4 commands, JSON storage)
  #2 collector -> implementer: Task: Wait for spec, then implement single-file Python
  #3 architect -> implementer: Spec: tasky — add/list/done/clear, ~/.tasky/tasks.json, argparse
  #4 implementer -> ALL: FINAL_CODE: ... (complete 85-line Python implementation with all edge cases)
```

## What demonstrates a2a

- **Divided labor**: architect handles design, implementer handles code
- **Dependency ordering**: implementer waits for architect's spec before starting
- **Structured delivery**: `FINAL_CODE:` prefix on the bus marks the deliverable
- **a2a-spawn integration**: agents launched with role-specific kit prompts
