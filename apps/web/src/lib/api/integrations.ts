import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import type { WorkspaceContext } from "./client";
import { createOpenApiClient, parseOpenApiResult, workspaceHeaders, workspaceQueryParams } from "./core";
import { queryKeys } from "./query-keys";
import { healthBandSchema, jsonObjectSchema, nullableStringSchema, supportTierSchema } from "./schema-helpers";
import { fetchWorkspaceContext, workspaceIntegrationSummarySchema } from "./catalog";

export const healthMetricSchema = z.object({
  key: z.string(),
  label: z.string(),
  score: z.number(),
  status: z.string(),
  detail: z.string(),
});

const connectorArtifactSchema = z.object({
  artifact_id: z.string(),
  filename: z.string(),
  download_path: z.string(),
});

export const integrationDetailResponseSchema = z.object({
  id: z.string(),
  connector_type: z.string(),
  display_name: z.string(),
  auth_mode: z.string(),
  base_url: nullableStringSchema,
  resource_path: nullableStringSchema,
  status: z.string(),
  mapping_version: z.string(),
  certified_variant: nullableStringSchema,
  product_version: nullableStringSchema,
  support_tier: supportTierSchema,
  connectivity_mode: z.string(),
  credential_ref: nullableStringSchema,
  health_band: healthBandSchema,
  health_status: z
    .object({
      score: z.number(),
      band: healthBandSchema,
      metrics: z.array(healthMetricSchema),
      operator_message: z.string(),
      support_hint: z.string(),
      recommended_action: z.string(),
      retryable: z.boolean(),
      support_matrix_version: z.string(),
    })
    .nullable(),
  assigned_agent_id: nullableStringSchema,
  normalization_policy: jsonObjectSchema,
  connection_profile: jsonObjectSchema,
});

export const connectorOperationResponseSchema = z.object({
  operation_id: z.string(),
  operation_type: z.enum(["discover", "preflight", "preview_sync", "replay", "support_bundle"]),
  status: z.string(),
  current_stage: z.string(),
  support_tier: supportTierSchema,
  health_band: healthBandSchema,
  operator_message: nullableStringSchema,
  support_hint: nullableStringSchema,
  recommended_action: nullableStringSchema,
  retryable: z.boolean(),
  error_code: nullableStringSchema,
  error_message: nullableStringSchema,
  result: jsonObjectSchema,
  diagnostics: jsonObjectSchema,
  artifact: connectorArtifactSchema.nullable(),
});

export const integrationFormStateSchema = z.object({
  credentialRef: z.string(),
  certifiedVariant: z.string(),
  productVersion: z.string(),
  serviceUrl: z.string(),
  resourcePath: z.string(),
  host: z.string(),
  companyCode: z.string(),
  firmCode: z.string(),
  databaseName: z.string(),
  sqlViewName: z.string(),
  viewSchema: z.string(),
  authMethod: z.string(),
  username: z.string(),
  instanceName: z.string(),
});

export const saveIntegrationProfileInputSchema = z.object({
  tenant_id: z.string().trim().min(1),
  project_id: z.string().trim().min(1),
  connector_type: z.string().trim().min(1),
  display_name: z.string().trim().min(1),
  auth_mode: z.string().trim().min(1),
  base_url: z.string().trim().nullable(),
  resource_path: z.string().trim().nullable(),
  mapping_version: z.string().trim().min(1),
  certified_variant: z.string().trim(),
  product_version: z.string().trim(),
  connectivity_mode: z.string().trim().min(1),
  credential_ref: z.string().trim(),
  assigned_agent_id: z.string().trim().nullable(),
  connection_profile: z.object({
    service_url: z.string().optional(),
    resource_path: z.string().optional(),
    host: z.string().optional(),
    company_code: z.string().optional(),
    firm_code: z.string().optional(),
    database_name: z.string().optional(),
    sql_view_name: z.string().optional(),
    view_schema: z.string().optional(),
    auth_method: z.string().optional(),
    username: z.string().optional(),
    instance_name: z.string().optional(),
  }),
});

export const connectorOperationRequestSchema = z.object({
  tenant_id: z.string().trim().min(1),
  project_id: z.string().trim().min(1),
  limit: z.number().int().positive().optional(),
  mode: z.enum(["resume", "reset_cursor", "backfill_window"]).optional(),
});

