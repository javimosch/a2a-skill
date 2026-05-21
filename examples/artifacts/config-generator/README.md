# Config Generator Artifact

**Config-generator** demonstrates how two AI agents can collaborate via the
a2a bus to produce a complete server deployment configuration for a web
application stack.

## What it produces

Three files under `output/`:

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Multi-service definition (app, db, nginx) |
| `nginx.conf` | Reverse proxy configuration with SSL proxy settings |
| `.env.example` | Environment variable template with placeholders |

## Agents

| Agent | Role | Description |
|-------|------|-------------|
| `architect` | Infra architect | Describes the full server topology (services, network, volumes) |
| `implementer` | Config implementer | Generates the three configuration files from the spec |

## Process

1. Architect sends a detailed infrastructure spec to implementer via the bus
2. Implementer generates docker-compose.yml, nginx.conf, and .env.example
3. Each file is broadcast with a `FILE:` prefix so the build script captures it
4. The build script writes all three to `output/`

## Running

```bash
# From the repo root:
python3 examples/artifacts/config-generator/build.py --cli opencode --project artifact-config

# With a specific model:
python3 examples/artifacts/config-generator/build.py --cli claude --model haiku
```

Output lands in `output/` (gitignored).

## Requirements

- `a2a` and `a2a-spawn` on PATH (or at repo root)
- An AI CLI: `claude`, `opencode`, or `pi`
