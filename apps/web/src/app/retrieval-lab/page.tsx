"use client";

import { useEffect, useState } from "react";
import { Loader2, Search } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  buildApiHeaders,
  getApiBaseUrl,
  getInitialWorkspaceContext,
  parseJsonOrThrow,
  persistWorkspaceContext,
  type WorkspaceContext,
} from "@/lib/api/client";

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

function useWorkspace(): WorkspaceContext | null {
  const [workspace] = useState<WorkspaceContext | null>(() => {
    if (typeof window === "undefined") return null;
    return getInitialWorkspaceContext();
  });

  useEffect(() => {
    if (workspace) {
      persistWorkspaceContext(workspace);
    }
  }, [workspace]);

  return workspace;
}

export default function RetrievalLabPage() {
  const workspace = useWorkspace();
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
      title="Retrieval Lab"
      subtitle="Run hybrid retrieval against indexed evidence and inspect diagnostics."
      actions={[
        { href: "/evidence-center", label: "Open Evidence Center" },
        { href: "/approval-center", label: "Open Approval Center" },
      ]}
    >
      {!workspace ? (
        <div className="mb-4 rounded-xl border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
          Workspace not selected. Configure tenant/project from New Report Wizard first.
        </div>
      ) : (
        <div className="mb-4 rounded-xl border bg-card px-4 py-3 text-xs text-muted-foreground">
          tenant_id={workspace.tenantId} | project_id={workspace.projectId}
        </div>
      )}

      {error ? (
        <div className="mb-4 rounded-xl border border-destructive/35 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <section className="rounded-xl border bg-card p-5 shadow-sm">
        <h2 className="mb-3 text-lg font-semibold">Query Controls</h2>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <label className="space-y-1 text-sm md:col-span-2 xl:col-span-4">
            <span className="text-muted-foreground">Query</span>
            <input
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={queryText}
              onChange={(event) => setQueryText(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Top K</span>
            <input
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={topK}
              onChange={(event) => setTopK(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Mode</span>
            <select
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={retrievalMode}
              onChange={(event) => setRetrievalMode(event.target.value as "hybrid" | "sparse" | "dense")}
            >
              <option value="hybrid">hybrid</option>
              <option value="sparse">sparse</option>
              <option value="dense">dense</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Min Score</span>
            <input
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={minScore}
              onChange={(event) => setMinScore(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Min Coverage</span>
            <input
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={minCoverage}
              onChange={(event) => setMinCoverage(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Period Hint</span>
            <input
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={period}
              onChange={(event) => setPeriod(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm md:col-span-2">
            <span className="text-muted-foreground">Keywords (comma separated)</span>
            <input
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={keywords}
              onChange={(event) => setKeywords(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm md:col-span-2">
            <span className="text-muted-foreground">Section Tags (comma separated)</span>
            <input
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={sectionTags}
              onChange={(event) => setSectionTags(event.target.value)}
            />
          </label>
        </div>
        <div className="mt-3">
          <Button type="button" onClick={() => void handleQuery()} disabled={busy || !workspace}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            Run Retrieval
          </Button>
        </div>
      </section>

      <section className="mt-4 grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <article className="rounded-xl border bg-card p-4 shadow-sm">
          <h3 className="mb-2 text-sm font-semibold">Diagnostics</h3>
          <pre className="max-h-[28rem] overflow-auto rounded-md bg-muted/45 p-3 text-xs">
            {response ? JSON.stringify(response.diagnostics, null, 2) : "{}"}
          </pre>
        </article>
        <article className="rounded-xl border bg-card p-4 shadow-sm">
          <h3 className="mb-2 text-sm font-semibold">Evidence Results</h3>
          <div className="space-y-3">
            {response?.evidence.map((item) => (
              <div key={item.evidence_id} className="rounded-lg border bg-muted/30 p-3">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>evidence_id={item.evidence_id}</span>
                  <span>doc={item.source_document_id}</span>
                  <span>chunk={item.chunk_id}</span>
                  <span>score={item.score_final.toFixed(4)}</span>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm">{item.text}</p>
              </div>
            ))}
            {!response || response.evidence.length === 0 ? (
              <p className="text-sm text-muted-foreground">No evidence returned yet.</p>
            ) : null}
          </div>
        </article>
      </section>
    </AppShell>
  );
}
