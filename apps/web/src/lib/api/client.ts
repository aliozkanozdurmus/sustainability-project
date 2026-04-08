// Bu API yardimcisi, client akisindaki istemci davranisini toplar.

import { z } from "zod";

import { webEnv } from "@/lib/env/web-env";

export type WorkspaceContext = {
  tenantId: string;
  projectId: string;
};

export type UserRole =
  | "admin"
  | "compliance_manager"
  | "analyst"
  | "auditor_readonly"
  | "board_member";

export const WORKSPACE_STORAGE_KEY = "veni_workspace_context_v1";
export const WORKSPACE_STORAGE_EVENT = "veni-workspace-context-updated";

let cachedWorkspaceRaw: string | null | undefined;
let cachedWorkspaceValue: WorkspaceContext | null = null;

export const workspaceContextSchema = z.object({
  tenantId: z.string().trim().min(1),
  projectId: z.string().trim().min(1),
});

function parseWorkspaceContextValue(
  value: unknown,
): WorkspaceContext | null {
  const parsed = workspaceContextSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

export function getApiBaseUrl(): string {
  if (webEnv.NEXT_PUBLIC_API_BASE_URL) {
    return webEnv.NEXT_PUBLIC_API_BASE_URL;
  }
  if (typeof window !== "undefined" && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://127.0.0.1:8000";
}

export function getEnvWorkspaceFallback(): Partial<WorkspaceContext> {
  const parsed = parseWorkspaceContextValue({
    tenantId: webEnv.NEXT_PUBLIC_DEFAULT_TENANT_ID,
    projectId: webEnv.NEXT_PUBLIC_DEFAULT_PROJECT_ID,
  });

  return parsed ?? {};
}

export function readWorkspaceContext(): WorkspaceContext | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(WORKSPACE_STORAGE_KEY);
  if (raw === cachedWorkspaceRaw) {
    return cachedWorkspaceValue;
  }

  cachedWorkspaceRaw = raw;
  if (!raw) {
    cachedWorkspaceValue = null;
    return null;
  }
  try {
    cachedWorkspaceValue = parseWorkspaceContextValue(JSON.parse(raw));
    return cachedWorkspaceValue;
  } catch {
    cachedWorkspaceValue = null;
    return null;
  }
}

export function getInitialWorkspaceContext(): WorkspaceContext | null {
  const stored = readWorkspaceContext();
  if (stored) {
    return stored;
  }
  const fallback = getEnvWorkspaceFallback();
  if (fallback.tenantId && fallback.projectId) {
    return {
      tenantId: fallback.tenantId,
      projectId: fallback.projectId,
    };
  }
  return null;
}

export function persistWorkspaceContext(workspace: WorkspaceContext): void {
  if (typeof window === "undefined") {
    return;
  }
  const parsedWorkspace = workspaceContextSchema.parse(workspace);
  cachedWorkspaceValue = parsedWorkspace;
  cachedWorkspaceRaw = JSON.stringify(parsedWorkspace);
  window.localStorage.setItem(WORKSPACE_STORAGE_KEY, cachedWorkspaceRaw);
  window.dispatchEvent(new Event(WORKSPACE_STORAGE_EVENT));
}

type BuildApiHeadersOptions = {
  role?: UserRole;
  userId?: string;
  includeJsonContentType?: boolean;
};

export function buildApiHeaders(
  tenantId: string,
  options: BuildApiHeadersOptions = {},
): HeadersInit {
  const includeJsonContentType = options.includeJsonContentType ?? true;
  const headers: Record<string, string> = {
    "x-user-role": "analyst",
    "x-user-id": "web-ui-user",
    "x-tenant-id": tenantId,
  };
  headers["x-user-role"] = options.role ?? "analyst";
  headers["x-user-id"] = options.userId ?? "web-ui-user";
  if (includeJsonContentType) {
    headers["Content-Type"] = "application/json";
  }
  return headers;
}

export function buildRunReportPdfPath(workspace: WorkspaceContext, runId: string): string {
  return `/runs/${encodeURIComponent(runId)}/report-pdf?tenant_id=${encodeURIComponent(workspace.tenantId)}&project_id=${encodeURIComponent(workspace.projectId)}`;
}

export function buildRunArtifactPath(
  workspace: WorkspaceContext,
  runId: string,
  artifactId: string,
): string {
  return `/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}?tenant_id=${encodeURIComponent(workspace.tenantId)}&project_id=${encodeURIComponent(workspace.projectId)}`;
}

export function buildRunPackageStatusPath(workspace: WorkspaceContext, runId: string): string {
  return `/runs/${encodeURIComponent(runId)}/package-status?tenant_id=${encodeURIComponent(workspace.tenantId)}&project_id=${encodeURIComponent(workspace.projectId)}`;
}

export function buildDashboardOverviewPath(workspace: WorkspaceContext): string {
  return `/dashboard/overview?tenant_id=${encodeURIComponent(workspace.tenantId)}&project_id=${encodeURIComponent(workspace.projectId)}`;
}

export function getErrorMessageFromPayload(payload: unknown): string | null {
  if (typeof payload === "string" && payload.trim().length > 0) {
    return payload;
  }

  if (!payload || typeof payload !== "object") {
    return null;
  }

  const candidate = payload as { detail?: unknown; message?: string };

  if (typeof candidate.detail === "string" && candidate.detail.trim().length > 0) {
    return candidate.detail;
  }
  if (candidate.detail && typeof candidate.detail === "object") {
    return JSON.stringify(candidate.detail, null, 2);
  }
  if (typeof candidate.message === "string" && candidate.message.trim().length > 0) {
    return candidate.message;
  }

  return null;
}

export async function getResponseErrorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  if (raw) {
    try {
      const payload = JSON.parse(raw) as { detail?: unknown; message?: string };
      const normalized = getErrorMessageFromPayload(payload);
      if (normalized) {
        return normalized;
      }
    } catch {
      return raw;
    }

    return raw;
  }
  return `Request failed with status ${response.status}`;
}

export async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(await getResponseErrorMessage(response));
  }
  return (await response.json()) as T;
}
