# Multi-Service Docker Stack

A five-service microservices stack with PostgreSQL, Redis, FastAPI backend, Celery worker, and a React frontend served by Nginx.

## Services

### 1. Database (PostgreSQL 16)
- **Container**: 
- **Port**: 
- **Purpose**: Primary relational data store. Uses asyncpg via SQLAlchemy for async access from the FastAPI backend.
- **Persistence**: Named volume  at .

### 2. Cache (Redis 7)
- **Container**: 
- **Port**: 
- **Purpose**: In-memory cache, Celery message broker (result backend + broker), and session store.
- **Persistence**: Named volume  at .
- **Auth**: Password-protected via `REDIS_PASSWORD`.

### 3. Backend (FastAPI)
- **Container**: 
- **Port**: 
- **Purpose**: Async REST API built with FastAPI on Python 3.12. Handles business logic, auth, and data access.
- **Features**: Hot-reload dev mode via bind mount, health check endpoint at .
- **Dependencies**: Requires healthy  and .

### 4. Worker (Celery)
- **Container**:  (no external ports)
- **Purpose**: Background task processing — async jobs, email dispatch, data aggregation, scheduled tasks.
- **Concurrency**: 4 worker processes.
- **Dependencies**: Requires healthy , , and .

### 5. Frontend (React + Vite + Nginx)
- **Container**: 
- **Port**: 
- **Purpose**: Single-page application built with React and Vite. Served by Nginx with an API proxy to the backend.
- **Build**: Multi-stage Dockerfile — Node 20 for build, Nginx Alpine for runtime.
- **API Proxy**:  requests are proxied to .

## Getting Started

### Prerequisites
- Docker Engine 20.10+
- Docker Compose v2+

### Quick Start