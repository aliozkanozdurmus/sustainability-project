import { describe, expect, it } from "vitest";

import { canAccessRoute, getAccessibleRoutes } from "./rbac";

describe("rbac route enforcement", () => {
  it("allows board member to access board cockpit", () => {
    expect(canAccessRoute("board_member", "/app/dashboard/board-cockpit")).toBe(true);
  });

  it("denies analyst for publish route", () => {
    expect(canAccessRoute("analyst", "/app/projects/[projectId]/publish")).toBe(false);
  });

  it("returns approval center for committee secretary", () => {
    const routes = getAccessibleRoutes("committee_secretary");
    expect(routes).toContain("/app/approval-center");
  });
});

