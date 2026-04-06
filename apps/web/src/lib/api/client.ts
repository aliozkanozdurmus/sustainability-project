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

export function getApiBaseUrl(): string {
  if (process.env.NEXT_PUBLIC_API_BASE_URL) {
    return process.env.NEXT_PUBLIC_API_BASE_URL;
  }
  if (typeof window !== "undefined" && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://127.0.0.1:8000";
}

export function getEnvWorkspaceFallback(): Partial<WorkspaceContext> {
  return {
    tenantId: process.env.NEXT_PUBLIC_DEFAULT_TENANT_ID,
    projectId: process.env.NEXT_PUBLIC_DEFAULT_PROJECT_ID,
  };
}

export function readWorkspaceContext(): WorkspaceContext | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(WORKSPACE_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<WorkspaceContext>;
    if (parsed.tenantId && parsed.projectId) {
      return {
        tenantId: parsed.tenantId,
        projectId: parsed.projectId,
      };
    }
    return null;
  } catch {
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
  window.localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(workspace));
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

export async function getResponseErrorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  if (raw) {
    let payload: { detail?: unknown; message?: string } | null = null;
    try {
      payload = JSON.parse(raw) as { detail?: unknown; message?: string };
    } catch {
      payload = null;
    }
    if (payload) {
      if (typeof payload.detail === "string" && payload.detail.trim().length > 0) {
        return payload.detail;
      }
      if (payload.detail && typeof payload.detail === "object") {
        return JSON.stringify(payload.detail, null, 2);
      }
      if (typeof payload.message === "string" && payload.message.trim().length > 0) {
        return payload.message;
      }
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
