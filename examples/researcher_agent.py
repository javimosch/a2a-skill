#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Researcher Agent — Example a2a peer demonstrating collaborative investigation.

This agent demonstrates:
- Asking peers for information
- Aggregating responses
- Broadcasting findings
- Coordinating without central orchestrator
"""

import os
import json
import subprocess
import sys
import time

def run(cmd):
    """Execute shell command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def main():
    agent_id = "researcher"
    a2a = os.environ.get("A2A_CLI", "a2a")

    # Initialize a2a binary location
    for cand in [
        subprocess.run("command -v a2a 2>/dev/null", shell=True, capture_output=True, text=True).stdout.strip(),
        os.path.expanduser("~/.agents/skills/a2a/a2a"),
        os.path.expanduser("~/.claude/skills/a2a/a2a"),
    ]:
        if cand and os.path.exists(cand):
            a2a = cand
            break

    print(f"[{agent_id}] Starting researcher agent, using a2a at {a2a}")

    # Phase 1: Introduce yourself and request peer list
    print(f"[{agent_id}] Phase 1: Broadcasting introduction")
    peers = json.loads(run(f"{a2a} list --json"))
    peer_names = [p['id'] for p in peers if p['id'] != agent_id]

    intro = f"Hi team, I'm {agent_id}. I'm investigating a2a performance characteristics. Who wants to help?"
    run(f'{a2a} send all "{intro}" --from {agent_id}')

    # Phase 2: Wait for responses and collect data
    print(f"[{agent_id}] Phase 2: Listening for peer responses (up to 30s)")
    responses = {}
    for _ in range(6):  # Poll up to 30s
        messages = json.loads(run(f"{a2a} recv --as {agent_id} --json --wait 5") or "[]")
        for msg in messages:
            sender = msg['sender']
            if sender not in responses:
                responses[sender] = []
            responses[sender].append(msg['body'])
            print(f"[{agent_id}] Got response from {sender}")
        if len(responses) >= min(2, len(peer_names)):
            break

    # Phase 3: Summarize findings
    summary = f"Research summary: Collected data from {len(responses)} peers. Peers: {', '.join(responses.keys())}"
    print(f"[{agent_id}] Phase 3: Broadcasting summary")
    run(f'{a2a} send all "{summary}" --from {agent_id}')

    # Phase 4: Mark done
    run(f"{a2a} status done --as {agent_id}")
    print(f"[{agent_id}] Research complete, marked as done.")

if __name__ == "__main__":
    main()
