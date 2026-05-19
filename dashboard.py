#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a2a Dashboard — Real-time visualization of peer bus activity.

Shows:
- Agent roster and status (active/idle/done/blocked)
- Recent message flow
- Message rate and throughput
- Agent participation stats
"""

import json
import subprocess
import sys
import os
import time
from collections import defaultdict, deque
from datetime import datetime

def run(cmd):
    """Execute shell command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

class A2ADashboard:
    def __init__(self, project="default"):
        self.project = project
        self.a2a = "a2a"
        self.last_message_id = 0
        self.message_history = deque(maxlen=100)
        self.agent_stats = defaultdict(lambda: {"sent": 0, "recv": 0, "broadcasts": 0})

    def get_agents(self):
        """Fetch current agent roster."""
        try:
            data = run(f"A2A_PROJECT={self.project} {self.a2a} list --json")
            return json.loads(data) if data else []
        except:
            return []

    def get_messages(self):
        """Fetch recent messages since last check."""
        try:
            data = run(f"A2A_PROJECT={self.project} {self.a2a} peek --limit 100 --json")
            return json.loads(data) if data else []
        except:
            return []

    def update_stats(self, messages):
        """Update message statistics."""
        for msg in messages:
            if msg['id'] > self.last_message_id:
                self.last_message_id = msg['id']
                self.message_history.append(msg)

                sender = msg['sender']
                self.agent_stats[sender]["sent"] += 1

                if msg['recipient']:
                    self.agent_stats[msg['recipient']]["recv"] += 1
                else:
                    self.agent_stats[sender]["broadcasts"] += 1

    def format_status(self, status):
        """Format status with color/emoji."""
        status_map = {
            "active": "🟢 active",
            "idle": "🟡 idle",
            "done": "✅ done",
            "blocked": "🔴 blocked"
        }
        return status_map.get(status, f"? {status}")

    def format_time(self, timestamp):
        """Format timestamp as HH:MM:SS."""
        try:
            return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        except:
            return "??:??:??"

    def print_agents(self):
        """Print agent roster."""
        agents = self.get_agents()
        if not agents:
            print("  (no agents)")
            return

        print(f"  {'ID':<20} {'ROLE':<20} {'STATUS':<15} {'SENT':<6} {'RECV':<6}")
        print(f"  {'-'*75}")

        for agent in agents:
            agent_id = agent['id']
            role = agent.get('role', '-') or '-'
            status = self.format_status(agent.get('status', 'unknown'))
            stats = self.agent_stats.get(agent_id, {})
            sent = stats.get('sent', 0)
            recv = stats.get('recv', 0)
            print(f"  {agent_id:<20} {role:<20} {status:<15} {sent:<6} {recv:<6}")

    def print_recent_messages(self, limit=10):
        """Print recent message activity."""
        messages = list(self.message_history)[-limit:]
        if not messages:
            print("  (no messages)")
            return

        print(f"  {'TIME':<10} {'FROM':<15} {'TO':<15} {'PREVIEW':<40}")
        print(f"  {'-'*80}")

        for msg in messages:
            timestamp = self.format_time(msg.get('created_at', 0))
            sender = msg['sender'][:15]
            recipient = (msg.get('recipient') or 'ALL')[:15]
            body = msg['body'][:40].replace('\n', ' ')
            print(f"  {timestamp:<10} {sender:<15} {recipient:<15} {body:<40}")

    def print_stats(self):
        """Print message statistics."""
        total_messages = sum(s["sent"] for s in self.agent_stats.values())
        total_broadcasts = sum(s["broadcasts"] for s in self.agent_stats.values())
        total_direct = total_messages - total_broadcasts

        print(f"  Total messages: {total_messages}")
        print(f"  Direct messages: {total_direct}")
        print(f"  Broadcasts: {total_broadcasts}")

        if self.agent_stats:
            most_active = max(self.agent_stats.items(), key=lambda x: x[1]["sent"])
            print(f"  Most active: {most_active[0]} ({most_active[1]['sent']} messages)")

    def display(self):
        """Render full dashboard."""
        # Clear screen
        os.system("clear" if os.name != "nt" else "cls")

        print("=" * 80)
        print(f"a2a Dashboard — {self.project}")
        print(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        print("\n[AGENTS]")
        self.print_agents()

        print("\n[RECENT ACTIVITY]")
        self.print_recent_messages(limit=8)

        print("\n[STATISTICS]")
        self.print_stats()

        print("\n[CONTROLS]")
        print("  q: quit | r: refresh | c: clear stats | p: peek full bus")
        print("=" * 80)

    def run_interactive(self):
        """Run dashboard in interactive mode."""
        print("Starting a2a dashboard (press 'q' to quit)...")
        time.sleep(1)

        try:
            while True:
                messages = self.get_messages()
                self.update_stats(messages)
                self.display()

                # Wait for input or timeout after 5s
                try:
                    import select
                    if sys.stdin in select.select([sys.stdin], [], [], 5)[0]:
                        cmd = input().strip().lower()
                        if cmd == 'q':
                            print("\nDashboard closed.")
                            break
                        elif cmd == 'r':
                            continue
                        elif cmd == 'c':
                            self.agent_stats.clear()
                            self.message_history.clear()
                        elif cmd == 'p':
                            print("\nFull bus peek:")
                            print(run(f"A2A_PROJECT={self.project} {self.a2a} peek --limit 50"))
                            input("\nPress Enter to continue...")
                except:
                    # Fallback for systems without select
                    time.sleep(5)
                    continue
        except KeyboardInterrupt:
            print("\n\nDashboard closed.")

    def run_batch(self, duration_seconds=60):
        """Run dashboard in batch mode for N seconds."""
        start = time.time()
        print(f"Running for {duration_seconds}s (project: {self.project})...\n")

        while time.time() - start < duration_seconds:
            messages = self.get_messages()
            self.update_stats(messages)
            self.display()
            time.sleep(2)

        print("\nDashboard session ended.")

def main():
    project = os.environ.get("A2A_PROJECT", "default")
    duration = None

    # Parse arguments
    if "--batch" in sys.argv:
        idx = sys.argv.index("--batch")
        if idx + 1 < len(sys.argv):
            try:
                duration = int(sys.argv[idx + 1])
            except:
                duration = 60

    dashboard = A2ADashboard(project=project)

    if duration:
        dashboard.run_batch(duration)
    else:
        dashboard.run_interactive()

if __name__ == "__main__":
    main()
