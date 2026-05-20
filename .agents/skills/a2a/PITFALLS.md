# Common Pitfalls

These were discovered while running Pattern 3 (auto-spawn) smoke tests. Future
agents using the `/a2a` skill should heed them.

### 1. `A2A_PROJECT` must be exported before spawning

The spawned CLI process inherits the parent shell's environment. Setting
`A2A_PROJECT=myproject` without `export` in the spawning script means the
agent won't see it. It falls back to `basename($PWD)`, which may resolve to
the wrong project — agents end up on different buses and never see each
other's messages.

**Fix:** Always `export A2A_PROJECT="$PROJECT"` before calling `a2a-spawn`.
Or, to be safe, include `--project $PROJECT` explicitly in every `a2a`
command inside the kit prompt.

### 2. `--project` flag position differs between Go and Python

The installed `a2a` binary (via `install.sh`) may be Go-compiled. The Go
binary requires `--project` **after** the subcommand:

```bash
a2a peek --project myproject --limit 10    # Go: works
a2a --project myproject peek --limit 10    # Go: FAILS
```

The Python `a2a.py` reference requires it **before** the subcommand:

```bash
python3 a2a.py --project myproject peek    # Python: works
python3 a2a.py peek --project myproject    # Python: FAILS
```

**Safest approach:** Use the `A2A_PROJECT` environment variable. It works
identically for both Go and Python binaries:

```bash
export A2A_PROJECT=myproject
a2a peek --limit 10                        # works for Go AND Python
```

### 3. Empty log files ≠ stuck agent

When spawning with `a2a-spawn`, the log file (`--log FILE`) may appear empty
for a long time. CLIs like `claude` buffer stdout aggressively and may not
flush until the process exits. An empty log does not mean the agent is stuck
or the spawn failed.

**Fix:** Check agent progress via the bus:

```bash
ps aux | grep claude              # verify process is running
a2a list --json --project X       # check agent status (active? done?)
a2a peek --limit 10               # see if any messages were sent
```

Only dump the log after ~60s of no bus activity.

### 4. Kit prompts must be self-contained

The kit prompt (Step 4) tells the agent "A2A_PROJECT is already in the
environment." If it isn't actually exported, the agent will write to the
wrong database and appear to send messages that no peer can see. This is
the most common cause of "agents don't find each other."

**Fix:** Either:
- `export A2A_PROJECT="$PROJECT"` before spawning, OR
- Include `--project $PROJECT` in every `a2a` command in the kit prompt

Doing both is safest.

### 5. Cross-project contamination is silent

If two agents land on different projects (e.g. one resolves `basename($PWD)`
to `project-a` and another to `project-b`), neither will error. They simply
write to different SQLite databases and never see each other's messages.

**Fix:** Always verify with `a2a list` that all agents appear in the same
project. The project info is visible in `a2a project` and `a2a list --json`.

### 6. PID registration requires correct project context

When running `a2a register alice --pid "$PID" --upsert` after spawning, the
command uses the current project (via `A2A_PROJECT` or `basename($PWD)`). If
the context is wrong, it will register (or update) the agent on a different
project's bus.

**Fix:** Always pass `--project "$PROJECT"` or ensure `A2A_PROJECT` is
exported before registering PIDs.

### 7. Broadcast messages appear in `recv` for all agents

A message sent to `all` (or `*` or `broadcast`) sets `recipient=NULL` in the
database. Every agent's `recv` will return it as an unread message — once per
agent. This is by design (per-agent read-tracking), but it means a single
broadcast produces N database rows in the `reads` table.

### 8. The spawned CLI must be able to find `a2a` on PATH

Agents running inside spawned CLI sessions (claude, pi, opencode) will shell
out to `a2a`. If `a2a` is not on the spawned process's `$PATH` (e.g. installed
only in the parent shell's config), the agent will fail with "command not
found."

**Fix:** Use the locator snippet from Step 4 to resolve `a2a` dynamically, or
hardcode the full path in the kit prompt.
