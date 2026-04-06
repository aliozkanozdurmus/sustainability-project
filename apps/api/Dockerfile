# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /workspace

RUN python -m pip install --upgrade pip
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libglib2.0-0 \
        libharfbuzz-subset0 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libjpeg62-turbo \
        libopenjp2-7 \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/README.md apps/api/README.md
COPY apps/api/alembic.ini apps/api/alembic.ini
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/api/alembic apps/api/alembic
COPY apps/api/app apps/api/app

RUN python -m pip install -e "apps/api[dev]"

FROM base AS dev

COPY . .

WORKDIR /workspace/apps/api

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS production

COPY . .

WORKDIR /workspace/apps/api

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
