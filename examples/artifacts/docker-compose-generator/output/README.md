# Multi-Service Application Stack

A microservices-based application stack with 5 services communicating over a shared internal bridge network (`appnet`). Built with Docker Compose v3.8.

## Services

### 1. db (PostgreSQL 16)
- **Image**: `postgres:16-alpine`
- **Port**: `5432`
- **Purpose**: Primary relational database. Stores application state with asyncpg support.
- **Volume**: `pgdata` (named) for persistent data storage.
- **Init**: Optional `./init-db.sh` script loaded into `/docker-entrypoint-initdb.d/`.

### 2. cache (Redis 7)
- **Image**: `redis:7-alpine`
- **Port**: `6379`
- **Purpose**: In-memory cache, Celery message broker, and Celery result backend.
- **Volume**: `redisdata` (named) for AOF persistence.
- **Auth**: Password-protected via `--requirepass`.

### 3. backend (Python FastAPI)
- **Build**: `./backend/Dockerfile`
- **Port**: `8000`
- **Purpose**: REST API server. Handles business logic, database access, and request routing.
- **Health**: Exposes `/health` endpoint for readiness checks.
- **Depends on**: `db` and `cache` (both must be healthy).

### 4. worker (Celery)
- **Build**: Same image as backend (`./backend/Dockerfile`)
- **Purpose**: Background task processor. Runs 4 concurrent workers via Celery.
- **Health**: Uses `celery inspect ping` to verify worker responsiveness.
- **Depends on**: `db` and `cache` (both must be healthy).

### 5. frontend (React/Vite + Nginx)
- **Build**: Two-stage `./frontend/Dockerfile`
  - Stage 1: `node:20-alpine` — installs deps and builds with Vite.
  - Stage 2: `nginx:1.25-alpine` — serves static build output.
- **Port**: `80`
- **Purpose**: Single-page application served by Nginx. Proxies `/api/` requests to `backend:8000`.
- **Health**: Nginx health endpoint at `/health`.
- **Depends on**: `backend` (must be healthy).

## Getting Started

### Prerequisites
- Docker and Docker Compose v2 installed.

### Setup

1. **Clone the repository** and navigate to the project root.

2. **Create a `.env` file** with required environment variables: