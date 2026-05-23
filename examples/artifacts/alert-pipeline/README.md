# Alert Pipeline — Collaborative Artifact

Two AI agents collaborate via the a2a bus to check system conditions and
produce a formatted alert log — demonstrating agents using real shell
commands (`df`, `free`, `uptime`, `ddgr`) to gather and evaluate data.

## How it works

| Agent | Role | Tools |
|-------|------|-------|
| `monitor` | Checks disk, memory, load, and searches for news | `df`, `free`, `uptime`, `ddgr` |
| `notifier` | Evaluates thresholds, formats alert log | — |

**Communication flow:**

```
collector → [sends tasks to both]
monitor → (shell commands + ddgr) → notifier → (formatted alert) → collector
```

## Requirements

- **a2a** and **a2a-spawn** on your PATH (or the repo root)
- An AI CLI: `claude`, `opencode`, or `pi`

## Running

```bash
# From the repo root:
python3 examples/artifacts/alert-pipeline/build.py --cli opencode
```

## Output

- `output/alert.log` — formatted system alert with threshold evaluation
- `output/bus-state.txt` — `a2a peek --limit 30` snapshot of the agent conversation

## What makes this different

This artifact demonstrates agents running **real system commands** and
**evaluating thresholds autonomously**. The monitor runs `df`, `free`,
`uptime`, and `ddgr` — sending raw findings to the notifier, which applies
business logic (disk > 80% = CRITICAL) and produces a polished alert.
This is a template for any monitoring → notification pipeline.
