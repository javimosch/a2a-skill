#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: quiz-generator.

Three agents (researcher, checker, formatter) collaborate via the a2a bus to
produce a self-contained HTML quiz page on a topic of the researcher's choice.

Usage:
  python3 examples/artifacts/quiz-generator/build.py [--project NAME] [--cli opencode]

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

ARTIFACT = "quiz-generator"
PROMPT_RESEARCHER = (
    "You are the topic researcher. Choose an interesting, educational topic "
    "(e.g., space exploration, world history, biology, or technology). "
    "Create exactly 5 multiple-choice quiz questions on that topic. "
    "Each question must have 4 options (A, B, C, D) with exactly one correct answer. "
    "Send your quiz to the checker in this structured format:\n"
    "TOPIC: <your topic>\n"
    "Q1: <question>\n"
    "A) <option>  B) <option>  C) <option>  D) <option>\n"
    "ANSWER: <letter>\n"
    "...repeat for Q2-Q5..."
)
PROMPT_CHECKER = (
    "You are the answer checker. Wait for the researcher to send you a quiz. "
    "Verify each answer is correct — apply common knowledge or reason about each question. "
    "If all answers are correct, send the COMPLETE VERIFIED quiz to the formatter "
    "with the prefix 'VERIFIED_QUIZ:' followed by the full quiz in the same structured format. "
    "If any answer is wrong, report the error to the researcher and ask for a fix. "
    "After at most one correction round, either approve or send an error message to the formatter."
)
PROMPT_FORMATTER = (
    "You are the HTML formatter. Wait for the checker to send you a verified quiz "
    "with prefix 'VERIFIED_QUIZ:'. Once received, create a single self-contained HTML page that: \n"
    "1. Shows the topic as a heading\n"
    "2. Renders each question with clickable options (radio buttons or buttons) \n"
    "3. Reveals the correct answer when the user clicks 'Check Answers'\n"
    "4. Uses a clean, modern design with inline CSS\n"
    "5. Is valid HTML5 with <!DOCTYPE html>\n"
    "6. Has JavaScript for interactivity — highlight correct/green, wrong/red\n\n"
    "Broadcast the final HTML to 'all' starting directly with <!DOCTYPE html> (no preamble)."
)


def main():
    parser = argparse.ArgumentParser(description="Build interactive quiz page via agent collaboration")
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

    # Init bus
    run_a2a("init", a2a_bin, project)
    run_a2a("clear --yes", a2a_bin, project)
    run_a2a("register collector --role build-script --cli python", a2a_bin, project)

    agents = [
        {"id": "researcher", "role": "topic researcher", "task": PROMPT_RESEARCHER},
        {"id": "checker", "role": "answer checker", "task": PROMPT_CHECKER},
        {"id": "formatter", "role": "html formatter", "task": PROMPT_FORMATTER},
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

    # Collect final HTML from the formatter via bus
    print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to 240s)...")
    deadline = time.time() + 240
    final_html = None

    while time.time() < deadline:
        msgs = run_a2a_json(f"recv --as collector --wait 20", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            sender = msg.get("sender", "")
            body = msg.get("body", "")
            # Formatter broadcasts the final HTML
            if sender == "formatter" and ("<html" in body.lower() or "<!DOCTYPE" in body):
                lowered = body.lower()
                doc_start = lowered.find("<!doctype")
                if doc_start == -1:
                    doc_start = lowered.find("<html")
                if doc_start > 0:
                    body = body[doc_start:]
                elif doc_start == -1:
                    # Try finding <!DOCTYPE or <html anywhere
                    doc_start = lowered.find("<!doctype html")
                    if doc_start >= 0:
                        body = body[doc_start:]
                final_html = body
                print(f"[{ARTIFACT}] ← Received final HTML from {sender} ({len(body)} chars)")
                break

            # Also catch VERIFIED_QUIZ: prefixed messages (in case checker broadcasts)
            if "VERIFIED_QUIZ:" in body and sender == "checker":
                print(f"[{ARTIFACT}] ← Verified quiz from checker → formatter should be working on it")

        if final_html:
            break

    # Write output
    if final_html:
        (output_dir / "index.html").write_text(final_html)
        print(f"[{ARTIFACT}] Wrote output/index.html ({len(final_html)} chars)")
    else:
        print(f"[{ARTIFACT}] WARNING: No final HTML received. Dumping bus state...")
        print(run_a2a("peek --limit 40", a2a_bin, project))

    # Capture bus state for README
    print(f"\n=== Bus state at end ===")
    print(run_a2a("list", a2a_bin, project))
    peek_output = run_a2a("peek --limit 20", a2a_bin, project)
    print(peek_output)

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
