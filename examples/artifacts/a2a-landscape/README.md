# a2a-landscape

Three-agent collaborative analysis of the multi-agent ecosystem, positioning a2a-skill against Google A2A, AutoGen, CrewAI, and LangGraph.

## Agents

| Agent | Role | Tools |
|-------|------|-------|
| searcher | Researches each framework via ddgr | `ddgr --json --num 10` |
| analyst | Compares architectures, builds comparison table | a2a bus |
| writer | Produces final landscape report in markdown | a2a bus |

## Output

- `output/a2a-landscape.md` — Full landscape analysis with comparison table, positioning matrix, and recommendations
- `output/bus-state.txt` — Raw a2a bus transcript showing agent collaboration

## How agents collaborate

1. Build script spawns 3 agents on the a2a bus
2. Script sends each agent their task instructions
3. **searcher** → uses ddgr to research each framework → sends structured findings to **analyst**
4. **analyst** → compares architectures, builds comparison table → sends analysis to **writer**
5. **writer** → compiles final markdown report → broadcasts it as `LANDSCAPE_START...LANDSCAPE_END`
6. Build script extracts the report from the bus and saves to disk

All inter-agent communication goes through `a2a send/recv`. No side channels.
