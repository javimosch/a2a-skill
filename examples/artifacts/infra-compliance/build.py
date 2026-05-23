#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: infra-compliance.

Three agents (designer, scanner, fixer) collaborate via the a2a bus to
produce an infrastructure compliance report.

Designer: proposes a sample Terraform configuration on the bus
Scanner:  runs checkov against the config, extracts compliance findings
Fixer:    reads findings and writes remediation recommendations

If the AI CLI hits an API key limit, falls back to generating the terraform
config directly, scanning it with checkov, and producing the report.

Usage:
  python3 examples/artifacts/infra-compliance/build.py [--project NAME] [--cli opencode]

Requires a2a, a2a-spawn, checkov (pip install checkov), and an AI CLI
(claude, opencode, or pi).
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
from _util import find_a2a, find_spawn, run_a2a, run_a2a_json, spawn_agent, make_kit, send_task, check_agent_logs, SpawnManager  # noqa: E402

ARTIFACT = "infra-compliance"

DESIGNER_INSTRUCTIONS = (
    "You are the infrastructure designer. Propose a sample Terraform configuration.\n\n"
    "You have shell access. Create a small but realistic Terraform config.\n\n"
    "Steps:\n"
    "1. Write a Terraform configuration that provisions:\n"
    "   - An AWS VPC with a public subnet\n"
    "   - A security group with overly permissive ingress (0.0.0.0/0 on SSH)\n"
    "   - An S3 bucket without versioning or encryption\n"
    "   - An IAM user with admin permissions\n"
    "   - Tags on resources where practical\n"
    "2. The config should intentionally include some security anti-patterns:\n"
    "   - Hardcoded passwords or access keys\n"
    "   - Public S3 bucket\n"
    "   - Overly permissive security group rules\n"
    "   - Missing encryption settings\n"
    "3. Send the complete Terraform config to the scanner:\n"
    '   a2a send scanner "TF_START\n<your terraform config>\nTF_END" --from designer\n\n'
    "Important: Use realistic HCL syntax. Include provider block, resource blocks, "
    "and at least one variable definition. Wrap in ```hcl if needed."
)

SCANNER_INSTRUCTIONS = (
    "You are the compliance scanner. You scan Terraform configurations for security issues.\n\n"
    "Tools available:\n"
    '  checkov -d /tmp/scanner-work  -- framework scan of directory\n'
    '  checkov -f /tmp/scanner-work/main.tf --json  # JSON output\n\n'
    "Steps:\n"
    "1. Wait for the designer to send the Terraform config:\n"
    '   a2a recv --as scanner --wait 60\n'
    "2. Save the config to /tmp/scanner-work/main.tf\n"
    '   mkdir -p /tmp/scanner-work && cat > /tmp/scanner-work/main.tf << \'EOF\'\n'
    "   <paste the terraform config here>\n"
    "   EOF\n"
    "3. Run checkov against the config:\n"
    '   checkov -f /tmp/scanner-work/main.tf --compact --quiet\n'
    "4. Also try with JSON output:\n"
    '   checkov -f /tmp/scanner-work/main.tf --compact --quiet --output json 2>/dev/null\n'
    "5. Categorize findings by severity (CRITICAL/HIGH/MEDIUM/LOW)\n"
    "6. Send structured findings to the fixer:\n"
    '   a2a send fixer "FINDINGS_START\n<your findings grouped by severity>\nFINDINGS_END" --from scanner'
)

FIXER_INSTRUCTIONS = (
    "You are the compliance fixer. You receive findings from the scanner\n"
    "and produce remediation recommendations.\n\n"
    "Steps:\n"
    "1. Wait for the scanner to send findings:\n"
    '   a2a recv --as fixer --wait 60\n'
    "2. For each finding, propose a fix:\n"
    "   - Critical/High: concrete code change, resource modification, or config update\n"
    "   - Medium: best practice improvement, monitoring addition\n"
    "   - Low: documentation, tagging, minor config tweaks\n"
    "3. Write a markdown compliance report with:\n"
    "   - Executive summary (overall compliance score)\n"
    "   - Finding severity distribution\n"
    "   - Per-finding details with severity, check ID, resource, and fix\n"
    "   - Remediation summary (ordered by priority)\n"
    "4. Broadcast the report:\n"
    '   a2a send all "COMPLIANCE_REPORT_START\n<full markdown report>\nCOMPLIANCE_REPORT_END" --from fixer'
)

# --- Fallback functions ---

