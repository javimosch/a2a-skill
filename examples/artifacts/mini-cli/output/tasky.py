#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

DATA_DIR = Path.home() / ".tasky"
DATA_FILE = DATA_DIR / "tasks.json"


def load_tasks():
    if not DATA_FILE.exists():
        return {"next_id": 1, "tasks": []}
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error: corrupt tasks file: {e}", file=sys.stderr)
        sys.exit(1)


def save_tasks(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def cmd_add(args):
    data = load_tasks()
    desc = " ".join(args)
    task = {"id": data["next_id"], "desc": desc, "done": False}
    data["tasks"].append(task)
    data["next_id"] += 1
    save_tasks(data)
    print(f"Added task #{task['id']}: {desc}")


def cmd_list():
    data = load_tasks()
    for t in data["tasks"]:
        status = "[x]" if t["done"] else "[ ]"
        print(f"#{t['id']} {status} {t['desc']}")


def cmd_done(args):
    if not args:
        print("Error: missing task id", file=sys.stderr)
        sys.exit(1)
    try:
        tid = int(args[0])
    except ValueError:
        print(f"Error: invalid task id: {args[0]}", file=sys.stderr)
        sys.exit(1)
    data = load_tasks()
    for t in data["tasks"]:
        if t["id"] == tid:
            if not t["done"]:
                t["done"] = True
                save_tasks(data)
            print(f"Done task #{tid}: {t['desc']}")
            return
    print(f"Error: task #{tid} not found", file=sys.stderr)
    sys.exit(1)


def cmd_clear():
    data = {"next_id": 1, "tasks": []}
    save_tasks(data)
    print("Cleared all tasks.")


def main():
    parser = argparse.ArgumentParser(prog="tasky", description="Simple task tracker")
    parser.add_argument("command", nargs="?", help="Command: add, list, done, clear")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for the command")
    args = parser.parse_args()

    if args.command is None:
        parser.print_usage(sys.stderr)
        sys.exit(2)

    cmds = {
        "add": cmd_add,
        "list": cmd_list,
        "done": cmd_done,
        "clear": cmd_clear,
    }

    if args.command not in cmds:
        print(f"Error: unknown command '{args.command}'", file=sys.stderr)
        parser.print_usage(sys.stderr)
        sys.exit(2)

    if args.command == "add":
        cmds[args.command](args.args)
    else:
        cmds[args.command](args.args)


if __name__ == "__main__":
    main()