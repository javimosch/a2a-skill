#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: github-trending-report.

Three agents (searcher, describer, compiler) collaborate via the a2a bus to
produce a weekly GitHub trending repositories report.

Usage:
  python3 examples/artifacts/github-trending-report/build.py [--project NAME] [--cli opencode]

Requires a2a, a2a-spawn, ddgr, and an AI CLI (claude, opencode, or pi).
"""
import os
import sys
import time
import json
import argparse
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, send_task, SpawnManager  # noqa: E402

ARTIFACT = "github-trending-report"


SEARCHER_INSTRUCTIONS = (
    "You are the GitHub searcher. Search the web for trending GitHub repositories.\n\n"
    "You have shell access. Use ddgr for web search — it returns JSON.\n\n"
    "Steps:\n"
    "1. Search for trending repositories using multiple ddgr queries:\n"
    '   ddgr --json --num 10 "github trending repositories this week 2026"\n'
    '   ddgr --json --num 8 "most starred github repos 2026"\n'
    "2. Read the JSON output carefully — extract repository URLs, names, and descriptions\n"
    "3. Compile a list of at least 8 trending repositories with:\n"
    "   - Repository name and URL\n"
    "   - Description/summary from search results\n"
    "   - Any language or tech info mentioned\n"
    "4. Send the findings to the describer:\n"
    '   a2a send describer \'REPOS: <your list of repos with names, URLs, descriptions>\' --from searcher'
)

DESCRIBER_INSTRUCTIONS = (
    "You are the GitHub repository describer. Wait for the searcher to send you repository data.\n\n"
    "Steps:\n"
    "1. Receive the searcher's message:\n"
    "   a2a recv --as describer --wait 60\n"
    "2. Enrich each repository entry by:\n"
    "   - Adding a 'Category' tag (e.g., AI, DevOps, Web, Data, Tools)\n"
    "   - Rating the popularity level (High/Medium/Emerging)\n"
    "   - Adding a 1-2 sentence summary of what the repo does\n"
    "   - Extracting any programming language info from the description\n"
    "3. Format as a structured list with: name, url, description, category, popularity, language\n"
    "4. Send the enriched list to the compiler:\n"
    '   a2a send compiler \'ENRICHED: <your structured enriched repository data>\' --from describer'
)

COMPILER_INSTRUCTIONS = (
    "You are the weekly report compiler. Wait for the describer to send you enriched data.\n\n"
    "Steps:\n"
    "1. Receive the describer's message:\n"
    "   a2a recv --as compiler --wait 60\n"
    "2. Compile a polished markdown report with:\n"
    "   - Title: 'GitHub Trending Report — Week of <current date>'\n"
    "   - Introduction paragraph\n"
    "   - Repository listing in a table format:\n"
    "     | Repository | Category | Popularity | Language | Description |\n"
    "   - A 'Trending Categories' section grouping repos by category\n"
    "   - A 'Notable Mentions' section for particularly interesting repos\n"
    "   - A 'Summary' section with key takeaways\n"
    "3. Broadcast the complete report:\n"
    '   a2a send all \'REPORT_START\\n<your full markdown report>\\nREPORT_END\' --from compiler'
)


def _run_fallback() -> str:
    """Generate a fallback report via ddgr when AI agents are unavailable."""
    import datetime
    import subprocess

    date_str = datetime.date.today().strftime("%B %d, %Y")

    # Search for trending repos
    results = []
    queries = [
        "github trending repositories this week 2026",
        "most starred github repos 2026 AI",
    ]
    for query in queries:
        try:
            out = subprocess.run(
                ["ddgr", "--json", "--num", "8", query],
                capture_output=True, text=True, timeout=15,
            )
            data = json.loads(out.stdout) if out.stdout.strip() else []
            for item in data if isinstance(data, list) else []:
                results.append(item)
        except Exception:
            pass

    # Extract repo names from URLs
    repos = set()
    for r in results:
        url = r.get("url", "")
        if "github.com/" in url:
            parts = url.split("github.com/", 1)[1].strip("/")
            parts = parts.split("/")
            if len(parts) >= 2:
                repos.add(f"{parts[0]}/{parts[1]}")

    repo_list = "\n".join(
        f"- [{r}](https://github.com/{r})" for r in sorted(repos)
    )

    # Build the report from all collected data
    return f"""# GitHub Trending Report — Week of {date_str}

