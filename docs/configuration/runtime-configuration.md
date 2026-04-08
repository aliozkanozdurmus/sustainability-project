# Runtime Configuration

Status: Public-safe configuration catalog
Date: 2026-03-10

## 1) Policy
- The only committed environment template is repo-root `/.env.example`.
- Local developers should use a single untracked repo-root `/.env` for file-based runtime configuration.
- Service-local `.env` files are not part of the supported workflow.
- Docker Compose reads the same root `/.env` for shared defaults and overrides container-local endpoints inline.
- Production secrets should come from Azure Key Vault or equivalent platform secret stores.

## 2) Shared Policy-Locked Variables
| Variable | Purpose | Notes |
|---|---|---|
| `DATABASE_URL` | Primary application database connection. | Must target Neon PostgreSQL (`*.neon.tech`). |
| `REDIS_URL` | Queue and cache connection. | Used by API and worker. |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint base URL. | Azure-only policy. |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key. | Do not commit. Prefer managed identity where supported. |
| `AZURE_OPENAI_API_VERSION` | API version for Azure OpenAI. | Keep aligned across services. |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | Chat deployment name. | Must remain `gpt-5.2`. |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Embedding deployment name. | Must remain `text-embedding-3-large`. |
| `ALLOW_LOCAL_DEV_DATABASE` | Opt-in local PostgreSQL override for Docker development. | Must remain `false` outside local development. |

## 3) Web Runtime Variables
| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Browser-facing API base URL. |
| `NEXT_PUBLIC_DEFAULT_TENANT_ID` | Optional tenant fallback for local demos. |
| `NEXT_PUBLIC_DEFAULT_PROJECT_ID` | Optional project fallback for local demos. |

Only `NEXT_PUBLIC_*` variables may be exposed to browser runtimes.

## 4) API Runtime Variables
| Variable | Purpose |
|---|---|
| `APP_ENV` | Runtime mode such as `development` or `production`. |
| `API_PREFIX` | Optional API route prefix. |
| `API_VERSION` | API version string. |
| `CORS_ALLOW_ORIGINS` | Comma-separated allowed web origins. |
| `ARQ_QUEUE_NAME` | Queue name consumed by background jobs. |
| `AZURE_STORAGE_ACCOUNT_NAME` | Azure Blob account name when using managed identity auth. |
| `AZURE_STORAGE_CONNECTION_STRING` | Fallback blob auth option. |
| `AZURE_STORAGE_CONTAINER_RAW` | Raw evidence container name. |
| `AZURE_STORAGE_CONTAINER_PARSED` | Parsed document container name. |
| `AZURE_STORAGE_CONTAINER_ARTIFACTS` | Report artifact container name. |
| `AZURE_STORAGE_USE_LOCAL` | Use local filesystem storage for development. |
| `LOCAL_BLOB_ROOT` | Local blob root path. |
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | Azure Document Intelligence endpoint. |
| `AZURE_DOCUMENT_INTELLIGENCE_API_KEY` | Azure Document Intelligence key. |
| `AZURE_DOCUMENT_INTELLIGENCE_API_VERSION` | Azure Document Intelligence API version. |
| `AZURE_AI_SEARCH_ENDPOINT` | Azure AI Search endpoint. |
| `AZURE_AI_SEARCH_API_KEY` | Azure AI Search key. |
| `AZURE_AI_SEARCH_INDEX_NAME` | Search index name. |
| `AZURE_AI_SEARCH_USE_LOCAL` | Enable local fallback search index. |
| `LOCAL_SEARCH_INDEX_ROOT` | Local search index root path. |
| `LOCAL_CHECKPOINT_ROOT` | Local orchestration checkpoint path. |
| `WORKFLOW_RETRY_MAX_PER_NODE` | Retry cap per node. |
| `WORKFLOW_RETRY_BASE_SECONDS` | Base retry delay. |
| `WORKFLOW_RETRY_MAX_DEFER_SECONDS` | Max retry delay. |
| `WORKFLOW_EXECUTE_MAX_STEPS` | Workflow step budget per run. |
| `AZURE_OPENAI_IMAGE_DEPLOYMENT` | Primary image deployment name for report visuals. |
| `AZURE_OPENAI_IMAGE_FALLBACK_DEPLOYMENT` | Fallback image deployment name for report visuals. |
| `VERIFIER_MODE` | Verifier implementation mode. |
| `VERIFIER_PASS_THRESHOLD` | PASS threshold. |
| `VERIFIER_UNSURE_THRESHOLD` | UNSURE threshold. |
| `REPORT_FACTORY_DEFAULT_BLUEPRINT_VERSION` | Default report blueprint version. |
| `REPORT_FACTORY_DEFAULT_LOCALE` | Default report locale. |

## 5) Worker Runtime Variables
| Variable | Purpose |
|---|---|
| `APP_ENV` | Runtime mode such as `development` or `production`. |
| `WORKER_CONCURRENCY` | Worker parallelism. |
| `QUEUE_NAME` | ARQ queue name. |
| `OCR_JOB_MAX_RETRIES` | OCR retry cap. |
| `OCR_RETRY_BASE_SECONDS` | OCR base retry delay. |
| `OCR_RETRY_MAX_DEFER_SECONDS` | OCR max retry delay. |
| `INDEX_JOB_MAX_RETRIES` | Indexing retry cap. |
| `INDEX_RETRY_BASE_SECONDS` | Indexing base retry delay. |
| `INDEX_RETRY_MAX_DEFER_SECONDS` | Indexing max retry delay. |
| `PACKAGE_JOB_MAX_RETRIES` | Package retry cap. |
| `PACKAGE_RETRY_BASE_SECONDS` | Package base retry delay. |
| `PACKAGE_RETRY_MAX_DEFER_SECONDS` | Package max retry delay. |

## 6) Playwright and Local Dev Helper Variables
| Variable | Purpose |
|---|---|
| `PLAYWRIGHT_WEB_BASE_URL` | Base URL for browser smoke flows. |
| `PLAYWRIGHT_API_BASE_URL` | API base URL used by Playwright helpers. |
| `PLAYWRIGHT_DEMO_TENANT_ID` | Optional pre-seeded tenant override for local smoke flows. |
| `PLAYWRIGHT_DEMO_PROJECT_ID` | Optional pre-seeded project override for local smoke flows. |

## 7) Public Repository Guardrails
- Never commit real keys, passwords, connection strings, or signed URLs.
- If a credential ever reaches git history, rotate it before making the repository public.
- Keep example values obviously fake and tenant-neutral in documentation.
