#!/usr/bin/env python3
"""
Code Reviewer Agent — Example a2a peer demonstrating async code review.

This agent demonstrates:
- Receiving work requests from peers
- Async review and feedback loop
- Non-blocking peer coordination
- Handling multiple review requests concurrently
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
    agent_id = "reviewer"
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

    print(f"[{agent_id}] Starting code reviewer agent")

    # Advertise availability
    msg = "I'm ready to review code. Send me diffs or pull requests with context."
    run(f'{a2a} send all "{msg}" --from {agent_id}')

    # Listen for review requests
    print(f"[{agent_id}] Listening for review requests...")
    review_count = 0

    for iteration in range(8):  # Max 8 iterations per kit prompt
        messages = json.loads(run(f"{a2a} recv --as {agent_id} --json --wait 20") or "[]")

        if not messages:
            print(f"[{agent_id}] No messages received in iteration {iteration}")
            continue

        for msg in messages:
            sender = msg['sender']
            body = msg['body']

            # Simulate review: provide feedback
            feedback = f"Reviewed {sender}'s code. Looks good! Suggestions: (1) Add docstrings. (2) Consider error handling."
            run(f'{a2a} send {sender} "{feedback}" --from {agent_id}')
            review_count += 1
            print(f"[{agent_id}] Reviewed code from {sender} (review #{review_count})")

        if iteration >= 2:  # After a few iterations, consider wrapping up
            break

    # Mark done
    run(f"{a2a} status done --as {agent_id}")
    print(f"[{agent_id}] Completed {review_count} reviews, marked as done.")

if __name__ == "__main__":
    main()
