import { expect, test } from "@playwright/test";

import { WORKSPACE_STORAGE_KEY } from "../src/lib/api/client";

test("workspace bootstrap UI creates and stores workspace context", async ({ page }) => {
  const suffix = `${Date.now()}`;
  await page.goto("/reports/new");

  await page.getByLabel("Tenant Name").fill(`Playwright Workspace ${suffix}`);
  await page.getByLabel("Tenant Slug").fill(`playwright-workspace-${suffix}`);
  await page.getByLabel("Project Name").fill(`Publish PDF Workspace ${suffix}`);
  await page.getByLabel("Project Code").fill(`PWSPACE${suffix.slice(-6)}`);
  await page.getByLabel("Currency").fill("TRY");
  await page.getByTestId("workspace-bootstrap-button").click();

  await expect(page.getByTestId("new-report-notice")).toContainText("Workspace ready.");
  await expect(page.getByTestId("workspace-context-status")).toContainText("tenant_id=");
  await expect(page.getByTestId("workspace-context-status")).toContainText("project_id=");

  const storedWorkspace = await page.evaluate((storageKey) => {
    const raw = window.localStorage.getItem(storageKey);
    return raw ? JSON.parse(raw) : null;
  }, WORKSPACE_STORAGE_KEY);

  expect(storedWorkspace).not.toBeNull();
  expect(storedWorkspace).toHaveProperty("tenantId");
  expect(storedWorkspace).toHaveProperty("projectId");
});
