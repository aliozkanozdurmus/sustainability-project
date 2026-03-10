# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /workspace

RUN python -m pip install --upgrade pip

COPY apps/api/README.md apps/api/README.md
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/api/app apps/api/app
COPY services/worker/README.md services/worker/README.md
COPY services/worker/pyproject.toml services/worker/pyproject.toml
COPY services/worker/worker services/worker/worker

RUN python -m pip install -e apps/api
RUN python -m pip install -e "services/worker[dev]"

FROM base AS dev

COPY . .

WORKDIR /workspace/services/worker

CMD ["python", "-m", "arq", "worker.app.WorkerSettings"]

FROM base AS production

COPY . .

WORKDIR /workspace/services/worker

CMD ["python", "-m", "arq", "worker.app.WorkerSettings"]
