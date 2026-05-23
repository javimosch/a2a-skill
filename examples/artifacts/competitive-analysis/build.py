#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: competitive-analysis.

Three agents (searcher, analyst, writer) collaborate via the a2a bus to produce
a markdown competitive analysis with a comparison table, market positioning,
and recommendations — using ddgr for live web research.

Usage:
  python3 examples/artifacts/competitive-analysis/build.py [--project NAME] [--cli opencode] [--topic "..."]

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

ARTIFACT = "competitive-analysis"
DEFAULT_TOPIC = "open source AI agent frameworks 2026"


def searcher_instructions(topic: str) -> str:
    return (
        f"You are the competitive searcher. Research the topic: \"{topic}\"\n\n"
        "You have shell access. Use ddgr for web search — it returns JSON.\n\n"
        "Steps:\n"
        f"1. Search for the topic: ddgr --json --num 10 \"{topic}\"\n"
        "2. Find at least 5-7 competitors/products in this space\n"
        "3. For each competitor, extract: name, description, URL, key features, pros/cons\n"
        "4. Send your findings to the analyst:\n"
        '   a2a send analyst COMPETITORS:<your structured findings> --from searcher\n\n'
        "Include the full details — the analyst needs this to build a comparison table."
    )

ANALYST_INSTRUCTIONS = (
    "You are the competitive analyst. Wait for the searcher to send you competitor findings.\n\n"
    "Steps:\n"
    "1. Receive the searcher's message:\n"
    "   a2a recv --as analyst --wait 60\n"
    "2. From the findings, extract key comparison dimensions:\n"
    "   - License (MIT, Apache, AGPL, proprietary)\n"
    "   - Primary language\n"
    "   - API style (CLI, SDK, REST, library)\n"
    "   - Key differentiators\n"
    "   - Pricing model\n"
    "3. Build a structured comparison with a feature table\n"
    "4. Identify market positioning (leader, challenger, niche, emerging)\n"
    "5. Send your structured analysis to the writer:\n"
    '   a2a send writer ANALYSIS:<your analysis with comparison data> --from analyst'
)

WRITER_INSTRUCTIONS = (
    "You are the report writer. Wait for the analyst to send you their analysis.\n\n"
    "Steps:\n"
    "1. Receive the analyst's message:\n"
    "   a2a recv --as writer --wait 60\n"
    "2. Compile a well-formatted markdown competitive analysis report:\n"
    "   - Title and date\n"
    "   - Executive summary (2-3 sentences)\n"
    "   - Competitive landscape overview\n"
    "   - Comparison table (with columns: tool, category, language, license, key differentiator)\n"
    "   - Market positioning analysis\n"
    "   - Recommendations section\n"
    "3. Use proper markdown: ##, ###, | tables, -, **bold**\n"
    "4. Broadcast the complete report:\n"
    '   a2a send all COMPARE_START\\n<your report>\\nCOMPARE_END --from writer'
)


COMPETITIVE_FRAMEWORKS = {
    "open source AI agent frameworks 2026": [
        ("LangChain", "Python/JS", "MIT", "Agent composability, tool integration, 80K+ GitHub stars"),
        ("AutoGen", "Python", "MIT", "Multi-agent conversation framework, Microsoft Research"),
        ("CrewAI", "Python", "MIT", "Role-based agent teams, hierarchical orchestration"),
        ("Semantic Kernel", "C#/Python", "MIT", "Enterprise AI orchestration, Microsoft, Azure integration"),
        ("Dify", "Python", "Apache 2.0", "Visual agent builder, RAG pipeline, workflow automation"),
        ("TaskWeaver", "Python", "MIT", "Code-first agent framework, Microsoft, type-safe execution"),
    ],
}

