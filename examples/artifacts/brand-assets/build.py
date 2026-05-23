#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: brand-assets.

Three agents (designer, reviewer, converter) collaborate via the a2a bus to
produce a brand identity package: SVG logo banner, ASCII art version, and
a color palette + brand guidelines HTML page.

Designer: proposes a color palette and logo description.
Reviewer: critiques the design, suggests improvements.
Converter: generates SVG banner, ASCII art, and HTML palette gallery.

Usage:
  python3 examples/artifacts/brand-assets/build.py [--project NAME] [--cli opencode]

Requires a2a, a2a-spawn, ascii-image-converter, and an AI CLI.
"""

import os
import sys
import time
import json
import shlex
import subprocess
import argparse
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, send_task, check_agent_logs, SpawnManager  # noqa: E402

ARTIFACT = "brand-assets"

DESIGNER_INSTRUCTIONS = """You are a brand designer. Propose a complete brand identity:

1. Choose a brand name (related to "a2a" or "agent-to-agent").
2. Describe a color palette (4-6 hex colors with rationale).
3. Describe a simple logo concept (shape, typography, icon).

Send your proposal to the reviewer:
  a2a send reviewer "DESIGN: <your brand name>\nPalette: <hex colors>\nLogo: <description>" --from designer

Wait for the reviewer's feedback, then refine and send a final version.
Mark as FINAL_DESIGN when you're satisfied."""

REVIEWER_INSTRUCTIONS = """You are a brand reviewer. Examine the designer's proposal and:
1. Check color harmony (complementary, analogous, monochromatic).
2. Assess logo clarity and scalability.
3. Suggest 1-2 concrete improvements.

Send feedback:
  a2a send designer "REVIEW: <your critique>" --from reviewer

After the designer sends FINAL_DESIGN, tell the converter to proceed:
  a2a send converter "READY: <brand name> <palette> <logo concept>" --from reviewer"""

CONVERTER_INSTRUCTIONS = """You are a brand asset converter. Once the reviewer tells you to proceed:

1. Generate an SVG banner (800x200) with the brand name and logo.
2. Generate an ASCII art version (60x20) of the logo.
3. Generate an HTML palette gallery page.

Use shell commands to create files. The output directory is enforced:
  mkdir -p /tmp/brand-output
  cat > /tmp/brand-output/banner.svg << 'SVGEOF'
  ...
  SVGEOF
  cat > /tmp/brand-output/palette.html << 'HTMLEOF'
  ...
  HTMLEOF
  echo "ASCII logo:" > /tmp/brand-output/logo.txt
  echo "...your ascii..." >> /tmp/brand-output/logo.txt

When done, broadcast the paths and content:
  a2a send all "ASSETS_DONE\nBANNER_SVG: <path>\nPALETTE_HTML: <path>\nLOGO_TXT: <path>" --from converter"""


def generate_fallback_svg(brand_name="A2A-Brand", palette=None):
    """Generate a fallback SVG banner."""
    colors = palette or ["#6366F1", "#8B5CF6", "#EC4899", "#F59E0B", "#10B981"]
    name = brand_name or "A2A"
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 200" width="800" height="200">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{colors[0]}"/>
      <stop offset="50%" style="stop-color:{colors[1]}"/>
      <stop offset="100%" style="stop-color:{colors[2]}"/>
    </linearGradient>
  </defs>
  <rect width="800" height="200" fill="url(#bg)" rx="12"/>
  <circle cx="200" cy="100" r="50" fill="{colors[3]}" opacity="0.3"/>
  <circle cx="600" cy="100" r="50" fill="{colors[4]}" opacity="0.3"/>
  <text x="400" y="110" font-family="Arial,Helvetica,sans-serif" font-size="64"
        font-weight="bold" fill="white" text-anchor="middle" dominant-baseline="middle">{name}</text>
  <text x="400" y="155" font-family="Arial,Helvetica,sans-serif" font-size="16"
        fill="white" opacity="0.8" text-anchor="middle">Agent-to-Agent Messaging</text>
