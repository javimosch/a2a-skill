#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: dependency-check.

Two agents (fetcher, reporter) collaborate via the a2a bus to produce a
security advisory report by analyzing project dependencies and searching
for known CVEs via ddgr.

Fetcher: reads go.mod and package.json for dependency lists
Reporter: searches ddgr for CVEs of each dependency, writes advisory

If agents hit API key limits, the build script falls back to generating
the advisory directly from ddgr search results.

Usage:
  python3 examples/artifacts/dependency-check/build.py [--project NAME] [--cli opencode]

Requires a2a, a2a-spawn, ddgr, and an AI CLI (claude, opencode, or pi).
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

ARTIFACT = "dependency-check"

# Paths to dependency files in the repo root (relative to this script)
REPO_ROOT = Path(__file__).parent.parent.parent.parent  # back to repo root
GO_MOD = REPO_ROOT / "go.mod"
CARGO_TOML = REPO_ROOT / "Cargo.toml"
PACKAGE_JSON = REPO_ROOT / "a2a_client.js"  # No package.json, use the JS client file

FETCHER_INSTRUCTIONS = (
    "You are the dependency fetcher for a2a-skill, a Go+Python+JS+Rust project.\n\n"
    "You have shell access. Read dependency files and extract the dependency list.\n\n"
    "Steps:\n"
    "1. Read the Go module dependencies:\n"
    '   cat go.mod | grep -E "^\\\\t" | head -30\n'
    "2. Read the Python imports from the main files:\n"
    '   grep "^import\\\\|^from" a2a.py a2a_client.py 2>/dev/null\n'
    "3. Combine all unique dependency names into a structured list\n"
    "4. Send the full dependency list to the reporter:\n"
    '   a2a send reporter "DEPS_START\\n<dependency list with one per line>\\nDEPS_END" --from fetcher\n\n'
    "Include the dependency name and source file for each entry."
)

REPORTER_INSTRUCTIONS = (
    "You are the security reporter. You search for CVEs of each dependency.\n\n"
    "Tools available:\n"
    '  ddgr --json -n 5 "<dependency> CVE vulnerability"\n\n'
    "Steps:\n"
    "1. Wait for the fetcher to send the dependency list:\n"
    '   a2a recv --as reporter --wait 60\n'
    "2. For each unique dependency, search ddgr for known CVEs:\n"
    '   ddgr --json -n 5 "<dependency> CVE security vulnerability"\n'
    "3. Group findings by dependency\n"
    "4. Write a markdown advisory with:\n"
    "   - Summary section with total dependencies checked and findings count\n"
    "   - Per-dependency section with CVE info (if any)\n"
    "   - Severity classification (Critical/High/Medium/Low/None)\n"
    "   - Recommendations section\n"
    "5. Broadcast the advisory:\n"
    '   a2a send all "ADVISORY_START\\n<full advisory>\\nADVISORY_END" --from reporter'
)

def read_go_deps() -> list:
    """Parse go.mod and return list of Go dependency dicts."""
    deps = []
    try:
        with open(GO_MOD) as f:
            in_require = False
            for line in f:
                line_stripped = line.strip()
                if line_stripped.startswith("require (") or line_stripped == "require":
                    in_require = True
                    continue
                if in_require and line_stripped.startswith(")"):
                    in_require = False
                    continue
                if in_require:
                    # Lines inside require (...) block
                    parts = line_stripped.split()
                    if len(parts) >= 2 and "/" in parts[0]:
                        name = parts[0].split("/")[-1]
                        version = parts[1] if len(parts) > 1 else "unknown"
                        deps.append({"name": name, "source": "go.mod", "version": version})
                elif line_stripped.startswith("\t") and "/" in line_stripped:
                    # Multi-line in require block
                    parts = line_stripped.split()
                    if len(parts) >= 1 and "/" in parts[0]:
                        name = parts[0].split("/")[-1]
                        version = parts[1] if len(parts) > 1 else "unknown"
                        deps.append({"name": name, "source": "go.mod", "version": version})
                elif line_stripped.startswith("require ") and "/" in line_stripped:
                    # Single-line: require <dep> <version>
                    parts = line_stripped.split()
                    for i, p in enumerate(parts):
                        if "/" in p and i > 0:  # After "require"
                            name = p.split("/")[-1]
                            version = parts[i + 1] if i + 1 < len(parts) else "unknown"
                            deps.append({"name": name, "source": "go.mod", "version": version})
    except FileNotFoundError:
        print(f"  [go.mod] Not found at {GO_MOD}")
    return deps

