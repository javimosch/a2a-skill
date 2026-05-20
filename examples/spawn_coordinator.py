#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spawn Coordinator — demonstrates Pattern 3 (auto-spawn) using a2a-spawn.

This harness script:
  - Initialises an a2a project bus
  - Registers itself as 'coordinator' plus two worker agents
  - Spawns the workers as background AI CLI sessions via a2a-spawn
  - Assigns tasks to each worker on the bus
  - Collects results via a2a recv
  - Broadcasts a summary and marks itself done
  - Cleans up spawned processes on exit

Usage:
  python3 examples/spawn_coordinator.py --project mytest [--cli claude]

Requires:
  - a2a and a2a-spawn on PATH (or at common skill paths)
  - The chosen AI CLI (claude, opencode, or pi) installed and configured
"""

import os
import sys
import json
import time
import atexit
import signal
import subprocess
import tempfile
import argparse
from pathlib import Path


# ── Locator helpers (same pattern as the kit prompt) ──────────────

def find_a2a():
    """Locate the a2a binary using the standard resolution order."""
    # 1. A2A_BIN env var
    a2a = os.environ.get("A2A_BIN", "")
    if a2a and os.path.isfile(a2a) and os.access(a2a, os.X_OK):
        return a2a

    # 2. command -v a2a
    try:
        out = subprocess.run(
            ["command", "-v", "a2a"], capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout.strip():
            a2a = out.stdout.strip()
            if os.path.isfile(a2a) and os.access(a2a, os.X_OK):
                return a2a
    except Exception:
        pass

    # 3. Common skill paths
    for p in [
        os.path.expanduser("~/.agents/skills/a2a/a2a"),
        os.path.expanduser("~/.claude/skills/a2a/a2a"),
    ]:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p

    return None


def find_spawn():
    """Locate the a2a-spawn helper script."""
    # 1. command -v a2a-spawn
    try:
        out = subprocess.run(
            ["command", "-v", "a2a-spawn"], capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout.strip():
            spawn = out.stdout.strip()
            if os.path.isfile(spawn) and os.access(spawn, os.X_OK):
                return spawn
    except Exception:
        pass

    # 2. Next to a2a binary
    a2a = find_a2a()
    if a2a:
        candidate = str(Path(a2a).parent / "a2a-spawn")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    # 3. Common skill paths
    for p in [
        os.path.expanduser("~/.agents/skills/a2a/a2a-spawn"),
        os.path.expanduser("~/.claude/skills/a2a/a2a-spawn"),
    ]:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p

    return None


# ── Helpers ────────────────────────────────────────────────────────

def a2a(cmd, a2a_bin, project):
    """Run an a2a CLI command and return parsed JSON (if --json) or stdout."""
    full_cmd = f'export A2A_PROJECT={project} && "{a2a_bin}" ' + cmd
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[a2a] CMD FAILED ({result.returncode}): {full_cmd}", file=sys.stderr)
        print(f"[a2a] stderr: {result.stderr}", file=sys.stderr)
    return result.stdout.strip()


def spawn_agent(spawn_bin, cli, agent_id, kit_path, model=None, project=None):
    """Spawn a background AI CLI session via a2a-spawn. Returns PID."""
    cmd = [spawn_bin, "--cli", cli, "--id", agent_id, "--kit-file", kit_path]
    if model:
        cmd.extend(["--model", model])
    env = os.environ.copy()
    if project:
        env["A2A_PROJECT"] = project

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    # a2a-spawn writes the PID to stdout
    if proc.stdout is None:
        print(f"[spawn] No stdout from a2a-spawn for {agent_id}", file=sys.stderr)
        return None
    try:
        pid_str = proc.stdout.readline().decode().strip()
        pid = int(pid_str)
    except (ValueError, AttributeError):
        print(f"[spawn] Failed to read PID from a2a-spawn for {agent_id}", file=sys.stderr)
        return None

    print(f"[spawn] {agent_id} -> PID {pid}")
    return pid


# ── Kit prompt builders ────────────────────────────────────────────

def make_worker_kit(agent_id, role, task, project, peers_json):
    """Build the kit prompt for a worker agent."""
    return f"""You are agent "{agent_id}" on an a2a peer bus (project={project}).

Your role: {role}
Your task: {task}

You are one of several peers. There is no boss. You decide whom to message,
when to answer, when to stop.

== Peers on the bus ==
{peers_json}

== How to find the a2a CLI ==
A2A="$(command -v a2a 2>/dev/null)"
[ -z "$A2A" ] && [ -x "$HOME/.agents/skills/a2a/a2a" ] && A2A="$HOME/.agents/skills/a2a/a2a"
[ -z "$A2A" ] && [ -x "$HOME/.claude/skills/a2a/a2a" ] && A2A="$HOME/.claude/skills/a2a/a2a"

== How to communicate ==
A2A_PROJECT={project} is already in the environment.

  # check your inbox (blocks up to 15s)
  $A2A recv --as {agent_id} --wait 15

  # send a direct message
  $A2A send <peer-id> "your message" --from {agent_id}

  # broadcast
  $A2A send all "your message" --from {agent_id}

  # mark done
  $A2A status done --as {agent_id}

== Instructions ==
1. Wait for the coordinator to assign you a task.
2. Complete the task and report your result to the coordinator.
3. If recv returns empty 3 times in a row, mark done and exit.
4. Hard cap: 8 loop iterations, then mark done and stop.

