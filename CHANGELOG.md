# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this repository follows semantic versioning once public releases are cut.

Until the first tagged release, `Unreleased` tracks all merged changes since the public baseline.

## [Unreleased]

### Added
- Root community files for license, contributing guidance, and code of conduct discoverability.
- README product preview screenshots for the dashboard, report builder, retrieval lab, approval center, and evidence center.
- Multi-service Dockerfiles for the web app, API, and worker.
- A root `compose.yaml` for a full local development stack with PostgreSQL and Redis.
- Development and example deployment runbooks under `docs/runbooks`.
- Deterministic report PDF artifact generation, persistence, blob upload/download helpers, and run API support for exposing `report_pdf` outputs.
- Playwright-based end-to-end smoke coverage in CI, including reusable web E2E helpers, environment scripts, and manual smoke tooling.
- Report factory foundation across the API, data model, and storage layers, including company profiles, brand kits, report blueprints, report packages, report visual assets, KPI snapshots, and related migrations.
- Integration APIs and services for connector configuration, sync execution, canonical fact access, and workspace context retrieval.
- Report packaging services, package templates, and download/status flows for brandable report outputs.
- Turkish localization support and richer visual fallback generation for report packaging, including localized labels, number formatting, freshness/source labels, and scene-specific image rendering.
- Worker-side report package job coverage and integration-focused backend tests.

### Changed
- Local Docker development can opt into a PostgreSQL container only with the explicit `ALLOW_LOCAL_DEV_DATABASE=true` override while production remains Neon-only.
- Publish flow now queues report packaging asynchronously instead of building packages inline, and returns a more consistent publish response shape for package/artifact state.
- Runs APIs, generated OpenAPI, and shared API types were expanded to surface report artifact and package metadata throughout list, status, publish, and download flows.
- Workspace and report-building UI flows were updated to support report factory, package-aware publishing, and integration-backed context.
- Integration extraction and normalization were hardened for connector-specific shapes such as `sap_odata`, `logo_tiger_sql_view`, and `netsis_rest`, including cursor handling, key resolution, unit aliases/defaults, and diagnostics.
- Report package lifecycle handling now explicitly creates, resets, and tracks package records before work is enqueued.

### Fixed
- Publish and packaging errors now record failure state more reliably so broken package attempts do not appear healthy after exceptions.
- Integration coercion and unit normalization logic now fail less often on inconsistent upstream payloads and provide clearer diagnostics during sync processing.
- Settings validation and related tests now properly enforce the opt-in local database policy during development.