def read_cargo_deps() -> list:
    """Parse Cargo.toml and return list of Rust dependency dicts."""
    deps = []
    try:
        with open(CARGO_TOML) as f:
            in_deps = False
            for line in f:
                ls = line.strip()
                if ls == "[dependencies]":
                    in_deps = True
                    continue
                if in_deps and ls.startswith("["):
                    break
                if in_deps and "=" in ls and not ls.startswith("#"):
                    name = ls.split("=")[0].strip()
                    version_part = "=".join(ls.split("=")[1:]).strip()
                    # Handle { version = "...", features = [...] } syntax
                    if "version" in version_part:
                        import re
                        m = re.search(r'version\s*=\s*"([^"]+)"', version_part)
                        version = m.group(1) if m else "unknown"
                    elif version_part.startswith('"') or version_part.startswith("'"):
                        version = version_part.strip('"').strip("'").strip()
                    else:
                        version = "unknown"
                    deps.append({"name": name, "source": "Cargo.toml", "version": version})
    except FileNotFoundError:
        print(f"  [Cargo.toml] Not found at {CARGO_TOML}")
    return deps

def read_python_imports() -> list:
    """Scan Python files for third-party imports, excluding stdlib."""
    stdlib = {"os", "sys", "json", "time", "math", "argparse", "textwrap", "sqlite3",
              "subprocess", "tempfile", "pathlib", "atexit", "signal", "shlex",
              "collections", "io", "re", "copy", "typing", "abc", "enum", "dataclasses",
              "hashlib", "uuid", "csv", "urllib", "platform", "itertools", "functools",
              "random", "string", "struct", "threading", "traceback", "xml", "zipfile",
              "http", "socket", "ssl", "email", "html", "base64", "binascii", "calendar",
              "datetime", "decimal", "difflib", "filecmp", "fnmatch", "fractions",
              "getopt", "getpass", "glob", "gzip", "hmac", "imp", "importlib",
              "inspect", "logging", "lzma", "mmap", "multiprocessing", "netrc",
              "numbers", "operator", "optparse", "pickle", "pkgutil", "pprint",
              "profile", "pstats", "pty", "pwd", "queue", "quopri", "reprlib",
              "rlcompleter", "runpy", "secrets", "select", "selectors", "shelve",
              "shutil", "signal", "smtpd", "smtplib", "sndhdr", "spwd", "statistics",
              "stringprep", "struct", "sunau", "symtable", "sysconfig", "tabnanny",
              "tarfile", "telnetlib", "test", "textwrap", "tkinter", "token", "tokenize",
              "trace", "tty", "turtle", "unittest", "venv", "warnings", "wave",
              "weakref", "webbrowser", "wsgiref", "xdrlib", "xmlrpc", "zipapp",
              "zoneinfo", "configparser", "ctypes", "curses", "dbm", "distutils",
              "asyncio", "contextlib", "concurrent"}
    deps = []
    for pyfile in ["a2a.py", "a2a_client.py", "a2a_client_async.py", "a2a_audit.py",
                    "a2a_crypto.py", "a2a_fts.py", "a2a_priority.py",
                    "a2a_priority_async.py", "a2a_routing.py", "a2a_routing_async.py",
                    "a2a_git_aware.py", "a2a_server.py", "benchmark.py", "dashboard.py"]:
        path = REPO_ROOT / pyfile
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("import ") or line.startswith("from "):
                        parts = line.split()
                        if len(parts) >= 2:
                            name = parts[1].split(".")[0]
                            if name not in stdlib and name not in {"__future__"}:
                                deps.append({"name": name, "source": pyfile, "version": "unknown"})
        except FileNotFoundError:
            pass
    return deps

