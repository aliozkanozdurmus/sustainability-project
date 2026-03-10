# Example Deployment Runbook

## Purpose
This document shows a safe example production topology for the public baseline repository.
Treat it as an implementation guide, not as a one-click production template.

## Recommended Topology
- Web: Vercel or another managed Node platform for the Next.js app
- API: Azure Container Apps, Azure App Service, or another managed container runtime
- Worker: Azure Container Apps Jobs or a dedicated long-running container workload
- Database: Neon PostgreSQL
- Queue/cache: managed Redis
- Object storage: Azure Blob Storage
- Search: Azure AI Search
- Model endpoints: Azure AI Foundry and Azure OpenAI only

## Production Policy Locks
- Do not enable `ALLOW_LOCAL_DEV_DATABASE` in production.
- `DATABASE_URL` must point to Neon PostgreSQL (`*.neon.tech`).
- `AZURE_OPENAI_CHAT_DEPLOYMENT` must remain `gpt-5.2`.
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` must remain `text-embedding-3-large`.

## Deployment Sequence
1. Provision Neon PostgreSQL, managed Redis, Azure Blob Storage, Azure AI Search, Azure OpenAI, and Azure Document Intelligence.
2. Build and push the API and worker images from the repository Dockerfiles.
3. Run database migrations with `alembic upgrade head` before switching traffic.
4. Deploy the API with production secrets injected from Azure Key Vault or your platform secret manager.
5. Deploy the worker with the same runtime policy variables and queue/database endpoints as the API.
6. Deploy the web app with `NEXT_PUBLIC_API_BASE_URL` pointed at the public API origin.
7. Run post-deploy checks against `/health/live`, `/health/ready`, and a representative report workflow.

## Minimum Runtime Variables
### Web
- `NEXT_PUBLIC_API_BASE_URL`

### API and Worker
- `APP_ENV=production`
- `DATABASE_URL`
- `REDIS_URL`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5.2`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large`

### API Only
- `CORS_ALLOW_ORIGINS`
- `AZURE_STORAGE_ACCOUNT_NAME` or `AZURE_STORAGE_CONNECTION_STRING`
- `AZURE_STORAGE_CONTAINER_RAW`
- `AZURE_STORAGE_CONTAINER_PARSED`
- `AZURE_STORAGE_CONTAINER_ARTIFACTS`
- `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`
- `AZURE_DOCUMENT_INTELLIGENCE_API_KEY`
- `AZURE_AI_SEARCH_ENDPOINT`
- `AZURE_AI_SEARCH_API_KEY`
- `AZURE_AI_SEARCH_INDEX_NAME`

## Operational Checks
- Verify migrations completed successfully before routing live traffic.
- Verify the worker can enqueue and process a background job.
- Verify API readiness returns `200`.
- Verify web-to-API CORS policy matches the deployed frontend origin.
- Verify no secret values are committed into the repository or build logs.
