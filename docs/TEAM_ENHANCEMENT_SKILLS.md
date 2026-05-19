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
# Export bus to graph
a2a peek --json --limit 500 | rtk build --format json -o team_graph.json

# Generate report
rtk report team_graph.json --output html --file team_collaboration.html

# Search for patterns
rtk search team_graph.json "WAL mode" --context 3
```

---

### 2. sc beads (SuperCLI Beads) ⚠️ NOT INSTALLED

> **Note:** `beads` is not installed on this machine. Commands below are aspirational — install beads before using.

**Location:** `sc beads` command (via supercli) — requires beads plugin installation

**Capabilities:**
- Persistent memory system for agents
- Store/retrieve structured data (JSON, text, code)
- Cross-session memory retention
- Full-text search across stored beads
- Tag-based organization

**Integration with a2a:**

```python
# Example: Persistent team memory
import beads

# Store important decisions
beads.add("decision", {
    "topic": "WAL mode enforcement",
    "decision": "All SQLite entrypoints must use WAL mode",
    "rationale": "Prevents delete journal mode bugs",
    "commit": "17f30d7"
})

# Retrieve for context
decisions = beads.search("WAL")
```

**Use Cases:**
- **Decision Memory:** Store team decisions beyond bus TTL
- **Pattern Library:** Save reusable code patterns and solutions
- **Sprint Handoff:** Preserve context between team rotations
- **Knowledge Base:** Build searchable team knowledge repository
- **Configuration Memory:** Store project-specific configurations

**Proof of Concept:**
```bash
# Store architectural decisions
sc beads add --tag architecture --type decision "WAL mode required for all SQLite entrypoints to prevent delete journal mode bugs"

# Store code patterns
sc beads add --tag pattern --type code "mkdir guard pattern for SQLite parent directories"

# Retrieve for new agents
sc beads search --tag architecture --format json
```

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

### Quick Start with rtk-graph
```bash
# Install rtk-graph skill
# Already at: ~/.agents/skills/rtk-context-memory-graph

# Export bus to graph
a2a peek --json --limit 100 > /tmp/bus.json
rtk build /tmp/bus.json --output graph.json

# Generate report
rtk report graph.json --output html --file team_report.html
```

### Quick Start with beads
```bash
# Install supercli (if not already)
# Already available via: sc command

# Store a decision
sc beads add --tag decision "WAL mode required for all SQLite entrypoints"

# Search decisions
sc beads search --tag decision
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
