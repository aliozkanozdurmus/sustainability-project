"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import {
  AlertOctagon,
  CheckCircle2,
  Clock3,
  Download,
  Loader2,
  PlayCircle,
  RefreshCw,
  Send,
  Users,
} from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  buildApiHeaders,
  buildRunReportPdfPath,
  getResponseErrorMessage,
  getApiBaseUrl,
  getInitialWorkspaceContext,
  parseJsonOrThrow,
  persistWorkspaceContext,
  type WorkspaceContext,
} from "@/lib/api/client";

type ReportArtifact = {
  artifact_id: string;
  artifact_type: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  checksum: string;
  created_at_utc: string;
  download_path: string;
};

type RunListItem = {
  run_id: string;
  report_run_status: string;
  publish_ready: boolean;
  started_at_utc: string | null;
  completed_at_utc: string | null;
  active_node: string;
  human_approval: string;
  triage_required: boolean;
  last_checkpoint_status: string;
  last_checkpoint_at_utc: string | null;
  report_pdf: ReportArtifact | null;
};

type RunListResponse = {
  total: number;
  page: number;
  size: number;
  items: RunListItem[];
};

type TriageItem = {
  section_code: string;
  claim_id: string;
  status: "FAIL" | "UNSURE";
  severity: string;
  reason: string;
  confidence?: number;
  evidence_refs: string[];
};

type TriageResponse = {
  run_id: string;
  fail_count: number;
  unsure_count: number;
  critical_fail_count: number;
  total_items: number;
  items: TriageItem[];
};

type RunPublishResponse = {
  report_pdf: ReportArtifact | null;
};

function formatUiErrorMessage(rawMessage: string): string {
  const trimmed = rawMessage.trim();
  if (!trimmed) {
    return rawMessage;
  }
  try {
    const parsed = JSON.parse(trimmed) as {
      blockers?: Array<{ code?: string; message?: string }>;
      reason?: string;
    };
    if (Array.isArray(parsed.blockers) && parsed.blockers.length > 0) {
      const blockerSummary = parsed.blockers
        .map((blocker) => {
          const code = blocker.code?.trim();
          const message = blocker.message?.trim();
          if (code && message) {
            return `${code}: ${message}`;
          }
          return code || message || null;
        })
        .filter((value): value is string => Boolean(value))
        .join(" | ");
      if (blockerSummary) {
        return `Publish blocked. ${blockerSummary}`;
      }
    }
    if (typeof parsed.reason === "string" && parsed.reason.trim().length > 0) {
      return parsed.reason;
    }
  } catch {
    return rawMessage;
  }
  return rawMessage;
}

function toUiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) {
    return formatUiErrorMessage(error.message);
  }
  return fallback;
}

function readInitialWorkspace(): WorkspaceContext | null {
  if (typeof window === "undefined") return null;
  return getInitialWorkspaceContext();
}

function useWorkspaceFromQueryAndStorage(): WorkspaceContext | null {
  const params = useSearchParams();
  const [storedWorkspace] = useState<WorkspaceContext | null>(() => readInitialWorkspace());

  const queryTenant = params.get("tenantId");
  const queryProject = params.get("projectId");

  const workspace = useMemo(() => {
    if (queryTenant && queryProject) {
      return { tenantId: queryTenant, projectId: queryProject };
    }
    return storedWorkspace;
  }, [queryProject, queryTenant, storedWorkspace]);

  useEffect(() => {
    if (workspace) {
      persistWorkspaceContext(workspace);
    }
  }, [workspace]);

  return workspace;
}

function ApprovalCenterFallback() {
  return (
    <AppShell
      activePath="/approval-center"
      title="Approval Center and SLA Control"
      subtitle="Loading approval data..."
      actions={[{ href: "/reports/new", label: "New Report Wizard" }]}
    >
      <div className="rounded-xl border bg-card px-4 py-6 text-sm text-muted-foreground">
        Loading approval center...
      </div>
    </AppShell>
  );
}

