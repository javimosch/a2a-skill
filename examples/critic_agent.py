#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Critic Agent — Example a2a peer demonstrating critical feedback pattern.

This agent demonstrates:
- Receiving proposals from peers
- Providing constructive criticism
- Iterative refinement through feedback loops
- Cross-agent discussion facilitation
"""

import os
import json
import subprocess
import sys

def run(cmd):
    """Execute shell command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def main():
    agent_id = "critic"
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

    print(f"[{agent_id}] Starting critic agent")

    # Advertise role
    msg = "I'm here to provide constructive feedback. Send me proposals to critique."
    run(f'{a2a} send all "{msg}" --from {agent_id}')

    # Listen for proposals and feedback requests
    print(f"[{agent_id}] Listening for proposals to critique...")
    iterations = 0
    max_iterations = 8

    while iterations < max_iterations:
        messages = json.loads(run(f"{a2a} recv --as {agent_id} --json --wait 20") or "[]")

        if not messages:
            print(f"[{agent_id}] No messages (iteration {iterations})")
            iterations += 1
            if iterations >= 3:
                break
            continue

        for msg in messages:
            sender = msg['sender']
            body = msg['body']

            # Generate constructive criticism
            feedback = f"🔍 Critical analysis: '{body[:30]}...': Strengths—clear direction. Improvements—consider edge cases, add error handling, document assumptions."
            run(f'{a2a} send {sender} "{feedback}" --from {agent_id}')
            print(f"[{agent_id}] Provided feedback to {sender}")

        iterations += 1

    # Mark done
    run(f"{a2a} status done --as {agent_id}")
    print(f"[{agent_id}] Critique session complete, marked as done.")

if __name__ == "__main__":
    main()
