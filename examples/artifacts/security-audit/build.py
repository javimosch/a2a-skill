#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: security-audit.

Two agents (scanner, reporter) collaborate via the a2a bus to produce a
security posture report covering web frameworks, AI/ML tools, and system
security — using ddgr web search and built-in system commands.

Scanner: searches ddgr for CVEs/vulnerabilities in 3 categories and runs
         basic system security checks (open ports, disk, running services)
Reporter: categorizes findings by severity (Critical/High/Medium/Low) and
          writes a formatted security posture report.

Usage:
  python3 examples/artifacts/security-audit/build.py [--project NAME] [--cli opencode]

Requires a2a, a2a-spawn, ddgr, and an AI CLI (opencode, claude, or pi).
"""

import os
import sys
import time
import json
import shlex
import subprocess
import argparse
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, send_task, SpawnManager  # noqa: E402

ARTIFACT = "security-audit"

SCANNER_INSTRUCTIONS = (
    "You are the security scanner for a comprehensive security audit.\\n\\n"
    "You have shell access. Available tools:\\n"
    '  ddgr --json -n 8 "<query>"    # web search for CVEs\\n'
    "  df -h                           # check disk usage\\n"
    "  ss -tlnp                        # check listening ports\\n"
    "  uptime                          # system uptime & load\\n"
    "  dmesg --level=err,warn | tail -20  # kernel errors\\n\\n"
    "Steps:\\n"
    "1. Search for vulnerabilities in three categories:\\n"
    '   a) ddgr --json -n 8 "critical web framework vulnerabilities 2026 CVE"\\n'
    '   b) ddgr --json -n 8 "AI ML supply chain security vulnerabilities 2026"\\n'
    '   c) ddgr --json -n 8 "critical Linux kernel vulnerability 2026 CVE"\\n'
    "2. Run system health commands: df -h, ss -tlnp, uptime, dmesg\\n"
    "3. Compile all findings into a structured report\\n"
    "4. Send the report to the reporter:\\n"
    '   a2a send reporter "SCAN_START\\n<your findings>\\nSCAN_END" --from scanner\\n\\n'
    "Important: Include the raw ddgr JSON results for the reporter to analyze."
)

REPORTER_INSTRUCTIONS = (
    "You are the security reporter. You receive findings from the scanner\\n"
    "and produce a formatted security posture report.\\n\\n"
    "Steps:\\n"
    "1. Wait for the scanner to send findings:\\n"
    '   a2a recv --as reporter --wait 60\\n'
    "2. Analyze the findings and categorize by severity:\\n"
    "   - Critical: Remote code execution, authentication bypass, data breach\\n"
    "   - High: Privilege escalation, sensitive data exposure, SSRF\\n"
    "   - Medium: XSS, CSRF, DoS, information disclosure\\n"
    "   - Low: Best practice violations, informational\\n"
    "3. Write a markdown security report with sections:\\n"
    "   - Executive Summary (overall risk level, score out of 10)\\n"
    "   - Category 1: Web Framework Vulnerabilities (per-finding: CVE, impact, severity)\\n"
    "   - Category 2: AI/ML Security (supply chain, model risks, tooling CVEs)\\n"
    "   - Category 3: System Security (open ports assessment, disk usage, uptime)\\n"
    "   - Recommendations (actionable items, ordered by priority)\\n"
    "4. Broadcast the report:\\n"
    '   a2a send all "REPORT_START\\n<full report>\\nREPORT_END" --from reporter'
)


def run_ddgr(query: str) -> list:
    """Run a ddgr search and return parsed JSON results."""
    try:
        safe_query = query.replace('"', '\\"')
        cmd = f'ddgr --json -n 8 "{safe_query}"'
        result = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if isinstance(data, list):
                return data
        return []
    except Exception as exc:
        print(f"  [ddgr] Failed: {exc}", file=sys.stderr)
        return []


def run_system_checks() -> dict:
    """Run basic system security checks and return results."""
    checks = {}
    try:
        result = subprocess.run(["df", "-h"], capture_output=True, text=True, timeout=10)
        checks["disk_usage"] = result.stdout.strip()
    except Exception as e:
        checks["disk_usage"] = f"Error: {e}"

    try:
        result = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=10)
        checks["listening_ports"] = result.stdout.strip()
    except Exception as e:
        checks["listening_ports"] = f"Error: {e}"

    try:
        result = subprocess.run(["uptime"], capture_output=True, text=True, timeout=10)
        checks["uptime"] = result.stdout.strip()
    except Exception as e:
        checks["uptime"] = f"Error: {e}"

    try:
        result = subprocess.run(["dmesg", "--level=err,warn"], capture_output=True, text=True, timeout=10)
        lines = result.stdout.strip().splitlines()
        checks["dmesg_errors"] = "\n".join(lines[-20:]) if lines else "No recent errors"
    except Exception as e:
        checks["dmesg_errors"] = f"Error: {e}"

    return checks


CATEGORIES = [
    "critical web framework vulnerabilities 2026 CVE",
    "AI ML supply chain security vulnerabilities 2026",
    "critical Linux kernel vulnerability 2026 CVE",
]


def run_scanner_fallback() -> dict:
    """Run ddgr searches and system checks directly as fallback."""
    print(f"  [{ARTIFACT}] Fallback: running ddgr searches + system checks...")
    findings = {}
    for category in CATEGORIES:
        print(f"    Searching: {category}")
        results = run_ddgr(category)
        # Filter for CVE/vulnerability-related results
        filtered = []
        for r in results:
            title = r.get("title", "")
            abstract = r.get("abstract", "")
            text = (title + " " + abstract).lower()
            if any(kw in text for kw in ["cve-", "vulnerability", "security", "advisory", "remote code",
                                          "privilege escalation", "exploit", "patch", "fix"]):
                filtered.append(r)
        findings[category] = filtered[:5]
    findings["system_checks"] = run_system_checks()
    return findings


def classify_severity(findings: dict) -> dict:
    """Classify findings by severity."""
    severity_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "Info": 0}
    total_cves = 0
    categorized = {}

    for category, results in findings.items():
        if category == "system_checks":
            continue
        items = []
        for r in results:
            title = r.get("title", "")
            abstract = r.get("abstract", "")
            text = (title + " " + abstract).lower()
            url = r.get("url", "")
            severity = "Low"
            if any(kw in text for kw in ["remote code", "rce", "critical", "authentication bypass",
                                          "unauthenticated", "pre-auth", "worm"]):
                severity = "Critical"
            elif any(kw in text for kw in ["privilege escalation", "elevation of privilege",
                                            "sensitive data", "information disclosure",
                                            "ssrf", "arbitrary code"]):
                severity = "High"
            elif any(kw in text for kw in ["xss", "csrf", "denial of service", "dos",
                                            "cross-site", "open redirect", "path traversal"]):
                severity = "Medium"
            elif "cve-" in text:
                severity = "Low"
            else:
                severity = "Info"

            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            if "cve-" in text:
                total_cves += 1

            items.append({
                "title": title,
                "url": url,
                "abstract": abstract[:150],
                "severity": severity,
            })
        categorized[category] = items

    return {
        "severity_counts": severity_counts,
        "total_cves": total_cves,
        "total_findings": sum(len(v) for v in categorized.values()),
        "categorized": categorized,
        "system_checks": findings.get("system_checks", {}),
    }


def generate_report(data: dict) -> str:
    """Generate the formatted security report markdown."""
    sc = data["severity_counts"]
    sys_c = data.get("system_checks", {})
    lines = [
        "# System Security Posture Report",
        "",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Scope:** Web frameworks, AI/ML tools, OS/kernel, system configuration",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "This report summarizes findings from web research and system security checks.",
        "",
        "### Risk Score",
        "",
    ]

    # Calculate risk score
    critical_w = sc.get("Critical", 0) * 10
    high_w = sc.get("High", 0) * 5
    medium_w = sc.get("Medium", 0) * 2
    low_w = sc.get("Low", 0) * 0.5
    total_weight = critical_w + high_w + medium_w + low_w
    # Cap at 10
    risk_score = min(10, total_weight / max(1, data["total_findings"]) * 2) if data["total_findings"] else 1
    risk_score = round(risk_score, 1)

    if risk_score >= 7:
        risk_level = "🔴 Critical"
    elif risk_score >= 4:
        risk_level = "🟡 Elevated"
    elif risk_score >= 2:
        risk_level = "🟢 Moderate"
    else:
        risk_level = "✅ Low"

    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| **Overall Risk Score** | **{risk_score}/10 — {risk_level}** |")
    lines.append(f"| Total Findings | {data['total_findings']} |")
    lines.append(f"| Total CVEs Referenced | {data['total_cves']} |")
    lines.append(f"| Critical | {sc.get('Critical', 0)} |")
    lines.append(f"| High | {sc.get('High', 0)} |")
    lines.append(f"| Medium | {sc.get('Medium', 0)} |")
    lines.append(f"| Low | {sc.get('Low', 0)} |")
    lines.append(f"| Info | {sc.get('Info', 0)} |")
    lines.append("")

    # Severity distribution bar
    total = max(data["total_findings"], 1)
    bars = []
    for sev in ["Critical", "High", "Medium", "Low", "Info"]:
        count = sc.get(sev, 0)
        if count > 0:
            pct = count / total * 100
            bar_len = max(1, int(pct / 5))
            bar = "█" * bar_len
            bars.append(f"  {sev}: {bar} ({count})")
    if bars:
        lines.append("### Severity Distribution")
        lines.append("")
        lines.extend(bars)
        lines.append("")

    # Per-category findings
    for i, (category, items) in enumerate(data["categorized"].items(), 1):
        # Extract short name
        if "web framework" in category.lower():
            cat_name = "Web Framework Vulnerabilities"
        elif "ml" in category.lower() or "supply chain" in category.lower():
            cat_name = "AI/ML Security"
        elif "kernel" in category.lower() or "linux" in category.lower():
            cat_name = "Operating System / Kernel"
        else:
            cat_name = category

        lines.append(f"### {i}. {cat_name}")
        lines.append("")
        if not items:
            lines.append("*No specific CVE findings in this category.*")
            lines.append("")
            continue

        for item in items:
            sev = item.get("severity", "Info")
            emoji = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🔵", "Info": "⚪"}
            sev_icon = emoji.get(sev, "⚪")
            title = item.get("title", "Untitled").replace("[", "").replace("]", "")
            url = item.get("url", "")
            abstract = item.get("abstract", "")
            lines.append(f"- {sev_icon} **[{sev}]** {title}")
            if abstract:
                lines.append(f"  - {abstract[:200]}")
            if url:
                lines.append(f"  - Source: [{url}]({url})")
        lines.append("")

    # System security section
    lines.append("### 4. System Configuration Assessment")
    lines.append("")
    lines.append("#### Disk Usage")
    lines.append("")
    lines.append("```")
    lines.append(sys_c.get("disk_usage", "N/A"))
    lines.append("```")
    lines.append("")

    # Parse disk for critical usage
    disk_output = sys_c.get("disk_usage", "")
    critical_mounts = []
    for line in disk_output.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[4].rstrip("%").isdigit():
            pct = int(parts[4].rstrip("%"))
            if pct >= 90:
                critical_mounts.append(f"  - ⚠️  **{parts[5]}** at {pct}% capacity")
    if critical_mounts:
        lines.append("**⚠️  High disk usage detected:**")
        lines.extend(critical_mounts)
        lines.append("")

    lines.append("#### Listening Ports")
    lines.append("")
    lines.append("```")
    ports = sys_c.get("listening_ports", "N/A")
    lines.append(ports)
    lines.append("```")
    lines.append("")

    # Assess ports
    open_ports = []
    unexpected_ports = []
    for line in ports.splitlines():
        if "LISTEN" in line:
            parts = line.split()
            for p in parts:
                if ":" in p and p.split(":")[-1].isdigit():
                    port_num = int(p.split(":")[-1])
                    open_ports.append(port_num)
                    if port_num not in (22, 80, 443, 3000, 8080, 8443, 9090):
                        unexpected_ports.append(port_num)
    lines.append(f"**Open ports:** {len(open_ports)} ({', '.join(map(str, sorted(set(open_ports))))})")
    if unexpected_ports:
        lines.append(f"**⚠️  Non-standard ports detected:** {', '.join(map(str, sorted(set(unexpected_ports))))}")
    lines.append("")

    lines.append("#### Uptime & Load")
    lines.append("")
    lines.append(f"```\n{sys_c.get('uptime', 'N/A')}\n```")
    lines.append("")

    # Kernel errors
    dmesg = sys_c.get("dmesg_errors", "")
    if dmesg and dmesg != "No recent errors":
        lines.append("#### Recent Kernel Errors (err/warn)")
        lines.append("")
        lines.append("```")
        lines.append(dmesg[:500])
        lines.append("```")
        lines.append("")
    else:
        lines.append("#### Kernel Errors")
        lines.append("")
        lines.append("*No recent kernel errors or warnings detected.*")
        lines.append("")

    # Recommendations
    lines.append("---")
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    recs = []
    if sc.get("Critical", 0) > 0:
        recs.append(f"1. **Immediate action:** {sc.get('Critical', 0)} critical findings require urgent review. Apply available patches and updates.")
    if sc.get("High", 0) > 0:
        recs.append(f"{len(recs) + 1}. **Priority review:** {sc.get('High', 0)} high-severity findings should be assessed within 7 days.")
    if critical_mounts:
        recs.append(f"{len(recs) + 1}. **Disk space:** Free up space on {len(critical_mounts)} mount(s) exceeding 90% capacity.")
    if unexpected_ports:
        recs.append(f"{len(recs) + 1}. **Network audit:** Review {len(unexpected_ports)} non-standard listening ports — verify they are intentional.")
    recs.append(f"{len(recs) + 1}. **Continuous monitoring:** Run this security audit weekly to track new CVEs and system changes.")
    recs.append(f"{len(recs) + 1}. **Patch management:** Subscribe to security advisories for all in-scope technologies and apply patches within SLA.")

    lines.extend(recs)
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Report generated by a2a security-audit artifact using ddgr web search and system commands.*")

    return "\n".join(lines)


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
    parser = argparse.ArgumentParser(description="Build security posture report via agent collaboration")
    parser.add_argument("--project", default=None)
    parser.add_argument("--cli", default="opencode", choices=["claude", "opencode", "pi"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=360, help="Total timeout in seconds")
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

    print(f"[{ARTIFACT}] a2a: {a2a_bin}, spawn: {spawn_bin}, project: {project}, cli: {args.cli}")

    # Init bus
    run_a2a("init", a2a_bin, project)
    run_a2a("clear --yes", a2a_bin, project)
    run_a2a("register collector --role build-script --cli python", a2a_bin, project)

    agents = [
        {"id": "scanner", "role": "security scanner", "task": SCANNER_INSTRUCTIONS},
        {"id": "reporter", "role": "security reporter", "task": REPORTER_INSTRUCTIONS},
    ]
    agent_ids = [ag["id"] for ag in agents]
    for ag in agents:
        run_a2a(f'register {ag["id"]} --role "{ag["role"]}" --cli {args.cli}', a2a_bin, project)

    # Spawn agents
    mgr = SpawnManager()
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
    all_agents_failed = not spawned_ok or api_errors
    final_report = None

    if all_agents_failed:
        print(f"[{ARTIFACT}] Agents have API/startup issues — skipping agent wait loop, generating fallback directly...")
    else:
        # Send tasks via stdin
        for ag in agents:
            send_task(a2a_bin, project, ag["id"], f"Your task: {ag['task']}")
            print(f"[{ARTIFACT}] → sent task to {ag['id']}")

        # Wait for agent-produced report
        print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
        deadline = time.time() + args.timeout

        while time.time() < deadline:
            msgs = run_a2a_json("recv --as collector --wait 30", a2a_bin, project)
            for msg in msgs if isinstance(msgs, list) else []:
                sender = msg.get("sender", "")
                body = msg.get("body", "")
                if sender == "reporter" and "REPORT_START" in body:
                    start_idx = body.find("REPORT_START") + len("REPORT_START")
                    end_idx = body.find("REPORT_END")
                    if end_idx > start_idx:
                        final_report = body[start_idx:end_idx].strip()
                    else:
                        final_report = body.replace("REPORT_START", "").replace("REPORT_END", "").strip()
                    print(f"[{ARTIFACT}] ← Received agent-produced report ({len(final_report)} chars)")
                    break
            if final_report:
                break

    # Write output
    report_path = output_dir / "report.md"
    if final_report:
        report_path.write_text(final_report)
        print(f"[{ARTIFACT}] Wrote output/report.md (agent-produced, {len(final_report)} chars)")
    else:
        print(f"[{ARTIFACT}] No agent-produced report. Generating fallback from ddgr + system checks...")
        scan_data = run_scanner_fallback()
        # Process system checks
        classified = classify_severity(scan_data)
        report = generate_report(classified)
        report_path.write_text(report)
        print(f"[{ARTIFACT}] Wrote output/report.md (fallback, {len(report)} chars)")

        # Also write raw findings
        raw_path = output_dir / "raw-findings.json"
        import json as _json
        raw_path.write_text(_json.dumps(classified, indent=2, default=str))
        print(f"[{ARTIFACT}] Wrote output/raw-findings.json")

    # Capture bus state
    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
