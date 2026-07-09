---
name: a2a-debri-runbook
description: Bootstrap flow for a fresh VM/operator that only has the a2a-skill repo and wants to add debri (a devin-wrapping CLI) as an a2a peer. Covers installing + authenticating devin, getting debri (release binary or source build), wiring it into a2a-spawn, and a smoke test. Read this before spawning a debri agent for the first time on a new host.
trigger: a2a debri bootstrap
---

# a2a + debri — discovery & bootstrap runbook

**Who this is for:** you have the `a2a-skill` repo (this repo) on a fresh
VM/container, but nothing else — no `devin`, no `debri`, maybe not even `tmux`.
You want to spawn a `debri` peer agent via `a2a-spawn --cli debri`. This doc is
the linear path from nothing to a working debri agent on the bus.

**Minimum debri version: v1.1.0.** Do not use the `v1.0.0` release — it
predates a set of reliability fixes this runbook and `a2a-spawn` depend on
(process-exit completion detection, collision-proof tmux session names, real
crash reporting instead of a false success, and tmux cleanup on external kill).
`debri --version` must print `1.1.0` or newer before you go further.

## Step 0 — Prerequisites

```bash
command -v tmux || echo "MISSING: tmux (apt/yum install tmux)"
command -v git  || echo "MISSING: git"
```

`tmux` is required — debri drives devin through a tmux pane. `git` is only
needed if you're building debri from source (Step 2, option B). No Go
toolchain is needed if you use the release binary (option A).

## Step 1 — Install and authenticate devin

devin is the underlying agentic CLI debri wraps. Installing it is outside the
scope of this doc — follow your organization's standard devin install method
or devin's own official documentation to get the `devin` binary on `PATH`.

Once installed, authenticate. On a fresh VM you are very likely over SSH with
no browser redirect available, so use the manual token flow:

```bash
devin auth login --force-manual-token-flow
# or, for the full interactive wizard (auth + shell integration + MCP):
devin setup --force-manual-token-flow
```

Verify before continuing:

```bash
devin auth status     # must show logged in
devin --version        # confirm the binary runs at all
```

If `devin auth status` doesn't show a valid login, stop here — nothing past
this point will work without it.

## Step 2 — Get debri (v1.1.0+)

Pick one.

### Option A — release binary (fastest, no Go toolchain needed)

```bash
curl -fsSL https://github.com/javimosch/debri/releases/download/v1.1.0/debri -o /usr/local/bin/debri
chmod +x /usr/local/bin/debri
debri --version    # expect: debri v1.1.0
```

(Check https://github.com/javimosch/debri/releases for anything newer than
v1.1.0 and prefer that instead — just keep the same install pattern with the
newer tag.)

### Option B — clone + build from source (always gets current `master`)

```bash
git clone https://github.com/javimosch/debri.git
cd debri
./build.sh          # requires Go; produces ./debri
./debri --version
```

### Verify devin is reachable through debri

```bash
debri probe --timeout 10
# expect: "probe: ok (devin responsive: '<path>' --version)"
# exit code 0 = healthy, exit code 1 = unhealthy (reason on stderr)
```

If `probe` fails, re-check Step 1 (auth) before touching a2a at all — debri
itself has no auth logic, it only shells out to `devin`.

## Step 3 — Point a2a-spawn at your debri binary

`a2a-spawn`'s debri branch resolves the binary in this order:

1. `$DEBRI_BIN` env var (if set and executable)
2. `~/ai/debri/debri`
3. `debri` on `PATH`

If you installed via Option A above (`/usr/local/bin/debri`), that's already
on `PATH` — nothing more to do. If you built from source somewhere other than
`~/ai/debri`, export the override:

```bash
export DEBRI_BIN=/path/to/your/debri/debri
```

Set this in your shell profile (or the environment the a2a-spawning agent
inherits) so it survives across sessions.

## Step 4 — Get a2a-skill itself onto the box (if you don't have it yet)

