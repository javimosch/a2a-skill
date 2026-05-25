# AGENTS.md — completion/

Shell completion scripts for the `a2a` CLI. See [`../docs/AGENTS.md`](../docs/AGENTS.md)
for the overall doc ownership model — this directory has no separate ownership entry
because completions always mirror `a2a.py`.

## Files

| File | Shell | Install |
|------|-------|---------|
| `a2a.bash` | Bash | `source completion/a2a.bash` or copy to `/etc/bash_completion.d/` |
| `a2a.zsh` | Zsh | Copy to a directory in `$fpath`, then `compinit` |

`install.sh` does not auto-install these. Users must opt in.

## When to update these files

Update completion scripts whenever **any** of the following change in `a2a.py`:

- A subcommand is added or removed (`cmd_*` + `build_parser()`)
- A flag is added or removed from an existing subcommand
- `--status` choices change (currently `active | idle | done | blocked`)

The completion scripts hard-code the subcommand list. They will silently
not complete new commands until updated.

## Current subcommand list (sync with `a2a --help`)

```
init  register  send  recv  peek  list  status  wait  clear
project  unregister  search  stats  thread
```

## Flag completions

Many commands accept common flags. When adding a new flag to `a2a.py`,
consider whether it should also be completed dynamically:

| Flag | Applies to | Completion behavior |
|------|-----------|-------------------|
| `--json` | All output commands (recv, list, peek, search, thread, stats) | Static flag, no value needed |
| `--limit N` | peek, search | Integer, no dynamic completion (capped at 1000 for peek, 200 for search) |
| `--wait N` | recv | Integer seconds (1-300), no dynamic completion |
| `--as AGENT_ID` | recv, status, wait | Could dynamically query `a2a list --json` for agent IDs |
| `--from AGENT_ID` | send | Same dynamic source as `--as` |
| `--since TIMESTAMP` | recv | Unix epoch seconds, no completion |
| `--ttl SECONDS` | send | Positive integer, no completion |
| `--all` | recv | Static flag, no value |
| `--include-self` | recv | Static flag, no value |
| `--upsert` | register | Static flag, no value |
| `--yes` | clear | Static flag, no value (confirmation bypass) |
| `--project NAME` | all | No completion (project name is arbitrary) |

The current completion scripts handle **subcommand names** and **status values**
(`--status` choices). Agent ID completion for `send` is implemented dynamically.
No other flag arguments are completed dynamically today — this is acceptable
but should be noted when adding new commands.

## Testing completions

```bash
# Bash
source completion/a2a.bash
a2a <TAB>           # should show all subcommands
a2a send <TAB>      # should suggest registered agent ids
a2a status <TAB>    # should show: active idle done blocked

# Zsh
fpath=(completion $fpath)
autoload -Uz compinit && compinit
a2a <TAB>
```

## Style

- Keep it simple — complete subcommands and flag values, not free-form arguments.
- The `send` completion attempts to call `a2a list` at completion time to suggest
  agent IDs. If `a2a` is not on PATH or the bus is empty, this call fails silently
  and falls back to no suggestions — that is acceptable.
- Do not add hard-coded agent IDs. Always derive them dynamically.
- Flag completions should prefer static values over dynamic calls unless the
  dynamic call is cheap (a single `a2a list --json`).

## See also

- [`../docs/AGENTS.md`](../docs/AGENTS.md) — Doc ownership and maintenance
- [`../README.md`](../README.md) — Project overview with shell completions section
- [`../a2a.py`](../a2a.py) — Source for the CLI (completions must mirror it)