function ApprovalCenterPageContent() {
  const params = useSearchParams();
  const workspace = useWorkspaceFromQueryAndStorage();
  const created = params.get("created") === "1";
  const mode = params.get("mode");
  const createdRunId = params.get("runId");

  const [busyRunId, setBusyRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [runsBusy, setRunsBusy] = useState(false);
  const [triage, setTriage] = useState<TriageResponse | null>(null);

  const runStats = useMemo(() => {
    const pending = runs.filter((row) => row.report_run_status !== "published").length;
    const slaRisk = runs.filter((row) => row.triage_required).length;
    const approverPool = runs.filter((row) => row.human_approval === "pending").length;
    return {
      pending,
      slaRisk,
      approverPool,
    };
  }, [runs]);

  const loadRuns = useCallback(async () => {
    if (!workspace) return;
    setRunsBusy(true);
    setError(null);
    try {
      const apiBase = getApiBaseUrl();
      const response = await fetch(
        `${apiBase}/runs?tenant_id=${encodeURIComponent(workspace.tenantId)}&project_id=${encodeURIComponent(workspace.projectId)}&page=1&size=50`,
        {
          headers: buildApiHeaders(workspace.tenantId),
        },
      );
      const payload = await parseJsonOrThrow<RunListResponse>(response);
      setRuns(payload.items);
    } catch (err) {
      setError(toUiErrorMessage(err, "Failed to load runs."));
    } finally {
      setRunsBusy(false);
    }
  }, [workspace]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  async function handleExecute(runId: string) {
    if (!workspace) return;
    setBusyRunId(runId);
    setError(null);
    setNotice(null);
    try {
      const apiBase = getApiBaseUrl();
      const response = await fetch(`${apiBase}/runs/${runId}/execute`, {
        method: "POST",
        headers: buildApiHeaders(workspace.tenantId),
        body: JSON.stringify({
          tenant_id: workspace.tenantId,
          project_id: workspace.projectId,
          max_steps: 32,
        }),
      });
      await parseJsonOrThrow(response);
      setNotice(`Run ${runId} executed.`);
      await loadRuns();
    } catch (err) {
      setError(toUiErrorMessage(err, "Execute failed."));
    } finally {
      setBusyRunId(null);
    }
  }

  async function handleHumanApproval(runId: string, decision: "approved" | "rejected") {
    if (!workspace) return;
    setBusyRunId(runId);
    setError(null);
    setNotice(null);
    try {
      const apiBase = getApiBaseUrl();
      const response = await fetch(`${apiBase}/runs/${runId}/execute`, {
        method: "POST",
        headers: buildApiHeaders(workspace.tenantId),
        body: JSON.stringify({
          tenant_id: workspace.tenantId,
          project_id: workspace.projectId,
          max_steps: 32,
          human_approval_override: decision,
        }),
      });
      await parseJsonOrThrow(response);
      setNotice(
        decision === "approved"
          ? `Run ${runId} approved and continued.`
          : `Run ${runId} rejected.`,
      );
      await loadRuns();
    } catch (err) {
      setError(toUiErrorMessage(err, "Approval update failed."));
    } finally {
      setBusyRunId(null);
    }
  }

  async function handlePublish(runId: string) {
    if (!workspace) return;
    setBusyRunId(runId);
    setError(null);
    setNotice(null);
    try {
      const apiBase = getApiBaseUrl();
      const response = await fetch(`${apiBase}/runs/${runId}/publish`, {
        method: "POST",
        headers: buildApiHeaders(workspace.tenantId, { role: "board_member" }),
        body: JSON.stringify({
          tenant_id: workspace.tenantId,
          project_id: workspace.projectId,
        }),
      });
      const payload = await parseJsonOrThrow<RunPublishResponse>(response);
      setNotice(
        payload.report_pdf
          ? `Run ${runId} published. PDF is ready for download.`
          : `Run ${runId} published.`,
      );
      await loadRuns();
    } catch (err) {
      setError(toUiErrorMessage(err, "Publish failed."));
    } finally {
      setBusyRunId(null);
    }
  }

  async function handleDownloadPdf(runId: string, reportPdf: ReportArtifact | null) {
    if (!workspace) return;
    setBusyRunId(runId);
    setError(null);
    setNotice(null);
    try {
      const apiBase = getApiBaseUrl();
      const path = reportPdf?.download_path ?? buildRunReportPdfPath(workspace, runId);
      const response = await fetch(`${apiBase}${path}`, {
        headers: buildApiHeaders(workspace.tenantId, {
          includeJsonContentType: false,
        }),
      });
      if (!response.ok) {
        throw new Error(await getResponseErrorMessage(response));
      }

      const blob = await response.blob();
      if (blob.size <= 0) {
        throw new Error("Downloaded PDF is empty.");
      }

      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = reportPdf?.filename ?? `report-${runId}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
      setNotice(`PDF download started for run ${runId}.`);
    } catch (err) {
      setError(toUiErrorMessage(err, "PDF download failed."));
    } finally {
      setBusyRunId(null);
    }
  }

  async function handleLoadTriage(runId: string) {
    if (!workspace) return;
    setBusyRunId(runId);
    setError(null);
    try {
      const apiBase = getApiBaseUrl();
      const response = await fetch(
        `${apiBase}/runs/${runId}/triage-report?tenant_id=${encodeURIComponent(workspace.tenantId)}&project_id=${encodeURIComponent(workspace.projectId)}&page=1&size=20`,
        {
          headers: buildApiHeaders(workspace.tenantId),
        },
      );
      const payload = await parseJsonOrThrow<TriageResponse>(response);
      setTriage(payload);
    } catch (err) {
      setError(toUiErrorMessage(err, "Triage fetch failed."));
    } finally {
      setBusyRunId(null);
    }
  }

  return (
    <AppShell
      activePath="/approval-center"
      title="Approval Center and SLA Control"
      subtitle="Run operations, triage, and publish control are managed from this screen."
      actions={[{ href: "/reports/new", label: "New Report Wizard" }]}
    >
      {created ? (
        <div className="mb-4 rounded-xl border border-emerald-500/35 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">
          Run created ({mode === "api" ? "API" : "unknown"} mode)
          {createdRunId ? ` - ${createdRunId}` : ""}.
        </div>
      ) : null}

      {!workspace ? (
        <div className="mb-4 rounded-xl border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
          Workspace not selected. Open &quot;New Report Wizard&quot; and create/select tenant + project first.
        </div>
      ) : (
        <div className="mb-4 rounded-xl border bg-card px-4 py-3 text-xs text-muted-foreground">
          tenant_id={workspace.tenantId} | project_id={workspace.projectId}
        </div>
      )}

      {error ? (
        <div
          className="mb-4 whitespace-pre-wrap rounded-xl border border-destructive/35 bg-destructive/10 px-4 py-3 text-sm text-destructive"
          data-testid="approval-center-error"
        >
          {error}
        </div>
      ) : null}

      {notice ? (
        <div
          className="mb-4 rounded-xl border border-emerald-500/35 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300"
          data-testid="approval-center-notice"
        >
          {notice}
        </div>
      ) : null}

      <article className="relative overflow-hidden rounded-xl border shadow-sm">
        <div className="absolute inset-0">
          <Image
            src="/images/approval-hero.png"
            alt="Approval workflow documents scene"
            fill
            sizes="100vw"
            className="object-cover opacity-30"
            priority
          />
          <div className="absolute inset-0 bg-gradient-to-r from-background/92 via-background/80 to-background/68" />
        </div>
        <div className="relative flex min-h-[230px] flex-col justify-end p-5 md:min-h-[280px]">
          <p className="text-muted-foreground text-xs uppercase tracking-[0.16em]">
            Governance Signature Workflow
          </p>
          <p className="mt-2 max-w-xl text-sm">
            Execute runs, inspect triage, and publish only when gates are clear.
          </p>
        </div>
      </article>

      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-xl border bg-card p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <Clock3 className="h-4 w-4 text-amber-600 dark:text-amber-300" />
            <p className="text-sm">Pending Runs</p>
          </div>
          <p className="mt-3 text-2xl font-semibold">{runStats.pending}</p>
          <p className="text-muted-foreground text-sm">Runs not yet published</p>
        </article>
        <article className="rounded-xl border bg-card p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <AlertOctagon className="h-4 w-4 text-destructive" />
            <p className="text-sm">Triage Required</p>
          </div>
          <p className="mt-3 text-2xl font-semibold">{runStats.slaRisk}</p>
          <p className="text-muted-foreground text-sm">Runs with verifier issues</p>
        </article>
        <article className="rounded-xl border bg-card p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-sky-600 dark:text-sky-300" />
            <p className="text-sm">Pending Human Approval</p>
          </div>
          <p className="mt-3 text-2xl font-semibold">{runStats.approverPool}</p>
          <p className="text-muted-foreground text-sm">Approval state = pending</p>
        </article>
      </div>

      <article className="mt-4 rounded-xl border bg-card p-5 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Run Queue</h2>
          <Button type="button" variant="outline" onClick={() => void loadRuns()} disabled={runsBusy || !workspace}>
            {runsBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Refresh
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table
            className="min-w-full border-separate border-spacing-y-2 text-left text-sm"
            data-testid="run-queue-table"
          >
            <thead className="text-muted-foreground text-xs uppercase tracking-[0.16em]">
              <tr>
                <th className="px-3 py-2">Run</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Node</th>
                <th className="px-3 py-2">Triage</th>
                <th className="px-3 py-2">Publish Ready</th>
                <th className="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((row) => (
                <tr key={row.run_id} className="bg-muted/35" data-testid={`run-row-${row.run_id}`}>
                  <td className="rounded-l-lg px-3 py-3 text-xs">{row.run_id}</td>
                  <td className="px-3 py-3" data-testid={`run-${row.run_id}-status`}>
                    {row.report_run_status}
                  </td>
                  <td className="px-3 py-3" data-testid={`run-${row.run_id}-node`}>
                    {row.active_node}
                  </td>
                  <td className="px-3 py-3">{row.triage_required ? "yes" : "no"}</td>
                  <td className="px-3 py-3" data-testid={`run-${row.run_id}-publish-ready`}>
                    {row.publish_ready ? "yes" : "no"}
                  </td>
                  <td className="rounded-r-lg px-3 py-3">
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => void handleExecute(row.run_id)}
                        disabled={busyRunId === row.run_id || !workspace}
                        data-testid={`run-${row.run_id}-execute`}
                      >
                        <PlayCircle className="h-4 w-4" />
                        Execute
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => void handleLoadTriage(row.run_id)}
                        disabled={busyRunId === row.run_id || !workspace}
                        data-testid={`run-${row.run_id}-triage`}
                      >
                        <RefreshCw className="h-4 w-4" />
                        Triage
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => void handlePublish(row.run_id)}
                        disabled={busyRunId === row.run_id || !workspace}
                        data-testid={`run-${row.run_id}-publish`}
                      >
                        <Send className="h-4 w-4" />
                        Publish
                      </Button>
                      {row.report_pdf || row.report_run_status === "published" ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => void handleDownloadPdf(row.run_id, row.report_pdf)}
                          disabled={busyRunId === row.run_id || !workspace}
                          data-testid={`run-${row.run_id}-download-pdf`}
                        >
                          <Download className="h-4 w-4" />
                          Download PDF
                        </Button>
                      ) : null}
                      {row.active_node === "HUMAN_APPROVAL" ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => void handleHumanApproval(row.run_id, "approved")}
                          disabled={busyRunId === row.run_id || !workspace}
                          data-testid={`run-${row.run_id}-approve`}
                        >
                          <CheckCircle2 className="h-4 w-4" />
                          Approve
                        </Button>
                      ) : null}
                      {row.active_node === "HUMAN_APPROVAL" ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => void handleHumanApproval(row.run_id, "rejected")}
                          disabled={busyRunId === row.run_id || !workspace}
                          data-testid={`run-${row.run_id}-reject`}
                        >
                          <AlertOctagon className="h-4 w-4" />
                          Reject
                        </Button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
              {runs.length === 0 ? (
                <tr>
                  <td className="rounded-lg px-3 py-4 text-sm text-muted-foreground" colSpan={6}>
                    No runs found for current workspace.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </article>

      {triage ? (
        <article className="mt-4 rounded-xl border bg-card p-5 shadow-sm">
          <h2 className="text-lg font-semibold">Triage Snapshot - {triage.run_id}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            FAIL: {triage.fail_count} | UNSURE: {triage.unsure_count} | CRITICAL FAIL: {triage.critical_fail_count}
          </p>
          <div className="mt-3 space-y-2">
            {triage.items.map((item) => (
              <div key={`${item.claim_id}-${item.status}`} className="rounded-lg border px-3 py-2 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium">
                    {item.status} - {item.section_code}
                  </p>
                  <p className="text-xs text-muted-foreground">{item.claim_id}</p>
                </div>
                <p className="mt-1 text-muted-foreground">{item.reason}</p>
              </div>
            ))}
            {triage.items.length === 0 ? (
              <p className="text-sm text-muted-foreground">No FAIL/UNSURE items in latest attempt.</p>
            ) : null}
          </div>
        </article>
      ) : null}

      <div className="mt-4 rounded-xl border border-emerald-500/35 bg-emerald-500/10 p-4 text-sm text-emerald-700 dark:text-emerald-300">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4" />
          Publish should only be triggered after execute + triage checks are clean.
        </div>
      </div>
    </AppShell>
  );
}

export default function ApprovalCenterPage() {
  return (
    <Suspense fallback={<ApprovalCenterFallback />}>
      <ApprovalCenterPageContent />
    </Suspense>
  );
}
