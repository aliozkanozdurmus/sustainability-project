import { expect, test } from "@playwright/test";

import { getSeededWorkspace, primeWorkspaceContext } from "../helpers";

test("integrations setup saves a profile and refreshes connector detail", async ({ page }) => {
  const workspace = getSeededWorkspace();

  await primeWorkspaceContext(page, workspace);
  await page.goto("/integrations/setup");

  const firstCard = page.locator('[data-testid^="integration-card-"]').first();
  await expect(firstCard).toBeVisible({ timeout: 30_000 });
  await firstCard.click();

  const credentialInput = page.getByLabel("Credential Ref");
  await expect(credentialInput).toBeVisible();
  await credentialInput.fill(`cred://playwright/${Date.now()}`);

  await page.getByTestId("connector-save-profile-button").click();
  await expect(page.getByTestId("integrations-notice")).toContainText("Connector profile saved", {
    timeout: 30_000,
  });

  await page.getByRole("button", { name: "Refresh Detail" }).click();
  await expect(credentialInput).toHaveValue(/cred:\/\/playwright\//);
  await expect(page.getByTestId("integrations-error")).toHaveCount(0);
});