def run_ddgr(query: str) -> list:
    """Run a ddgr search and return parsed JSON results."""
    try:
        safe_query = query.replace('"', '\\"')
        cmd = f'ddgr --json -n 5 "{safe_query}"'
        result = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if isinstance(data, list):
                return data
        return []
    except Exception as exc:
        print(f"  [ddgr] Failed: {exc}", file=sys.stderr)
        return []

def search_cve(dep_name: str) -> list:
    """Search ddgr for CVE info about a dependency."""
    results = []
    for query in [
        f'{dep_name} CVE security vulnerability',
        f'{dep_name} CVE advisory github',
    ]:
        data = run_ddgr(query)
        for r in data:
            title = r.get("title", "")
            url = r.get("url", "")
            abstract = r.get("abstract", "")
            if any(kw in (title + abstract).lower() for kw in ["cve", "vulnerability", "security", "advisory", "fix"]):
                results.append({"title": title, "url": url, "abstract": abstract})
        if results:
            break  # Found some CVEs, no need for second query
    return results

def generate_fallback_advisory(deps: list) -> str:
    """Produce a security advisory from ddgr CVE searches directly."""
    print(f"[{ARTIFACT}] Generating fallback advisory from ddgr CVE searches...")
    lines = [
        "# Security Advisory — a2a-skill Dependencies",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Summary",
        "",
    ]

    results = []
    for dep in deps:
        print(f"  Checking {dep['name']} (from {dep['source']})...")
        cves = search_cve(dep["name"])
        severity = "High" if cves else "None"
        if cves:
            # Count CVE mentions
            cve_count = sum(1 for r in cves if "CVE-" in r.get("title", "") + r.get("abstract", ""))
            if cve_count > 2:
                severity = "Critical"
            elif cve_count > 0:
                severity = "High"
        results.append({**dep, "cves": cves, "severity": severity})

    checked = len(deps)
    findings = sum(1 for r in results if r["cves"])
    high_findings = sum(1 for r in results if r["severity"] in ("Critical", "High"))

    lines.append(f"- **Dependencies checked:** {checked}")
    lines.append(f"- **Dependencies with CVE findings:** {findings}")
    lines.append(f"- **High/Critical severity:** {high_findings}")
    lines.append(f"- **Recommendation:** {'Review high-severity findings immediately' if high_findings else 'No urgent issues detected'}")
    lines.append("")

    # Per-dependency details
    for r in sorted(results, key=lambda x: x["severity"], reverse=True):
        if r["severity"] == "None" and r["name"] in ("sqlite3",):
            continue  # Skip common stdlib-adjacent deps with no findings

        if r["severity"] != "None" or r["cves"]:
            lines.append(f"### {r['name']}")
            lines.append(f"")
            lines.append(f"- **Source:** {r['source']}")
            lines.append(f"- **Version:** {r['version']}")
            lines.append(f"- **Severity:** {r['severity']}")
            if r["cves"]:
                lines.append(f"- **Findings ({len(r['cves'])}):**")
                for cve in r["cves"][:3]:
                    title = cve.get("title", "").replace("[", "").replace("]", "")
                    url = cve.get("url", "")
                    abstract = cve.get("abstract", "")
                    lines.append(f"  - **{title}** — {abstract[:100]}")
                    if url:
                        lines.append(f"    [{url}]({url})")
            else:
                lines.append(f"- **Findings:** No CVEs found in search results")
            lines.append("")

    # Include clean deps summary
    clean = [r for r in results if not r["cves"]]
    if clean:
        lines.append("### Clean Dependencies (no CVE findings)")
        lines.append("")
        for r in clean:
            lines.append(f"- {r['name']} ({r['source']}, {r['version']})")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    if high_findings:
        lines.append(f"1. **Immediate action:** {high_findings} dependencies have High/Critical severity findings.")
        lines.append("2. **Update priority:** Update affected dependencies to latest versions.")
        lines.append("3. **Monitor:** Subscribe to GitHub Advisory Database for these packages.")
    else:
        lines.append("1. **Current status:** No critical vulnerabilities detected in the dependency tree.")
        lines.append("2. **Best practice:** Run this check regularly to catch new CVEs as they are published.")
        lines.append("3. **Monitor:** Consider setting up Dependabot or Renovate for automated updates.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Advisory generated by a2a dependency-check artifact using live ddgr web search.*")

    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Build dependency security advisory via agent collaboration")
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

    # Step 1: Read dependency files from the repo
    print(f"[{ARTIFACT}] Reading project dependencies...")
    go_deps = read_go_deps()
    cargo_deps = read_cargo_deps()
    py_deps = read_python_imports()
    all_deps = go_deps + cargo_deps + py_deps
    # Deduplicate by name
    seen = set()
    unique_deps = []
    for d in all_deps:
        if d["name"] not in seen:
            seen.add(d["name"])
            unique_deps.append(d)
    print(f"[{ARTIFACT}] Found {len(unique_deps)} unique dependencies ({len(go_deps)} Go, {len(cargo_deps)} Rust, {len(py_deps)} Python)")

    # Init bus
    run_a2a("init", a2a_bin, project)
    run_a2a("clear --yes", a2a_bin, project)
    run_a2a("register collector --role build-script --cli python", a2a_bin, project)

    agents = [
        {"id": "fetcher", "role": "dependency fetcher", "task": FETCHER_INSTRUCTIONS},
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
    api_errors = check_agent_logs(agent_ids, ARTIFACT)
    all_agents_failed = not spawned_ok or api_errors
    final_advisory = None

    if all_agents_failed:
        print(f"[{ARTIFACT}] Agents have API/startup issues — skipping agent wait loop, generating fallback directly...")
    else:
        # Send tasks via stdin
        for ag in agents:
            send_task(a2a_bin, project, ag["id"], f"Your task: {ag['task']}")
            print(f"[{ARTIFACT}] → sent task to {ag['id']}")

        # Wait for agent-produced advisory
        print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
        deadline = time.time() + args.timeout
        final_advisory = None

        while time.time() < deadline:
            msgs = run_a2a_json("recv --as collector --wait 30", a2a_bin, project)
            for msg in msgs if isinstance(msgs, list) else []:
                sender = msg.get("sender", "")
                body = msg.get("body", "")
                if sender == "reporter" and "ADVISORY_START" in body:
                    start_idx = body.find("ADVISORY_START") + len("ADVISORY_START")
                    end_idx = body.find("ADVISORY_END")
                    if end_idx > start_idx:
                        final_advisory = body[start_idx:end_idx].strip()
                    else:
                        final_advisory = body.replace("ADVISORY_START", "").replace("ADVISORY_END", "").strip()
                    print(f"[{ARTIFACT}] ← Received agent-produced advisory ({len(final_advisory)} chars)")
                    break
            if final_advisory:
                break

    # Write output — fallback to generated advisory if agents failed
    advisory_path = output_dir / "advisory.md"
    if final_advisory:
        advisory_path.write_text(final_advisory)
        print(f"[{ARTIFACT}] Wrote output/advisory.md (agent-produced, {len(final_advisory)} chars)")
    else:
        print(f"[{ARTIFACT}] No agent-produced advisory. Generating fallback from ddgr...")
        fallback = generate_fallback_advisory(unique_deps)
        advisory_path.write_text(fallback)
        print(f"[{ARTIFACT}] Wrote output/advisory.md (fallback, {len(fallback)} chars)")

    # Capture bus state
    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")

if __name__ == "__main__":
    main()
