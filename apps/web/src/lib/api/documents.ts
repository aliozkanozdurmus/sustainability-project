import { useMutation } from "@tanstack/react-query";
import { z } from "zod";

import type { WorkspaceContext } from "./client";
import {
  createOpenApiClient,
  parseOpenApiResult,
  requestJsonWithFetch,
  workspaceHeaders,
  workspaceQueryParams,
} from "./core";
import { nullableStringSchema } from "./schema-helpers";

const fileSchema = z.custom<File>(
  (value) => typeof File !== "undefined" && value instanceof File,
  "Select a file to upload.",
);

export const documentUploadFormSchema = z.object({
  documentType: z.string().trim().min(1),
  issuedAt: z.string().trim().optional(),
  file: fileSchema,
});

export const documentUploadResponseSchema = z.object({
  document_id: z.string(),
  tenant_id: z.string(),
  project_id: z.string(),
  filename: z.string(),
  document_type: z.string(),
  storage_uri: z.string(),
  checksum: z.string(),
  mime_type: nullableStringSchema,
  status: z.string(),
  ingested_at: z.string(),
});

export const extractionRequestSchema = z.object({
  tenant_id: z.string().trim().min(1),
  project_id: z.string().trim().min(1),
  extraction_mode: z.string().trim().min(1),
});

export const extractionResponseSchema = z.object({
  extraction_id: z.string(),
  source_document_id: z.string(),
  status: z.string(),
  provider: z.string(),
  quality_score: z.number().nullable(),
  extracted_text_uri: nullableStringSchema,
  raw_payload_uri: nullableStringSchema,
  chunk_count: z.number(),
});

export const extractionQueueResponseSchema = z.object({
  extraction_id: z.string(),
  source_document_id: z.string(),
  status: z.string(),
  queue_job_id: z.string(),
});

export const extractionStatusResponseSchema = z.object({
  extraction_id: z.string(),
  source_document_id: z.string(),
  status: z.string(),
  provider: z.string(),
  extraction_mode: z.string(),
  quality_score: z.number().nullable(),
  chunk_count: z.number(),
  error_message: nullableStringSchema,
  started_at: nullableStringSchema,
  completed_at: nullableStringSchema,
});

export const indexStatusResponseSchema = z.object({
  extraction_id: z.string(),
  source_document_id: z.string(),
  status: z.string(),
  index_provider: z.string(),
  index_name: z.string(),
  indexed_chunk_count: z.number(),
  error_message: nullableStringSchema,
});

export type DocumentUploadResponse = z.infer<typeof documentUploadResponseSchema>;
export type ExtractionResponse = z.infer<typeof extractionResponseSchema>;
export type ExtractionQueueResponse = z.infer<typeof extractionQueueResponseSchema>;
export type ExtractionStatusResponse = z.infer<typeof extractionStatusResponseSchema>;
export type IndexStatusResponse = z.infer<typeof indexStatusResponseSchema>;

export async function uploadDocument(
  workspace: WorkspaceContext,
  input: z.infer<typeof documentUploadFormSchema>,
) {
  const parsed = documentUploadFormSchema.parse(input);
  const formData = new FormData();
  formData.set("tenant_id", workspace.tenantId);
  formData.set("project_id", workspace.projectId);
  formData.set("document_type", parsed.documentType);
  if (parsed.issuedAt && parsed.issuedAt.trim().length > 0) {
    formData.set("issued_at", parsed.issuedAt.trim());
  }
  formData.set("file", parsed.file);

  return requestJsonWithFetch(
    "/documents/upload",
    {
      method: "POST",
      headers: workspaceHeaders({
        workspace,
        includeJsonContentType: false,
      }),
      body: formData,
    },
    documentUploadResponseSchema,
  );
}

