// Bu E2E senaryosu, ust bardaki global arama kutusunun sayfa yonlendirmesini dogrular.

import { expect, test } from "@playwright/test";

import { getSeededWorkspace, primeWorkspaceContext } from "../helpers";

test("global search routes to retrieval lab", async ({ page }) => {
  const workspace = getSeededWorkspace();

  await primeWorkspaceContext(page, workspace);
  await page.goto(
    `/dashboard?tenantId=${encodeURIComponent(workspace.tenantId)}&projectId=${encodeURIComponent(workspace.projectId)}`,
  );

  const searchInput = page.getByTestId("global-search-input");
  await expect(searchInput).toBeVisible();
  await expect(page.getByTestId("app-shell-brand-logo")).toBeVisible();
  await expect(page.getByTestId("dashboard-hero-logo")).toBeVisible();

  await searchInput.fill("retrieval");
  await expect(page.getByTestId("global-search-results")).toContainText("Retrieval Lab");

  await searchInput.press("Enter");

  await expect(page).toHaveURL(/\/retrieval-lab/);
  await expect(page.getByRole("heading", { name: "Retrieval Research Bench" })).toBeVisible();
});
