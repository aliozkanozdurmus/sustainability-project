# AGENTS.md
## Multi-Agent Workflow, Contracts, and Quality Gates

Status: Draft v0.4  
Date: 2026-03-05

## 1) Purpose
This document defines the operational model for virtual agents in the ESG reporting platform.  
The target is deterministic, evidence-grounded, auditor-traceable report generation for TSRS/CSRD-aligned packs with strict zero-hallucination controls.

This version is aligned with:
- `README.md` for product scope, architecture baseline, and delivery phases
- `docs/architecture/public-baseline.md` for one-click pipeline, readiness, governance, and packaging policy
- `docs/security/secrets-policy.md` for secret handling and model-provider restrictions

## 2) Non-Negotiable Operating Rules
- Agents never bypass schema validation.
- Agents communicate via typed state and typed payloads, not free-form handoffs.
- Every claim must include at least one citation.
- Every numeric claim must reference calculator artifacts.
- Verifier gate controls publish readiness.
- AI endpoint policy is strict:
  - Azure AI Foundry + Azure OpenAI only.
- Model allowlist is strict:
  - `gpt-5.2` (generation + verifier reasoning)
  - `text-embedding-3-large` (chunk/query embeddings)
- Any model call outside the allowlist is a hard policy violation.
- Scope decisions are compliance-governed:
  - rule versions and legal references are mandatory.
- Critical evidence gaps block generation or publish per policy.
- Dashboard insights can only use verified data.

## 2.1 Model Assignment Matrix
| Agent / Stage | Model Policy |
|---|---|
| Saga Coordinator (routing/reasoning) | `gpt-5.2` |
| Retrieval embedding pipeline | `text-embedding-3-large` |
| Writer Agent | `gpt-5.2` |
| Verifier Agent | `gpt-5.2` |
| Calculator Agent | deterministic code execution only; `gpt-5.2` allowed only for non-numeric helper reasoning |

## 3) Agent Registry
## 3.1 Saga Coordinator (Router Agent)
Responsibilities:
- Parse user request and generation mode.
- Build execution plan and node dependencies.
- Route tasks to specialized agents.
- Control retries, compensations, and escalation paths.

Inputs:
- `user_request`
- `tenant_id`
- `project_id`
- `reporting_period`
- `generation_mode` (`one_click` or `guided`)

Outputs:
- `TaskEnvelope[]`
- `ExecutionPlan`

Hard constraints:
- Must route numeric work to Calculator Agent.
- Must reject publish transition unless all hard gates pass.

## 3.2 Applicability and Regulation Pack Agent
Responsibilities:
- Resolve legal scope by entity and jurisdiction.
- Select required framework pack and version.
- Apply transition relief logic.

Inputs:
- `LegalProfile`
- `JurisdictionFacts`
- `RuleEngineSnapshot`

Outputs:
- `ScopeDecision`
- `ActiveRegulationPack`

Hard constraints:
- Scope output must include legal instrument references.
- Rule snapshots must be versioned and timestamped.

## 3.3 Intake and Readiness Agent
Responsibilities:
- Validate mandatory intake fields and required evidence lists.
- Compute readiness scores.
- Produce gap remediation pack if blocking criteria fail.

Inputs:
- `MasterDataIntake`
- `EvidenceChecklist`
- `KpiCatalogStatus`

Outputs:
- `ReadinessScorecard`
- `MissingDataRequestPack` (when needed)

Hard constraints:
- `completeness_score < 85` blocks final generation and triggers remediation mode.
- Missing critical mandatory data blocks one-click run start.

## 3.4 Retrieval and Evidence Agent
Responsibilities:
- Execute hybrid retrieval (semantic + lexical).
- Enforce tenant/project isolation and framework filters.
- Return evidence with full provenance and quality metadata.

Inputs:
- `TaskEnvelope`
- `RetrievalHints`
- `ActiveRegulationPack`

Outputs:
- `EvidenceBlock[]`
- `RetrievalDiagnostics`

Hard constraints:
- No evidence without `source_document_id` and location metadata.
- Must include `quality_grade` and `quality_score` in outputs.

## 3.5 KPI Quality Agent
Responsibilities:
- Validate KPI freshness, ownership, quality grade, and schema completeness.
- Enforce critical KPI evidence grade policy for downstream agents.

Inputs:
- `KpiDataset[]`
- `EvidenceBlock[]`
- `QualityPolicy`

Outputs:
- `KpiQualityAssessment[]`
- `KpiBlocker[]`

