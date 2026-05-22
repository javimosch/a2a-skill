#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: data-to-chart.

Three agents (fetcher, analyst, plotter) collaborate via the a2a bus to
generate sample data, analyze it statistically, and produce ASCII charts.

If the AI CLI hits an API key limit, falls back to direct generation so
the artifact is always produced.

Usage:
  python3 examples/artifacts/data-to-chart/build.py [--project NAME] [--cli opencode]

Requires a2a, a2a-spawn, and an AI CLI (claude, opencode, or pi).
"""
import os
import sys
import time
import json
import math
import random
import shlex
import subprocess
import argparse
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, send_task, SpawnManager  # noqa: E402

ARTIFACT = "data-to-chart"

FETCHER_INSTRUCTIONS = (
    "You are the data fetcher. Generate interesting sample CSV data.\\n\\n"
    "Steps:\\n"
    "1. Think of a real-world dataset to generate — examples:\\n"
    "   - Server CPU temperature (°C) every 30 minutes over 48 hours\\n"
    "   - Website response times (ms) over a 24-hour period\\n"
    "   - Daily active users of an app over 30 days\\n"
    "   - Stock price (USD) over 90 trading days\\n"
    "2. Generate 20-30 data points as CSV with headers\\n"
    "3. Add realistic variation — include trends, spikes, and noise\\n"
    "4. Send the CSV data to the analyst:\\n"
    '   a2a send analyst DATA_START\\\\n<your CSV data>\\\\nDATA_END --from fetcher\\n\\n'
    "Example CSV format:\\n"
    "timestamp,value\\n"
    "0,35.2\\n"
    "1,36.8\\n"
    "...\\n\\n"
    "The DATA must be between DATA_START and DATA_END markers."
)

ANALYST_INSTRUCTIONS = (
    "You are the data analyst. Wait for the fetcher to send you CSV data.\\n\\n"
    "Steps:\\n"
    "1. Receive the fetcher's message:\\n"
    '   a2a recv --as analyst --wait 60\\n'
    "2. Parse the CSV data (timestamp,value format)\\n"
    "3. Compute these statistics:\\n"
    "   - Number of data points\\n"
    "   - Minimum, maximum, mean, median\\n"
    "   - Trend direction (increasing, decreasing, or stable)\\n"
    "   - Volatility (standard deviation of changes between consecutive points)\\n"
    "4. Send the analysis + the raw values array to the plotter:\\n"
    '   a2a send plotter ANALYSIS_START\\\\n<your analysis as markdown>\\\\nVALUES:[val1,val2,...]\\\\nANALYSIS_END --from analyst\\n\\n'
    "The VALUES must be a JSON array of floats that the plotter can use."
)

PLOTTER_INSTRUCTIONS = (
    "You are the chart plotter. Wait for the analyst to send you data.\\n\\n"
    "Steps:\\n"
    "1. Receive the analyst's message:\\n"
    '   a2a recv --as plotter --wait 60\\n'
    "2. Extract the VALUES array and the analysis from the message\\n"
    "3. Generate an ASCII line chart from the values (use characters like ▁▂▃▄▅▆▇█ or |/-\\\\)\\n"
    "4. Label the chart with min/max values and a title\\n"
    "5. Broadcast the complete output:\\n"
    '   a2a send all CHART_START\\\\n<your formatted chart with analysis>\\\\nCHART_END --from plotter\\n\\n'
    "The output must be between CHART_START and CHART_END markers."
)


def ascii_chart(values, width=50, height=10, title="Data Chart"):
    """Generate a pure-Python ASCII line chart from a list of floats.

    No external dependencies — uses only stdlib math.
    Returns a string with the rendered chart.
    """
    if not values:
        return "[empty data]"

    min_v = min(values)
    max_v = max(values)
    range_v = max_v - min_v if max_v != min_v else 1

    # Build the chart lines
    lines = []
    lines.append(f" {title}")
    lines.append(f" Range: {min_v:.1f} to {max_v:.1f}")
    lines.append("")

    # Normalize values to chart height
    def normalize(v):
        return int((v - min_v) / range_v * (height - 1))

    # Draw the Y axis and data line
    for row in range(height - 1, -1, -1):
        threshold = min_v + (range_v * row / (height - 1))
        label = f"{threshold:8.1f} |"
        chars = []
        for v in values:
            n = normalize(v)
            chars.append("*" if n == row else " ")
        lines.append(label + "".join(chars))

    # X axis
    x_label = "          " + "+" + "-" * (len(values) - 2) + "+"
    lines.append(x_label)

    # X axis labels
    step = max(1, len(values) // 6)
    x_ticks = ""
    for i, v in enumerate(values):
        if i % step == 0 or i == len(values) - 1:
            x_ticks += str(i)
        else:
            x_ticks += " "
    lines.append("           " + x_ticks)

    # Data point label
    lines.append(f"           Data points: 0 to {len(values)-1} (n={len(values)})")
    lines.append("")

    # Summary statistics bar
    lines.append("  Statistics")
    lines.append(f"    Min: {min_v:.2f}")
    lines.append(f"    Max: {max_v:.2f}")
    lines.append(f"    Mean: {sum(values)/len(values):.2f}")
    lines.append(f"    Range: {range_v:.2f}")

    # Direction
    first_half = sum(values[:len(values)//2]) / max(len(values)//2, 1)
    second_half = sum(values[len(values)//2:]) / max(len(values) - len(values)//2, 1)
    diff = second_half - first_half
    if diff > range_v * 0.05:
        direction = "📈 Increasing"
    elif diff < -range_v * 0.05:
        direction = "📉 Decreasing"
    else:
        direction = "➡️  Stable"
    lines.append(f"    Trend: {direction}")

    return "\n".join(lines)


def compute_analysis(values):
    """Compute statistics from a list of values."""
    n = len(values)
    if n == 0:
        return "No data"
    sorted_v = sorted(values)
    mean = sum(values) / n
    median = sorted_v[n // 2] if n % 2 == 1 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    min_v = min(values)
    max_v = max(values)
    range_v = max_v - min_v

    # Standard deviation
    variance = sum((v - mean) ** 2 for v in values) / n
    std_dev = math.sqrt(variance)

    # Trend
    first_half = sum(values[:n // 2]) / max(n // 2, 1)
    second_half = sum(values[n // 2:]) / max(n - n // 2, 1)
    if second_half - first_half > range_v * 0.05:
        trend = "increasing"
    elif first_half - second_half > range_v * 0.05:
        trend = "decreasing"
    else:
        trend = "stable"

    # Volatility (mean absolute change)
    changes = [abs(values[i] - values[i - 1]) for i in range(1, n)]
    volatility = sum(changes) / len(changes) if changes else 0

    return {
        "n": n,
        "min": min_v,
        "max": max_v,
        "mean": mean,
        "median": median,
        "std_dev": std_dev,
        "range": range_v,
        "trend": trend,
        "volatility": volatility,
    }


def generate_sample_data(kind="temperature"):
    """Generate realistic sample data."""
    if kind == "temperature":
        # CPU temperature over time — starts cool, warms up, cycles
        values = []
        for i in range(30):
            base = 55 + 15 * math.sin(i / 6)  # Daily cycle
            noise = random.gauss(0, 3)
            spike = 20 if random.random() < 0.05 else 0  # Occasional spike
            values.append(round(base + noise + spike, 1))
        return values, "cpu_temp", "CPU Temperature (°C) over 30 time points"

    elif kind == "response_time":
        values = []
        for i in range(25):
            base = 120 + 40 * math.sin(i / 4) + 10 * (i / 25)
            noise = random.gauss(0, 15)
            spike = 200 if random.random() < 0.08 else 0
            values.append(round(base + noise + spike, 1))
        return values, "response_ms", "Server Response Time (ms) over 25 samples"

    elif kind == "users":
        # DAU — growing with weekly cycles
        values = []
        growth = 0
        for i in range(30):
            growth += random.gauss(5, 3)  # Gradual growth
            weekly = 50 * math.sin(i * 2 * math.pi / 7)
            noise = random.gauss(0, 10)
            values.append(round(1000 + growth + weekly + noise, 0))
        return values, "daily_users", "Daily Active Users over 30 days"

    else:
        # Stock price — random walk
        price = 100.0
        values = []
        for i in range(25):
            change = random.gauss(0, 2)
            price = max(price + change, 50)
            values.append(round(price, 2))
        return values, "stock_price", "Simulated Stock Price (USD) over 25 days"


def generate_fallback_output() -> tuple:
    """Generate data, analysis, and chart directly (fallback when agents fail)."""
    print(f"[{ARTIFACT}] Generating fallback data + analysis + charts...")

    # Generate 3 datasets for a richer output
    all_sections = []
    for kind in ["temperature", "response_time", "users"]:
        values, name, title = generate_sample_data(kind)
        analysis = compute_analysis(values)
        chart = ascii_chart(values, width=50, height=8, title=title)

        section = {
            "name": name,
            "title": title,
            "values": values,
            "analysis": analysis,
            "chart": chart,
        }
        all_sections.append(section)

    # Build charts.txt
    chart_lines = []
    for sec in all_sections:
        if chart_lines:
            chart_lines.append("")
            chart_lines.append("=" * 70)
            chart_lines.append("")
        chart_lines.append(sec["chart"])
    charts_text = "\n".join(chart_lines)

    # Build analysis.md
    md_lines = [
        "# Data Analysis Report",
        "",
        "Analysis of generated datasets with statistical summaries and ASCII charts.",
        "",
        "## Datasets",
        "",
    ]
    for sec in all_sections:
        a = sec["analysis"]
        md_lines.extend([
            f"### {sec['title']}",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Data Points | {a['n']} |",
            f"| Minimum | {a['min']:.2f} |",
            f"| Maximum | {a['max']:.2f} |",
            f"| Mean | {a['mean']:.2f} |",
            f"| Median | {a['median']:.2f} |",
            f"| Std Deviation | {a['std_dev']:.2f} |",
            f"| Range | {a['range']:.2f} |",
            f"| Trend | {a['trend']} |",
            f"| Volatility | {a['volatility']:.2f} |",
            "",
            "```",
            sec['chart'],
            "```",
            "",
        ])

    md_lines.extend([
        "## Methodology",
        "",
        "- **CPU Temperature**: Synthetic data modeling a server CPU with diurnal cycles and occasional thermal spikes.",
        "- **Response Time**: Server response times with increasing baseline load and outlier spikes.",
        "- **Daily Active Users**: Growth trend with weekly seasonality patterns.",
        "",
        "ASCII charts rendered at 50-character width with 8-row height.",
        "",
        "*This report was generated from synthesized data. "
        "Agents were unable to participate due to API key limits; "
        "the build script produced this directly as a fallback.*",
    ])

    return charts_text, "\n".join(md_lines)


def check_agent_logs(agent_ids: list) -> bool:
    """Check agent logs for API errors. Returns True if any agent has errors."""
    had_errors = False
    for aid in agent_ids:
        log_path = f"/tmp/a2a-{aid}.log"
        try:
            with open(log_path) as f:
                content = f.read()
            for marker in ["Key limit exceeded", "insufficient_quota", "rate_limit_exceeded",
                            "401", "402", "429", "403"]:
                if marker in content:
                    print(f"[{ARTIFACT}] WARNING: Agent '{aid}' log shows '{marker}' — API key may be exhausted.")
                    had_errors = True
                    break
        except (FileNotFoundError, OSError):
            pass
    return had_errors


def main():
    parser = argparse.ArgumentParser(description="Build data-to-chart artifact via agent collaboration")
    parser.add_argument("--project", default=None)
    parser.add_argument("--cli", default="opencode", choices=["claude", "opencode", "pi"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=420, help="Total timeout in seconds")
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
        {"id": "fetcher", "role": "data fetcher", "task": FETCHER_INSTRUCTIONS},
        {"id": "analyst", "role": "data analyst", "task": ANALYST_INSTRUCTIONS},
        {"id": "plotter", "role": "chart plotter", "task": PLOTTER_INSTRUCTIONS},
    ]
    agent_ids = [ag["id"] for ag in agents]
    for ag in agents:
        run_a2a(f'register {ag["id"]} --role "{ag["role"]}" --cli {args.cli}', a2a_bin, project)

    # Spawn agents
    spawned_ok = True
    for ag in agents:
        kit = make_kit(ag["id"], ag["role"], ag["task"], project)
        with tempfile.NamedTemporaryFile(mode="w", prefix=f"a2a-{project}-{ag['id']}-", suffix=".kit", delete=False) as f:
            f.write(kit)
            kit_path = f.name
        pid = spawn_agent(spawn_bin, args.cli, ag["id"], kit_path, project=project, model=args.model, a2a_bin=a2a_bin)
        if pid:
            mgr.add(pid)
        else:
            spawned_ok = False
        os.unlink(kit_path)

    time.sleep(2)

    # Check for API errors in agent logs
    api_errors = check_agent_logs(agent_ids)

    if not spawned_ok or api_errors:
        print(f"[{ARTIFACT}] Agents have API/startup issues. Sending tasks anyway in case some agents work...")

    # Send tasks via stdin
    for ag in agents:
        send_task(a2a_bin, project, ag["id"], f"Your task: {ag['task']}")
        print(f"[{ARTIFACT}] → sent task to {ag['id']}")

    # Wait for agent-produced chart
    print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
    deadline = time.time() + args.timeout
    agent_chart = None
    agent_analysis = None

    while time.time() < deadline:
        msgs = run_a2a_json("recv --as collector --wait 30", a2a_bin, project)
        for msg in msgs if isinstance(msgs, list) else []:
            sender = msg.get("sender", "")
            body = msg.get("body", "")
            if sender == "analyst" and "VALUES:" in body:
                agent_analysis = body
                print(f"[{ARTIFACT}] ← Received analysis from analyst")
            if sender == "plotter" and "CHART_START" in body:
                start_idx = body.find("CHART_START") + len("CHART_START")
                end_idx = body.find("CHART_END")
                if end_idx > start_idx:
                    agent_chart = body[start_idx:end_idx].strip()
                else:
                    agent_chart = body.replace("CHART_START", "").replace("CHART_END", "").strip()
                if agent_chart:
                    print(f"[{ARTIFACT}] ← Received chart from plotter ({len(agent_chart)} chars)")
                    break
        if agent_chart:
            break

    # Write output — fallback if agents failed
    if agent_chart:
        charts_text = agent_chart
        analysis_md = agent_analysis or "# Agent Analysis\n\nAnalysis received from the analyst agent via the a2a bus."
        print(f"[{ARTIFACT}] Wrote output (agent-produced)")
    else:
        print(f"[{ARTIFACT}] No agent-produced output. Generating fallback from Python...")
        charts_text, analysis_md = generate_fallback_output()

    (output_dir / "charts.txt").write_text(charts_text)
    (output_dir / "analysis.md").write_text(analysis_md)
    print(f"[{ARTIFACT}] Wrote output/charts.txt ({len(charts_text)} chars)")
    print(f"[{ARTIFACT}] Wrote output/analysis.md ({len(analysis_md)} chars)")

    # Capture bus state
    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
