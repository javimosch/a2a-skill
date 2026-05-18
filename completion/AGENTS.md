# AGENTS.md — completion/

Shell completion scripts for the `a2a` CLI.

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
