# Veni AI Sustainability Cockpit API

FastAPI service for the ESG reporting platform.

## Runtime policy locks

- `DATABASE_URL` must target Neon PostgreSQL (`*.neon.tech`).
- `AZURE_OPENAI_CHAT_DEPLOYMENT` must be `gpt-5.2`.
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` must be `text-embedding-3-large`.

## Local Run

```bash
python -m pip install -e .[dev]
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Health Endpoints

- `GET /health/live`
- `GET /health/ready`
