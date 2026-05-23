#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: local-discovery.

Two agents (researcher, mapper) collaborate via the a2a bus to discover
and document businesses/services in a category using real web search.

Usage:
  python3 examples/artifacts/local-discovery/build.py [--project NAME] [--cli opencode] [--topic "..."]

Requires a2a, a2a-spawn, ddgr, and an AI CLI.
"""
import os
import sys
import time
import json
import argparse
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, send_task, check_agent_logs, SpawnManager  # noqa: E402

ARTIFACT = "local-discovery"
DEFAULT_TOPIC = "best AI developer tools startups 2026"


def researcher_instructions(topic: str) -> str:
    return (
        f"You are the web researcher. Topic: \"{topic}\"\n\n"
        "You have shell access. Use ddgr for web search — it returns JSON.\n"
        "Example: ddgr --json --num 10 \"your search query\"\n\n"
        "Steps:\n"
        f"1. Search: ddgr --json --num 10 \"{topic}\"\n"
        "2. Search again: ddgr --json --num 10 --site techcrunch.com \"AI developer tools 2026\"\n"
        "3. Read the JSON output carefully — extract business names, descriptions, URLs\n"
        "4. For each result extract: name, description, URL, key features/focus area\n"
        "5. Send your findings to the mapper:\n"
        '   a2a send mapper \'FINDINGS: <structured list with name, description, url, focus>\' --from researcher\n\n'
        "Important: Send structured text (not raw JSON). Include company/business name, "
        "what they do, their URL, and their primary focus area."
    )


MAPPER_INSTRUCTIONS = (
    "You are the data mapper. Wait for the researcher to send you findings.\n\n"
    "Steps:\n"
    "1. Receive the researcher's data:\n"
    "   a2a recv --as mapper --wait 60\n"
    "2. Extract each business/organization from the researcher's FINDINGS\n"
    "3. Format into a structured JSON array with fields: name, description, url, focus_area\n"
    "4. Compute stats: total count, focus areas breakdown\n"
    "5. Write a markdown report with:\n"
    "   - Title and date\n"
    "   - Executive summary (how many found, variety of focus areas)\n"
    "   - Table of each entry (name | description | focus | URL)\n"
    "   - Statistics section\n"
    "6. Broadcast the complete report:\n"
    '   a2a send all \'REPORT_START\\n<your full markdown report>\\n'
    'JSON_START\\n<JSON array>\\nJSON_END\\nREPORT_END\' --from mapper\n\n'
    "The report must be between REPORT_START and REPORT_END markers, "
    "with the JSON data between JSON_START and JSON_END markers."
)


def main():
    parser = argparse.ArgumentParser(description="Build a local discovery report via agent collaboration")
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
        {"id": "mapper", "role": "data mapper", "task": MAPPER_INSTRUCTIONS},
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
    # Send tasks via stdin
    for ag in agents:
        send_task(a2a_bin, project, ag["id"], f"Your task: {ag['task']}")
        print(f"[{ARTIFACT}] → sent task to {ag['id']}")

    # Wait for mapper's report broadcast
    print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
    deadline = time.time() + args.timeout
    final_report = None
    json_data = None

    while time.time() < deadline:
        msgs = run_a2a_json(f"recv --as collector --wait 30", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            sender = msg.get("sender", "")
            body = msg.get("body", "")
            if sender == "mapper" and "REPORT_START" in body:
                # Extract report between markers
                start_idx = body.find("REPORT_START") + len("REPORT_START")
                end_idx = body.find("REPORT_END")
                if end_idx > start_idx:
                    final_report = body[start_idx:end_idx].strip()

                # Extract JSON between markers
                js_start = body.find("JSON_START")
                js_end = body.find("JSON_END")
                if js_start >= 0 and js_end > js_start:
                    json_text = body[js_start + len("JSON_START"):js_end].strip()
                    try:
                        json_data = json.loads(json_text)
                    except json.JSONDecodeError:
                        json_data = None

                print(f"[{ARTIFACT}] ← Received report from mapper ({len(final_report or '')} chars)")
                break
        if final_report:
            break

    # Write outputs
    report_path = output_dir / "report.md"
    if final_report:
        # Strip JSON markers from report if they leaked
        clean_report = final_report
        if "JSON_START" in clean_report:
            js_idx = clean_report.find("JSON_START")
            clean_report = clean_report[:js_idx].strip()
        report_path.write_text(clean_report)
        print(f"[{ARTIFACT}] Wrote output/report.md ({len(clean_report)} chars)")
    else:
        print(f"[{ARTIFACT}] WARNING: No report received. Writing bus state...")
        peek = run_a2a("peek --limit 30", a2a_bin, project)
        report_path.write_text(f"# Local Discovery — FAILED\n\nNo report produced within timeout.\n\n## Bus State\n```\n{peek}\n```\n")

    if json_data:
        json_path = output_dir / "businesses.json"
        json_path.write_text(json.dumps(json_data, indent=2))
        print(f"[{ARTIFACT}] Wrote output/businesses.json ({len(json_data)} entries)")

    # Capture bus state
    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    # Check agent logs
    agent_ids = [ag["id"] for ag in agents]
    had_errors = check_agent_logs(agent_ids, ARTIFACT)
    if had_errors:
        print(f"[{ARTIFACT}] WARNING: Some agents had API errors")
    else:
        print(f"[{ARTIFACT}] Agent logs: clean")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
