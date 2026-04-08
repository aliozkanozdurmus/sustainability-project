import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import {
  buildRunArtifactPath,
  buildRunReportPdfPath,
  type WorkspaceContext,
  type UserRole,
} from "./client";
import {
  createOpenApiClient,
  downloadBlob,
  parseOpenApiResult,
  triggerBrowserDownload,
  workspaceHeaders,
  workspaceQueryParams,
} from "./core";
import { queryKeys } from "./query-keys";
import { healthBandSchema, jsonObjectSchema, nullableStringSchema, supportTierSchema } from "./schema-helpers";

export const approvalCenterSearchParamsSchema = z.object({
  created: z.string().optional(),
  mode: z.string().optional(),
  runId: z.string().trim().min(1).optional(),
  tenantId: z.string().trim().min(1).optional(),
  projectId: z.string().trim().min(1).optional(),
});

export const reportArtifactSchema = z.object({
  artifact_id: z.string(),
  artifact_type: z.string(),
  filename: z.string(),
  content_type: z.string(),
  size_bytes: z.number(),
  checksum: z.string(),
  created_at_utc: z.string(),
  download_path: z.string(),
  metadata: jsonObjectSchema.optional(),
});

export const runListItemSchema = z.object({
  run_id: z.string(),
  report_run_status: z.string(),
  publish_ready: z.boolean(),
  started_at_utc: nullableStringSchema,
  completed_at_utc: nullableStringSchema,
  active_node: z.string(),
  human_approval: z.string(),
  triage_required: z.boolean(),
  last_checkpoint_status: z.string(),
  last_checkpoint_at_utc: nullableStringSchema,
  package_status: z.string(),
  report_quality_score: z.number().nullable(),
  latest_sync_at_utc: nullableStringSchema,
  visual_generation_status: z.string(),
  report_pdf: reportArtifactSchema.nullable(),
});

export const runListResponseSchema = z.object({
  total: z.number(),
  page: z.number(),
  size: z.number(),
  items: z.array(runListItemSchema),
});

export const triageItemSchema = z.object({
  section_code: z.string(),
  claim_id: z.string(),
  status: z.enum(["FAIL", "UNSURE"]),
  severity: z.string(),
  reason: z.string(),
  confidence: z.number().optional(),
  evidence_refs: z.array(z.string()),
});

export const triageResponseSchema = z.object({
  run_id: z.string(),
  fail_count: z.number(),
  unsure_count: z.number(),
  critical_fail_count: z.number(),
  total_items: z.number(),
  items: z.array(triageItemSchema),
});

export const runPublishResponseSchema = z.object({
  published: z.boolean(),
  report_run_status: z.string(),
  package_job_id: nullableStringSchema,
  package_status: z.string(),
  estimated_stage: nullableStringSchema,
  artifacts: z.array(reportArtifactSchema),
  report_pdf: reportArtifactSchema.nullable(),
});

export const runPackageStatusSchema = z.object({
  run_id: z.string(),
  package_job_id: nullableStringSchema,
  package_status: z.string(),
  current_stage: nullableStringSchema,
  report_quality_score: z.number().nullable(),
  visual_generation_status: z.string(),
  artifacts: z.array(reportArtifactSchema),
  stage_history: z.array(
    z.object({
      stage: z.string(),
      status: z.string(),
      at_utc: z.string(),
      detail: nullableStringSchema,
    }),
  ),
  generated_at_utc: z.string(),
});

export const executeRunRequestSchema = z.object({
  tenant_id: z.string().trim().min(1),
  project_id: z.string().trim().min(1),
  max_steps: z.number().int().positive(),
  human_approval_override: z.enum(["approved", "rejected"]).optional(),
});

export const publishRunRequestSchema = z.object({
  tenant_id: z.string().trim().min(1),
  project_id: z.string().trim().min(1),
});

export const createRunRequestSchema = z.object({
  tenant_id: z.string().trim().min(1),
  project_id: z.string().trim().min(1),
  framework_target: z.array(z.string().trim().min(1)).min(1),
  active_reg_pack_version: z.string().trim().min(1),
  report_blueprint_version: z.string().trim().min(1),
  company_profile_ref: z.string().trim().min(1),
  brand_kit_ref: z.string().trim().min(1),
  connector_scope: z.array(z.string().trim().min(1)).min(1),
  scope_decision: z.object({
    reporting_year: z.string().trim().min(4),
    include_scope3: z.boolean(),
    operation_countries: z.string().trim().min(1),
    sustainability_owner: z.string().trim().min(1),
    board_approver: z.string().trim().min(1),
    approval_sla_days: z.number().int().positive(),
    retrieval_tasks: z.array(
      z.object({
        task_id: z.string(),
        framework: z.string(),
        section_target: z.string(),
        query_text: z.string(),
        retrieval_mode: z.enum(["hybrid", "sparse", "dense"]),
        top_k: z.number().int().positive(),
      }),
    ),
  }),
});

