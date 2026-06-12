---
name: a2a-tau-runbook
description: Guide for using tau (Zig AI CLI) with a2a agent-to-agent messaging. Covers critical configuration flags, kit prompt best practices, common pitfalls, provider-specific notes, and debugging tips for successful tau + a2a integration.
trigger: a2a tau
---

# a2a with tau — Runbook & Caveats

## Overview

tau is a non-interactive Zig AI CLI designed for agents. When using tau with a2a for multi-agent coordination, there are specific considerations, caveats, and best practices to ensure successful agent-to-agent communication.

## Key Differences from Other CLIs

| Aspect | claude/opencode | pi | tau |
|--------|----------------|-----|-----|
| **Runtime** | Node.js/TypeScript | Python | Zig (compiled binary) |
| **Tool-calling** | Built-in, mature | Built-in, mature | Built-in, mature (v0.2.0+) |
| **Streaming** | Default, can disable | Default, can disable | Default, must disable for a2a |
| **Default output** | Text | Text | JSON (agent-first) |
| **Process model** | Interactive + non-interactive | Interactive + non-interactive | Non-interactive only |

## Critical Configuration for a2a

### Required a2a-spawn Flags

```bash
# Minimum required flags for tau with a2a:
--no-stream            # MUST disable streaming for tool-calling
--tools bash           # Enable bash tool for a2a coordination (override with TAU_TOOLS)
--max-iterations 40    # MUST increase from default 10 for multi-exchange debates
--timeout-ms 300000    # 5-minute HTTP timeout (slow models need it)
--append-system-prompt $KIT  # Pass kit prompt as system prompt
-p "Begin."            # Single-shot mode

# Optional debugging flags (set via env vars):
TAU_THINKING=1         # Enable --thinking (show reasoning chunks in logs)
TAU_DEBUG=1            # Enable --debug (perf stats + tool I/O to stderr)
```

### Why These Flags Matter

**`--no-stream`**: Streaming mode (default) outputs token-by-token, which breaks tool-calling. Tool-calling requires the full response to parse `tool_calls` before executing them.

**`--tools bash`**: tau has 7 built-in tools (bash, read, write, edit, ls, grep, find). For a2a coordination, only `bash` is needed. Limiting to `bash` reduces token usage and prevents the model from calling file operations that could interfere with a2a coordination. Override with `TAU_TOOLS` env var (e.g., `TAU_TOOLS="bash,read"` to let the agent read files).

**`--thinking` (via `TAU_THINKING=1`)** : Enables reasoning/thinking chunk visibility in logs. Useful for debugging agent behavior. Off by default to save tokens.

**`--debug` (via `TAU_DEBUG=1`)** : Logs performance stats and tool I/O to stderr (visible in agent log). Invaluable for troubleshooting stalled or misbehaving tau agents.

**`--max-iterations 40`**: The default agentic loop limit is 10 iterations. A multi-exchange a2a debate requires ~2 tool calls per round (send + recv). For a 3-round debate, you need at least 6 iterations. 40 provides headroom for longer debates and error recovery.

## Kit Prompt Best Practices

### 1. Plain ASCII Messages

**Problem**: Quotes, apostrophes, and special characters in a2a messages break shell quoting when sent via `bash "a2a send ..."`.

**Solution**: Restrict messages to plain ASCII without quotes or apostrophes.

**Bad kit prompt**:
```
Send your theories to agent-skeptic. Each theory should be detailed and include evidence.
```

**Good kit prompt**:
```
Send your theories to agent-skeptic. Keep each theory to one plain ASCII sentence without quotes or apostrophes.
```

### 2. Explicit Tool Instructions

tau's model (xiaomi mimo-v2.5 by default) needs explicit instructions about when and how to use tools.

**Required in every tau kit**:
```
IMPORTANT: You have access to the bash tool. Use it to run a2a commands:
- Run: bash "A2A_PROJECT=mars-debate /home/jarancibia/ai/a2a-skill/a2a send agent-skeptic 'your message' --from agent-optimist"
- Run: bash "A2A_PROJECT=mars-debate /home/jarancibia/ai/a2a-skill/a2a recv --as agent-optimist --wait 30"
- Run: bash "A2A_PROJECT=mars-debate /home/jarancibia/ai/a2a-skill/a2a status done --as agent-optimist"

Do NOT call any other tools. Only use bash to run a2a commands.
```

### 3. Fixed Round Limits

**Problem**: Open-ended debates can run indefinitely, burning tokens and budget.

**Solution**: Specify a fixed number of rounds with a hard cap.

**Example**:
```
Debate protocol:
1. Send your first theory
2. Receive counter-argument
3. Send your second theory
4. Receive counter-argument
5. Send your third theory
6. Receive counter-argument
7. Mark yourself as done

Hard cap: 3 rounds max. After 3 empty receives, mark yourself done.
```

### 4. Empty Recv Bail-Out

**Problem**: If one agent finishes early, the other can hang waiting for messages that never come.

