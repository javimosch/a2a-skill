# Security Audit

A collaborative security posture report generator. Two agents (scanner, reporter)
collaborate via the a2a bus to research current security vulnerabilities and
assess system configuration.

## Output

| File | Description |
|------|-------------|
| `output/report.md` | Formatted security report with severity classification, per-category findings, system assessment, and recommendations |
| `output/raw-findings.json` | Raw ddgr search results and system check data |
| `output/bus-state.txt` | Full bus state log showing all agent communication |

## Agent roles

| Agent | Role | Tools |
|-------|------|-------|
| **scanner** | Searches ddgr for CVEs across 3 categories (web frameworks, AI/ML, kernel) and runs system security checks | `ddgr --json -n 8`, `df -h`, `ss -tlnp`, `uptime`, `dmesg` |
| **reporter** | Categorizes findings by severity (Critical/High/Medium/Low) and writes a formatted markdown report with executive summary | `a2a recv/send` |

## How it works

1. **scanner** searches ddgr for latest CVEs in web frameworks, AI/ML tools, and operating system/kernel vulnerabilities
2. **scanner** runs system health checks (disk usage, listening ports, uptime, kernel errors)
3. **scanner** sends all findings to **reporter** via the a2a bus
4. **reporter** categorizes each finding by severity and writes a formatted report with:
   - Executive summary with risk score (0-10)
   - Severity distribution chart
   - Per-category findings with CVEs, impact, and severity
   - System configuration assessment with recommendations
5. **reporter** broadcasts the completed report to the bus

If agents hit API key limits, the build script falls back to performing the
searches directly using ddgr and generating the report from raw results.

## Running

```bash
python3 examples/artifacts/security-audit/build.py --cli opencode
```

Requires: a2a, a2a-spawn, ddgr, and an AI CLI (opencode, claude, or pi).
