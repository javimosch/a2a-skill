import json
import argparse
import sys
from pathlib import Path
from datetime import datetime


TASKS_FILE = Path.home() / ".tasky" / "tasks.json"


def load_tasks() -> list:
    if not TASKS_FILE.exists():
        return []
    try:
        with open(TASKS_FILE) as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data
    except (json.JSONDecodeError, OSError):
        return []


def save_tasks(tasks: list) -> None:
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TASKS_FILE, "w") as f:
        json.dump(tasks, f, indent=2)
        f.write("\n")


def add_task(tasks: list, description: str) -> dict:
    max_id = max((t["id"] for t in tasks), default=0)
    task = {
        "id": max_id + 1,
        "desc": description,
        "done": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    tasks.append(task)
    return task


def list_tasks(tasks: list) -> None:
    if not tasks:
        print("No tasks.")
        return
    for t in tasks:
        status = "[x]" if t["done"] else "[ ]"
        print(f"{t['id']}. {status} {t['desc']}")


def done_task(tasks: list, task_id: int) -> bool:
    for t in tasks:
        if t["id"] == task_id:
            t["done"] = True
            return True
    return False


def clear_tasks(tasks: list) -> list:
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal JSON task tracker")
    parser.add_argument("command", choices=["add", "list", "done", "clear"])
    parser.add_argument("args", nargs=argparse.REMAINDER)
    parsed = parser.parse_args()

    cmd = parsed.command
    args = parsed.args

    if cmd == "add":
        if not args:
            print("Error: task description cannot be empty.", file=sys.stderr)
            sys.exit(1)
        description = " ".join(args)
        tasks = load_tasks()
        task = add_task(tasks, description)
        save_tasks(tasks)
        print(f"Added task {task['id']}: {description}")

    elif cmd == "list":
        tasks = load_tasks()
        list_tasks(tasks)

    elif cmd == "done":
        if not args:
            print("Error: missing task id.", file=sys.stderr)
            sys.exit(1)
        try:
            task_id = int(args[0])
        except ValueError:
            print(f"Error: invalid task id '{args[0]}'.", file=sys.stderr)
            sys.exit(1)
        tasks = load_tasks()
        if not done_task(tasks, task_id):
            print(f"Task {task_id} not found.", file=sys.stderr)
            sys.exit(1)
        save_tasks(tasks)
        print(f"Task {task_id} marked as done.")

    elif cmd == "clear":
        tasks = clear_tasks(load_tasks())
        save_tasks(tasks)
        print("All tasks cleared.")


if __name__ == "__main__":
    main()