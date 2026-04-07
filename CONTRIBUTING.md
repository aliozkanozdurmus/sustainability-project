# Contributing

## Scope
This repository contains a public-safe baseline of a sustainability reporting platform.
Changes should preserve traceability, deterministic numeric handling, and the Azure-only model policy.

## Prerequisites
- Node.js 20+
- pnpm 10+
- Python 3.12+

## Local Setup
1. Install workspace dependencies with `pnpm install`.
2. Install API dev dependencies with `python -m pip install -e "apps/api[dev]"`.
3. Install worker dev dependencies with `python -m pip install -e "services/worker[dev]"`.
4. Inject runtime configuration through local secrets or untracked `.env` files only.
5. For the full local container stack, use `docker compose up --build` and follow `docs/runbooks/docker-development.md`.

## Quality Gates
- Web: `pnpm --filter web lint`, `pnpm --filter web typecheck`, `pnpm --filter web test`
- Web E2E: `pnpm --filter web e2e` and `pnpm --filter web e2e:manual-smoke`
- API: `pytest apps/api/tests`
- Worker: `pytest services/worker/tests`
- Secret hygiene: no committed credentials, tokens, passwords, or live connection strings

Web browser automation is organized under `apps/web/e2e/`. Keep new Playwright specs in `apps/web/e2e/specs/`, shared helpers in `apps/web/e2e/helpers.ts`, and runner/bootstrap logic in `apps/web/e2e/scripts/`. Test artifacts belong in the repository-root `output/playwright/` tree, not under `apps/web/output/`.

## Pull Request Expectations
- Keep pull requests focused and reviewable.
- Include tests or a clear reason why tests are not applicable.
- Update documentation when interfaces, architecture, or runtime configuration change.
- Do not loosen tenant-isolation, citation, verifier-gate, or production database policy rules without an ADR-level rationale.
