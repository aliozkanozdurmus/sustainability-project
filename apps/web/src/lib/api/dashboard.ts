import { useQuery } from "@tanstack/react-query";
import { z } from "zod";

import type { WorkspaceContext } from "./client";
import { createOpenApiClient, parseOpenApiResult, workspaceHeaders, workspaceQueryParams } from "./core";
import { queryKeys } from "./query-keys";
import { nullableStringSchema, toneSchema } from "./schema-helpers";

const kpiTrendPointSchema = z.object({
  label: z.string(),
  value: z.number(),
});

const dashboardMetricSchema = z.object({
  key: z.string(),
  label: z.string(),
  display_value: z.string(),
  detail: nullableStringSchema,
  delta_text: nullableStringSchema,
  status: toneSchema,
  trend: z.array(kpiTrendPointSchema),
});

const pipelineLaneSchema = z.object({
  lane_id: z.string(),
  label: z.string(),
  count: z.number(),
  total: z.number(),
  ratio: z.number(),
  status: toneSchema,
  description: z.string(),
});

const connectorHealthSchema = z.object({
  connector_id: z.string(),
  connector_type: z.string(),
  display_name: z.string(),
  status: z.string(),
  auth_mode: z.string(),
  last_synced_at_utc: nullableStringSchema,
  job_status: nullableStringSchema,
  current_stage: nullableStringSchema,
  record_count: z.number(),
  inserted_count: z.number(),
  updated_count: z.number(),
  freshness_hours: z.number().nullable().optional(),
  status_tone: toneSchema,
});

const riskItemSchema = z.object({
  risk_id: z.string(),
  title: z.string(),
  severity: toneSchema,
  count: z.number(),
  detail: z.string(),
});

const scheduleItemSchema = z.object({
  item_id: z.string(),
  title: z.string(),
  subtitle: z.string(),
  slot_label: z.string(),
  status: toneSchema,
  run_id: nullableStringSchema,
});

const artifactHealthSummarySchema = z.object({
  artifact_type: z.string(),
  label: z.string(),
  available: z.number(),
  total_runs: z.number(),
  completion_ratio: z.number(),
});

const activityItemSchema = z.object({
  activity_id: z.string(),
  title: z.string(),
  detail: z.string(),
  category: z.string(),
  status: toneSchema,
  occurred_at_utc: nullableStringSchema,
});

const runQueueItemSchema = z.object({
  run_id: z.string(),
  report_run_status: z.string(),
  active_node: z.string(),
  publish_ready: z.boolean(),
  human_approval: z.string(),
  package_status: z.string(),
  report_quality_score: z.number().nullable().optional(),
  latest_sync_at_utc: nullableStringSchema,
  visual_generation_status: z.string(),
});

export const dashboardOverviewResponseSchema = z.object({
  hero: z.object({
    tenant_name: z.string(),
    company_name: z.string(),
    project_name: z.string(),
    project_code: z.string(),
    sector: nullableStringSchema,
    headquarters: nullableStringSchema,
    reporting_currency: z.string(),
    blueprint_version: nullableStringSchema,
    readiness_label: z.string(),
    readiness_score: z.number(),
    summary: z.string(),
    logo_uri: nullableStringSchema,
    primary_color: nullableStringSchema,
    accent_color: nullableStringSchema,
  }),
  metrics: z.array(dashboardMetricSchema),
  pipeline: z.array(pipelineLaneSchema),
  connector_health: z.array(connectorHealthSchema),
  risks: z.array(riskItemSchema),
  schedule: z.array(scheduleItemSchema),
  artifact_health: z.array(artifactHealthSummarySchema),
  activity_feed: z.array(activityItemSchema),
  run_queue: z.array(runQueueItemSchema),
  generated_at_utc: z.string(),
});

export type DashboardOverviewResponse = z.infer<typeof dashboardOverviewResponseSchema>;
export type DashboardTone = z.infer<typeof toneSchema>;

export async function fetchDashboardOverview(
  workspace: WorkspaceContext,
  signal?: AbortSignal,
): Promise<DashboardOverviewResponse> {
  const client = createOpenApiClient();

  return parseOpenApiResult(
    await client.GET("/dashboard/overview", {
      params: {
        query: workspaceQueryParams(workspace),
      },
      headers: workspaceHeaders({ workspace }),
      signal,
    }),
    dashboardOverviewResponseSchema,
  );
}

export function useDashboardOverviewQuery(workspace: WorkspaceContext | null) {
  return useQuery({
    queryKey: queryKeys.dashboard.overview(workspace),
    queryFn: ({ signal }) => fetchDashboardOverview(workspace!, signal),
    enabled: Boolean(workspace),
  });
}
