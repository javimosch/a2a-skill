# a2a-watchdog & a2a-lease

Deterministic (no-LLM, no-network) liveness for an a2a peer team. Ported and
adapted from [chrisreedbates/a2a-dms](https://github.com/chrisreedbates/a2a-dms)
(`bin/watchdog.mjs`, `bin/lease`, `bin/doorbell`). a2a-dms wakes **persistent
tmux** agents by typing into their terminal; this port targets a2a's **SQLite
bus** and one-shot `-p` agents, so the "poke" becomes a bus message.

## What it does — one pass

1. `~/.a2a/<project>/paused` present → do nothing.
2. Read the roster from `a2a list --json` (source of truth for who exists).
3. For each agent whose status is not `done`:
   - **PID gone** → seat exited without marking done. One-shot agents leave no
     session, so this is *finished-and-forgot* OR *crashed* — indistinguishable.
     Mark it `done`, broadcast `[A2A watchdog] … EXITED`, desktop-notify once.
   - **PID alive + lease overdue past grace** → alive but not checking in. Send a
     wake message on the bus (a seat blocked on `a2a recv` gets it immediately),
     once per cooldown.
4. State in `~/.a2a/<project>/watchdog-state.json` prevents re-alerting the same
   event. Log at `~/.a2a/<project>/watchdog.log`.

The watchdog holds **no authority**: it only reports, marks, and nudges — it
never spawns, kills, or supersedes a session.

### Removing the finished-vs-crashed ambiguity

Have every kit end with `a2a status done --as <id>`. A `done` agent is skipped,
so a clean finisher never triggers a false "EXITED" notice. Only agents that
crash (or forget) are flagged — which is exactly what you want reported.

## Commands

```bash
a2a-watchdog                 # one pass (for cron/systemd/launchd)
a2a-watchdog --loop 60       # foreground dev loop, every 60s
a2a-lease alice 1800         # alice promises to check in within 30 min
a2a-lease alice 1800 off     # alice going quiet on purpose
```

Env knobs: `A2A_BIN`, `A2A_HOME` (default `~/.a2a`), `A2A_PROJECT`,
`A2A_WD_MIN_GRACE_S` (default 600), `A2A_WD_COOLDOWN_S` (default 600),
`A2A_WD_NOTIFY` (1/0, default 1).

## Scheduling

### Linux — systemd user timer

`~/.config/systemd/user/a2a-watchdog@.service`:

```ini
[Unit]
Description=a2a watchdog for project %i

[Service]
Type=oneshot
Environment=A2A_PROJECT=%i
ExecStart=%h/.local/bin/a2a-watchdog
```

`~/.config/systemd/user/a2a-watchdog@.timer`:

```ini
[Unit]
Description=run a2a watchdog for %i every minute

[Timer]
OnBootSec=60
OnUnitActiveSec=60
AccuracySec=5s

[Install]
WantedBy=timers.target
```

```bash
systemctl --user enable --now a2a-watchdog@myproject.timer
```

### Linux/macOS — cron

```cron
* * * * * A2A_PROJECT=myproject $HOME/.local/bin/a2a-watchdog >/dev/null 2>&1
```

### macOS — launchd

`~/Library/LaunchAgents/com.a2a.watchdog.myproject.plist`, `StartInterval` 60,
`EnvironmentVariables` → `A2A_PROJECT=myproject`,
`ProgramArguments` → `[~/.local/bin/a2a-watchdog]`.

### Simplest of all — foreground loop in its own terminal

```bash
A2A_PROJECT=myproject a2a-watchdog --loop 60
```

## Pause / resume

```bash
touch  ~/.a2a/myproject/paused   # watchdog goes fully quiet
rm     ~/.a2a/myproject/paused   # resume
```
