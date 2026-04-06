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
  await page.getByLabel("Workspace Legal Name").fill(`Playwright Sustainability Holding ${suffix}`);
  await page.getByLabel("Workspace Sector").fill("Ambalaj ve endustriyel uretim");
  await page.getByLabel("Workspace Headquarters").fill("Istanbul, Turkiye");
  await page.getByLabel("Workspace Company Description").fill(
    "ERP verisini ve kanit katmanini kurumsal rapora donusturen demo sirket profili.",
  );
  await page.getByLabel("Workspace CEO Name").fill("Playwright Demo CEO");
  await page.getByLabel("Workspace CEO Message").fill(
    "Kurumsal surdurulebilirlik performansimizi otomatik ve izlenebilir sekilde yonetiyoruz.",
  );
  await page.getByLabel("Workspace Sustainability Approach").fill(
    "Veri butunlugu, operasyonel verimlilik ve paydas guvenini birlikte koruyan bir model.",
  );
  await page.getByLabel("Workspace Brand Name").fill(`Playwright Brand ${suffix}`);
  await page.getByLabel("Workspace Logo URI").fill(
    "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='320' height='120'><rect width='320' height='120' rx='24' fill='%230c4a6e'/><text x='160' y='72' font-size='42' text-anchor='middle' fill='white' font-family='Segoe UI'>PW</text></svg>",
  );
  await page.getByTestId("workspace-bootstrap-button").click();

  await expect(page.getByTestId("new-report-notice")).toContainText("Workspace hazır.");
  await expect(page.getByTestId("workspace-context-status")).toContainText("tenant_id=");
  await expect(page.getByTestId("workspace-context-status")).toContainText("project_id=");
  await expect(page.getByTestId("factory-readiness-panel")).toContainText("Readiness: hazır");

  const storedWorkspace = await page.evaluate((storageKey) => {
    const raw = window.localStorage.getItem(storageKey);
    return raw ? JSON.parse(raw) : null;
  }, WORKSPACE_STORAGE_KEY);

  expect(storedWorkspace).not.toBeNull();
  expect(storedWorkspace).toHaveProperty("tenantId");
  expect(storedWorkspace).toHaveProperty("projectId");
});
