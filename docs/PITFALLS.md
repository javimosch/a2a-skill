# PITFALLS.md — lessons from artifact smoke testing

Pitfalls discovered during collaborative artifact smoke testing with a2a agent
teams. Focuses on **agent behavior** and **build-script orchestration** problems,
not CLI bugs or feature gaps.

## How agents communicate (and miscommunicate)

### Agents wrap output in markdown code blocks

Even when kit prompts say "start directly with <!DOCTYPE html> — no preamble,"
agents frequently wrap the HTML in a markdown fenced code block:

    ```html
    <!DOCTYPE html>
    <html>...
    </html>
    ```

Same for SVG (` ```svg `), Python (` ```python `), YAML (` ```yaml `), and
other formats. The `_util.py` helper function `strip_html_preamble()` handles
HTML specifically, but other formats need their own extraction logic.

**Fix:** Build scripts that expect code output (not HTML) should either:
- Use a prefix marker like `FINAL_CODE:` and extract everything after it.
- Strip the outermost markdown code fence if present.
- Embed the format hint in the kit prompt as a prefix requirement.

### Agents send "test message" first

In color-palette builds, the colorist agent sent `"Test message"` as message #3
before the real palette in message #4. The build script's `recv` loop must
filter out non-matching messages rather than accepting the first arrival.

**Fix:** In `recv` loops, check `sender` AND content criteria. Don't break on
the first message from a peer — wait for one that actually matches.

### Agent preamble text contaminates extraction

Agents love to preface output with "Here is the final HTML:" or "I have
generated the SVG below:" before the actual content. This makes regex-based
extraction fragile.

**Fix:** `strip_html_preamble()` handles HTML by finding `<!DOCTYPE` or `<html`.
For non-HTML formats, use distinctive content markers (e.g. `FINAL_CODE:`,
`FILE:docker-compose.yml`) that the agent places before the data.

### Agents sometimes truncate output mid-stream

In svg-banner builds, the designer's first SVG was truncated — an `<svg>`
element with a `<text>` attribute cut off mid-value and no closing tags. The
reviewer caught the truncation and asked for a resend.

**Fix:** Always have at least one review round for complex artifacts. Before
accepting output, verify structural completeness (valid XML, matching tags).

## Spawn and process management

### PID may not be emitted if spawn fails silently

The `spawn_agent()` function reads a single line from the subprocess stdout
expecting a PID. If `a2a-spawn` fails (e.g. missing CLI binary), stdout is
empty and `int('')` raises ValueError. The function returns `None` but the
parent may not check the return value.

**Fix:** After `spawn_agent()` returns `None`, log the spawn binary's stderr
before continuing.

### Orphaned processes survive unclean termination

The `SpawnManager` uses `atexit.register()` which only fires on normal exit.
If the script receives SIGKILL, the spawned agents keep running in the
background forever.

**Fix:** Register a `--pidfile` per spawned agent and use `a2a list --json`
to enumerate PIDs on startup. Clean up orphans at the start of each build.

### Concurrent builds on the same project name collide

If two cron jobs or build scripts use the same `--project` name, their agents
interleave on the same bus. Agents from build A receive messages meant for
build B, and vice versa.

**Fix:** Always use a unique project name per run. The cron-based approach
should use `a2a-artifact-verify-<timestamp>` or similar.

### Agent spawn is I/O-bound, not CPU-bound

Spawning 3 opencode agents sequentially (in a `for` loop) takes 30+ seconds
just for startup. The build script's 180-second timeout includes this startup
time, so don't set it too tight.

**Fix:** If opencode startup is slow, increase `--wait` values in kit prompts
and the build script's overall timeout. The kit prompt's `--wait 20` gives
each agent time to boot up before their first `recv` blocks.

## Kit prompt design

### "All peers are listening" is a dangerous assumption

The kit prompt tells each agent to start by running the locator snippet, then
`recv --wait 5`. But agents spawn sequentially, so the last agent spawned may
not be listening yet when the first agents start sending.

**Fix:** The build script should sleep 3-5 seconds after spawning all agents
before sending startup tasks. All kit prompts should use `recv --wait 20` with
a loop so late-starting agents catch up.

### Agents invent peers not on the bus

Despite the kit prompt rule "Do not invent peers. Address only ids returned by
`a2a list`", agents sometimes invent peer names based on their understanding
of what roles should exist.

**Fix:** The kit prompt's peer list section should be explicit: list every
registered peer id and role. Don't just say "there are other agents."

### Hard cap prevents runaway costs

The 8-iteration hard cap in the kit prompt is essential. Without it, an agent
that gets stuck in a loop (e.g. continually receiving empty `recv` results)
will keep going until manually killed. With opencode, each loop iteration
costs model inference tokens.

**Fix:** Always include `"Hard cap: 8 loop iterations, then mark done and stop"`
in every kit prompt. Also set `--max-turns` on the spawn CLI flags where
supported.

## Build script design

### Multiple messages with the same prefix

When using `FILE:` or `FINAL_CODE:` prefix patterns, the agent may send
multiple messages with the same prefix as they iterate. The build script
should capture the LAST message, not the first.

**Fix:** In the `recv` loop, update a dict keyed by file/type prefix rather
than breaking on the first match. Only break when all expected files are
collected.

### The integrator may not broadcast directly

In the landing-page artifact, the integrator broadcasts the final HTML wrapped
in a markdown code block (````html...````). The build script captures this but
the saved file includes the markdown wrapper if `strip_html_preamble` doesn't
catch it.

**Fix:** The kit prompt for the integrator should say "Broadcast the final HTML
directly — no markdown code blocks, no explanatory text. Start with
<!DOCTYPE html>."

### Shell quoting fails when task instructions contain single quotes

When a build script uses `run_a2a(f'send {id} "Your task: {prompt}"')`, the
prompt is embedded in a shell command via shlex. If the prompt contains shell
metacharacters — particularly single quotes (`'`) or double quotes (`"`) —
shlex.split() raises `ValueError: No closing quotation`.

This happened in the web-research-report and news-briefing artifacts, whose
agent kit prompts include a2a command examples like:

```
a2a send analyst 'FINDINGS: ...' --from researcher
```

The single quotes inside the prompt, when embedded in `"Your task: ..."`,
are interpreted by shlex as starting new quote boundaries.

**Fix:** Send task bodies via stdin instead of embedding in shell command args.
Use subprocess directly:

```python
proc = subprocess.run(
    [a2a_bin, "send", agent_id, "-", "--from", "collector"],
    input=body.encode(), capture_output=True, timeout=30, env=env,
)
```

The `-` body argument tells a2a to read the message body from stdin.

### wait_for_messages() drops subsequent peer messages

The `wait_for_messages()` helper in `_util.py` returns on the first message
from each expected sender. If a peer sends multiple rounds (like the svg
reviewer), only the first message is captured.

**Fix:** For multi-round workflows, use the inline `recv` loop pattern that
updates a dict and only breaks when all criteria are met. See the
`svg-banner/build.py` for an example that handles review rounds.

### Bus peek output can exceed terminal buffer

`a2a peek --limit 50` dumps raw message bodies to stdout. If agents sent large
HTML blocks, the terminal output can be megabytes. This is mostly a concern
for cron jobs that log all output.

**Fix:** Use `peek --limit 10` for summary views. For detailed inspection,
use `peek --json` and process with `jq` or Python.

## Source vs doc divergence

### strip_html_preamble() only handles HTML

The `_util.py` helper `strip_html_preamble()` searches for `<!DOCTYPE` or
`<html` to strip preamble text. It does NOT handle:
- SVG (`<svg` tag)
- YAML (`version:` or `services:`)
- Python (`#!/usr/bin/env python3`)
- Plain text or markdown

**Fix:** When adding a new artifact format, add a corresponding strip function
to `_util.py` or handle extraction in the build script directly.

## Remote machine spawn

### SSH becomes unresponsive when 4+ agents start simultaneously

Spawning 4 claude processes on a remote host causes 60–90 seconds of SSH
connection timeouts. Each agent starts up, reads source files, and hits the
Claude API almost simultaneously, peaking CPU and network. Subsequent SSH
connections time out during this window.

**This is normal. The agents are running.** Do not panic or assume something
went wrong.

**Fix:** After spawning all agents, wait 90 seconds before attempting to
monitor via SSH. Use `a2a peek` from the remote side (via an already-open
session) rather than opening a new connection. Stagger spawns if you need
the host to remain responsive:

```bash
for id in pm architect dev1 qa; do
  # ... spawn $id ...
  sleep 5  # small gap between spawns reduces peak load
done
```

### claude is not on PATH in non-login SSH sessions

`claude` is typically installed at `~/.local/bin/claude`. Non-login SSH
sessions (e.g. `ssh host "command"`) do not source `.bashrc` or `.profile`,
so `~/.local/bin` may not be in `$PATH`. `which claude` returns nothing even
though the binary exists.

**Diagnosis:** `ssh host "which claude"` returns empty, but
`ssh host "ls ~/.local/bin/claude"` succeeds.

**Fix:** In kit prompts and spawn scripts on remote machines, resolve claude
explicitly:

```bash
CLAUDE=""
for cand in "$(command -v claude 2>/dev/null)" "$HOME/.local/bin/claude"; do
  [ -x "$cand" ] && { CLAUDE="$cand"; break; }
done
```

`a2a-spawn` handles this internally — pass `--cli claude` and it resolves
the binary. The issue only surfaces if you try to invoke claude directly
in a script.

### a2a-spawn is not on PATH remotely

`a2a-spawn` is not typically symlinked to a system PATH location. The
installer puts it in `~/.local/bin/` but that may not be on PATH in
non-login SSH sessions (same issue as claude above).

**Fix:** Always resolve `a2a-spawn` by full path:

```bash
SPAWN=""
for cand in "$(command -v a2a-spawn 2>/dev/null)" \
            "$REPO_PATH/a2a-spawn" \
            "$HOME/.agents/skills/a2a/a2a-spawn" \
            "$HOME/.claude/skills/a2a/a2a-spawn"; do
  [ -x "$cand" ] && { SPAWN="$cand"; break; }
done
[ -z "$SPAWN" ] && { echo "ERROR: a2a-spawn not found"; exit 1; }
```

### Stale rebase blocks worktree creation

If a previous session left an interactive rebase in progress (`.git/rebase-merge`
or `.git/rebase-apply` exists), `git worktree add` produces a detached HEAD
on the stale rebase state, not the target branch.

**Diagnosis:** `git status` shows "interactive rebase in progress".

**Fix:** Before creating a worktree, always check and abort:

```bash
if [ -d ".git/rebase-merge" ] || [ -d ".git/rebase-apply" ]; then
  git rebase --abort
fi
```

### Diverged local/origin branches must be reset before creating a worktree

If local `main` and `origin/main` have the same commit message but different
SHAs (both sides amended or cherry-picked independently), `git pull --ff-only`
fails. A naive `git pull` would create a merge commit on the source branch,
contaminating the worktree's lineage.

**Fix:** When preparing a remote machine for a worktree, reset hard to origin:

```bash
git fetch origin main
git reset --hard origin/main
```

Only do this when you confirm the local commit is a duplicate/stale version
of the remote commit (same intent, different SHA).

### Root + claude: the only fully working method is a dedicated non-root user

Several methods have been tried on Claude Code 2.1.147 as root. Here is what actually works:

| Method | As root | Bash tool auto-runs |
|--------|---------|---------------------|
| `--dangerously-skip-permissions` | ❌ blocked | — |
| `--permission-mode bypassPermissions` | ❌ blocked | — |
| `--permission-mode dontAsk` | ✅ accepted | ❌ still prompts |
| `--permission-mode auto` | ✅ accepted | ❌ still prompts |
| `CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS=1` (env var) | ✅ accepted | ❌ still prompts for bash |
| non-root user + `--allow-dangerously-skip-permissions --permission-mode bypassPermissions` | ✅ | ✅ fully autonomous |

**The only method that makes agents fully autonomous (no bash permission prompts) on
Claude Code 2.1.147 is running as a non-root user.** Even though
`CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS=1` is documented as the env var equivalent of
`--dangerously-skip-permissions`, it does not suppress in-session bash tool prompts
when the session runs as root.

**Recommended setup for spawning agents on root-only machines:**

```bash
# 1. Create a dedicated agent user once
useradd -m -s /bin/bash agent
cp -r /root/.claude/. /home/agent/.claude/
chown -R agent:agent /home/agent/.claude

# 2. Share the a2a bus
ln -sf /root/.a2a /home/agent/.a2a
chown -R agent:agent /root/.a2a

# 3. Make the project writable by agent
chown -R agent:agent /root/projects/myproject

# 4. Patch a2a-spawn claude case to use sudo
# Change: CLAUDE_CODE_DANGEROUSLY_SKIP_PERMISSIONS=1 \
# To:     sudo -u agent env A2A_PROJECT="$A2A_PROJECT" \
# And keep FLAGS=(-p --dangerously-skip-permissions --max-turns 16)
```

Note: `sudo -u agent env A2A_PROJECT="..."` passes the project env var through `sudo`'s
env stripping (which drops most vars by default). Always use `env KEY=VAL` explicitly.

### Always pass --project explicitly; don't rely on basename($PWD)

`a2a-spawn` defaults `A2A_PROJECT` to `basename($PWD)`. On a remote machine
where the working directory is `/root`, this becomes `root` — a project name
that collides with any other session on that host also using the default.

**Fix:** Always pass `--project YOURNAME` to every `a2a-spawn` call, and
export `A2A_PROJECT` before all `a2a` CLI calls in the spawn script.

### PM agents over-poll before receiving the architect's design

Without explicit "wait for signal X before re-prompting" wording, PM agents
send repeated "where's the design?" messages every loop iteration. In the
observed session, pm sent 3 check-in messages to architect before the design
arrived — architect had already sent it but pm's recv window hadn't captured
it yet.

**Fix:** Add to the PM kit prompt:

```
After broadcasting GOAL, send ONE check-in to architect asking for the
design ETA. Then recv --wait 30. Do NOT send another check-in until you
have received a response or 3 recv loops have passed empty.
```

### Implementers must be told to ACK receipt immediately

Without an explicit "ACK receipt" instruction, developer agents read the
DESIGN spec silently and begin implementing. The PM and architect see no
confirmation for 2+ minutes, triggering redundant check-ins that create
noise on the bus.

**Fix:** Add to dev1 and qa kit prompts:

```
When you receive a DESIGN spec or TESTPLAN, ACK it immediately before
doing any work: "$A2A send architect 'DESIGN received, starting impl' --from dev1"
```

### Design specs must be explicit about which operations write to the DB

In the agent-groups implementation, `cmd_group_create` was documented in the
design as "create the group" but implemented as a validation-only noop (nothing
written to DB). Groups only appear in `list` after the first member is added.
The architect caught this in review and flagged it as a "behavior quirk" — but
it could have caused test failures if QA's test plan had asserted group
visibility immediately after create.

**Fix:** Design specs should explicitly mark each operation:
- `[DB-write]` — inserts/updates rows
- `[validate-only]` — checks input, writes nothing
- `[DB-read]` — query only

## Cross-CLI validation parity

### Python and Go CLIs must agree on invalid inputs

The a2a ecosystem has two CLIs: `a2a.py` (Python) and `cmd/a2a/main.go` (Go
binary compiled to `a2a`). They share the same database schema but handle
input validation independently. Inconsistencies cause test failures when
integration tests (which use the Go binary) exercise validation paths that
the Python CLI tests cover.

Known gaps (and fixes):
- `--ttl`: Python rejects `<= 0`. Go used to silently ignore non-positive
  values. **Fixed:** Go now parses `--ttl` strictly and rejects non-positive
  values with the same error message.
- `--limit` on `peek`/`search`: Python rejects `<= 0`. Go used to accept `0`
  for some commands. **Fixed:** Go now rejects non-positive limits.
- Empty agent IDs: Python rejects `""` and whitespace-only IDs for
  `register` and `unregister`. Go used to pass them to SQLite, which would
  either succeed (creating a DB entry with an empty ID) or fail with a
  confusing SQL error. **Fixed:** Go now checks `strings.TrimSpace(id) == ""`
  and prints the same error message.
- Empty `to` in `Send`: Python client raises `ValueError`. Go client library
  used to pass empty strings to SQLite, creating messages with NULL or empty
  recipients. Go CLI also didn't validate. **Fixed:** Go client library and
  CLI, Node.js client, and Rust client now reject empty recipients.
- Empty query in `Search`: Python CLI and Go CLI used to pass empty strings
  to SQLite `LIKE` matching (which matched everything). **Fixed:** Go client
  library, Python sync and async clients, and Rust client now all reject empty
  or whitespace-only search queries with a clear error.
- Non-positive limit in `Peek`: Python client validates, but Go client library
  and Node.js/Rust clients did not. **Fixed:** All client libraries now reject
  `limit <= 0` at the library level, matching the Python CLI behavior.
- Non-positive count in `Wait`: Go CLI validated, but Go client library did
  not. **Fixed:** Go `Wait()` now rejects `count <= 0` at the library level.
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
- `recv(wait)` and `wait_for_messages(timeout)` NaN/Inf in Python clients:
  Python sync and async client libraries accepted NaN and Inf for `wait`
  and `timeout` parameters, which could cause infinite loops in the recv
  polling loop (e.g. `deadline = inf` makes `time.time() >= deadline`
  always False).
  **Fixed:** Both `A2AClient.recv()` and `A2AClientAsync.recv()` now reject
  NaN/Inf `wait` via `math.isfinite()`. Both `wait_for_messages()` methods
  reject NaN/Inf `timeout`, matching the CLI's `_validate_finite_float()`. 

**Fix:** When adding a new validation check to `a2a.py`, add the equivalent
check to `cmd/a2a/main.go` at the same time. Run both test suites before
committing.

### Integration tests use the Go binary, unit tests use Python

`test_integration.py` shells out to the `a2a` binary (Go), while
`test_a2a.py` imports `a2a.py` and calls functions directly. This means a
validation bug in one CLI may pass the other's test suite. Always run both.

**Fix:** When adding validation tests in `test_a2a.py`, add corresponding
integration tests in `test_integration.py` that exercise the same path
through the Go binary. Expected behavior must match.

### API key exhaustion silently kills agent spawns

AI CLIs (opencode, claude, pi) require valid API keys with available quota.
When the key is exhausted or invalid, `a2a-spawn` still creates a process
(PID assigned, log file written) but the agent process immediately errors
out without registering on the bus or doing any work:

```
> build · deepseek/deepseek-v4-flash
Error: Key limit exceeded (total limit).
```

This wasted ~8 minutes of wall-clock time per build before timeouts kicked in.

The `spawn_agent()` health check polls `a2a list --json` and waits up to 30s
for the agent to appear. If the agent never registers, the health check fails
and spawn returns `None`. However, this 30s timeout adds significant latency
— 3 agents × 30s = 90s spent waiting for timeouts before fallback activates.

**Diagnosis:** Check `/tmp/a2a-<agent-id>.log` for the agent's log output.
Common markers:
- `Key limit exceeded` — opencode API key monthly budget exhausted
- `insufficient_quota` — claude/pi API key out of credits
- `429` — rate limit hit; wait and retry

**Mitigation (free models):** For opencode, use a free-tier model:
- `opencode/deepseek-v4-flash-free` (recommended — same model, free tier)
- `opencode/nemotron-3-super-free`
- `openrouter/deepseek/deepseek-v4-flash:free`

Pass via: `--model opencode/deepseek-v4-flash-free`

**Detection pattern** (implemented in `_util.py` `_check_agent_health()`):
```python
for marker in ["Key limit exceeded", "insufficient_quota", "rate_limit_exceeded",
                "401", "402", "429", "403"]:
    if marker in log_contents:
        return False  # Fast-fail: don't wait for full timeout
```

This checks the agent's log file immediately after spawn, before the 30s poll.

**Fallback pattern** (implemented in all build scripts):
```python
api_errors = check_agent_logs(agent_ids)
if not spawned_ok or api_errors:
    print(f"Agents have API/startup issues. Generating fallback...")
    # Produce output directly so the artifact directory is always populated
```

**Best practices for build scripts:**
1. Always implement a fallback path that produces output without agents.
2. Check agent logs before entering the polling loop (fast-fail).
3. The `output/` directory should always be populated, even with a fallback note.
4. The bus state snapshot (`peek --limit 30`) provides debugging context even
   when agents fail — send messages are visible even without agent responses.

### ddgr / DuckDuckGo blocks automated requests (HTTP 202)

ddgr (DuckDuckGo CLI search) returns `HTTP Error 202: Accepted` with empty
results in environments where DuckDuckGo has flagged the IP for automated
querying. This is a server-side block, not a client configuration issue:

```
$ ddgr --json -n 3 "test"
[ERROR] HTTP Error 202: Accepted
[]
```

All artifacts that use `ddgr` for web research (web-research-report,
news-briefing, competitive-analysis, a2a-landscape, weekly-digest) will
return empty results when ddgr is blocked. The agents attempt the search,
get back empty JSON, and have nothing to work with.

This typically happens in:
- Cloud/VM environments with datacenter IP ranges
- Environments behind VPNs or proxy services
- CI/CD runners that share IPs

**Diagnosis:** Run `ddgr --json -n 1 "test"` directly. If it returns
`HTTP Error 202`, ddgr is blocked.

**Mitigations (none guaranteed):**
- Use `-t w` (past week) instead of `-t m` to reduce query scope
- Increase `--num 3` to avoid hitting rate limits too fast
- Run from a residential IP or use a different search tool
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

### Cross-client send() validation — Node.js and Rust need sender/recipient existence checks

The Python and Go clients verify that both the sender and recipient agents
exist in the `agents` table before inserting a message. The Node.js and Rust
clients did not perform these checks (fixed in v1.4), silently inserting messages
from unregistered senders or to unknown recipients.

This matters because agent build scripts that use the Python `a2a_client.py`
or Go library expect these validation errors. A script sending via the Node.js
or Rust client would not get the expected error and would proceed with a broken
message that no agent can read.

**Fix (applied in v1.4 across all clients):**
- **Node.js** (`a2a_client.js`): `send()` now queries `agents` table for sender
  and recipient existence before INSERT. Closes the database handle on error.
- **Rust** (`src/lib.rs`): `send()` uses `query_row` with `COUNT(1)` to check
  sender and recipient existence before INSERT. New tests added for unknown
  sender and unknown recipient rejection.

**Checklist when hardening client `send()`:**
1. Validate `to` not empty/whitespace (all clients: ✓)
2. Validate `ttl_seconds > 0` if set (all clients: ✓)
3. Validate sender exists in `agents` table (Python, Go, Node.js, Rust: ✓)
4. Validate recipient exists for non-broadcast (Python, Go, Node.js, Rust: ✓)
5. Close the database handle on validation failure to avoid resource leaks
   (Node.js: fixed in v1.4, Rust: sqlite3 handles via Drop)
6. Validate `thread_id` not empty/whitespace if set (Python ✓, Go ✓, Node.js ✓, Rust ✓)
7. Support `thread_id` parameter in `send()` (Python ✓, Go ✓, Node.js ✓, Rust ✓)

### Cross-client thread_id support — Node.js and Rust send() lacked thread_id parameter

The Python and Go clients support sending messages with a `thread_id` to group
related messages into threads. The Node.js and Rust clients did not accept a
`thread_id` parameter in their `send()` methods, creating a cross-client parity
gap for agent workflows that depend on thread-scoped communication.

The Python CLI (`--thread`) and Python sync/async client libraries all support
thread_id. The Go client library also accepts `threadID string` in `Send()`.
Node.js and Rust were the only clients missing this.

**Fix (applied in this session):**
- **Node.js** (`a2a_client.js`): `send()` now accepts `threadId` as an optional
  4th parameter. Empty/whitespace thread_id raises an error. INSERT statement
  updated to persist `thread_id` column.
- **Rust** (`src/lib.rs`): `send()` now accepts `thread_id: Option<&str>` as a
  4th parameter. Empty/whitespace thread_id raises a validation error. INSERT
  updated to persist `thread_id` column.
- **Tests added:** Both Node.js and Rust test suites now include thread_id
  storage, empty thread_id rejection, and whitespace thread_id rejection tests.

### Agent ID, thread ID, and body max length validation (Go parity)

The Python CLI (`a2a.py`) has enforced `MAX_ID_LENGTH=256`, `MAX_THREAD_ID_LENGTH=256`,
and `MAX_BODY_LENGTH=100000` since v1.3.2. The Go client library and Go CLI did not
validate any of these limits, allowing oversized inputs that could cause SQLite/text
abuse.

**Fixed (this session):**
- **Go client library** (`a2a_client.go`): Added `MaxAgentIDLength`, `MaxThreadIDLength`,
  `MaxBodyLength` exported constants. `Register()` rejects agent IDs > 256 chars.
  `Send()` rejects sender IDs, recipient IDs, thread IDs, and body content exceeding
  their respective limits.
- **Go CLI** (`cmd/a2a/main.go`): All commands that accept agent IDs (`register`,
  `unregister`, `send`, `status`, `recv`, `wait`) now validate max length at the
  CLI entry point before delegating to the client library.
- **Tests added:**
  - 7 Go client library tests (register max length, send max sender/recipient/thread/body,
    body boundary test, send max sender length)
  - 9 Python integration tests (register max length + boundary, send max from/recipient/
    thread, unregister max length, status max --as, recv max --as, wait max --as)

### Peek and search limit capping in Go CLI (Python→Go parity)

The Python CLI caps `peek --limit` at 1000 and `search --limit` at 200, silently
reducing any value above the cap to the maximum. The Go CLI used to pass the
raw limit directly to SQLite without capping, allowing `peek --limit 9999` to
attempt a 9999-row query. While SQLite handles this fine for small buses, the
behavior was inconsistent with Python and caused different output for the same
command line.

**Fixed (this session):**
- **Go CLI** (`cmd/a2a/main.go`): `cmdPeek()` now caps `--limit` at 1000.
  `cmdSearch()` now caps `--limit` at 200. Both match Python behavior exactly.
- **Tests added:** 2 Python integration tests (`test_peek_limit_over_max_does_not_error`,
  `test_search_limit_over_max_does_not_error`) that verify large limit values
  return all available messages without error.

**Checklist when adding Go CLI parity:**
1. Check Python `cmd_*` function for limit caps, rejection ranges, and edge cases.
2. Add equivalent check in Go `cmd*` function — same error message, same exit code.
3. Add integration test that exercises the check via the Go binary.
4. Rebuild the Go binary: `go build -o a2a ./cmd/a2a/`
5. Run both test suites before committing.

