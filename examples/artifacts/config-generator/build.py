#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: config-generator.

Two agents (architect, implementer) collaborate via the a2a bus to produce
a complete server deployment configuration: docker-compose.yml, nginx.conf,
and .env.example for a typical web application stack.

Usage:
  python3 examples/artifacts/config-generator/build.py [--project NAME] [--cli claude]

Requires a2a, a2a-spawn, and an AI CLI (claude, opencode, or pi).
"""
import os
import sys
import re
import time
import argparse
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, SpawnManager  # noqa: E402

ARTIFACT = "config-generator"
PROMPT_ARCHITECT = (
    "You are the infrastructure architect. Describe a complete server setup for "
    "a production Node.js/Express web API with PostgreSQL, fronted by Nginx as a "
    "reverse proxy, with SSL termination via Let's Encrypt, and environment-based "
    "configuration. The app exposes port 3000 internally. Use 3 containers: "
    "app (Node.js), db (PostgreSQL 16), nginx. "
    "Send the full architecture spec to the implementer. Include: service topology, "
    "network configuration, volume mounts, environment variables needed, and "
    "any healthcheck requirements."
)
PROMPT_IMPLEMENTER = (
    "You are the config implementer. Wait for the architect to send you the server "
    "architecture spec. Once received, generate three files:\n\n"
    "1. docker-compose.yml — multi-service definition with app, db, and nginx services\n"
    "2. nginx.conf — reverse proxy config with SSL proxy settings, rate limiting, "
    "and health endpoint passthrough\n"
    "3. .env.example — all environment variables with placeholder values and comments\n\n"
    "Broadcast each file to 'all' with prefixes 'FILE:docker-compose.yml', "
    "'FILE:nginx.conf', and 'FILE:.env.example' so the build script can capture them. "
    "Wrap each file in ```yaml / ```nginx / ```ini code blocks. "
    "After sending all three, validate to the architect that the files are consistent "
    "(same port references, matching service names, no missing env vars)."
)


def main():
    parser = argparse.ArgumentParser(description="Build server config via agent collaboration")
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
        {"id": "architect", "role": "infra architect", "task": PROMPT_ARCHITECT},
        {"id": "implementer", "role": "config implementer", "task": PROMPT_IMPLEMENTER},
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
    files = {}  # filename -> content

    while time.time() < deadline:
        msgs = run_a2a_json(f"recv --as collector --wait 15", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            body = msg.get("body", "") or ""
            sender = msg.get("sender", "") or ""
            # Extract files by FILE: prefix
            for prefix in ["FILE:docker-compose.yml", "FILE:nginx.conf", "FILE:.env.example"]:
                if prefix in body and prefix.replace("FILE:", "") not in files:
                    fname = prefix.replace("FILE:", "")
                    content = _extract_from_fence(body, prefix, fname)
                    if content and len(content) > 20:
                        files[fname] = content
                        print(f"[{ARTIFACT}] ← Captured {fname} ({len(content)} chars) from {sender}")

            # Also scan for code blocks not prefixed with FILE:
            body_ = body
            sender_ = sender
            for fname, lang in [("docker-compose.yml", "yaml"), ("nginx.conf", "nginx"), (".env.example", "ini")]:
                if fname not in files:
                    for match in re.finditer(rf"```{lang}\n(.*?)```", body_, re.DOTALL):
                        content = match.group(1).strip()
                        if len(content) > 20 and fname not in files:
                            files[fname] = content
                            print(f"[{ARTIFACT}] ← Captured {fname} via code-fence ({len(content)} chars) from {sender_}")

        if len(files) >= 3:
            break

    # Write captured files
    written = 0
    for fname in ["docker-compose.yml", "nginx.conf", ".env.example"]:
        content = files.get(fname)
        if content:
            (output_dir / fname).write_text(content)
            print(f"[{ARTIFACT}] Wrote output/{fname} ({len(content)} chars)")
            written += 1
        else:
            print(f"[{ARTIFACT}] WARNING: {fname} not captured")

    if written == 0:
        print(f"[{ARTIFACT}] WARNING: No files received. Checking bus...")
        print(run_a2a("peek --limit 40", a2a_bin, project))

    print(run_a2a("list", a2a_bin, project))
    print(run_a2a("peek --limit 10", a2a_bin, project))

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done. {written}/3 files captured.")


def _extract_from_fence(body: str, prefix: str, fname: str) -> str | None:
    """Extract file content from after FILE: prefix, parsing code fences."""
    idx = body.index(prefix)
    after = body[idx + len(prefix):].strip()
    # Look for code fence after the prefix
    fences = re.findall(r"```\w*\n(.*?)```", after, re.DOTALL)
    for content in fences:
        stripped = content.strip()
        if len(stripped) > 20:
            return stripped
    # If no fence, return text before next FILE: or end
    clean = after.split("FILE:")[0].strip()
    if clean.startswith("```"):
        clean = re.sub(r"```\w*\n?", "", clean).strip()
        clean = re.sub(r"```", "", clean).strip()
    return clean if len(clean) > 20 else None


if __name__ == "__main__":
    main()
