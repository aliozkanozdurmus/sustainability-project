import createClient from "openapi-fetch";
import { z } from "zod";

import type { paths } from "@sustainability/shared-types";

import {
  buildApiHeaders,
  getErrorMessageFromPayload,
  getApiBaseUrl,
  getResponseErrorMessage,
  type UserRole,
  type WorkspaceContext,
} from "./client";

export type ApiRequestOptions = {
  tenantId: string;
  role?: UserRole;
  userId?: string;
  includeJsonContentType?: boolean;
  signal?: AbortSignal;
};

export type WorkspaceRequestOptions = {
  workspace: WorkspaceContext;
  role?: UserRole;
  userId?: string;
  includeJsonContentType?: boolean;
  signal?: AbortSignal;
};

export function createOpenApiClient() {
  return createClient<paths>({
    baseUrl: getApiBaseUrl(),
  });
}

export function workspaceQueryParams(workspace: WorkspaceContext) {
  return {
    tenant_id: workspace.tenantId,
    project_id: workspace.projectId,
  };
}

export function workspaceHeaders(options: WorkspaceRequestOptions): HeadersInit {
  return buildApiHeaders(options.workspace.tenantId, {
    role: options.role,
    userId: options.userId,
    includeJsonContentType: options.includeJsonContentType,
  });
}

export async function parseOpenApiResult<TResponse, TOutput>(
  result: {
    data?: TResponse;
    error?: unknown;
    response: Response;
  },
  schema: z.ZodType<TOutput>,
): Promise<TOutput> {
  if (!result.response.ok || result.error) {
    const normalizedError = getErrorMessageFromPayload(result.error);
    if (normalizedError) {
      throw new Error(normalizedError);
    }

    throw new Error(await getResponseErrorMessage(result.response));
  }

  if (typeof result.data === "undefined") {
    throw new Error("API response body was empty.");
  }

  return schema.parse(result.data);
}

export async function requestJsonWithFetch<TOutput>(
  path: string,
  init: RequestInit,
  schema: z.ZodType<TOutput>,
): Promise<TOutput> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, init);
  if (!response.ok) {
    throw new Error(await getResponseErrorMessage(response));
  }
  return schema.parse(await response.json());
}

export async function downloadBlob(
  path: string,
  options: ApiRequestOptions,
): Promise<{ blob: Blob; filename: string | null }> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "GET",
    headers: buildApiHeaders(options.tenantId, {
      role: options.role,
      userId: options.userId,
      includeJsonContentType: options.includeJsonContentType ?? false,
    }),
    signal: options.signal,
  });

  if (!response.ok) {
    throw new Error(await getResponseErrorMessage(response));
  }

  const blob = await response.blob();
  if (blob.size <= 0) {
    throw new Error("Downloaded file is empty.");
  }

  const contentDisposition = response.headers.get("content-disposition");
  const filenameMatch = contentDisposition?.match(/filename=\"?([^\";]+)\"?/i);

  return {
    blob,
    filename: filenameMatch?.[1] ?? null,
  };
}

export function triggerBrowserDownload(blob: Blob, filename: string): void {
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
}
