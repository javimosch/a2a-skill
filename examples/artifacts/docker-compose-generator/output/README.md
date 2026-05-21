# Multi-Service Docker Stack

A 5-service Docker Compose stack for a modern web application: React/Vite frontend served by Nginx, Python FastAPI backend, PostgreSQL 16 database, Redis 7 cache, and a Celery worker for async task processing.

## Services Overview

### 1. frontend — React (Vite) + Nginx

- **Role**: Serves the built React/Vite SPA via Nginx with SPA fallback routing, gzip compression, and security headers.
- **Build**: Multi-stage Dockerfile — `node:20-alpine` builds the app; `nginx:1.25-alpine` serves the static assets.
- **Access**: `http://localhost:80`
- **Health Endpoint**: `http://localhost:80/healthz`

### 2. backend — Python FastAPI

- **Role**: REST API server handling business logic, authentication, and data access.
- **Build**: `python:3.12-slim` with uvicorn ASGI server on port 8000.
- **Access**: `http://localhost:8000` — FastAPI auto-docs at `http://localhost:8000/docs`
- **Health Endpoint**: `http://localhost:8000/health`

### 3. db — PostgreSQL 16

- **Role**: Primary relational database for persistent application data.
- **Image**: Official `postgres:16-alpine`
- **Port**: `5432` (exposed for admin tools like pgAdmin or DBeaver)
- **Initialization**: SQL scripts in `./db/init/` are run automatically on first start.

### 4. cache — Redis 7

- **Role**: In-memory cache for session storage, API response caching, and Celery message broker.
- **Image**: Official `redis:7-alpine`
- **Port**: `6379`
- **Persistence**: RDB/AOF snapshots stored in the `redis-data` named volume.

### 5. worker — Celery Worker

- **Role**: Executes background/async tasks (email sending, report generation, data processing).
- **Build**: Reuses the same `backend` Docker image with an overridden command.
- **Concurrency**: 4 worker processes by default.
- **No exposed ports** — communicates internally via Redis broker.

## Getting Started

### Prerequisites

- Docker Engine 20.10+ and Docker Compose (v2 recommended)
- Git (for cloning the project repository)

### Start the Stack