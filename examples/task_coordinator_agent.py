#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task Coordinator Agent — Example a2a peer demonstrating work distribution.

This agent demonstrates:
- Distributing tasks to peers without central control
- Tracking completion status
- Async work coordination
- Broadcasting team progress
"""

import os
import json
import subprocess

def run(cmd):
    """Execute shell command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def main():
    agent_id = "coordinator"
    a2a = os.environ.get("A2A_CLI", "a2a")

    # Find a2a binary
    for cand in [
        subprocess.run("command -v a2a 2>/dev/null", shell=True, capture_output=True, text=True).stdout.strip(),
        os.path.expanduser("~/.agents/skills/a2a/a2a"),
        os.path.expanduser("~/.claude/skills/a2a/a2a"),
    ]:
        if cand and os.path.exists(cand):
            a2a = cand
            break

    print(f"[{agent_id}] Starting task coordinator agent")

    # Get list of available peers
    peers = json.loads(run(f"{a2a} list --json"))
    available_peers = [p['id'] for p in peers if p['id'] != agent_id and p['status'] == 'active']

    print(f"[{agent_id}] Found {len(available_peers)} available peers: {available_peers}")

    # Distribute tasks to peers
    tasks = [
        "Implement auth module",
        "Write unit tests",
        "Update documentation",
        "Review pull requests"
    ]

    assigned_tasks = {}
    for i, (peer, task) in enumerate(zip(available_peers[:len(tasks)], tasks)):
        msg = f"Task assigned: {task}. Please complete and report back when done."
        run(f'{a2a} send {peer} "{msg}" --from {agent_id}')
        assigned_tasks[peer] = task
        print(f"[{agent_id}] Assigned '{task}' to {peer}")

    # Listen for task completion reports
    print(f"[{agent_id}] Waiting for task completion reports...")
    completed = set()

    for iteration in range(8):
        messages = json.loads(run(f"{a2a} recv --as {agent_id} --json --wait 20") or "[]")

        if not messages:
            if iteration > 2:
                break
            continue

        for msg in messages:
            sender = msg['sender']
            if sender in assigned_tasks and sender not in completed:
                completed.add(sender)
                print(f"[{agent_id}] Received completion report from {sender}")

    # Broadcast final status
    status_msg = f"Sprint status: {len(completed)}/{len(assigned_tasks)} tasks completed. Team: {', '.join(completed)}"
    run(f'{a2a} send all "{status_msg}" --from {agent_id}')
    print(f"[{agent_id}] Status: {status_msg}")

    # Mark done
    run(f"{a2a} status done --as {agent_id}")
    print(f"[{agent_id}] Coordination complete, marked as done.")

if __name__ == "__main__":
    main()
