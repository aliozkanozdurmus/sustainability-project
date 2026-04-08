import { afterEach, describe, expect, it, vi } from "vitest";

import { bootstrapWorkspace, fetchWorkspaceContext, syncIntegrations } from "./catalog";
import { fetchDashboardNotifications, fetchDashboardOverview } from "./dashboard";
import {
  fetchIntegrationDetail,
  runConnectorOperation,
  saveIntegrationProfile,
} from "./integrations";
import { queryRetrieval } from "./retrieval";
import { createRun, executeRun, fetchRunPackageStatus, publishRun } from "./runs";

const workspace = {
  tenantId: "tenant-1",
  projectId: "project-1",
};

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json",
    },
  });
}

function requestUrl(input: string | URL | Request) {
  if (typeof input === "string") {
    return new URL(input);
  }

  if (input instanceof URL) {
    return input;
  }

  return new URL(input.url);
}

function requestHeaders(input: string | URL | Request, init?: RequestInit) {
  if (input instanceof Request) {
    return new Headers(input.headers);
  }

  return new Headers(init?.headers);
}

async function requestJson(input: string | URL | Request, init?: RequestInit) {
  if (input instanceof Request) {
    const text = await input.clone().text();
    return text ? JSON.parse(text) : null;
  }

  if (!init?.body || typeof init.body !== "string") {
    return null;
  }

  return JSON.parse(init.body);
}