Hard constraints:
- Critical claims cannot use KPI data below `A-` without approved exception.
- Stale or low-grade KPI inputs must raise deterministic warnings or blocks.

## 3.6 Calculator Agent (Coder/Interpreter)
Responsibilities:
- Run deterministic ESG calculations.
- Normalize units and periods.
- Produce auditable execution artifacts.

Inputs:
- `CalculationTask`
- `StructuredNumericInputs`

Outputs:
- `CalculationResult`
- `ExecutionArtifact`

Hard constraints:
- No prose-based numeric estimation.
- Must persist `code_hash`, `inputs_snapshot_ref`, `runtime_log_ref`.
- Must fail on ambiguous units unless resolved by policy-approved mapping.

## 3.7 Writer Agent (Generator)
Responsibilities:
- Build section drafts from evidence + calculations + templates.
- Produce claim-bound narrative with strict references.

Inputs:
- `EvidenceBlock[]`
- `CalculationResult[]`
- `SectionTemplate`
- `ActiveRegulationPack`

Outputs:
- `DraftSection[]`
- `Claim[]`

Hard constraints:
- Claims without citations are invalid output.
- Numeric statements without calculator refs are invalid output.
- Style is flexible, facts and references are not.

## 3.8 Verifier Agent (Critic/Validator)
Responsibilities:
- Evaluate claim support using evidence and calculation artifacts.
- Return strict verification status and revision instructions.

Inputs:
- `DraftSection[]`
- `Claim[]`
- `EvidenceBlock[]`
- `CalculationResult[]`

Outputs:
- `VerificationResult[]`
- `RevisionInstructions`

Hard constraints:
- Status set is fixed: `PASS | FAIL | UNSURE`.
- `FAIL` must include explicit mismatch reason and source refs.
- Critical `FAIL` always blocks publish.

## 3.9 Approval and SLA Agent
Responsibilities:
- Orchestrate role-based approval routing.
- Track SLA timers, reminders, and escalations.
- Enforce signing chain requirements.

Inputs:
- `ApprovalWorkflowPolicy`
- `ApprovalTask[]`
- `VerificationSummary`

Outputs:
- `ApprovalStatusBoard`
- `SlaEvent[]`

Hard constraints:
- Final publish requires configured signing chain completion.
- Overdue board-critical approvals must raise blocking alerts.

## 3.10 Dashboard Insight Agent
Responsibilities:
- Generate KPI tile narratives and board insights.
- Prepare dashboard-ready summaries and board-pack snippets.

Inputs:
- `VerifiedKpiSnapshot`
- `VerificationSummary`
- `ThresholdPolicy`

Outputs:
- `DashboardInsight[]`
- `BoardSnapshotBlock[]`

Hard constraints:
- Must consume only `PASS` claims and approved metric snapshots.
- Every narrative tile must carry traceability refs.

## 3.11 Publish and Packaging Agent
Responsibilities:
- Assemble final report package and evidence index.
- Generate coverage matrix and audit bundle.
- Trigger signing workflow (if policy enabled).

Inputs:
- `ApprovedDraft`
- `VerificationSummary`
- `CoverageAudit`
- `ApprovalStatusBoard`

Outputs:
- `PublishBundleManifest`
- `FinalPackageRefs`

Hard constraints:
- Must fail if mandatory package artifacts are missing.
- Must preserve citation links and index navigability after packaging.

## 4) Supporting Agents (Phase 3+)
- Compliance Rules Agent:
  - validates completeness by framework/version and disclosure mapping
- Cost Controller Agent:
  - controls token/rerank depth by budget policy
- Citation Formatter Agent:
  - standardizes citation style for PDF/dashboard consistency
- Red-Team Safety Agent:
  - tests prompt-injection and policy bypass paths in non-production eval runs

## 5) Canonical Contracts
## 5.1 TaskEnvelope
```json
{
  "task_id": "tsk_123",
  "tenant_id": "ten_001",
  "project_id": "prj_100",
  "framework_target": "TSRS2",
  "section_target": "Climate Risk Management",
  "priority": "high",
  "deadline_utc": "2026-03-05T18:00:00Z"
}
```

## 5.2 ScopeDecision
```json
{
  "decision_id": "scp_001",
  "jurisdiction_code": "TR",
  "in_scope": true,
  "required_frameworks": ["TSRS1", "TSRS2"],
  "legal_instrument_refs": ["KGK_TSRS_DECISION_XYZ"],
  "transition_reliefs_applied": ["scope3_first_two_years_relief"],
  "rule_version": "scope-rules-2026.03.01",
  "snapshot_date": "2026-03-05"
}
```

