#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: tech-stack-advisor.

Two agents (researcher, recommender) collaborate via the a2a bus to
research and recommend the best technology stack for a given category
using real web search (ddgr).

Usage:
  python3 examples/artifacts/tech-stack-advisor/build.py [--project NAME] [--cli opencode] [--category "..."]
  python3 examples/artifacts/tech-stack-advisor/build.py --cli opencode --category "best python web frameworks 2026"

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
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, send_task, wait_for_messages, SpawnManager  # noqa: E402

ARTIFACT = "tech-stack-advisor"
DEFAULT_CATEGORY = "best python web frameworks 2026"


def researcher_instructions(category: str) -> str:
    return (
        f"You are the technology researcher. Your job is to research the category: \"{category}\".\n\n"
        "You have shell access. Use ddgr for web search — it returns JSON.\n"
        "Example: ddgr --json --num 10 \"your search query\"\n\n"
        "Steps:\n"
        f"1. Search: ddgr --json --num 10 \"{category}\"\n"
        "2. Also try: ddgr --json --num 5 --site github.com \"<category> comparison\"\n"
        "3. Read the JSON output carefully — extract key technologies, descriptions, and URLs\n"
        "4. Send your findings to the recommender:\n"
        '   a2a send recommender \'FINDINGS: <your structured findings with tool names, descriptions, URLs>\' --from researcher\n\n'
        "Important: Send the findings as structured text. "
        "Include for each tool/technology:\n"
        "  - Name and version/release year\n"
        "  - Description (1-2 sentences)\n"
        "  - Key features and strengths\n"
        "  - Weaknesses or limitations\n"
        "  - Source URL"
    )


RECOMMENDER_INSTRUCTIONS = (
    "You are the technology advisor/recommender. Wait for the researcher to send you findings.\n\n"
    "Steps:\n"
    "1. Receive the researcher's message:\n"
    "   a2a recv --as recommender --wait 60\n"
    "2. Read the structured findings carefully\n"
    "3. Pick the top 3 technologies/tools that best fit the category\n"
    "4. Create a well-reasoned recommendation with:\n"
    "   - Title: the recommended technology stack\n"
    "   - Use cases: what each tool is best for\n"
    "   - Comparison table: features, pros, cons, pricing\n"
    "   - Final verdict: which one to pick and why\n"
    "5. Use proper markdown formatting: ##, ###, -, | tables, **bold**\n"
    "6. Broadcast the complete guide:\n"
    '   a2a send all \'GUIDE_START\\n<your complete markdown guide>\\nGUIDE_END\' --from recommender\n'
    "   The guide must be between GUIDE_START and GUIDE_END markers."
)


def main():
    parser = argparse.ArgumentParser(description="Build a tech stack guide via agent collaboration")
    parser.add_argument("--project", default=None)
    parser.add_argument("--cli", default="opencode", choices=["claude", "opencode", "pi"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--category", default=DEFAULT_CATEGORY)
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
    print(f"[{ARTIFACT}] Category: \"{args.category}\"")

    # Init bus
    run_a2a("init", a2a_bin, project)
    run_a2a("clear --yes", a2a_bin, project)
    run_a2a("register collector --role build-script --cli python", a2a_bin, project)

    agents = [
        {"id": "researcher", "role": "technology researcher", "task": researcher_instructions(args.category)},
        {"id": "recommender", "role": "technology advisor", "task": RECOMMENDER_INSTRUCTIONS},
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

    # Wait for the recommender's guide broadcast
    print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
    deadline = time.time() + args.timeout
    final_guide = None

    while time.time() < deadline:
        msgs = run_a2a_json(f"recv --as collector --wait 30", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            sender = msg.get("sender", "")
            body = msg.get("body", "")
            if sender == "recommender" and "GUIDE_START" in body:
                start_idx = body.find("GUIDE_START") + len("GUIDE_START")
                end_idx = body.find("GUIDE_END")
                if end_idx > start_idx:
                    final_guide = body[start_idx:end_idx].strip()
                else:
                    final_guide = body.replace("GUIDE_START", "").replace("GUIDE_END", "").strip()
                print(f"[{ARTIFACT}] ← Received guide from recommender ({len(final_guide)} chars)")
                break
        if final_guide:
            break

    # Write output
    guide_path = output_dir / "tech-stack-guide.md"
    if final_guide:
        guide_path.write_text(final_guide)
        print(f"[{ARTIFACT}] Wrote output/tech-stack-guide.md ({len(final_guide)} chars)")
    else:
        print(f"[{ARTIFACT}] WARNING: No guide received. Writing bus state...")
        peek = run_a2a("peek --limit 40", a2a_bin, project)
        guide_path.write_text(f"# Tech Stack Guide — FAILED\n\nNo guide produced within the timeout.\n\n## Bus State (last 40 messages)\n\n```\n{peek}\n```\n")

    # Capture bus state
    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