```bash
git clone https://github.com/javimosch/a2a-skill.git
cd a2a-skill
./install.sh        # symlinks a2a, a2a-spawn, a2a-watchdog, a2a-lease onto PATH
                     # and the skill into ~/.claude/skills + ~/.agents/skills
a2a version
```

## Step 5 — Smoke test: one debri agent, solo

Before joining a multi-agent team, confirm debri can complete a single a2a
round-trip on its own.

```bash
PROJECT=debri-smoke
export A2A_PROJECT=$PROJECT
a2a clear --yes 2>/dev/null; a2a init
a2a register solo --role dev --cli debri

cat > /tmp/debri-smoke.kit <<EOF
You are agent "solo" on an a2a peer bus, project $PROJECT.
Do EXACTLY this, then stop:
1. Run: a2a status active --as solo
2. Write the word "hello" to /tmp/debri-smoke-output.txt
3. Run: a2a status done --as solo
EOF

PID=$(a2a-spawn --cli debri --id solo --model SWE-1.6 --project $PROJECT \
    --log /tmp/debri-smoke.log --kit-file /tmp/debri-smoke.kit)
a2a register solo --pid "$PID" --upsert
echo "spawned pid=$PID, tail the log:"
tail -f /tmp/debri-smoke.log   # Ctrl-C once you see the JSONL "done" event
```

Expect within roughly 30-90s (devin startup + one file write):

```json
{"event":"done","content":"...","elapsed_ms":...}
```

and:

```bash
a2a list --json          # solo should show status: "done"
cat /tmp/debri-smoke-output.txt   # should contain: hello
```

If it hangs past a couple of minutes, check `/tmp/debri-smoke.log` for
`[debri] session=...` and `[debri] devin active at poll N` lines — if those
never appear, devin isn't starting inside the tmux pane (recheck Step 1/2). If
you see repeated `stable after N polls` instead of `devin exited (pane back to
shell)`, you're likely on an old debri build — recheck the version (Step 2).

## Step 6 — Join a real a2a team

Once the smoke test passes, follow the main `/a2a` skill
([`.agents/skills/a2a/SKILL.md`](../a2a/SKILL.md)) Pattern 3 spawn protocol as
normal — `--cli debri` works exactly like `--cli claude`/`--cli opencode` from
that point on. See its "Step 5.5" section for `a2a-watchdog`/`a2a-lease`, which
apply to debri agents the same as any other CLI.

## Debri-specific pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `a2a-spawn: debri not found` | Resolution order in Step 3 didn't find your binary | Set `DEBRI_BIN` explicitly |
| Debri exits ~immediately with `"cannot create tmux session"` | Old debri (< v1.1.0) had a session-name collision under concurrent spawns | Upgrade to v1.1.0+ |
| A crashed/killed devin session silently reports `{"event":"done"}` with empty content | Old debri (< v1.1.0) treated a vanished session as success | Upgrade to v1.1.0+ |
| Agent hangs to the full `--stable-timeout` (default 600000ms in `a2a-spawn`) even after finishing | Old debri (< v1.1.0), no process-exit detection | Upgrade to v1.1.0+ |
| `debri probe` fails | devin not authenticated, or not on PATH | Recheck Step 1 |
| Kit prompt doesn't reach devin correctly across bash calls | devin runs each tool call in a fresh shell — env vars don't persist | `a2a-spawn`'s debri branch already inlines `A2A_PROJECT=<proj> <resolved-a2a>` into every `$A2A` in the kit; if you're hand-writing a kit outside `a2a-spawn`, do the same — never rely on an exported env var surviving between devin's tool calls |
| A team teardown (`kill $pid` on a still-working debri agent) used to leave the tmux session behind | Fixed in v1.1.0 (SIGTERM/SIGINT now triggers debri's own session cleanup) | Upgrade to v1.1.0+ |

## References

- debri repo: https://github.com/javimosch/debri
- debri releases: https://github.com/javimosch/debri/releases
- a2a-skill main skill: [`.agents/skills/a2a/SKILL.md`](../a2a/SKILL.md)
- watchdog/lease: [`docs/WATCHDOG.md`](../../../docs/WATCHDOG.md)