describe("web sdk functions", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("fetches dashboard overview through the workspace-aware sdk", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
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
          summary: "Ready for governed generation.",
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
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const payload = await fetchDashboardOverview(workspace);

    const [input, init] = fetchMock.mock.calls[0]!;
    const url = requestUrl(input);

    expect(url.pathname).toBe("/dashboard/overview");
    expect(url.searchParams.get("tenant_id")).toBe("tenant-1");
    expect(url.searchParams.get("project_id")).toBe("project-1");
    expect(requestHeaders(input, init).get("x-tenant-id")).toBe("tenant-1");
    expect(payload.hero.project_code).toBe("AR2025");
  });

  it("fetches dashboard notifications through the workspace-aware sdk", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        items: [
          {
            notification_id: "publish:1",
            title: "Controlled publish queued",
            detail: "queued • compose",
            category: "publish",
            status: "attention",
            occurred_at_utc: "2026-04-08T10:05:00Z",
            source_ref: {
              run_id: "run-1",
              audit_event_id: "audit-1",
            },
          },
        ],
        generated_at_utc: "2026-04-08T10:05:00Z",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const payload = await fetchDashboardNotifications(workspace);

    const [input, init] = fetchMock.mock.calls[0]!;
    const url = requestUrl(input);

    expect(url.pathname).toBe("/dashboard/notifications");
    expect(url.searchParams.get("tenant_id")).toBe("tenant-1");
    expect(url.searchParams.get("project_id")).toBe("project-1");
    expect(url.searchParams.get("limit")).toBe("25");
    expect(requestHeaders(input, init).get("x-tenant-id")).toBe("tenant-1");
    expect(payload.items[0]?.title).toBe("Controlled publish queued");
  });

  it("fetches package status and executes/publishes runs with typed payloads", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          run_id: "run-1",
          package_job_id: "job-1",
          package_status: "running",
          current_stage: "package_pdf",
          report_quality_score: 92.5,
          visual_generation_status: "queued",
          artifacts: [],
          stage_history: [],
          generated_at_utc: "2026-04-08T10:00:00Z",
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ accepted: true }))
      .mockResolvedValueOnce(
        jsonResponse({
          published: false,
          report_run_status: "running",
          package_job_id: "job-1",
          package_status: "queued",
          estimated_stage: "package_pdf",
          artifacts: [],
          report_pdf: null,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const packageStatus = await fetchRunPackageStatus(workspace, "run-1");
    await executeRun(workspace, "run-1", {
      tenant_id: "tenant-1",
      project_id: "project-1",
      max_steps: 32,
    });
    const publishPayload = await publishRun(workspace, "run-1", {
      tenant_id: "tenant-1",
      project_id: "project-1",
    });

    const packageRequest = requestUrl(fetchMock.mock.calls[0]![0]);
    const executeInput = fetchMock.mock.calls[1]![0];
    const executeInit = fetchMock.mock.calls[1]![1];
    const publishInput = fetchMock.mock.calls[2]![0];
    const publishInit = fetchMock.mock.calls[2]![1];

    expect(packageRequest.pathname).toBe("/runs/run-1/package-status");
    expect(packageRequest.searchParams.get("tenant_id")).toBe("tenant-1");
    expect(packageStatus.package_status).toBe("running");
    await expect(requestJson(executeInput, executeInit)).resolves.toEqual({
      tenant_id: "tenant-1",
      project_id: "project-1",
      max_steps: 32,
    });
    expect(requestHeaders(publishInput, publishInit).get("x-user-role")).toBe("board_member");
    expect(publishPayload.package_status).toBe("queued");
  });

  it("submits retrieval queries with parsed numeric filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        retrieval_run_id: "retrieval-1",
        evidence: [],
        diagnostics: {
          backend: "hybrid",
          retrieval_mode: "hybrid",
          top_k: 8,
          result_count: 0,
          filter_hit_count: 0,
          coverage: 0,
          best_score: 0,
          quality_gate_passed: false,
          latency_ms: 52,
          index_name: "tenant-1-project-1",
          applied_filters: {},
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await queryRetrieval(workspace, {
      queryText: "scope 2",
      topK: "8",
      retrievalMode: "hybrid",
      minScore: "0.5",
      minCoverage: "42",
      period: "2025",
      keywords: "scope 2,electricity",
      sectionTags: "TSRS2,CSRD",
    });

    const [input, init] = fetchMock.mock.calls[0]!;
    const url = requestUrl(input);

    expect(url.pathname).toBe("/retrieval/query");
    await expect(requestJson(input, init)).resolves.toEqual({
      tenant_id: "tenant-1",
      project_id: "project-1",
      query_text: "scope 2",
      top_k: 8,
      retrieval_mode: "hybrid",
      min_score: 0.5,
      min_coverage: 42,
      retrieval_hints: {
        period: "2025",
        keywords: ["scope 2", "electricity"],
        section_tags: ["TSRS2", "CSRD"],
        small_to_big: true,
        context_window: 1,
      },
    });
  });

  it("bootstraps workspace context, syncs connectors, and creates runs through the sdk", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
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
            description: "Industrial demo tenant.",
            ceo_name: "Demo CEO",
            ceo_message: "Traceable sustainability reporting.",
            sustainability_approach: "Governance first.",
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
          tenant_created: true,
          project_created: true,
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ queued: true }))
      .mockResolvedValueOnce(
        jsonResponse({
          run_id: "run-1",
          report_run_id: "run-1",
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const bootstrapPayload = await bootstrapWorkspace({
      tenantHeader: "dev-tenant",
      tenant_name: "Tenant One",
      tenant_slug: "tenant-one",
      project_name: "Annual Report",
      project_code: "AR2025",
      reporting_currency: "TRY",
      company_profile: {
        legal_name: "Sustainability Holding",
        sector: "",
        headquarters: "",
        description: "",
        ceo_name: "",
        ceo_message: "",
        sustainability_approach: "",
      },
      brand_kit: {
        brand_name: "Tenant Brand",
        logo_uri: "",
        primary_color: "#f07f13",
        secondary_color: "#262421",
        accent_color: "#d2b24a",
        font_family_headings: "Inter",
        font_family_body: "Inter",
        tone_name: "editorial-corporate",
      },
    });
    await syncIntegrations({
      tenant_id: "tenant-1",
      project_id: "project-1",
      connector_ids: ["integration-1"],
    });
    const runPayload = await createRun({
      tenant_id: "tenant-1",
      project_id: "project-1",
      framework_target: ["TSRS1", "TSRS2"],
      active_reg_pack_version: "core-pack-v1",
      report_blueprint_version: "bp-v1",
      company_profile_ref: "company-1",
      brand_kit_ref: "brand-1",
      connector_scope: ["sap_odata"],
      scope_decision: {
        reporting_year: "2025",
        include_scope3: true,
        operation_countries: "Turkiye",
        sustainability_owner: "Owner",
        board_approver: "Board",
        approval_sla_days: 5,
        retrieval_tasks: [
          {
            task_id: "task-1",
            framework: "TSRS1",
            section_target: "TSRS1 Governance",
            query_text: "TSRS1 governance",
            retrieval_mode: "hybrid",
            top_k: 3,
          },
        ],
      },
    });

    const syncUrl = requestUrl(fetchMock.mock.calls[1]![0]);
    const createRunUrl = requestUrl(fetchMock.mock.calls[2]![0]);

    expect(
      requestHeaders(fetchMock.mock.calls[0]![0], fetchMock.mock.calls[0]![1]).get("x-tenant-id"),
    ).toBe("dev-tenant");
    expect(syncUrl.pathname).toBe("/integrations/sync");
    expect(createRunUrl.pathname).toBe("/runs");
    expect(bootstrapPayload.project.code).toBe("AR2025");
    expect(runPayload.run_id).toBe("run-1");
  });

  it("loads integration detail, saves the profile, and executes connector operations", async () => {
    const detailPayload = {
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
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(detailPayload))
      .mockResolvedValueOnce(jsonResponse(detailPayload))
      .mockResolvedValueOnce(
        jsonResponse({
          operation_id: "operation-1",
          operation_type: "preview_sync",
          status: "completed",
          current_stage: "preview",
          support_tier: "certified",
          health_band: "green",
          operator_message: "Preview completed.",
          support_hint: null,
          recommended_action: null,
          retryable: false,
          error_code: null,
          error_message: null,
          result: {
            preview_rows: [],
          },
          diagnostics: {},
          artifact: null,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const detail = await fetchIntegrationDetail(workspace, "integration-1");
    await saveIntegrationProfile({
      tenant_id: "tenant-1",
      project_id: "project-1",
      connector_type: "sap_odata",
      display_name: "SAP OData",
      auth_mode: "oauth2",
      base_url: "https://sap.example.test",
      resource_path: "/odata/materials",
      mapping_version: "map-v1",
      certified_variant: "s4hana",
      product_version: "2025.1",
      connectivity_mode: "pull",
      credential_ref: "cred://sap",
      assigned_agent_id: null,
      connection_profile: {
        service_url: "https://sap.example.test",
      },
    });
    const operation = await runConnectorOperation(workspace, "integration-1", "preview-sync", {
      tenant_id: "tenant-1",
      project_id: "project-1",
      limit: 20,
    });

    const detailUrl = requestUrl(fetchMock.mock.calls[0]![0]);
    const saveUrl = requestUrl(fetchMock.mock.calls[1]![0]);
    const operationUrl = requestUrl(fetchMock.mock.calls[2]![0]);

    expect(detailUrl.pathname).toBe("/integrations/connectors/integration-1");
    expect(saveUrl.pathname).toBe("/integrations/connectors");
    expect(operationUrl.pathname).toBe("/integrations/connectors/integration-1/preview-sync");
    await expect(
      requestJson(fetchMock.mock.calls[2]![0], fetchMock.mock.calls[2]![1]),
    ).resolves.toEqual({
      tenant_id: "tenant-1",
      project_id: "project-1",
      limit: 20,
    });
    expect(detail.display_name).toBe("SAP OData");
    expect(operation.status).toBe("completed");
  });

  it("loads workspace context through the catalog sdk", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
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
          description: "Industrial demo tenant.",
          ceo_name: "Demo CEO",
          ceo_message: "Traceable sustainability reporting.",
          sustainability_approach: "Governance first.",
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
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const payload = await fetchWorkspaceContext(workspace);
    const url = requestUrl(fetchMock.mock.calls[0]![0]);

    expect(url.pathname).toBe("/catalog/workspace-context");
    expect(url.searchParams.get("tenant_id")).toBe("tenant-1");
    expect(payload.factory_readiness.is_ready).toBe(true);
  });
});
