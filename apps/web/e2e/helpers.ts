import { expect, type APIRequestContext, type Page } from "@playwright/test";

import { WORKSPACE_STORAGE_KEY } from "../src/lib/api/client";

export type WorkspaceContext = {
  tenantId: string;
  projectId: string;
};

type CreateRunOptions = {
  legalName?: string;
  taxId?: string;
  sustainabilityOwner?: string;
  boardApprover?: string;
};

type WorkspaceContextResponse = {
  company_profile: {
    id: string;
  };
  brand_kit: {
    id: string;
  };
  integrations: Array<{
    id: string;
    connector_type: string;
  }>;
  blueprint_version: string;
};

type RunListItem = {
  run_id: string;
  report_run_status: string;
  report_pdf: { artifact_id: string } | null;
};

type RunListResponse = {
  items: RunListItem[];
};

function resolveApiBaseUrl(): string {
  return process.env.PLAYWRIGHT_API_BASE_URL ?? "http://127.0.0.1:8000";
}

export function getSeededWorkspace(): WorkspaceContext {
  const tenantId = process.env.PLAYWRIGHT_DEMO_TENANT_ID;
  const projectId = process.env.PLAYWRIGHT_DEMO_PROJECT_ID;
  if (!tenantId || !projectId) {
    throw new Error(
      "Missing PLAYWRIGHT_DEMO_TENANT_ID / PLAYWRIGHT_DEMO_PROJECT_ID. Run the Playwright setup script first.",
    );
  }
  return { tenantId, projectId };
}

export function buildApiHeaders(
  tenantId: string,
  options: { role?: string; includeJsonContentType?: boolean } = {},
): Record<string, string> {
  const headers: Record<string, string> = {
    "x-tenant-id": tenantId,
    "x-user-id": "playwright-user",
    "x-user-role": options.role ?? "analyst",
  };
  if (options.includeJsonContentType ?? true) {
    headers["content-type"] = "application/json";
  }
  return headers;
}

function buildDeterministicRetrievalTasks(reportingYear: string) {
  return [
    {
      task_id: "task_tsrs1_demo",
      framework: "TSRS1",
      section_target: "TSRS1 Governance and Risk Management",
      query_text: `TSRS1 governance and risk management sustainability committee oversight ${reportingYear}`,
      retrieval_mode: "hybrid",
      top_k: 3,
    },
    {
      task_id: "task_tsrs2_demo",
      framework: "TSRS2",
      section_target: "TSRS2 Climate and Energy",
      query_text: `TSRS2 climate and energy scope 2 electricity emissions renewable electricity ${reportingYear}`,
      retrieval_mode: "hybrid",
      top_k: 3,
    },
    {
      task_id: "task_csrd_demo",
      framework: "CSRD",
      section_target: "CSRD Workforce and Supply Chain",
      query_text: `CSRD workforce supply chain lost time injury supplier screening ${reportingYear}`,
      retrieval_mode: "hybrid",
      top_k: 3,
    },
  ];
}

async function waitForPublishedRunViaApi(
  request: APIRequestContext,
  workspace: WorkspaceContext,
  runId: string,
): Promise<void> {
  const apiBaseUrl = resolveApiBaseUrl();
  for (let attempt = 0; attempt < 90; attempt += 1) {
    const response = await request.get(`${apiBaseUrl}/runs`, {
      headers: buildApiHeaders(workspace.tenantId),
      params: {
        tenant_id: workspace.tenantId,
        project_id: workspace.projectId,
        page: 1,
        size: 50,
      },
    });
    expect(response.ok()).toBeTruthy();
    const payload = (await response.json()) as RunListResponse;
    const row = payload.items.find((item) => item.run_id === runId);
    if (row?.report_run_status === "published" && row.report_pdf) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`Timed out waiting for run ${runId} to reach published state.`);
}

export async function primeWorkspaceContext(
  page: Page,
  workspace: WorkspaceContext = getSeededWorkspace(),
): Promise<void> {
  await page.addInitScript(
    ({ key, value }) => {
      window.localStorage.setItem(key, JSON.stringify(value));
    },
    { key: WORKSPACE_STORAGE_KEY, value: workspace },
  );
}

export function runRow(page: Page, runId: string) {
  return page.getByTestId(`run-row-${runId}`);
}

export async function waitForRunRow(page: Page, runId: string): Promise<void> {
  await expect(runRow(page, runId)).toBeVisible({ timeout: 30_000 });
}

