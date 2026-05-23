     1|# PITFALLS.md — lessons from artifact smoke testing
     2|
     3|Pitfalls discovered during collaborative artifact smoke testing with a2a agent
     4|teams. Focuses on **agent behavior** and **build-script orchestration** problems,
     5|not CLI bugs or feature gaps.
     6|
     7|## How agents communicate (and miscommunicate)
     8|
     9|### Agents wrap output in markdown code blocks
    10|
    11|Even when kit prompts say "start directly with <!DOCTYPE html> — no preamble,"
    12|agents frequently wrap the HTML in a markdown fenced code block:
    13|
    14|    ```html
    15|    <!DOCTYPE html>
    16|    <html>...
    17|    </html>
    18|    ```
    19|
    20|Same for SVG (` ```svg `), Python (` ```python `), YAML (` ```yaml `), and
    21|other formats. The `_util.py` helper function `strip_html_preamble()` handles
    22|HTML specifically, but other formats need their own extraction logic.
    23|
    24|**Fix:** Build scripts that expect code output (not HTML) should either:
    25|- Use a prefix marker like `FINAL_CODE:` and extract everything after it.
    26|- Strip the outermost markdown code fence if present.
    27|- Embed the format hint in the kit prompt as a prefix requirement.
    28|
    29|### Agents send "test message" first
    30|
    31|In color-palette builds, the colorist agent sent `"Test message"` as message #3
    32|before the real palette in message #4. The build script's `recv` loop must
    33|filter out non-matching messages rather than accepting the first arrival.
    34|
    35|**Fix:** In `recv` loops, check `sender` AND content criteria. Don't break on
    36|the first message from a peer — wait for one that actually matches.
    37|
    38|### Agent preamble text contaminates extraction
    39|
    40|Agents love to preface output with "Here is the final HTML:" or "I have
    41|generated the SVG below:" before the actual content. This makes regex-based
    42|extraction fragile.
    43|
    44|**Fix:** `strip_html_preamble()` handles HTML by finding `<!DOCTYPE` or `<html`.
    45|For non-HTML formats, use distinctive content markers (e.g. `FINAL_CODE:`,
    46|`FILE:docker-compose.yml`) that the agent places before the data.
    47|
    48|### Agents sometimes truncate output mid-stream
    49|
    50|In svg-banner builds, the designer's first SVG was truncated — an `<svg>`
    51|element with a `<text>` attribute cut off mid-value and no closing tags. The
    52|reviewer caught the truncation and asked for a resend.
    53|
    54|**Fix:** Always have at least one review round for complex artifacts. Before
    55|accepting output, verify structural completeness (valid XML, matching tags).
    56|
    57|## Spawn and process management
    58|
    59|### PID may not be emitted if spawn fails silently
    60|
    61|The `spawn_agent()` function reads a single line from the subprocess stdout
    62|expecting a PID. If `a2a-spawn` fails (e.g. missing CLI binary), stdout is
    63|empty and `int('')` raises ValueError. The function returns `None` but the
    64|parent may not check the return value.
    65|
    66|**Fix:** After `spawn_agent()` returns `None`, log the spawn binary's stderr
    67|before continuing.
    68|
    69|### Orphaned processes survive unclean termination
    70|
    71|The `SpawnManager` uses `atexit.register()` which only fires on normal exit.
    72|If the script receives SIGKILL, the spawned agents keep running in the
    73|background forever.
    74|
    75|**Fix:** Register a `--pidfile` per spawned agent and use `a2a list --json`
    76|to enumerate PIDs on startup. Clean up orphans at the start of each build.
    77|
    78|### Concurrent builds on the same project name collide
    79|
    80|If two cron jobs or build scripts use the same `--project` name, their agents
    81|interleave on the same bus. Agents from build A receive messages meant for
    82|build B, and vice versa.
    83|
    84|**Fix:** Always use a unique project name per run. The cron-based approach
    85|should use `a2a-artifact-verify-<timestamp>` or similar.
    86|
    87|### Agent spawn is I/O-bound, not CPU-bound
    88|
    89|Spawning 3 opencode agents sequentially (in a `for` loop) takes 30+ seconds
    90|just for startup. The build script's 180-second timeout includes this startup
    91|time, so don't set it too tight.
    92|
    93|**Fix:** If opencode startup is slow, increase `--wait` values in kit prompts
    94|and the build script's overall timeout. The kit prompt's `--wait 20` gives
    95|each agent time to boot up before their first `recv` blocks.
    96|
    97|## Kit prompt design
    98|
    99|### "All peers are listening" is a dangerous assumption
   100|
   101|The kit prompt tells each agent to start by running the locator snippet, then
   102|`recv --wait 5`. But agents spawn sequentially, so the last agent spawned may
   103|not be listening yet when the first agents start sending.
   104|
   105|**Fix:** The build script should sleep 3-5 seconds after spawning all agents
   106|before sending startup tasks. All kit prompts should use `recv --wait 20` with
   107|a loop so late-starting agents catch up.
   108|
   109|### Agents invent peers not on the bus
   110|
   111|Despite the kit prompt rule "Do not invent peers. Address only ids returned by
   112|`a2a list`", agents sometimes invent peer names based on their understanding
   113|of what roles should exist.
   114|
   115|**Fix:** The kit prompt's peer list section should be explicit: list every
   116|registered peer id and role. Don't just say "there are other agents."
   117|
   118|### Hard cap prevents runaway costs
   119|
   120|The 8-iteration hard cap in the kit prompt is essential. Without it, an agent
   121|that gets stuck in a loop (e.g. continually receiving empty `recv` results)
   122|will keep going until manually killed. With opencode, each loop iteration
   123|costs model inference tokens.
   124|
   125|**Fix:** Always include `"Hard cap: 8 loop iterations, then mark done and stop"`
   126|in every kit prompt. Also set `--max-turns` on the spawn CLI flags where
   127|supported.
   128|
   129|## Build script design
   130|
   131|### Multiple messages with the same prefix
   132|
   133|When using `FILE:` or `FINAL_CODE:` prefix patterns, the agent may send
   134|multiple messages with the same prefix as they iterate. The build script
   135|should capture the LAST message, not the first.
   136|
   137|**Fix:** In the `recv` loop, update a dict keyed by file/type prefix rather
   138|than breaking on the first match. Only break when all expected files are
   139|collected.
   140|
   141|### The integrator may not broadcast directly
   142|
   143|In the landing-page artifact, the integrator broadcasts the final HTML wrapped
   144|in a markdown code block (````html...````). The build script captures this but
   145|the saved file includes the markdown wrapper if `strip_html_preamble` doesn't
   146|catch it.
   147|
   148|**Fix:** The kit prompt for the integrator should say "Broadcast the final HTML
   149|directly — no markdown code blocks, no explanatory text. Start with
   150|<!DOCTYPE html>."
   151|
   152|### Shell quoting fails when task instructions contain single quotes
   153|
   154|When a build script uses `run_a2a(f'send {id} "Your task: {prompt}"')`, the
   155|prompt is embedded in a shell command via shlex. If the prompt contains shell
   156|metacharacters — particularly single quotes (`'`) or double quotes (`"`) —
   157|shlex.split() raises `ValueError: No closing quotation`.
   158|
   159|This happened in the web-research-report and news-briefing artifacts, whose
   160|agent kit prompts include a2a command examples like:
   161|
   162|```
   163|a2a send analyst 'FINDINGS: ...' --from researcher
   164|```
   165|
   166|The single quotes inside the prompt, when embedded in `"Your task: ..."`,
   167|are interpreted by shlex as starting new quote boundaries.
   168|
   169|**Fix:** Send task bodies via stdin instead of embedding in shell command args.
   170|Use subprocess directly:
   171|
   172|```python
   173|proc = subprocess.run(
   174|    [a2a_bin, "send", agent_id, "-", "--from", "collector"],
   175|    input=body.encode(), capture_output=True, timeout=30, env=env,
   176|)
   177|```
   178|
   179|The `-` body argument tells a2a to read the message body from stdin.
   180|
   181|### wait_for_messages() drops subsequent peer messages
   182|
   183|The `wait_for_messages()` helper in `_util.py` returns on the first message
   184|from each expected sender. If a peer sends multiple rounds (like the svg
   185|reviewer), only the first message is captured.
   186|
   187|**Fix:** For multi-round workflows, use the inline `recv` loop pattern that
   188|updates a dict and only breaks when all criteria are met. See the
   189|`svg-banner/build.py` for an example that handles review rounds.
   190|
   191|### Bus peek output can exceed terminal buffer
   192|
   193|`a2a peek --limit 50` dumps raw message bodies to stdout. If agents sent large
   194|HTML blocks, the terminal output can be megabytes. This is mostly a concern
   195|for cron jobs that log all output.
   196|
   197|**Fix:** Use `peek --limit 10` for summary views. For detailed inspection,
   198|use `peek --json` and process with `jq` or Python.
   199|
   200|## Source vs doc divergence
   201|
   202|### strip_html_preamble() only handles HTML
   203|
   204|The `_util.py` helper `strip_html_preamble()` searches for `<!DOCTYPE` or
   205|`<html` to strip preamble text. It does NOT handle:
   206|- SVG (`<svg` tag)
   207|- YAML (`version:` or `services:`)
   208|- Python (`#!/usr/bin/env python3`)
   209|- Plain text or markdown
   210|
   211|**Fix:** When adding a new artifact format, add a corresponding strip function
   212|to `_util.py` or handle extraction in the build script directly.
   213|
   214|## Cross-CLI validation parity
   215|
   216|### Python and Go CLIs must agree on invalid inputs
   217|
   218|The a2a ecosystem has two CLIs: `a2a.py` (Python) and `cmd/a2a/main.go` (Go
   219|binary compiled to `a2a`). They share the same database schema but handle
   220|input validation independently. Inconsistencies cause test failures when
   221|integration tests (which use the Go binary) exercise validation paths that
   222|the Python CLI tests cover.
   223|
   224|Known gaps (and fixes):
   225|- `--ttl`: Python rejects `<= 0`. Go used to silently ignore non-positive
   226|  values. **Fixed:** Go now parses `--ttl` strictly and rejects non-positive
   227|  values with the same error message.
   228|- `--limit` on `peek`/`search`: Python rejects `<= 0`. Go used to accept `0`
   229|  for some commands. **Fixed:** Go now rejects non-positive limits.
   230|- Empty agent IDs: Python rejects `""` and whitespace-only IDs for
   231|  `register` and `unregister`. Go used to pass them to SQLite, which would
   232|  either succeed (creating a DB entry with an empty ID) or fail with a
   233|  confusing SQL error. **Fixed:** Go now checks `strings.TrimSpace(id) == ""`
   234|  and prints the same error message.
   235|- Empty `to` in `Send`: Python client raises `ValueError`. Go client library
   236|  used to pass empty strings to SQLite, creating messages with NULL or empty
   237|  recipients. Go CLI also didn't validate. **Fixed:** Go client library and
   238|  CLI, Node.js client, and Rust client now reject empty recipients.
   239|- Empty query in `Search`: Python CLI and Go CLI used to pass empty strings
   240|  to SQLite `LIKE` matching (which matched everything). **Fixed:** Go client
   241|  library, Python sync and async clients, and Rust client now all reject empty
   242|  or whitespace-only search queries with a clear error.
   243|- Non-positive limit in `Peek`: Python client validates, but Go client library
   244|  and Node.js/Rust clients did not. **Fixed:** All client libraries now reject
   245|  `limit <= 0` at the library level, matching the Python CLI behavior.
   246|- Non-positive count in `Wait`: Go CLI validated, but Go client library did
   247|  not. **Fixed:** Go `Wait()` now rejects `count <= 0` at the library level.
- Empty project/agentId in constructor: Node.js client did not validate.
  **Fixed:** Node.js `A2AClient` constructor now throws on empty project or
  agentId, matching Python behavior.
- Invalid status in `setStatus`: Node.js client accepted any string.
  **Fixed:** Node.js `setStatus()` now validates against the known status
  values (`active`, `idle`, `done`, `blocked`), matching Python behavior.
- Non-positive limit in `Search()`: Go client library did not validate.
  **Fixed:** Go `Search()` now rejects `limit <= 0` at the library level,
  matching Python/Node.js/Rust client behavior.
- Invalid status in `SetStatus()`: Go client library did not validate.
  **Fixed:** Go `SetStatus()` now validates against the known status values
  (`active`, `idle`, `done`, `blocked`), matching Node.js/Rust behavior.
- Non-positive limit in `search()`: Python sync and async clients did not
  validate, and Rust client did not validate.
  **Fixed:** Python `A2AClient.search()` and `A2AClientAsync.search()` now
  reject `limit <= 0`. Rust `Client.search()` rejects `limit <= 0`.
- TTL validation in `Send()`: Python client rejects `ttl_seconds <= 0`. Go
  client library used to accept non-positive TTL values without error.
  **Fixed:** Go `Client.Send()` now rejects `ttl_seconds <= 0` at the library
  level, matching Python and Node.js client behavior.
- Limit validation in `Recv()`: Python client rejects `limit < 0`. Go client
  library used to pass negative limits to SQLite (which treats them as no limit).
  **Fixed:** Go `Client.Recv()` now rejects negative limits at the library
  level, matching Python client behavior.
- `--since` NaN/Inf in Go CLI: Python CLI rejects NaN/Inf `--since` values
  via `_validate_finite_float`. Go CLI `cmdRecv()` parsed `--since` without
  checking for NaN/Inf — `inf` and `NaN` would silently pass through (Inf
  comparison with `< 0` is always false).
  **Fixed:** Go CLI `cmdRecv()` now rejects `--since` values that are
  infinite or NaN, matching Python CLI behavior.
- `--pid` negative in Go CLI: Python CLI rejects `--pid < 0`. Go CLI
  `cmdRegister()` did not validate negative PID values.
  **Fixed:** Go CLI `cmdRegister()` now rejects `--pid < 0`, matching Python
  CLI behavior.

**Fix:** When adding a new validation check to `a2a.py`, add the equivalent
   256|check to `cmd/a2a/main.go` at the same time. Run both test suites before
   257|committing.
   258|
   259|### Integration tests use the Go binary, unit tests use Python
   260|
   261|`test_integration.py` shells out to the `a2a` binary (Go), while
   262|`test_a2a.py` imports `a2a.py` and calls functions directly. This means a
   263|validation bug in one CLI may pass the other's test suite. Always run both.
   264|
   265|**Fix:** When adding validation tests in `test_a2a.py`, add corresponding
   266|integration tests in `test_integration.py` that exercise the same path
   267|through the Go binary. Expected behavior must match.
   268|
   269|### API key exhaustion silently kills agent spawns
   270|
   271|AI CLIs (opencode, claude, pi) require valid API keys with available quota.
   272|When the key is exhausted or invalid, `a2a-spawn` still creates a process
   273|(PID assigned, log file written) but the agent process immediately errors
   274|out without registering on the bus or doing any work:
   275|
   276|```
   277|> build · deepseek/deepseek-v4-flash
   278|Error: Key limit exceeded (total limit).
   279|```
   280|
   281|This wasted ~8 minutes of wall-clock time per build before timeouts kicked in.
   282|
   283|The `spawn_agent()` health check polls `a2a list --json` and waits up to 30s
   284|for the agent to appear. If the agent never registers, the health check fails
   285|and spawn returns `None`. However, this 30s timeout adds significant latency
   286|— 3 agents × 30s = 90s spent waiting for timeouts before fallback activates.
   287|
   288|**Diagnosis:** Check `/tmp/a2a-<agent-id>.log` for the agent's log output.
   289|Common markers:
   290|- `Key limit exceeded` — opencode API key monthly budget exhausted
   291|- `insufficient_quota` — claude/pi API key out of credits
   292|- `429` — rate limit hit; wait and retry
   293|
   294|**Mitigation (free models):** For opencode, use a free-tier model:
   295|- `opencode/deepseek-v4-flash-free` (recommended — same model, free tier)
   296|- `opencode/nemotron-3-super-free`
   297|- `openrouter/deepseek/deepseek-v4-flash:free`
   298|
   299|Pass via: `--model opencode/deepseek-v4-flash-free`
   300|
   301|**Detection pattern** (implemented in `_util.py` `_check_agent_health()`):
   302|```python
   303|for marker in ["Key limit exceeded", "insufficient_quota", "rate_limit_exceeded",
   304|                "401", "402", "429", "403"]:
   305|    if marker in log_contents:
   306|        return False  # Fast-fail: don't wait for full timeout
   307|```
   308|
   309|This checks the agent's log file immediately after spawn, before the 30s poll.
   310|
   311|**Fallback pattern** (implemented in all build scripts):
   312|```python
   313|api_errors = check_agent_logs(agent_ids)
   314|if not spawned_ok or api_errors:
   315|    print(f"Agents have API/startup issues. Generating fallback...")
   316|    # Produce output directly so the artifact directory is always populated
   317|```
   318|
   319|**Best practices for build scripts:**
   320|1. Always implement a fallback path that produces output without agents.
   321|2. Check agent logs before entering the polling loop (fast-fail).
   322|3. The `output/` directory should always be populated, even with a fallback note.
   323|4. The bus state snapshot (`peek --limit 30`) provides debugging context even
   324|   when agents fail — send messages are visible even without agent responses.
   325|
   326|### ddgr / DuckDuckGo blocks automated requests (HTTP 202)
   327|
   328|ddgr (DuckDuckGo CLI search) returns `HTTP Error 202: Accepted` with empty
   329|results in environments where DuckDuckGo has flagged the IP for automated
   330|querying. This is a server-side block, not a client configuration issue:
   331|
   332|```
   333|$ ddgr --json -n 3 "test"
   334|[ERROR] HTTP Error 202: Accepted
   335|[]
   336|```
   337|
   338|All artifacts that use `ddgr` for web research (web-research-report,
   339|news-briefing, competitive-analysis, a2a-landscape, weekly-digest) will
   340|return empty results when ddgr is blocked. The agents attempt the search,
   341|get back empty JSON, and have nothing to work with.
   342|
   343|This typically happens in:
   344|- Cloud/VM environments with datacenter IP ranges
   345|- Environments behind VPNs or proxy services
   346|- CI/CD runners that share IPs
   347|
   348|**Diagnosis:** Run `ddgr --json -n 1 "test"` directly. If it returns
   349|`HTTP Error 202`, ddgr is blocked.
   350|
   351|**Mitigations (none guaranteed):**
   352|- Use `-t w` (past week) instead of `-t m` to reduce query scope
   353|- Increase `--num 3` to avoid hitting rate limits too fast
   354|- Run from a residential IP or use a different search tool
- The build script should detect empty ddgr results and fall back gracefully
  (as the weekly-digest build script does)

### AI CLI API key quotas cause agent spawn failures

When spawning multiple agents (3+) for a collaborative artifact, one or more
agents may fail to start due to API key rate limits or quota exhaustion on
the AI CLI service.

In the ascii-gallery build:
- The finder and artist agents registered successfully on the a2a bus
- The curator agent failed with "Key limit exceeded" before completing setup
- This left the build script waiting indefinitely for curator output

**Mitigations:**
- Build scripts should implement an `--offline` flag that generates output
  without spawning agents (the ascii-gallery build has this)
- Use agent health checks (as `_util.py`'s `_check_agent_health()` does)
  to detect spawn failures early and fall back gracefully
- Reduce concurrent agent count to 2 when API quota is tight
- Consider staggering agent spawns with a short delay between each

### Stale agent log files cause false-positive health check failures

The `_check_agent_health()` function in `_util.py` reads `/tmp/a2a-{agent_id}.log`
immediately after spawn and searches for API error markers like "Key limit exceeded"
and "403". If a log file from a **previous run** still exists at that path, the
health check returns `False` immediately — even though the current agent is perfectly
healthy.

This happened during the web-research-report build: the researcher agent had a stale
log from a prior session containing "403", causing `spawn_agent()` to return `None`
even though the agent went on to successfully search ddgr and send findings to the
analyst.

**Fix:** `_check_agent_health()` should ignore log entries with timestamps older
than the current spawn time, or the build script should rotate/delete agent logs
at startup:

```python
import os, glob
for log in glob.glob("/tmp/a2a-*.log"):
    os.remove(log)
```

Alternatively, the `SpawnManager` or build script preamble should clear stale logs
before spawning agents to avoid false positives.

### Agent build scripts need timeouts on waiting loops

Build scripts that use `a2a recv --as collector --wait N` in a polling loop
must have an overall deadline that kills the loop and falls back to cached
or partial output. Without this, a single agent failure causes the entire
build to hang.

The ascii-gallery build uses `--timeout N` with an overall deadline, but
when the curator agent fails to spawn (API key limit), the build waits the
full timeout before falling back to the offline-generated output.

**Fix:** All artifact build scripts should implement a two-tier approach:
1. Generate core output via local tool calls (no agents) first
2. Then spawn agents and try to get agent-curated output
3. Use the local output as fallback if agents fail or timeout

### Brand-assets build needs ASCII converter plugin

The brand-assets artifact uses `ascii-image-converter` for the agent-driven
path. During the initial build, neither the agents nor the fallback needed
this plugin because the fallback path generates ASCII art inline. However,
if agents succeed and try to download + convert images, the plugin must
be installed:

```bash
sc plugins install ascii-image-converter
```

Without it, the agent conversion path fails silently (agents get empty
results from shell commands). The build remains healthy because the
fallback path always produces output.

**Fix:** The brand-assets build script generates three types of output
regardless of agent availability:
1. `output/brand/banner.svg` — generic A2A-branded SVG banner
2. `output/brand/palette.html` — color palette gallery page
3. `output/brand/logo.txt` — ASCII art logo
4. `output/brand/bus-state.txt` — collaboration log

### Python and Go binaries have different validation coverage

The `a2a` binary is the Go-compiled companion CLI. The `a2a.py` script is the
Python source. Both are designed to be interchangeable, but **validation logic
must be ported to both** when hardening:

- The Go binary already trimmed agent IDs and validated PID before the Python
  script did (commits in late v1.3).
- Python-only whitespace/strip validations (e.g., `--role`, `--cli` empty checks)
  added in later hardening do not apply to the Go binary until ported.

Test helpers in `test_integration.py` now include a `_a2a_py()` helper that
bypasses the Go binary for validation-specific asserts. Use this when testing
Python-only validation rules.

**Fix:** When adding CLI validation:
1. Add to `a2a.py` first (fastest iteration)
2. Port the same validation to Go `cmd/a2a/main.go`
3. Rebuild the Go binary: `go build -o a2a ./cmd/a2a/`
4. Use `_a2a_py()` in tests for Python-only rules

This multi-tier approach (agent path → fallback path) ensures the
artifact always produces output even when API keys are exhausted.

