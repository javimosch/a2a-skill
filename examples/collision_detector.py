#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Work Collision Detector Agent

Monitors the a2a bus for work status updates and alerts when
multiple agents are working on the same code areas.

Usage:
    python collision_detector.py <project> <agent-id>
"""

import asyncio
import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from a2a_client_async import A2AClientAsync
from a2a_git_aware import GitAwareClient


async def monitor_collisions(client: A2AClientAsync, project: str, agent_id: str):
    """Monitor a2a bus for work status updates and detect collisions.

    Args:
        client: A2AClientAsync client
        project: Project name
        agent_id: This agent's ID
    """
    git_client = GitAwareClient(agent_id, ".")

    print(f"[DETECTOR] Starting collision detector for project '{project}'")
    print(f"[DETECTOR] Monitoring agents for work-collision patterns\n")

    # Announce detector status
    await client.set_status("active")
    await client.send(
        "all",
        json.dumps(
            {
                "type": "detector_status",
                "agent": agent_id,
                "action": "monitoring",
            }
        ),
    )

    agent_statuses = {}
    check_interval = 10  # seconds between collision checks

    try:
        iteration = 0
        while True:
            iteration += 1

            # Poll for work status messages from other agents
            messages = await client.recv(wait=5, unread_only=True, limit=20)

            for msg in messages:
                try:
                    data = json.loads(msg["body"])

                    # Track git status updates
                    if "branch" in data and "agent" in data:
                        agent = data["agent"]
                        agent_statuses[agent] = data

                        print(f"[{iteration}] {agent} on branch: {data['branch']}")
                        if data.get("changed_files"):
                            print(
                                f"    Files: {', '.join(data['changed_files'][:3])}"
                            )

                except json.JSONDecodeError:
                    pass  # Not a git status message

            # Check for collisions every N iterations
            if iteration % check_interval == 0 and agent_statuses:
                print(f"\n[DETECTOR] Collision check at iteration {iteration}...")

                # Analyze branch overlaps
                branches = {}
                for agent, status in agent_statuses.items():
                    branch = status.get("branch")
                    if branch:
                        if branch not in branches:
                            branches[branch] = []
                        branches[branch].append(agent)

                # Alert on same-branch work
                for branch, agents in branches.items():
                    if len(agents) > 1:
                        alert = {
                            "type": "collision_warning",
                            "severity": "high" if len(agents) > 2 else "medium",
                            "branch": branch,
                            "agents": agents,
                            "detector": agent_id,
                        }
                        await client.send("all", json.dumps(alert))
                        print(
                            f"⚠️  COLLISION: {', '.join(agents)} on '{branch}'"
                        )

                # Analyze file overlaps
                all_files = {}
                for agent, status in agent_statuses.items():
                    for file in status.get("changed_files", []):
                        if file not in all_files:
                            all_files[file] = []
                        all_files[file].append(agent)

                overlaps = {f: agents for f, agents in all_files.items() if len(agents) > 1}
                if overlaps:
                    for file, agents in list(overlaps.items())[:3]:
                        alert = {
                            "type": "file_overlap",
                            "severity": "medium",
                            "file": file,
                            "agents": agents,
                            "detector": agent_id,
                        }
                        await client.send("all", json.dumps(alert))
                        print(f"⚠️  FILE OVERLAP: {file} by {', '.join(agents)}")

                print()

    except KeyboardInterrupt:
        print("\n[DETECTOR] Shutdown requested")
    except Exception as e:
        print(f"[DETECTOR] Error: {e}")
    finally:
        await client.set_status("done")


async def broadcaster(client: A2AClientAsync, project: str, agent_id: str):
    """Broadcast this agent's git status periodically.

    Args:
        client: A2AClientAsync client
        project: Project name
        agent_id: This agent's ID
    """
    git_client = GitAwareClient(agent_id, ".")

    print(f"[BROADCASTER] Starting git-status broadcaster for '{agent_id}'")

    await client.set_status("active")

    try:
        iteration = 0
        while True:
            iteration += 1

            # Announce git status every 30 seconds
            if iteration % 6 == 0:  # 6 * 5 second wait = 30 seconds
                status = git_client.get_branch_status()
                await client.send("all", json.dumps(status))
                print(
                    f"[{iteration}] Broadcasted status: {status['branch']} "
                    f"({len(status['changed_files'])} files)"
                )

            # Wait for messages
            await client.recv(wait=5, unread_only=False, limit=1)

    except KeyboardInterrupt:
        print("\n[BROADCASTER] Shutdown requested")
    except Exception as e:
        print(f"[BROADCASTER] Error: {e}")
    finally:
        await client.set_status("done")


async def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: python collision_detector.py <project> <agent-id> [detector|broadcaster]")
        print("  detector:    Monitor bus for collisions")
        print("  broadcaster: Broadcast this agent's git status")
        sys.exit(1)

    project = sys.argv[1]
    agent_id = sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else "detector"

    async with A2AClientAsync(project, agent_id) as client:
        if mode == "broadcaster":
            await broadcaster(client, project, agent_id)
        else:
            await monitor_collisions(client, project, agent_id)


if __name__ == "__main__":
    asyncio.run(main())
