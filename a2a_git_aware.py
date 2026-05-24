#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a2a Git-Aware Features — Prevent work collisions in collaborative development.

Tracks git branch state and recent commits to alert agents about
potential work collisions and duplicated efforts.
"""

import subprocess
import json
from typing import Optional, Dict, List, Any
from pathlib import Path
from datetime import datetime


class GitAwareClient:
    """Git-aware agent client for work-collision prevention."""

    def __init__(self, agent_id: str, repo_path: Optional[str] = None):
        """Initialize git-aware client.

        Args:
            agent_id: This agent's ID
            repo_path: Path to git repository (defaults to cwd)

        Raises:
            ValueError: If agent_id is empty or whitespace-only
        """
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id must not be empty")
        self.agent_id = agent_id
        self.repo_path = Path(repo_path or ".")

    def _run_git(self, cmd: str) -> str:
        """Run git command and return output.

        Args:
            cmd: Git command (without 'git' prefix)

        Returns:
            Command output
        """
        try:
            result = subprocess.run(
                f"git {cmd}",
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                shell=True,
                timeout=5,
            )
            return result.stdout.strip()
        except Exception as e:
            return f"Error: {e}"

    def get_current_branch(self) -> str:
        """Get current git branch name.

        Returns:
            Branch name or 'unknown'
        """
        output = self._run_git("rev-parse --abbrev-ref HEAD")
        return output if output and "Error" not in output else "unknown"

    def get_recent_commits(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent commits on current branch.

        Args:
            count: Number of commits to retrieve

        Returns:
            List of commit dicts with hash, author, message, timestamp
        """
        cmd = f"log -{count} --format='%H|%an|%s|%aI'"
        output = self._run_git(cmd)

        commits = []
        if output and "Error" not in output:
            for line in output.split("\n"):
                if not line:
                    continue
                parts = line.split("|")
                if len(parts) >= 4:
                    commits.append(
                        {
                            "hash": parts[0],
                            "author": parts[1],
                            "message": parts[2],
                            "timestamp": parts[3],
                        }
                    )

        return commits

    def get_changed_files(self) -> List[str]:
        """Get files changed since last commit.

        Returns:
            List of changed file paths
        """
        output = self._run_git("diff --name-only")
        return output.split("\n") if output and "Error" not in output else []

    def get_branch_status(self) -> Dict[str, Any]:
        """Get detailed branch status.

        Returns:
            Dict with branch info, commits, changed files
        """
        return {
            "branch": self.get_current_branch(),
            "commits": self.get_recent_commits(5),
            "changed_files": self.get_changed_files(),
            "timestamp": datetime.now().isoformat(),
            "agent": self.agent_id,
        }

    def detect_work_collision(
        self, other_agents_branches: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Detect potential work collisions with other agents.

        Args:
            other_agents_branches: List of branch status from other agents

        Returns:
            Dict with collision warnings and recommendations
        """
        my_branch = self.get_current_branch()
        my_files = set(self.get_changed_files())
        my_commits = {c["hash"]: c for c in self.get_recent_commits()}

        collisions = {
            "agent": self.agent_id,
            "branch": my_branch,
            "warnings": [],
            "recommendations": [],
        }

        for other in other_agents_branches:
            # Same branch work
            if other.get("branch") == my_branch:
                collisions["warnings"].append(
                    f"⚠️  {other.get('agent')} also working on '{my_branch}'"
                )
                collisions["recommendations"].append(
                    f"Coordinate with {other.get('agent')} or use feature branches"
                )

            # Overlapping file changes
            other_files = set(other.get("changed_files", []))
            overlap = my_files & other_files
            if overlap:
                collisions["warnings"].append(
                    f"⚠️  {other.get('agent')} modifying: {', '.join(list(overlap)[:3])}"
                )
                collisions["recommendations"].append(
                    "Consider pairing or sequential work on overlapping files"
                )

            # Duplicate commits
            other_commits = {c["hash"] for c in other.get("commits", [])}
            duplicate = set(my_commits.keys()) & other_commits
            if duplicate:
                collisions["warnings"].append(
                    f"⚠️  Duplicate commits detected with {other.get('agent')}"
                )
                collisions["recommendations"].append(
                    "Review recent commits - may indicate branch merge needed"
                )

        return collisions

    def get_collaboration_summary(self) -> str:
        """Get human-readable collaboration summary.

        Returns:
            Formatted text summary
        """
        status = self.get_branch_status()
        summary = f"""
Git Status for {self.agent_id}:
- Branch: {status['branch']}
- Recent commits: {len(status['commits'])}
- Changed files: {len(status['changed_files'])}
- Last change: {status['timestamp']}

Changed files:
"""
        for f in status["changed_files"][:10]:
            summary += f"  - {f}\n"

        if status["changed_files"] and len(status["changed_files"]) > 10:
            summary += f"  ... and {len(status['changed_files']) - 10} more\n"

        return summary

    def format_for_bus(self) -> str:
        """Format git status as JSON for a2a bus.

        Returns:
            JSON string with git status
        """
        return json.dumps(self.get_branch_status())

    @staticmethod
    def parse_bus_message(message: str) -> Optional[Dict[str, Any]]:
        """Parse git status from a2a bus message.

        Args:
            message: Message body from a2a bus

        Returns:
            Parsed dict or None if not valid git status
        """
        try:
            return json.loads(message)
        except json.JSONDecodeError:
            return None


def announce_work_status(client: "GitAwareClient", a2a_client) -> None:
    """Announce current work status to a2a bus.

    Args:
        client: GitAwareClient instance
        a2a_client: A2AClient instance for messaging
    """
    message = client.format_for_bus()
    a2a_client.send("all", message)
    print(f"✓ Work status announced to bus")


def check_collisions(
    client: "GitAwareClient", a2a_client, other_agents: List[str]
) -> None:
    """Check for work collisions with other agents.

    Args:
        client: GitAwareClient instance
        a2a_client: A2AClient instance
        other_agents: List of agent IDs to check
    """
    print("Checking for work collisions...")

    other_statuses = []
    for agent in other_agents:
        # In real use, would poll recent messages from other agents
        # For now, just structure the function
        pass

    collisions = client.detect_work_collision(other_statuses)

    if collisions["warnings"]:
        print(f"\n⚠️  Collision warnings for {client.agent_id}:")
        for warning in collisions["warnings"]:
            print(f"  {warning}")

        print(f"\n💡 Recommendations:")
        for rec in collisions["recommendations"]:
            print(f"  • {rec}")
    else:
        print("✓ No work collisions detected")
