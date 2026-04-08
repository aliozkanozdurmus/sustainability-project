import { describe, expect, it } from "vitest";

import { queryKeys } from "./query-keys";

const workspace = {
  tenantId: "tenant-1",
  projectId: "project-1",
};

describe("queryKeys", () => {
  it("builds stable workspace scoped keys", () => {
    expect(queryKeys.dashboard.overview(workspace)).toEqual([
      "dashboard",
      "tenant",
      "tenant-1",
      "project",
      "project-1",
      "overview",
    ]);
    expect(queryKeys.dashboard.notifications(workspace)).toEqual([
      "dashboard",
      "tenant",
      "tenant-1",
      "project",
      "project-1",
      "notifications",
    ]);
    expect(queryKeys.runs.list(workspace)).toEqual([
      "runs",
      "tenant",
      "tenant-1",
      "project",
      "project-1",
      "list",
    ]);
  });

  it("falls back to a workspace-none key when no workspace is available", () => {
    expect(queryKeys.catalog.workspaceContext(null)).toEqual([
      "catalog",
      "workspace",
      "none",
      "workspace-context",
    ]);
    expect(queryKeys.runs.packageStatus(null, null)).toEqual([
      "runs",
      "workspace",
      "none",
      "package-status",
      "none",
    ]);
  });
});
