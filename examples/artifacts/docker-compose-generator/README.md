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

## Bus state (from latest run)

```
$ a2a list
ID                   ROLE                 CLI        STATUS
collector            build-script         python     active
specifier            stack specifier      opencode   done
writer               docker-compose writer opencode   active

$ a2a peek --limit 10
#1 collector -> specifier     "Your task: You are the stack specifier..."
#2 collector -> writer        "Your task: You are the docker-compose writer..."
#3 specifier -> writer        "DOCKER STACK SPEC\n\n== OVERVIEW ==..."
#4 writer -> ALL              "FILE:docker-compose.yml\n```yaml\nversion: '3.8'..."
#5 writer -> ALL              "FILE:README.md\n```markdown\n# Multi-Service..."
```

## Running

```bash
python3 examples/artifacts/docker-compose-generator/build.py --cli opencode
```
