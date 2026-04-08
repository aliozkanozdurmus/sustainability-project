import { expect, test } from "@playwright/test";

import { buildNotificationSessionStorageKey } from "../../src/lib/notification-center";
import { primeWorkspaceContext } from "../helpers";

test("notification center popover opens and clears unread state across shell pages", async ({
  page,
}) => {
  const workspace = {
    tenantId: "playwright-tenant",
    projectId: "playwright-project",
  };
  const notificationStorageKey = buildNotificationSessionStorageKey(workspace);
  const mockedOverview = {
    hero: {
      tenant_name: "Playwright Tenant",
      company_name: "Playwright Sustainability Holding",
      project_name: "Playwright Project",
      project_code: "PW-001",
      sector: "Manufacturing",
      headquarters: "Istanbul",
      reporting_currency: "TRY",
      blueprint_version: "factory-v1",
      readiness_label: "Factory ready",
      readiness_score: 96,
      summary: "Ready for governed generation.",
      logo_uri: null,
      primary_color: "#f07f13",
      accent_color: "#2d6d53",
    },
    metrics: [],
    pipeline: [],
    connector_health: [],
    risks: [],
    schedule: [],
    artifact_health: [],
    activity_feed: [],
    run_queue: [],
    generated_at_utc: "2026-04-08T10:06:00Z",
  };
  const mockedNotifications = {
    items: [
      {
        notification_id: "notification-publish-1",
        title: "Controlled publish queued",
        detail: "queued • compose",
        category: "publish",
        status: "attention",
        occurred_at_utc: "2026-04-08T10:05:00Z",
        source_ref: {
          run_id: "run-1",
          audit_event_id: "audit-1",
        },
      },
      {
        notification_id: "notification-verification-1",
        title: "Verification triage required",
        detail: "Critical FAIL 1 • FAIL 2 • UNSURE 1",
        category: "verification",
        status: "critical",
        occurred_at_utc: "2026-04-08T10:06:00Z",
        source_ref: {
          run_id: "run-1",
          audit_event_id: "audit-2",
        },
      },
    ],
    generated_at_utc: "2026-04-08T10:06:00Z",
  };

  await primeWorkspaceContext(page, workspace);
  await page.route("**/dashboard/overview?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mockedOverview),
    });
  });
  await page.route("**/dashboard/notifications?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mockedNotifications),
    });
  });

  await page.goto(
    `/dashboard?tenantId=${encodeURIComponent(workspace.tenantId)}&projectId=${encodeURIComponent(workspace.projectId)}`,
  );

  const bellButton = page.getByTestId("notification-bell-button");
  await expect(bellButton).toBeVisible();
  await expect(page.getByTestId("notification-badge")).toContainText("2");

  await bellButton.click();
  await expect(page.getByTestId("notification-center-panel")).toBeVisible();
  await expect(page.getByTestId("notification-center-panel")).toContainText("Operational activity");
  await expect(page.getByTestId("notification-item-notification-publish-1")).toContainText(
    "Controlled publish queued",
  );

  const currentUrl = page.url();
  await page.getByTestId("notification-item-notification-publish-1").click();
  await expect(page).toHaveURL(currentUrl);
  await expect(page.getByTestId("notification-badge")).toHaveCount(0);

  const seenIds = await page.evaluate((storageKey) => {
    const raw = window.sessionStorage.getItem(storageKey);
    return raw ? JSON.parse(raw) : [];
  }, notificationStorageKey);
  expect(seenIds).toContain("notification-publish-1");
  expect(seenIds).toContain("notification-verification-1");

  await page.keyboard.press("Escape");
  await expect(page.getByTestId("notification-center-panel")).toHaveCount(0);

  await bellButton.click();
  await expect(page.getByTestId("notification-center-panel")).toBeVisible();
  await page.mouse.click(8, 8);
  await expect(page.getByTestId("notification-center-panel")).toHaveCount(0);

  await page.goto(
    `/retrieval-lab?tenantId=${encodeURIComponent(workspace.tenantId)}&projectId=${encodeURIComponent(workspace.projectId)}`,
  );

  await expect(page.getByTestId("notification-bell-button")).toBeVisible();
  await expect(page.getByTestId("notification-badge")).toHaveCount(0);

  await page.getByTestId("notification-bell-button").click();
  await expect(page.getByTestId("notification-center-panel")).toBeVisible();
  await expect(page.getByTestId("notification-center-panel")).toContainText(
    "Controlled publish queued",
  );
});
