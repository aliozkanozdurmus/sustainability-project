import { mkdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";

import {
  PLAYWRIGHT_DOWNLOAD_ROOT,
  PLAYWRIGHT_MANUAL_ROOT,
  buildPlaywrightEnv,
  preparePlaywrightEnvironment,
} from "./playwright-env.mjs";

const WORKSPACE_STORAGE_KEY = "veni_workspace_context_v1";

async function main() {
  const args = process.argv.slice(2);
  const headed = args.includes("--headed");
  const skipDocker = args.includes("--skip-docker");

  const workspace = await preparePlaywrightEnvironment({ skipDocker });
  const env = buildPlaywrightEnv(workspace);
  const sessionId = `${Date.now()}`;
  const screenshotDir = path.join(PLAYWRIGHT_MANUAL_ROOT, sessionId);
  const downloadDir = path.join(PLAYWRIGHT_DOWNLOAD_ROOT, sessionId);

  await mkdir(screenshotDir, { recursive: true });
  await mkdir(downloadDir, { recursive: true });

  const { chromium } = await import("@playwright/test");
  const browser = await chromium.launch({ headless: !headed });
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();

  await page.addInitScript(
    ({ key, value }) => {
      window.localStorage.setItem(key, JSON.stringify(value));
    },
    {
      key: WORKSPACE_STORAGE_KEY,
      value: {
        tenantId: workspace.tenant_id,
        projectId: workspace.project_id,
      },
    },
  );

  try {
    await page.goto(`${env.PLAYWRIGHT_WEB_BASE_URL}/reports/new`);
    await page.getByLabel("Legal Entity Name").fill("Manual Smoke Sustainability Holding");
    await page.getByLabel("Tax / Registry ID").fill("TR-5556667778");
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await page.getByLabel("Sustainability Owner").fill("Manual Smoke Owner");
    await page.getByLabel("Board Approver").fill("Manual Smoke Board Approver");
    await page.screenshot({
      path: path.join(screenshotDir, "01-new-report.png"),
      fullPage: true,
    });

    await page.getByTestId("create-report-run-button").click();
    await page.waitForFunction(() => window.location.pathname === "/approval-center");
    const runId = new URL(page.url()).searchParams.get("runId");
    if (!runId) {
      throw new Error(`Could not determine run id from ${page.url()}`);
    }

    await page.getByTestId(`run-row-${runId}`).waitFor({ state: "visible", timeout: 30_000 });
    await page.getByTestId(`run-${runId}-execute`).click();
    await page.getByTestId(`run-${runId}-approve`).waitFor({ state: "visible", timeout: 30_000 });
    await page.screenshot({
      path: path.join(screenshotDir, "02-after-execute.png"),
      fullPage: true,
    });

    await page.getByTestId(`run-${runId}-approve`).click();
    await page.getByTestId(`run-${runId}-publish`).waitFor({ state: "visible", timeout: 30_000 });
    await page.screenshot({
      path: path.join(screenshotDir, "03-after-approve.png"),
      fullPage: true,
    });

    await page.getByTestId(`run-${runId}-publish`).click();
    await page.getByTestId(`run-${runId}-download-pdf`).waitFor({ state: "visible", timeout: 30_000 });
    await page.screenshot({
      path: path.join(screenshotDir, "04-after-publish.png"),
      fullPage: true,
    });

    const downloadPromise = page.waitForEvent("download");
    await page.getByTestId(`run-${runId}-download-pdf`).click();
    const download = await downloadPromise;
    const pdfPath = path.join(downloadDir, `${runId}.pdf`);
    await download.saveAs(pdfPath);
    const pdfStats = await stat(pdfPath);
    if (pdfStats.size <= 0) {
      throw new Error("Downloaded PDF is empty.");
    }

    const summary = {
      run_id: runId,
      tenant_id: workspace.tenant_id,
      project_id: workspace.project_id,
      pdf_path: pdfPath,
      pdf_size_bytes: pdfStats.size,
      screenshots: [
        path.join(screenshotDir, "01-new-report.png"),
        path.join(screenshotDir, "02-after-execute.png"),
        path.join(screenshotDir, "03-after-approve.png"),
        path.join(screenshotDir, "04-after-publish.png"),
      ],
    };
    await writeFile(
      path.join(screenshotDir, "manual-smoke-summary.json"),
      JSON.stringify(summary, null, 2),
      "utf-8",
    );
    console.log(JSON.stringify(summary, null, 2));
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
