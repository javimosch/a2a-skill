#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a2a Performance Benchmarking Suite

Measures:
- Message latency (send → recv)
- Throughput (messages/sec)
- Concurrent agent scalability
- Message TTL overhead
"""

import time
import json
import subprocess
import sys
import os
from pathlib import Path

def run(cmd):
    """Execute shell command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

class Benchmark:
    def __init__(self, project="a2a-bench"):
        self.project = project
        self.a2a = "a2a"
        self.results = {}

    def init_project(self):
        """Initialize a fresh benchmark project."""
        run(f"A2A_PROJECT={self.project} {self.a2a} clear --yes 2>/dev/null || true")
        run(f"A2A_PROJECT={self.project} {self.a2a} init")
        print(f"✓ Initialized project '{self.project}'")

    def register_agents(self, count=3):
        """Register N test agents."""
        for i in range(count):
            agent_id = f"agent-{i}"
            run(f"A2A_PROJECT={self.project} {self.a2a} register {agent_id}")
        print(f"✓ Registered {count} agents")
        return [f"agent-{i}" for i in range(count)]

    def bench_latency(self, sender="agent-0", receiver="agent-1"):
        """Measure message latency."""
        print(f"\n[Latency] {sender} → {receiver}")

        times = []
        for i in range(10):
            t0 = time.time()
            run(f"A2A_PROJECT={self.project} {self.a2a} send {receiver} 'latency-test-{i}' --from {sender}")
            # Simulate receive delay
            time.sleep(0.01)
            t1 = time.time()
            times.append((t1 - t0) * 1000)  # Convert to ms

        avg_latency = sum(times) / len(times)
        print(f"  Average latency: {avg_latency:.2f}ms")
        print(f"  Min: {min(times):.2f}ms, Max: {max(times):.2f}ms")
        self.results['latency_ms'] = avg_latency
        return avg_latency

    def bench_throughput(self, sender="agent-0", receiver="agent-1", count=100):
        """Measure message throughput."""
        print(f"\n[Throughput] Sending {count} messages")

        t0 = time.time()
        for i in range(count):
            run(f"A2A_PROJECT={self.project} {self.a2a} send {receiver} 'msg-{i}' --from {sender} 2>/dev/null")
        t1 = time.time()

        elapsed = t1 - t0
        throughput = count / elapsed
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Throughput: {throughput:.0f} msg/sec")
        self.results['throughput_mps'] = throughput
        return throughput

    def bench_broadcast(self, sender="agent-0", agents_count=5):
        """Measure broadcast latency."""
        print(f"\n[Broadcast] {sender} → ALL ({agents_count} agents)")

        t0 = time.time()
        for i in range(10):
            run(f"A2A_PROJECT={self.project} {self.a2a} send all 'broadcast-{i}' --from {sender} 2>/dev/null")
        t1 = time.time()

        avg_time = (t1 - t0) * 1000 / 10
        print(f"  Avg broadcast time: {avg_time:.2f}ms")
        self.results['broadcast_ms'] = avg_time
        return avg_time

    def bench_ttl(self, sender="agent-0", receiver="agent-1"):
        """Measure TTL overhead."""
        print(f"\n[TTL] Comparing with/without TTL")

        # Without TTL
        t0 = time.time()
        for i in range(50):
            run(f"A2A_PROJECT={self.project} {self.a2a} send {receiver} 'no-ttl-{i}' --from {sender} 2>/dev/null")
        t1 = time.time()
        without_ttl = (t1 - t0) * 1000 / 50

        # With TTL (3600 seconds)
        t0 = time.time()
        for i in range(50):
            run(f"A2A_PROJECT={self.project} {self.a2a} send {receiver} 'with-ttl-{i}' --from {sender} --ttl 3600 2>/dev/null")
        t1 = time.time()
        with_ttl = (t1 - t0) * 1000 / 50

        print(f"  Without TTL: {without_ttl:.2f}ms/msg")
        print(f"  With TTL: {with_ttl:.2f}ms/msg")
        print(f"  Overhead: {((with_ttl - without_ttl) / without_ttl * 100):.1f}%")
        self.results['ttl_overhead_pct'] = (with_ttl - without_ttl) / without_ttl * 100
        return with_ttl, without_ttl

    def bench_recv_latency(self, agent="agent-0"):
        """Measure recv blocking latency."""
        print(f"\n[Recv Latency] {agent} recv --wait 5")

        t0 = time.time()
        run(f"A2A_PROJECT={self.project} {self.a2a} recv --as {agent} --wait 5 2>/dev/null")
        t1 = time.time()

        elapsed = (t1 - t0) * 1000
        print(f"  Blocking recv took: {elapsed:.0f}ms")
        self.results['recv_block_ms'] = elapsed
        return elapsed

    def print_summary(self):
        """Print benchmark summary."""
        print("\n" + "=" * 50)
        print("BENCHMARK SUMMARY")
        print("=" * 50)
        for key, val in self.results.items():
            if isinstance(val, float):
                print(f"{key:.<35} {val:.2f}")
            else:
                print(f"{key:.<35} {val}")

    def cleanup(self):
        """Clean up benchmark project."""
        run(f"A2A_PROJECT={self.project} {self.a2a} clear --yes 2>/dev/null")
        print(f"\n✓ Cleaned up project '{self.project}'")

def main():
    bench = Benchmark(project="a2a-benchmark")
    bench.init_project()
    agents = bench.register_agents(5)

    try:
        print("\nRunning benchmarks...")
        bench.bench_latency()
        bench.bench_throughput(count=100)
        bench.bench_broadcast(agents_count=5)
        bench.bench_ttl()
        bench.bench_recv_latency()
        bench.print_summary()
    finally:
        bench.cleanup()

if __name__ == "__main__":
    main()
