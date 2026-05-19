# Team Enhancement Skills for a2a

This document explores integration opportunities between a2a and external skills/libraries that can enhance multi-agent collaboration.

> **Availability audit (pm-2, 2026-05-19):** rtk-context-memory-graph ✅ confirmed at `~/.agents/skills/rtk-context-memory-graph`. `sc` (supercli) ✅ available. `beads` ❌ not installed on this machine — section 2 below is aspirational only.

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

## Integration Architecture

### Proposed Integration Points

```python
class EnhancedA2AClient(A2AClient):
    def __init__(self, project):
        super().__init__(project)
        self.graph = rtk_graph.Graph()
        self.memory = beads.Client()
        self.plugins = sc.PluginManager()
    
    def send_with_memory(self, recipient, message):
        # Store in persistent memory
        self.memory.add("message", {
            "sender": self.agent_id,
            "recipient": recipient,
            "body": message,
            "timestamp": time.time()
        })
        
        # Add to knowledge graph
        self.graph.add_node(message, type="communication")
        
        # Send via a2a
        return super().send(recipient, message)
    
    def recv_with_context(self, wait=30):
        messages = super().recv(wait=wait)
        
        # Enrich with graph context
        for msg in messages:
            related = self.graph.query(msg.body)
            msg["context"] = related
        
        return messages
```

### Bus Enhancement Wrapper

```bash
# a2a-enhanced wrapper script
#!/bin/bash

export A2A_PROJECT=${1:-default}
export BEADS_DB=~/.a2a/$A2A_PROJECT/beads.db
export GRAPH_DB=~/.a2a/$A2A_PROJECT/graph.db

# Enhanced commands
case "$1" in
    send)
        # Store in beads
        sc beads add --tag message --type communication "$2"
        # Send via a2a
        a2a send "$2" --from "$3"
        # Update graph
        rtk add --node "$2" --type communication
        ;;
    recv)
        # Get from a2a
        messages=$(a2a recv --as "$2" --json)
        # Enrich with graph context
        enriched=$(rtk context --graph "$GRAPH_DB" --input "$messages")
        echo "$enriched"
        ;;
esac
```

---

## Implementation Roadmap

### Phase 1: Proof of Concept (1-2 sprints)
- [ ] Basic rtk-graph integration with bus export
- [ ] Beads memory for decision storage
- [ ] Plugin delegation for simple tasks
- [ ] Documentation and examples

### Phase 2: Deep Integration (2-3 sprints)
- [ ] Enhanced a2a client with memory/graph
- [ ] Bus enrichment wrapper
- [ ] Skill-specific agent patterns
- [ ] Testing and validation

### Phase 3: Production Ready (1-2 sprints)
- [ ] Performance optimization
- [ ] Error handling and recovery
- [ ] Security and access control
- [ ] Documentation and training

---

## Benefits for a2a Teams

### Immediate Benefits
- **Persistent Memory:** Team decisions survive bus TTL
- **Knowledge Visualization:** See team expertise and collaboration patterns
- **Extended Capabilities:** Access specialized tools without coding
- **Better Handoffs:** Preserve context between agent rotations

### Long-term Benefits
- **Organizational Learning:** Build team knowledge over time
- **Process Improvement:** Identify and optimize collaboration patterns
- **Scalability:** Handle more complex goals through plugin ecosystem
- **Cross-Project Knowledge:** Share learnings across different a2a projects

---

## Example Use Cases

### Sprint Planning with Memory
```python
# Coordinator reviews past decisions
decisions = beads.search("sprint planning --tag decision")
context = rtk.build_graph(decisions)

# Proposes new sprint based on patterns
proposal = sc.goal("plan v1.4 sprint", context=context)
a2a.send all proposal
```

### Code Review with Graph
```python
# Architect reviews code changes
changes = git.diff()
graph = rtk.build_graph(changes)

# Identifies affected components
components = graph.query("database entrypoints")
violations = check_wal_mode(components)

a2a.send coordinator f"WAL violations found: {violations}"
```

### Testing with Plugins
```python
# QA agent delegates test execution
test_plan = sc.decompose("test v1.3 features")
for test in test_plan:
    result = sc.execute(test, plugin="pytest")
    beads.add("test_result", result)
    a2a.send all f"Test {test}: {result['status']}"
```

---

## Getting Started

### Quick Start with graphify (via sc plugin)
```bash
# graphify is installed: sc plugins list | grep graphify
# The ~/.agents/skills/rtk-context-memory-graph skill documents the strategy

# Export bus to graph
a2a peek --json --limit 100 > /tmp/bus.json
sc graphify.graph.build /tmp/bus.json --output graph.json

# Generate HTML report
sc graphify.report.html graph.json --file team_report.html
```

> **Note:** `rtk` (at /usr/local/bin/rtk) is a token-reduction CLI proxy — not a
> graph builder. The graphify plugin handles knowledge graph construction.

### Quick Start with beads (br issue tracker)
```bash
# sc beads wraps br (beads_rust) — issue tracking, not memory storage
# sc command is available: sc beads --help

# Create a workspace
sc beads workspace create my-sprint

# File a bug found during the sprint
sc beads issue create "FTS5 rebuild on every search" --type bug

# View sprint stats
sc beads stats
```

### Quick Start with plugins
```bash
# List available plugins
sc plugins list

# Execute a task
sc run test --plugin pytest

# Decompose a goal
sc goal "implement feature" --decompose
```

---

## Contributing

To add new integration examples or improve existing ones:

1. Add example code to `examples/team-enhancement/`
2. Update this document with new use cases
3. Test integration with current a2a bus
4. Document lessons learned and best practices

---

## Related Documentation

- [AGENTS.md](../AGENTS.md) — Agent development guide
- [CLIENT_API.md](CLIENT_API.md) — Python client reference
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) — Multi-interface coordination
- [ADVANCED_PATTERNS.md](ADVANCED_PATTERNS.md) — Performance and optimization

---

**Status:** Proof of Concept — availability audited by pm-2 (2026-05-19 20:42 Paris)
**Last Updated:** 2026-05-19 20:42 Paris time
**Authors:** devin (skill-integrator, initial draft), pm-2 (availability audit)
