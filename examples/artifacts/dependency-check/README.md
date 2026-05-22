# Dependency Security Check

A collaborative security advisory generator. Two agents (fetcher, reporter)
collaborate via the a2a bus to analyze project dependencies and search for
known CVEs using live web search.

## Output

| File | Description |
|------|-------------|
| `output/advisory.md` | Security advisory with per-dependency CVE findings, severity classification, and remediation recommendations |
| `output/bus-state.txt` | Full bus state log showing all agent communication |

## Agent roles

| Agent | Role | Tools |
|-------|------|-------|
| **fetcher** | Reads go.mod, Python imports, and dependency files to build a list of project dependencies | `cat`, `grep` |
| **reporter** | For each dependency, searches ddgr for known CVEs and writes the advisory | `ddgr --json -n 5` |

## How it works

1. **fetcher** scans the repo's dependency files (go.mod, Python imports) and sends the deduplicated list to **reporter**
2. **reporter** iterates through each dependency, searching ddgr for CVE/vulnerability mentions
3. **reporter** compiles the findings into a markdown advisory with severity ratings per dependency
4. **reporter** broadcasts the complete advisory to the bus

If agents hit API key limits, the build script falls back to performing the
CVE searches directly using the same ddgr tool and generating the advisory
from raw search results.

## Running

```bash
python3 examples/artifacts/dependency-check/build.py --cli opencode
```

Requires: a2a, a2a-spawn, ddgr, and an AI CLI (opencode, claude, or pi).