export async function extractDocument(
  workspace: WorkspaceContext,
  documentId: string,
  input: z.infer<typeof extractionRequestSchema>,
) {
  const client = createOpenApiClient();
  const parsed = extractionRequestSchema.parse(input);
  return parseOpenApiResult(
    await client.POST("/documents/{document_id}/extract", {
      params: {
        path: {
          document_id: documentId,
        },
      },
      headers: workspaceHeaders({ workspace }),
      body: parsed,
    }),
    extractionResponseSchema,
  );
}

export async function queueDocumentExtraction(
  workspace: WorkspaceContext,
  documentId: string,
  input: z.infer<typeof extractionRequestSchema>,
) {
  const client = createOpenApiClient();
  const parsed = extractionRequestSchema.parse(input);
  return parseOpenApiResult(
    await client.POST("/documents/{document_id}/extract/queue", {
      params: {
        path: {
          document_id: documentId,
        },
      },
      headers: workspaceHeaders({ workspace }),
      body: parsed,
    }),
    extractionQueueResponseSchema,
  );
}

export async function readExtractionStatus(
  workspace: WorkspaceContext,
  documentId: string,
  extractionId: string,
  signal?: AbortSignal,
) {
  const client = createOpenApiClient();
  return parseOpenApiResult(
    await client.GET("/documents/{document_id}/extractions/{extraction_id}", {
      params: {
        path: {
          document_id: documentId,
          extraction_id: extractionId,
        },
        query: workspaceQueryParams(workspace),
      },
      headers: workspaceHeaders({ workspace }),
      signal,
    }),
    extractionStatusResponseSchema,
  );
}

export async function readIndexStatus(
  workspace: WorkspaceContext,
  documentId: string,
  extractionId: string,
  signal?: AbortSignal,
) {
  const client = createOpenApiClient();
  return parseOpenApiResult(
    await client.GET("/documents/{document_id}/extractions/{extraction_id}/index-status", {
      params: {
        path: {
          document_id: documentId,
          extraction_id: extractionId,
        },
        query: workspaceQueryParams(workspace),
      },
      headers: workspaceHeaders({ workspace }),
      signal,
    }),
    indexStatusResponseSchema,
  );
}

export function useUploadDocumentMutation(workspace: WorkspaceContext | null) {
  return useMutation({
    mutationFn: (input: z.infer<typeof documentUploadFormSchema>) => {
      if (!workspace) {
        throw new Error("Workspace not selected. Create/select workspace from New Report first.");
      }
      return uploadDocument(workspace, input);
    },
  });
}

export function useExtractDocumentMutation(workspace: WorkspaceContext | null) {
  return useMutation({
    mutationFn: (variables: { documentId: string; extractionMode: string }) => {
      if (!workspace) {
        throw new Error("Workspace is required.");
      }

      return extractDocument(workspace, variables.documentId, {
        tenant_id: workspace.tenantId,
        project_id: workspace.projectId,
        extraction_mode: variables.extractionMode,
      });
    },
  });
}

export function useQueueDocumentExtractionMutation(workspace: WorkspaceContext | null) {
  return useMutation({
    mutationFn: (variables: { documentId: string; extractionMode: string }) => {
      if (!workspace) {
        throw new Error("Workspace is required.");
      }

      return queueDocumentExtraction(workspace, variables.documentId, {
        tenant_id: workspace.tenantId,
        project_id: workspace.projectId,
        extraction_mode: variables.extractionMode,
      });
    },
  });
}

export function useReadExtractionStatusMutation(workspace: WorkspaceContext | null) {
  return useMutation({
    mutationFn: (variables: { documentId: string; extractionId: string }) => {
      if (!workspace) {
        throw new Error("Workspace is required.");
      }

      return readExtractionStatus(workspace, variables.documentId, variables.extractionId);
    },
  });
}

export function useReadIndexStatusMutation(workspace: WorkspaceContext | null) {
  return useMutation({
    mutationFn: (variables: { documentId: string; extractionId: string }) => {
      if (!workspace) {
        throw new Error("Workspace is required.");
      }

      return readIndexStatus(workspace, variables.documentId, variables.extractionId);
    },
  });
}
