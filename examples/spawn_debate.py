#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spawn Debate — demonstrates Pattern 3 (auto-spawn) with adversarial peers.

This harness script:
  - Initialises an a2a project bus
  - Registers 'proposer' and 'critic' agents
  - Spawns both as background AI CLI sessions via a2a-spawn
  - The proposer broadcasts an idea, the critic responds
  - After 2-3 exchanges both mark done
  - Monitors the bus and logs exchanges
  - Cleans up spawned processes on exit

Usage:
  python3 examples/spawn_debate.py --project mydebate [--cli claude]

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


# ── Locator helpers ────────────────────────────────────────────────

def find_a2a():
    """Locate the a2a binary using the standard resolution order."""
    a2a = os.environ.get("A2A_BIN", "")
    if a2a and os.path.isfile(a2a) and os.access(a2a, os.X_OK):
        return a2a

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

    for p in [
        os.path.expanduser("~/.agents/skills/a2a/a2a"),
        os.path.expanduser("~/.claude/skills/a2a/a2a"),
    ]:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p

    return None


def find_spawn():
    """Locate the a2a-spawn helper script."""
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

    a2a = find_a2a()
    if a2a:
        candidate = str(Path(a2a).parent / "a2a-spawn")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    for p in [
        os.path.expanduser("~/.agents/skills/a2a/a2a-spawn"),
        os.path.expanduser("~/.claude/skills/a2a/a2a-spawn"),
    ]:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p

    return None


# ── Helpers ────────────────────────────────────────────────────────

def a2a(cmd, a2a_bin, project):
    """Run an a2a CLI command."""
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

def make_proposer_kit(agent_id, project, peers_json):
    """Build kit prompt for the proposer agent."""
    return f"""You are agent "{agent_id}" on an a2a peer bus (project={project}).

Your role: proposer
Your task: Propose a bold idea for improving team productivity. Broadcast it,
then listen for the critic's response. If the critic responds, reply with a
counter-argument or refinement. After 2-3 exchanges, mark yourself done.

== Peers on the bus ==
{peers_json}

== How to find the a2a CLI ==
A2A="$(command -v a2a 2>/dev/null)"
[ -z "$A2A" ] && [ -x "$HOME/.agents/skills/a2a/a2a" ] && A2A="$HOME/.agents/skills/a2a/a2a"
[ -z "$A2A" ] && [ -x "$HOME/.claude/skills/a2a/a2a" ] && A2A="$HOME/.claude/skills/a2a/a2a"

== How to communicate ==
A2A_PROJECT={project} is already in the environment.

  $A2A recv --as {agent_id} --wait 15
  $A2A send <peer-id> "message" --from {agent_id}
  $A2A send all "message" --from {agent_id}
  $A2A status done --as {agent_id}

== Instructions ==
1. Broadcast your bold idea.
2. Wait for the critic to respond.
3. Reply to the critic with a counter-argument.
4. After 2-3 exchanges total, mark done and exit.
5. If recv returns empty 3 times in a row, mark done and exit.
6. Hard cap: 10 loop iterations, then mark done and stop.

Begin now: run the locator snippet, then broadcast your idea."""


def make_critic_kit(agent_id, project, peers_json):
    """Build kit prompt for the critic agent."""
    return f"""You are agent "{agent_id}" on an a2a peer bus (project={project}).

Your role: critic
Your task: Wait for the proposer to broadcast an idea. Then deliver a sharp but
constructive critique. If the proposer responds to your critique, reply with a
rebuttal. After 2-3 exchanges, mark yourself done.

== Peers on the bus ==
{peers_json}

== How to find the a2a CLI ==
A2A="$(command -v a2a 2>/dev/null)"
[ -z "$A2A" ] && [ -x "$HOME/.agents/skills/a2a/a2a" ] && A2A="$HOME/.agents/skills/a2a/a2a"
[ -z "$A2A" ] && [ -x "$HOME/.claude/skills/a2a/a2a" ] && A2A="$HOME/.claude/skills/a2a/a2a"

== How to communicate ==
A2A_PROJECT={project} is already in the environment.

  $A2A recv --as {agent_id} --wait 15
  $A2A send <peer-id> "message" --from {agent_id}
  $A2A send all "message" --from {agent_id}
  $A2A status done --as {agent_id}

== Instructions ==
1. Wait for the proposer's broadcast.
2. Deliver a constructive critique of their idea.
3. If they reply, issue a rebuttal.
4. After 2-3 exchanges total (or if recv is empty 3 times), mark done and exit.
5. Hard cap: 10 loop iterations, then mark done and stop.

Begin now: run the locator snippet, then recv and wait for the proposer."""


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


