#!/usr/bin/env python3
"""
High-performance async task worker demonstrating concurrent message handling.

Uses Python's asyncio for handling multiple concurrent tasks efficiently.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from a2a_client_async import A2AClientAsync, run_agent


async def handle_task(client: A2AClientAsync, task_data: dict):
    """Process a single task asynchronously.

    Args:
        client: a2a async client
        task_data: Task data dict
    """
    task_id = task_data.get("id", "unknown")
    work = task_data.get("work", "no description")
    priority = task_data.get("priority", "normal")

    print(f"[WORKER] Processing task {task_id} (priority: {priority})")
    print(f"[WORKER] Work: {work}")

    # Simulate async work (non-blocking)
    await asyncio.sleep(1)

    # Send result back
    result = {
        "task_id": task_id,
        "status": "complete",
        "result": f"Completed: {work}",
        "duration": 1.0,
    }

    await client.send("coordinator", json.dumps(result))
    print(f"[WORKER] Task {task_id} complete, result sent")


async def worker_agent(client: A2AClientAsync):
    """Main async worker agent loop.

    Args:
        client: a2a async client
    """
    print("[WORKER] Starting task worker...")

    try:
        while True:
            # Non-blocking wait for tasks
            messages = await client.recv(wait=10, unread_only=True, limit=5)

            if not messages:
                print("[WORKER] No tasks, exiting")
                break

            # Process multiple tasks concurrently
            tasks = []
            for msg in messages:
                try:
                    task_data = json.loads(msg["body"])
                    task = asyncio.create_task(handle_task(client, task_data))
                    tasks.append(task)
                except json.JSONDecodeError:
                    print(f"[WORKER] Skipping non-JSON message: {msg['body'][:50]}")

            # Wait for all concurrent tasks to complete
            if tasks:
                await asyncio.gather(*tasks)

    except KeyboardInterrupt:
        print("[WORKER] Interrupted by user")
    except Exception as e:
        print(f"[WORKER] Error: {e}")


async def batch_coordinator(client: A2AClientAsync):
    """Coordinator that sends batch tasks and waits for results.

    Args:
        client: a2a async client
    """
    print("[COORDINATOR] Starting batch coordinator...")

    # Define batch tasks
    tasks = [
        {
            "id": "task-1",
            "work": "Analyze customer data",
            "priority": "high",
        },
        {
            "id": "task-2",
            "work": "Generate report",
            "priority": "normal",
        },
        {
            "id": "task-3",
            "work": "Validate schema",
            "priority": "high",
        },
        {
            "id": "task-4",
            "work": "Optimize queries",
            "priority": "low",
        },
        {
            "id": "task-5",
            "work": "Backup database",
            "priority": "critical",
        },
    ]

    # Send tasks as broadcast
    print(f"[COORDINATOR] Broadcasting {len(tasks)} tasks...")
    for task in tasks:
        await client.send("all", json.dumps(task))
        print(f"[COORDINATOR] Sent {task['id']}")

    # Wait for results with timeout
    print("[COORDINATOR] Waiting for results...")
    results = await client.wait_for_messages(count=len(tasks), timeout=30)

    print(f"[COORDINATOR] Received {len(results)} results")
    for result in results:
        try:
            data = json.loads(result["body"])
            print(f"[COORDINATOR] Result: {data.get('task_id')} - {data.get('status')}")
        except json.JSONDecodeError:
            pass

    # Show stats
    stats = await client.stats()
    print(f"[COORDINATOR] Bus stats: {stats['messages']} total messages")


async def main():
    """Main entry point."""
    import sys

    project = "async-demo"
    agent_type = sys.argv[1] if len(sys.argv) > 1 else "worker"

    if agent_type == "worker":
        await run_agent("worker-1", project, worker_agent)
    elif agent_type == "coordinator":
        await run_agent("coordinator", project, batch_coordinator)
    else:
        print(f"Unknown agent type: {agent_type}")
        print("Usage: python async_task_worker.py [worker|coordinator]")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
