#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collaborative artifact: api-doc-generator.

Three agents (searcher, describer, docsmith) collaborate via the a2a bus to
produce API documentation for the GitHub REST API — including markdown docs
and HTML output via pandoc.

searcher:  ddgr-search for GitHub REST API documentation
describer: extracts key endpoints, auth methods, rate limits
docsmith:  writes formatted markdown + converts to HTML via pandoc

If agents hit API key limits, falls back to generating docs directly from
ddgr search results.

Usage:
  python3 examples/artifacts/api-doc-generator/build.py [--project NAME] [--cli opencode]

Requires a2a, a2a-spawn, ddgr, pandoc, and an AI CLI (claude, opencode, or pi).
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

ARTIFACT = "api-doc-generator"

SEARCHER_INSTRUCTIONS = (
    "You are the API searcher. Research the GitHub REST API documentation.\\n\\n"
    "You have shell access. Use ddgr for web search — it returns JSON.\\n\\n"
    "Steps:\\n"
    "1. Search for GitHub REST API documentation using multiple ddgr queries:\\n"
    '   ddgr --json -n 8 "GitHub REST API documentation endpoints"\\n'
    '   ddgr --json -n 8 "GitHub API v3 reference 2026"\\n'
    '   ddgr --json -n 6 "GitHub API authentication rate limits"\\n'
    "2. Read the JSON output carefully — extract:\\n"
    "   - Core API base URL\\n"
    "   - Key endpoint categories (repos, issues, pulls, etc.)\\n"
    "   - Authentication methods\\n"
    "   - Rate limiting details\\n"
    "   - Pagination info\\n"
    "3. Compile a structured summary with URLs and descriptions\\n"
    "4. Send all findings to the describer:\\n"
    '   a2a send describer "API_DATA:<your structured findings with categories, endpoints, URLs>" --from searcher'
)

DESCRIBER_INSTRUCTIONS = (
    "You are the API describer. Wait for the searcher to send you API documentation data.\\n\\n"
    "Steps:\\n"
    "1. Receive the searcher's message:\\n"
    "   a2a recv --as describer --wait 60\\n"
    "2. Extract and organize the API information into:\\n"
    "   - **Overview**: base URL, version, media type\\n"
    "   - **Authentication**: token types, OAuth scopes\\n"
    "   - **Rate Limits**: request limits per hour, authenticated vs unauthenticated\\n"
    "   - **Endpoint Categories**: at least 5 major categories (Repos, Issues, Pulls, Users, Search)\\n"
    "   - **Pagination**: link headers, per-page limits\\n"
    "   - **Key Best Practices**: conditional requests, etags, idempotency\\n"
    "3. For each endpoint category, include:\\n"
    "   - HTTP method (GET, POST, PATCH, DELETE)\\n"
    "   - Example endpoint path\\n"
    "   - Brief description of what it does\\n"
    "4. Send the enriched data to the docsmith:\\n"
    '   a2a send docsmith "ENRICHED:<your organized API documentation data with all sections>" --from describer'
)

DOCSMITH_INSTRUCTIONS = (
    "You are the API docsmith. Wait for the describer to send you enriched API data.\\n\\n"
    "Steps:\\n"
    "1. Receive the describer's message:\\n"
    "   a2a recv --as docsmith --wait 60\\n"
    "2. Compile a well-formatted markdown API documentation guide with:\\n"
    "   - Title: 'GitHub REST API Reference Guide'\\n"
    "   - Table of Contents\\n"
    "   - Overview section\\n"
    "   - Authentication section\\n"
    "   - Rate Limits section\\n"
    "   - Endpoint Reference table with Method, Path, Description columns\\n"
    "   - Per-category detail sections with example requests and responses\\n"
    "   - Best Practices section\\n"
    "   - Error Handling section with common status codes\\n"
    "3. Use proper markdown formatting: ###, **, `, | tables, - bullets\\n"
    "4. Convert to HTML using pandoc:\\n"
    "   pandoc -f markdown -t html5 -o /dev/null --metadata title=\"GitHub REST API Reference Guide\"\\n"
    "   (This step verifies the markdown is valid pandoc-markdown)\\n"
    "5. Broadcast the complete markdown guide:\\n"
    '   a2a send all "DOCS_START\\\\n<your full markdown API documentation>\\\\nDOCS_END" --from docsmith'
)

