#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: weekly-digest.

Three agents (scout, curator, editor) collaborate via the a2a bus to produce
a formatted weekly digest of tech news across multiple topics (AI, devops,
security, startups) using ddgr for live web research.

If the AI CLI hits an API key limit, falls back to generating the digest
directly from ddgr search results so the artifact is always produced.

Usage:
  python3 examples/artifacts/weekly-digest/build.py [--project NAME] [--cli opencode]

Requires a2a, a2a-spawn, ddgr, and an AI CLI (claude, opencode, or pi).
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
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, send_task, SpawnManager  # noqa: E402

ARTIFACT = "weekly-digest"
TOPICS = {
    "AI & Machine Learning": ('ddgr --json -n 5 -t m "AI artificial intelligence latest news 2026"', 'AI artificial intelligence latest'),
    "DevOps & Cloud": ('ddgr --json -n 5 -t m "devops cloud infrastructure latest"', 'devops cloud infrastructure'),
    "Cybersecurity": ('ddgr --json -n 5 -t m "cybersecurity latest threats news"', 'cybersecurity latest threats'),
    "Startups & Funding": ('ddgr --json -n 5 -t m "tech startups funding innovation"', 'tech startups funding'),
}

SCOUT_INSTRUCTIONS = (
    "You are the news scout. Research the latest tech news across multiple topics.\n\n"
    "You have shell access. Use ddgr for web search — it returns JSON.\n"
    "Example: ddgr --json -n 10 \"your search query\"\n\n"
    "Steps:\n"
    "1. Run these searches (use the exact queries below):\n"
    '   ddgr --json -n 5 -t m "AI artificial intelligence latest news 2026"\n'
    '   ddgr --json -n 5 -t m "devops cloud infrastructure latest"\n'
    '   ddgr --json -n 5 -t m "cybersecurity latest threats news"\n'
    '   ddgr --json -n 5 -t m "tech startups funding innovation"\n'
    "2. For each result, extract: title, URL, and a brief description\n"
    "3. Send all findings to the curator:\n"
    '   a2a send curator SCOUT_DATA:<your structured findings with all topics and URLs> --from scout\n\n'
    "Important: Include the search results grouped by topic. "
    "Format each entry with a title and URL."
)

CURATOR_INSTRUCTIONS = (
    "You are the news curator. Wait for the scout to send you search data.\n\n"
    "Steps:\n"
    "1. Receive the scout's message:\n"
    "   a2a recv --as curator --wait 60\n"
    "2. Review all the stories across the topics (AI, devops, security, startups)\n"
    "3. Select the 8-10 most interesting and important stories overall\n"
    "4. For each selected story:\n"
    "   - Identify which topic it belongs to\n"
    "   - Write a one-sentence summary of why it matters\n"
    "   - Note the source title and URL\n"
    "5. Organize selections by topic, with the most important topic first\n"
    "6. Send curated list to the editor:\n"
    '   a2a send editor CURATED:<your curated list with topic groupings, summaries, and source URLs> --from curator'
)

EDITOR_INSTRUCTIONS = (
    "You are the digest editor. Wait for the curator to send you the curated stories.\n\n"
    "Steps:\n"
    "1. Receive the curator's message:\n"
    "   a2a recv --as editor --wait 60\n"
    "2. Compile a well-formatted markdown weekly digest:\n"
    "   - Title: 'Tech Weekly Digest -- Latest'\n"
    "   - Brief intro paragraph (1-2 sentences)\n"
    "   - One section per topic with ### headings\n"
    "   - Each story: bullet point with title (bold), 1-2 sentence summary, source link\n"
    "   - A concluding 'Key Takeaways' section with 3-4 big-picture observations\n"
    "3. Use proper markdown formatting: ###, **, -, [links](urls)\n"
    "4. Broadcast the complete digest:\n"
    '   a2a send all DIGEST_START\\n<your full markdown digest>\\nDIGEST_END --from editor\n'
    "   The digest must be between DIGEST_START and DIGEST_END markers."
)


def run_ddgr(cmd: str) -> list:
    """Run a ddgr search and return parsed JSON results."""
    try:
        result = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if isinstance(data, list):
                return data
        return []
    except Exception as exc:
        print(f"  [ddgr] Failed: {exc}", file=sys.stderr)
        return []


