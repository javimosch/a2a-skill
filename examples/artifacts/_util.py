#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared utilities for artifact build scripts.
Keeps each build.py under 200 lines by factoring out common locator
and a2a CLI helper logic.
"""
import os
import sys
import json
import time
import atexit
import signal
import shlex
import subprocess
import tempfile
from pathlib import Path


def find_a2a(script_dir: str) -> str | None:
    """Locate the a2a binary. Checks repo root first, then common paths."""
    # 1. Repo root (running from examples/artifacts/<name>/)
    candidates = [
        str(Path(script_dir) / "../../../a2a"),
        str(Path(script_dir) / "../../a2a"),
        os.environ.get("A2A_BIN", ""),
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return os.path.realpath(c)

    # 2. command -v a2a
    try:
        out = subprocess.run(["command", "-v", "a2a"], capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            a2a = out.stdout.strip()
            if os.path.isfile(a2a) and os.access(a2a, os.X_OK):
                return a2a
    except Exception:
        pass

    return None


def find_spawn(script_dir: str) -> str | None:
    """Locate a2a-spawn, next to a2a or in repo root."""
    # 1. Next to a2a
    a2a = find_a2a(script_dir)
    if a2a:
        candidate = str(Path(a2a).parent / "a2a-spawn")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return os.path.realpath(candidate)

    # 2. Repo root
    candidates = [
        str(Path(script_dir) / "../../../a2a-spawn"),
        str(Path(script_dir) / "../../a2a-spawn"),
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return os.path.realpath(c)

    return None


def run_a2a(cmd: str, a2a_bin: str, project: str) -> str:
    """Run an a2a CLI command and return stdout.

    Uses shlex.split() + subprocess.run() without shell=True to avoid
    shell interpretation of backticks, $, and other special characters
    that may appear in task prompts or message bodies.
    """
    env = os.environ.copy()
    env["A2A_PROJECT"] = project
    args = [a2a_bin] + shlex.split(cmd)
    result = subprocess.run(args, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(f"[a2a] FAILED ({result.returncode}): {a2a_bin} {cmd}", file=sys.stderr)
        print(f"[a2a] stderr: {result.stderr}", file=sys.stderr)
    return result.stdout.strip()


def run_a2a_json(cmd: str, a2a_bin: str, project: str) -> list | dict:
    """Run a2a with --json and parse result."""
    raw = run_a2a(f"{cmd} --json", a2a_bin, project)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def spawn_agent(spawn_bin: str, cli: str, agent_id: str, kit_path: str,
                project: str | None = None, model: str | None = None) -> int | None:
    """Spawn a background AI CLI session via a2a-spawn. Returns PID."""
    cmd = [spawn_bin, "--cli", cli, "--id", agent_id, "--kit-file", kit_path]
    if model:
        cmd.extend(["--model", model])
    env = os.environ.copy()
    if project:
        env["A2A_PROJECT"] = project

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if not proc.stdout:
        print(f"[spawn] No stdout for {agent_id}", file=sys.stderr)
        return None
    try:
        pid_str = proc.stdout.readline().decode().strip()
        pid = int(pid_str)
        print(f"[spawn] {agent_id} -> PID {pid}")
        return pid
    except (ValueError, AttributeError):
        print(f"[spawn] Bad PID from {agent_id}", file=sys.stderr)
        return None


def make_kit(agent_id: str, role: str, instructions: str, project: str) -> str:
    """Build the kit prompt for an a2a peer agent.

    Follows the standard pattern: identity, locator, communication guide,
    instructions, hard cap.
    """
    return f"""You are agent "{agent_id}" on an a2a peer bus (project={project}).

Your role: {role}

== How to find the a2a CLI ==
A2A="${{A2A_BIN:-}}"
[ -z "$A2A" ] && A2A="$(command -v a2a 2>/dev/null)"
[ -z "$A2A" ] && [ -x "$HOME/.agents/skills/a2a/a2a" ] && A2A="$HOME/.agents/skills/a2a/a2a"
[ -z "$A2A" ] && [ -x "$HOME/.claude/skills/a2a/a2a" ] && A2A="$HOME/.claude/skills/a2a/a2a"

== How to communicate ==
A2A_PROJECT={project} is in your environment.

  # check your inbox (blocks up to 20s):
  $A2A recv --as {agent_id} --wait 20

  # send a direct message:
  $A2A send <peer-id> "your message" --from {agent_id}

  # mark done when finished:
  $A2A status done --as {agent_id}

== Instructions ==
{instructions}

== Ground rules ==
1. If recv returns empty 3 times in a row, mark done and exit.
2. Hard cap: 8 loop iterations, then mark done and stop.
3. Use the locator snippet first, then recv and wait for instructions.
4. Do NOT write any files to disk. Use the a2a bus (send/recv) to communicate — never create files, never edit files directly."""


class SpawnManager:
    """Manages spawned agent PIDs and cleans them up on exit."""

    def __init__(self):
        self.pids = []
        atexit.register(self.cleanup)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def add(self, pid: int):
        self.pids.append(pid)

    def cleanup(self, signum=None, frame=None):
        for pid in self.pids:
            try:
                os.kill(pid, signal.SIGTERM)
                print(f"[cleanup] Killed PID {pid}")
            except ProcessLookupError:
                pass
        if signum is not None:
            sys.exit(1)

    def _signal_handler(self, signum, frame):
        self.cleanup(signum, frame)


def strip_html_preamble(body: str) -> str:
    """Strip any preamble text before the HTML doctype or <html tag.

    AI agents often prepend explanatory text before the actual HTML output.
    This function finds the start of the HTML content and slices from there.
    """
    lowered = body.lower()
    doc_start = lowered.find("<!doctype")
    if doc_start == -1:
        doc_start = lowered.find("<html")
    if doc_start > 0:
        body = body[doc_start:]
    elif doc_start == -1:
        # Try more specific matches
        alt = lowered.find("<!doctype html")
        if alt >= 0:
            body = body[alt:]
    return body


def wait_for_messages(a2a_bin: str, project: str, agent_id: str,
                     expected_senders: set, timeout: int = 120) -> dict:
    """Wait for messages from expected senders. Returns {sender: body}."""
    results = {}
    deadline = time.time() + timeout
    while time.time() < deadline and len(results) < len(expected_senders):
        msgs = run_a2a_json(f"recv --as {agent_id} --wait 15", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            sender = msg.get("sender", "")
            body = msg.get("body", "")
            if sender in expected_senders and sender not in results:
                results[sender] = body
                print(f"[recv] ← from {sender}: {body[:100]}...")
    return results
