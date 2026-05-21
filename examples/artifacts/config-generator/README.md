# Config Generator Artifact

**Config-generator** demonstrates how two AI agents can collaborate via the
a2a bus to produce a complete server deployment configuration for a web
application stack (Node.js/Express + PostgreSQL + Nginx).

## What it produces

Three files under `output/`:

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Multi-service definition (app, db, nginx) with networks and volumes |
| `nginx.conf` | Reverse proxy configuration with SSL proxy settings and rate limiting |
| `.env.example` | Environment variable template with placeholders for secrets |

## Agents

| Agent | Role | Description |
|-------|------|-------------|
| `architect` | Infra architect | Describes the full server topology (services, network, volumes) |
| `implementer` | Config implementer | Generates the three configuration files from the architect's spec |

## Process

1. Architect sends a detailed infrastructure spec to implementer via the bus
2. Implementer generates docker-compose.yml, nginx.conf, and .env.example
3. Each file is broadcast with a `FILE:` prefix so the build script captures it
4. The build script writes all three to `output/`

## Running

```bash
cd /root/projects/a2a-skill
python3 examples/artifacts/config-generator/build.py --cli opencode
```

## Output quality (from opencode build)

- `docker-compose.yml` — 1,548 bytes: 3 services (nginx, app, db), networks, healthchecks, named volumes
- `nginx.conf` — 3,790 bytes: SSL termination, rate limiting, gzip, reverse proxy to app, health endpoint
- `.env.example` — 1,618 bytes: database, session, CORS, Redis env vars with comments

## Bus transcript (from opencode build)

```
STATS:
  Messages: 4 total (1 direct + 3 broadcast)
  Agents: 1 collector + 2 worker agents
  Top senders: implementer (3), collector (1)

CONVERSATION:
  #1 collector -> architect: Task: Describe topology for Node.js/Express — PostgreSQL — Nginx
  #2 architect -> implementer: Spec: 3 containers (nginx, app:3000, db:5432), bridge network, healthchecks, volumes
  #3 implementer -> ALL: FILE:docker-compose.yml (3 services with healthcheck conditions)
  #4 implementer -> ALL: FILE:nginx.conf (SSL proxy, rate limiting, gzip, /health passthrough)
  #5 implementer -> ALL: FILE:.env.example (DB, session, CORS, Redis env vars)

Note: implementer sent all 3 files as broadcasts; architect sent a single spec message.
```

## Requirements

- `a2a` and `a2a-spawn` on PATH (or at repo root)
- An AI CLI: `claude`, `opencode`, or `pi`
