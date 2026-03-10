# UI Starter Adaptation Blueprint

Status: Draft v0.1  
Date: 2026-03-05  
Task: T-011A

## 1) Objective
Define how to reuse proven SaaS dashboard patterns from `Kiranism/next-shadcn-dashboard-starter` without copying its product assumptions.  
This project keeps the package constraints and premium dashboard UI/motion guardrails from `docs/architecture/public-baseline.md` as hard rules.

## 2) Hard Constraints
- Keep current architecture and policy contracts as source of truth:
  - `README.md` system architecture sections
  - `docs/architecture/public-baseline.md` Sections 5, 6, and 7
  - `AGENTS.md` quality gates (citation + verifier + publish blockers)
- Azure-only AI policy is unchanged and unaffected by UI starter adoption.
- Do not import third-party auth/billing assumptions directly into core flows.
- Keep design system single-source: shadcn/ui + Tailwind tokens.

## 3) Reuse Strategy (Adopt Patterns, Not Product Logic)
Use the starter as a UI pattern donor for:
- dashboard shell composition
- sidebar/header ergonomics
- table/filter UX
- command palette and quick actions
- card density and spacing rhythm

Do not inherit:
- starter-specific auth stack assumptions
- starter-specific billing flows
- starter-specific domain entities

## 4) Mapping to Our Page Map
Reference: `README.md` Section 4 and `docs/architecture/public-baseline.md` Section 7.

1. Dashboard shell pattern
- Source pattern:
  - multi-zone shell with persistent sidebar + top actions
- Target routes:
  - `/app/dashboard/executive`
  - `/app/dashboard/board-cockpit`
  - `/app/dashboard/esg-analytics`
  - `/app/dashboard/risk-opportunity`
  - `/app/dashboard/operations-sla`

2. Data table pattern
- Source pattern:
  - server-side filtering, sorting, pagination UX
- Target routes:
  - `/app/projects/[projectId]/data-room`
  - `/app/projects/[projectId]/kpi-catalog`
  - `/app/projects/[projectId]/verification-center`
  - `/app/projects/[projectId]/filing-index`

3. Form/wizard pattern
- Source pattern:
  - multi-step forms with validation and autosave-like UX
- Target routes:
  - `/onboarding/*`
  - `/app/projects/new/wizard`

4. Kanban/queue visualization pattern
- Source pattern:
  - stage-based boards and status chips
- Target routes:
  - `/app/projects/[projectId]/report-builder`
  - `/app/projects/[projectId]/approvals`
  - `/app/projects/[projectId]/approvals/sla`

5. Command/search pattern
- Source pattern:
  - global command bar and keyboard-first nav
- Target areas:
  - dashboard global filters
  - project workspace quick jump
  - evidence search and traceability actions

## 5) Technical Delta for `apps/web`
Current baseline is minimal. The following will be implemented incrementally in upcoming UI tasks:

Required package alignment (from Section 66):
- `next-themes`
- `@tanstack/react-query`
- `@tanstack/react-table`
- `@tanstack/react-virtual`
- `react-hook-form`
- `zod`
- `@hookform/resolvers`
- `echarts`
- `echarts-for-react`

Recommended package alignment (from Section 66/67):
- `motion` (`motion/react`)
- `cmdk`
- `sonner`
- `date-fns`

## 6) Target Frontend Structure (Feature-Oriented)
The starter's feature grouping idea is adopted with our route map:

- `src/app/*`:
  - route entrypoints and layout composition only
- `src/features/dashboard/*`:
  - KPI cards, board cockpit widgets, infographic modules
- `src/features/projects/*`:
  - data room, KPI catalog, report builder, verification center
- `src/features/onboarding/*`:
  - wizard steps and completion scoring UI
- `src/features/approvals/*`:
  - approval queues, SLA timers, escalation actions
- `src/features/evidence/*`:
  - retrieval explorer, claim-citation-source drilldowns
- `src/components/ui/*`:
  - shared shadcn primitives only
- `src/lib/*`:
  - API clients, auth guards, shared helpers

## 7) Design Token and Motion Policy
Token system:
- use semantic tokens for states: `success`, `warning`, `critical`, `info`
- keep tenant branding via token aliases, not direct component colors

Motion policy:
- only meaningful transitions (state changes, workflow progress, filter transitions)
- respect `prefers-reduced-motion`
- no decorative continuous motion in board cockpit

## 8) Accessibility and Governance Guards
- WCAG 2.2 AA target for dashboard routes
- keyboard-operable filter and drilldown flows
- every critical KPI tile must display:
  - freshness timestamp
  - quality grade
  - verified status
- publish-related actions must remain role-gated and audit-logged

## 9) UI Migration Sequence (Post-T-011A)
1. `T-012-UI`:
   - app shell (sidebar/header/filter bar), token setup, theme plumbing
2. `T-013-UI`:
   - executive + board cockpit page skeletons with infographic card placeholders
3. `T-014-UI`:
   - table stack integration for data room and verification center
4. `T-015-UI`:
   - onboarding/project wizard scaffolds with form validation
5. `T-016-UI`:
   - motion + reduced-motion compliance + a11y hardening

## 10) Acceptance Criteria
- Blueprint explicitly maps starter patterns to our page map and route inventory.
- No conflict introduced with Section 66 package policy.
- No conflict introduced with Section 67 premium dashboard standards.
- No conflict introduced with AGENTS quality gates and publish controls.
- Document is actionable for implementation tasks without re-architecting core product scope.
