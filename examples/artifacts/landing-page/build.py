#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: landing-page.

Three agents (designer, copywriter, integrator) collaborate via the a2a bus
to produce a single landing page HTML file.

Usage:
  python3 examples/artifacts/landing-page/build.py [--project NAME] [--cli claude]

Requires a2a, a2a-spawn, and an AI CLI (claude, opencode, or pi).
"""
import os
import sys
import json
import time
import argparse
import tempfile
from pathlib import Path

# Add parent dir for _util import
sys.path.insert(0, str(Path(__file__).parent.parent))
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, SpawnManager, wait_for_messages  # noqa: E402

ARTIFACT = "landing-page"
AGENTS = [
    {"id": "designer", "role": "html-css designer",
     "task": "You are the designer. Propose a complete HTML+CSS structure for a landing page "
             "for 'FlowForge' — a project management SaaS. Include navigation, hero, features, "
             "and footer sections. Use a modern, clean design with a blue/indigo color scheme. "
             "Send your HTML structure (without body content, just structure + CSS styles) to the integrator."},
    {"id": "copywriter", "role": "copywriter",
     "task": "You are the copywriter. Write compelling marketing copy for a landing page "
             "for 'FlowForge' — a project management SaaS. Write the hero headline, "
             "subheadline, feature descriptions (3 features: Kanban boards, Gantt charts, "
             "team chat), and a call-to-action. Send your copy to the integrator."},
    {"id": "integrator", "role": "integrator",
     "task": "You are the integrator. Wait for the designer and copywriter to send you their "
             "work. Once you have both: combine the designer's HTML structure + CSS with the "
             "copywriter's content into a single, complete, self-contained HTML page. "
             "The page must be valid HTML5 with inline CSS. "
             "Broadcast the final HTML to 'all' so it appears on the bus."},
]


def main():
    parser = argparse.ArgumentParser(description="Build FlowForge landing page via agent collaboration")
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
    if not a2a_bin:
        print("ERROR: a2a binary not found. Run this from the a2a-skill repo root.")
        sys.exit(1)
    if not spawn_bin:
        print("ERROR: a2a-spawn not found.")
        sys.exit(1)

    mgr = SpawnManager()
    print(f"[{ARTIFACT}] a2a: {a2a_bin}, spawn: {spawn_bin}, project: {project}, cli: {args.cli}")

    # Init bus
    run_a2a("init", a2a_bin, project)
    run_a2a("clear --yes", a2a_bin, project)

    # Register agent 'collector' (this script acts through it)
    run_a2a(f"register collector --role build-script --cli python", a2a_bin, project)

    # Register and spawn agents
    for ag in AGENTS:
        run_a2a(f'register {ag["id"]} --role "{ag["role"]}" --cli {args.cli}', a2a_bin, project)

    peers_json = run_a2a("list --json", a2a_bin, project)

    for ag in AGENTS:
        kit = make_kit(ag["id"], ag["role"], ag["task"], project)
        with tempfile.NamedTemporaryFile(mode="w", prefix=f"a2a-{project}-{ag['id']}-", suffix=".kit", delete=False) as f:
            f.write(kit)
            kit_path = f.name
        pid = spawn_agent(spawn_bin, args.cli, ag["id"], kit_path, project=project, model=args.model)
        if pid:
            mgr.add(pid)
        os.unlink(kit_path)

    # Send startup tasks to designer and copywriter
    time.sleep(3)
    for ag in AGENTS:
        run_a2a(f'send {ag["id"]} "Your task: {ag["task"]}" --from collector', a2a_bin, project)
        print(f"[{ARTIFACT}] → sent task to {ag['id']}")

    # Wait up to 180s for the integrator to broadcast the final HTML
    print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to 180s)...")
    deadline = time.time() + 180
    final_html = None
    while time.time() < deadline:
        msgs = run_a2a_json(f"recv --as collector --wait 20", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            sender = msg.get("sender", "")
            body = msg.get("body", "")
            if sender == "integrator" and ("<html" in body.lower() or "<!DOCTYPE" in body):
                final_html = body
                print(f"[{ARTIFACT}] ← Received final HTML from integrator ({len(body)} chars)")
                break
        if final_html:
            break

    # Write output
    if final_html:
        (output_dir / "index.html").write_text(final_html)
        print(f"[{ARTIFACT}] Wrote output/index.html ({len(final_html)} chars)")
    else:
        print(f"[{ARTIFACT}] WARNING: No final HTML received. Output not written.")
        # Dump bus state for debugging
        print("Bus state:")
        print(run_a2a("peek --limit 30", a2a_bin, project))

    # Verify bus
    print(run_a2a("list", a2a_bin, project))
    print(run_a2a("peek --limit 10", a2a_bin, project))

    # Mark collector done
    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
