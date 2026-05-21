#!/usr/bin/env python3
import json
import argparse
import sys
import os

TASKY_DIR = os.path.expanduser("~/.tasky")
TASKS_FILE = os.path.join(TASKY_DIR, "tasks.json")

def load_data() -> dict:
    try:
        with open(TASKS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"next_id": 1, "tasks": {}}

def save_data(data: dict) -> None:
    os.makedirs(TASKY_DIR, exist_ok=True)
    with open(TASKS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def cmd_add(tasks: list[str]) -> None:
    if not tasks:
        print("Usage: tasky add <task description>")
        sys.exit(1)
    data = load_data()
    text = " ".join(tasks)
    task_id = str(data["next_id"])
    data["tasks"][task_id] = {"id": data["next_id"], "text": text, "done": False}
    data["next_id"] += 1
    save_data(data)
    print(f"Added task {task_id}: {text}")

def cmd_list() -> None:
    data = load_data()
    if not data["tasks"]:
        print("No tasks.")
        return
    for tid in sorted(data["tasks"], key=int):
        t = data["tasks"][tid]
        status = "[x]" if t["done"] else "[ ]"
        print(f"{status} {t['id']}. {t['text']}")

def cmd_done(task_id: str) -> None:
    data = load_data()
    if task_id not in data["tasks"]:
        print(f"Error: task {task_id} not found.")
        sys.exit(1)
    data["tasks"][task_id]["done"] = True
    save_data(data)
    print(f"Task {task_id} marked as done.")

def cmd_clear() -> None:
    save_data({"next_id": 1, "tasks": {}})
    print("All tasks cleared.")

def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal JSON task tracker")
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("task", nargs="*", help="Task description")

    subparsers.add_parser("list", help="List all tasks")

    done_parser = subparsers.add_parser("done", help="Mark a task as done")
    done_parser.add_argument("task_id", help="Task ID to mark as done")

    subparsers.add_parser("clear", help="Clear all tasks")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args.task)
    elif args.command == "list":
        cmd_list()
    elif args.command == "done":
        cmd_done(args.task_id)
    elif args.command == "clear":
        cmd_clear()
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()