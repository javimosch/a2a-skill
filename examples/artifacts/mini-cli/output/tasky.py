#!/usr/bin/env python3
"""tasky - A single-file Python CLI task tracker."""

import json
import os
import sys
import argparse
import shutil
from pathlib import Path

DATA_DIR = Path.home() / ".tasky"
DATA_FILE = DATA_DIR / "tasks.json"


def load_tasks() -> dict:
    """Load and return the tasks dict from JSON file."""
    if not DATA_FILE.exists():
        return {"next_id": 1, "tasks": []}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        print("Warning: corrupted data file, resetting.", file=sys.stderr)
        return {"next_id": 1, "tasks": []}


def save_tasks(data: dict) -> None:
    """Write the tasks dict to JSON file (pretty-printed, indent=2)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")


def cmd_add(args: argparse.Namespace) -> None:
    """Handle `tasky add <task>`."""
    description = " ".join(args.task)
    data = load_tasks()
    task_id = data["next_id"]
    data["tasks"].append({"id": task_id, "description": description, "done": False})
    data["next_id"] = task_id + 1
    save_tasks(data)
    print(f"Added task {task_id}: {description}")


def cmd_list(args: argparse.Namespace) -> None:
    """Handle `tasky list`."""
    data = load_tasks()
    if not data["tasks"]:
        print("No tasks.")
        return
    for task in data["tasks"]:
        status = "[X]" if task["done"] else "[ ]"
        print(f"{task['id']}. {status} {task['description']}")


def cmd_done(args: argparse.Namespace) -> None:
    """Handle `tasky done <id>`."""
    data = load_tasks()
    for task in data["tasks"]:
        if task["id"] == args.id:
            task["done"] = True
            save_tasks(data)
            print(f"Task {args.id} marked as done.")
            return
    print(f"Error: no task with id {args.id}")
    sys.exit(1)


def cmd_clear(args: argparse.Namespace) -> None:
    """Handle `tasky clear`. Prompts confirm unless --force is given."""
    if not args.force:
        print("Clear all tasks? [y/N] ", end="", file=sys.stderr)
        answer = sys.stdin.readline().strip().lower()
        if answer not in ("y", "yes"):
            return
    save_tasks({"next_id": 1, "tasks": []})
    print("All tasks cleared.")


def build_parser() -> argparse.ArgumentParser:
    """Build and return the ArgumentParser with subcommands."""
    parser = argparse.ArgumentParser(prog="tasky")
    subparsers = parser.add_subparsers(title="Commands", dest="command")

    # add
    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("task", nargs="+", help="Task description")

    # list
    subparsers.add_parser("list", help="List all tasks")

    # done
    done_parser = subparsers.add_parser("done", help="Mark a task as done")
    done_parser.add_argument("id", type=int, help="Task ID")

    # clear
    clear_parser = subparsers.add_parser("clear", help="Clear all tasks")
    clear_parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    return parser


def main() -> None:
    """Entry point: parse args, dispatch to cmd_* function."""
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "add":
        cmd_add(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "done":
        cmd_done(args)
    elif args.command == "clear":
        cmd_clear(args)
    else:
        parser.print_usage()
        print(f"{parser.prog}: error: missing command", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()