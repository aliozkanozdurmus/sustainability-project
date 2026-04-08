# E2E Development Runbook

## Purpose
Use this runbook when you are working on browser-level verification for the web app.
The repository keeps Playwright smoke coverage, manual smoke tooling, and shared E2E bootstrap utilities in one dedicated location so the suite is easier to maintain.

## E2E Layout
- `apps/web/src/lib/load-root-env.mjs`: shared repo-root env loader for Next.js and Playwright entrypoints
- `apps/web/e2e/playwright.config.ts`: Playwright smoke configuration
- `apps/web/e2e/specs/`: browser test specs
- `apps/web/e2e/helpers.ts`: shared workspace seeding, API setup, and flow helpers
- `apps/web/e2e/scripts/playwright-env.mjs`: Docker/bootstrap orchestration and shared environment setup
- `apps/web/e2e/scripts/run-playwright-e2e.mjs`: standard smoke runner
- `apps/web/e2e/scripts/run-playwright-manual-smoke.mjs`: guided screenshot-and-download smoke runner

## First-Time Setup
Create `/.env` from `/.env.example` at the repository root, then install dependencies:

```bash
pnpm install
pnpm --filter web exec playwright install --with-deps chromium
```

## Run the Standard E2E Smoke Flow
This command prepares the demo workspace, ensures the required services are healthy, and executes the Playwright suite:

```bash
pnpm --filter web e2e
```

If you already started the full Docker stack yourself, skip the extra bootstrap step:

```bash
pnpm --filter web e2e -- --skip-docker
```

## Run the Manual Smoke Flow
Use this when you want deterministic screenshots and a downloaded PDF artifact for README or release verification:

```bash
pnpm --filter web e2e:manual-smoke
```

With an already-running local stack:

```bash
pnpm --filter web e2e:manual-smoke -- --skip-docker
```

## Artifact Locations
- `output/playwright/report/`: HTML Playwright report
- `output/playwright/test-results/`: traces, videos, and failure screenshots
- `output/playwright/downloads/`: downloaded manual-smoke PDFs
- `output/playwright/manual-smoke/`: screenshot sequences and summary JSON

## Conventions
- Add new end-to-end coverage under `apps/web/e2e/specs/`.
- Reuse `helpers.ts` for workspace priming, seeded tenant context, and API-assisted setup before adding new ad hoc bootstrapping code.
- Keep repo-root env loading in `apps/web/src/lib/load-root-env.mjs` so Next.js and Playwright stay aligned.
- Keep bootstrap logic in `apps/web/e2e/scripts/` so package scripts and CI stay aligned.
- Write Playwright outputs only to the repository-root `output/playwright/` tree. Do not create app-local artifact folders such as `apps/web/output/`.

## CI Notes
The CI workflow installs Chromium, runs the happy-path smoke subset through the web package script, and uploads `output/playwright/` artifacts when the job fails.
