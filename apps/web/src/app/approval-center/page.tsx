"use client";

// Bu sayfa, approval-center ekraninin ana deneyimini kurar.

import { Suspense, useEffect, useMemo, useState } from "react";
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
import { useQueryClient } from "@tanstack/react-query";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  persistWorkspaceContext,
  type WorkspaceContext,
} from "@/lib/api/client";
import { queryKeys } from "@/lib/api/query-keys";
import {
  downloadRunArtifact,
  fetchRunPackageStatus,
  fetchRunTriage,
  parseApprovalCenterSearchParams,
  type ReportArtifact,
  type RunPackageStatus,
  type TriageResponse,
  useExecuteRunMutation,
  usePublishRunMutation,
  useRunPackageStatusQuery,
  useRunsQuery,
} from "@/lib/api/runs";
import { useWorkspaceContext } from "@/lib/api/workspace-store";

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

function useWorkspaceFromQueryAndStorage(): WorkspaceContext | null {
  const params = useSearchParams();
  const storedWorkspace = useWorkspaceContext();

  const queryTenant = params.get("tenantId");
  const queryProject = params.get("projectId");
  const queryWorkspace = useMemo(() => {
    if (queryTenant && queryProject) {
      return { tenantId: queryTenant, projectId: queryProject };
    }
    return null;
  }, [queryProject, queryTenant]);

  const workspace = queryWorkspace ?? storedWorkspace;

  useEffect(() => {
    if (
      workspace &&
      (
        !storedWorkspace ||
        storedWorkspace.tenantId !== workspace.tenantId ||
        storedWorkspace.projectId !== workspace.projectId
      )
    ) {
      persistWorkspaceContext(workspace);
    }
  }, [storedWorkspace, workspace]);

  return workspace;
}

function ApprovalCenterFallback() {
  return (
    <AppShell
      activePath="/approval-center"
      title="Controlled Publish Board"
      subtitle="Loading report factory operations..."
      actions={[{ href: "/reports/new", label: "New Report Run" }]}
    >
      <div className="rounded-xl border bg-card px-4 py-6 text-sm text-muted-foreground">
        Loading report factory surface...
      </div>
    </AppShell>
  );
}

