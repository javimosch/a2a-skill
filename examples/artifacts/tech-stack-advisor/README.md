# Collaborative Artifact: Tech Stack Advisor

Two AI agents collaborate to research and recommend the best technology
stack for a given category — demonstrating the research-to-recommendation
pipeline on the a2a bus.

## Agent team

| Agent | Role | Task |
|-------|------|------|
| `researcher` | Technology researcher | Uses ddgr to search for the latest tools/tech in a category |
| `recommender` | Technology advisor | Analyzes findings, compares top options, writes recommendation guide |

## Workflow

1. Build script registers and spawns both agents
2. Researcher uses `ddgr --json --num 10` to search for the category
3. Researcher sends structured findings to the recommender via the bus
4. Recommender analyzes the findings, picks top 3, and writes a detailed guide
5. Recommender broadcasts the final guide marked with `GUIDE_START`/`GUIDE_END`
6. Build script captures it and writes `output/tech-stack-guide.md`

## Running

```bash
cd /root/projects/a2a-skill
python3 examples/artifacts/tech-stack-advisor/build.py --cli opencode --category "best python web frameworks 2026"
```

## Output

- `output/tech-stack-guide.md` — formatted markdown guide with comparison table
- `output/bus-state.txt` — raw bus transcript of the collaboration

## What demonstrates a2a

- **Real web research**: researcher agent executes live ddgr searches
- **Bus-based handoff**: structured `FINDINGS:` and `GUIDE_START/GUIDE_END` markers
- **Role specialization**: dedicated researcher (gathers data) and recommender (synthesizes)
- **a2a-spawn integration**: both spawn non-interactively, communicate via send/recv
