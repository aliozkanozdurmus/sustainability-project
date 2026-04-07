// Bu E2E senaryosu, publish to pdf akisini uctan uca dogrular.

import { expect, test } from "@playwright/test";
import { stat } from "node:fs/promises";

import {
  createPublishedRunViaApi,
  createRunViaWizard,
  getSeededWorkspace,
  primeWorkspaceContext,
  runRow,
  waitForRunRow,
} from "../helpers";

test("happy-path publish-to-pdf", async ({ page }, testInfo) => {
  const workspace = getSeededWorkspace();
  const runId = await createRunViaWizard(page);

  await page.getByTestId(`run-${runId}-execute`).click();
  await expect(page.getByTestId("approval-center-notice")).toContainText(`Run ${runId} executed.`);
  await expect(page.getByTestId(`run-${runId}-node`)).toHaveText("HUMAN_APPROVAL");

  await page.getByTestId(`run-${runId}-approve`).click();
  await expect(page.getByTestId("approval-center-notice")).toContainText(
    `Run ${runId} approved and continued.`,
  );
  await expect(page.getByTestId(`run-${runId}-status`)).toHaveText("completed");
  await expect(page.getByTestId(`run-${runId}-publish-ready`)).toHaveText("yes");

  await page.getByTestId(`run-${runId}-publish`).click();
  await expect(page.getByTestId("approval-center-notice")).toContainText(`Run ${runId}`);
  await expect(page.getByTestId(`run-${runId}-status`)).toHaveText("published", {
    timeout: 120_000,
  });
  await expect(page.getByTestId(`run-${runId}-download-pdf`)).toBeVisible({
    timeout: 120_000,
  });

  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId(`run-${runId}-download-pdf`).click();
  const download = await downloadPromise;
  const downloadPath = testInfo.outputPath(`${runId}.pdf`);
  await download.saveAs(downloadPath);
  const pdfStats = await stat(downloadPath);
  expect(pdfStats.size).toBeGreaterThan(0);

  await page.goto(
    `/approval-center?tenantId=${encodeURIComponent(workspace.tenantId)}&projectId=${encodeURIComponent(workspace.projectId)}`,
  );
  await waitForRunRow(page, runId);
  await expect(page.getByTestId(`run-${runId}-status`)).toHaveText("published");
  await expect(page.getByTestId(`run-${runId}-download-pdf`)).toBeVisible();
});

test("publish-too-early shows blocker state", async ({ page }) => {
  const runId = await createRunViaWizard(page, {
    legalName: "Playwright Blocker Holding",
    taxId: "TR-0001112223",
  });

  await page.getByTestId(`run-${runId}-publish`).click();
  await expect(page.getByTestId("approval-center-error")).toContainText("Publish blocked.");
  await expect(page.getByTestId("approval-center-error")).toContainText("WORKFLOW_NOT_PUBLISH_READY");
  await expect(page.getByTestId(`run-${runId}-status`)).not.toHaveText("published");
});

test("download-after-refresh stays available for published runs", async ({ page, request }, testInfo) => {
  const workspace = getSeededWorkspace();
  const runId = await createPublishedRunViaApi(request, workspace);

  await primeWorkspaceContext(page, workspace);
  await page.goto(
    `/approval-center?tenantId=${encodeURIComponent(workspace.tenantId)}&projectId=${encodeURIComponent(workspace.projectId)}`,
  );
  await waitForRunRow(page, runId);
  await expect(page.getByTestId(`run-${runId}-status`)).toHaveText("published");

  await page.reload();
  await waitForRunRow(page, runId);
  await expect(page.getByTestId(`run-${runId}-download-pdf`)).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId(`run-${runId}-download-pdf`).click();
  const download = await downloadPromise;
  const downloadPath = testInfo.outputPath(`${runId}-refresh.pdf`);
  await download.saveAs(downloadPath);
  const pdfStats = await stat(downloadPath);
  expect(pdfStats.size).toBeGreaterThan(0);

  await expect(runRow(page, runId)).toBeVisible();
});
