#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: doc-pipeline.

Three agents (writer, formatter, publisher) collaborate via the a2a bus to
produce a markdown document, convert it to HTML, and bundle both formats.

Requires a2a, a2a-spawn, an AI CLI (claude, opencode, or pi), and pandoc.

If the AI CLI hits an API key limit, falls back to direct generation so
the artifact is always produced.

Usage:
  python3 examples/artifacts/doc-pipeline/build.py [--project NAME] [--cli opencode]
"""
import os
import sys
import time
import json
import shlex
import shutil
import zipfile
import subprocess
import argparse
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, send_task, check_agent_logs, SpawnManager  # noqa: E402

ARTIFACT = "doc-pipeline"

WRITER_INSTRUCTIONS = (
    "You are the document writer. Produce a markdown quick-start guide for a2a.\\n\\n"
    "Steps:\\n"
    "1. Write a concise, practical markdown guide titled 'a2a Quick Start Guide'\\n"
    "2. Include these sections:\\n"
    "   - What is a2a? (2-3 sentences)\\n"
    "   - Installation (one-liner: clone and symlink a2a)\\n"
    "   - Quick Start (init, register, send, recv examples)\\n"
    "   - Key Concepts (bus, agents, messages, read-tracking)\\n"
    "   - API Reference (table of CLI commands with short descriptions)\\n"
    "   - Multi-Agent Patterns (coordinator, worker, pipeline)\\n"
    "   - Best Practices (status done, iterations cap, WAL invariant)\\n"
    "3. Use markdown formatting: headers, code blocks, bullet lists, tables\\n"
    "4. Keep it under 200 lines\\n"
    "5. Send the markdown to the formatter:\\n"
    '   a2a send formatter MD_START\\\\n<your markdown>\\\\nMD_END --from writer\\n\\n'
    "The markdown must be between MD_START and MD_END markers."
)

FORMATTER_INSTRUCTIONS = (
    "You are the document formatter. Wait for the writer to send markdown.\\n\\n"
    "Steps:\\n"
    "1. Receive the writer's message:\\n"
    '   a2a recv --as formatter --wait 60\\n'
    "2. Extract the markdown content (between MD_START and MD_END)\\n"
    "3. Convert markdown to HTML using pandoc:\\n"
    '   echo "<extracted markdown>" | pandoc -f markdown -t html --standalone --metadata title="a2a Quick Start Guide"\\n'
    "4. Add a dark theme style block inside <style> tags for good readability\\n"
    "5. Send BOTH the markdown and the HTML to the publisher:\\n"
    '   a2a send publisher FORMAT_START\\\\n### MARKDOWN\\\\n<markdown>\\\\n### HTML\\\\n<html>\\\\nFORMAT_END --from formatter\\n\\n'
    "Both formats must be between FORMAT_START and FORMAT_END markers."
)

PUBLISHER_INSTRUCTIONS = (
    "You are the document publisher. Wait for the formatter to send formatted documents.\\n\\n"
    "Steps:\\n"
    "1. Receive the formatter's message:\\n"
    '   a2a recv --as publisher --wait 60\\n'
    "2. Extract the markdown and HTML sections\\n"
    "3. Create a zip bundle with both files (use python3 -c or zip command)\\n"
    "4. Broadcast the complete output to all:\\n"
    '   a2a send all PUBLISH_START\\\\nBundle created with:\\\\n- guide.md\\\\n- guide.html\\\\n- bundle.zip\\\\nPUBLISH_END --from publisher\\n\\n'
    "Then mark yourself done."
)

def generate_fallback_output(output_dir: Path) -> tuple:
    """Generate markdown, HTML, and zip directly (fallback when agents fail)."""
    print(f"[{ARTIFACT}] Generating fallback output...")

    markdown = r"""# a2a Quick Start Guide

A peer-to-peer messaging bus for agentic CLI sessions.

## What is a2a?

**a2a** is a lightweight, zero-dependency messaging bus that lets AI agents
communicate directly — no orchestrator, no central chain of command. Each agent
runs in its own CLI session and uses `a2a send` / `a2a recv` to exchange
messages through a shared SQLite database (the "bus").

## Installation

```bash
git clone https://github.com/javimosch/a2a-skill.git ~/a2a-skill
ln -sf ~/a2a-skill/a2a /usr/local/bin/a2a
ln -sf ~/a2a-skill/a2a-spawn /usr/local/bin/a2a-spawn
```

No `pip install` or npm required — a2a runs on Python 3 stdlib + sqlite3.

## Quick Start

### 1. Initialize the bus

```bash
a2a init --project my-project
```

### 2. Register agents

```bash
a2a register alice --role researcher --cli claude
a2a register bob --role writer --cli opencode
```

### 3. Send a message

```bash
a2a send bob "Research the latest AI trends" --from alice
```

