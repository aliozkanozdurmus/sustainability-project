import { expect, test } from "@playwright/test";

import { getSeededWorkspace, primeWorkspaceContext } from "../helpers";

test("retrieval lab runs a successful query with seeded workspace context", async ({ page }) => {
  await primeWorkspaceContext(page, getSeededWorkspace());
  await page.goto("/retrieval-lab");

  await expect(page.getByTestId("retrieval-submit-button")).toBeEnabled();
  await page.getByTestId("retrieval-submit-button").click();

  await expect(page.getByTestId("retrieval-error")).toHaveCount(0);
  await expect(page.locator("pre").first()).toContainText("backend", { timeout: 30_000 });
  await expect(page.getByTestId("retrieval-results")).toBeVisible();
});

test("retrieval lab shows validation feedback for undersized queries", async ({ page }) => {
  await primeWorkspaceContext(page, getSeededWorkspace());
  await page.goto("/retrieval-lab");

  await page.getByLabel("Query").fill("a");
  await page.getByTestId("retrieval-submit-button").click();

  await expect(page.getByTestId("retrieval-error")).toContainText("Query must be at least 2 characters.");
});