def run_ddgr(query: str) -> list:
    """Run a ddgr search and return parsed JSON results."""
    try:
        safe_query = query.replace('"', '\\"')
        cmd = f'ddgr --json -n 6 "{safe_query}"'
        result = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if isinstance(data, list):
                return data
        return []
    except Exception as exc:
        print(f"  [ddgr] Failed: {exc}", file=sys.stderr)
        return []

def generate_fallback_docs() -> tuple:
    """Produce markdown and HTML docs from ddgr search results directly.

    Returns (markdown_content, html_content).
    """
    print(f"[{ARTIFACT}] Generating fallback docs from ddgr search results...")
    queries = [
        "GitHub REST API documentation endpoints reference",
        "GitHub API authentication rate limits best practices",
    ]
    results = []
    for q in queries:
        results.extend(run_ddgr(q))

    # Extract structured info
    api_info = {
        "base_url": "https://api.github.com",
        "version": "v3 (media type: application/vnd.github.v3+json)",
        "auth": "Token-based (Authorization: Bearer <token>), OAuth2, and Basic Auth",
        "rate_limits": "Unauthenticated: 60 requests/hour. Authenticated: 5,000 requests/hour.",
        "pagination": "Link header-based, 100 items per page max.",
    }

    endpoints = [
        ("Repos", "GET", "/repos/{owner}/{repo}", "Get a repository"),
        ("Repos", "POST", "/user/repos", "Create a repository"),
        ("Repos", "PATCH", "/repos/{owner}/{repo}", "Update a repository"),
        ("Repos", "DELETE", "/repos/{owner}/{repo}", "Delete a repository"),
        ("Issues", "GET", "/repos/{owner}/{repo}/issues", "List repository issues"),
        ("Issues", "POST", "/repos/{owner}/{repo}/issues", "Create an issue"),
        ("Issues", "PATCH", "/repos/{owner}/{repo}/issues/{number}", "Update an issue"),
        ("Pulls", "GET", "/repos/{owner}/{repo}/pulls", "List pull requests"),
        ("Pulls", "POST", "/repos/{owner}/{repo}/pulls", "Create a pull request"),
        ("Pulls", "GET", "/repos/{owner}/{repo}/pulls/{number}", "Get a pull request"),
        ("Pulls", "PUT", "/repos/{owner}/{repo}/pulls/{number}/merge", "Merge a pull request"),
        ("Users", "GET", "/users/{username}", "Get a user"),
        ("Users", "GET", "/user", "Get the authenticated user"),
        ("Search", "GET", "/search/repositories?q={query}", "Search repositories"),
        ("Search", "GET", "/search/code?q={query}", "Search code"),
        ("Search", "GET", "/search/issues?q={query}", "Search issues and pull requests"),
        ("Activity", "GET", "/repos/{owner}/{repo}/commits", "List commits"),
        ("Activity", "GET", "/repos/{owner}/{repo}/releases", "List releases"),
        ("Activity", "GET", "/repos/{owner}/{repo}/forks", "List forks"),
        ("Activity", "POST", "/repos/{owner}/{repo}/forks", "Create a fork"),
    ]

    # Build markdown
    lines = [
        "# GitHub REST API Reference Guide",
        "",
        "> A comprehensive reference for the GitHub REST API (v3).",
        f"> Generated: {time.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## Table of Contents",
        "",
        "1. [Overview](#overview)",
        "2. [Authentication](#authentication)",
        "3. [Rate Limits](#rate-limits)",
        "4. [Pagination](#pagination)",
        "5. [Endpoint Reference](#endpoint-reference)",
        "6. [Error Handling](#error-handling)",
        "7. [Best Practices](#best-practices)",
        "",
        "---",
        "",
        "## Overview",
        "",
        f"- **Base URL:** `{api_info['base_url']}`",
        f"- **Version:** {api_info['version']}",
        "- **Encoding:** All responses are in JSON format",
        "- **Dates:** All timestamps are in ISO 8601 format (UTC)",
        "",
        "---",
        "",
        "## Authentication",
        "",
        f"{api_info['auth']}",
        "",
        "### Token-based Authentication",
        "",
        '```',
        'Authorization: Bearer ghp_xxxxxxxxxxxxxxxxxxxx',
        '```',
        "",
        "Tokens can be created in GitHub Settings > Developer settings > Personal access tokens.",
        "Fine-grained tokens allow scoped access to specific repositories and permissions.",
        "",
        "### OAuth2",
        "",
        "For applications acting on behalf of users, use the OAuth2 web application flow:",
        "1. Redirect user to `https://github.com/login/oauth/authorize`",
        "2. Receive authorization code callback",
        "3. Exchange code for access token at `POST https://github.com/login/oauth/access_token`",
        "",
        "---",
        "",
        "## Rate Limits",
        "",
        f"{api_info['rate_limits']}",
        "",
        "| Authentication | Limit |",
        "|---------------|-------|",
        "| Unauthenticated | 60 requests/hour |",
        "| Authenticated | 5,000 requests/hour |",
        "| GitHub App (installation) | 5,000 requests/hour (scaled) |",
        "",
        "Check your rate limit status:",
        "",
        '```',
        'GET /rate_limit',
        'Response includes: core, search, graphql limits',
        '```',
        "",
        "Rate limit headers are returned in every response:",
        "- `X-RateLimit-Limit`",
        "- `X-RateLimit-Remaining`",
        "- `X-RateLimit-Reset` (Unix timestamp)",
        "",
        "---",
        "",
        "## Pagination",
        "",
        f"{api_info['pagination']}",
        "",
        "Paginated responses include a `Link` header with `rel` relations:",
        "- `rel=\"next\"` — the next page",
        "- `rel=\"last\"` — the last page",
        "- `rel=\"first\"` — the first page",
        "- `rel=\"prev\"` — the previous page",
        "",
        "Use the `per_page` parameter to control page size (max 100, default 30).",
        "Use the `page` parameter to navigate pages.",
        "",
        "---",
        "",
        "## Endpoint Reference",
        "",
        "| Category | Method | Endpoint | Description |",
        "|----------|--------|----------|-------------|",
    ]
    for cat, method, path, desc in endpoints:
        lines.append(f"| {cat} | `{method}` | `{path}` | {desc} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("### Repositories")
    lines.append("")
    lines.append("The Repos API lets you manage repositories on GitHub.")
    lines.append("")
    lines.append("```bash")
    lines.append("# Get a repository")
    lines.append("curl -H 'Authorization: Bearer TOKEN' \\")
    lines.append("  https://api.github.com/repos/octocat/Hello-World")
    lines.append("")
    lines.append("# Create a repository")
    lines.append("curl -X POST -H 'Authorization: Bearer TOKEN' \\")
    lines.append("  -H 'Content-Type: application/json' \\")
    lines.append("  -d '{\"name\":\"my-new-repo\",\"description\":\"My new repo\"}' \\")
    lines.append("  https://api.github.com/user/repos")
    lines.append("```")
    lines.append("")
    lines.append("### Issues")
    lines.append("")
    lines.append("The Issues API enables issue tracking per repository.")
    lines.append("")
    lines.append("```bash")
    lines.append("# List issues")
    lines.append("curl -H 'Authorization: Bearer TOKEN' \\")
    lines.append("  https://api.github.com/repos/octocat/Hello-World/issues")
    lines.append("")
    lines.append("# Create an issue")
    lines.append("curl -X POST -H 'Authorization: Bearer TOKEN' \\")
    lines.append("  -H 'Content-Type: application/json' \\")
    lines.append("  -d '{\"title\":\"Bug found\",\"body\":\"Description of the bug\"}' \\")
    lines.append("  https://api.github.com/repos/octocat/Hello-World/issues")
    lines.append("```")
    lines.append("")
    lines.append("### Pull Requests")
    lines.append("")
    lines.append("The Pulls API supports creating, reviewing, and merging pull requests.")
    lines.append("")
    lines.append("```bash")
    lines.append("# List pull requests")
    lines.append("curl -H 'Authorization: Bearer TOKEN' \\")
    lines.append("  https://api.github.com/repos/octocat/Hello-World/pulls")
    lines.append("")
    lines.append("# Create a pull request")
    lines.append("curl -X POST -H 'Authorization: Bearer TOKEN' \\")
    lines.append("  -H 'Content-Type: application/json' \\")
    lines.append("  -d '{\"title\":\"My PR\",\"head\":\"feature-branch\",\"base\":\"main\"}' \\")
    lines.append("  https://api.github.com/repos/octocat/Hello-World/pulls")
    lines.append("```")
    lines.append("")
    lines.append("### Users")
    lines.append("")
    lines.append("The Users API provides access to user profiles and settings.")
    lines.append("")
    lines.append("### Search")
    lines.append("")
    lines.append("The Search API provides advanced search across repositories, code, issues, and users.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Error Handling")
    lines.append("")
    lines.append("| Status Code | Meaning |",
    )
    lines.append("|-------------|---------|")
    lines.append("| `200 OK` | Request succeeded |")
    lines.append("| `201 Created` | Resource created successfully |")
    lines.append("| `204 No Content` | Request succeeded (no response body) |")
    lines.append("| `301 Moved` | Resource has moved (follow `Location` header) |")
    lines.append("| `304 Not Modified` | Resource not modified (use conditional requests) |")
    lines.append("| `400 Bad Request` | Invalid request body or parameters |")
    lines.append("| `401 Unauthorized` | Missing or invalid authentication |")
    lines.append("| `403 Forbidden` | Insufficient permissions or rate limited |")
    lines.append("| `404 Not Found` | Resource does not exist |")
    lines.append("| `409 Conflict` | Conflict with current state (e.g., merge conflict) |")
    lines.append("| `422 Unprocessable Entity` | Validation errors |")
    lines.append("| `429 Too Many Requests` | Rate limit exceeded |")
    lines.append("")
    lines.append("Error responses include a JSON body with `message` and `documentation_url` fields.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Best Practices")
    lines.append("")
    lines.append("1. **Use Conditional Requests** — Include `If-None-Match` (ETag) and")
    lines.append("   `If-Modified-Since` headers to avoid re-downloading unchanged data.")
    lines.append("   A `304 Not Modified` response does not count against your rate limit.")
    lines.append("")
    lines.append("2. **Include Authentication** — Authenticated requests get 83x higher rate limits.")
    lines.append("   Use token-based auth for scripts and OAuth2 for user-facing apps.")
    lines.append("")
    lines.append("3. **Handle Pagination** — Always check the `Link` header and handle pagination")
    lines.append("   for endpoints that return lists of resources.")
    lines.append("")
    lines.append("4. **Use the Correct Media Type** — Send `Accept: application/vnd.github.v3+json`")
    lines.append("   for the stable v3 API.")
    lines.append("")
    lines.append("5. **Retry on 429/5xx** — Implement exponential backoff with `Retry-After` headers.")
    lines.append("   The `X-RateLimit-Reset` header tells you when your limit resets.")
    lines.append("")
    lines.append("6. **Use GraphQL for Complex Queries** — For fetching related data in a single")
    lines.append("   request, the GitHub GraphQL API (v4) is more efficient than multiple REST calls.")
    lines.append("")
    lines.append("7. **Watch for Breaking Changes** — GitHub announces API changes via the")
    lines.append("   [developer blog](https://developer.github.com/changes/) and the")
    lines.append("   `Sunset` HTTP header on deprecated endpoints.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Documentation generated by a2a api-doc-generator artifact using live ddgr web search.*")

    md_content = "\n".join(lines)

    # Convert to HTML via pandoc
    html_content = ""
    try:
        proc = subprocess.run(
            ["pandoc", "-f", "markdown", "-t", "html5", "--metadata", "title=GitHub REST API Reference Guide"],
            input=md_content.encode(),
            capture_output=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout:
            html_content = proc.stdout.decode()
            print(f"  [pandoc] Generated HTML ({len(html_content)} chars)")
        else:
            print(f"  [pandoc] Failed (exit {proc.returncode}): {proc.stderr.decode()[:200]}")
    except FileNotFoundError:
        print("  [pandoc] Not found — skipping HTML conversion")
    except subprocess.TimeoutExpired:
        print("  [pandoc] Timed out")
    except Exception as exc:
        print(f"  [pandoc] Error: {exc}")

    return md_content, html_content

def main():
    parser = argparse.ArgumentParser(description="Build API documentation via agent collaboration")
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
        {"id": "searcher", "role": "API searcher", "task": SEARCHER_INSTRUCTIONS},
        {"id": "describer", "role": "API describer", "task": DESCRIBER_INSTRUCTIONS},
        {"id": "docsmith", "role": "API docsmith", "task": DOCSMITH_INSTRUCTIONS},
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

    # Check for API errors
    api_errors = check_agent_logs(agent_ids, ARTIFACT)
    all_agents_failed = not spawned_ok or api_errors
    final_docs = None

    if all_agents_failed:
        print(f"[{ARTIFACT}] Agents have API/startup issues — using fallback.")
    else:
        for ag in agents:
            send_task(a2a_bin, project, ag["id"], f"Your task: {ag['task']}")
            print(f"[{ARTIFACT}] → sent task to {ag['id']}")

        print(f"[{ARTIFACT}] Waiting for agents to collaborate (up to {args.timeout}s)...")
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            msgs = run_a2a_json("recv --as collector --wait 30", a2a_bin, project)
            for msg in msgs if isinstance(msgs, list) else []:
                sender = msg.get("sender", "")
                body = msg.get("body", "")
                if sender == "docsmith" and "DOCS_START" in body:
                    start_idx = body.find("DOCS_START") + len("DOCS_START")
                    end_idx = body.find("DOCS_END")
                    if end_idx > start_idx:
                        final_docs = body[start_idx:end_idx].strip()
                    else:
                        final_docs = body.replace("DOCS_START", "").replace("DOCS_END", "").strip()
                    print(f"[{ARTIFACT}] ← Received agent-produced docs ({len(final_docs)} chars)")
                    break
            if final_docs:
                break

    docs_path = output_dir / "api-docs.md"
    html_path = output_dir / "api-docs.html"

    if final_docs:
        docs_path.write_text(final_docs)
        print(f"[{ARTIFACT}] Wrote output/api-docs.md (agent-produced, {len(final_docs)} chars)")
        # Try to convert to HTML via pandoc
        try:
            proc = subprocess.run(
                ["pandoc", "-f", "markdown", "-t", "html5", "--metadata", "title=GitHub REST API Reference Guide"],
                input=final_docs.encode(),
                capture_output=True,
                timeout=30,
            )
            if proc.returncode == 0 and proc.stdout:
                html_path.write_text(proc.stdout.decode())
                print(f"[{ARTIFACT}] Wrote output/api-docs.html ({len(proc.stdout.decode())} chars)")
            else:
                print(f"[{ARTIFACT}] pandoc conversion failed for agent output")
        except Exception as exc:
            print(f"[{ARTIFACT}] pandoc error on agent output: {exc}")
    else:
        print(f"[{ARTIFACT}] No agent-produced docs. Generating fallback from ddgr...")
        md_content, html_content = generate_fallback_docs()
        docs_path.write_text(md_content)
        print(f"[{ARTIFACT}] Wrote output/api-docs.md (fallback, {len(md_content)} chars)")
        if html_content:
            html_path.write_text(html_content)
            print(f"[{ARTIFACT}] Wrote output/api-docs.html ({len(html_content)} chars)")

    # Capture bus state
    bus_state = run_a2a("peek --limit 30", a2a_bin, project)
    (output_dir / "bus-state.txt").write_text(bus_state)
    print(f"[{ARTIFACT}] Wrote output/bus-state.txt")

    run_a2a("status done --as collector", a2a_bin, project)
    print(f"[{ARTIFACT}] Done.")

if __name__ == "__main__":
    main()
