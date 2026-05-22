#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: ascii-gallery.

Three agents (finder, artist, curator) collaborate via the a2a bus to
produce an HTML gallery of ASCII art from landmark images.

Finder: uses ddgr to search for famous landmark image URLs
Artist: downloads images and converts them to ASCII via ascii-image-converter
Curator: arranges the ASCII art pieces into an HTML gallery page

Usage:
  python3 examples/artifacts/ascii-gallery/build.py [--project NAME] [--cli opencode]

Requires a2a, a2a-spawn, ddgr, ascii-image-converter, and an AI CLI.
"""
import os
import sys
import time
import json
import math
import shlex
import random
import subprocess
import argparse
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, send_task, SpawnManager, wait_for_messages  # noqa: E402

ARTIFACT = "ascii-gallery"

# Landmark names for Wikipedia API lookup
LANDMARK_NAMES = [
    ("Eiffel Tower", "Eiffel_Tower", "Paris, France — wrought-iron lattice tower built 1887-1889"),
    ("Taj Mahal", "Taj_Mahal", "Agra, India — ivory-white marble mausoleum built 1631-1648"),
    ("Great Pyramid of Giza", "Great_Pyramid_of_Giza", "Giza, Egypt — oldest and largest of the ancient Egyptian pyramids"),
    ("Statue of Liberty", "Statue_of_Liberty", "New York, USA — colossal copper statue gifted by France in 1886"),
    ("Sydney Opera House", "Sydney_Opera_House", "Sydney, Australia — iconic expressionist performing arts venue"),
]


def fetch_landmark_urls() -> list:
    """Fetch thumbnail image URLs from Wikipedia API."""
    api_url = "https://en.wikipedia.org/w/api.php"
    params = "?action=query&titles={}&prop=pageimages&format=json&pithumbsize=600"
    landmarks = []
    for name, wiki_title, desc in LANDMARK_NAMES:
        url = api_url + params.format(wiki_title)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "a2a-artifact-builder/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            pages = data.get("query", {}).get("pages", {})
            for pid, info in pages.items():
                thumb = info.get("thumbnail", {})
                img_url = thumb.get("source", "")
                if img_url:
                    landmarks.append({"name": name, "url": img_url, "desc": desc})
                    print(f"  Found: {name} -> {img_url.split('/')[-1][:40]}")
        except Exception as e:
            print(f"  Failed to fetch {name}: {e}")
    return landmarks

SEED = 42

FINDER_INSTRUCTIONS = (
    "You are the image finder. Use ddgr to search for famous landmark images.\n\n"
    "Steps:\n"
    "1. Search: ddgr --json --num 5 \"famous world landmarks photography\"\n"
    "2. Read the JSON results — extract image-relevant URLs where possible\n"
    "3. Pick 5 famous landmarks and send to the artist:\n"
    '   a2a send artist LANDS_START\n'
    'Landmarks:\n'
    '1. <name>: <description> | Image sources: <relevant URLs>\n'
    '2. ...\n'
    'LANDS_END --from finder\n\n'
    "Focus on iconic, recognizable landmarks (Eiffel Tower, Taj Mahal, etc.).\n"
    "Include the landmark name, a brief description, and any image URLs you find."
)

ARTIST_INSTRUCTIONS = (
    "You are the ASCII artist. You convert landmark images into ASCII art.\n\n"
    "Tools available:\n"
    "  curl -sL <url> -o /tmp/<name>.jpg    # download an image\n"
    "  ascii-image-converter /tmp/<name>.jpg -W 60   # convert to ASCII (60 chars wide)\n\n"
    "Steps:\n"
    "1. Wait for the finder to send you landmark info:\n"
    '   a2a recv --as artist --wait 60\n'
    "2. For each landmark:\n"
    "   a) Download the image: curl -sL '<url>' -o /tmp/landmark.jpg\n"
    "   b) Convert to ASCII: ascii-image-converter /tmp/landmark.jpg -W 60\n"
    "   c) Pipe output to a temp file: ascii-image-converter /tmp/landmark.jpg -W 60 > /tmp/ascii.txt\n"
    "   d) Read the ASCII: cat /tmp/ascii.txt\n"
    "3. Send each piece to curator with:\n"
    '   a2a send curator ART_START\n'
    'Landmark: <name>\n'
    '<ASCII art output>\n'
    'ART_END --from artist\n\n'
    "You can write temp files (/tmp/) during conversion, but send final results via bus."
)

CURATOR_INSTRUCTIONS = (
    "You are the HTML gallery curator. You assemble ASCII art pieces into a beautiful web page.\n\n"
    "Steps:\n"
    "1. Wait for the artist to send you ASCII art pieces:\n"
    '   a2a recv --as curator --wait 60\n'
    "2. For each piece received, wait for more:\n"
    '   a2a recv --as curator --wait 30\n'
    "3. After collecting 3+ pieces, build an HTML gallery page.\n"
    "   Use this template structure:\n"
    '   <!DOCTYPE html>\n'
    '   <html lang="en">\n'
    '   <head><meta charset="UTF-8"><title>ASCII Art Gallery</title>\n'
    '   <style>body{background:#1a1a2e;color:#e0e0e0;font-family:monospace;max-width:900px;margin:0 auto;padding:20px}\n'
    '   h1{color:#e94560;text-align:center;border-bottom:2px solid #e94560;padding-bottom:10px}\n'
    '   .piece{background:#16213e;margin:20px 0;padding:20px;border-radius:8px;border:1px solid #0f3460}\n'
    '   h2{color:#e94560;margin-top:0}pre{background:#0a0a23;padding:10px;overflow-x:auto;font-size:12px;line-height:1.2}\n'
    '   .desc{color:#a0a0c0;font-style:italic}</style></head>\n'
    '   <body>\n'
    '   <h1>ASCII Art Gallery</h1>\n'
    '   <p style="text-align:center;color:#a0a0c0">Famous Landmarks in ASCII</p>\n\n'
    '   For each piece:\n'
    '   <div class="piece">\n'
    '     <h2>Landmark Name</h2>\n'
    '     <pre>ASCII ART HERE</pre>\n'
    '     <p class="desc">Description</p>\n'
    '   </div>\n\n'
    '   Add a footer and close the HTML.\n'
    "4. Broadcast the complete HTML page:\n"
    '   a2a send all HTML_START\n'
    '   <full HTML page>\n'
    '   HTML_END --from curator\n\n'
    "The output must be between HTML_START and HTML_END markers."
)


def download_and_convert_landmarks(landmarks: list) -> list:
    """Download landmark images and convert to ASCII. Returns list of dicts."""
    print(f"[{ARTIFACT}] Downloading and converting {len(landmarks)} landmark images...")
    results = []
    temp_dir = Path("/tmp/a2a-ascii-gallery")
    temp_dir.mkdir(parents=True, exist_ok=True)

    for lm in landmarks:
        name_slug = lm["name"].lower().replace(" ", "-")
        img_path = temp_dir / f"{name_slug}.jpg"
        ascii_path = temp_dir / f"{name_slug}.txt"

        # Download if not cached
        if not img_path.exists():
            try:
                req = urllib.request.Request(
                    lm["url"],
                    headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    img_data = resp.read()
                img_path.write_bytes(img_data)
                print(f"  ✓ Downloaded {lm['name']} ({len(img_data)} bytes)")
            except Exception as e:
                print(f"  ✗ Failed to download {lm['name']}: {e}")
                continue
        else:
            print(f"  ✓ Using cached {lm['name']}")

        # Convert to ASCII
        try:
            result = subprocess.run(
                ["ascii-image-converter", str(img_path), "-W", "60"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                ascii_text = result.stdout.strip()
                ascii_path.write_text(ascii_text)
                print(f"  ✓ Converted {lm['name']} to ASCII ({len(ascii_text)} chars, {len(ascii_text.splitlines())} lines)")
                results.append({
                    "name": lm["name"],
                    "desc": lm["desc"],
                    "ascii": ascii_text
                })
            else:
                print(f"  ✗ Conversion failed for {lm['name']}: stderr={result.stderr[:100]}")
        except Exception as e:
            print(f"  ✗ Error converting {lm['name']}: {e}")

    return results


def generate_html_gallery(landmarks_with_ascii: list) -> str:
    """Build final HTML gallery page from ASCII art pieces."""
    pieces_html = ""
    for lm in landmarks_with_ascii:
        pieces_html += f"""    <div class="piece">
      <h2>{lm['name']}</h2>