DEFAULT_COMPETITIVE = """# Competitive Analysis: Open Source AI Agent Frameworks

## Executive Summary

The open source AI agent framework landscape in 2026 is dominated by established players (LangChain, AutoGen) and emerging platforms (Dify, CrewAI). Key differentiators include language support, enterprise integration, and multi-agent orchestration capabilities.

## Competitive Landscape

| Framework | Language | License | Key Differentiator |
|-----------|----------|---------|-------------------|
| **LangChain** | Python/JS | MIT | Largest ecosystem, extensive tool/API integrations |
| **AutoGen** | Python | MIT | Multi-agent conversation with structured handoffs |
| **CrewAI** | Python | MIT | Role-based agent teams with hierarchical planning |
| **Semantic Kernel** | C#/Python | MIT | Deep Azure/Azure AI Studio integration |
| **Dify** | Python | Apache 2.0 | Visual workflow builder + built-in RAG pipeline |
| **TaskWeaver** | Python | MIT | Code-first with type-safe plugin execution |

## Market Positioning

- **Leader**: LangChain — largest community, most integrations, broadest adoption
- **Challenger**: AutoGen — Microsoft-backed, strong multi-agent capabilities
- **Niche Innovators**: Dify (visual builder), TaskWeaver (code-first)
- **Emerging**: CrewAI (role-based teams), Semantic Kernel (enterprise)

## Recommendations

1. Choose **LangChain** for maximum flexibility and community support
2. Choose **AutoGen** for structured multi-agent workflows
3. Choose **Dify** for visual agent development without deep coding
4. Choose **Semantic Kernel** when deeply integrated with Microsoft/Azure stack

---

*This analysis was compiled from curated knowledge. Agents were unable to participate due to API key limits.*"""


def generate_fallback_analysis(topic: str) -> str:
    """Produce a curated competitive analysis report when agents fail."""
    print(f"[{ARTIFACT}] Generating curated fallback analysis for topic: \"{topic}\"")
    if topic in COMPETITIVE_FRAMEWORKS:
        items = COMPETITIVE_FRAMEWORKS[topic]
        lines = [
            f"# Competitive Analysis: {topic}",
            "",
            "## Competitive Landscape",
            "",
            "| Tool | Language | License | Key Differentiator |",
            "|------|----------|---------|-------------------|",
        ]
        for name, lang, lic, diff in items:
            lines.append(f"| **{name}** | {lang} | {lic} | {diff} |")
        lines.extend([
            "",
            "---",
            "",
            "*This analysis was compiled from curated knowledge. Agents were unable to participate due to API key limits.*",
        ])
        return "\n".join(lines)
    return DEFAULT_COMPETITIVE


def main():
    parser = argparse.ArgumentParser(description="Build a competitive analysis report via agent collaboration")
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

    run_a2a("init", a2a_bin, project)
    run_a2a("clear --yes", a2a_bin, project)
    run_a2a("register collector --role build-script --cli python", a2a_bin, project)

    agents = [
        {"id": "searcher", "role": "competitive searcher", "task": searcher_instructions(args.topic)},
        {"id": "analyst", "role": "competitive analyst", "task": ANALYST_INSTRUCTIONS},
        {"id": "writer", "role": "report writer", "task": WRITER_INSTRUCTIONS},
    ]
    for ag in agents:
        run_a2a(f'register {ag["id"]} --role "{ag["role"]}" --cli {args.cli}', a2a_bin, project)

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

    print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
    deadline = time.time() + args.timeout
    final_report = None

    while time.time() < deadline:
        msgs = run_a2a_json(f"recv --as collector --wait 30", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            sender = msg.get("sender", "")
            body = msg.get("body", "")
            if sender == "writer":
                if "COMPARE_START" in body and "COMPARE_END" in body:
                    start_idx = body.find("COMPARE_START") + len("COMPARE_START")
                    end_idx = body.find("COMPARE_END")
                    if end_idx > start_idx:
                        final_report = body[start_idx:end_idx].strip()
                    else:
                        final_report = body.replace("COMPARE_START", "").replace("COMPARE_END", "").strip()
                    print(f"[{ARTIFACT}] ← Received analysis from writer ({len(final_report)} chars)")
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

    report_path = output_dir / "competitive-analysis.md"
    if final_report:
        report_path.write_text(final_report)
        print(f"[{ARTIFACT}] Wrote output/competitive-analysis.md (agent-produced, {len(final_report)} chars)")
    elif had_errors:
        print(f"[{ARTIFACT}] No agent-produced report. Generating fallback...")
        fallback = generate_fallback_analysis(args.topic)
        report_path.write_text(fallback)
        print(f"[{ARTIFACT}] Wrote output/competitive-analysis.md (fallback, {len(fallback)} chars)")
    else:
        print(f"[{ARTIFACT}] WARNING: No report received. Writing bus state...")
        peek = run_a2a("peek --limit 40", a2a_bin, project)
        report_path.write_text(f"# Competitive Analysis \u2014 FAILED\n\nNo report was produced.\n\n## Bus State\n\n```\n{peek}\n```\n")

    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