export async function createRunViaWizard(
  page: Page,
  options: CreateRunOptions = {},
): Promise<string> {
  const workspace = getSeededWorkspace();
  await primeWorkspaceContext(page, workspace);
  await page.goto("/reports/new");

  await expect(page.getByTestId("workspace-context-status")).toContainText(workspace.tenantId);
  await expect(page.getByTestId("factory-context-panel")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("factory-readiness-panel")).toContainText("Readiness: hazır");
  await page.getByLabel("Legal Entity Name").fill(
    options.legalName ?? "Playwright Demo Sustainability Holding",
  );
  await page.getByLabel("Tax / Registry ID").fill(options.taxId ?? "TR-9876543210");
  await page.getByTestId("wizard-next-button").click();
  await page.getByTestId("wizard-next-button").click();
  await page
    .getByLabel("Sustainability Owner")
    .fill(options.sustainabilityOwner ?? "Playwright Sustainability Owner");
  await page
    .getByLabel("Board Approver")
    .fill(options.boardApprover ?? "Playwright Board Approver");

  const createButton = page.getByTestId("create-report-run-button");
  await expect(createButton).toBeEnabled();
  await createButton.click();

  await expect(page).toHaveURL(/approval-center/);
  const runId = new URL(page.url()).searchParams.get("runId");
  if (!runId) {
    throw new Error(`Run id was not present in approval-center URL: ${page.url()}`);
  }

  await waitForRunRow(page, runId);
  return runId;
}

export async function createPublishedRunViaApi(
  request: APIRequestContext,
  workspace: WorkspaceContext = getSeededWorkspace(),
): Promise<string> {
  const apiBaseUrl = resolveApiBaseUrl();
  const workspaceContextResponse = await request.get(`${apiBaseUrl}/catalog/workspace-context`, {
    headers: buildApiHeaders(workspace.tenantId),
    params: {
      tenant_id: workspace.tenantId,
      project_id: workspace.projectId,
    },
  });
  expect(workspaceContextResponse.ok()).toBeTruthy();
  const workspaceContext = (await workspaceContextResponse.json()) as WorkspaceContextResponse;
  const connectorIds = workspaceContext.integrations.map((integration) => integration.id);
  const connectorScope = workspaceContext.integrations.map(
    (integration) => integration.connector_type,
  );
  expect(connectorIds.length).toBeGreaterThan(0);

  const syncResponse = await request.post(`${apiBaseUrl}/integrations/sync`, {
    headers: buildApiHeaders(workspace.tenantId),
    data: {
      tenant_id: workspace.tenantId,
      project_id: workspace.projectId,
      connector_ids: connectorIds,
    },
  });
  expect(syncResponse.ok()).toBeTruthy();

  const createResponse = await request.post(`${apiBaseUrl}/runs`, {
    headers: buildApiHeaders(workspace.tenantId),
    data: {
      tenant_id: workspace.tenantId,
      project_id: workspace.projectId,
      framework_target: ["TSRS1", "TSRS2", "CSRD"],
      active_reg_pack_version: "core-pack-v1",
      report_blueprint_version: workspaceContext.blueprint_version,
      company_profile_ref: workspaceContext.company_profile.id,
      brand_kit_ref: workspaceContext.brand_kit.id,
      connector_scope: connectorScope,
      scope_decision: {
        reporting_year: "2025",
        include_scope3: true,
        operation_countries: "Turkiye",
        sustainability_owner: "Playwright Sustainability Owner",
        board_approver: "Playwright Board Approver",
        approval_sla_days: 5,
        retrieval_tasks: buildDeterministicRetrievalTasks("2025"),
      },
    },
  });
  expect(createResponse.ok()).toBeTruthy();
  const createPayload = (await createResponse.json()) as { run_id: string };
  const runId = createPayload.run_id;

  const executeResponse = await request.post(`${apiBaseUrl}/runs/${runId}/execute`, {
    headers: buildApiHeaders(workspace.tenantId),
    data: {
      tenant_id: workspace.tenantId,
      project_id: workspace.projectId,
      max_steps: 64,
      human_approval_override: "approved",
    },
  });
  expect(executeResponse.ok()).toBeTruthy();

  const publishResponse = await request.post(`${apiBaseUrl}/runs/${runId}/publish`, {
    headers: buildApiHeaders(workspace.tenantId, { role: "board_member" }),
    data: {
      tenant_id: workspace.tenantId,
      project_id: workspace.projectId,
    },
  });
  expect(publishResponse.ok()).toBeTruthy();
  await waitForPublishedRunViaApi(request, workspace, runId);
  return runId;
}