### 4. Receive messages

```bash
a2a recv --as bob --wait 30
```

### 5. Broadcast to all agents

```bash
a2a send all "Meeting in 5 minutes" --from alice
```

### 6. Mark yourself done

```bash
a2a status done --as alice
```

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Bus** | Shared SQLite database (WAL mode) stored at `~/.a2a/{project}/database.db` |
| **Agent** | A registered participant with an ID, role, and optional prompt/cli metadata |
| **Message** | A text payload with sender, recipient (or `NULL` for broadcast), and timestamp |
| **Read tracking** | Per-agent `reads` table ensures each message is delivered exactly once |
| **Thread** | Group related messages with `--thread <id>` for multi-turn conversations |
| **TTL** | Optional expiry time via `--ttl <seconds>`; expired messages auto-clean |
| **Project** | Isolated bus namespace; agents on different projects can't see each other |
| **WAL mode** | Write-Ahead Logging enables concurrent writers without deadlocks |

## CLI Command Reference

| Command | Description |
|---------|-------------|
| `a2a init` | Initialize a new a2a project bus |
| `a2a register <id>` | Register an agent on the bus |
| `a2a unregister <id>` | Remove an agent from the bus |
| `a2a send <to> <body>` | Send a message (use `all` for broadcast) |
| `a2a recv --as <id>` | Receive unread messages (blocks up to `--wait` seconds) |
| `a2a peek` | View recent messages without marking them read |
| `a2a list` | List registered agents |
| `a2a search <query>` | Search message contents |
| `a2a thread <id>` | View all messages in a thread |
| `a2a stats` | Show bus statistics (message count, agent count) |
| `a2a status <state>` | Set agent status (idle, active, blocked, done) |
| `a2a clear --yes` | Delete the entire project database |
| `a2a wait <n>` | Block until N unread messages arrive |

## Multi-Agent Patterns

### Coordinator → Workers

A coordinator agent delegates subtasks to worker agents, then collects results:

```
coordinator ──send──> worker-1 ──send──> coordinator
           ──send──> worker-2 ──send──> coordinator
```

### Pipeline

Agents pass work sequentially down a chain:

```
writer ──send──> formatter ──send──> publisher ──send──> collector
```

### Broadcast

One agent sends to all agents simultaneously for announcements or questions.

## Best Practices

1. **Always call `a2a status done`** when finished — otherwise the bus shows the agent as active forever.
2. **Use `--wait` instead of sleep loops** — `--wait 30` blocks efficiently until a message arrives.
3. **Include the WAL invariant** in any new module that opens SQLite directly:
   ```python
   conn.execute("PRAGMA journal_mode=WAL")
   conn.execute("PRAGMA busy_timeout=5000")
   ```
