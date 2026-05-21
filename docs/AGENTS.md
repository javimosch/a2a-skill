     1|# AGENTS.md — docs/
     2|
     3|All user-facing documentation lives here. One file per topic.
     4|
     5|## Ownership rules
     6|
     7|Every file in `docs/` is **owned by a feature or module**. Before editing,
     8|know which module you are documenting and check that the implementation
     9|matches what you write.
    10|
    11|| Doc file | Owned by | Keep in sync with |
    12||----------|----------|-------------------|
    13|| `SKILL.md` | `/a2a` skill spec | kit prompt in `a2a-spawn`, `smoke_test.sh` |
    14|| `CLIENT_API.md` | `a2a_client.py` | public method signatures |
    15|| `QUICKSTART.md` | install + first run | `install.sh`, `a2a --help` output |
    16|| `INSTALLATION.md` | `install.sh` | path resolution in `a2a` wrapper |
    17|| `AUDIT.md` | `a2a_audit.py` | `AuditClient` methods |
    18|| `ENCRYPTION.md` | `a2a_crypto.py` | `CryptoClient` methods |
    19|| `FTS_SEARCH.md` | `a2a_fts.py` | `FTSClient` methods |
    20|| `PRIORITY.md` | `a2a_priority.py` | `PriorityClient`, `Priority` enum |
    21|| `ROUTING.md` | `a2a_routing.py` | `RoutingClient`, `RoutingRule`, `RoutingAction` |
    22|| `GIT_AWARE.md` | `a2a_git_aware.py` | `GitAwareClient` methods |
    23|| `REST_API.md` | `a2a_server.py` | endpoint handlers |
    24|| `GO_CLIENT_API.md` | `a2a_client.go` | exported functions |
    25|| `NODE_CLIENT_API.md` | `a2a_client.js` | exported class |
    26|| `RUST_CLIENT_API.md` | `src/lib.rs` | `Client` struct methods |
    27|| `DEPLOYMENT.md` | `docker-compose.yml`, `Dockerfile.multi` | image definitions |
    28|| `ADVANCED_PATTERNS.md` | `examples/` | example files |
    29|| `INTEGRATION_GUIDE.md` | `examples/` | cross-interface patterns |
    30|| `TROUBLESHOOTING.md` | operations | common issues |
    31|| `SECURITY_HARDENING.md` | `a2a_crypto.py` + ops | production security |
    32|| `V13_QUICKREF.md` | all v1.3 modules | feature code snippets |
    33|| `GO_CLI_REFERENCE.md` | `cmd/a2a/main.go` | Go binary CLI flags |
    34|
    35|## SKILL.md is duplicated intentionally
    36|
    37|`SKILL.md` exists at **both** `docs/SKILL.md` (this directory) and the project
    38|root `SKILL.md`. The root copy is required because `~/.claude/skills/a2a` is
    39|a symlink to the project root — Claude Code's skill loader reads `SKILL.md`
    40|at the symlink target root. Always edit `docs/SKILL.md` and then copy to root:
    41|
    42|```bash
    43|cp docs/SKILL.md ../SKILL.md
    44|```
    45|
    46|If you update the kit prompt in `SKILL.md`, also update the inlined copy in
    47|`smoke_test.sh` and `smoke_test_multi.sh` — they embed the kit prompt directly.
    48|
    49|## Adding a new doc file
    50|
    51|1. Name it `TOPIC.md` in ALL_CAPS. Use the topic as the stem (e.g. `CACHING.md`).
    52|2. Add an entry to the ownership table above.
    53|3. Add it to `README.md`'s docs section at the project root.
    54|4. If it documents a new module, add the module to the repo layout in root `AGENTS.md`.
    55|
    56|## What not to put here
    57|
    58|- **Test output or benchmark numbers** — these rot. Link to commands instead.
    59|- **Inline code that duplicates source** — paste signatures only, not implementations.
    60|- **Session logs or bus history** — those belong in `review.md` at most, and only temporarily.
    61|
    62|## review.md
    63|
    64|`review.md` is a scratchpad for post-sprint notes. It is **not** canonical
    65|documentation. Content here may be stale. Do not rely on it for implementation
    66|decisions — read the source.
    67|