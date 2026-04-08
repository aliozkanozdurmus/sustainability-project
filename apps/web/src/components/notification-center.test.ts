import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { NotificationCenterPanel } from "./notification-center";

describe("NotificationCenterPanel", () => {
  it("renders the workspace-required state", () => {
    const html = renderToStaticMarkup(
      createElement(NotificationCenterPanel, {
        workspaceReady: false,
        notifications: [],
      }),
    );

    expect(html).toContain("Workspace required");
    expect(html).toContain("Select or bootstrap a workspace before loading notifications.");
  });

  it("renders the empty-feed state", () => {
    const html = renderToStaticMarkup(
      createElement(NotificationCenterPanel, {
        workspaceReady: true,
        notifications: [],
      }),
    );

    expect(html).toContain("No notifications yet");
    expect(html).toContain("New sync, verification, and publish events will appear here.");
  });
});