SAMPLE_TF = """# Intentionally insecure Terraform configuration for compliance scanning
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
  # Hardcoded access key — security anti-pattern CKV_AWS_41
  access_key = "AKIAIOSFODNN7EXAMPLE"
  secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
}

variable "bucket_name" {
  description = "Name of the S3 bucket"
  type        = string
  default     = "my-insecure-app-data-2026"
}

# VPC with public subnet
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name        = "main-vpc"
    Environment = var.environment
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true

  tags = {
    Name = "public-subnet"
  }
}

# Overly permissive security group — CKV_AWS_24, CKV_AWS_260
resource "aws_security_group" "web" {
  name        = "web-sg"
  description = "Security group for web server"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "SSH from anywhere"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # CKV_AWS_260:0.0.0.0/0 on SSH
  }

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "web-sg"
  }
}

# S3 bucket without encryption or versioning — CKV_AWS_19, CKV_AWS_145
resource "aws_s3_bucket" "data" {
  bucket = var.bucket_name
  acl    = "public-read"  # CKV_AWS_20: S3 bucket ACL public-read

  tags = {
    Name        = var.bucket_name
    Environment = var.environment
  }
}

# Missing server-side encryption config — CKV_AWS_19
# Missing versioning config — CKV_AWS_145

# IAM user with full admin — CKV_AWS_40, CKV_AWS_63
resource "aws_iam_user" "admin" {
  name = "admin-user"
  path = "/system/"

  tags = {
    Environment = var.environment
  }
}

resource "aws_iam_user_policy_attachment" "admin" {
  user       = aws_iam_user.admin.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"  # CKV_AWS_63: full admin
}

# Access key without rotation — CKV_AWS_46
resource "aws_iam_access_key" "admin" {
  user = aws_iam_user.admin.name
}
"""

