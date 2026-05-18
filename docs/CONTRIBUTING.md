# Contributing to a2a-skill

Welcome! This guide will help you contribute to a2a-skill.

## Getting Started

1. **Clone and install**
   ```bash
   git clone https://github.com/javimosch/a2a-skill.git
   cd a2a-skill
   ./install.sh
   ```

2. **Run tests locally**
   ```bash
   python3 test_a2a.py -v          # unit tests
   python3 test_integration.py -v  # integration tests
   ./smoke_test.sh                 # simple smoke test
   ```

3. **Test your changes**
   - For CLI changes: update `a2a.py`, run tests
   - For skill changes: see `SKILL.md`, test with `/a2a` in Claude Code
   - For examples: add to `examples/`, test with `smoke_test_examples.sh`

## Code Structure

```
a2a.py                 Core CLI implementation (~480 lines)
├── Commands: init, register, send, recv, peek, list, status, wait, clear
├── Database schema: agents, messages, reads tables
├── Message filtering: per-agent read tracking, unread-only, broadcast handling
└── Features: TTL expiry, message threading, agent presence

test_a2a.py            Unit tests (19+ tests)
├── Schema & WAL mode
├── Agent lifecycle
├── Message send/recv workflows
├── TTL & cleanup
└── Edge cases & errors

test_integration.py    Integration tests (18+ tests)
├── End-to-end CLI workflows
├── Full registration → message → recv cycles
└── Concurrent write safety

examples/              Pattern implementations
├── researcher_agent.py    → broadcast + aggregation
├── code_reviewer_agent.py → request-response
└── task_coordinator_agent.py → work distribution
```

## Adding Features

### New CLI Command

1. Add the command function to `a2a.py`:
   ```python
   def cmd_my_command(args):
       # Your implementation
       print("Success!")
   ```

2. Register it in `build_parser()`:
   ```python
   s = sub.add_parser("my-command", help="...")
   s.add_argument("--my-flag")
   s.set_defaults(func=cmd_my_command)
   ```

3. Add unit tests to `test_a2a.py`:
   ```python
   def test_my_command(self):
       result = a2a("my-command", "--my-flag", "value", project=...)
       assert result.returncode == 0
   ```

4. Add integration test to `test_integration.py`:
   ```python
   def test_my_command_workflow(self):
       # Full end-to-end test
   ```

5. Update `SKILL.md` with usage examples.

### New Agent Pattern

1. Create a new file in `examples/`:
   ```python
   # examples/my_agent.py
   import subprocess
   import json
   
   def main():
       agent_id = "my-agent"
       # Register, send, recv, mark done
   
   if __name__ == "__main__":
       main()
   ```

2. Make it executable:
   ```bash
   chmod +x examples/my_agent.py
   ```

3. Test it:
   ```bash
   python3 examples/my_agent.py &
   # Verify via: a2a peek
   ```

4. Document it in `examples/README.md`:
   - Describe the pattern and use case
   - Show usage example
   - Explain key behaviors

### Extending the Database Schema

Be careful — migrations affect existing users' databases.

1. Update `SCHEMA` in `a2a.py`:
   ```python
   SCHEMA = """
   CREATE TABLE IF NOT EXISTS my_table (
       id INTEGER PRIMARY KEY,
       ...
   );
   """
   ```

2. Add migration logic in `connect()`:
   ```python
   try:
       conn.execute("SELECT my_column FROM my_table WHERE 1=0")
   except sqlite3.OperationalError:
       conn.execute("ALTER TABLE my_table ADD COLUMN my_column ...")
   ```

3. Test with both fresh and existing databases:
   ```bash
   # Fresh DB
   A2A_PROJECT=test-fresh a2a init && a2a send all "msg" --from alice
   
   # Existing DB (simulate upgrade)
   # Create old schema, then run new a2a
   ```

## Testing Guidelines

### Unit Tests
- Test individual functions in isolation
- Mock database when practical
- Cover happy path + edge cases

### Integration Tests
- Test full workflows (register → send → recv → done)
- Use real CLI invocations
- Clean up test projects

### Smoke Tests
- Multi-agent coordination
- Verify all agents complete (`status='done'`)
- Check final message bus state

### Example Agents
- Should complete in <60 seconds
- Should mark `status=done` when finished
- Should handle empty recv gracefully (don't hang forever)

## Performance Considerations

Baseline performance (from `benchmark.py`):
- **Latency**: ~82ms per message (send → recv)
- **Throughput**: ~14 messages/sec
- **Broadcast**: ~73ms (all recipients receive once)
- **TTL overhead**: ~11% (vs. no TTL)

For optimizations:
- Profile with `benchmark.py` before and after
- Changes affecting send/recv should justify the tradeoff
- Test with 10+ agents concurrently (not just 2–3)

## Documentation

- **README.md**: User-facing overview, install, quick start
- **SKILL.md**: Full specification of `/a2a` skill for Claude Code
- **AGENTS.md**: Developer guide for extending a2a
- **examples/README.md**: Pattern walkthroughs and tutorials
- **CONTRIBUTING.md**: This file — for contributors

Keep docs in sync with code. If you change behavior, update docs too.

## Commit Guidelines

Use clear, descriptive messages:

```
Add feature: description of what changed

Optional: More details about why and how.

Co-Authored-By: <name> <email>
```

Examples:
```
Add message TTL (time-to-live) support
Fix cmd_peek not committing after cleanup
Add code_reviewer example agent
Docs: update README with examples section
```

## Code Style

- **Python**: Follow PEP 8. Use `python3 -m py_compile` to check syntax.
- **Shell**: POSIX sh/bash. Use `bash -n` for syntax checking.
- **Comments**: Only for non-obvious WHY, not WHAT. Clear names beat comments.
- **No external dependencies** — a2a.py must work with stdlib only.

## Backwards Compatibility

- CLI commands/flags should be stable once released
- Adding new flags: use `--new-flag` with sensible defaults
- Changing behavior: consider a new command or flag, don't break existing usage
- Database schema: migrations must handle old databases gracefully

## Release Process

1. Update version info (if any) in docs
2. Run full test suite locally:
   ```bash
   python3 test_a2a.py -v
   python3 test_integration.py -v
   ./smoke_test.sh
   ./smoke_test_examples.sh
   ```
3. Create a commit summarizing changes
4. Tag with `git tag vX.Y.Z`
5. Push to GitHub

GitHub Actions will automatically:
- Run tests on Python 3.10, 3.11, 3.12
- Check code style and documentation
- Build and publish releases (if configured)

## Questions?

- Check `AGENTS.md` for development patterns
- Read `SKILL.md` for deep dive on architecture
- Look at existing tests for usage examples
- Open an issue on GitHub for questions/suggestions

## License

By contributing, you agree your work is licensed under MIT (see LICENSE).
Attribution to original authors required.
