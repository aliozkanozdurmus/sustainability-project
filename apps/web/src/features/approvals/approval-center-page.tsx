"use client";

// Bu sayfa, approval-center ekranini queue-first operator deneyimiyle kurar.

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  CheckCircle2,
  Clock3,
  Download,
  Loader2,
  PlayCircle,
  RefreshCw,
  Send,
  ShieldCheck,
  Workflow,
  XCircle,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  MetricPill,
  SectionHeading,
  StatusChip,
  SubtleAlert,
  SurfaceCard,
  TimelineRail,
} from "@/components/workbench-ui";
import { persistWorkspaceContext, type WorkspaceContext } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/query-keys";
import {
  downloadRunArtifact,
  fetchRunPackageStatus,
  fetchRunTriage,
  parseApprovalCenterSearchParams,
  type ReportArtifact,
  type RunListItem,
  type RunPackageStatus,
  type TriageResponse,
  useExecuteRunMutation,
  usePublishRunMutation,
  useRunPackageStatusQuery,
  useRunTriageQuery,
  useRunsQuery,
} from "@/lib/api/runs";
import { useWorkspaceContext } from "@/lib/api/workspace-store";
import { cn } from "@/lib/utils";

type QueueBucket = "blockers" | "release" | "archive";

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
      (!storedWorkspace ||
        storedWorkspace.tenantId !== workspace.tenantId ||
        storedWorkspace.projectId !== workspace.projectId)
    ) {
      persistWorkspaceContext(workspace);
    }
  }, [storedWorkspace, workspace]);

  return workspace;
}

