# Docker Development Runbook

## Purpose
Use the root `compose.yaml` when you want the entire local stack running together:
- Next.js web app
- FastAPI API
- ARQ worker
- PostgreSQL
- Redis

This setup is intended for local development only.
Production database policy remains Neon PostgreSQL.

## Prerequisites
- Docker Desktop or Docker Engine with Compose v2
- 6 GB+ free RAM recommended for the full stack

## What the Stack Does
- Boots PostgreSQL and Redis locally.
- Starts the API with Alembic migrations applied on container startup.
- Starts the worker against the same database and queue.
- Starts the web app in hot-reload mode on port `3000`.
- Keeps blob storage, search index, and orchestration checkpoints on the repository filesystem for local inspection.

## Start the Stack
Create `/.env` from `/.env.example` at the repository root before starting Docker Compose.

```bash
docker compose up --build
```

## Endpoints
- Web: `http://localhost:3000`
- API: `http://localhost:8000`
- API liveness: `http://localhost:8000/health/live`
- API readiness: `http://localhost:8000/health/ready`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

## Important Environment Behavior
- Compose resolves shared runtime defaults from the repo-root `/.env`.
- `ALLOW_LOCAL_DEV_DATABASE=true` is set only inside the compose workflow so the API and worker may use the local PostgreSQL container.
- Compose overrides database and Redis endpoints inline for container-to-container networking.
- Only `NEXT_PUBLIC_*` variables are passed into the web container environment.
- Local filesystem fallbacks stay enabled for blob storage and search index.
- Azure-backed features remain optional. If you need live OCR, Azure OpenAI, or Azure AI Search, inject the required credentials through the untracked root `.env` or shell environment variables before starting the stack.

## Useful Commands
```bash
docker compose up --build
docker compose logs -f api
docker compose logs -f worker
docker compose exec api pytest tests/test_settings_policy.py -q
pnpm --filter web e2e -- --skip-docker
pnpm --filter web e2e:manual-smoke -- --skip-docker
docker compose down
docker compose down -v
```

## Run E2E Against the Compose Stack
After the stack is healthy, you can reuse the running containers instead of letting the Playwright runner start Docker again:

```bash
pnpm --filter web e2e -- --skip-docker
pnpm --filter web e2e:manual-smoke -- --skip-docker
```

The web E2E harness lives under `apps/web/e2e/`:
- `playwright.config.ts` for smoke configuration
- `specs/` for user-flow coverage
- `scripts/` for environment bootstrap and manual smoke runners
- `helpers.ts` for shared workspace seeding and API-assisted setup

Artifacts are written to the repository root under `output/playwright/` so CI uploads and README-linked assets resolve consistently.

## Reset Local State
Use this only when you want a clean database and Redis volume:

```bash
docker compose down -v
```

Local API filesystem artifacts remain in `apps/api/storage/` because that directory is part of the repository working tree and is intentionally ignored by git.