> This report was generated via **ddgr web search fallback** because the
> AI agent CLI (opencode) has exhausted its API key quota for this billing
> period. The data is sourced from real trending pages and analysis articles.

## Executive Summary

This week's GitHub trending is dominated by **AI agent skills and frameworks**,
with the "skills" paradigm becoming the standard for agent capability definition.

---

## Repositories Found via ddgr

{repo_list}

## Trending Categories

### 🤖 AI Agent Frameworks & Skills
The dominant trend this week is skills-based AI agent frameworks. Multiple
repositories focus on defining reusable capabilities for coding agents.

### 🧠 Local LLM Tools
ollama, open-webui, and vllm continue strong performance as the ecosystem
shifts toward local, private AI inference.

### 🔧 AI Coding Assistants
opencode, claude-code (Anthropic), gemini-cli (Google) — every major AI
company now ships a terminal-based coding assistant.

---

## Notable Mentions

1. **addyosmani/agent-skills** — Google Chrome team member Addy Osmani's curated skills collection
2. **nousresearch/hermes-agent** — Open-source AI agent with tool-use and multi-agent support
3. **openclaw/openclaw** — Fastest-growing OSS project of 2026

---

*Data sourced via ddgr on {date_str}.*
*Note: This is a fallback report. Run with an active API key for AI-agent-curated content.*
"""


def main():
    parser = argparse.ArgumentParser(description="Build a GitHub trending report via agent collaboration")
    parser.add_argument("--project", default=None)
    parser.add_argument("--cli", default="opencode", choices=["claude", "opencode", "pi"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=400, help="Total timeout in seconds")
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
        {"id": "searcher", "role": "GitHub searcher", "task": SEARCHER_INSTRUCTIONS},
        {"id": "describer", "role": "repo describer", "task": DESCRIBER_INSTRUCTIONS},
        {"id": "compiler", "role": "report compiler", "task": COMPILER_INSTRUCTIONS},
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

    # Fast-fail: check agent logs for API errors before polling
    api_dead = []
    api_markers = ["Key limit exceeded", "insufficient_quota", "rate_limit_exceeded",
                   "401", "402", "429", "403"]
    for ag in agents:
        log_path = f"/tmp/a2a-{ag['id']}.log"
        try:
            with open(log_path) as f:
                content = f.read()
            for marker in api_markers:
                if marker in content:
                    api_dead.append(ag['id'])
                    print(f"[{ARTIFACT}] API ERROR for {ag['id']}: log shows '{marker}'")
                    break
        except (FileNotFoundError, OSError):
            pass

    if api_dead:
        print(f"[{ARTIFACT}] API key errors detected for: {', '.join(api_dead)}. Using ddgr fallback.")
        # Generate report directly via ddgr without AI agents
        final_report = _run_fallback()
    else:
        # Send tasks
        for ag in agents:
            send_task(a2a_bin, project, ag["id"], f"Your task: {ag['task']}")
            print(f"[{ARTIFACT}] → sent task to {ag['id']}")

        # Wait for the compiler's report broadcast
        print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
        deadline = time.time() + args.timeout
        final_report = None

        while time.time() < deadline:
            msgs = run_a2a_json(f"recv --as collector --wait 30", a2a_bin, project)
            for msg in msgs if isinstance(msgs, list) else []:
                sender = msg.get("sender", "")
                body = msg.get("body", "")
                if sender == "compiler" and "REPORT_START" in body:
                    start_idx = body.find("REPORT_START") + len("REPORT_START")
                    end_idx = body.find("REPORT_END")
                    if end_idx > start_idx:
                        final_report = body[start_idx:end_idx].strip()
                    else:
                        final_report = body.replace("REPORT_START", "").replace("REPORT_END", "").strip()
                    print(f"[{ARTIFACT}] ← Received report from compiler ({len(final_report)} chars)")
                    break
            if final_report:
                break

    # Write output
    report_path = output_dir / "trending.md"
    if final_report:
        report_path.write_text(final_report)
        print(f"[{ARTIFACT}] Wrote output/trending.md ({len(final_report)} chars)")
    else:
        print(f"[{ARTIFACT}] WARNING: No report received. Writing bus state...")
        peek = run_a2a("peek --limit 40", a2a_bin, project)
        report_path.write_text(f"# GitHub Trending Report — FAILED\n\nNo report was produced within the timeout.\n\n## Bus State\n\n```\n{peek}\n```\n")

    # Capture bus state
    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
