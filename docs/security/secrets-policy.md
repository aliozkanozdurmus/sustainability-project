# Secrets and Environment Policy (Azure-Only)

Status: Draft v1.0  
Date: 2026-03-05

## 1) Purpose
This policy defines allowed environment variables and secret handling for the ESG platform.

## 2) Core Security Rules
- No secrets in source code.
- No version-controlled environment files in the repository other than the fake-value root template `/.env.example`.
- Secrets must be loaded from Azure Key Vault in production where possible.
- Service-to-service auth should prefer Managed Identity.

## 3) AI Endpoint Allowlist
Allowed model endpoints:
- Azure AI Foundry
- Azure OpenAI

Required variables (by service profile):
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`
- deployment names (`AZURE_OPENAI_CHAT_DEPLOYMENT`, etc.)
- either managed identity flow or `AZURE_OPENAI_API_KEY` depending on environment

## 4) Denylist (Not Allowed)
The following model provider variables are disallowed in production config:
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `COHERE_API_KEY`
- `MISTRAL_API_KEY`

## 5) Runtime Configuration Contract
- Runtime variables are documented in `docs/configuration/runtime-configuration.md`.
- Local file-based configuration should use a single untracked repo-root `/.env`.
- Public repository history must never include live credentials or connection strings.

## 6) Rotation and Audit
- API keys rotate at least every 90 days or on incident.
- Secret access logs must be retained for audit.
- Any denylist violation fails CI and blocks release.

## 7) Validation Controls
Pre-merge checks must verify:
- required Azure variables exist in deployment configuration or secret stores
- denylist variables are absent from committed files and runtime manifests
- no accidental secret literal appears in repository
