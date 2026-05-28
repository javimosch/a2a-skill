# a2a Git-Aware Features

Prevent work collisions and coordinate changes across distributed agents using git state tracking.

## Overview

The git-aware features help teams avoid duplicated work and merge conflicts by:
- Broadcasting git branch and file changes to the a2a bus
- Detecting when multiple agents modify the same files
- Alerting when agents are working on the same branch
- Recommending coordination strategies

## Quick Start

### 1. Broadcaster Agent

Announces current git state periodically:

```bash
python examples/collision_detector.py my-project alice broadcaster
```

This agent:
- Announces branch name every 30 seconds
- Reports changed files
- Sends commit history
- Allows other agents to detect potential conflicts

### 2. Detector Agent

Monitors the bus for collision patterns:

```bash
python examples/collision_detector.py my-project detector-1 detector
```

This agent:
- Listens for git status updates
- Detects same-branch work
- Identifies file overlaps
- Sends alerts to the bus

## API Reference

### GitAwareClient

```python
from a2a_git_aware import GitAwareClient

client = GitAwareClient("alice", repo_path=".")

# Get current branch
branch = client.get_current_branch()

# Get recent commits
commits = client.get_recent_commits(count=10)

# Get changed files
files = client.get_changed_files()

# Full status
status = client.get_branch_status()

# Detect collisions
collisions = client.detect_work_collision(other_agents_branches)

# Format for a2a bus
message = client.format_for_bus()
```

### Integration with A2AClient

```python
import asyncio
from a2a_client_async import A2AClientAsync
from a2a_git_aware import GitAwareClient

async def announce_status():
    async with A2AClientAsync("my-project", "alice") as a2a_client:
        git_client = GitAwareClient("alice")
        
        # Announce git status
        status = git_client.get_branch_status()
        await a2a_client.send("all", json.dumps(status))
        
        # Listen for collision alerts
        messages = await a2a_client.recv(wait=30)
        for msg in messages:
            data = json.loads(msg["body"])
            if data.get("type") == "collision_warning":
                print(f"⚠️  Collision: {data['agents']} on {data['branch']}")

asyncio.run(announce_status())
```

## Message Types

### Git Status Update

```json
{
  "branch": "feature/auth",
  "agent": "alice",
  "commits": [
    {"hash": "abc123", "author": "alice", "message": "Add login", "timestamp": "2026-05-19T00:17:00Z"}
  ],
  "changed_files": ["src/auth.py", "tests/test_auth.py"],
  "timestamp": "2026-05-19T00:17:00Z"
}
```

### Collision Warning

```json
{
  "type": "collision_warning",
  "severity": "high",
  "branch": "feature/auth",
  "agents": ["alice", "bob"],
  "detector": "detector-1"
}
```

### File Overlap Alert

```json
{
  "type": "file_overlap",
  "severity": "medium",
  "file": "src/auth.py",
  "agents": ["alice", "bob"],
  "detector": "detector-1"
}
```

### Detector Status

```json
{
  "type": "detector_status",
  "agent": "detector-1",
  "action": "monitoring"
}
```

## Workflows

### Workflow 1: Broadcast + Detect (Recommended)

```bash
# Terminal 1: Start broadcaster (announces your work)
python examples/collision_detector.py myproject alice broadcaster &

# Terminal 2: Start detector (monitors team's work)
python examples/collision_detector.py myproject detector-1 detector

# You'll see alerts like:
# [4] bob on branch: feature/payments
# [30] COLLISION: alice, bob, charlie on 'main'
# ⚠️  FILE OVERLAP: src/models.py by bob, charlie
```

### Workflow 2: Manual Status Checks

```python
from a2a_client import A2AClient
from a2a_git_aware import GitAwareClient
import json

project = "myproject"
a2a = A2AClient(project, "alice")
git = GitAwareClient("alice")

# Send your status
a2a.send("all", json.dumps(git.get_branch_status()))

# Check for recent collisions
messages = a2a.recv(wait=5)
for msg in messages:
    data = json.loads(msg["body"])
    if data.get("type") in ("collision_warning", "file_overlap"):
        collisions = git.detect_work_collision([data])
        print(collisions["warnings"])
```

### Workflow 3: Pre-Commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

python3 << 'EOF'
import json
from a2a_client import A2AClient
from a2a_git_aware import GitAwareClient

try:
    git = GitAwareClient("developer", ".")
    status = git.get_branch_status()
    
    a2a = A2AClient("myproject", "developer")
    a2a.send("all", json.dumps(status))
    
    # Wait briefly for collision alerts
    messages = a2a.recv(wait=2)
    for msg in messages:
        data = json.loads(msg["body"])
        if data.get("type") == "collision_warning":
            print(f"⚠️  WARNING: {data['agents']} also on {data['branch']}")
            print("💡 Consider: git pull, merge, or use feature branch")
except Exception:
    pass  # Don't block commits on error
EOF
```

## Configuration

### Environment Variables

```bash
# Git repository path
export A2A_GIT_REPO=/path/to/repo

# Check interval (seconds)
export A2A_COLLISION_CHECK_INTERVAL=30

# Alert threshold (number of agents)
export A2A_COLLISION_THRESHOLD=2
```

### Per-Project Settings

```python
# Customize collision detection
git = GitAwareClient("alice", repo_path=".")

# Monitor only certain files
important_files = ["src/core.py", "src/database.py"]
changed = set(git.get_changed_files()) & set(important_files)

# Or ignore certain files
ignore_patterns = ["*.test.py", "docs/*"]
```

## Limitations & Considerations

1. **Eventual Consistency**: Git state is announced periodically, not in real-time. Brief concurrent work may not be detected immediately.

2. **False Positives**: Agents on the same branch aren't necessarily conflicting (especially with feature branches).

3. **Git State Only**: Detection is based on local git state. Unpushed commits are visible; remote-only changes are not.

4. **Setup Required**: Agents must be connected to the same a2a bus and actively broadcasting status.

## Best Practices

1. **Use Feature Branches**: Reduces same-branch collisions
   ```bash
   git checkout -b feature/my-work
   ```

2. **Broadcast Status**: Run broadcaster on each agent
   ```bash
   python examples/collision_detector.py proj alice broadcaster
   ```

3. **Monitor Alerts**: Keep detector running in a dedicated agent
   ```bash
   python examples/collision_detector.py proj monitor detector
   ```

4. **Act on Alerts**: Coordinate with other agents when collisions are detected
   ```bash
   # Check what bob is working on
   a2a recv --json | grep bob
   ```

5. **Commit Frequently**: Small, focused commits make merges easier

6. **Pull Before Work**: Stay in sync with recent changes
   ```bash
   git pull origin main
   ```

## Troubleshooting

### "No collision alerts even though we're on same branch"

Ensure:
- Broadcaster agent is running: `a2a list | grep broadcaster`
- Same a2a project: `a2a project`
- Agents are communicating: `a2a recv --as detector-1`

### "False positive: we're on same branch but different features"

Use feature branches to isolate work:
```bash
git checkout -b feature/my-specific-task
```

### "Missing recent commits in status"

Git state is announced every 30 seconds. Allow time for propagation.

## See Also

- [README.md](../README.md) — Project overview
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) — Multi-interface coordination
- [CHANGELOG.md](../CHANGELOG.md) — Release history and roadmap