# ── Bus Monitor ────────────────────────────────────────────────────

def monitor_bus(a2a_bin, project, duration=120, interval=10):
    """Poll the bus and print new messages."""
    print(f"[monitor] Watching bus for {duration}s (every {interval}s)...")
    seen = set()
    deadline = time.time() + duration
    while time.time() < deadline:
        raw = a2a("peek --json --limit 30", a2a_bin, project)
        if raw:
            try:
                msgs = json.loads(raw)
            except json.JSONDecodeError:
                msgs = []
            for m in msgs:
                mid = m.get("id", "")
                if mid and mid not in seen:
                    seen.add(mid)
                    sender = m.get("sender", "?")
                    recipient = m.get("recipient", "ALL")
                    body = m.get("body", "")[:120]
                    print(f"[bus] #{mid} {sender} → {recipient}: {body}")
        # Check if both agents are done
        list_raw = a2a("list --json", a2a_bin, project)
        if list_raw:
            try:
                agents = json.loads(list_raw)
                active = [a for a in agents if a.get("status") not in ("done",)]
                agent_ids = [a.get("id", "") for a in agents]
                if all(a.get("status") in ("done",) for a in agents if a.get("id") != "bus-monitor"):
                    print("[monitor] All agents done.")
                    return
            except json.JSONDecodeError:
                pass
        time.sleep(interval)
    print("[monitor] Monitoring period expired.")


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="a2a spawn-debate example")
    parser.add_argument("--project", default=None, help="a2a project name")
    parser.add_argument("--cli", default="claude", choices=["claude", "opencode", "pi"],
                        help="AI CLI to spawn agents with (default: claude)")
    parser.add_argument("--model", default=None, help="Model to use (e.g. haiku)")
    parser.add_argument("--duration", type=int, default=120,
                        help="Max monitoring duration in seconds (default: 120)")
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

    print(f"[harness] Using a2a: {a2a_bin}")
    print(f"[harness] Using a2a-spawn: {spawn_bin}")
    print(f"[harness] Project: {project}")
    print(f"[harness] CLI: {args.cli}")

    # Register cleanup on exit
    atexit.register(cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    # Step 1 — Init bus
    print("[harness] Initialising bus...")
    a2a("init", a2a_bin, project)

    # Register a bus-monitor agent so we can recv as observer
    a2a('register bus-monitor --role observer --cli python', a2a_bin, project)

    # Step 2 — Register agents
    agents = [
        {"id": "proposer", "role": "proposer"},
        {"id": "critic", "role": "critic"},
    ]
    print("[harness] Registering agents...")
    for a in agents:
        a2a(f'register {a["id"]} --role {a["role"]} --cli {args.cli}', a2a_bin, project)

    # Get peer info for kit prompts
    peers_json = a2a("list --json", a2a_bin, project)

    # Step 3 — Spawn agents via a2a-spawn
    print("[harness] Spawning agents...")
    for a in agents:
        if a["id"] == "proposer":
            kit = make_proposer_kit(a["id"], project, peers_json)
        else:
            kit = make_critic_kit(a["id"], project, peers_json)

        with tempfile.NamedTemporaryFile(
            mode="w", prefix=f"a2a-{project}-{a['id']}-", suffix=".kit", delete=False
        ) as f:
            f.write(kit)
            kit_path = f.name

        pid = spawn_agent(spawn_bin, args.cli, a["id"], kit_path,
                          model=args.model, project=project)
        if pid:
            spawned_pids.append(pid)
            a2a(f'register {a["id"]} --pid {pid} --upsert', a2a_bin, project)

        try:
            os.unlink(kit_path)
        except OSError:
            pass

    # Step 4 — Monitor the bus
    monitor_bus(a2a_bin, project, duration=args.duration)
    a2a("status done --as bus-monitor", a2a_bin, project)

    # Step 5 — Show final state
    print("\n[harness] Final bus state:")
    print(a2a("peek --limit 50", a2a_bin, project))
    print("\n[harness] Final agent status:")
    print(a2a("list", a2a_bin, project))

    # Cleanup
    cleanup()


if __name__ == "__main__":
    main()