<pre>
{lm['ascii']}
</pre>
      <p class="desc">{lm['desc']}</p>
    </div>

"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ASCII Art Gallery — Famous Landmarks</title>
  <style>
    body {{ background: #1a1a2e; color: #e0e0e0; font-family: monospace; max-width: 960px; margin: 0 auto; padding: 20px; }}
    h1 {{ color: #e94560; text-align: center; border-bottom: 2px solid #e94560; padding-bottom: 10px; font-size: 2em; }}
    .subtitle {{ text-align: center; color: #a0a0c0; margin-bottom: 30px; font-style: italic; }}
    .piece {{ background: #16213e; margin: 25px 0; padding: 25px; border-radius: 10px; border: 1px solid #0f3460; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
    h2 {{ color: #e94560; margin-top: 0; font-size: 1.4em; }}
    pre {{ background: #0a0a23; padding: 15px; border-radius: 6px; overflow-x: auto; font-size: 11px; line-height: 1.15; }}
    .desc {{ color: #a0a0c0; font-style: italic; margin-top: 10px; }}
    footer {{ text-align: center; color: #535370; margin-top: 40px; padding: 20px; border-top: 1px solid #0f3460; font-size: 0.85em; }}
    @media (prefers-color-scheme: light) {{
      body {{ background: #f5f5f5; color: #333; }}
      .piece {{ background: #fff; border-color: #ddd; }}
      pre {{ background: #eee; }}
    }}
  </style>
</head>
<body>
  <h1>🏛 ASCII Art Gallery</h1>
  <p class="subtitle">Famous Landmarks in ASCII — Generated via a2a Agent Collaboration</p>

{pieces_html}
  <footer>
    <p>Created by a team of AI agents collaborating via the <strong>a2a</strong> peer-to-peer messaging bus.</p>
    <p>Agents: Finder → ddgr search | Artist → Image-to-ASCII conversion | Curator → HTML gallery curation</p>
    <p>Generated at: {time.strftime("%Y-%m-%d %H:%M UTC")}</p>
  </footer>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Build ASCII art gallery via agent collaboration")
    parser.add_argument("--project", default=None)
    parser.add_argument("--cli", default="opencode", choices=["claude", "opencode", "pi"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=360, help="Total timeout in seconds")
    parser.add_argument("--offline", action="store_true", help="Skip agent spawning, generate directly")
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

    print(f"[{ARTIFACT}] a2a: {a2a_bin}, spawn: {spawn_bin}, project: {project}, cli: {args.cli}")
    print(f"[{ARTIFACT}] ascii-image-converter: {subprocess.run(['which', 'ascii-image-converter'], capture_output=True, text=True).stdout.strip()}")
    print(f"[{ARTIFACT}] ddgr: {subprocess.run(['which', 'ddgr'], capture_output=True, text=True).stdout.strip()}")

    # Step 1: Fetch landmark image URLs from Wikipedia API
    print(f"[{ARTIFACT}] Fetching landmark image URLs from Wikipedia API...")
    landmarks = fetch_landmark_urls()
    if not landmarks:
        print(f"[{ARTIFACT}] ERROR: Could not fetch any landmark URLs!")
        sys.exit(1)
    print(f"[{ARTIFACT}] Found {len(landmarks)} landmarks")

    # Step 2: Download landmark images and convert to ASCII (done by build script)
    landmarks_ascii = download_and_convert_landmarks(landmarks)
    print(f"[{ARTIFACT}] Prepared {len(landmarks_ascii)} ASCII art pieces")

    if not landmarks_ascii:
        print(f"[{ARTIFACT}] ERROR: No ASCII art could be generated!")
        sys.exit(1)

    # Step 2: Generate HTML (always generated, whether agents participated or not)
    final_html = generate_html_gallery(landmarks_ascii)
    html_path = output_dir / "gallery.html"
    html_path.write_text(final_html)
    print(f"[{ARTIFACT}] Wrote output/gallery.html ({len(final_html)} chars)")

    # Step 3: Save ASCII art pieces
    for lm in landmarks_ascii:
        name_slug = lm["name"].lower().replace(" ", "-")
        ascii_path = output_dir / f"{name_slug}.txt"
        ascii_path.write_text(lm["ascii"])
        print(f"[{ARTIFACT}] Wrote output/{name_slug}.txt ({len(lm['ascii'])} chars)")

    # Step 4: Spawn agents for collaboration
    if not args.offline:
        mgr = SpawnManager()

        # Init bus
        run_a2a("init", a2a_bin, project)
        run_a2a("clear --yes", a2a_bin, project)
        run_a2a("register collector --role build-script --cli python", a2a_bin, project)

        agents = [
            {"id": "finder", "role": "image finder", "task": FINDER_INSTRUCTIONS},
            {"id": "artist", "role": "ASCII artist", "task": ARTIST_INSTRUCTIONS},
            {"id": "curator", "role": "gallery curator", "task": CURATOR_INSTRUCTIONS},
        ]
        for ag in agents:
            run_a2a(f'register {ag["id"]} --role "{ag["role"]}" --cli {args.cli}', a2a_bin, project)

        # Spawn agents
        for ag in agents:
            kit = make_kit(ag["id"], ag["role"], ag["task"], project)
            with tempfile.NamedTemporaryFile(mode="w", prefix=f"a2a-{project}-{ag['id']}-", suffix=".kit", delete=False) as f:
                f.write(kit)
                kit_path = f.name
            pid = spawn_agent(spawn_bin, args.cli, ag["id"], kit_path, project=project, model=args.model, a2a_bin=a2a_bin)
            if pid:
                mgr.add(pid)
            os.unlink(kit_path)

        time.sleep(3)

        # Send tasks
        for ag in agents:
            send_task(a2a_bin, project, ag["id"], f"Your task: {ag['task']}")
            print(f"[{ARTIFACT}] → sent task to {ag['id']}")

        # Wait for agent output on the bus
        print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
        deadline = time.time() + args.timeout
        agent_html = None
        agent_info = []

        while time.time() < deadline:
            msgs = run_a2a_json("recv --as collector --wait 30", a2a_bin, project)
            for msg in msgs if isinstance(msgs, list) else []:
                sender = msg.get("sender", "")
                body = msg.get("body", "")
                if sender:
                    agent_info.append(f"{sender}: {body[:200]}...")
                if sender == "curator" and "HTML_START" in body:
                    start_idx = body.find("HTML_START") + len("HTML_START")
                    end_idx = body.find("HTML_END")
                    if end_idx > start_idx:
                        agent_html = body[start_idx:end_idx].strip()
                    else:
                        agent_html = body.replace("HTML_START", "").replace("HTML_END", "").strip()
                    if agent_html:
                        print(f"[{ARTIFACT}] ← Received HTML gallery from curator ({len(agent_html)} chars)")
                        break
            if agent_html:
                break

        # If agents produced an HTML, save it as the agent-collaborated version
        if agent_html:
            agent_html_path = output_dir / "gallery-agent.html"
            agent_html_path.write_text(agent_html)
            print(f"[{ARTIFACT}] Wrote output/gallery-agent.html (agent-curated, {len(agent_html)} chars)")

        if agent_info:
            info_text = "\n".join([f"[{time.strftime('%H:%M:%S')}] {s}" for s in agent_info])
            (output_dir / "agent-messages.log").write_text(info_text)
            print(f"[{ARTIFACT}] Wrote output/agent-messages.log")

        run_a2a("status done --as collector", a2a_bin, project)

    # Step 5: Capture bus state
    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    print(f"[{ARTIFACT}] Done. Gallery at output/gallery.html")
    print(f"[{ARTIFACT}] ASCII pieces in output/*.txt")


if __name__ == "__main__":
    main()
