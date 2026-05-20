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
| `PROJECT_STATUS.md` | release tracking | git tags, version numbers |

## SKILL.md is duplicated intentionally

`SKILL.md` exists at **both** `docs/SKILL.md` (this directory) and the project
root `SKILL.md`. The root copy is required because `~/.claude/skills/a2a` is
a symlink to the project root — Claude Code's skill loader reads `SKILL.md`
at the symlink target root. Always edit `docs/SKILL.md` and then copy to root:

```bash
cp docs/SKILL.md ../SKILL.md
```

If you update the kit prompt in `SKILL.md`, also update the inlined copy in
`smoke_test.sh` and `smoke_test_multi.sh` — they embed the kit prompt directly.

## Adding a new doc file

1. Name it `TOPIC.md` in ALL_CAPS. Use the topic as the stem (e.g. `CACHING.md`).
2. Add an entry to the ownership table above.
3. Add it to `README.md`'s docs section at the project root.
4. If it documents a new module, add the module to the repo layout in root `AGENTS.md`.

## What not to put here

- **Test output or benchmark numbers** — these rot. Link to commands instead.
- **Inline code that duplicates source** — paste signatures only, not implementations.
- **Session logs or bus history** — those belong in `review.md` at most, and only temporarily.

## review.md

`review.md` is a scratchpad for post-sprint notes. It is **not** canonical
documentation. Content here may be stale. Do not rely on it for implementation
decisions — read the source.
