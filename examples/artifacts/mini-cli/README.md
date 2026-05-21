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

```
python3 tasky.py add "Write docs"
python3 tasky.py list
python3 tasky.py done 1
python3 tasky.py clear
```

Tasks are stored in a JSON file. Uses only Python stdlib (`json`, `argparse`,
`sys`, `pathlib`).

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

## What demonstrates a2a

- **Divided labor**: architect handles design, implementer handles code
- **Dependency ordering**: implementer waits for architect's spec before starting
- **Structured delivery**: FINAL_CODE: prefix on the bus marks the deliverable
- **a2a-spawn integration**: agents launched with role-specific kit prompts
