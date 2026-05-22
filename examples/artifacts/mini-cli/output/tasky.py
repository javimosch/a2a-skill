#!/usr/bin/env python3
"""tasky — minimal JSON-backed task tracker."""
import argparse, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path.home() / ".tasky"
DATA_FILE = DATA_DIR / "tasks.json"

def load_tasks():
    if not DATA_FILE.exists():
        return {"next_id": 1, "tasks": []}
    with open(DATA_FILE) as f:
        return json.load(f)

def save_tasks(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

def cmd_add(description):
    if not description or not description.strip():
        print("Error: task description cannot be empty", file=sys.stderr)
        sys.exit(1)
    data = load_tasks()
    task = {"id": data["next_id"], "description": description.strip(),
            "done": False, "created_at": datetime.now(timezone.utc).isoformat()}
    tid = data["next_id"]
    data["tasks"].append(task)
    data["next_id"] += 1
    save_tasks(data)
    print(f"Added task {tid}: {description.strip()}")

def cmd_list():
    data = load_tasks()
    if not data["tasks"]:
        print("No tasks")
        return
    for t in data["tasks"]:
        status = "done" if t["done"] else "pending"
        print(f"[{t['id']}] {t['description']} ({status})")

def cmd_done(tid_str):
    try:
        tid = int(tid_str)
    except (ValueError, TypeError):
        print("Error: task id must be an integer", file=sys.stderr)
        sys.exit(1)
    data = load_tasks()
    for t in data["tasks"]:
        if t["id"] == tid:
            t["done"] = True
            save_tasks(data)
            print(f"Task {tid} marked as done")
            return
    print(f"Error: task {tid} not found", file=sys.stderr)
    sys.exit(1)

def cmd_clear():
    data = load_tasks()
    count = len(data["tasks"])
    data["tasks"] = []
    data["next_id"] = 1
    save_tasks(data)
    print(f"Cleared {count} tasks")

def main():
    parser = argparse.ArgumentParser(description="tasky — JSON-backed task tracker")
    parser.add_argument("command", choices=["add", "list", "done", "clear"],
                        help="command to execute")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="command arguments")
    parsed = parser.parse_args()
    if parsed.command == "add":
        if not parsed.args:
            print("Error: task description required", file=sys.stderr)
            sys.exit(1)
        cmd_add(" ".join(parsed.args))
    elif parsed.command == "list":
        cmd_list()
    elif parsed.command == "done":
        if not parsed.args:
            print("Error: task id required", file=sys.stderr)
            sys.exit(1)
        cmd_done(parsed.args[0])
    elif parsed.command == "clear":
        cmd_clear()

if __name__ == "__main__":
    main()