export type IntegrationDetailResponse = z.infer<typeof integrationDetailResponseSchema>;
export type ConnectorOperationResponse = z.infer<typeof connectorOperationResponseSchema>;
export type IntegrationFormState = z.infer<typeof integrationFormStateSchema>;
export type WorkspaceIntegrationSummary = z.infer<typeof workspaceIntegrationSummarySchema>;

export const EMPTY_INTEGRATION_FORM: IntegrationFormState = {
  credentialRef: "",
  certifiedVariant: "",
  productVersion: "",
  serviceUrl: "",
  resourcePath: "",
  host: "",
  companyCode: "",
  firmCode: "",
  databaseName: "",
  sqlViewName: "",
  viewSchema: "",
  authMethod: "",
  username: "",
  instanceName: "",
};

export function buildIntegrationFormState(
  detail: IntegrationDetailResponse,
): IntegrationFormState {
  const profile = detail.connection_profile;
  return integrationFormStateSchema.parse({
    credentialRef: detail.credential_ref ?? "",
    certifiedVariant: detail.certified_variant ?? "",
    productVersion: detail.product_version ?? "",
    serviceUrl: String(profile.service_url ?? ""),
    resourcePath: String(profile.resource_path ?? detail.resource_path ?? ""),
    host: String(profile.host ?? ""),
    companyCode: String(profile.company_code ?? ""),
    firmCode: String(profile.firm_code ?? ""),
    databaseName: String(profile.database_name ?? ""),
    sqlViewName: String(profile.sql_view_name ?? ""),
    viewSchema: String(profile.view_schema ?? ""),
    authMethod: String(profile.auth_method ?? detail.auth_mode ?? ""),
    username: String(profile.username ?? ""),
    instanceName: String(profile.instance_name ?? ""),
  });
}

export function buildSaveIntegrationProfileInput(
  workspace: WorkspaceContext,
  detail: IntegrationDetailResponse,
  form: IntegrationFormState,
) {
  return saveIntegrationProfileInputSchema.parse({
    tenant_id: workspace.tenantId,
    project_id: workspace.projectId,
    connector_type: detail.connector_type,
    display_name: detail.display_name,
    auth_mode: detail.auth_mode,
    base_url: detail.base_url ?? null,
    resource_path: detail.resource_path ?? null,
    mapping_version: detail.mapping_version,
    certified_variant: form.certifiedVariant.trim(),
    product_version: form.productVersion.trim(),
    connectivity_mode: detail.connectivity_mode,
    credential_ref: form.credentialRef.trim(),
    assigned_agent_id: detail.assigned_agent_id ?? null,
    connection_profile: {
      service_url: form.serviceUrl.trim() || undefined,
      resource_path: form.resourcePath.trim() || undefined,
      host: form.host.trim() || undefined,
      company_code: form.companyCode.trim() || undefined,
      firm_code: form.firmCode.trim() || undefined,
      database_name: form.databaseName.trim() || undefined,
      sql_view_name: form.sqlViewName.trim() || undefined,
      view_schema: form.viewSchema.trim() || undefined,
      auth_method: form.authMethod.trim() || undefined,
      username: form.username.trim() || undefined,
      instance_name: form.instanceName.trim() || undefined,
    },
  });
}

export async function fetchIntegrationSummaries(
  workspace: WorkspaceContext,
  signal?: AbortSignal,
): Promise<WorkspaceIntegrationSummary[]> {
  const context = await fetchWorkspaceContext(workspace, signal);
  return context.integrations;
}

export async function fetchIntegrationDetail(
  workspace: WorkspaceContext,
  integrationId: string,
  signal?: AbortSignal,
): Promise<IntegrationDetailResponse> {
  const client = createOpenApiClient();

  return parseOpenApiResult(
    await client.GET("/integrations/connectors/{integration_id}", {
      params: {
        path: {
          integration_id: integrationId,
        },
        query: workspaceQueryParams(workspace),
      },
      headers: workspaceHeaders({ workspace }),
      signal,
    }),
    integrationDetailResponseSchema,
  );
}

export async function saveIntegrationProfile(
  input: z.infer<typeof saveIntegrationProfileInputSchema>,
): Promise<IntegrationDetailResponse> {
  const client = createOpenApiClient();
  const parsed = saveIntegrationProfileInputSchema.parse(input);

  return parseOpenApiResult(
    await client.POST("/integrations/connectors", {
      headers: {
        "x-tenant-id": parsed.tenant_id,
        "x-user-id": "web-ui-user",
        "x-user-role": "analyst",
        "Content-Type": "application/json",
      },
      body: parsed,
    }),
    integrationDetailResponseSchema,
  );
}