## 5.3 ReadinessScorecard
```json
{
  "run_id": "run_100",
  "completeness_score": 88,
  "evidence_quality_score": 91,
  "traceability_score": 94,
  "numeric_reliability_score": 92,
  "blocking_issues": [],
  "advisory_issues": ["supplier_scope3_data_quality_b_plus"]
}
```

## 5.4 EvidenceBlock
```json
{
  "evidence_id": "ev_987",
  "source_document_id": "doc_45",
  "chunk_id": "chk_120",
  "page": 19,
  "text": "...",
  "score_dense": 0.82,
  "score_sparse": 0.74,
  "score_final": 0.79,
  "quality_grade": "A-",
  "quality_score": 89,
  "metadata": {
    "section": "Scope 2 emissions",
    "period": "2025",
    "framework_tags": ["TSRS2", "CSRD"]
  }
}
```

## 5.5 CalculationResult
```json
{
  "calc_id": "calc_001",
  "formula_name": "ghg_scope2_market_based",
  "inputs_ref": "obj://calc-inputs/calc_001.json",
  "code_hash": "sha256:...",
  "output": 12450.23,
  "unit": "tCO2e",
  "trace_log_ref": "obj://calc-logs/calc_001.log"
}
```

## 5.6 Claim
```json
{
  "claim_id": "clm_200",
  "statement": "Scope 2 emissions decreased by 15.1% year-over-year.",
  "citations": [
    {
      "source_document_id": "doc_45",
      "chunk_id": "chk_120",
      "span_start": 101,
      "span_end": 241
    }
  ],
  "calculation_refs": ["calc_001"],
  "confidence": 0.93
}
```

## 5.7 VerificationResult
```json
{
  "verification_id": "ver_77",
  "claim_id": "clm_200",
  "status": "PASS",
  "reason": "Claim is supported by cited evidence and calculator artifact.",
  "evidence_refs": ["ev_987"],
  "severity": "normal"
}
```

## 5.8 ApprovalTask
```json
{
  "approval_task_id": "apr_301",
  "stage": "board_final_approval",
  "assignee_role": "board_member",
  "due_at_utc": "2026-03-10T12:00:00Z",
  "status": "pending",
  "sla_policy_ref": "sla_policy_v2"
}
```

## 5.9 DashboardInsight
```json
{
  "insight_id": "ins_51",
  "kpi_code": "E_SCOPE2_YOY",
  "summary": "Scope 2 trend is improving and remains within target corridor.",
  "status_band": "green",
  "trace_refs": {
    "claim_ids": ["clm_200"],
    "evidence_ids": ["ev_987"]
  }
}
```

## 5.10 PublishBundleManifest
```json
{
  "bundle_id": "pkg_2026_001",
  "run_id": "run_100",
  "artifacts": [
    "final_report_pdf",
    "claim_citation_index",
    "verification_log",
    "calculation_artifacts",
    "regulatory_coverage_matrix",
    "assumption_register",
    "dashboard_snapshot_pack"
  ],
  "approved": true,
  "generated_at_utc": "2026-03-05T16:22:00Z"
}
```

## 6) LangGraph Node Flow (One-Click Mode)
1. `INIT_REQUEST`
2. `RESOLVE_APPLICABILITY` (Applicability Agent)
3. `VALIDATE_READINESS` (Intake and Readiness Agent)
4. `PLAN_TASKS` (Saga Coordinator)
5. `RETRIEVE_EVIDENCE` (Retrieval and Evidence Agent)
6. `VALIDATE_KPI_QUALITY` (KPI Quality Agent)
7. `COMPUTE_METRICS` (Calculator Agent, conditional)
8. `DRAFT_SECTION` (Writer Agent)
9. `VERIFY_CLAIMS` (Verifier Agent)
10. `REVIEW_LOOP` (Writer <-> Verifier until exit rule)
11. `RUN_COVERAGE_AUDIT` (Compliance Rules Agent or policy check node)
12. `BUILD_DASHBOARD_SNAPSHOTS` (Dashboard Insight Agent)
13. `RUN_APPROVAL_ROUTING` (Approval and SLA Agent)
14. `HUMAN_APPROVAL`
15. `PUBLISH_REPORT_PACKAGE` (Publish and Packaging Agent)
16. `CLOSE_RUN`