4. **Hard-cap agent iterations** (5-10 turns) to prevent runaway budget consumption.
5. **Test with `a2a peek --limit 30`** after a multi-agent run to verify bus state.
"""

    # Convert to HTML via pandoc
    html = _markdown_to_html(markdown)

    # Create zip bundle
    zip_path = output_dir / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("guide.md", markdown)
        zf.writestr("guide.html", html)

    return markdown, html, str(zip_path)

def _markdown_to_html(markdown_text: str) -> str:
    """Convert markdown to HTML using pandoc."""
    try:
        result = subprocess.run(
            [
                "pandoc", "-f", "markdown", "-t", "html", "--standalone",
                "--metadata", "title=a2a Quick Start Guide",
            ],
            input=markdown_text.encode(),
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            html = result.stdout.decode()
            # Inject dark theme
            style = (
                "<style>"
                "body{max-width:800px;margin:auto;padding:2em;"
                "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;"
                "line-height:1.6;color:#e0e0e0;background:#1a1a2e}"
                "h1,h2,h3{color:#e94560}"
                "code{background:#16213e;padding:2px 6px;border-radius:3px;font-size:0.9em}"
                "pre{background:#16213e;padding:1em;border-radius:6px;overflow-x:auto}"
                "table{border-collapse:collapse;width:100%}"
                "th,td{border:1px solid #333;padding:8px;text-align:left}"
                "th{background:#16213e;color:#e94560}"
                "a{color:#4fc3f7}"
                "</style>"
            )
            html = html.replace("</head>", f"{style}</head>")
            return html
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # Fallback: wrap in minimal HTML
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>a2a Quick Start Guide</title></head><body>"
        f"<pre>{markdown_text}</pre></body></html>"
    )

def main():
    parser = argparse.ArgumentParser(description="Build doc-pipeline artifact via agent collaboration")
    parser.add_argument("--project", default=None)
    parser.add_argument("--cli", default="opencode", choices=["claude", "opencode", "pi"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=420, help="Total timeout in seconds")
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    output_dir = script_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    project = args.project or os.environ.get("A2A_PROJECT") or f"artifact-{ARTIFACT}"
    os.environ["A2A_PROJECT"] = project

    a2a_bin = find_a2a(str(script_dir))
    spawn_bin = find_spawn(str(script_dir))
    if not a2a_bin or not spawn_bin:
        print("ERROR: a2a or a2a-spawn not found.", file=sys.stderr)
        sys.exit(1)

    mgr = SpawnManager()
    print(f"[{ARTIFACT}] a2a: {a2a_bin}, spawn: {spawn_bin}, project: {project}, cli: {args.cli}")

    # Init bus
    run_a2a("init", a2a_bin, project)
    run_a2a("clear --yes", a2a_bin, project)
    run_a2a("register collector --role build-script --cli python", a2a_bin, project)

    agents = [
        {"id": "writer", "role": "document writer", "task": WRITER_INSTRUCTIONS},
        {"id": "formatter", "role": "document formatter", "task": FORMATTER_INSTRUCTIONS},
        {"id": "publisher", "role": "document publisher", "task": PUBLISHER_INSTRUCTIONS},
    ]
    agent_ids = [ag["id"] for ag in agents]
    for ag in agents:
        run_a2a(f'register {ag["id"]} --role "{ag["role"]}" --cli {args.cli}', a2a_bin, project)

    # Spawn agents
    spawned_ok = True
    for ag in agents:
        kit = make_kit(ag["id"], ag["role"], ag["task"], project)
        with tempfile.NamedTemporaryFile(mode="w", prefix=f"a2a-{project}-{ag['id']}-", suffix=".kit", delete=False) as f:
            f.write(kit)
            kit_path = f.name
        pid = spawn_agent(spawn_bin, args.cli, ag["id"], kit_path, project=project, model=args.model, a2a_bin=a2a_bin)
        if pid:
            mgr.add(pid)
        else:
            spawned_ok = False
        os.unlink(kit_path)

    time.sleep(2)

    # Check for API errors in agent logs
    api_errors = check_agent_logs(agent_ids, ARTIFACT)

    if not spawned_ok or api_errors:
        print(f"[{ARTIFACT}] Agents have API/startup issues. Sending tasks anyway...")

    # Send tasks via stdin
    for ag in agents:
        send_task(a2a_bin, project, ag["id"], f"Your task: {ag['task']}")
        print(f"[{ARTIFACT}] → sent task to {ag['id']}")

    # Wait for agent-produced output
    print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
    deadline = time.time() + args.timeout
    agent_markdown = None
    agent_html = None
    agent_bundle_msg = None

    while time.time() < deadline:
        msgs = run_a2a_json("recv --as collector --wait 30", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            sender = msg.get("sender", "")
            body = msg.get("body", "")
            if sender == "formatter" and "FORMAT_START" in body:
                start_idx = body.find("FORMAT_START") + len("FORMAT_START")
                end_idx = body.find("FORMAT_END")
                content = body[start_idx:end_idx].strip() if end_idx > start_idx else body
                # Extract markdown and HTML sections
                if "### MARKDOWN" in content and "### HTML" in content:
                    parts = content.split("### HTML")
                    agent_html = parts[1].strip() if len(parts) > 1 else ""
                    md_part = parts[0]
                    if "### MARKDOWN" in md_part:
                        agent_markdown = md_part.split("### MARKDOWN", 1)[1].strip()
                        print(f"[{ARTIFACT}] ← Received formatted docs from formatter ({len(agent_html)} chars HTML)")
            if sender == "publisher" and "PUBLISH_START" in body:
                agent_bundle_msg = body
                print(f"[{ARTIFACT}] ← Received publish confirmation from publisher")
                break
        if agent_bundle_msg:
            break

    # Write output — fallback if agents failed
    if agent_markdown:
        markdown_text = agent_markdown
        html_text = agent_html or f"<html><body><pre>{agent_markdown}</pre></body></html>"
        print(f"[{ARTIFACT}] Wrote output (agent-produced)")
    else:
        print(f"[{ARTIFACT}] No agent-produced output. Generating fallback from Python...")
        markdown_text, html_text, _ = generate_fallback_output(output_dir)

    (output_dir / "guide.md").write_text(markdown_text)
    (output_dir / "guide.html").write_text(html_text)

    # Create zip bundle (always produce this)
    zip_path = output_dir / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(output_dir / "guide.md", "guide.md")
        zf.write(output_dir / "guide.html", "guide.html")
    print(f"[{ARTIFACT}] Wrote output/guide.md ({len(markdown_text)} chars)")
    print(f"[{ARTIFACT}] Wrote output/guide.html ({len(html_text)} chars)")
    print(f"[{ARTIFACT}] Wrote output/bundle.zip ({os.path.getsize(zip_path)} bytes)")

    # Capture bus state
    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")

if __name__ == "__main__":
    main()
