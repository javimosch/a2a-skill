#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: svg-banner.

Two agents (designer, reviewer) collaborate via the a2a bus to produce
an SVG banner image through iterative design and critique.

Usage:
  python3 examples/artifacts/svg-banner/build.py [--project NAME] [--cli claude]

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

ARTIFACT = "svg-banner"
PROMPT_DESIGNER = (
    "You are the SVG designer. Create an SVG banner (800x200) for 'FlowForge' "
    "— a project management SaaS. Use a modern tech aesthetic with a blue/indigo "
    "gradient background, the product name in clean typography, and abstract geometric "
    "decorations (nodes, connecting lines, or circuit-like patterns). "
    "The SVG must be self-contained (no external resources), valid XML, "
    "and responsive (viewBox). Send your SVG to the reviewer for feedback."
)
PROMPT_REVIEWER = (
    "You are the SVG reviewer. Review the banner SVG sent by the designer. "
    "Check for: valid XML, appropriate color harmony, visual balance, typography choices, "
    "and overall aesthetic quality. Send constructive critique back to the designer. "
    "After 2 rounds, send the FINAL APPROVED SVG to 'all' "
    "with the prefix 'FINAL_SVG:' so the build script can capture it."
)


def main():
    parser = argparse.ArgumentParser(description="Build SVG banner via agent collaboration")
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
        {"id": "designer", "role": "svg designer", "task": PROMPT_DESIGNER},
        {"id": "reviewer", "role": "svg reviewer", "task": PROMPT_REVIEWER},
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

    # Collect final SVG from bus
    print(f"[{ARTIFACT}] Waiting for final SVG (up to 180s)...")
    deadline = time.time() + 180
    final_svg = None

    while time.time() < deadline:
        # Also check for direct messages with FINAL_SVG:
        msgs_direct = run_a2a_json(f"recv --as collector --wait 15", a2a_bin, project)
        for msg in msgs_direct if isinstance(msgs_direct, list) else []:
            body = msg.get("body", "")
            sender = msg.get("sender", "")
            if "FINAL_SVG:" in body:
                svg = body[body.index("FINAL_SVG:") + len("FINAL_SVG:"):].strip()
                if svg.startswith("```"):
                    svg = svg.strip("`").strip()
                    if svg.startswith("svg"):
                        svg = svg[3:].strip()
                if "<svg" in svg:
                    final_svg = svg
                    print(f"[{ARTIFACT}] ← Final SVG from {sender} ({len(svg)} chars)")
                    break
                else:
                    # Try looking for SVG between backticks
                    parts = body.split("```")
                    for p in parts:
                        if "<svg" in p or "<SVG" in p:
                            final_svg = p.strip()
                            if final_svg.startswith("svg") or final_svg.startswith("xml"):
                                final_svg = final_svg.split("\n", 1)[-1].strip()
                            print(f"[{ARTIFACT}] ← Final SVG ({len(final_svg)} chars)")
                            break
            if final_svg:
                break

        if final_svg:
            break

    if final_svg:
        (output_dir / "banner.svg").write_text(final_svg)
        print(f"[{ARTIFACT}] Wrote output/banner.svg ({len(final_svg)} chars)")
    else:
        print(f"[{ARTIFACT}] WARNING: No final SVG received. Checking bus...")
        print(run_a2a("peek --limit 40", a2a_bin, project))

    print(run_a2a("list", a2a_bin, project))
    print(run_a2a("peek --limit 10", a2a_bin, project))

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