function formatDateTime(value?: string | null): string {
  if (!value) return "Bekliyor";
  return new Date(value).toLocaleString("tr-TR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatPercent(value: number): string {
  return new Intl.NumberFormat("tr-TR", {
    style: "percent",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatCountdown(deadline?: string | null): string {
  if (!deadline) return "SLA tanimsiz";
  const target = new Date(deadline).getTime();
  const diff = target - Date.now();
  const sign = diff < 0 ? "-" : "";
  const totalMinutes = Math.abs(Math.round(diff / 60000));
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) {
    return `${sign}${days}g ${hours}s`;
  }
  return `${sign}${hours}s ${minutes}d`;
}

function toneForSla(status: RunListItem["approval_sla_status"]) {
  if (status === "breached") return "critical" as const;
  if (status === "risk") return "attention" as const;
  if (status === "complete") return "good" as const;
  return "neutral" as const;
}

function toneForPackage(status: string) {
  if (status === "completed") return "good" as const;
  if (status === "failed") return "critical" as const;
  if (status === "queued" || status === "running") return "attention" as const;
  return "neutral" as const;
}

function toneForRun(run: RunListItem) {
  if (run.triage_required || run.approval_sla_status === "breached") return "critical" as const;
  if (run.publish_ready || run.report_run_status === "published") return "good" as const;
  if (run.approval_sla_status === "risk" || run.package_status === "running")
    return "attention" as const;
  return "neutral" as const;
}

function deriveQueueBucket(run: RunListItem): QueueBucket {
  // Approval center'da en kritik tercih burada:
  // kullaniciyi once blocker kuyruğuna, sonra release akışına yonlendiriyoruz.
  if (run.report_run_status === "published" || run.package_status === "completed") {
    return "archive";
  }
  if (run.triage_required || run.approval_sla_status === "breached") {
    return "blockers";
  }
  return "release";
}

function pickInitialRunId(runs: RunListItem[], preferredRunId?: string | null): string | null {
  if (preferredRunId && runs.some((run) => run.run_id === preferredRunId)) {
    return preferredRunId;
  }
  const blocker = runs.find((run) => deriveQueueBucket(run) === "blockers");
  if (blocker) return blocker.run_id;
  return runs[0]?.run_id ?? null;
}

function buildRunBlockers(
  run: RunListItem,
  triage: TriageResponse | null,
  packageState: RunPackageStatus | null,
): string[] {
  // Drawer icindeki blocker listesi, backend publish gate sinyallerini
  // operator'a aksiyon diline ceviren UI katmanidir.
  const blockers: string[] = [];
  if (run.triage_required) {
    blockers.push("Verifier triage kuyruğu temizlenmeden controlled publish ilerlemez.");
  }
  if (!run.publish_ready) {
    blockers.push("Workflow publish-ready durumuna gelmemis.");
  }
  if (run.approval_sla_status === "risk") {
    blockers.push(
      `Approval SLA pencere daraliyor: ${formatCountdown(run.approval_sla_deadline_utc)} kaldi.`,
    );
  }
  if (run.approval_sla_status === "breached") {
    blockers.push("Approval SLA asildi; governance owner eskalasyonu gerekli.");
  }
  if (packageState && ["queued", "running"].includes(packageState.package_status)) {
    blockers.push(
      "Package pipeline halen calisiyor; artefact seti tamamlanmadan publish yapılmaz.",
    );
  }
  if (triage && triage.total_items > 0) {
    blockers.push(
      `${triage.fail_count} FAIL ve ${triage.unsure_count} UNSURE kaydı inceleme bekliyor.`,
    );
  }
  if (run.report_pdf == null && run.report_run_status === "published") {
    blockers.push("Published run icin PDF artefakti görünmüyor.");
  }
  return blockers;
}

function ApprovalCenterFallback() {
  return (
    <AppShell
      activePath="/approval-center"
      title="Controlled Publish Board"
      subtitle="Loading release operations..."
      actions={[{ href: "/reports/new", label: "New Report Run" }]}
    >
      <div className="bg-card text-muted-foreground rounded-xl border px-4 py-6 text-sm">
        Loading release queue...
      </div>
    </AppShell>
  );
}

function QueueStat({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string | number;
  detail: string;
  tone: "good" | "attention" | "critical" | "neutral";
}) {
  return <MetricPill label={label} value={value} detail={detail} tone={tone} />;
}

function ArtifactBadgeStrip({ badges }: { badges: string[] }) {
  if (!badges.length) {
    return (
      <p className="text-[11px] text-[color:var(--foreground-muted)]">No package artifacts yet.</p>
    );
  }
  return (
    <div className="flex flex-wrap gap-2">
      {badges.map((badge) => (
        <span
          key={badge}
          className="text-foreground rounded-full border border-[color:var(--border)] bg-white/78 px-2.5 py-1 text-[11px] font-medium"
        >
          {badge}
        </span>
      ))}
    </div>
  );
}

function QueueCard({
  run,
  busyRunId,
  selected,
  onSelect,
  onExecute,
  onLoadTriage,
  onLoadPackageStatus,
  onPublish,
  onDownloadArtifact,
  onHumanApproval,
}: {
  run: RunListItem;
  busyRunId: string | null;
  selected: boolean;
  onSelect: (runId: string) => void;
  onExecute: (runId: string) => Promise<void>;
  onLoadTriage: (runId: string) => Promise<void>;
  onLoadPackageStatus: (runId: string) => Promise<void>;
  onPublish: (runId: string) => Promise<void>;
  onDownloadArtifact: (
    runId: string,
    artifact: ReportArtifact | null,
    fallbackFilename: string,
  ) => Promise<void>;
  onHumanApproval: (runId: string, decision: "approved" | "rejected") => Promise<void>;
}) {
  const busy = busyRunId === run.run_id;
  const bucket = deriveQueueBucket(run);
  const tone = toneForRun(run);

  return (
    <div
      className={cn(
        "rounded-[1.7rem] border px-4 py-4 transition-all",
        selected
          ? "border-[rgba(31,122,74,0.28)] bg-[linear-gradient(180deg,rgba(255,255,255,0.92)_0%,rgba(240,247,241,0.95)_100%)] shadow-[0_16px_32px_rgba(25,59,44,0.08)]"
          : "border-[color:var(--border)] bg-white/82",
      )}
      data-testid={`run-row-${run.run_id}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip tone={tone}>
              {bucket === "blockers"
                ? "Blocker queue"
                : bucket === "archive"
                  ? "Archive"
                  : "Release queue"}
            </StatusChip>
            <StatusChip tone={toneForPackage(run.package_status)}>{run.package_status}</StatusChip>
            <StatusChip tone={toneForSla(run.approval_sla_status)}>
              SLA {run.approval_sla_status}
            </StatusChip>
          </div>
          <div>
            <p className="text-foreground text-[17px] font-semibold tracking-[-0.03em]">
              Run {run.run_id.slice(0, 8)}
            </p>
            <p className="mt-1 text-[12px] leading-5 text-[color:var(--foreground-soft)]">
              Node {run.active_node} • Last checkpoint {formatDateTime(run.last_checkpoint_at_utc)}
            </p>
          </div>
        </div>

        <Button
          type="button"
          variant={selected ? "default" : "outline"}
          size="sm"
          onClick={() => onSelect(run.run_id)}
        >
          {selected ? "Selected" : "Inspect"}
        </Button>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {/* Ilk fold'da tablo yerine ozet kartlari kullanmamizin nedeni,
            operator'un package, SLA ve publish readiness'i tek bakista ayirmasidir. */}
        <div className="rounded-[1.25rem] border border-[color:var(--border)] bg-[color:var(--muted)]/55 px-3 py-3">
          <p className="text-[11px] tracking-[0.14em] text-[color:var(--foreground-muted)] uppercase">
            Workflow
          </p>
          <p
            className="text-foreground mt-2 text-[14px] font-medium"
            data-testid={`run-${run.run_id}-status`}
          >
            {run.report_run_status}
          </p>
          <p
            className="mt-1 text-[11px] text-[color:var(--foreground-soft)]"
            data-testid={`run-${run.run_id}-node`}
          >
            {run.active_node}
          </p>
        </div>

        <div className="rounded-[1.25rem] border border-[color:var(--border)] bg-[color:var(--muted)]/55 px-3 py-3">
          <p className="text-[11px] tracking-[0.14em] text-[color:var(--foreground-muted)] uppercase">
            Publish readiness
          </p>
          <p
            className="text-foreground mt-2 text-[14px] font-medium"
            data-testid={`run-${run.run_id}-publish-ready`}
          >
            {run.publish_ready ? "yes" : "no"}
          </p>
          <p className="mt-1 text-[11px] text-[color:var(--foreground-soft)]">
            Human approval: {run.human_approval}
          </p>
        </div>

        <div className="rounded-[1.25rem] border border-[color:var(--border)] bg-[color:var(--muted)]/55 px-3 py-3">
          <p className="text-[11px] tracking-[0.14em] text-[color:var(--foreground-muted)] uppercase">
            Artifact integrity
          </p>
          <p className="text-foreground mt-2 text-[14px] font-medium">
            {formatPercent(run.artifact_completion_ratio)}
          </p>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-[rgba(23,22,19,0.08)]">
            <div
              className="h-full rounded-full bg-[linear-gradient(90deg,#0c4a6e_0%,#1f7a4a_100%)]"
              style={{ width: `${Math.max(8, run.artifact_completion_ratio * 100)}%` }}
            />
          </div>
        </div>

        <div className="rounded-[1.25rem] border border-[color:var(--border)] bg-[color:var(--muted)]/55 px-3 py-3">
          <p className="text-[11px] tracking-[0.14em] text-[color:var(--foreground-muted)] uppercase">
            Approval SLA
          </p>
          <p className="text-foreground mt-2 text-[14px] font-medium">
            {formatCountdown(run.approval_sla_deadline_utc)}
          </p>
          <p className="mt-1 text-[11px] text-[color:var(--foreground-soft)]">
            Started {formatDateTime(run.started_at_utc)}
          </p>
        </div>
      </div>

      <div className="mt-4 space-y-3">
        <ArtifactBadgeStrip badges={run.artifact_badges} />
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void onExecute(run.run_id)}
            disabled={busy || run.report_run_status === "published"}
            data-testid={`run-${run.run_id}-execute`}
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <PlayCircle className="size-4" />}
            Execute
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void onLoadTriage(run.run_id)}
            disabled={busy}
            data-testid={`run-${run.run_id}-triage`}
          >
            <ShieldCheck className="size-4" />
            Triage
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void onLoadPackageStatus(run.run_id)}
            disabled={busy}
            data-testid={`run-${run.run_id}-package-status`}
          >
            <RefreshCw className="size-4" />
            Package
          </Button>
          <Button
            type="button"
            variant="soft"
            size="sm"
            onClick={() => void onPublish(run.run_id)}
            disabled={busy}
            data-testid={`run-${run.run_id}-publish`}
          >
            <Send className="size-4" />
            Publish
          </Button>
          {run.report_pdf ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                void onDownloadArtifact(run.run_id, run.report_pdf, `${run.run_id}.pdf`)
              }
              disabled={busy}
              data-testid={`run-${run.run_id}-download-pdf`}
            >
              <Download className="size-4" />
              PDF
            </Button>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void onHumanApproval(run.run_id, "approved")}
            disabled={busy || run.report_run_status === "published"}
            data-testid={`run-${run.run_id}-approve`}
          >
            <CheckCircle2 className="size-4" />
            Approve
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void onHumanApproval(run.run_id, "rejected")}
            disabled={busy || run.report_run_status === "published"}
            data-testid={`run-${run.run_id}-reject`}
          >
            <XCircle className="size-4" />
            Reject
          </Button>
        </div>
      </div>
    </div>
  );
}

function QueueLane({
  title,
  description,
  runs,
  busyRunId,
  selectedRunId,
  onSelect,
  onExecute,
  onLoadTriage,
  onLoadPackageStatus,
  onPublish,
  onDownloadArtifact,
  onHumanApproval,
}: {
  title: string;
  description: string;
  runs: RunListItem[];
  busyRunId: string | null;
  selectedRunId: string | null;
  onSelect: (runId: string) => void;
  onExecute: (runId: string) => Promise<void>;
  onLoadTriage: (runId: string) => Promise<void>;
  onLoadPackageStatus: (runId: string) => Promise<void>;
  onPublish: (runId: string) => Promise<void>;
  onDownloadArtifact: (
    runId: string,
    artifact: ReportArtifact | null,
    fallbackFilename: string,
  ) => Promise<void>;
  onHumanApproval: (runId: string, decision: "approved" | "rejected") => Promise<void>;
}) {
  return (
    <SurfaceCard className="space-y-4">
      <SectionHeading eyebrow="Queue" title={title} description={description} />
      {runs.length ? (
        <div className="space-y-3" data-testid="run-queue-table">
          {runs.map((run) => (
            <QueueCard
              key={run.run_id}
              run={run}
              busyRunId={busyRunId}
              selected={selectedRunId === run.run_id}
              onSelect={onSelect}
              onExecute={onExecute}
              onLoadTriage={onLoadTriage}
              onLoadPackageStatus={onLoadPackageStatus}
              onPublish={onPublish}
              onDownloadArtifact={onDownloadArtifact}
              onHumanApproval={onHumanApproval}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title="Queue empty"
          description="Bu kuyrukta gosterilecek run yok. Diger lane'leri kontrol edin veya yeni run baslatin."
        />
      )}
    </SurfaceCard>
  );
}

function BlockersDrawer({
  run,
  packageState,
  triage,
  loadingPackage,
  loadingTriage,
  blockers,
  onRefreshPackage,
  onRefreshTriage,
}: {
  run: RunListItem | null;
  packageState: RunPackageStatus | null;
  triage: TriageResponse | null;
  loadingPackage: boolean;
  loadingTriage: boolean;
  blockers: string[];
  onRefreshPackage: () => Promise<void>;
  onRefreshTriage: () => Promise<void>;
}) {
  return (
    <SurfaceCard className="sticky top-4 space-y-4" data-testid="publish-blockers-drawer">
      <SectionHeading
        eyebrow="Drawer"
        title="Publish blockers"
        description="Secili run icin publish gate, triage ve package state ayni yerde toplanir."
        action={
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void onRefreshTriage()}
              disabled={!run}
            >
              {loadingTriage ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <ShieldCheck className="size-4" />
              )}
              Triage
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void onRefreshPackage()}
              disabled={!run}
            >
              {loadingPackage ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <RefreshCw className="size-4" />
              )}
              Package
            </Button>
          </div>
        }
      />

      {!run ? (
        <EmptyState
          title="Select a run"
          description="Kuyruktan bir run secin; blocker listesi, stage timeline ve triage snapshot burada acilacak."
        />
      ) : (
        <>
          {/* Bu panel, bizim ekipteki publish owner'in bakis acisini temsil ediyor:
              secili run icin karar vermeyi saglayan minimum ama yeterli veri burada toplanir. */}
          <div className="rounded-[1.45rem] border border-[color:var(--border)] bg-[linear-gradient(160deg,#1a1917_0%,#234a3a_100%)] px-4 py-4 text-white">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[11px] tracking-[0.14em] text-white/68 uppercase">
                  Selected run
                </p>
                <p className="mt-2 text-[24px] font-semibold tracking-[-0.05em]">
                  {run.run_id.slice(0, 8)}
                </p>
                <p className="mt-1 text-[12px] text-white/76">
                  {run.report_run_status} • package {run.package_status}
                </p>
              </div>
              <Workflow className="size-5 text-white/78" />
            </div>
            <div className="mt-4 grid gap-2 md:grid-cols-2">
              <div className="rounded-[1rem] border border-white/10 bg-white/8 px-3 py-2.5">
                <p className="text-[10px] tracking-[0.14em] text-white/60 uppercase">
                  Artifact coverage
                </p>
                <p className="mt-1 text-[15px] font-medium text-white">
                  {formatPercent(run.artifact_completion_ratio)}
                </p>
              </div>
              <div className="rounded-[1rem] border border-white/10 bg-white/8 px-3 py-2.5">
                <p className="text-[10px] tracking-[0.14em] text-white/60 uppercase">
                  Approval countdown
                </p>
                <p className="mt-1 text-[15px] font-medium text-white">
                  {formatCountdown(run.approval_sla_deadline_utc)}
                </p>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <p className="text-[12px] font-semibold tracking-[0.14em] text-[color:var(--foreground-muted)] uppercase">
              Active blockers
            </p>
            {blockers.length ? (
              blockers.map((blocker) => (
                <SubtleAlert key={blocker} tone="critical" title="Blocking item">
                  {blocker}
                </SubtleAlert>
              ))
            ) : (
              <SubtleAlert tone="good" title="Ready lane">
                Hard blocker tespit edilmedi. Publish gate son kontroller icin hazir.
              </SubtleAlert>
            )}
          </div>

          <div className="space-y-3">
            <p className="text-[12px] font-semibold tracking-[0.14em] text-[color:var(--foreground-muted)] uppercase">
              Stage history
            </p>
            {packageState?.stage_history?.length ? (
              <TimelineRail
                items={packageState.stage_history.map((item) => ({
                  title: item.stage,
                  subtitle: `${item.status} • ${formatDateTime(item.at_utc)}`,
                  detail: item.detail ?? undefined,
                  tone:
                    item.status === "failed"
                      ? "critical"
                      : item.status === "completed"
                        ? "good"
                        : "attention",
                }))}
              />
            ) : (
              <EmptyState
                title="No stage history"
                description="Package state henuz alinmadi. Package butonu ile son kontrollu publish durumunu yukleyin."
              />
            )}
          </div>

          <div className="space-y-3">
            <p className="text-[12px] font-semibold tracking-[0.14em] text-[color:var(--foreground-muted)] uppercase">
              Artifact completeness
            </p>
            <ArtifactBadgeStrip badges={run.artifact_badges} />
            <p className="text-[12px] leading-5 text-[color:var(--foreground-soft)]">
              Quality score:{" "}
              {packageState?.report_quality_score ?? run.report_quality_score ?? "N/A"} • Visual
              pipeline: {packageState?.visual_generation_status ?? run.visual_generation_status}
            </p>
          </div>

          <div className="space-y-3">
            <p className="text-[12px] font-semibold tracking-[0.14em] text-[color:var(--foreground-muted)] uppercase">
              Triage snapshot
            </p>
            {triage ? (
              <div className="space-y-3">
                <div className="grid gap-2 sm:grid-cols-3">
                  <div className="rounded-[1rem] border border-[color:var(--border)] bg-white/78 px-3 py-3">
                    <p className="text-[11px] tracking-[0.12em] text-[color:var(--foreground-muted)] uppercase">
                      FAIL
                    </p>
                    <p className="text-foreground mt-1 text-[18px] font-semibold">
                      {triage.fail_count}
                    </p>
                  </div>
                  <div className="rounded-[1rem] border border-[color:var(--border)] bg-white/78 px-3 py-3">
                    <p className="text-[11px] tracking-[0.12em] text-[color:var(--foreground-muted)] uppercase">
                      UNSURE
                    </p>
                    <p className="text-foreground mt-1 text-[18px] font-semibold">
                      {triage.unsure_count}
                    </p>
                  </div>
                  <div className="rounded-[1rem] border border-[color:var(--border)] bg-white/78 px-3 py-3">
                    <p className="text-[11px] tracking-[0.12em] text-[color:var(--foreground-muted)] uppercase">
                      Critical
                    </p>
                    <p className="text-foreground mt-1 text-[18px] font-semibold">
                      {triage.critical_fail_count}
                    </p>
                  </div>
                </div>
                <div className="space-y-2">
                  {triage.items.slice(0, 4).map((item) => (
                    <div
                      key={`${item.claim_id}-${item.section_code}`}
                      className="rounded-[1.2rem] border border-[color:var(--border)] bg-white/78 px-3 py-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-foreground text-[13px] font-medium">
                          {item.section_code}
                        </p>
                        <StatusChip tone={item.status === "FAIL" ? "critical" : "attention"}>
                          {item.status}
                        </StatusChip>
                      </div>
                      <p className="mt-1 text-[12px] leading-5 text-[color:var(--foreground-soft)]">
                        {item.reason}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <EmptyState
                title="No triage loaded"
                description="Verifier triage detaylari bu drawer'a yuklenir. Triage butonuyla son snapshot'i alin."
              />
            )}
          </div>
        </>
      )}
    </SurfaceCard>
  );
}

function ApprovalCenterPageContent() {
  const params = useSearchParams();
  const workspace = useWorkspaceFromQueryAndStorage();
  const queryClient = useQueryClient();
  const searchParamString = params.toString();
  const {
    created,
    mode,
    runId: createdRunId,
  } = useMemo(
    () => parseApprovalCenterSearchParams(new URLSearchParams(searchParamString)),
    [searchParamString],
  );

  const [busyRunId, setBusyRunId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(createdRunId ?? null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const runsQuery = useRunsQuery(workspace, {
    page: 1,
    size: 50,
    pollWhilePending: true,
  });
  const packageStatusQuery = useRunPackageStatusQuery(workspace, selectedRunId, {
    enabled: Boolean(selectedRunId),
    pollWhilePending: true,
  });
  const triageQuery = useRunTriageQuery(workspace, selectedRunId, Boolean(selectedRunId));
  const executeRunMutation = useExecuteRunMutation(workspace);
  const publishRunMutation = usePublishRunMutation(workspace);

  const runItems = runsQuery.data?.items;
  const runs = useMemo(() => runItems ?? [], [runItems]);
  const selectedRun = runs.find((run) => run.run_id === selectedRunId) ?? null;
  const pageError =
    error ??
    (runsQuery.isError
      ? toUiErrorMessage(runsQuery.error, "Failed to load runs.")
      : packageStatusQuery.isError
        ? toUiErrorMessage(packageStatusQuery.error, "Package status could not be loaded.")
        : triageQuery.isError
          ? toUiErrorMessage(triageQuery.error, "Triage could not be loaded.")
          : null);

  useEffect(() => {
    setBusyRunId(null);
    setError(null);
    setNotice(null);
    setSelectedRunId(createdRunId ?? null);
  }, [workspace?.tenantId, workspace?.projectId, createdRunId]);

  useEffect(() => {
    if (!runs.length) return;
    setSelectedRunId((current) => pickInitialRunId(runs, current ?? createdRunId));
  }, [createdRunId, runs]);

  const groupedRuns = useMemo(() => {
    return {
      blockers: runs.filter((run) => deriveQueueBucket(run) === "blockers"),
      release: runs.filter((run) => deriveQueueBucket(run) === "release"),
      archive: runs.filter((run) => deriveQueueBucket(run) === "archive"),
    };
  }, [runs]);

  const stats = useMemo(() => {
    const blockers = groupedRuns.blockers.length;
    const release = groupedRuns.release.length;
    const archive = groupedRuns.archive.length;
    const risk = runs.filter((run) =>
      ["risk", "breached"].includes(run.approval_sla_status),
    ).length;
    const publishReady = runs.filter((run) => run.publish_ready).length;
    return { blockers, release, archive, risk, publishReady };
  }, [groupedRuns, runs]);

  const blockers = useMemo(
    () =>
      buildRunBlockers(
        selectedRun ?? {
          run_id: "",
          report_run_status: "",
          publish_ready: false,
          started_at_utc: null,
          completed_at_utc: null,
          active_node: "",
          human_approval: "",
          triage_required: false,
          last_checkpoint_status: "",
          last_checkpoint_at_utc: null,
          package_status: "",
          report_quality_score: null,
          latest_sync_at_utc: null,
          visual_generation_status: "",
          approval_sla_deadline_utc: null,
          approval_sla_status: "unknown",
          artifact_completion_ratio: 0,
          artifact_badges: [],
          report_pdf: null,
        },
        triageQuery.data ?? null,
        packageStatusQuery.data ?? null,
      ),
    [packageStatusQuery.data, selectedRun, triageQuery.data],
  );

  async function handleLoadPackageStatus(runId: string) {
    if (!workspace) return;
    setSelectedRunId(runId);
    setBusyRunId(runId);
    setError(null);
    try {
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

  async function handleLoadTriage(runId: string) {
    if (!workspace) return;
    setSelectedRunId(runId);
    setBusyRunId(runId);
    setError(null);
    try {
      const payload = await queryClient.fetchQuery({
        queryKey: queryKeys.runs.triage(workspace, runId),
        queryFn: ({ signal }) => fetchRunTriage(workspace, runId, signal),
      });
      setNotice(`Triage refreshed: ${payload.total_items} verification items loaded.`);
    } catch (err) {
      setError(toUiErrorMessage(err, "Triage fetch failed."));
    } finally {
      setBusyRunId(null);
    }
  }

  async function handleExecute(runId: string) {
    if (!workspace) return;
    setSelectedRunId(runId);
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
    setSelectedRunId(runId);
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
        decision === "approved" ? `Run ${runId} approved and continued.` : `Run ${runId} rejected.`,
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
    setSelectedRunId(runId);
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

      queryClient.setQueryData(queryKeys.runs.packageStatus(workspace, runId), nextPackageState);
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
    setSelectedRunId(runId);
    setBusyRunId(runId);
    setError(null);
    setNotice(null);
    try {
      const filename = await downloadRunArtifact(workspace, runId, artifact, fallbackFilename);
      setNotice(`Download started: ${filename}`);
    } catch (err) {
      setError(toUiErrorMessage(err, "Artifact download failed."));
    } finally {
      setBusyRunId(null);
    }
  }

  return (
    <AppShell
      activePath="/approval-center"
      title="Controlled Publish Board"
      subtitle="Queue-first operations board for verifier triage, package completeness, and controlled publish readiness."
      actions={[{ href: "/reports/new", label: "New Report Run" }]}
    >
      {created ? (
        <div className="mb-4 rounded-[1.35rem] border border-emerald-500/35 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">
          Run created ({mode === "api" ? "API" : "wizard"} mode)
          {createdRunId ? ` - ${createdRunId}` : ""}.
        </div>
      ) : null}

      {!workspace ? (
        <SubtleAlert tone="attention" title="Workspace missing">
          Once bir tenant ve project secin. New Report Run akisi workspace baglamini burada devam
          ettirir.
        </SubtleAlert>
      ) : (
        <SurfaceCard className="mb-4 border-none bg-[linear-gradient(135deg,#f8f4ed_0%,#ffffff_48%,#eef7f1_100%)]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-[11px] tracking-[0.16em] text-[color:var(--foreground-muted)] uppercase">
                Active workspace
              </p>
              <p className="text-foreground mt-2 text-[18px] font-semibold tracking-[-0.04em]">
                {workspace.tenantId} / {workspace.projectId}
              </p>
              <p className="mt-1 text-[12px] leading-5 text-[color:var(--foreground-soft)]">
                First fold shows blockers, SLA watch, and publish readiness before archive and
                passive package history.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <StatusChip tone="attention">
                <Clock3 className="size-3.5" />
                {stats.risk} SLA watch
              </StatusChip>
              <StatusChip tone="good">
                <ShieldCheck className="size-3.5" />
                {stats.publishReady} publish ready
              </StatusChip>
            </div>
          </div>
        </SurfaceCard>
      )}

      {pageError ? (
        <div className="mb-4" data-testid="approval-center-error">
          <SubtleAlert tone="critical" title="Action required">
            {pageError}
          </SubtleAlert>
        </div>
      ) : null}

      {notice ? (
        <div className="mb-4" data-testid="approval-center-notice">
          <SubtleAlert tone="good" title="Latest activity">
            {notice}
          </SubtleAlert>
        </div>
      ) : null}

      <div className="mb-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <QueueStat
          label="Immediate blockers"
          value={stats.blockers}
          detail="Triage-required veya SLA-breached runlar ilk once gorunur."
          tone={stats.blockers > 0 ? "critical" : "good"}
        />
        <QueueStat
          label="Release queue"
          value={stats.release}
          detail="Execute, review ve package handoff bekleyen aktif runlar."
          tone={stats.release > 0 ? "attention" : "neutral"}
        />
        <QueueStat
          label="Publish-ready"
          value={stats.publishReady}
          detail="Hard gate'leri gecmis ve controlled publish icin hazir runlar."
          tone={stats.publishReady > 0 ? "good" : "neutral"}
        />
        <QueueStat
          label="Archive"
          value={stats.archive}
          detail="Published veya package-complete runlar sonraki fold'a kayar."
          tone="neutral"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_23rem]">
        <div className="space-y-4">
          <QueueLane
            title="Immediate blockers"
            description="Verifier fail/unsure kümeleri ve aşılmış approval SLA olayları burada toplanır."
            runs={groupedRuns.blockers}
            busyRunId={busyRunId}
            selectedRunId={selectedRunId}
            onSelect={setSelectedRunId}
            onExecute={handleExecute}
            onLoadTriage={handleLoadTriage}
            onLoadPackageStatus={handleLoadPackageStatus}
            onPublish={handlePublish}
            onDownloadArtifact={handleDownloadArtifact}
            onHumanApproval={handleHumanApproval}
          />

          <QueueLane
            title="Release queue"
            description="Package completeness, approval decisions ve publish handoff bu kuyrukta ilerler."
            runs={groupedRuns.release}
            busyRunId={busyRunId}
            selectedRunId={selectedRunId}
            onSelect={setSelectedRunId}
            onExecute={handleExecute}
            onLoadTriage={handleLoadTriage}
            onLoadPackageStatus={handleLoadPackageStatus}
            onPublish={handlePublish}
            onDownloadArtifact={handleDownloadArtifact}
            onHumanApproval={handleHumanApproval}
          />

          <QueueLane
            title="Archive and completed packages"
            description="Published runlar ve tamamlanmis package setleri pasif izleme alanina taşınır."
            runs={groupedRuns.archive}
            busyRunId={busyRunId}
            selectedRunId={selectedRunId}
            onSelect={setSelectedRunId}
            onExecute={handleExecute}
            onLoadTriage={handleLoadTriage}
            onLoadPackageStatus={handleLoadPackageStatus}
            onPublish={handlePublish}
            onDownloadArtifact={handleDownloadArtifact}
            onHumanApproval={handleHumanApproval}
          />
        </div>

        <BlockersDrawer
          run={selectedRun}
          packageState={packageStatusQuery.data ?? null}
          triage={triageQuery.data ?? null}
          loadingPackage={packageStatusQuery.isFetching}
          loadingTriage={triageQuery.isFetching}
          blockers={selectedRun ? blockers : []}
          onRefreshPackage={async () => {
            if (selectedRunId) {
              await handleLoadPackageStatus(selectedRunId);
            }
          }}
          onRefreshTriage={async () => {
            if (selectedRunId) {
              await handleLoadTriage(selectedRunId);
            }
          }}
        />
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