**Solution**: After N empty receives, mark the agent as done.

**Example**:
```
Hard cap: 3 rounds max. After 3 empty receives, mark yourself done.
```

## Common Pitfalls

### Pitfall 1: Forgetting `--no-stream`

**Symptom**: Agent hangs, no tool calls executed, log shows streaming output.

**Fix**: Always include `--no-stream` in a2a-spawn for tau.

### Pitfall 2: Default `--max-iterations` Too Low

**Symptom**: Agent stops mid-debate after 2-3 rounds, doesn't complete protocol.

**Fix**: Use `--max-iterations 40` or higher for multi-exchange coordination.

### Pitfall 3: Shell Quoting Failures

**Symptom**: a2a send fails with syntax error, message never reaches bus.

**Fix**: Restrict kit prompt messages to plain ASCII without quotes/apostrophes.

### Pitfall 4: Model Doesn't Recognize Tool Instructions

**Symptom**: Agent responds to kit prompt but doesn't execute bash commands.

**Fix**: Make tool instructions explicit and prominent in kit prompt. Use "IMPORTANT:" prefix.

### Pitfall 5: Agent Never Marks Done

**Symptom**: Agent stays `status=active` indefinitely, process doesn't exit.

**Fix**: Include explicit "Mark yourself as done" instruction in protocol. Consider manual intervention if needed.

## Provider-Specific Notes

### xiaomi (mimo-v2.5) - Default

- **Pros**: Fast, cost-effective, good tool-calling
- **Cons**: May need more explicit instructions than other models
- **Notes**: Works well with a2a when kit prompts are clear

### openai (gpt-4o-mini)

- **Pros**: Excellent instruction following, robust tool-calling
- **Cons**: More expensive, slower
- **Notes**: May require different prompt structure

### deepseek (deepseek-chat)

- **Pros**: Good value, capable tool-calling
- **Cons**: May have different output format expectations
- **Notes**: Test thoroughly before production use

## Debugging Tips

### 1. Check Agent Logs

```bash
tail -f /tmp/a2a-{agent}.log
```

Look for:
- Streaming output (indicates `--no-stream` missing)
- Tool call parsing errors
- Bash command execution failures

### 2. Monitor the Bus

```bash
a2a peek --limit 10 --project {project}
```

Check if messages are landing on the bus. If not, the bash tool isn't working.

### 3. Check Agent Status

```bash
a2a list --json --project {project}
```

Verify:
- Both agents are registered
- PIDs are correct
- Status transitions (active → done)

### 4. Test Tool-Calling in Isolation

```bash
./zig-out/bin/tau --tools bash --no-stream -p "Run: bash 'echo test'"
```

If this fails, the issue is with tau's tool-calling, not a2a.

## Example: Working Smoke Test

See the tau repository `smoke.md` for a complete working example:
- Project: mars-debate
- Agents: agent-optimist, agent-skeptic
- Protocol: 3-round debate
- Kit prompts: Plain ASCII, explicit tool instructions

## Integration Checklist

Before deploying tau with a2a:

- [ ] a2a-spawn updated with `--no-stream --tools bash --max-iterations 40 --timeout-ms 300000`
- [ ] TAU_TOOLS, TAU_THINKING, TAU_DEBUG env vars configured if needed
- [ ] Kit prompts use plain ASCII (no quotes/apostrophes)
- [ ] Kit prompts have explicit tool instructions
- [ ] Kit prompts specify fixed round limits
- [ ] Kit prompts include empty recv bail-out
- [ ] tau binary built and accessible (`./zig-out/bin/tau` or in PATH)
- [ ] a2a project initialized
- [ ] Agents registered before spawning
- [ ] PIDs updated after spawn with `--upsert`
- [ ] Monitoring plan in place (peek, list, logs)

## Performance Considerations

### Token Usage

- tau uses JSON output by default (more tokens than text)
- Tool-calling adds overhead (schemas, tool_calls, results)
- Consider `--mode text` for non-a2a use cases

### Process Management

- tau processes are backgrounded via `nohup` in a2a-spawn
- Processes exit when agent marks done or max iterations reached
- Manual kill may be needed if agent hangs

### Resource Limits

- tau is a compiled Zig binary (~250KB), very lightweight
- No Node.js runtime required
- Minimal memory footprint

## Future Enhancements

Potential improvements for tau + a2a:

1. **Native a2a client**: Direct SQLite access instead of bash wrapper
2. **Config file support**: a2a settings in `~/.config/tau/config.json`
3. **Provider-specific defaults**: Different max-iterations per provider
4. **Automatic done detection**: Heuristics to detect completion
5. **Better error messages**: Clearer tool-calling failure diagnostics

## References

- tau README: https://github.com/javimosch/tau
- a2a-skill repo: https://github.com/javimosch/a2a-skill
- a2a AGENTS.md: Full repo guide and protocols
- a2a SMOKE_TEST.md: General smoke testing patterns
