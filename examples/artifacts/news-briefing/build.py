#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: news-briefing.

Two agents (curator, narrator) collaborate via the a2a bus to produce a
markdown news briefing with top tech stories from live web search.

Usage:
  python3 examples/artifacts/news-briefing/build.py [--project NAME] [--cli opencode]

Requires a2a, a2a-spawn, ddgr, and an AI CLI (claude, opencode, or pi).
"""
import os
import sys
import time
import argparse
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, send_task, SpawnManager  # noqa: E402

ARTIFACT = "news-briefing"


CURATOR_INSTRUCTIONS = (
    "You are the news curator. Search the web for the latest technology news.\n\n"
    "You have shell access. Use ddgr for web search — it returns JSON.\n\n"
    "Steps:\n"
    "1. Search for tech news using multiple ddgr queries:\n"
    '   ddgr --json --num 7 "technology news today 2026"\n'
    '   ddgr --json --num 5 "AI industry news 2026"\n'
    '   ddgr --json --num 5 "open source news 2026"\n'
    "2. Read the JSON output carefully — pick the top 5-7 most interesting stories\n"
    "3. For each story, extract: headline, source URL, and a 1-2 sentence summary\n"
    "4. Send the curated stories to the narrator:\n"
    '   a2a send narrator \'STORIES: <your curated stories with headlines, URLs, summaries>\' --from curator'
)

NARRATOR_INSTRUCTIONS = (
    "You are the news narrator. Wait for the curator to send you stories.\n\n"
    "Steps:\n"
    "1. Receive the curator's message:\n"
    "   a2a recv --as narrator --wait 60\n"
    "2. Compile a well-formatted markdown news briefing with:\n"
    '   - Title: "Tech News Briefing — <today\'s date>"\n'
    "   - Opening paragraph with the date and a summary of the day's themes\n"
    "   - Each story as a subsection with:\n"
    "     - ## Headline linked to source\n"
    "     - 2-3 sentence summary\n"
    "     - Key takeaway\n"
    "   - A 'Trending Themes' section at the end connecting the stories\n"
    "3. Include source URLs as reference links\n"
    "4. Broadcast the complete briefing:\n"
    '   a2a send all \'BRIEFING_START\\n<your full markdown briefing>\\nBRIEFING_END\' --from narrator'
)


def main():
    parser = argparse.ArgumentParser(description="Build a news briefing via agent collaboration")
    parser.add_argument("--project", default=None)
    parser.add_argument("--cli", default="opencode", choices=["claude", "opencode", "pi"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=300, help="Total timeout in seconds")
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

    # Init bus
    run_a2a("init", a2a_bin, project)
    run_a2a("clear --yes", a2a_bin, project)
    run_a2a("register collector --role build-script --cli python", a2a_bin, project)

    agents = [
        {"id": "curator", "role": "news curator", "task": CURATOR_INSTRUCTIONS},
        {"id": "narrator", "role": "news narrator", "task": NARRATOR_INSTRUCTIONS},
    ]
    for ag in agents:
        run_a2a(f'register {ag["id"]} --role "{ag["role"]}" --cli {args.cli}', a2a_bin, project)

    # Spawn agents
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

    # Send tasks via stdin to avoid shell quoting issues
    for ag in agents:
        send_task(a2a_bin, project, ag["id"], f"Your task: {ag['task']}")
        print(f"[{ARTIFACT}] → sent task to {ag['id']}")

    # Wait for the narrator's briefing broadcast
    print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
    deadline = time.time() + args.timeout
    final_briefing = None

    while time.time() < deadline:
        msgs = run_a2a_json(f"recv --as collector --wait 30", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            sender = msg.get("sender", "")
            body = msg.get("body", "")
            if sender == "narrator" and "BRIEFING_START" in body:
                start_idx = body.find("BRIEFING_START") + len("BRIEFING_START")
                end_idx = body.find("BRIEFING_END")
                if end_idx > start_idx:
                    final_briefing = body[start_idx:end_idx].strip()
                else:
                    final_briefing = body.replace("BRIEFING_START", "").replace("BRIEFING_END", "").strip()
                print(f"[{ARTIFACT}] ← Received briefing from narrator ({len(final_briefing)} chars)")
                break
        if final_briefing:
            break

    # Write output
    briefing_path = output_dir / "briefing.md"
    if final_briefing:
        briefing_path.write_text(final_briefing)
        print(f"[{ARTIFACT}] Wrote output/briefing.md ({len(final_briefing)} chars)")
    else:
        print(f"[{ARTIFACT}] WARNING: No briefing received. Writing bus state...")
        peek = run_a2a("peek --limit 40", a2a_bin, project)
        briefing_path.write_text(f"# News Briefing — FAILED\n\nNo briefing was produced within the timeout.\n\n## Bus State\n\n```\n{peek}\n```\n")

    # Capture bus state
    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