</svg>'''
    return svg


def generate_palette_html(brand_name="A2A-Brand", palette=None):
    """Generate an HTML color palette page."""
    colors = palette or ["#6366F1", "#8B5CF6", "#EC4899", "#F59E0B", "#10B981"]
    swatches = "".join(
        f'<div class="swatch" style="background:{c}"><span class="hex">{c}</span></div>'
        for c in colors
    )
    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{brand_name} — Color Palette</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #1a1a2e; color: #eee; padding: 2rem; }}
  h1 {{ color: white; }}
  .palette {{ display: flex; gap: 1rem; flex-wrap: wrap; margin: 2rem 0; }}
  .swatch {{ width: 120px; height: 120px; border-radius: 12px; display: flex;
             align-items: flex-end; justify-content: center; padding: 8px; }}
  .hex {{ background: rgba(0,0,0,0.5); color: white; padding: 2px 8px; border-radius: 4px;
          font-size: 12px; font-family: monospace; }}
  .guidelines {{ background: #16213e; padding: 1.5rem; border-radius: 12px; line-height: 1.6; }}
</style></head><body>
<h1>🎨 {brand_name} — Brand Palette</h1>
<div class="palette">{swatches}</div>
<div class="guidelines">
  <h2>Brand Guidelines</h2>
  <p><strong>Primary:</strong> {colors[0]} — Main brand color for headers, buttons, primary elements.</p>
  <p><strong>Secondary:</strong> {colors[1]} — Accent color for highlights, hover states, secondary buttons.</p>
  <p><strong>Tertiary:</strong> {colors[2]} — Alert/notification color, emphasis.</p>
  <p><strong>Accent 1:</strong> {colors[3]} — Call-to-action, special offers, badges.</p>
  <p><strong>Accent 2:</strong> {colors[4]} — Success states, confirmations, positive metrics.</p>
  <hr>
  <p>Typography: System UI (Inter, system-ui). Heavy weight for headlines, regular for body.</p>
  <p>Logo: Abstract interlocking circles representing agent-to-agent communication.</p>
  <p>Generated: {time.strftime('%Y-%m-%d %H:%M UTC')}</p>
</div>
</body></html>'''
    return html


def generate_ascii_logo():
    """Generate fallback ASCII art logo."""
    return r"""   ╔═══════════════════════════════════╗
   ║          ╔═══╗     ╔═══╗          ║
   ║          ║ A ║─────║ A ║          ║
   ║          ╚═══╝     ╚═══╝          ║
   ║             Agent-to-Agent         ║
   ║         ◀─── messaging ───▶         ║
   ║          ╔═══╗     ╔═══╗          ║
   ║          ║ 2 ║─────║ 2 ║          ║
   ║          ╚═══╝     ╚═══╝          ║
   ╚═══════════════════════════════════╝"""