export const createRunResponseSchema = z.object({
  run_id: z.string(),
  report_run_id: z.string(),
});

export type RunListResponse = z.infer<typeof runListResponseSchema>;
export type RunListItem = z.infer<typeof runListItemSchema>;
export type RunPackageStatus = z.infer<typeof runPackageStatusSchema>;
export type RunPublishResponse = z.infer<typeof runPublishResponseSchema>;
export type TriageResponse = z.infer<typeof triageResponseSchema>;
export type ReportArtifact = z.infer<typeof reportArtifactSchema>;
export type ApprovalCenterSearchParams = z.infer<typeof approvalCenterSearchParamsSchema>;
export type CreateRunRequest = z.infer<typeof createRunRequestSchema>;

function shouldPollStatus(status: string | null | undefined): boolean {
  return status === "queued" || status === "running";
}

async function invalidateRunData(
  queryClient: ReturnType<typeof useQueryClient>,
  workspace: WorkspaceContext | null,
  runId?: string | null,
) {
  const tasks: Promise<unknown>[] = [
    queryClient.invalidateQueries({ queryKey: queryKeys.runs.list(workspace) }),
  ];

  if (runId) {
    tasks.push(queryClient.invalidateQueries({ queryKey: queryKeys.runs.packageStatus(workspace, runId) }));
    tasks.push(queryClient.invalidateQueries({ queryKey: queryKeys.runs.triage(workspace, runId) }));
  }

  await Promise.all(tasks);
}

export function parseApprovalCenterSearchParams(
  params: URLSearchParams,
): ApprovalCenterSearchParams {
  return approvalCenterSearchParamsSchema.parse({
    created: params.get("created") ?? undefined,
    mode: params.get("mode") ?? undefined,
    runId: params.get("runId") ?? undefined,
    tenantId: params.get("tenantId") ?? undefined,
    projectId: params.get("projectId") ?? undefined,
  });
}

export async function fetchRuns(
  workspace: WorkspaceContext,
  options: { page?: number; size?: number; signal?: AbortSignal } = {},
): Promise<RunListResponse> {
  const client = createOpenApiClient();
  return parseOpenApiResult(
    await client.GET("/runs", {
      params: {
        query: {
          ...workspaceQueryParams(workspace),
          page: options.page ?? 1,
          size: options.size ?? 50,
        },
      },
      headers: workspaceHeaders({ workspace }),
      signal: options.signal,
    }),
    runListResponseSchema,
  );
}

export async function fetchRunPackageStatus(
  workspace: WorkspaceContext,
  runId: string,
  signal?: AbortSignal,
): Promise<RunPackageStatus> {
  const client = createOpenApiClient();
  return parseOpenApiResult(
    await client.GET("/runs/{run_id}/package-status", {
      params: {
        path: {
          run_id: runId,
        },
        query: workspaceQueryParams(workspace),
      },
      headers: workspaceHeaders({ workspace }),
      signal,
    }),
    runPackageStatusSchema,
  );
}

export async function fetchRunTriage(
  workspace: WorkspaceContext,
  runId: string,
  signal?: AbortSignal,
): Promise<TriageResponse> {
  const client = createOpenApiClient();
  return parseOpenApiResult(
    await client.GET("/runs/{run_id}/triage-report", {
      params: {
        path: {
          run_id: runId,
        },
        query: {
          ...workspaceQueryParams(workspace),
          page: 1,
          size: 20,
        },
      },
      headers: workspaceHeaders({ workspace }),
      signal,
    }),
    triageResponseSchema,
  );
}

export async function executeRun(
  workspace: WorkspaceContext,
  runId: string,
  input: z.infer<typeof executeRunRequestSchema>,
) {
  const client = createOpenApiClient();
  const parsed = executeRunRequestSchema.parse(input);

  return parseOpenApiResult(
    await client.POST("/runs/{run_id}/execute", {
      params: {
        path: {
          run_id: runId,
        },
      },
      headers: workspaceHeaders({ workspace }),
      body: parsed,
    }),
    z.object({}).passthrough(),
  );
}

