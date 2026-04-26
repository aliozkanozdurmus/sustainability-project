import { useMutation } from "@tanstack/react-query";
import { z } from "zod";

import type { WorkspaceContext } from "./client";
import { createOpenApiClient, parseOpenApiResult, workspaceHeaders } from "./core";
import { jsonObjectSchema } from "./schema-helpers";

export const retrievalModeSchema = z.enum(["hybrid", "sparse", "dense"]);

export const retrievalLabFormSchema = z.object({
  queryText: z.string().trim().min(2, "Query must be at least 2 characters."),
  topK: z.string().trim().default("10"),
  retrievalMode: retrievalModeSchema,
  minScore: z.string().trim().default("0"),
  minCoverage: z.string().trim().default("0"),
  period: z.string().trim().default(""),
  keywords: z.string().trim().default(""),
  sectionTags: z.string().trim().default(""),
});

export const retrievalRequestSchema = z.object({
  tenant_id: z.string().trim().min(1),
  project_id: z.string().trim().min(1),
  query_text: z.string().trim().min(2),
  top_k: z.number().int().positive(),
  retrieval_mode: retrievalModeSchema,
  min_score: z.number(),
  min_coverage: z.number(),
  retrieval_hints: z.object({
    period: z.string().trim().nullable(),
    keywords: z.array(z.string()),
    section_tags: z.array(z.string()),
    small_to_big: z.boolean(),
    context_window: z.number().int().nonnegative(),
  }),
});

const rankingBreakdownSchema = z
  .object({
    dense: z.number().nullable().optional(),
    sparse: z.number().nullable().optional(),
    final: z.number().nullable().optional(),
    average_final_score: z.number().nullable().optional(),
    min_final_score: z.number().nullable().optional(),
    max_final_score: z.number().nullable().optional(),
  })
  .passthrough();

const sourceQualitySchema = z
  .object({
    quality_grade: z.string().nullable().optional(),
    quality_score: z.number().nullable().optional(),
    average_quality_score: z.number().nullable().optional(),
    quality_grades: z.array(z.string()).optional(),
    owner: z.string().nullable().optional(),
    period: z.string().nullable().optional(),
    document_type: z.string().nullable().optional(),
    issued_at: z.string().nullable().optional(),
  })
  .passthrough();

const evidenceItemSchema = z.object({
  evidence_id: z.string(),
  source_document_id: z.string(),
  chunk_id: z.string(),
  page: z.number().nullable(),
  text: z.string(),
  score_dense: z.number().nullable(),
  score_sparse: z.number().nullable(),
  score_final: z.number(),
  metadata: jsonObjectSchema,
  matched_terms: z.array(z.string()).default([]),
  ranking_breakdown: rankingBreakdownSchema.default({}),
  source_quality: sourceQualitySchema.default({}),
});

export const retrievalResponseSchema = z.object({
  retrieval_run_id: z.string(),
  evidence: z.array(evidenceItemSchema),
  diagnostics: z.object({
    backend: z.string(),
    retrieval_mode: z.string(),
    top_k: z.number(),
    result_count: z.number(),
    filter_hit_count: z.number(),
    coverage: z.number(),
    coverage_percent: z.number().default(0),
    best_score: z.number(),
    quality_gate_passed: z.boolean(),
    latency_ms: z.number(),
    index_name: z.string(),
    applied_filters: z.record(z.string(), z.string()).default({}),
    matched_terms: z.array(z.string()).default([]),
    ranking_breakdown: rankingBreakdownSchema.default({}),
    source_quality: sourceQualitySchema.default({}),
  }),
});

export type RetrievalResponse = z.infer<typeof retrievalResponseSchema>;
export type RetrievalLabFormInput = z.infer<typeof retrievalLabFormSchema>;

export function buildRetrievalRequest(workspace: WorkspaceContext, input: RetrievalLabFormInput) {
  const parsed = retrievalLabFormSchema.parse(input);

  return retrievalRequestSchema.parse({
    tenant_id: workspace.tenantId,
    project_id: workspace.projectId,
    query_text: parsed.queryText,
    top_k: Number(parsed.topK) || 10,
    retrieval_mode: parsed.retrievalMode,
    min_score: Number(parsed.minScore) || 0,
    min_coverage: Number(parsed.minCoverage) || 0,
    retrieval_hints: {
      period: parsed.period.length > 0 ? parsed.period : null,
      keywords: parsed.keywords
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      section_tags: parsed.sectionTags
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      small_to_big: true,
      context_window: 1,
    },
  });
}

export async function queryRetrieval(
  workspace: WorkspaceContext,
  input: RetrievalLabFormInput,
): Promise<RetrievalResponse> {
  const client = createOpenApiClient();
  const body = buildRetrievalRequest(workspace, input);

  return parseOpenApiResult(
    await client.POST("/retrieval/query", {
      headers: workspaceHeaders({ workspace }),
      body,
    }),
    retrievalResponseSchema,
  );
}

export function useRetrievalQueryMutation(workspace: WorkspaceContext | null) {
  return useMutation({
    mutationFn: (input: RetrievalLabFormInput) => {
      if (!workspace) {
        throw new Error("Workspace not selected. Create/select workspace from New Report first.");
      }

      return queryRetrieval(workspace, input);
    },
  });
}
