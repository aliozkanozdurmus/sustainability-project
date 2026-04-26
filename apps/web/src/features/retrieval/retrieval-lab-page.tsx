"use client";

import { useMemo, useState } from "react";
import { ArrowRightLeft, CheckCircle2, Loader2, Search, Sparkles } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  fieldClassName,
  FormField,
  MetricPill,
  SectionHeading,
  StatChip,
  SubtleAlert,
  SurfaceCard,
} from "@/components/workbench-ui";
import { retrievalModeSchema, useRetrievalQueryMutation } from "@/lib/api/retrieval";
import { useWorkspaceContext } from "@/lib/api/workspace-store";

const QUERY_PRESETS = [
  {
    label: "Scope 2 YoY",
    queryText: "Scope 2 emissions year-over-year change",
    keywords: "scope 2,electricity,emissions",
    sectionTags: "TSRS2,CSRD",
    period: "2025",
  },
  {
    label: "Supplier Risk",
    queryText: "high risk supplier screening coverage",
    keywords: "supplier,screening,high risk,due diligence",
    sectionTags: "CSRD,Social",
    period: "2025",
  },
  {
    label: "Governance",
    queryText: "board oversight sustainability committee meetings",
    keywords: "board,committee,governance,oversight",
    sectionTags: "TSRS1,GOVERNANCE",
    period: "2025",
  },
];

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "0%";
  }
  return `${new Intl.NumberFormat("tr-TR", {
    maximumFractionDigits: value >= 10 ? 0 : 2,
  }).format(value)}%`;
}

function formatRatio(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "0.00";
  }
  return value.toFixed(2);
}

