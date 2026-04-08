import type { WorkspaceContext } from "./client";

type QueryKey = readonly unknown[];

function workspaceKey(workspace: WorkspaceContext | null): QueryKey {
  return workspace
    ? (["tenant", workspace.tenantId, "project", workspace.projectId] as const)
    : (["workspace", "none"] as const);
}

export const queryKeys = {
  catalog: {
    workspaceContext: (workspace: WorkspaceContext | null) =>
      ["catalog", ...workspaceKey(workspace), "workspace-context"] as const,
  },
  dashboard: {
    overview: (workspace: WorkspaceContext | null) =>
      ["dashboard", ...workspaceKey(workspace), "overview"] as const,
    notifications: (workspace: WorkspaceContext | null) =>
      ["dashboard", ...workspaceKey(workspace), "notifications"] as const,
  },
  runs: {
    list: (workspace: WorkspaceContext | null) =>
      ["runs", ...workspaceKey(workspace), "list"] as const,
    packageStatus: (workspace: WorkspaceContext | null, runId: string | null) =>
      ["runs", ...workspaceKey(workspace), "package-status", runId ?? "none"] as const,
    triage: (workspace: WorkspaceContext | null, runId: string | null) =>
      ["runs", ...workspaceKey(workspace), "triage", runId ?? "none"] as const,
  },
  integrations: {
    summaries: (workspace: WorkspaceContext | null) =>
      ["integrations", ...workspaceKey(workspace), "summaries"] as const,
    detail: (workspace: WorkspaceContext | null, integrationId: string | null) =>
      ["integrations", ...workspaceKey(workspace), "detail", integrationId ?? "none"] as const,
  },
  documents: {
    extractionStatus: (
      workspace: WorkspaceContext | null,
      documentId: string | null,
      extractionId: string | null,
    ) =>
      [
        "documents",
        ...workspaceKey(workspace),
        "extraction-status",
        documentId ?? "none",
        extractionId ?? "none",
      ] as const,
    indexStatus: (
      workspace: WorkspaceContext | null,
      documentId: string | null,
      extractionId: string | null,
    ) =>
      [
        "documents",
        ...workspaceKey(workspace),
        "index-status",
        documentId ?? "none",
        extractionId ?? "none",
      ] as const,
  },
  retrieval: {
    query: (workspace: WorkspaceContext | null) =>
      ["retrieval", ...workspaceKey(workspace), "query"] as const,
  },
};
