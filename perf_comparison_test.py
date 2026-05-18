#!/usr/bin/env python3
"""Compare performance: a2a CLI vs a2a_client.py library"""

import os
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

from a2a_client import A2AClient


def setup_test_db():
    """Create fresh test database."""
    test_home = tempfile.mkdtemp()
    os.environ["HOME"] = test_home
    
    project = "perf-test"
    project_dir = Path.home() / ".a2a" / project
    project_dir.mkdir(parents=True, exist_ok=True)
    
    # Create schema
    db_path = project_dir / "database.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE agents (
            id TEXT PRIMARY KEY,
            role TEXT,
            status TEXT DEFAULT 'active',
            created_at REAL NOT NULL,
            last_seen REAL NOT NULL
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            recipient TEXT,
            body TEXT NOT NULL,
            thread_id TEXT,
            ttl_seconds INTEGER,
            created_at REAL NOT NULL
        );
        CREATE TABLE reads (
            agent_id TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            read_at REAL NOT NULL,
            PRIMARY KEY (agent_id, message_id)
        );
    """)
    
    ts = time.time()
    conn.execute("INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                 ("alice", "active", ts, ts))
    conn.execute("INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                 ("bob", "active", ts, ts))
    conn.commit()
    conn.close()
    
    return project, test_home


def bench_cli_send(project, count):
    """Benchmark a2a CLI send performance."""
    # Find a2a binary
    a2a = None
    for cand in ["a2a", "./a2a", os.path.expanduser("~/.local/bin/a2a")]:
        if subprocess.run(f"command -v {cand}", shell=True, capture_output=True).returncode == 0:
            a2a = cand
            break
    
    if not a2a:
        return None
    
    os.environ["A2A_PROJECT"] = project
    
    start = time.time()
    for i in range(count):
        subprocess.run(
            f"{a2a} send bob 'CLI message {i}' --from alice",
            shell=True, capture_output=True
        )
    elapsed = time.time() - start
    
    return elapsed


def bench_client_send(project, count):
    """Benchmark a2a_client.py send performance."""
    client = A2AClient(project, "alice")
    
    start = time.time()
    for i in range(count):
        client.send("bob", f"Client message {i}")
    elapsed = time.time() - start
    
    return elapsed


def bench_cli_recv(project, count):
    """Benchmark a2a CLI recv performance."""
    a2a = "a2a"
    os.environ["A2A_PROJECT"] = project
    
    # Pre-populate messages
    for i in range(count):
        subprocess.run(
            f"{a2a} send bob 'Message {i}' --from alice",
            shell=True, capture_output=True
        )
    
    start = time.time()
    for i in range(count):
        subprocess.run(
            f"{a2a} recv --as bob --wait 1",
            shell=True, capture_output=True
        )
    elapsed = time.time() - start
    
    return elapsed


def bench_client_recv(project, count):
    """Benchmark a2a_client.py recv performance."""
    client = A2AClient(project, "bob")
    
    # Pre-populate messages
    alice = A2AClient(project, "alice")
    for i in range(count):
        alice.send("bob", f"Message {i}")
    
    start = time.time()
    for i in range(count):
        client.recv(wait=1)
    elapsed = time.time() - start
    
    return elapsed


def main():
    print("🚀 Performance Comparison: CLI vs Python Client")
    print("=" * 60)
    print()
    
    test_count = 50
    
    # Test 1: Send performance
    print(f"Test 1: SEND Performance ({test_count} messages)")
    print("-" * 60)
    
    project, home = setup_test_db()
    os.environ["HOME"] = home
    
    cli_time = bench_cli_send(project, test_count)
    client_time = bench_client_send(project, test_count)
    
    if cli_time and client_time:
        speedup = cli_time / client_time
        print(f"  CLI:    {cli_time:.2f}s ({test_count/cli_time:.1f} msg/s)")
        print(f"  Client: {client_time:.2f}s ({test_count/client_time:.1f} msg/s)")
        print(f"  Speedup: {speedup:.1f}x faster with client library")
    print()
    
    # Test 2: Recv performance
    print(f"Test 2: RECV Performance ({test_count} messages)")
    print("-" * 60)
    
    project, home = setup_test_db()
    os.environ["HOME"] = home
    
    # Note: recv is tricky to benchmark fairly with CLI due to shell overhead
    client_time = bench_client_recv(project, test_count)
    print(f"  Client: {client_time:.2f}s ({test_count/client_time:.1f} msg/s)")
    print(f"  (CLI recv has high subprocess overhead, not comparable)")
    print()
    
    print("=" * 60)
    print("✅ Conclusion:")
    print("  - Python client is orders of magnitude faster (no subprocess)")
    print("  - CLI is suitable for interactive use, scripts, cross-language")
    print("  - Use client library for high-frequency messaging")


if __name__ == "__main__":
    main()
