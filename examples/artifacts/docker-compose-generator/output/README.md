# Multi-Service Web App Stack

A complete multi-service web application stack running on Docker Compose (v3.8 format).

## Services

### db — PostgreSQL 16 (Alpine)
Persistent relational database for application data. Exposes port `5432`. Uses a named volume `pgdata` for data persistence. Health-checked via `pg_isready`.

### cache — Redis 7 (Alpine)
In-memory data store used for caching and Celery task broker (two separate Redis logical databases: `0` and `1`). Exposes port `6379`. Uses a named volume `redisdata` for persistence.

### backend — FastAPI (Python 3.12)
Async web API built with FastAPI, served via Uvicorn on port `8000` with hot-reload enabled. Depends on `db` (healthy) and `cache` (started). Requires a `Dockerfile.backend` to build.

### worker — Celery Worker (Python 3.12)
Background task processor using Celery, consuming from the Redis broker at `redis://cache:6379/1`. Shares the same `Dockerfile.backend` as the backend service. No exposed ports.

### frontend — Vite + Nginx (two-stage build)
Static frontend built with Vite (Node 20) and served via Nginx on port `80`. Uses build-time arg `VITE_API_URL` to point to the backend API. Requires a `Dockerfile.frontend` for the multi-stage build.

## Getting Started

### Prerequisites
- Docker Engine 19.03+
- Docker Compose 1.27+

### Startup order (automated via depends_on)
1. **db** + **cache** start in parallel (no dependencies)
2. **backend** starts after `db` is healthy and `cache` is started
3. **worker** starts after `db` is healthy and `cache` is started (parallel with backend)
4. **frontend** starts after `backend` is started

### Start the stack