function ApprovalCenterPageContent() {
  const params = useSearchParams();
  const workspace = useWorkspaceFromQueryAndStorage();
  const queryClient = useQueryClient();
  const searchParamString = params.toString();
  const { created, mode, runId: createdRunId } = useMemo(
    () => parseApprovalCenterSearchParams(new URLSearchParams(searchParamString)),
    [searchParamString],
  );

  const [busyRunId, setBusyRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [triage, setTriage] = useState<TriageResponse | null>(null);
  const [selectedPackageRunId, setSelectedPackageRunId] = useState<string | null>(null);

  const runsQuery = useRunsQuery(workspace, {
    page: 1,
    size: 50,
    pollWhilePending: true,
  });
  const packageStatusQuery = useRunPackageStatusQuery(workspace, selectedPackageRunId, {
    enabled: Boolean(selectedPackageRunId),
    pollWhilePending: true,
  });
  const executeRunMutation = useExecuteRunMutation(workspace);
  const publishRunMutation = usePublishRunMutation(workspace);

  const runs = runsQuery.data?.items ?? [];
  const runsBusy = runsQuery.isPending || runsQuery.isFetching;
  const packageState = packageStatusQuery.data ?? null;
  const pageError =
    error ??
    (runsQuery.isError
      ? toUiErrorMessage(runsQuery.error, "Failed to load runs.")
      : packageStatusQuery.isError
        ? toUiErrorMessage(packageStatusQuery.error, "Package status could not be loaded.")
        : null);

  const runStats = useMemo(() => {
    const pending = runs.filter((row) => row.report_run_status !== "published").length;
    const slaRisk = runs.filter((row) => row.triage_required).length;
    const packageRunning = runs.filter((row) => ["queued", "running"].includes(row.package_status)).length;
    return {
      pending,
      slaRisk,
      packageRunning,
    };
  }, [runs]);

  useEffect(() => {
    setBusyRunId(null);
    setError(null);
    setNotice(null);
    setTriage(null);
    setSelectedPackageRunId(null);
  }, [workspace?.tenantId, workspace?.projectId]);

  async function handleLoadPackageStatus(runId: string) {
    if (!workspace) return;
    setBusyRunId(runId);
    setError(null);
    try {
      setSelectedPackageRunId(runId);
      const payload = await queryClient.fetchQuery({
        queryKey: queryKeys.runs.packageStatus(workspace, runId),
        queryFn: ({ signal }) => fetchRunPackageStatus(workspace, runId, signal),
      });
      setNotice(`Package status refreshed: ${payload.package_status}.`);
      await runsQuery.refetch();
    } catch (err) {
      setError(toUiErrorMessage(err, "Package status could not be loaded."));
    } finally {
      setBusyRunId(null);
    }
  }

  async function handleExecute(runId: string) {
    if (!workspace) return;
    setBusyRunId(runId);
    setError(null);
    setNotice(null);
    try {
      await executeRunMutation.mutateAsync({
        runId,
        maxSteps: 32,
      });
      setNotice(`Run ${runId} executed.`);
      await runsQuery.refetch();
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
      await executeRunMutation.mutateAsync({
        runId,
        maxSteps: 32,
        humanApprovalOverride: decision,
      });
      setNotice(
        decision === "approved"
          ? `Run ${runId} approved and continued.`
          : `Run ${runId} rejected.`,
      );
      await runsQuery.refetch();
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
      const payload = await publishRunMutation.mutateAsync({ runId });
      setNotice(
        payload.published
          ? `Run ${runId} is now published. The package is complete and the PDF is ready to download.`
          : `Run ${runId} entered the controlled publish queue. Stage: ${payload.estimated_stage ?? payload.package_status}.`,
      );
      const nextPackageState: RunPackageStatus = {
        run_id: runId,
        package_job_id: payload.package_job_id,
        package_status: payload.package_status,
        current_stage: payload.estimated_stage,
        report_quality_score: null,
        visual_generation_status: "queued",
        artifacts: payload.artifacts,
        stage_history: [],
        generated_at_utc: new Date().toISOString(),
      };

      queryClient.setQueryData(
        queryKeys.runs.packageStatus(workspace, runId),
        nextPackageState,
      );
      setSelectedPackageRunId(runId);
      await runsQuery.refetch();
    } catch (err) {
      setError(toUiErrorMessage(err, "Publish failed."));
    } finally {
      setBusyRunId(null);
    }
  }

  async function handleDownloadArtifact(
    runId: string,
    artifact: ReportArtifact | null,
    fallbackFilename: string,
  ) {
    if (!workspace) return;
    setBusyRunId(runId);
    setError(null);
    setNotice(null);
    try {
      const filename = await downloadRunArtifact(
        workspace,
        runId,
        artifact,
        fallbackFilename,
      );
      setNotice(`Download started: ${filename}`);
    } catch (err) {
      setError(toUiErrorMessage(err, "Artifact download failed."));
    } finally {
      setBusyRunId(null);
    }
  }

  async function handleLoadTriage(runId: string) {
    if (!workspace) return;
    setBusyRunId(runId);
    setError(null);
    try {
      const payload = await queryClient.fetchQuery({
        queryKey: queryKeys.runs.triage(workspace, runId),
        queryFn: ({ signal }) => fetchRunTriage(workspace, runId, signal),
      });
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
      title="Controlled Publish Board"
      subtitle="Manage run execution, package generation, verifier triage, and the controlled publish handoff from one premium board."
      actions={[{ href: "/reports/new", label: "New Report Run" }]}
    >
      {created ? (
        <div className="mb-4 rounded-[1.35rem] border border-emerald-500/35 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">
          Run created ({mode === "api" ? "API" : "unknown"} mode)
          {createdRunId ? ` - ${createdRunId}` : ""}.
        </div>
      ) : null}

      {!workspace ? (
        <div className="mb-4 rounded-[1.35rem] border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
          No workspace selected yet. Open &quot;New Report Run&quot; first to pick a tenant and project.
        </div>
      ) : (
        <div className="mb-4 rounded-[1.35rem] border border-[color:var(--border)] bg-white/72 px-4 py-3 text-xs text-muted-foreground">
          tenant_id={workspace.tenantId} | project_id={workspace.projectId}
        </div>
      )}

      {pageError ? (
        <div
          className="mb-4 whitespace-pre-wrap rounded-xl border border-destructive/35 bg-destructive/10 px-4 py-3 text-sm text-destructive"
          data-testid="approval-center-error"
        >
          {pageError}
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

      <article className="relative overflow-hidden rounded-[1.75rem] border border-[color:var(--border)] shadow-[var(--shadow-soft)]">
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
            Report Factory Pipeline
          </p>
          <p className="mt-2 max-w-xl text-sm">
            Watch sync, execute, triage, package, and controlled publish from one compact operations surface.
          </p>
        </div>
      </article>

      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-[1.5rem] border border-[color:var(--border)] bg-white/72 p-4 shadow-[var(--shadow-soft)]">
          <div className="flex items-center gap-2">
            <Clock3 className="h-4 w-4 text-amber-600 dark:text-amber-300" />
            <p className="text-sm">Pending Runs</p>
          </div>
          <p className="mt-3 text-2xl font-semibold">{runStats.pending}</p>
          <p className="text-muted-foreground text-sm">Runs that have not reached publish yet</p>
        </article>
        <article className="rounded-[1.5rem] border border-[color:var(--border)] bg-white/72 p-4 shadow-[var(--shadow-soft)]">
          <div className="flex items-center gap-2">
            <AlertOctagon className="h-4 w-4 text-destructive" />
            <p className="text-sm">Triage Pressure</p>
          </div>
          <p className="mt-3 text-2xl font-semibold">{runStats.slaRisk}</p>
          <p className="text-muted-foreground text-sm">Verifier-driven blocks that still need attention</p>
        </article>
        <article className="rounded-[1.5rem] border border-[color:var(--border)] bg-white/72 p-4 shadow-[var(--shadow-soft)]">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-sky-600 dark:text-sky-300" />
            <p className="text-sm">Packaging Active</p>
          </div>
          <p className="mt-3 text-2xl font-semibold">{runStats.packageRunning}</p>
          <p className="text-muted-foreground text-sm">Packaging jobs currently in flight</p>
          <p className="text-muted-foreground text-xs">queued + running</p>
        </article>
      </div>

      <article className="mt-4 rounded-[1.75rem] border border-[color:var(--border)] bg-white/72 p-5 shadow-[var(--shadow-soft)]">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Run Queue</h2>
          <Button
            type="button"
            variant="outline"
            onClick={() => void runsQuery.refetch()}
            disabled={runsBusy || !workspace}
          >
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
                <th className="px-3 py-2">Package</th>
                <th className="px-3 py-2">Quality</th>
                <th className="px-3 py-2">Triage</th>
                <th className="px-3 py-2">Publish Ready</th>
                <th className="px-3 py-2">Last Sync</th>
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
                  <td className="px-3 py-3">{row.package_status}</td>
                  <td className="px-3 py-3">
                    {row.report_quality_score !== null ? row.report_quality_score.toFixed(1) : "-"}
                  </td>
                  <td className="px-3 py-3">{row.triage_required ? "yes" : "no"}</td>
                  <td className="px-3 py-3" data-testid={`run-${row.run_id}-publish-ready`}>
                    {row.publish_ready ? "yes" : "no"}
                  </td>
                  <td className="px-3 py-3">{row.latest_sync_at_utc ? new Date(row.latest_sync_at_utc).toLocaleString("en-GB") : "-"}</td>
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
                        variant="outline"
                        onClick={() => void handleLoadPackageStatus(row.run_id)}
                        disabled={busyRunId === row.run_id || !workspace}
                        data-testid={`run-${row.run_id}-package-status`}
                      >
                        <RefreshCw className="h-4 w-4" />
                        Package
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => void handlePublish(row.run_id)}
                        disabled={busyRunId === row.run_id || !workspace || ["queued", "running"].includes(row.package_status)}
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
                          onClick={() =>
                            void handleDownloadArtifact(
                              row.run_id,
                              row.report_pdf,
                              `report-${row.run_id}.pdf`,
                            )
                          }
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
                  <td className="rounded-lg px-3 py-4 text-sm text-muted-foreground" colSpan={9}>
                    No runs were found for the current workspace.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </article>

      {packageState ? (
        <article className="mt-4 rounded-[1.75rem] border border-[color:var(--border)] bg-white/72 p-5 shadow-[var(--shadow-soft)]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">Package Status - {packageState.run_id}</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Status: {packageState.package_status}
                {packageState.current_stage ? ` | Stage: ${packageState.current_stage}` : ""}
                {packageState.report_quality_score !== null
                  ? ` | Quality: ${packageState.report_quality_score.toFixed(1)}`
                  : ""}
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => void handleLoadPackageStatus(packageState.run_id)}
              disabled={busyRunId === packageState.run_id || !workspace}
            >
              {busyRunId === packageState.run_id ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Refresh Package
            </Button>
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="rounded-2xl border bg-muted/25 p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Stage History</p>
              <div className="mt-3 space-y-2">
                {packageState.stage_history.map((item) => (
                  <div key={`${item.stage}-${item.at_utc}`} className="rounded-xl border bg-background px-3 py-2 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <strong>{item.stage}</strong>
                      <span className="text-xs text-muted-foreground">{item.status}</span>
                    </div>
                    {item.detail ? <p className="mt-1 text-xs text-muted-foreground">{item.detail}</p> : null}
                  </div>
                ))}
                {packageState.stage_history.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No stage history available yet.</p>
                ) : null}
              </div>
            </div>
            <div className="rounded-2xl border bg-muted/25 p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Artifacts</p>
              <div className="mt-3 space-y-2">
                {packageState.artifacts.map((artifact) => (
                  <div key={artifact.artifact_id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-background px-3 py-3 text-sm">
                    <div>
                      <p className="font-medium">{artifact.filename}</p>
                      <p className="text-xs text-muted-foreground">
                        {artifact.artifact_type} | {artifact.content_type} | {artifact.size_bytes} bytes
                      </p>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => void handleDownloadArtifact(packageState.run_id, artifact, artifact.filename)}
                      disabled={busyRunId === packageState.run_id || !workspace}
                    >
                      <Download className="h-4 w-4" />
                      Download
                    </Button>
                  </div>
                ))}
                {packageState.artifacts.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No artifacts have been produced yet.</p>
                ) : null}
              </div>
            </div>
          </div>
        </article>
      ) : null}

      {triage ? (
        <article className="mt-4 rounded-[1.75rem] border border-[color:var(--border)] bg-white/72 p-5 shadow-[var(--shadow-soft)]">
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

      <div className="mt-4 rounded-[1.35rem] border border-emerald-500/35 bg-emerald-500/10 p-4 text-sm text-emerald-700 dark:text-emerald-300">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4" />
          Trigger controlled publish only after execute is complete and the triage board is clear.
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
