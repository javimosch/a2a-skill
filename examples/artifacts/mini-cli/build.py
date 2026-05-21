#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: mini-cli.

Two agents (architect, implementer) collaborate via the a2a bus to
produce a small, runnable Python CLI tool from a spec.

Usage:
  python3 examples/artifacts/mini-cli/build.py [--project NAME] [--cli claude]

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

ARTIFACT = "mini-cli"
PROMPT_ARCHITECT = (
    "You are the architect. Design a simple Python CLI tool called 'tasky' "
    "— a minimal task tracker that stores tasks in a JSON file (no external deps). "
    "It must be a single-file Python script (no shell wrapper, no multi-file structure). "
    "It must support these commands: add <task>, list, done <id>, and clear. "
    "Send the complete spec to the implementer. The spec must include: "
    "function signatures, JSON format, and usage examples."
)
PROMPT_IMPLEMENTER = (
    "You are the implementer. Wait for the architect to send you the spec for 'tasky'. "
    "Once received, write the complete Python implementation as a single-file CLI "
    "script using argparse. Send ONLY the Python source code — no shell wrapper scripts. "
    "It must use only stdlib (json, argparse, sys, pathlib). "
    "Broadcast the final source code to 'all' "
    "with the prefix 'FINAL_CODE:' so the build script can capture it. "
    "Wrap the code in ```python ... ``` markers."
)


def main():
    parser = argparse.ArgumentParser(description="Build tasky CLI tool via agent collaboration")
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
        {"id": "architect", "role": "cli architect", "task": PROMPT_ARCHITECT},
        {"id": "implementer", "role": "cli implementer", "task": PROMPT_IMPLEMENTER},
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

    # Collect final source code
    print(f"[{ARTIFACT}] Waiting for final code (up to 180s)...")
    deadline = time.time() + 180
    final_code = None

    while time.time() < deadline:
        msgs = run_a2a_json(f"recv --as collector --wait 15", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            body = msg.get("body", "")
            sender = msg.get("sender", "")
            if "FINAL_CODE:" in body or (sender == "implementer" and "import" in body and "def " in body):
                # Extract code from markdown code blocks
                if "```" in body:
                    parts = body.split("```")
                    for p in parts:
                        if "import" in p and ("def " in p or "class " in p or "argparse" in p or '"""' in p or "#!/usr/bin/env python" in p):
                            # Strip language tag if present
                            code = p.strip()
                            if code.startswith("python"):
                                code = code[6:].strip()
                            elif code.startswith("py"):
                                code = code[2:].strip()
                            elif code.startswith("bash"):
                                code = code[4:].strip()
                            # Strip any shell wrapper preamble — find the python shebang or first import
                            py_start = code.find("#!/usr/bin/env python")
                            if py_start == -1:
                                py_start = code.find("import ")
                            if py_start > 0:
                                code = code[py_start:]
                            final_code = code
                            print(f"[{ARTIFACT}] ← Final code from {sender} ({len(final_code)} chars)")
                            break
                elif "FINAL_CODE:" in body:
                    code = body[body.index("FINAL_CODE:") + len("FINAL_CODE:"):].strip()
                    final_code = code
                    print(f"[{ARTIFACT}] ← Final code from {sender} ({len(final_code)} chars)")
            if final_code:
                break
        if final_code:
            break

    if final_code:
        output_path = output_dir / "tasky.py"
        output_path.write_text(final_code)
        os.chmod(output_path, 0o755)
        print(f"[{ARTIFACT}] Wrote output/tasky.py ({len(final_code)} chars, chmod 755)")
    else:
        print(f"[{ARTIFACT}] WARNING: No final code received. Checking bus...")
        print(run_a2a("peek --limit 40", a2a_bin, project))

    print(run_a2a("list", a2a_bin, project))
    print(run_a2a("peek --limit 10", a2a_bin, project))

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