def check_checkov() -> bool:
    """Check if checkov is available."""
    try:
        result = subprocess.run(["checkov", "--version"], capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def run_checkov_scan(tf_content: str) -> dict:
    """Run checkov against a terraform string and return parsed results."""
    workdir = Path(tempfile.mkdtemp(prefix="infra-compliance-"))
    tf_path = workdir / "main.tf"
    tf_path.write_text(tf_content)

    print(f"  [checkov] Scanning {tf_path}...")
    try:
        result = subprocess.run(
            ["checkov", "-f", str(tf_path), "--compact", "--output", "json"],
            capture_output=True, text=True, timeout=60,
        )
        # checkov exits 1 when checks fail (expected behavior), so check stdout regardless
        if result.stdout.strip():
            data = json.loads(result.stdout)
        else:
            print(f"  [checkov] No JSON output. stderr: {result.stderr[:200]}", file=sys.stderr)
            data = {"results": {"passed_checks": [], "failed_checks": []}}
    except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  [checkov] Error: {e}")
        data = {"results": {"passed_checks": [], "failed_checks": []}}

    # Clean up temp dir
    import shutil
    shutil.rmtree(workdir, ignore_errors=True)
    return data

def parse_checkov_results(data) -> dict:
    """Extract and categorize checkov findings.

    Handles both dict (single scanner) and list (multi-scanner) output formats.
    """
    categorized = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": [], "passed": []}

    # Normalize to list of result sections
    sections = data if isinstance(data, list) else [data]

    severity_map = {
        "CRITICAL": "CRITICAL",
        "HIGH": "HIGH",
        "MEDIUM": "MEDIUM",
        "LOW": "LOW",
    }

    for section in sections:
        results = section.get("results", {}) if isinstance(section, dict) else {}
        failed = results.get("failed_checks", [])
        passed = results.get("passed_checks", [])

        for check in failed:
            sev = check.get("severity")
            if sev and sev.upper() != "NONE":
                sev = severity_map.get(sev.upper(), "LOW")
            else:
                # Infer severity: CRITICAL if secret or hardcoded credential
                cid = check.get("check_id", "")
                cname = check.get("check_name", "").lower()
                if "secret" in cid.lower() or "akid" in cid.lower() or "secret" in cname:
                    sev = "CRITICAL"
                elif "iam" in cid.lower() and "admin" in cname:
                    sev = "HIGH"
                elif "public" in cname or "0.0.0.0" in cname:
                    sev = "HIGH"
                else:
                    sev = "MEDIUM"

            categorized[sev].append({
                "check_id": check.get("check_id", ""),
                "check_name": check.get("check_name", ""),
                "resource": check.get("resource", ""),
                "file_line": check.get("file_line", 0),
                "guideline": check.get("guideline", ""),
                "severity": sev,
                "status": "FAILED",
            })

        for check in passed:
            categorized["passed"].append({
                "check_id": check.get("check_id", ""),
                "check_name": check.get("check_name", ""),
                "resource": check.get("resource", ""),
                "severity": check.get("severity", "LOW"),
                "status": "PASSED",
            })

    return categorized

def generate_compliance_report(categorized: dict, total_checks: int) -> str:
    """Generate a formatted compliance report markdown."""
    failed_total = sum(len(v) for k, v in categorized.items() if k != "passed")
    passed_total = len(categorized.get("passed", []))
    total = failed_total + passed_total

    # Score: 100 - (failed_critical*25 + failed_high*10 + failed_medium*5 + failed_low*1)
    critical_w = len(categorized.get("CRITICAL", [])) * 25
    high_w = len(categorized.get("HIGH", [])) * 10
    medium_w = len(categorized.get("MEDIUM", [])) * 5
    low_w = len(categorized.get("LOW", [])) * 1
    penalty = critical_w + high_w + medium_w + low_w
    score = max(0, min(100, 100 - penalty)) if total > 0 else 100

    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 50:
        grade = "C"
    elif score >= 25:
        grade = "D"
    else:
        grade = "F"

    lines = [
        "# Infrastructure Compliance Report",
        "",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Scanner:** checkov",
        f"**Scope:** Terraform configuration compliance (CIS, HIPAA, GDPR, AWS best practices)",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        f"**Compliance Score: {score}/100 — Grade {grade}**",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| **Total Checks** | {total} |",
        f"| **Passed** | {passed_total} |",
        f"| **Failed** | {failed_total} |",
        f"| **Pass Rate** | {passed_total / max(total, 1) * 100:.1f}% |",
        f"| **Critical** | {len(categorized.get('CRITICAL', []))} |",
        f"| **High** | {len(categorized.get('HIGH', []))} |",
        f"| **Medium** | {len(categorized.get('MEDIUM', []))} |",
        f"| **Low** | {len(categorized.get('LOW', []))} |",
        "",
    ]

    if failed_total > 0:
        lines.append("### Severity Distribution")
        lines.append("")
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            count = len(categorized.get(sev, []))
            if count > 0:
                pct = count / failed_total * 100
                bar_len = max(1, int(pct / 5))
                bar = "█" * bar_len
                emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}
                lines.append(f"  {emoji.get(sev, '')} **{sev}**: {bar} ({count})")
        lines.append("")

    # Failed checks by severity
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        items = categorized.get(sev, [])
        if not items:
            continue
        emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}
        lines.append(f"### {emoji.get(sev, '')} {sev} Severity Findings ({len(items)})")
        lines.append("")
        for item in items:
            cid = item.get("check_id", "")
            cname = item.get("check_name", "")
            resource = item.get("resource", "")
            guideline = item.get("guideline", "")
            lines.append(f"- **{cid}**: {cname}")
            lines.append(f"  - Resource: `{resource}`")
            if guideline:
                lines.append(f"  - Guideline: [{guideline}]({guideline})")
        lines.append("")

    # Remediation recommendations
    lines.append("---")
    lines.append("")
    lines.append("## Remediation Recommendations")
    lines.append("")
    rec_num = 0

    for item in categorized.get("CRITICAL", []):
        rec_num += 1
        cid = item.get("check_id", "")
        cname = item.get("check_name", "")
        resource = item.get("resource", "")
        if "IAM" in cname or "iam" in cname or "admin" in cname or "AKIA" in cname:
            lines.append(f"{rec_num}. **Remove hardcoded AWS credentials** — Use IAM roles, instance profiles, or environment variables instead of hardcoded `access_key`/`secret_key` in provider config. ({cid})")
        elif "bucket" in resource.lower() or "s3" in cname.lower():
            lines.append(f"{rec_num}. **Enable S3 bucket encryption and versioning** — Set `server_side_encryption_configuration` with AES256 or aws:kms, enable `versioning` block, and remove `acl = public-read`. ({cid})")
        elif "security_group" in resource.lower() or "ssh" in cname.lower() or "0.0.0.0" in cname:
            lines.append(f"{rec_num}. **Restrict security group ingress** — Replace `0.0.0.0/0` with specific IP ranges (e.g., corporate VPN CIDR). Remove SSH (port 22) from public ingress entirely. ({cid})")
        elif "admin" in resource.lower():
            lines.append(f"{rec_num}. **Use least-privilege IAM policies** — Replace `AdministratorAccess` with scoped policies. Use IAM roles with trust policies instead of long-term users. ({cid})")
        else:
            lines.append(f"{rec_num}. **Fix {cid}** — Resource `{resource}`: {cname}")

    for item in categorized.get("HIGH", []):
        rec_num += 1
        cid = item.get("check_id", "")
        cname = item.get("check_name", "")
        resource = item.get("resource", "")
        lines.append(f"{rec_num}. **{cname}** (Resource: `{resource}`, {cid}) — Review and remediate per checkov guideline.")

    for item in categorized.get("MEDIUM", []):
        rec_num += 1
        cid = item.get("check_id", "")
        cname = item.get("check_name", "")
        resource = item.get("resource", "")
        lines.append(f"{rec_num}. **{cname}** (Resource: `{resource}`, {cid}) — Address as part of routine compliance maintenance.")

    if rec_num == 0:
        lines.append("1. **No remediation needed** — All checks passed.")
    else:
        lines.append(f"{rec_num + 1}. **Re-scan after fixes** — Run checkov after applying each remediation to verify the fix.")
        lines.append(f"{rec_num + 2}. **Integrate into CI/CD** — Add `checkov -f main.tf` to your CI pipeline to prevent new compliance violations.")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Example Terraform Configuration (Scanned)")
    lines.append("")
    lines.append("The following intentionally insecure Terraform configuration was scanned:")
    lines.append("")
    lines.append("```hcl")
    lines.append(SAMPLE_TF.strip())
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Report generated by a2a infra-compliance artifact using checkov.*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Build infrastructure compliance report via agent collaboration")
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

    # Check available tools
    has_checkov = check_checkov()
    print(f"[{ARTIFACT}] checkov available: {has_checkov}")

    # Init bus
    run_a2a("init", a2a_bin, project)
    run_a2a("clear --yes", a2a_bin, project)
    run_a2a("register collector --role build-script --cli python", a2a_bin, project)

    agents = [
        {"id": "designer", "role": "infrastructure designer", "task": DESIGNER_INSTRUCTIONS},
        {"id": "scanner", "role": "compliance scanner", "task": SCANNER_INSTRUCTIONS},
        {"id": "fixer", "role": "compliance fixer", "task": FIXER_INSTRUCTIONS},
    ]
    agent_ids = [ag["id"] for ag in agents]
    for ag in agents:
        run_a2a(f'register {ag["id"]} --role "{ag["role"]}\" --cli {args.cli}', a2a_bin, project)

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

    # Check for API errors
    api_errors = check_agent_logs(agent_ids, ARTIFACT)
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
                if sender == "fixer" and "COMPLIANCE_REPORT_START" in body:
                    start_idx = body.find("COMPLIANCE_REPORT_START") + len("COMPLIANCE_REPORT_START")
                    end_idx = body.find("COMPLIANCE_REPORT_END")
                    if end_idx > start_idx:
                        final_report = body[start_idx:end_idx].strip()
                    else:
                        final_report = body.replace("COMPLIANCE_REPORT_START", "").replace("COMPLIANCE_REPORT_END", "").strip()
                    print(f"[{ARTIFACT}] ← Received agent-produced report ({len(final_report)} chars)")
                    break
            if final_report:
                break

    # Write output
    report_path = output_dir / "compliance-report.md"
    if final_report:
        report_path.write_text(final_report)
        print(f"[{ARTIFACT}] Wrote output/compliance-report.md (agent-produced, {len(final_report)} chars)")
    elif has_checkov:
        print(f"[{ARTIFACT}] No agent-produced report. Generating fallback via checkov scan...")
        scan_data = run_checkov_scan(SAMPLE_TF)
        categorized = parse_checkov_results(scan_data)

        # Count totals
        total_checks = (
            sum(len(v) for v in categorized.values())
        )
        report = generate_compliance_report(categorized, total_checks)
        report_path.write_text(report)
        print(f"[{ARTIFACT}] Wrote output/compliance-report.md (fallback, {len(report)} chars)")

        # Also write raw scan results
        raw_path = output_dir / "raw-scan.json"
        raw_path.write_text(json.dumps(scan_data, indent=2, default=str))
        print(f"[{ARTIFACT}] Wrote output/raw-scan.json")
    else:
        print(f"[{ARTIFACT}] WARNING: checkov not available and no agent report. Writing placeholder report...")
        report_path.write_text(f"# Infrastructure Compliance Report — FAILED\n\nNo report was produced.\ncheckov was not installed and agents did not produce output.\n\nInstall checkov: `pip install checkov`\n")
        print(f"[{ARTIFACT}] Wrote output/compliance-report.md (placeholder)")

    # Capture bus state
    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")


if __name__ == "__main__":
    main()
