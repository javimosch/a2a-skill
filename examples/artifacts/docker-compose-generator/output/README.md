# Multi-Service Docker Stack

A 5-service application stack consisting of PostgreSQL, Redis, a Python FastAPI backend, a Celery worker, and a React Vite frontend served via Nginx.

## Services

### 1. db (PostgreSQL 16)
Relational database. Stores application data accessible via the backend.  
**Hostname:** `db` | **Port:** 5432 (internal only)

### 2. cache (Redis 7)
In-memory data store used for caching, Celery broker, and Celery result backend.  
**Hostname:** `redis` | **Port:** 6379 (internal only)

### 3. backend (Python FastAPI)
REST API built with FastAPI. Handles business logic, connects to PostgreSQL via SQLAlchemy (asyncpg), and uses Redis for caching and Celery task orchestration.  
**Hostname:** `backend` | **Port:** `8000:8000`

### 4. worker (Celery)
Background task processor. Executes async tasks from the backend using Celery. Shares the same image as the backend. No public ports.  
**Hostname:** `worker`

### 5. frontend (React Vite + Nginx)
Static frontend built with Vite and served by Nginx. Proxies API requests to the backend.  
**Hostname:** `frontend` | **Port:** `80:80`

## Getting Started