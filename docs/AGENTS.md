# AGENTS.md — docs/

All user-facing documentation lives here. One file per topic.

## Ownership rules

Every file in `docs/` is **owned by a feature or module**. Before editing,
know which module you are documenting and check that the implementation
matches what you write.

| Doc file | Owned by | Keep in sync with |
|----------|----------|-------------------|
| `SKILL.md` | `/a2a` skill spec | kit prompt in `a2a-spawn`, `smoke_test.sh` |
| `CLIENT_API.md` | `a2a_client.py` | public method signatures |
| `QUICKSTART.md` | install + first run | `install.sh`, `a2a --help` output |
| `INSTALLATION.md` | `install.sh` | path resolution in `a2a` wrapper |
| `AUDIT.md` | `a2a_audit.py` | `AuditClient` methods |
| `ENCRYPTION.md` | `a2a_crypto.py` | `CryptoClient` methods |
| `FTS_SEARCH.md` | `a2a_fts.py` | `FTSClient` methods |
| `PRIORITY.md` | `a2a_priority.py` | `PriorityClient`, `Priority` enum |
| `ROUTING.md` | `a2a_routing.py` | `RoutingClient`, `RoutingRule`, `RoutingAction` |
| `GIT_AWARE.md` | `a2a_git_aware.py` | `GitAwareClient` methods |
| `REST_API.md` | `a2a_server.py` | endpoint handlers |
| `GO_CLIENT_API.md` | `a2a_client.go` | exported functions |
| `NODE_CLIENT_API.md` | `a2a_client.js` | exported class |
| `RUST_CLIENT_API.md` | `src/lib.rs` | `Client` struct methods |
| `DEPLOYMENT.md` | `docker-compose.yml`, `Dockerfile.multi` | image definitions |
| `ADVANCED_PATTERNS.md` | `examples/` | example files |
| `INTEGRATION_GUIDE.md` | `examples/` | cross-interface patterns |
| `TROUBLESHOOTING.md` | operations | common issues |
| `SECURITY_HARDENING.md` | `a2a_crypto.py` + ops | production security |
| `V13_QUICKREF.md` | all v1.3 modules | feature code snippets |
| `GO_CLI_REFERENCE.md` | `cmd/a2a/main.go` | Go binary CLI flags |
| `PITFALLS.md` | artifact smoke testing | `examples/artifacts/`, `_util.py` |

## SKILL.md is duplicated (three copies, chain of truth)

The canonical skill specification lives at **`.agents/skills/a2a/SKILL.md`**.
It is duplicated into two stubs for CLI discovery:

1. **`.agents/skills/a2a/SKILL.md`** — canonical, edit this one
2. **`docs/SKILL.md`** — stub with quick reference, points to canonical
3. **`SKILL.md`** (root) — stub, points to `docs/SKILL.md` → canonical

The root copy is required because `~/.claude/skills/a2a` is a symlink to the
project root — Claude Code's skill loader reads `SKILL.md` at the symlink
target root. The `docs/` copy is for repository browsing. Always edit the
canonical at `.agents/skills/a2a/SKILL.md`, then sync the stubs:

```bash
# After editing canonical at .agents/skills/a2a/SKILL.md:
# docs/SKILL.md and root SKILL.md are stubs — update quick-ref only
```

If you update the kit prompt in the canonical `SKILL.md`, also update the
inlined copy in `smoke_test.sh` and `smoke_test_multi.sh` — they embed the
kit prompt directly.

## Related AGENTS.md files outside docs/

Sub-directories have their own `AGENTS.md` with scoped guidance. Keep the
cross-references in this file up to date when those files change:

- `../examples/AGENTS.md` — Example agent patterns, client choice guide
- `../completion/AGENTS.md` — Shell completion scripts for Bash and Zsh
- `../src/AGENTS.md` — Rust client library
- `../AGENTS.md` (root) — Full repo guide for AI agents

## Adding a new doc file

1. **Name it `TOPIC.md` in ALL_CAPS.** Use the topic as the stem (e.g. `CACHING.md`).
2. **Add an entry to the ownership table above.** Fill in the doc file, the owning
   module, and the source file(s) it must stay in sync with.
3. **Add it to `README.md`'s docs section** at the project root.
4. **If it documents a new module,** add the module to the repo layout in root
   `AGENTS.md` and the file to the test-tree section if applicable.
5. **Wire any cross-references** from related docs files (e.g., if you add
   `CACHING.md`, add a "See also" link from `ADVANCED_PATTERNS.md`).

## Removing or deprecating a doc file

- Mark it with a `> **Deprecated**` banner at the top, pointing to the replacement.
- Do not delete files without a transition period — agents may have cached links.
- Remove the ownership table entry only after the deprecation notice has been
  in place for at least one minor version.

## What not to put here

- **Test output or benchmark numbers** — these rot. Link to commands instead.
- **Inline code that duplicates source** — paste signatures only, not implementations.
- **Session logs or bus history** — those belong in `review.md` at most, and only temporarily.
- **Process documents for contributors** — those go in `~/ai/a2a-dev/`, not in `docs/`.

## review.md

`review.md` is a scratchpad for post-sprint notes. It is **not** canonical
documentation. Content here may be stale. Do not rely on it for implementation
decisions — read the source. It exists only temporarily and should be cleared
when its observations have been either addressed or moved to permanent docs.

## Keeping this file (docs/AGENTS.md) in sync

This file describes the documentation system itself. Keep it accurate when:

- A new doc file is added or removed
- Ownership of a doc file changes
- A new sub-directory with its own AGENTS.md is created
- The SKILL.md chain (root → docs → .agents) changes
