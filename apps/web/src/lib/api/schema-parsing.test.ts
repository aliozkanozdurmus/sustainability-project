import { describe, expect, it } from "vitest";

import { workspaceContextResponseSchema } from "./catalog";
import { dashboardOverviewResponseSchema } from "./dashboard";
import { integrationDetailResponseSchema } from "./integrations";
import { retrievalResponseSchema } from "./retrieval";
import { runPackageStatusSchema } from "./runs";

describe("web api schemas", () => {
  it("parses representative dashboard responses", () => {
    expect(
      dashboardOverviewResponseSchema.parse({
        hero: {
          tenant_name: "Tenant One",
          company_name: "Sustainability Holding",
          project_name: "Annual Report",
          project_code: "AR2025",
          sector: "Manufacturing",
          headquarters: "Istanbul",
          reporting_currency: "TRY",
          blueprint_version: "bp-v1",
          readiness_label: "ready",
          readiness_score: 97,
          summary: "Ready for governed report generation.",
          logo_uri: null,
          primary_color: "#f07f13",
          accent_color: "#d2b24a",
        },
        metrics: [],
        pipeline: [],
        connector_health: [],
        risks: [],
        schedule: [],
        artifact_health: [],
        activity_feed: [],
        run_queue: [],
        generated_at_utc: "2026-04-08T10:00:00Z",
      }).hero.project_code,
    ).toBe("AR2025");
  });

  it("parses representative workspace context responses", () => {
    expect(
      workspaceContextResponseSchema.parse({
        tenant: {
          id: "tenant-1",
          name: "Tenant One",
          slug: "tenant-one",
          status: "active",
        },
        project: {
          id: "project-1",
          tenant_id: "tenant-1",
          name: "Annual Report",
          code: "AR2025",
          reporting_currency: "TRY",
          status: "active",
        },
        company_profile: {
          id: "company-1",
          legal_name: "Sustainability Holding",
          sector: "Manufacturing",
          headquarters: "Istanbul",
          description: "Industrial sustainability demo tenant.",
          ceo_name: "Demo CEO",
          ceo_message: "We operate with traceable sustainability data.",
          sustainability_approach: "Governance and traceability first.",
          is_configured: true,
        },
        brand_kit: {
          id: "brand-1",
          brand_name: "Tenant Brand",
          logo_uri: null,
          primary_color: "#f07f13",
          secondary_color: "#262421",
          accent_color: "#d2b24a",
          font_family_headings: "Inter",
          font_family_body: "Inter",
          tone_name: "editorial-corporate",
          is_configured: true,
        },
        integrations: [],
        blueprint_version: "bp-v1",
        factory_readiness: {
          is_ready: true,
          company_profile_ready: true,
          brand_kit_ready: true,
          blockers: [],
        },
      }).factory_readiness.is_ready,
    ).toBe(true);
  });

  it("parses representative run package responses", () => {
    expect(
      runPackageStatusSchema.parse({
        run_id: "run-1",
        package_job_id: "job-1",
        package_status: "running",
        current_stage: "package_pdf",
        report_quality_score: 92.4,
        visual_generation_status: "queued",
        artifacts: [
          {
            artifact_id: "artifact-1",
            artifact_type: "final_report_pdf",
            filename: "report.pdf",
            content_type: "application/pdf",
            size_bytes: 1024,
            checksum: "sha256:abc",
            created_at_utc: "2026-04-08T10:00:00Z",
            download_path: "/runs/run-1/report-pdf",
          },
        ],
        stage_history: [
          {
            stage: "package_pdf",
            status: "running",
            at_utc: "2026-04-08T10:00:00Z",
            detail: null,
          },
        ],
        generated_at_utc: "2026-04-08T10:00:00Z",
      }).artifacts[0]?.filename,
    ).toBe("report.pdf");
  });

  it("parses representative retrieval responses", () => {
    expect(
      retrievalResponseSchema.parse({
        retrieval_run_id: "retrieval-1",
        evidence: [
          {
            evidence_id: "evidence-1",
            source_document_id: "doc-1",
            chunk_id: "chunk-1",
            page: 4,
            text: "Scope 2 emissions decreased 15.1% year over year.",
            score_dense: 0.82,
            score_sparse: 0.76,
            score_final: 0.8,
            metadata: {
              period: "2025",
            },
          },
        ],
        diagnostics: {
          backend: "hybrid",
          retrieval_mode: "hybrid",
          top_k: 10,
          result_count: 1,
          filter_hit_count: 1,
          coverage: 88,
          best_score: 0.8,
          quality_gate_passed: true,
          latency_ms: 121,
          index_name: "tenant-1-project-1",
          applied_filters: {
            period: "2025",
          },
        },
      }).diagnostics.best_score,
    ).toBe(0.8);
  });

  it("parses representative integration detail responses", () => {
    expect(
      integrationDetailResponseSchema.parse({
        id: "integration-1",
        connector_type: "sap_odata",
        display_name: "SAP OData",
        auth_mode: "oauth2",
        base_url: "https://sap.example.test",
        resource_path: "/odata/materials",
        status: "active",
        mapping_version: "map-v1",
        certified_variant: "s4hana",
        product_version: "2025.1",
        support_tier: "certified",
        connectivity_mode: "pull",
        credential_ref: "cred://sap",
        health_band: "green",
        health_status: {
          score: 98,
          band: "green",
          metrics: [],
          operator_message: "Ready",
          support_hint: "None",
          recommended_action: "Continue",
          retryable: false,
          support_matrix_version: "support-v1",
        },
        assigned_agent_id: null,
        normalization_policy: {},
        connection_profile: {
          service_url: "https://sap.example.test",
        },
      }).support_tier,
    ).toBe("certified");
  });
});
