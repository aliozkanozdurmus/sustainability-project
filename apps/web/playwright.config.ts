import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  timeout: 120_000,
  expect: {
    timeout: 15_000,
  },
  reporter: [
    ["list"],
    ["html", { outputFolder: "../../output/playwright/report", open: "never" }],
  ],
  outputDir: "../../output/playwright/test-results",
  use: {
    baseURL: process.env.PLAYWRIGHT_WEB_BASE_URL ?? "http://127.0.0.1:3000",
    acceptDownloads: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    headless: true,
  },
});
