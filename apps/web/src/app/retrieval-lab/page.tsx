"use client";

// Bu sayfa, retrieval-lab ekraninin ana deneyimini kurar.

import { useState } from "react";
import { Loader2, Search } from "lucide-react";

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
import {
  buildApiHeaders,
  getApiBaseUrl,
  parseJsonOrThrow,
} from "@/lib/api/client";
import { useWorkspaceContext } from "@/lib/api/workspace-store";

type EvidenceItem = {
  evidence_id: string;
  source_document_id: string;
  chunk_id: string;
  page: number | null;
  text: string;
  score_dense: number | null;
  score_sparse: number | null;
  score_final: number;
  metadata: Record<string, unknown>;
};

type RetrievalResponse = {
  retrieval_run_id: string;
  evidence: EvidenceItem[];
  diagnostics: {
    backend: string;
    retrieval_mode: string;
    top_k: number;
    result_count: number;
    filter_hit_count: number;
    coverage: number;
    best_score: number;
    quality_gate_passed: boolean;
    latency_ms: number;
    index_name: string;
    applied_filters: Record<string, string>;
  };
};

export default function RetrievalLabPage() {
  const workspace = useWorkspaceContext();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [queryText, setQueryText] = useState("Scope 2 emissions year-over-year change");
  const [topK, setTopK] = useState("10");
  const [retrievalMode, setRetrievalMode] = useState<"hybrid" | "sparse" | "dense">("hybrid");
  const [minScore, setMinScore] = useState("0");
  const [minCoverage, setMinCoverage] = useState("0");
  const [period, setPeriod] = useState("2025");
  const [keywords, setKeywords] = useState("scope 2,electricity,emissions");
  const [sectionTags, setSectionTags] = useState("TSRS2,CSRD");
  const [response, setResponse] = useState<RetrievalResponse | null>(null);

  async function handleQuery() {
    if (!workspace) {
      setError("Workspace not selected. Create/select workspace from New Report first.");
      return;
    }
    if (queryText.trim().length < 2) {
      setError("Query must be at least 2 characters.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const result = await fetch(`${getApiBaseUrl()}/retrieval/query`, {
        method: "POST",
        headers: buildApiHeaders(workspace.tenantId),
        body: JSON.stringify({
          tenant_id: workspace.tenantId,
          project_id: workspace.projectId,
          query_text: queryText.trim(),
          top_k: Number(topK) || 10,
          retrieval_mode: retrievalMode,
          min_score: Number(minScore) || 0,
          min_coverage: Number(minCoverage) || 0,
          retrieval_hints: {
            period: period.trim() || null,
            keywords: keywords
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
            section_tags: sectionTags
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
            small_to_big: true,
            context_window: 1,
          },
        }),
      });
      const payload = await parseJsonOrThrow<RetrievalResponse>(result);
      setResponse(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retrieval query failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell
      activePath="/retrieval-lab"
      title="Retrieval Research Bench"
      subtitle="Compose retrieval queries, inspect diagnostics, and review ranked evidence without leaving the premium workbench."
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
        </div>
      )}

      {error ? (
        <SubtleAlert tone="critical" title="Retrieval issue">
          {error}
        </SubtleAlert>
      ) : null}

      <div className="grid dense-grid xl:grid-cols-[1.05fr_0.95fr]">
        <SurfaceCard className="px-5 py-5">
          <SectionHeading
            eyebrow="Query composer"
            title="Build a filtered retrieval request"
            description="Tune scoring thresholds, disclosure filters, and hint packs before dispatching a hybrid, sparse, or dense query."
          />
          <div className="mt-4 grid dense-grid md:grid-cols-2 xl:grid-cols-4">
            <FormField label="Query" className="md:col-span-2 xl:col-span-4">
              <input className={fieldClassName()} value={queryText} onChange={(event) => setQueryText(event.target.value)} />
            </FormField>
            <FormField label="Top K">
              <input className={fieldClassName()} value={topK} onChange={(event) => setTopK(event.target.value)} />
            </FormField>
            <FormField label="Mode">
              <select className={fieldClassName()} value={retrievalMode} onChange={(event) => setRetrievalMode(event.target.value as "hybrid" | "sparse" | "dense")}>
                <option value="hybrid">hybrid</option>
                <option value="sparse">sparse</option>
                <option value="dense">dense</option>
              </select>
            </FormField>
            <FormField label="Min Score">
              <input className={fieldClassName()} value={minScore} onChange={(event) => setMinScore(event.target.value)} />
            </FormField>
            <FormField label="Min Coverage">
              <input className={fieldClassName()} value={minCoverage} onChange={(event) => setMinCoverage(event.target.value)} />
            </FormField>
            <FormField label="Period Hint">
              <input className={fieldClassName()} value={period} onChange={(event) => setPeriod(event.target.value)} />
            </FormField>
            <FormField label="Keywords" hint="comma separated" className="md:col-span-2">
              <input className={fieldClassName()} value={keywords} onChange={(event) => setKeywords(event.target.value)} />
            </FormField>
            <FormField label="Section Tags" hint="comma separated" className="md:col-span-2">
              <input className={fieldClassName()} value={sectionTags} onChange={(event) => setSectionTags(event.target.value)} />
            </FormField>
          </div>
          <div className="mt-4">
            <Button type="button" onClick={() => void handleQuery()} disabled={busy || !workspace}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Run Retrieval
            </Button>
          </div>
        </SurfaceCard>

        <SurfaceCard className="px-5 py-5">
          <SectionHeading
            eyebrow="Diagnostics"
            title="Result health"
            description="Live quality signals from the latest retrieval response."
          />
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <MetricPill label="results" value={response?.diagnostics.result_count ?? 0} detail="Number of evidence blocks returned." tone={response?.diagnostics.result_count ? "good" : "neutral"} />
            <MetricPill label="best score" value={response ? response.diagnostics.best_score.toFixed(3) : "0.000"} detail="Highest final score from the latest response." tone={response?.diagnostics.best_score && response.diagnostics.best_score >= 0.7 ? "good" : "attention"} />
            <MetricPill label="coverage" value={response ? `${response.diagnostics.coverage}%` : "0%"} detail="Coverage figure reported by retrieval diagnostics." tone={response?.diagnostics.coverage && response.diagnostics.coverage >= 70 ? "good" : "attention"} />
            <MetricPill label="latency" value={response ? `${response.diagnostics.latency_ms} ms` : "pending"} detail="Backend retrieval latency." tone="neutral" />
          </div>
        </SurfaceCard>
      </div>

      <div className="grid dense-grid xl:grid-cols-[0.9fr_1.1fr]">
        <SurfaceCard className="px-5 py-5">
          <SectionHeading
            eyebrow="Raw diagnostics"
            title="Provider and scoring ledger"
            description="Use the raw payload for debugging thresholds, filters, and index selection."
          />
          <div className="mt-4 rounded-[1.35rem] border border-[color:var(--border)] bg-white/58 p-4">
            <pre className="max-h-[28rem] overflow-auto rounded-md bg-muted/45 p-3 text-xs">{response ? JSON.stringify(response.diagnostics, null, 2) : "{}"}</pre>
          </div>
        </SurfaceCard>

        <SurfaceCard className="px-5 py-5">
          <SectionHeading
            eyebrow="Evidence stream"
            title="Ranked evidence results"
            description="Inspect the ranked chunks, document provenance, and final scoring output."
          />
          <div className="mt-4 space-y-3">
            {response?.evidence.map((item) => (
              <div key={item.evidence_id} className="rounded-[1.35rem] border border-[color:var(--border)] bg-white/58 p-4">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>evidence_id={item.evidence_id}</span>
                  <span>doc={item.source_document_id}</span>
                  <span>chunk={item.chunk_id}</span>
                  <span>score={item.score_final.toFixed(4)}</span>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-foreground">{item.text}</p>
              </div>
            ))}
            {!response || response.evidence.length === 0 ? (
              <EmptyState title="No evidence returned yet" description="Run a retrieval query to populate the ranked evidence stream." />
            ) : null}
          </div>
        </SurfaceCard>
      </div>
    </AppShell>
  );
}
