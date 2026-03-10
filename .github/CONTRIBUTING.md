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

## Quality Gates
- Web: `pnpm --filter web lint`, `pnpm --filter web typecheck`, `pnpm --filter web test`
- API: `pytest apps/api/tests`
- Worker: `pytest services/worker/tests`
- Secret hygiene: no committed credentials, tokens, passwords, or live connection strings

## Pull Request Expectations
- Keep pull requests focused and reviewable.
- Include tests or a clear reason why tests are not applicable.
- Update documentation when interfaces, architecture, or runtime configuration change.
- Do not loosen tenant-isolation, citation, or verifier-gate rules without an ADR-level rationale.
