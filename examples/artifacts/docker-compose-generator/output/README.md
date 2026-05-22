# Multi-Service Docker Stack

A modern web application stack with React frontend, FastAPI backend, PostgreSQL database, Redis cache, and Celery worker — all orchestrated via Docker Compose.

## Architecture



All services communicate over the internal  bridge. Only the frontend port (80) is exposed externally by default; the backend port (8000) is accessible for development.

## Services

### frontend (:80)
React (Vite) SPA served by Nginx. Reverse-proxies `/api/*` requests to the backend. Built via multi-stage Dockerfile — Node 20 for build, Nginx 1.25-alpine for runtime.

### backend (:8000)
Python FastAPI application with auto-reload for development. Exposes a `/health` endpoint for health checks. Connects to PostgreSQL via SQLAlchemy (async) and Redis for caching/task brokering.

### db (:5432)
PostgreSQL 16 Alpine with persistent storage in the `pgdata` named volume. Health-checked via `pg_isready`.

### cache (:6379)
Redis 7 Alpine for caching and Celery message brokering. Persistent storage in the `redisdata` named volume.

### worker
Celery worker sharing the backend codebase. Processes async tasks from the Redis broker. No external ports — communicates internally only.

## Getting Started

### Prerequisites

- Docker Engine 20.10+
- Docker Compose v2+

### Quick Start