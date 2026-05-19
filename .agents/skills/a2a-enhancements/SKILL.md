---
name: a2a-enhancements
description: Integration opportunities between a2a and external tools available in this codebase's dev environment (rtk-context-memory-graph, sc). Scoped to this codebase's dev environment.
---

# Team Enhancement Skills for a2a

This document explores integration opportunities between a2a and external skills/libraries that can enhance multi-agent collaboration.

> **Note:** The integrations below depend on optional tools (`sc`, `rtk`, `beads`) that vary by environment.
> Check availability with: `command -v sc`, `sc plugins list | grep graphify`, `command -v rtk`.

## Available Enhancements

### 1. rtk-context-memory-graph

**Location:** `~/.agents/skills/rtk-context-memory-graph`

**Capabilities:**
- Builds knowledge graphs from any input (code, docs, papers, images)
- Creates clustered communities and HTML/JSON audit reports
- Full-text search with relevance ranking
- Visualizes relationships between concepts

**Integration with a2a:**

```python
# Example: Graph team conversation history
import rtk_graph

# Export a2a bus messages to graph
messages = a2a.peek --json --limit 1000
graph = rtk_graph.build_graph(messages)

# Generate HTML report
graph.export_html("team_knowledge.html")

# Query for expertise clusters
python_clusters = graph.query("Python implementation")
security_clusters = graph.query("encryption and security")
```

**Use Cases:**
- **Team Knowledge Mapping:** Visualize expertise areas across agents
- **Conversation Analysis:** Identify knowledge gaps and collaboration patterns
- **Documentation Generation:** Auto-generate docs from team discussions
- **Cross-Session Learning:** Preserve knowledge between sprints
- **Audit Trails:** HTML reports of decision-making processes

**Proof of Concept:**
```bash
# Export bus messages to a file
a2a peek --json --limit 500 > /tmp/bus.json

# Build knowledge graph via sc graphify plugin (installed)
sc graphify.graph.build /tmp/bus.json --output team_graph.json

# Generate HTML report
sc graphify.report.html team_graph.json --file team_collaboration.html

# Search graph for patterns
sc graphify.graph.search team_graph.json "WAL mode"
```

> **Note:** `rtk` is a CLI proxy for token-optimized output (git, ls, tree, etc.) —
> it does NOT support graph subcommands (`build/report/search`). Use `sc graphify`
> (installed — `sc plugins list | grep graphify`) for knowledge graph work.

---

### 2. sc beads (SuperCLI Beads)

**Location:** `sc beads` command (via supercli) — wraps `br` (beads_rust) for lightweight
issue tracking. Available on this machine: `sc beads --help`.

**What it actually is:** `br`/beads_rust is an issue tracker, not a free-form memory store.
Resources: `install`, `workspace`, `issue`, `dep`, `sync`, `stats`.

**Capabilities:**
- Workspace and project management (`sc beads workspace`)
- Issue creation and tracking (`sc beads issue`)
- Dependency tracking (`sc beads dep`)
- Sync and stats reporting (`sc beads sync`, `sc beads stats`)

**Integration with a2a (issue tracking angle):**

```bash
# Create a workspace for the a2a sprint
sc beads workspace create a2a-sprint

# File an issue when an agent finds a bug
sc beads issue create "FTS5 rebuild runs on every search call" --type bug

# Track sprint tasks as issues
sc beads issue create "Add WAL invariant tests" --type task

# Check sprint stats
sc beads stats
```

**Use Cases:**
- **Bug Tracking:** Agents file issues when they find defects on the bus
- **Task Management:** Coordinator creates issues; agents update status
- **Sprint Reporting:** `sc beads stats` for end-of-sprint metrics
- **Dependency Mapping:** Track which tasks block others

> **Note:** sc beads is NOT a general-purpose key-value memory store. For
> persistent agent memory, see the graphify skill or the `mem` skill.

---

### 3. supercli/sc Plugins

**Location:** `supercli/sc` directory and plugin ecosystem

**Capabilities:**
- Vast plugin ecosystem for development tasks
- Goal decomposition and execution
- Specialized tools (testing, deployment, analysis)
- Cross-tool integration
- Workflow automation

**Integration with a2a:**

```python
# Example: Delegate tasks to plugins
def handle_complex_task(task):
    # Decompose using supercli
    subtasks = sc.decompose(task)
    
    # Execute via plugins
    for subtask in subtasks:
        result = sc.execute(subtask, plugin="auto")
        a2a.send all f"Subtask complete: {subtask}"
```

**Use Cases:**
- **Task Delegation:** Agents delegate specialized work to plugins
- **Capability Extension:** Add new abilities without code changes
- **Goal Achievement:** Break down complex goals into executable steps
- **Tool Integration:** Connect a2a with external development tools
- **Workflow Automation:** Automate repetitive development tasks

**Proof of Concept:**
```bash
# Agent delegates testing to plugin
sc run test --plugin pytest --directory ./tests

# Agent delegates deployment
sc run deploy --plugin docker --target production

# Goal decomposition
sc goal "implement encryption feature" --decompose --execute
```

---

## Related Documentation

- [AGENTS.md](../../AGENTS.md) — Agent development guide
- [CLIENT_API.md](../../docs/CLIENT_API.md) — Python client reference
- [INTEGRATION_GUIDE.md](../../docs/INTEGRATION_GUIDE.md) — Multi-interface coordination
- [ADVANCED_PATTERNS.md](../../docs/ADVANCED_PATTERNS.md) — Performance and optimization

---

**Status:** Proof of Concept — verify tool availability in your environment before use
**Last Updated:** 2026-05-19
