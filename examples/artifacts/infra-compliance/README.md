# infra-compliance — Infrastructure Compliance Scanner

Three agents (designer, scanner, fixer) collaborate via the a2a bus to produce
an infrastructure compliance report by scanning a Terraform configuration with
[checkov](https://www.checkov.io/).

## How it works

1. **Designer** proposes a sample Terraform configuration with intentional
   security anti-patterns (hardcoded credentials, public S3 buckets, overly
   permissive security groups, wide-open IAM policies)
2. **Scanner** receives the config, writes it to a temp file, and runs
   `checkov -f main.tf --compact --output json` to detect CIS, HIPAA, GDPR,
   and AWS best practice violations
3. **Fixer** reads the scanner's categorized findings and produces a markdown
   compliance report with severity breakdown, per-finding details, and ordered
   remediation recommendations

## Output

| File | Description |
|------|-------------|
| `output/compliance-report.md` | Formatted compliance report with executive summary, severity breakdown, findings, remediation recommendations, and the scanned terraform config |
| `output/raw-scan.json` | Raw checkov JSON output (72KB, all findings) |
| `output/bus-state.txt` | a2a bus message history |

## Requirements

- **a2a** and **a2a-spawn** on PATH
- An AI CLI (`claude`, `opencode`, or `pi`) for agent collaboration
- `checkov` via pip (`pip install checkov`) for fallback scanning

## Running

```bash
python3 examples/artifacts/infra-compliance/build.py --cli opencode --project artifact-infra-compliance
```

If AI agents hit API limits, the build script generates the compliance report
directly via checkov scanning — so the artifact is always produced.
