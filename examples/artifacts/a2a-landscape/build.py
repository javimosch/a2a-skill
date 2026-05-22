#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: a2a-landscape.

Three agents (searcher, analyst, writer) collaborate via the a2a bus to produce
a landscape analysis comparing a2a-skill against other multi-agent frameworks
(Google A2A, AutoGen, CrewAI, LangGraph) using ddgr for live web research.

Usage:
  python3 examples/artifacts/a2a-landscape/build.py [--project NAME] [--cli opencode]

Requires a2a, a2a-spawn, ddgr, and an AI CLI (claude, opencode, or pi).
"""
import os
import sys
import time
import argparse
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, send_task, SpawnManager  # noqa: E402

ARTIFACT = "a2a-landscape"


SEARCHER_INSTRUCTIONS = (
    "You are the landscape searcher. Research multi-agent frameworks.\n\n"
    "You have shell access. Use ddgr for web search.\n\n"
    "Steps:\n"
    "1. Run these 2 searches:\n"
    '   ddgr --json --num 5 "multi-agent framework comparison 2026 AutoGen CrewAI LangGraph"\n'
    '   ddgr --json --num 5 "Agent-to-Agent protocol a2a Google peer mesh architecture"\n'
    "2. For each framework you find (a2a, AutoGen, CrewAI, LangGraph, Google A2A):\n"
    "   extract name, creator, architecture, license, key features\n"
    "3. Send findings to the analyst:\n"
    '   a2a send analyst LANDSCAPE:<your findings> --from searcher\n\n'
    "Include all details you find."
)

ANALYST_INSTRUCTIONS = (
    "You are the landscape analyst. Wait for the searcher to send you findings.\n\n"
    "Steps:\n"
    "1. Receive the searcher's message:\n"
    "   a2a recv --as analyst --wait 60\n"
    "2. Build a comparison across these dimensions for each framework:\n"
    "   - License\n"
    "   - Architecture (hub-spoke / mesh / orchestrator)\n"
    "   - Communication model (direct peer-to-peer / broker / orchestrator)\n"
    "   - Persistence (database / in-memory / event log)\n"
    "   - Multi-language support\n"
    "   - Ease of setup\n"
    "   - Typical use case\n"
    "3. Include a special row comparing a2a-skill's unique traits:\n"
    "   - No central orchestrator (truly peer-to-peer)\n"
    "   - SQLite bus (zero deps, stdlib only)\n"
    "   - Read-tracking per agent\n"
    "   - Works across different AI CLIs (Claude, OpenCode, Pi)\n"
    "4. Identify market positioning: who leads in each dimension\n"
    "5. Send your structured analysis to the writer:\n"
    '   a2a send writer ANALYSIS:<your analysis with comparison data> --from analyst'
)

WRITER_INSTRUCTIONS = (
    "You are the landscape report writer. Wait for the analyst.\n\n"
    "Steps:\n"
    "1. Receive the analyst's message:\n"
    "   a2a recv --as writer --wait 60\n"
    "2. Compile a well-formatted markdown landscape analysis:\n"
    "   - Title: 'a2a-skill in the Multi-Agent Ecosystem'\n"
    "   - Executive summary\n"
    "   - Section per framework with description and analysis\n"
    "   - Comparison table (columns: framework, architecture, communication,"
    " persistence, multi-lang, setup, use case)\n"
    "   - Positioning matrix (which framework wins in which scenario)\n"
    "   - Where a2a-skill excels (truly P2P, no orchestrator, cross-CLI, stdlib db)\n"
    "   - Recommendations for when to use each framework\n"
    "3. Use proper markdown: ##, ###, | tables, -, **bold**\n"
    "4. Broadcast the complete report:\n"
    '   a2a send all LANDSCAPE_START\\n<your report>\\nLANDSCAPE_END --from writer'
)


def main():
    parser = argparse.ArgumentParser(description="Build a multi-agent landscape analysis via agent collaboration")
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

    run_a2a("init", a2a_bin, project)
    run_a2a("clear --yes", a2a_bin, project)
    run_a2a("register collector --role build-script --cli python", a2a_bin, project)

    agents = [
        {"id": "searcher", "role": "landscape searcher", "task": SEARCHER_INSTRUCTIONS},
        {"id": "analyst", "role": "landscape analyst", "task": ANALYST_INSTRUCTIONS},
        {"id": "writer", "role": "landscape writer", "task": WRITER_INSTRUCTIONS},
    ]
    for ag in agents:
        run_a2a(f'register {ag["id"]} --role "{ag["role"]}" --cli {args.cli}', a2a_bin, project)

    for ag in agents:
        kit = make_kit(ag["id"], ag["role"], ag["task"], project)
        with tempfile.NamedTemporaryFile(mode="w", prefix=f"a2a-{project}-{ag['id']}-", suffix=".kit", delete=False) as f:
            f.write(kit)
            kit_path = f.name
        pid = spawn_agent(spawn_bin, args.cli, ag["id"], kit_path, project=project, model=args.model)
        if pid:
            mgr.add(pid)
        os.unlink(kit_path)

    time.sleep(3)

    for ag in agents:
        send_task(a2a_bin, project, ag["id"], f"Your task: {ag['task']}")
        print(f"[{ARTIFACT}] → sent task to {ag['id']}")

    print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
    deadline = time.time() + args.timeout
    final_report = None

    while time.time() < deadline:
        msgs = run_a2a_json("recv --as collector --wait 30", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            sender = msg.get("sender", "")
            body = msg.get("body", "")
            if sender == "writer":
                if "LANDSCAPE_START" in body and "LANDSCAPE_END" in body:
                    start_idx = body.find("LANDSCAPE_START") + len("LANDSCAPE_START")
                    end_idx = body.find("LANDSCAPE_END")
                    if end_idx > start_idx:
                        final_report = body[start_idx:end_idx].strip()
                    else:
                        final_report = body.replace("LANDSCAPE_START", "").replace("LANDSCAPE_END", "").strip()
                    print(f"[{ARTIFACT}] ← Received landscape analysis from writer ({len(final_report)} chars)")
                    break
        if final_report:
            break

    report_path = output_dir / "a2a-landscape.md"
    if final_report:
        report_path.write_text(final_report)
        print(f"[{ARTIFACT}] Wrote output/a2a-landscape.md ({len(final_report)} chars)")
    else:
        print(f"[{ARTIFACT}] WARNING: No report received. Writing bus state...")
        peek = run_a2a("peek --limit 40", a2a_bin, project)
        report_path.write_text(f"# a2a-skill Landscape Analysis — FAILED\n\nNo report was produced.\n\n## Bus State\n\n```\n{peek}\n```\n")

    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
