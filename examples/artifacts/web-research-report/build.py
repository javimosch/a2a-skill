#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: web-research-report.

Three agents (researcher, analyst, writer) collaborate via the a2a bus to
produce a markdown research report on a specified topic using real web search
(DDG via ddgr).

Usage:
  python3 examples/artifacts/web-research-report/build.py [--project NAME] [--cli opencode] [--topic "..."]
  python3 examples/artifacts/web-research-report/build.py --cli opencode --model opencode-go/deepseek-v4-flash

Requires a2a, a2a-spawn, ddgr, and an AI CLI (claude, opencode, or pi).
"""
import os
import sys
import time
import json
import shlex
import argparse
import subprocess
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, send_task, check_agent_logs, SpawnManager  # noqa: E402

ARTIFACT = "web-research-report"
DEFAULT_TOPIC = "best open source LLM tools 2026"


def researcher_instructions(topic: str) -> str:
    return (
        f"You are the web researcher. Topic to research: \"{topic}\"\n\n"
        "You have shell access. Use ddgr for web search — it returns JSON.\n"
        "Example: ddgr --json --num 10 \"your search query\"\n\n"
        "Steps:\n"
        f"1. Search: ddgr --json --num 10 \"{topic}\"\n"
        "2. Also try: ddgr --json --num 5 --site github.com \"open source LLM tools\"\n"
        "3. Read the JSON output carefully — extract key tools, descriptions, and URLs\n"
        "4. Send your findings to the analyst:\n"
        '   a2a send analyst \'FINDINGS: <your structured findings with tool names, descriptions, URLs>\' --from researcher\n\n'
        "Important: Send the findings as structured text (not raw JSON). "
        "Include: for each tool/result — name, description, URL, key features."
    )


ANALYST_INSTRUCTIONS = (
    "You are the data analyst. Wait for the researcher to send you search findings.\n\n"
    "Steps:\n"
    "1. Receive the researcher's message:\n"
    "   a2a recv --as analyst --wait 60\n"
    "2. Extract key findings (tools, trends, patterns) from the data\n"
    "3. Group related items into categories (e.g., 'Local LLM runners', 'Agent frameworks', 'Code assistants')\n"
    "4. Create a structured analysis with:\n"
    "   - Category name\n"
    "   - For each tool: name, description, key features, pros/cons\n"
    "   - Notable trends or patterns\n"
    "5. Send your analysis to the writer:\n"
    '   a2a send writer \'ANALYSIS: <your structured analysis>\' --from analyst'
)


WRITER_INSTRUCTIONS = (
    "You are the report writer. Wait for the analyst to send you their analysis.\n\n"
    "Steps:\n"
    "1. Receive the analyst's message:\n"
    "   a2a recv --as writer --wait 60\n"
    "2. Compile a well-formatted markdown research report with:\n"
    "   - Title and date at the top\n"
    "   - Executive summary (2-4 sentences)\n"
    "   - Detailed findings organized by category (### headings)\n"
    "   - A comparison table of key tools\n"
    "   - Recommendations section\n"
    "3. Use proper markdown formatting: ##, ###, -, **bold**, | tables\n"
    "4. Include source URLs where available\n"
    "5. Broadcast the complete report:\n"
    '   a2a send all \'REPORT_START\\n<your full markdown report>\\nREPORT_END\' --from writer\n'
    "   The report must be between REPORT_START and REPORT_END markers."
)


FYI_TOPICS = {
    "best open source LLM tools 2026": [
        "Llama.cpp — C/C++ inference for LLaMA models, CPU optimized, GGUF format",
        "Ollama — Easiest local LLM runner, model library with one-click setup",
        "Hugging Face Transformers — Industry standard Python library for transformer models",
        "vLLM — High-throughput LLM serving with PagedAttention, OpenAI-compatible API",
        "LangChain — Framework for building LLM-powered applications with composable chains",
        "OpenAI Python SDK — Official Python client for OpenAI and compatible APIs",
    ],
    "best python web frameworks 2026": [
        "FastAPI — Modern, fast web framework with automatic OpenAPI docs (most popular)",
        "Django — Full-featured framework with ORM, admin, batteries-included",
        "Flask — Minimalist micro-framework with extensive extension ecosystem",
    ],
}

DEFAULT_LLM_FALLBACK = """# Web Research Report: Open Source LLM Tools

## Executive Summary

This report provides an overview of the most popular open source LLM tools available in 2026. These tools enable developers to run large language models locally, build LLM-powered applications, and serve models in production environments.

## Key Tools

### Local LLM Runners
| Tool | Description | Key Feature |
|------|-------------|-------------|
| **Llama.cpp** | C/C++ inference engine for LLaMA-family models | CPU-optimized, GGUF quantization, runs on laptops |
| **Ollama** | User-friendly local LLM runner with model library | One-click setup, Docker-like pull/run workflow |
| **vLLM** | High-throughput serving engine by UC Berkeley | PagedAttention, continuous batching, OpenAI API |

### LLM Development Frameworks
| Tool | Description | Key Feature |
|------|-------------|-------------|
| **LangChain** | Composable LLM application framework | Chains, agents, RAG, tool integration |
| **Hugging Face Transformers** | Industry-standard model library | 500K+ models, training + inference pipelines |
| **OpenAI SDK** | Python client for OpenAI-compatible APIs | Chat completions, embeddings, assistants API |

