# Docker Compose Generator

This artifact demonstrates **2-agent sequential collaboration**: a **specifier** defines a 5-service Docker stack, and a **writer** produces the corresponding `docker-compose.yml` and `README.md`.

## How it works

1. The build script initializes the bus and registers three agents: `collector` (the build script), `specifier`, and `writer`
2. Each agent receives a task message from the collector
3. The specifier designs the stack architecture and sends it to the writer
4. The writer generates both output files and broadcasts them as bus messages
5. The build script captures the messages and writes them to `output/`

## Pattern

**Sequential handoff** — a linear 2-agent pipeline:

```
collector → specifier → writer → files
```

The writer waits for the specifier's input before generating output. This is the simplest collaboration pattern.

## Output

| File | Description |
|------|-------------|
| `output/docker-compose.yml` | Complete 5-service Docker Compose definition |
| `output/README.md` | Human-readable documentation for the stack |

## Stack

The generated stack includes:
- **frontend** — React (Vite) app served by Nginx (port 80)
- **backend** — Python FastAPI (port 8000)
- **db** — PostgreSQL 16 (port 5432)
- **cache** — Redis 7 (port 6379)
- **worker** — Celery worker for async tasks

## Output sizes (from opencode build)

- `output/docker-compose.yml` — 2,575 bytes: 5 services (frontend, backend, db, cache, worker), 2 named volumes, custom bridge network
- `output/README.md` — 1,642 bytes: service descriptions, how to start, env vars table, networking details

## Bus transcript (from opencode build)

```
STATS:
  Messages: 5 total (3 direct + 2 broadcast)
  Agents: 1 collector + 2 worker agents
  Top senders: writer (2), collector (2), specifier (1)

CONVERSATION:
  #1 collector -> specifier: Design 5-service Docker stack (React, FastAPI, PostgreSQL, Redis, Celery)
  #2 collector -> writer: Wait for spec, then generate docker-compose.yml + README
  #3 specifier -> writer: DOCKER STACK SPEC — 5 services, bridge network, healthchecks, env vars
  #4 writer -> ALL: FILE:docker-compose.yml (5 services with depends_on conditions)
  #5 writer -> ALL: FILE:README.md (stack overview, run instructions, env var reference)
```

## Running

```bash
python3 examples/artifacts/docker-compose-generator/build.py --cli opencode
```
