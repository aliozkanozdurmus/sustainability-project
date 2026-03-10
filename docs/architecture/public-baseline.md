# Public Architecture Baseline

Status: Public-safe baseline
Date: 2026-03-10

## 1) Purpose
This document is the public architecture baseline for the repository.
It replaces the internal planning file that was removed before making the project public.

## 2) Non-Negotiable Product Rules
- Azure AI Foundry and Azure OpenAI are the only allowed inference paths.
- Allowed model names are locked to `gpt-5.2` and `text-embedding-3-large`.
- All numeric claims require deterministic calculation artifacts.
- All publishable claims require evidence-backed citations.
- Cross-tenant isolation is mandatory across API, retrieval, storage, and approvals.

## 3) One-Click Report Pipeline
1. Resolve applicability and active framework scope.
2. Validate readiness, completeness, and critical evidence presence.
3. Route tasks across retrieval, calculator, writer, and verifier stages.
4. Run coverage audit and human approval checkpoints.
5. Build the publish bundle and dashboard snapshots.

## 4) Readiness, Evidence, and Data Quality
- Missing critical evidence blocks generation or publish depending on policy severity.
- Completeness below the required threshold moves the run into remediation mode.
- KPI freshness, ownership, and evidence grade are validated before narrative generation.
- Dashboard insights may consume only verified claims and approved KPI snapshots.

## 5) Technology and Infrastructure Baseline
- Frontend: Next.js App Router, React, TypeScript, Tailwind, shadcn/ui.
- API: FastAPI, Pydantic v2, SQLAlchemy, Alembic.
- Worker: Python ARQ worker for OCR and indexing jobs.
- Data plane: Neon PostgreSQL, Azure Blob Storage, Azure AI Search, Redis.
- Orchestration: LangGraph-based typed state workflow.

## 6) Package and Dependency Governance
- Dependency changes require architecture review when they affect runtime policy, traceability, or compliance surfaces.
- Production charting is standardized on ECharts.
- Tailwind plus shadcn/ui is the single production CSS/component baseline.
- Public documentation must not rely on versioned secret templates.

## 7) Dashboard UI and Motion Guardrails
- Information density must stay high without compromising audit traceability.
- Motion is allowed only when it clarifies system state, workflow progress, or evidence lineage.
- Reduced-motion support is required.
- Board-facing views must show freshness, quality grade, and traceability access points.

## 8) Approval, Publish, and Audit Controls
- Verifier `FAIL` on critical claims blocks publish.
- Missing signing-chain approvals block publish.
- Packaging must preserve citation navigability and audit bundle completeness.
- Observability must capture retries, loop depth, latency, and publish-readiness metrics.