export async function publishRun(
  workspace: WorkspaceContext,
  runId: string,
  input: z.infer<typeof publishRunRequestSchema>,
) {
  const client = createOpenApiClient();
  const parsed = publishRunRequestSchema.parse(input);

  return parseOpenApiResult(
    await client.POST("/runs/{run_id}/publish", {
      params: {
        path: {
          run_id: runId,
        },
      },
      headers: workspaceHeaders({ workspace, role: "board_member" }),
      body: parsed,
    }),
    runPublishResponseSchema,
  );
}

export async function createRun(input: CreateRunRequest) {
  const client = createOpenApiClient();
  const parsed = createRunRequestSchema.parse(input);

  return parseOpenApiResult(
    await client.POST("/runs", {
      headers: {
        "x-tenant-id": parsed.tenant_id,
        "x-user-id": "web-ui-user",
        "x-user-role": "analyst",
        "Content-Type": "application/json",
      },
      body: parsed,
    }),
    createRunResponseSchema,
  );
}

export async function downloadRunArtifact(
  workspace: WorkspaceContext,
  runId: string,
  artifact: ReportArtifact | null,
  fallbackFilename: string,
  role?: UserRole,
): Promise<string> {
  const path =
    artifact?.download_path ??
    (artifact
      ? buildRunArtifactPath(workspace, runId, artifact.artifact_id)
      : buildRunReportPdfPath(workspace, runId));

  const { blob, filename } = await downloadBlob(path, {
    tenantId: workspace.tenantId,
    role,
    includeJsonContentType: false,
  });

  const resolvedFilename = filename ?? artifact?.filename ?? fallbackFilename;
  triggerBrowserDownload(blob, resolvedFilename);
  return resolvedFilename;
}

export function useRunsQuery(
  workspace: WorkspaceContext | null,
  options: { page?: number; size?: number; pollWhilePending?: boolean } = {},
) {
  return useQuery({
    queryKey: queryKeys.runs.list(workspace),
    queryFn: ({ signal }) => fetchRuns(workspace!, { page: options.page, size: options.size, signal }),
    enabled: Boolean(workspace),
    refetchInterval: options.pollWhilePending
      ? (query) => {
          const data = query.state.data;
          return data?.items.some((item) => shouldPollStatus(item.package_status)) ? 2000 : false;
        }
      : false,
  });
}

export function useRunPackageStatusQuery(
  workspace: WorkspaceContext | null,
  runId: string | null,
  options: { enabled?: boolean; pollWhilePending?: boolean } = {},
) {
  return useQuery({
    queryKey: queryKeys.runs.packageStatus(workspace, runId),
    queryFn: ({ signal }) => fetchRunPackageStatus(workspace!, runId!, signal),
    enabled: Boolean(workspace && runId && (options.enabled ?? true)),
    refetchInterval: options.pollWhilePending
      ? (query) => (shouldPollStatus(query.state.data?.package_status) ? 2000 : false)
      : false,
  });
}

export function useRunTriageQuery(
  workspace: WorkspaceContext | null,
  runId: string | null,
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.runs.triage(workspace, runId),
    queryFn: ({ signal }) => fetchRunTriage(workspace!, runId!, signal),
    enabled: Boolean(workspace && runId && enabled),
  });
}

export function useExecuteRunMutation(workspace: WorkspaceContext | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (variables: {
      runId: string;
      maxSteps: number;
      humanApprovalOverride?: "approved" | "rejected";
    }) => {
      if (!workspace) {
        throw new Error("Workspace is required.");
      }

      return executeRun(workspace, variables.runId, {
        tenant_id: workspace.tenantId,
        project_id: workspace.projectId,
        max_steps: variables.maxSteps,
        human_approval_override: variables.humanApprovalOverride,
      });
    },
    onSuccess: async (_data, variables) => {
      await invalidateRunData(queryClient, workspace, variables.runId);
    },
  });
}

export function usePublishRunMutation(workspace: WorkspaceContext | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (variables: { runId: string }) => {
      if (!workspace) {
        throw new Error("Workspace is required.");
      }

      return publishRun(workspace, variables.runId, {
        tenant_id: workspace.tenantId,
        project_id: workspace.projectId,
      });
    },
    onSuccess: async (_data, variables) => {
      await invalidateRunData(queryClient, workspace, variables.runId);
    },
  });
}
