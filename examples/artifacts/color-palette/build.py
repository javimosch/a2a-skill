#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: color-palette.

Two agents (colorist, html-generator) collaborate via the a2a bus to
produce an HTML preview page showcasing a harmonious color palette.

Usage:
  python3 examples/artifacts/color-palette/build.py [--project NAME] [--cli claude]

Requires a2a, a2a-spawn, and an AI CLI (claude, opencode, or pi).
"""
import os
import sys
import time
import argparse
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, SpawnManager, strip_html_preamble  # noqa: E402

ARTIFACT = "color-palette"
PROMPT_COLORIST = (
    "You are the colorist. Propose a harmonious color palette for a modern web app called 'FlowForge'. "
    "Define exactly 5 colors: primary, secondary, accent, background, and text. "
    "For each color provide: a name, hex code, and a short description of where it's used. "
    "Send your palette as structured text to the html-generator."
)
PROMPT_GENERATOR = (
    "You are the HTML generator. Wait for the colorist to send you the palette spec. "
    "Once received, create a single self-contained HTML page that previews the palette. "
    "The page must include: a header with the palette name, each color shown as a large swatch "
    "with its hex code and description, and a sample UI section showing the colors applied to "
    "a mock card (title, text, button). Use inline CSS. "
    "Broadcast the final HTML to 'all' with no preamble — start directly with <!DOCTYPE html>."
)


def main():
    parser = argparse.ArgumentParser(description="Build color palette preview via agent collaboration")
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
        {"id": "colorist", "role": "color palette designer", "task": PROMPT_COLORIST},
        {"id": "generator", "role": "html preview generator", "task": PROMPT_GENERATOR},
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

    # Collect final HTML
    print(f"[{ARTIFACT}] Waiting for final HTML (up to 180s)...")
    deadline = time.time() + 180
    final_html = None

    while time.time() < deadline:
        msgs = run_a2a_json(f"recv --as collector --wait 15", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            sender = msg.get("sender", "")
            body = msg.get("body", "")
            if sender == "generator" and ("<html" in body.lower() or "<!DOCTYPE" in body):
                body = strip_html_preamble(body)
                final_html = body
                print(f"[{ARTIFACT}] ← Received final HTML from generator ({len(body)} chars)")
                break
        if final_html:
            break

    if final_html:
        (output_dir / "index.html").write_text(final_html)
        print(f"[{ARTIFACT}] Wrote output/index.html ({len(final_html)} chars)")
    else:
        print(f"[{ARTIFACT}] WARNING: No final HTML received.")
        print(run_a2a("peek --limit 30", a2a_bin, project))

    print(run_a2a("list", a2a_bin, project))
    print(run_a2a("peek --limit 10", a2a_bin, project))

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