Begin now: run the locator snippet, then recv and wait for instructions."""


# ── Spawned PIDs tracker for cleanup ─────────────────────────────

spawned_pids = []


def cleanup(signum=None, frame=None):
    """Kill all spawned background sessions."""
    for pid in spawned_pids:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"[cleanup] Killed PID {pid}")
        except ProcessLookupError:
            pass
    if signum is not None:
        sys.exit(1)


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="a2a spawn-coordinator example")
    parser.add_argument("--project", default=None, help="a2a project name")
    parser.add_argument("--cli", default="claude", choices=["claude", "opencode", "pi"],
                        help="AI CLI to spawn workers with (default: claude)")
    parser.add_argument("--model", default=None, help="Model to use (e.g. haiku)")
    args = parser.parse_args()

    project = args.project or os.environ.get("A2A_PROJECT") or os.path.basename(os.getcwd())
    os.environ["A2A_PROJECT"] = project

    # Locate tools
    a2a_bin = find_a2a()
    spawn_bin = find_spawn()
    if not a2a_bin:
        print("ERROR: a2a binary not found. Install a2a first.", file=sys.stderr)
        sys.exit(1)
    if not spawn_bin:
        print("ERROR: a2a-spawn not found. Install the a2a skill first.", file=sys.stderr)
        sys.exit(1)

    print(f"[coordinator] Using a2a: {a2a_bin}")
    print(f"[coordinator] Using a2a-spawn: {spawn_bin}")
    print(f"[coordinator] Project: {project}")
    print(f"[coordinator] CLI: {args.cli}")

    # Register cleanup on exit
    atexit.register(cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    # Step 1 — Init bus
    print("[coordinator] Initialising bus...")
    a2a("init", a2a_bin, project)

    # Step 2 — Register agents
    agent_id = "coordinator"
    workers = [
        {"id": "worker-1", "role": "summariser",
         "task": "Read the bus for a question from coordinator. Reply with a one-sentence summary of the previous day's weather in San Francisco."},
        {"id": "worker-2", "role": "fact-checker",
         "task": "Read the bus for a question from coordinator. Reply with a one-sentence fact about the Eiffel Tower."},
    ]

    print("[coordinator] Registering agents...")
    a2a(f'register {agent_id} --role orchestrator --cli python', a2a_bin, project)
    for w in workers:
        a2a(f'register {w["id"]} --role "{w["role"]}" --prompt "{w["task"]}" --cli {args.cli}', a2a_bin, project)

    # Get peer info for kit prompts
    peers_json = a2a("list --json", a2a_bin, project)

    # Step 3 — Spawn workers via a2a-spawn
    print("[coordinator] Spawning workers...")
    for w in workers:
        kit = make_worker_kit(w["id"], w["role"], w["task"], project, peers_json)
        with tempfile.NamedTemporaryFile(
            mode="w", prefix=f"a2a-{project}-{w['id']}-", suffix=".kit", delete=False
        ) as f:
            f.write(kit)
            kit_path = f.name

        pid = spawn_agent(spawn_bin, args.cli, w["id"], kit_path,
                          model=args.model, project=project)
        if pid:
            spawned_pids.append(pid)
            # Record PID in the registry so peers can see who is online
            a2a(f'register {w["id"]} --pid {pid} --upsert', a2a_bin, project)

        # Clean up the temp kit file
        try:
            os.unlink(kit_path)
        except OSError:
            pass

    # Step 4 — Assign tasks on the bus
    print("[coordinator] Assigning tasks...")
    time.sleep(2)  # brief pause for agents to start up
    for w in workers:
        a2a(f'send {w["id"]} "Task: {w["task"]}" --from {agent_id}', a2a_bin, project)
        print(f"[coordinator] → sent task to {w['id']}")

    # Step 5 — Collect results
    print("[coordinator] Waiting for results (up to 90s)...")
    results = {}
    deadline = time.time() + 90
    while time.time() < deadline and len(results) < len(workers):
        messages_raw = a2a(f"recv --as {agent_id} --json --wait 10", a2a_bin, project)
        if messages_raw:
            try:
                messages = json.loads(messages_raw)
            except json.JSONDecodeError:
                messages = []
            for msg in messages:
                sender = msg.get("sender", "")
                body = msg.get("body", "")
                if sender not in results:
                    results[sender] = body
                    print(f"[coordinator] ← result from {sender}: {body[:80]}...")

    # Step 6 — Broadcast summary
    summary_parts = [f"Received {len(results)}/{len(workers)} results."]
    for w in workers:
        wid = w["id"]
        result = results.get(wid, "NO RESPONSE")
        summary_parts.append(f"  {wid} ({w['role']}): {result}")
    summary = "\n".join(summary_parts)
    print(f"[coordinator] Summary:\n{summary}")
    a2a(f'send all "Coordinator summary:\\\\n{summary}" --from {agent_id}', a2a_bin, project)

    # Step 7 — Mark done
    a2a(f"status done --as {agent_id}", a2a_bin, project)
    print("[coordinator] Marked done. Final bus state:")
    print(a2a("peek --limit 20", a2a_bin, project))

    # Cleanup
    cleanup()


if __name__ == "__main__":
    main()