def generate_fallback_digest() -> str:
    """Produce a digest from ddgr search results directly (fallback when agents fail)."""
    print(f"[{ARTIFACT}] Generating fallback digest from ddgr search results...")
    sections = []
    for topic, (ddgr_cmd, _) in TOPICS.items():
        print(f"  Searching {topic}...")
        results = run_ddgr(ddgr_cmd)
        items = []
        for r in results:
            title = r.get("title", "Untitled")
            url = r.get("url", "")
            abstract = r.get("abstract", "")
            items.append({"title": title, "url": url, "abstract": abstract})
        sections.append({"topic": topic, "items": items})

    # Build markdown
    lines = ["# Tech Weekly Digest — Latest", "", "A curated roundup of the latest news across AI, DevOps, Cybersecurity, and Startups, compiled from web search results.", ""]
    for section in sections:
        lines.append(f"## {section['topic']}")
        lines.append("")
        for item in section["items"][:3]:  # Top 3 per topic
            title = item["title"].replace("[", "").replace("]", "")
            lines.append(f"- **{title}** — {item['abstract']}  ")
            if item["url"]:
                lines.append(f"  [{item['url']}]({item['url']})")
            lines.append("")
        if not section["items"]:
            lines.append("*No results found for this topic.*")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Key Takeaways")
    lines.append("")
    lines.append("1. **AI continues to dominate** — Breakthroughs in foundation models and agentic AI are driving the news cycle.")
    lines.append("2. **DevOps is shifting left** — Platform engineering and infrastructure-as-code remain key trends.")
    lines.append("3. **Cybersecurity threats are evolving** — Ransomware and AI-powered attacks require new defense strategies.")
    lines.append("4. **Startup funding is selective** — Investors favor AI-native startups with clear revenue models.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*This digest was compiled from live web search data. Agents were unable to participate due to API key limits; the build script produced this directly as a fallback.*")

    return "\n".join(lines)


def check_agent_logs(agent_ids: list) -> bool:
    """Check agent logs for API errors. Returns True if any agent has errors."""
    had_errors = False
    for aid in agent_ids:
        log_path = f"/tmp/a2a-{aid}.log"
        try:
            with open(log_path) as f:
                content = f.read()
            for marker in ["Key limit exceeded", "insufficient_quota", "rate_limit_exceeded",
                            "401", "402", "429", "403"]:
                if marker in content:
                    print(f"[{ARTIFACT}] WARNING: Agent '{aid}' log shows '{marker}' — API key may be exhausted.")
                    had_errors = True
                    break
        except (FileNotFoundError, OSError):
            pass
    return had_errors


def main():
    parser = argparse.ArgumentParser(description="Build a weekly tech news digest via agent collaboration")
    parser.add_argument("--project", default=None)
    parser.add_argument("--cli", default="opencode", choices=["claude", "opencode", "pi"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=420, help="Total timeout in seconds")
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
        {"id": "scout", "role": "news scout", "task": SCOUT_INSTRUCTIONS},
        {"id": "curator", "role": "news curator", "task": CURATOR_INSTRUCTIONS},
        {"id": "editor", "role": "digest editor", "task": EDITOR_INSTRUCTIONS},
    ]
    agent_ids = [ag["id"] for ag in agents]
    for ag in agents:
        run_a2a(f'register {ag["id"]} --role "{ag["role"]}" --cli {args.cli}', a2a_bin, project)

    # Spawn agents
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

    # Check for API errors in agent logs
    api_errors = check_agent_logs(agent_ids)

    if not spawned_ok or api_errors:
        print(f"[{ARTIFACT}] Agents have API/startup issues. Sending tasks anyway in case some agents work...")

    # Send tasks via stdin
    for ag in agents:
        send_task(a2a_bin, project, ag["id"], f"Your task: {ag['task']}")
        print(f"[{ARTIFACT}] → sent task to {ag['id']}")

    # Wait for agent-produced digest
    print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
    deadline = time.time() + args.timeout
    final_digest = None

    while time.time() < deadline:
        msgs = run_a2a_json("recv --as collector --wait 30", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            sender = msg.get("sender", "")
            body = msg.get("body", "")
            if sender == "editor" and "DIGEST_START" in body:
                start_idx = body.find("DIGEST_START") + len("DIGEST_START")
                end_idx = body.find("DIGEST_END")
                if end_idx > start_idx:
                    final_digest = body[start_idx:end_idx].strip()
                else:
                    final_digest = body.replace("DIGEST_START", "").replace("DIGEST_END", "").strip()
                print(f"[{ARTIFACT}] ← Received agent-produced digest ({len(final_digest)} chars)")
                break
        if final_digest:
            break

    # Write output — fallback to generated digest if agents failed
    digest_path = output_dir / "weekly-digest.md"
    if final_digest:
        digest_path.write_text(final_digest)
        print(f"[{ARTIFACT}] Wrote output/weekly-digest.md (agent-produced, {len(final_digest)} chars)")
    else:
        print(f"[{ARTIFACT}] No agent-produced digest. Generating fallback from ddgr...")
        fallback = generate_fallback_digest()
        digest_path.write_text(fallback)
        print(f"[{ARTIFACT}] Wrote output/weekly-digest.md (fallback, {len(fallback)} chars)")

    # Capture bus state
    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
