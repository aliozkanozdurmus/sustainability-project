# Veni AI Sustainability Cockpit Worker

ARQ worker service for background jobs in the ESG platform.

## Runtime policy locks

- `DATABASE_URL` must target Neon PostgreSQL (`*.neon.tech`) in production.
- Local Docker development may use the compose PostgreSQL service only when `APP_ENV=development` and `ALLOW_LOCAL_DEV_DATABASE=true`.
- `AZURE_OPENAI_CHAT_DEPLOYMENT` must be `gpt-5.2`.
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` must be `text-embedding-3-large`.

## Local install

```bash
python -m pip install -e .[dev]
```

## Execute sample job (local smoke)

```bash
python -m worker.run_once
```

## Run tests

```bash
python -m pytest tests -q
```
