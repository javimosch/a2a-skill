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