## 7) State Model (Minimum Required Fields)
- `run_id`
- `tenant_id`
- `project_id`
- `framework_target[]`
- `active_reg_pack_version`
- `scope_decision`
- `active_node`
- `completed_nodes[]`
- `failed_nodes[]`
- `retry_count_by_node`
- `task_queue[]`
- `readiness_scorecard`
- `evidence_pool[]`
- `kpi_quality_pool[]`
- `calculation_pool[]`
- `draft_pool[]`
- `verification_pool[]`
- `coverage_audit`
- `approval_status_board`
- `dashboard_snapshot_pool[]`
- `publish_ready` (bool)
- `human_approval` (`pending|approved|rejected`)

## 8) Retry, Recovery, and Compensation
Retry policy:
- Exponential backoff per node.
- Max retry budget per node with circuit-breaker behavior.

Compensation rules:
- Invalidate failed node outputs and dependent downstream outputs only.
- Resume from latest healthy checkpoint.
- Preserve immutable audit trail for failed attempts and reruns.

Escalation rules:
- Writer/Verifier loop exceeds 3 rounds -> escalate to human reviewer.
- Missing calculator input -> route to Retrieval/Readiness remediation.
- Repeated approval SLA breach on board-critical stage -> escalate to governance owner.

## 9) Verification and Publish Gates
Hard blockers:
- Any critical `FAIL` claim.
- Missing citation on any claim.
- Missing calculator artifact for numeric claims.
- Active tenant policy violation.
- `numeric_reliability_score < 90` for climate-critical GHG sections.
- Missing critical evidence items defined by policy.
- Incomplete final signing chain.

Soft blockers (human decision required):
- `UNSURE` claims in non-critical sections.
- Low-confidence claim clusters.
- Critical KPI inputs below `A-` with approved exception pending review.

## 10) Security and Isolation Boundaries
- Tenant isolation is enforced in every retrieval and storage access.
- Calculator tool execution runs in sandboxed runtime.
- Source text is data, never policy.
- Instruction hierarchy is immutable and centrally controlled.
- Outbound tools/domains are allowlisted.
- Model inference allowlist:
  - Azure AI Foundry endpoints
  - Azure OpenAI endpoints
  - Model names: `gpt-5.2`, `text-embedding-3-large`

## 11) Observability and Cost Controls
Per-agent metrics:
- latency p50/p95
- token usage
- failure rate
- retry count
- correction loop depth

System metrics:
- citation coverage
- verifier pass ratio
- cost per report run
- queue lag
- readiness pass ratio
- approval SLA breach rate

FinOps controls:
- token and retrieval-depth budgets per tenant and run class
- model/rerank depth throttling through policy

## 12) Human-in-the-Loop Control Points
- Scope decision review for edge legal entities.
- Readiness fail triage and data-gap remediation approval.
- Draft readiness review.
- Verifier `FAIL` triage.
- Pre-publish final approval.
- Post-publish audit sampling.

## 13) UI and Dashboard Trust Integration Rules
- Dashboard narrative tiles consume only `PASS`-verified claims.
- Each board KPI card shows:
  - freshness timestamp
  - quality grade
  - status band
  - traceability link path
- Board snapshot generation must use approved period and framework filters.
- Insight generation must fail closed if trace refs are missing.

## 14) Agent Prompting Standards
- Use task-specific prompts, not a single monolithic prompt.
- Prefer structured JSON outputs.
- Embed explicit negative constraints:
  - do not invent numbers
  - do not cite uncited evidence
  - do not infer beyond retrieved context
  - do not continue when required fields are missing
- Include contract schema and validation checklist in every agent prompt.

## 15) Phase-Wise Rollout Plan for Agents
Phase 1:
- Saga Coordinator + Applicability + Intake/Readiness + Retrieval + Writer
- No publish path

Phase 2:
- Add Calculator + Verifier + basic approval routing

Phase 3:
- Add KPI Quality + Dashboard Insight + coverage audit + packaging

Phase 4:
- Add policy hardening, cost controller, red-team safety scenarios, and benchmark-driven tuning

## 16) Definition of Done for an Agent Run
- All mandatory disclosures in active pack are covered or explicitly justified.
- Every claim is citation-bound.
- Every numeric claim has deterministic calculation artifact.
- Verification results satisfy publish gate policy.
- Approval chain is complete and auditable.
- Final package artifacts are generated with traceable manifest.
