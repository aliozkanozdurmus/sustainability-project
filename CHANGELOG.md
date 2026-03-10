# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this repository follows semantic versioning once public releases are cut.

## [Unreleased]

### Added
- Root community files for license, contributing guidance, and code of conduct discoverability.
- Multi-service Dockerfiles for the web app, API, and worker.
- A root `compose.yaml` for a full local development stack with PostgreSQL and Redis.
- Development and example deployment runbooks under `docs/runbooks`.

### Changed
- Local Docker development can opt into a PostgreSQL container only with the explicit `ALLOW_LOCAL_DEV_DATABASE=true` override while production remains Neon-only.