def main():
    parser = argparse.ArgumentParser(description="Build brand assets via agent collaboration")
    parser.add_argument("--project", default=None)
    parser.add_argument("--cli", default="opencode", choices=["claude", "opencode", "pi"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=360)
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    output_dir = script_dir / "output" / "brand"
    output_dir.mkdir(parents=True, exist_ok=True)

    project = args.project or os.environ.get("A2A_PROJECT") or f"artifact-{ARTIFACT}"
    os.environ["A2A_PROJECT"] = project

    a2a_bin = find_a2a(str(script_dir))
    spawn_bin = find_spawn(str(script_dir))
    if not a2a_bin or not spawn_bin:
        print("ERROR: a2a or a2a-spawn not found.", file=sys.stderr)
        sys.exit(1)

    print(f"[{ARTIFACT}] a2a: {a2a_bin}, spawn: {spawn_bin}, project: {project}, cli: {args.cli}")

    # Init bus
    run_a2a("init", a2a_bin, project)
    run_a2a("clear --yes", a2a_bin, project)
    run_a2a("register collector --role build-script --cli python", a2a_bin, project)

    agents = [
        {"id": "designer", "role": "brand designer", "task": DESIGNER_INSTRUCTIONS},
        {"id": "reviewer", "role": "brand reviewer", "task": REVIEWER_INSTRUCTIONS},
        {"id": "converter", "role": "asset converter", "task": CONVERTER_INSTRUCTIONS},
    ]
    agent_ids = [ag["id"] for ag in agents]
    for ag in agents:
        run_a2a(f'register {ag["id"]} --role "{ag["role"]}" --cli {args.cli}', a2a_bin, project)

    # Spawn agents
    mgr = SpawnManager()
    spawned_ok = True
    for ag in agents:
        kit = make_kit(ag["id"], ag["role"], ag["task"], project)
        with tempfile.NamedTemporaryFile(mode="w", prefix=f"a2a-{project}-{ag['id']}-", suffix=".kit", delete=False) as f:
            f.write(kit)
            kit_path = f.name
        pid = spawn_agent(spawn_bin, args.cli, ag["id"], kit_path, project=project, model=args.model, a2a_bin=a2a_bin)
        if pid:
            mgr.add(pid)
        else:
            spawned_ok = False
        os.unlink(kit_path)

    time.sleep(2)

    api_errors = check_agent_logs(agent_ids, ARTIFACT)
    all_agents_failed = not spawned_ok or api_errors
    agent_output = None

    if not all_agents_failed:
        for ag in agents:
            send_task(a2a_bin, project, ag["id"], f"Your task: {ag['task']}")
            print(f"[{ARTIFACT}] → sent task to {ag['id']}")

        print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            msgs = run_a2a_json("recv --as collector --wait 30", a2a_bin, project)
            for msg in msgs if isinstance(msgs, list) else []:
                sender = msg.get("sender", "")
                body = msg.get("body", "")
                if sender == "converter" and "ASSETS_DONE" in body:
                    agent_output = body
                    print(f"[{ARTIFACT}] Received agent-produced output ({len(body)} chars)")
                    break
            if agent_output:
                break

    # --- Write output: always produce something ---
    if agent_output:
        lines = agent_output.splitlines()
        svg_content = None
        ascii_content = None
        html_content = None
        for line in lines:
            if line.startswith("BANNER_SVG:"):
                path = line.split(":", 1)[1].strip()
                try:
                    svg_content = Path(path).read_text()
                except (OSError, IOError):
                    pass
            elif line.startswith("PALETTE_HTML:"):
                path = line.split(":", 1)[1].strip()
                try:
                    html_content = Path(path).read_text()
                except (OSError, IOError):
                    pass
            elif line.startswith("LOGO_TXT:"):
                path = line.split(":", 1)[1].strip()
                try:
                    ascii_content = Path(path).read_text()
                except (OSError, IOError):
                    pass

        if svg_content:
            (output_dir / "banner.svg").write_text(svg_content)
            print(f"[{ARTIFACT}] Wrote output/brand/banner.svg (agent-produced)")
        if html_content:
            (output_dir / "palette.html").write_text(html_content)
            print(f"[{ARTIFACT}] Wrote output/brand/palette.html (agent-produced)")
        if ascii_content:
            (output_dir / "logo.txt").write_text(ascii_content)
            print(f"[{ARTIFACT}] Wrote output/brand/logo.txt (agent-produced)")

    if not (output_dir / "banner.svg").exists():
        svg = generate_fallback_svg()
        (output_dir / "banner.svg").write_text(svg)
        print(f"[{ARTIFACT}] Wrote output/brand/banner.svg (fallback, {len(svg)} chars)")

    if not (output_dir / "palette.html").exists():
        html = generate_palette_html()
        (output_dir / "palette.html").write_text(html)
        print(f"[{ARTIFACT}] Wrote output/brand/palette.html (fallback, {len(html)} chars)")

    if not (output_dir / "logo.txt").exists():
        ascii_art = generate_ascii_logo()
        (output_dir / "logo.txt").write_text(ascii_art)
        print(f"[{ARTIFACT}] Wrote output/brand/logo.txt (fallback, {len(ascii_art)} chars)")

    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/brand/bus-state.txt")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
