#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: docker-compose-generator.

Two agents (specifier, writer) collaborate via the a2a bus to produce
a docker-compose.yml and accompanying README.md for a multi-service stack.

Usage:
  python3 examples/artifacts/docker-compose-generator/build.py [--project NAME] [--cli opencode]

Requires a2a, a2a-spawn, and an AI CLI (claude, opencode, or pi).
"""
import os
import sys
import time
import argparse
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, SpawnManager  # noqa: E402

ARTIFACT = "docker-compose-generator"
PROMPT_SPECIFIER = (
    "You are the stack specifier. Design a multi-service Docker stack for a "
    "modern web application with these services:\n\n"
    "1. frontend: React (Vite) app served by Nginx, port 80\n"
    "2. backend: Python FastAPI, port 8000\n"
    "3. db: PostgreSQL 16, port 5432\n"
    "4. cache: Redis 7, port 6379\n"
    "5. worker: Celery worker for async tasks (same code as backend)\n\n"
    "Describe each service: image/base, ports, volumes, environment variables, "
    "health checks, dependencies, and networking. Send the complete spec to the writer."
)
PROMPT_WRITER = (
    "You are the docker-compose writer. Wait for the specifier to send you "
    "the multi-service stack spec. Once received, generate two files:\n\n"
    "1. docker-compose.yml — complete multi-service definition for all 5 services "
    "using version '3.8' format. Include: named volumes, custom networks, "
    "health checks with conditions in depends_on, environment variables with "
    "sensible placeholders, and port mappings.\n\n"
    "2. README.md — a human-readable document explaining the stack: purpose of "
    "each service, how to start (docker compose up -d), how to access each "
    "service, and key environment variables.\n\n"
    "Broadcast both files to 'all' with prefixes 'FILE:docker-compose.yml' "
    "and 'FILE:README.md'. Wrap each file content in triple-backtick code blocks "
    "with the appropriate language tag (yaml, markdown)."
)


def main():
    parser = argparse.ArgumentParser(description="Build docker-compose stack via agent collaboration")
    parser.add_argument("--project", default=None)
    parser.add_argument("--cli", default="opencode", choices=["claude", "opencode", "pi"])
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    output_dir = script_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    project = args.project or os.environ.get("A2A_PROJECT") or f"artifact-{ARTIFACT}"
    os.environ["A2A_PROJECT"] = project

    a2a_bin = find_a2a(str(script_dir))
    spawn_bin = find_spawn(str(script_dir))
    if not a2a_bin or not spawn_bin:
        print("ERROR: a2a or a2a-spawn not found.", file=sys.stderr)
        sys.exit(1)

    mgr = SpawnManager()
    print(f"[{ARTIFACT}] a2a: {a2a_bin}, spawn: {spawn_bin}, project: {project}, cli: {args.cli}")

    run_a2a("init", a2a_bin, project)
    run_a2a("clear --yes", a2a_bin, project)
    run_a2a("register collector --role build-script --cli python", a2a_bin, project)

    agents = [
        {"id": "specifier", "role": "stack specifier", "task": PROMPT_SPECIFIER},
        {"id": "writer", "role": "docker-compose writer", "task": PROMPT_WRITER},
    ]
    for ag in agents:
        run_a2a(f'register {ag["id"]} --role "{ag["role"]}" --cli {args.cli}', a2a_bin, project)

    for ag in agents:
        kit = make_kit(ag["id"], ag["role"], ag["task"], project)
        with tempfile.NamedTemporaryFile(mode="w", prefix=f"a2a-{project}-{ag['id']}-", suffix=".kit", delete=False) as f:
            f.write(kit)
            kit_path = f.name
        pid = spawn_agent(spawn_bin, args.cli, ag["id"], kit_path, project=project, model=args.model)
        if pid:
            mgr.add(pid)
        os.unlink(kit_path)

    time.sleep(3)
    for ag in agents:
        run_a2a(f'send {ag["id"]} "Your task: {ag["task"]}" --from collector', a2a_bin, project)
        print(f"[{ARTIFACT}] → sent task to {ag['id']}")

    # Collect generated files from the bus
    print(f"[{ARTIFACT}] Waiting for config files (up to 180s)...")
    deadline = time.time() + 180
    files = {}

    while time.time() < deadline:
        msgs = run_a2a_json(f"recv --as collector --wait 15", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            body = msg.get("body", "") or ""
            sender = msg.get("sender", "") or ""
            # Extract files by FILE: prefix
            for fname in ["docker-compose.yml", "README.md"]:
                prefix = f"FILE:{fname}"
                if prefix in body and fname not in files:
                    content = _extract_file(body, prefix)
                    if content and len(content) > 30:
                        files[fname] = content
                        print(f"[{ARTIFACT}] ← Captured {fname} ({len(content)} chars) from {sender}")

        if len(files) >= 2:
            break

    # Write captured files
    written = 0
    for fname in ["docker-compose.yml", "README.md"]:
        content = files.get(fname)
        if content:
            (output_dir / fname).write_text(content)
            print(f"[{ARTIFACT}] Wrote output/{fname} ({len(content)} chars)")
            written += 1
        else:
            print(f"[{ARTIFACT}] WARNING: {fname} not captured")

    if written == 0:
        print(f"[{ARTIFACT}] WARNING: No files received. Dumping bus state...")
        print(run_a2a("peek --limit 40", a2a_bin, project))

    print(run_a2a("list", a2a_bin, project))
    print(run_a2a("peek --limit 10", a2a_bin, project))

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done. {written}/2 files captured.")


def _extract_file(body: str, prefix: str) -> str | None:
    """Extract file content from after FILE: prefix, parsing code fences."""
    idx = body.find(prefix)
    if idx == -1:
        return None
    after = body[idx + len(prefix):].strip()
    # Try to find a code fence after the prefix
    import re
    fences = re.findall(r"```\w*\n(.*?)```", after, re.DOTALL)
    for content in fences:
        stripped = content.strip()
        if len(stripped) > 30:
            return stripped
    # If no fence, return text before next FILE: or end
    clean = after.split("FILE:")[0].strip()
    return clean if len(clean) > 30 else None


if __name__ == "__main__":
    main()