function highlightTerms(text: string, terms: string[]) {
  const cleanedTerms = terms
    .map((term) => term.trim())
    .filter(Boolean)
    .sort((left, right) => right.length - left.length);
  if (cleanedTerms.length === 0) {
    return text;
  }

  const pattern = new RegExp(
    `(${cleanedTerms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "gi",
  );
  const parts = text.split(pattern);
  return parts.map((part, index) => {
    const matched = cleanedTerms.some((term) => term.toLowerCase() === part.toLowerCase());
    if (!matched) {
      return <span key={`${part}-${index}`}>{part}</span>;
    }
    return (
      <mark
        key={`${part}-${index}`}
        className="rounded bg-[rgba(45,109,83,0.14)] px-1 py-0.5 text-[color:var(--accent-strong)]"
      >
        {part}
      </mark>
    );
  });
}

export default function RetrievalLabPage() {
  const workspace = useWorkspaceContext();
  const [error, setError] = useState<string | null>(null);
  const [queryText, setQueryText] = useState("Scope 2 emissions year-over-year change");
  const [topK, setTopK] = useState("10");
  const [retrievalMode, setRetrievalMode] = useState<"hybrid" | "sparse" | "dense">("hybrid");
  const [minScore, setMinScore] = useState("0");
  const [minCoverage, setMinCoverage] = useState("0");
  const [period, setPeriod] = useState("2025");
  const [keywords, setKeywords] = useState("scope 2,electricity,emissions");
  const [sectionTags, setSectionTags] = useState("TSRS2,CSRD");
  const [comparisonIds, setComparisonIds] = useState<string[]>([]);
  const retrievalMutation = useRetrievalQueryMutation(workspace);
  const busy = retrievalMutation.isPending;
  const response = retrievalMutation.data ?? null;
  const displayError =
    error ?? (retrievalMutation.error instanceof Error ? retrievalMutation.error.message : null);

  const comparisonItems = useMemo(
    () =>
      response?.evidence.filter((item) => comparisonIds.includes(item.evidence_id)).slice(0, 2) ??
      [],
    [comparisonIds, response],
  );

  async function handleQuery() {
    if (!workspace) {
      setError("Workspace not selected. Create/select workspace from New Report first.");
      return;
    }
    if (queryText.trim().length < 2) {
      setError("Query must be at least 2 characters.");
      return;
    }

    setError(null);
    try {
      await retrievalMutation.mutateAsync({
        queryText,
        topK,
        retrievalMode,
        minScore,
        minCoverage,
        period,
        keywords,
        sectionTags,
      });
      setComparisonIds([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retrieval query failed.");
    }
  }

  function applyPreset(preset: (typeof QUERY_PRESETS)[number]) {
    setQueryText(preset.queryText);
    setKeywords(preset.keywords);
    setSectionTags(preset.sectionTags);
    setPeriod(preset.period);
  }

  function toggleComparison(evidenceId: string) {
    setComparisonIds((current) => {
      if (current.includes(evidenceId)) {
        return current.filter((item) => item !== evidenceId);
      }
      return [...current, evidenceId].slice(-2);
    });
  }

  return (
    <AppShell
      activePath="/retrieval-lab"
      title="Retrieval Command Center"
      subtitle="Triage evidence quality, compare provenance, and inspect score drivers before claims move downstream."
      actions={[
        { href: "/evidence-center", label: "Open Evidence Center" },
        { href: "/approval-center", label: "Open Publish Board" },
      ]}
    >
      {!workspace ? (
        <SubtleAlert tone="attention" title="Workspace required">
          Open New Report Run first so the lab can apply tenant and project isolation correctly.
        </SubtleAlert>
      ) : (
        <div className="flex flex-wrap gap-2">
          <StatChip label="tenant" value={workspace.tenantId} />
          <StatChip label="project" value={workspace.projectId} />
          <StatChip label="mode" value={retrievalMode} />
          <StatChip
            label="coverage"
            value={response ? formatPercent(response.diagnostics.coverage_percent) : "pending"}
          />
        </div>
      )}

      {displayError ? (
        <SubtleAlert tone="critical" title="Retrieval issue" data-testid="retrieval-error">
          {displayError}
        </SubtleAlert>
      ) : null}

      <div className="dense-grid grid xl:grid-cols-[1.04fr_0.96fr]">
        <SurfaceCard className="px-5 py-5">
          <SectionHeading
            eyebrow="Query composer"
            title="Operator query presets and controls"
            description="Start from common ESG investigations, then tighten thresholds and hints before dispatch."
          />

          <div className="mt-4 flex flex-wrap gap-2">
            {QUERY_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => applyPreset(preset)}
                className="inline-flex rounded-full border border-[color:var(--border)] bg-white/76 px-3 py-1.5 text-xs font-semibold text-[color:var(--foreground-soft)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent-strong)]"
              >
                <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                {preset.label}
              </button>
            ))}
          </div>

          <div className="dense-grid mt-4 grid md:grid-cols-2 xl:grid-cols-4">
            <FormField label="Query" className="md:col-span-2 xl:col-span-4">
              <input
                className={fieldClassName()}
                value={queryText}
                onChange={(event) => setQueryText(event.target.value)}
              />
            </FormField>
            <FormField label="Top K">
              <input
                className={fieldClassName()}
                value={topK}
                onChange={(event) => setTopK(event.target.value)}
              />
            </FormField>
            <FormField label="Mode">
              <select
                className={fieldClassName()}
                value={retrievalMode}
                onChange={(event) =>
                  setRetrievalMode(retrievalModeSchema.parse(event.target.value))
                }
              >
                <option value="hybrid">hybrid</option>
                <option value="sparse">sparse</option>
                <option value="dense">dense</option>
              </select>
            </FormField>
            <FormField label="Min Score">
              <input
                className={fieldClassName()}
                value={minScore}
                onChange={(event) => setMinScore(event.target.value)}
              />
            </FormField>
            <FormField label="Min Coverage">
              <input
                className={fieldClassName()}
                value={minCoverage}
                onChange={(event) => setMinCoverage(event.target.value)}
              />
            </FormField>
            <FormField label="Period Hint">
              <input
                className={fieldClassName()}
                value={period}
                onChange={(event) => setPeriod(event.target.value)}
              />
            </FormField>
            <FormField label="Keywords" hint="comma separated" className="md:col-span-2">
              <input
                className={fieldClassName()}
                value={keywords}
                onChange={(event) => setKeywords(event.target.value)}
              />
            </FormField>
            <FormField label="Section Tags" hint="comma separated" className="md:col-span-2">
              <input
                className={fieldClassName()}
                value={sectionTags}
                onChange={(event) => setSectionTags(event.target.value)}
              />
            </FormField>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button
              type="button"
              onClick={() => void handleQuery()}
              disabled={busy || !workspace}
              data-testid="retrieval-submit-button"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Run Retrieval
            </Button>
            <p className="text-xs text-[color:var(--foreground-soft)]">
              Compare up to two evidence blocks to inspect provenance side by side.
            </p>
          </div>
        </SurfaceCard>

        <SurfaceCard className="px-5 py-5">
          <SectionHeading
            eyebrow="Diagnostics"
            title="Coverage, ranking, and source quality"
            description="Use both ratio and percent so threshold decisions stay operationally clear."
          />
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <MetricPill
              label="results"
              value={response?.diagnostics.result_count ?? 0}
              detail="Evidence blocks returned."
              tone={response?.diagnostics.result_count ? "good" : "neutral"}
            />
            <MetricPill
              label="best score"
              value={response ? response.diagnostics.best_score.toFixed(3) : "0.000"}
              detail="Highest final score from the latest response."
              tone={
                response?.diagnostics.best_score && response.diagnostics.best_score >= 0.7
                  ? "good"
                  : "attention"
              }
            />
            <MetricPill
              label="coverage %"
              value={response ? formatPercent(response.diagnostics.coverage_percent) : "0%"}
              detail={`Coverage ratio ${response ? formatRatio(response.diagnostics.coverage) : "0.00"}`}
              tone={
                response?.diagnostics.coverage_percent &&
                response.diagnostics.coverage_percent >= 70
                  ? "good"
                  : "attention"
              }
            />
            <MetricPill
              label="latency"
              value={response ? `${response.diagnostics.latency_ms} ms` : "pending"}
              detail="Backend retrieval latency."
              tone="neutral"
            />
          </div>

          <div className="mt-4 rounded-[1.35rem] border border-[color:var(--border)] bg-white/64 p-4">
            <p className="text-[11px] font-semibold tracking-[0.14em] text-[color:var(--foreground-muted)] uppercase">
              Matched terms
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {response?.diagnostics.matched_terms.length ? (
                response.diagnostics.matched_terms.map((term) => (
                  <span
                    key={term}
                    className="rounded-full bg-[rgba(45,109,83,0.1)] px-2.5 py-1 text-[11px] font-medium text-[color:var(--accent-strong)]"
                  >
                    {term}
                  </span>
                ))
              ) : (
                <span className="text-xs text-[color:var(--foreground-soft)]">
                  No matched terms yet.
                </span>
              )}
            </div>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-[1.25rem] border border-[color:var(--border)] bg-white/64 p-4">
              <p className="text-[11px] font-semibold tracking-[0.14em] text-[color:var(--foreground-muted)] uppercase">
                Ranking breakdown
              </p>
              <p className="text-foreground mt-2 text-sm">
                avg {String(response?.diagnostics.ranking_breakdown.average_final_score ?? "0.000")}
              </p>
              <p className="mt-1 text-xs text-[color:var(--foreground-soft)]">
                min {String(response?.diagnostics.ranking_breakdown.min_final_score ?? "0.000")} •
                max {String(response?.diagnostics.ranking_breakdown.max_final_score ?? "0.000")}
              </p>
            </div>
            <div className="rounded-[1.25rem] border border-[color:var(--border)] bg-white/64 p-4">
              <p className="text-[11px] font-semibold tracking-[0.14em] text-[color:var(--foreground-muted)] uppercase">
                Source quality
              </p>
              <p className="text-foreground mt-2 text-sm">
                avg {response?.diagnostics.source_quality.average_quality_score ?? "-"}
              </p>
              <p className="mt-1 text-xs text-[color:var(--foreground-soft)]">
                grades{" "}
                {(
                  response?.diagnostics.source_quality.quality_grades as string[] | undefined
                )?.join(", ") || "-"}
              </p>
            </div>
          </div>
        </SurfaceCard>
      </div>

      <div className="dense-grid grid xl:grid-cols-[1.14fr_0.86fr]">
        <SurfaceCard className="px-5 py-5">
          <SectionHeading
            eyebrow="Evidence table"
            title="Ranked evidence with provenance chips"
            description="Review score drivers, matched terms, and source quality before downstream drafting."
          />
          <div className="mt-4 space-y-3" data-testid="retrieval-results">
            {response?.evidence.map((item) => {
              const selected = comparisonIds.includes(item.evidence_id);
              return (
                <div
                  key={item.evidence_id}
                  className="rounded-[1.35rem] border border-[color:var(--border)] bg-white/62 p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 text-[11px] text-[color:var(--foreground-soft)]">
                        <span>{item.source_document_id}</span>
                        <span>chunk {item.chunk_id}</span>
                        <span>page {item.page ?? "-"}</span>
                        <span>{String(item.source_quality.quality_grade ?? "grade n/a")}</span>
                        <span>score {item.score_final.toFixed(4)}</span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {item.matched_terms.map((term) => (
                          <span
                            key={`${item.evidence_id}-${term}`}
                            className="rounded-full bg-[rgba(29,27,25,0.06)] px-2 py-0.5 text-[11px] text-[color:var(--foreground-soft)]"
                          >
                            {term}
                          </span>
                        ))}
                      </div>
                    </div>
                    <Button
                      type="button"
                      variant={selected ? "default" : "outline"}
                      onClick={() => toggleComparison(item.evidence_id)}
                    >
                      <ArrowRightLeft className="h-4 w-4" />
                      {selected ? "Selected" : "Compare"}
                    </Button>
                  </div>
                  <p className="text-foreground mt-3 text-sm leading-6 whitespace-pre-wrap">
                    {highlightTerms(item.text, item.matched_terms)}
                  </p>
                  <div className="mt-4 grid gap-2 sm:grid-cols-3">
                    <div className="rounded-[1rem] bg-[color:var(--surface)] px-3 py-2 text-xs text-[color:var(--foreground-soft)]">
                      sparse {String(item.ranking_breakdown.sparse ?? "-")}
                    </div>
                    <div className="rounded-[1rem] bg-[color:var(--surface)] px-3 py-2 text-xs text-[color:var(--foreground-soft)]">
                      dense {String(item.ranking_breakdown.dense ?? "-")}
                    </div>
                    <div className="rounded-[1rem] bg-[color:var(--surface)] px-3 py-2 text-xs text-[color:var(--foreground-soft)]">
                      owner {String(item.source_quality.owner ?? "-")}
                    </div>
                  </div>
                </div>
              );
            })}
            {!response || response.evidence.length === 0 ? (
              <EmptyState
                title="No evidence returned yet"
                description="Run a retrieval query to populate the ranked evidence stream."
              />
            ) : null}
          </div>
        </SurfaceCard>

        <SurfaceCard className="px-5 py-5">
          <SectionHeading
            eyebrow="Compare"
            title="Side-by-side evidence review"
            description="Select up to two rows to compare wording, provenance, and ranking context."
          />
          {comparisonItems.length === 2 ? (
            <div className="mt-4 grid gap-3">
              {comparisonItems.map((item) => (
                <div
                  key={`compare-${item.evidence_id}`}
                  className="rounded-[1.25rem] border border-[color:var(--border)] bg-white/64 p-4"
                >
                  <div className="flex items-center gap-2 text-[11px] text-[color:var(--foreground-soft)]">
                    <CheckCircle2 className="h-4 w-4 text-[color:var(--accent)]" />
                    {item.source_document_id} • chunk {item.chunk_id}
                  </div>
                  <p className="text-foreground mt-3 text-sm leading-6 whitespace-pre-wrap">
                    {highlightTerms(item.text, item.matched_terms)}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Select two evidence blocks"
              description="Use Compare on two ranked items to open a side-by-side provenance check."
            />
          )}

          <div className="mt-5 rounded-[1.35rem] border border-[color:var(--border)] bg-white/58 p-4">
            <p className="text-[11px] font-semibold tracking-[0.14em] text-[color:var(--foreground-muted)] uppercase">
              Raw diagnostics
            </p>
            <pre className="bg-muted/45 mt-3 max-h-[18rem] overflow-auto rounded-md p-3 text-xs">
              {response ? JSON.stringify(response.diagnostics, null, 2) : "{}"}
            </pre>
          </div>
        </SurfaceCard>
      </div>
    </AppShell>
  );
}
