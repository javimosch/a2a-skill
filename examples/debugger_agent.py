#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debugger Agent — Example a2a peer demonstrating diagnostic assistance pattern.

This agent demonstrates:
- Receiving error reports from peers
- Diagnostic problem-solving
- Suggesting fixes and workarounds
- Collaborative debugging workflows
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
    agent_id = "debugger"
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

    print(f"[{agent_id}] Starting debugger agent")

    # Advertise availability
    msg = "🐛 Debugger online. Send error reports or troubleshooting requests."
    run(f'{a2a} send all "{msg}" --from {agent_id}')

    # Listen for error reports and debug requests
    print(f"[{agent_id}] Listening for debug requests...")
    debug_sessions = 0
    max_iterations = 8

    for iteration in range(max_iterations):
        messages = json.loads(run(f"{a2a} recv --as {agent_id} --json --wait 20") or "[]")

        if not messages:
            print(f"[{agent_id}] No debug requests (iteration {iteration})")
            if iteration >= 2:
                break
            continue

        for msg in messages:
            sender = msg['sender']
            problem = msg['body']

            # Generate diagnostic response
            diagnosis = f"🔧 Diagnosis: Error in '{problem[:20]}...':\n1. Check preconditions\n2. Add logging\n3. Verify dependencies\n4. Test in isolation"
            run(f'{a2a} send {sender} "{diagnosis}" --from {agent_id}')
            debug_sessions += 1
            print(f"[{agent_id}] Helped debug issue from {sender} (session #{debug_sessions})")

    # Mark done
    run(f"{a2a} status done --as {agent_id}")
    print(f"[{agent_id}] Completed {debug_sessions} debug sessions, marked as done.")

if __name__ == "__main__":
    main()
