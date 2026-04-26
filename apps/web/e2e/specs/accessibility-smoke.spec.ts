// Bu E2E senaryosu, locale ve reduced-motion temel guven sinyallerini dogrular.

import { expect, test } from "@playwright/test";

import { getSeededWorkspace, primeWorkspaceContext } from "../helpers";

test("primary surfaces honor tr locale and reduced motion", async ({ page }) => {
  const workspace = getSeededWorkspace();
  await primeWorkspaceContext(page, workspace);
  await page.emulateMedia({ reducedMotion: "reduce" });

  await page.goto(
    `/approval-center?tenantId=${encodeURIComponent(workspace.tenantId)}&projectId=${encodeURIComponent(workspace.projectId)}`,
  );

  await expect(page.locator("html")).toHaveAttribute("lang", "tr");
  await expect(page.getByRole("link", { name: "New Report Run" })).toBeVisible();

  const motionSnapshot = await page.evaluate(() => ({
    reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
  }));

  expect(motionSnapshot.reducedMotion).toBeTruthy();
  expect(motionSnapshot.scrollBehavior).toBe("auto");
});