export async function runConnectorOperation(
  workspace: WorkspaceContext,
  integrationId: string,
  operation:
    | "discover"
    | "preflight"
    | "preview-sync"
    | "replay"
    | "support-bundle",
  input: z.infer<typeof connectorOperationRequestSchema>,
) {
  const client = createOpenApiClient();
  const parsed = connectorOperationRequestSchema.parse(input);

  const params = {
    path: {
      integration_id: integrationId,
    },
  } as const;

  if (operation === "discover") {
    return parseOpenApiResult(
      await client.POST("/integrations/connectors/{integration_id}/discover", {
        params,
        headers: workspaceHeaders({ workspace }),
        body: parsed,
      }),
      connectorOperationResponseSchema,
    );
  }

  if (operation === "preflight") {
    return parseOpenApiResult(
      await client.POST("/integrations/connectors/{integration_id}/preflight", {
        params,
        headers: workspaceHeaders({ workspace }),
        body: parsed,
      }),
      connectorOperationResponseSchema,
    );
  }

  if (operation === "preview-sync") {
    const previewRequest = z
      .object({
        tenant_id: z.string().trim().min(1),
        project_id: z.string().trim().min(1),
        limit: z.number().int().positive(),
      })
      .parse(parsed);

    return parseOpenApiResult(
      await client.POST("/integrations/connectors/{integration_id}/preview-sync", {
        params,
        headers: workspaceHeaders({ workspace }),
        body: previewRequest,
      }),
      connectorOperationResponseSchema,
    );
  }

  if (operation === "replay") {
    const replayRequest = z
      .object({
        tenant_id: z.string().trim().min(1),
        project_id: z.string().trim().min(1),
        mode: z.enum(["resume", "reset_cursor", "backfill_window"]),
      })
      .parse(parsed);

    return parseOpenApiResult(
      await client.POST("/integrations/connectors/{integration_id}/replay", {
        params,
        headers: workspaceHeaders({ workspace }),
        body: replayRequest,
      }),
      connectorOperationResponseSchema,
    );
  }

  return parseOpenApiResult(
    await client.POST("/integrations/connectors/{integration_id}/support-bundle", {
      params,
      headers: workspaceHeaders({ workspace }),
      body: parsed,
    }),
    connectorOperationResponseSchema,
  );
}

export function useIntegrationSummariesQuery(workspace: WorkspaceContext | null) {
  return useQuery({
    queryKey: queryKeys.integrations.summaries(workspace),
    queryFn: ({ signal }) => fetchIntegrationSummaries(workspace!, signal),
    enabled: Boolean(workspace),
  });
}

export function useIntegrationDetailQuery(
  workspace: WorkspaceContext | null,
  integrationId: string | null,
) {
  return useQuery({
    queryKey: queryKeys.integrations.detail(workspace, integrationId),
    queryFn: ({ signal }) => fetchIntegrationDetail(workspace!, integrationId!, signal),
    enabled: Boolean(workspace && integrationId),
  });
}

export function useSaveIntegrationProfileMutation(workspace: WorkspaceContext | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (variables: {
      detail: IntegrationDetailResponse;
      form: IntegrationFormState;
    }) => {
      if (!workspace) {
        throw new Error("Workspace is required.");
      }

      return saveIntegrationProfile(
        buildSaveIntegrationProfileInput(workspace, variables.detail, variables.form),
      );
    },
    onSuccess: async (data) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.integrations.summaries(workspace) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.catalog.workspaceContext(workspace) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.integrations.detail(workspace, data.id) }),
      ]);
    },
  });
}

export function useRunConnectorOperationMutation(workspace: WorkspaceContext | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (variables: {
      integrationId: string;
      operation:
        | "discover"
        | "preflight"
        | "preview-sync"
        | "replay"
        | "support-bundle";
      body?: {
        limit?: number;
        mode?: "resume" | "reset_cursor" | "backfill_window";
      };
    }) => {
      if (!workspace) {
        throw new Error("Workspace is required.");
      }

      return runConnectorOperation(workspace, variables.integrationId, variables.operation, {
        tenant_id: workspace.tenantId,
        project_id: workspace.projectId,
        limit: variables.body?.limit,
        mode: variables.body?.mode,
      });
    },
    onSuccess: async (_data, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.integrations.summaries(workspace) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.catalog.workspaceContext(workspace) }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.integrations.detail(workspace, variables.integrationId),
        }),
      ]);
    },
  });
}
