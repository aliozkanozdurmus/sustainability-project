// Bu E2E senaryosu, approval center queue-first deneyimini dogrular.

import { expect, test } from "@playwright/test";

import { createRunViaWizard } from "../helpers";

test("queue-first approval center keeps blockers drawer and grouped lanes visible", async ({ page }) => {
  const runId = await createRunViaWizard(page, {
    legalName: "Playwright Queue Holding",
    taxId: "TR-5556667778",
  });

  await expect(page.getByText("Immediate blockers")).toBeVisible();
  await expect(page.getByText("Release queue")).toBeVisible();
  await expect(page.getByTestId("publish-blockers-drawer")).toBeVisible();

  await page.getByTestId(`run-${runId}-package-status`).click();
  await expect(page.getByTestId("approval-center-notice")).toContainText("Package status refreshed");
  await expect(page.getByTestId("publish-blockers-drawer")).toContainText(runId.slice(0, 8));
  await expect(page.getByTestId(`run-row-${runId}`)).toContainText("Artifact integrity");
});