## Recommendations

1. **Local development**: Use Ollama for quick prototyping, Llama.cpp for production inference
2. **Serving**: vLLM for high-throughput API endpoints with PagedAttention
3. **Application building**: LangChain for complex workflows, Hugging Face for model experimentation

---

*This report was compiled from curated data. Agents were unable to participate due to API key limits.*"""


def generate_fallback_report(topic: str) -> str:
    """Produce a curated research report when agents fail."""
    print(f"[{ARTIFACT}] Generating curated fallback report for topic: \"{topic}\"")
    # Use topic-specific curated content if available
    if topic in FYI_TOPICS:
        items = FYI_TOPICS[topic]
        lines = [
            f"# Web Research Report: {topic}",
            "",
            "## Overview",
            f"Research summary on \"{topic}\" — compiled from curated knowledge sources.",
            "",
            "## Findings",
            "",
        ]
        for item in items:
            name = item.split(" — ")[0] if " — " in item else item
            desc = item.split(" — ", 1)[1] if " — " in item else ""
            lines.append(f"- **{name}**")
            if desc:
                lines.append(f"  {desc}")
            lines.append("")
        lines.extend([
            "---",
            "",
            "*This report was compiled from curated data. Agents were unable to participate due to API key limits.*",
        ])
        return "\n".join(lines)
    return DEFAULT_LLM_FALLBACK


def main():
    parser = argparse.ArgumentParser(description="Build a web research report via agent collaboration")
    parser.add_argument("--project", default=None)
    parser.add_argument("--cli", default="opencode", choices=["claude", "opencode", "pi"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--timeout", type=int, default=300, help="Total timeout in seconds")
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
    print(f"[{ARTIFACT}] Topic: \"{args.topic}\"")

    # Init bus
    run_a2a("init", a2a_bin, project)
    run_a2a("clear --yes", a2a_bin, project)
    run_a2a("register collector --role build-script --cli python", a2a_bin, project)

    agents = [
        {"id": "researcher", "role": "web researcher", "task": researcher_instructions(args.topic)},
        {"id": "analyst", "role": "data analyst", "task": ANALYST_INSTRUCTIONS},
        {"id": "writer", "role": "report writer", "task": WRITER_INSTRUCTIONS},
    ]
    for ag in agents:
        run_a2a(f'register {ag["id"]} --role "{ag["role"]}" --cli {args.cli}', a2a_bin, project)

    # Spawn agents
    for ag in agents:
        kit = make_kit(ag["id"], ag["role"], ag["task"], project)
        with tempfile.NamedTemporaryFile(mode="w", prefix=f"a2a-{project}-{ag['id']}-", suffix=".kit", delete=False) as f:
            f.write(kit)
            kit_path = f.name
        pid = spawn_agent(spawn_bin, args.cli, ag["id"], kit_path, project=project, model=args.model, a2a_bin=a2a_bin)
        if pid:
            mgr.add(pid)
        os.unlink(kit_path)

    time.sleep(3)
    # Send tasks via stdin to avoid shell quoting issues
    for ag in agents:
        send_task(a2a_bin, project, ag["id"], f"Your task: {ag['task']}")
        print(f"[{ARTIFACT}] → sent task to {ag['id']}")

    # Wait for the writer's report broadcast
    print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
    deadline = time.time() + args.timeout
    final_report = None

    while time.time() < deadline:
        msgs = run_a2a_json(f"recv --as collector --wait 30", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            sender = msg.get("sender", "")
            body = msg.get("body", "")
            if sender == "writer" and "REPORT_START" in body:
                # Extract content between markers
                start_idx = body.find("REPORT_START") + len("REPORT_START")
                end_idx = body.find("REPORT_END")
                if end_idx > start_idx:
                    final_report = body[start_idx:end_idx].strip()
                else:
                    final_report = body.replace("REPORT_START", "").replace("REPORT_END", "").strip()
                print(f"[{ARTIFACT}] ← Received report from writer ({len(final_report)} chars)")
                break
        if final_report:
            break

    # Check agent logs for API errors
    agent_ids = [ag["id"] for ag in agents]
    had_errors = check_agent_logs(agent_ids, ARTIFACT)
    if had_errors:
        print(f"[{ARTIFACT}] WARNING: Some agents had API errors")
    else:
        print(f"[{ARTIFACT}] Agent logs: clean")

    # Write output
    report_path = output_dir / "report.md"
    if final_report:
        report_path.write_text(final_report)
        print(f"[{ARTIFACT}] Wrote output/report.md (agent-produced, {len(final_report)} chars)")
    elif had_errors:
        print(f"[{ARTIFACT}] No agent-produced report. Generating fallback...")
        fallback = generate_fallback_report(args.topic)
        report_path.write_text(fallback)
        print(f"[{ARTIFACT}] Wrote output/report.md (fallback, {len(fallback)} chars)")
    else:
        print(f"[{ARTIFACT}] WARNING: No report received. Writing bus state to output/report.md...")
        peek = run_a2a("peek --limit 40", a2a_bin, project)
        report_path.write_text(f"# Web Research Report \u2014 FAILED\n\nNo report was produced within the timeout.\n\n## Bus State (last 40 messages)\n\n```\n{peek}\n```\n")

    # Capture bus state
    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
