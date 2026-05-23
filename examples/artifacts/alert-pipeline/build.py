#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: alert-pipeline.

Two agents (monitor, notifier) collaborate via the a2a bus to check a
condition (disk usage, ddgr search, etc.) and produce a formatted alert.

Usage:
  python3 examples/artifacts/alert-pipeline/build.py [--project NAME] [--cli opencode]

Requires a2a, a2a-spawn, and an AI CLI.
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

ARTIFACT = "alert-pipeline"


MONITOR_INSTRUCTIONS = (
    "You are the system monitor. Your job: check system conditions and report findings.\n\n"
    "Steps:\n"
    "1. First, run: df -h /app/agent/data 2>/dev/null || df -h / 2>/dev/null\n"
    "   to check disk usage. Extract the 'Use%' value (e.g., '23%').\n"
    "2. Run: free -h | head -3 2>/dev/null || cat /proc/meminfo | head -5\n"
    "   to check memory usage.\n"
    "3. Run: uptime 2>/dev/null\n"
    "   to see system load.\n"
    "4. Run: ddgr --json --num 3 'latest cybersecurity alerts 2026' 2>/dev/null || true\n"
    "   to check for real news.\n"
    "5. Compile findings and send to the notifier:\n"
    '   a2a send notifier \'ALERT: <your structured alert data with disk, memory, load, and any news findings>\' --from monitor\n\n'
    "Include exact numbers for disk usage %, memory used/total, load averages, "
    "and any relevant security headlines."
)

NOTIFIER_INSTRUCTIONS = (
    "You are the alert notifier. Wait for the monitor to send you system data.\n\n"
    "Steps:\n"
    "1. Receive the monitor's message:\n"
    "   a2a recv --as notifier --wait 60\n"
    "2. Extract the system metrics from the ALERT message\n"
    "3. Evaluate each metric against thresholds:\n"
    "   - Disk > 80% = CRITICAL, > 60% = WARNING\n"
    "   - Memory > 80% = CRITICAL, > 60% = WARNING\n"
    "   - Load > 4 = CRITICAL, > 2 = WARNING\n"
    "4. If any news was found, include a news section\n"
    "5. Write a formatted alert log with:\n"
    "   - Timestamp and severity banner\n"
    "   - System health table (metric | value | status | threshold)\n"
    "   - Recommendations section\n"
    "6. Broadcast the complete alert:\n"
    '   a2a send all \'ALERT_START\\n<your formatted alert log>\\nALERT_END\' --from notifier\n\n'
    "Use the format:\n"
    "   [ALERT] Severity: <PASS/WARNING/CRITICAL>\n"
    "   Timestamp: <date>\n"
    "   ---\n"
    "   | Metric | Value | Status | Threshold |\n"
    "   |---\n"
    "   ...\n"
    "   ---\n"
    "   Recommendations: ..."
)


def main():
    parser = argparse.ArgumentParser(description="Build an alert pipeline via agent collaboration")
    parser.add_argument("--project", default=None)
    parser.add_argument("--cli", default="opencode", choices=["claude", "opencode", "pi"])
    parser.add_argument("--model", default=None)
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

    # Init bus
    run_a2a("init", a2a_bin, project)
    run_a2a("clear --yes", a2a_bin, project)
    run_a2a("register collector --role build-script --cli python", a2a_bin, project)

    agents = [
        {"id": "monitor", "role": "system monitor", "task": MONITOR_INSTRUCTIONS},
        {"id": "notifier", "role": "alert notifier", "task": NOTIFIER_INSTRUCTIONS},
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

    # Wait for notifier's alert broadcast
    print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
    deadline = time.time() + args.timeout
    final_alert = None

    while time.time() < deadline:
        msgs = run_a2a_json(f"recv --as collector --wait 30", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            sender = msg.get("sender", "")
            body = msg.get("body", "")
            if sender == "notifier" and "ALERT_START" in body:
                start_idx = body.find("ALERT_START") + len("ALERT_START")
                end_idx = body.find("ALERT_END")
                if end_idx > start_idx:
                    final_alert = body[start_idx:end_idx].strip()
                else:
                    final_alert = body.replace("ALERT_START", "").replace("ALERT_END", "").strip()
                print(f"[{ARTIFACT}] ← Received alert from notifier ({len(final_alert)} chars)")
                break
        if final_alert:
            break

    # Write output
    alert_path = output_dir / "alert.txt"
    if final_alert:
        alert_path.write_text(final_alert)
        print(f"[{ARTIFACT}] Wrote output/alert.txt ({len(final_alert)} chars)")
    else:
        print(f"[{ARTIFACT}] WARNING: No alert received. Writing bus state...")
        peek = run_a2a("peek --limit 30", a2a_bin, project)
        alert_path.write_text(f"# Alert Pipeline — FAILED\n\nNo alert produced within timeout.\n\n## Bus State\n```\n{peek}\n```\n")

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
