#!/usr/bin/env python3
import argparse, json, sys, pathlib

TASKS_PATH = pathlib.Path.home() / ".tasky" / "tasks.json"

def load_tasks(path: str) -> list:
    p = pathlib.Path(path)
    if not p.exists():
        return []
    try:
        with open(p) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []

def save_tasks(path: str, tasks: list) -> None:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(tasks, f, indent=2)
        f.write("\n")

def add_task(tasks: list, description: str) -> dict:
    task_id = max((t["id"] for t in tasks), default=0) + 1
    task = {"id": task_id, "description": description, "done": False}
    tasks.append(task)
    save_tasks(str(TASKS_PATH), tasks)
    return task

def list_tasks(tasks: list) -> None:
    print(f"{'ID':<4} {'Description':<30} {'Done'}")
    print("-" * 44)
    for t in tasks:
        done = "yes" if t["done"] else "no"
        desc = t["description"][:30]
        print(f"{t['id']:<4} {desc:<30} {done}")

def done_task(tasks: list, task_id: int) -> dict | None:
    for t in tasks:
        if t["id"] == task_id:
            t["done"] = True
            save_tasks(str(TASKS_PATH), tasks)
            return t
    return None

def clear_tasks() -> list:
    save_tasks(str(TASKS_PATH), [])
    return []

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="tasky", description="Minimal task tracker.")
    sub = p.add_subparsers(dest="command", required=True)
    add_p = sub.add_parser("add", help="Add a new task")
    add_p.add_argument("description", help="Task description")
    done_p = sub.add_parser("done", help="Mark a task as done")
    done_p.add_argument("task_id", type=int, help="Task ID to mark done")
    sub.add_parser("list", help="List all tasks")
    sub.add_parser("clear", help="Clear all tasks")
    return p.parse_args(argv)

def main() -> None:
    args = parse_args(sys.argv[1:])
    if args.command == "clear":
        clear_tasks()
        print("All tasks cleared")
        return
    tasks = load_tasks(str(TASKS_PATH))
    if args.command == "add":
        t = add_task(tasks, args.description)
        print(f"Added task {t['id']}: {t['description']}")
    elif args.command == "list":
        list_tasks(tasks)
    elif args.command == "done":
        t = done_task(tasks, args.task_id)
        if t:
            print(f"Task {args.task_id} marked as done")
        else:
            print(f"Error: task {args.task_id} not found", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()