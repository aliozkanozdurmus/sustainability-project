import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import type { WorkspaceContext } from "./client";
import { createOpenApiClient, parseOpenApiResult, workspaceHeaders, workspaceQueryParams } from "./core";
import { queryKeys } from "./query-keys";
import { healthBandSchema, nullableStringSchema, supportTierSchema } from "./schema-helpers";

const workspaceContextCompanyProfileSchema = z.object({
  id: z.string(),
  legal_name: z.string(),
  sector: nullableStringSchema,
  headquarters: nullableStringSchema,
  description: nullableStringSchema,
  ceo_name: nullableStringSchema,
  ceo_message: nullableStringSchema,
  sustainability_approach: nullableStringSchema,
  is_configured: z.boolean(),
});

const workspaceContextBrandKitSchema = z.object({
  id: z.string(),
  brand_name: z.string(),
  logo_uri: nullableStringSchema,
  primary_color: z.string(),
  secondary_color: z.string(),
  accent_color: z.string(),
  font_family_headings: z.string(),
  font_family_body: z.string(),
  tone_name: nullableStringSchema,
  is_configured: z.boolean(),
});

export const workspaceIntegrationSummarySchema = z.object({
  id: z.string(),
  connector_type: z.string(),
  display_name: z.string(),
  status: z.string(),
  support_tier: supportTierSchema,
  certified_variant: nullableStringSchema,
  product_version: nullableStringSchema,
  health_band: healthBandSchema,
  assigned_agent_status: nullableStringSchema,
  last_discovered_at: nullableStringSchema,
  last_preflight_at: nullableStringSchema,
  last_preview_sync_at: nullableStringSchema,
  last_synced_at: nullableStringSchema,
});

export const factoryReadinessSchema = z.object({
  is_ready: z.boolean(),
  company_profile_ready: z.boolean(),
  brand_kit_ready: z.boolean(),
  blockers: z.array(
    z.object({
      code: z.string(),
      message: z.string(),
    }),
  ),
});

export const workspaceContextResponseSchema = z.object({
  tenant: z.object({
    id: z.string(),
    name: z.string(),
    slug: z.string(),
    status: z.string(),
  }),
  project: z.object({
    id: z.string(),
    tenant_id: z.string(),
    name: z.string(),
    code: z.string(),
    reporting_currency: z.string(),
    status: z.string(),
  }),
  company_profile: workspaceContextCompanyProfileSchema,
  brand_kit: workspaceContextBrandKitSchema,
  integrations: z.array(workspaceIntegrationSummarySchema),
  blueprint_version: z.string(),
  factory_readiness: factoryReadinessSchema,
});

export const workspaceBootstrapResponseSchema = workspaceContextResponseSchema.extend({
  tenant_created: z.boolean(),
  project_created: z.boolean(),
});

export const workspaceBootstrapRequestSchema = z.object({
  tenantHeader: z.string().trim().min(1),
  tenant_name: z.string().trim().min(2),
  tenant_slug: z.string().trim().min(2),
  project_name: z.string().trim().min(2),
  project_code: z.string().trim().min(2),
  reporting_currency: z.string().trim().min(1),
  company_profile: z.object({
    legal_name: z.string().trim().min(1),
    sector: z.string().trim(),
    headquarters: z.string().trim(),
    description: z.string().trim(),
    ceo_name: z.string().trim(),
    ceo_message: z.string().trim(),
    sustainability_approach: z.string().trim(),
  }),
  brand_kit: z.object({
    brand_name: z.string().trim().min(1),
    logo_uri: z.string().trim(),
    primary_color: z.string().trim().min(1),
    secondary_color: z.string().trim().min(1),
    accent_color: z.string().trim().min(1),
    font_family_headings: z.string().trim().min(1),
    font_family_body: z.string().trim().min(1),
    tone_name: z.string().trim(),
  }),
});

export const integrationSyncRequestSchema = z.object({
  tenant_id: z.string().trim().min(1),
  project_id: z.string().trim().min(1),
  connector_ids: z.array(z.string().trim().min(1)).min(1),
});

export const integrationSyncResponseSchema = z.object({}).passthrough();

export type WorkspaceContextResponse = z.infer<typeof workspaceContextResponseSchema>;
export type WorkspaceBootstrapResponse = z.infer<typeof workspaceBootstrapResponseSchema>;
export type WorkspaceIntegrationSummary = z.infer<typeof workspaceIntegrationSummarySchema>;
export type WorkspaceBootstrapRequest = z.infer<typeof workspaceBootstrapRequestSchema>;
export type IntegrationSyncRequest = z.infer<typeof integrationSyncRequestSchema>;

export async function fetchWorkspaceContext(
  workspace: WorkspaceContext,
  signal?: AbortSignal,
): Promise<WorkspaceContextResponse> {
  const client = createOpenApiClient();
  return parseOpenApiResult(
    await client.GET("/catalog/workspace-context", {
      params: {
        query: workspaceQueryParams(workspace),
      },
      headers: workspaceHeaders({ workspace }),
      signal,
    }),
    workspaceContextResponseSchema,
  );
}

export async function bootstrapWorkspace(
  input: WorkspaceBootstrapRequest,
): Promise<WorkspaceBootstrapResponse> {
  const parsed = workspaceBootstrapRequestSchema.parse(input);
  const client = createOpenApiClient();

  return parseOpenApiResult(
    await client.POST("/catalog/bootstrap-workspace", {
      headers: {
        "x-tenant-id": parsed.tenantHeader,
        "x-user-id": "web-ui-user",
        "x-user-role": "analyst",
        "Content-Type": "application/json",
      },
      body: {
        tenant_name: parsed.tenant_name,
        tenant_slug: parsed.tenant_slug,
        project_name: parsed.project_name,
        project_code: parsed.project_code,
        reporting_currency: parsed.reporting_currency,
        company_profile: parsed.company_profile,
        brand_kit: parsed.brand_kit,
      },
    }),
    workspaceBootstrapResponseSchema,
  );
}

export async function syncIntegrations(
  request: IntegrationSyncRequest,
  signal?: AbortSignal,
) {
  const parsed = integrationSyncRequestSchema.parse(request);
  const client = createOpenApiClient();

  return parseOpenApiResult(
    await client.POST("/integrations/sync", {
      headers: {
        "x-tenant-id": parsed.tenant_id,
        "x-user-id": "web-ui-user",
        "x-user-role": "analyst",
        "Content-Type": "application/json",
      },
      body: parsed,
      signal,
    }),
    integrationSyncResponseSchema,
  );
}

export function useWorkspaceContextQuery(workspace: WorkspaceContext | null) {
  return useQuery({
    queryKey: queryKeys.catalog.workspaceContext(workspace),
    queryFn: ({ signal }) => fetchWorkspaceContext(workspace!, signal),
    enabled: Boolean(workspace),
  });
}

export function useBootstrapWorkspaceMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: bootstrapWorkspace,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["catalog"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["runs"] }),
        queryClient.invalidateQueries({ queryKey: ["integrations"] }),
      ]);
    },
  });
}
