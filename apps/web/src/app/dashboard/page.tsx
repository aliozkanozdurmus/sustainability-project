"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  Building2,
  CalendarRange,
  FileStack,
  ShieldCheck,
  Loader2,
  RefreshCw,
  Waypoints,
} from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  buildApiHeaders,
  buildDashboardOverviewPath,
  getApiBaseUrl,
  parseJsonOrThrow,
} from "@/lib/api/client";
import { useWorkspaceContext } from "@/lib/api/workspace-store";
import {
  ChecklistStack,
  EmptyState,
  MetricPill,
  SectionHeading,
  SegmentedBar,
  ShimmerBlock,
  StatChip,
  StatusChip,
  SubtleAlert,
  SurfaceCard,
  TimelineRail,
} from "@/components/workbench-ui";
import {
  CapsuleBarChart,
  MiniBarChart,
  RadialMetricChart,
  SparklineArea,
  StackedBarChart,
} from "@/components/workbench-charts";
import { cn } from "@/lib/utils";

type Tone = "good" | "attention" | "critical" | "neutral";

type KpiTrendPoint = {
  label: string;
  value: number;
};

type DashboardMetric = {
  key: string;
  label: string;
  display_value: string;
  detail?: string | null;
  delta_text?: string | null;
  status: Tone;
  trend: KpiTrendPoint[];
};

type PipelineLane = {
  lane_id: string;
  label: string;
  count: number;
  total: number;
  ratio: number;
  status: Tone;
  description: string;
};

type ConnectorHealthItem = {
  connector_id: string;
  connector_type: string;
  display_name: string;
  status: string;
  auth_mode: string;
  last_synced_at_utc?: string | null;
  job_status?: string | null;
  current_stage?: string | null;
  record_count: number;
  inserted_count: number;
  updated_count: number;
  freshness_hours?: number | null;
  status_tone: Tone;
};

type RiskItem = {
  risk_id: string;
  title: string;
  severity: Tone;
  count: number;
  detail: string;
};

type ScheduleItem = {
  item_id: string;
  title: string;
  subtitle: string;
  slot_label: string;
  status: Tone;
  run_id?: string | null;
};

type ArtifactHealthSummary = {
  artifact_type: string;
  label: string;
  available: number;
  total_runs: number;
  completion_ratio: number;
};

type ActivityItem = {
  activity_id: string;
  title: string;
  detail: string;
  category: string;
  status: Tone;
  occurred_at_utc?: string | null;
};

type RunQueueItem = {
  run_id: string;
  report_run_status: string;
  active_node: string;
  publish_ready: boolean;
  human_approval: string;
  package_status: string;
  report_quality_score?: number | null;
  latest_sync_at_utc?: string | null;
  visual_generation_status: string;
};

type DashboardOverviewResponse = {
  hero: {
    tenant_name: string;
    company_name: string;
    project_name: string;
    project_code: string;
    sector?: string | null;
    headquarters?: string | null;
    reporting_currency: string;
    blueprint_version?: string | null;
    readiness_label: string;
    readiness_score: number;
    summary: string;
    logo_uri?: string | null;
    primary_color?: string | null;
    accent_color?: string | null;
  };
  metrics: DashboardMetric[];
  pipeline: PipelineLane[];
  connector_health: ConnectorHealthItem[];
  risks: RiskItem[];
  schedule: ScheduleItem[];
  artifact_health: ArtifactHealthSummary[];
  activity_feed: ActivityItem[];
  run_queue: RunQueueItem[];
  generated_at_utc: string;
};

function formatDateTime(value?: string | null) {
  if (!value) return "Pending";
  return new Date(value).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function shortLabel(value: string) {
  const tokens = value.split(" ");
  return tokens.length <= 2 ? value : `${tokens[0]} ${tokens[1]}`;
}

function inferReportingCycle(overview: DashboardOverviewResponse) {
  const labels = overview.metrics.flatMap((metric) => metric.trend.map((point) => point.label));
  const year = labels.find((label) => /^\d{4}$/.test(label)) ?? String(new Date().getFullYear());
  return `${year} sustainability report cycle`;
}

function toneTextClass(tone: Tone) {
  if (tone === "good") return "text-[color:var(--success)]";
  if (tone === "attention") return "text-[color:var(--warning)]";
  if (tone === "critical") return "text-[color:var(--destructive)]";
  return "text-[color:var(--foreground-soft)]";
}

function toneBarClass(tone: Tone) {
  if (tone === "good") return "bg-[color:var(--success)]";
  if (tone === "attention") return "bg-[color:var(--warning)]";
  if (tone === "critical") return "bg-[color:var(--destructive)]";
  return "bg-[color:var(--foreground-muted)]";
}

function HeroStatCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string | number;
  detail: string;
}) {
  return (
    <div className="rounded-[1.35rem] border border-[rgba(23,22,19,0.06)] bg-[linear-gradient(180deg,#f8f4ed_0%,#ffffff_100%)] px-3.5 py-3.5">
      <p className="eyebrow">{label}</p>
      <p className="mt-2 text-[28px] font-semibold tracking-[-0.06em] text-foreground">{value}</p>
      <p className="mt-1 text-[11px] leading-5 text-[color:var(--foreground-soft)]">{detail}</p>
    </div>
  );
}

function InlineProgressMetric({
  label,
  detail,
  value,
  ratio,
  tone,
}: {
  label: string;
  detail: string;
  value: string;
  ratio: number;
  tone: Tone;
}) {
  const safeRatio = Math.max(0, Math.min(1, ratio));

  return (
    <div className="rounded-[1.25rem] border border-[color:var(--border)] bg-white/78 px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[12px] font-medium text-foreground">{label}</p>
          <p className="mt-0.5 text-[11px] leading-5 text-[color:var(--foreground-soft)]">{detail}</p>
        </div>
        <span className={cn("text-[12px] font-semibold", toneTextClass(tone))}>{value}</span>
      </div>
      <div className="mt-3 h-2 rounded-full bg-[rgba(23,22,19,0.08)]">
        <div
          className={cn("h-full rounded-full transition-all", toneBarClass(tone))}
          style={{ width: `${safeRatio * 100}%` }}
        />
      </div>
    </div>
  );
}

function ConnectorRow({
  connector,
}: {
  connector: ConnectorHealthItem;
}) {
  const freshnessRatio =
    connector.freshness_hours !== null && connector.freshness_hours !== undefined
      ? Math.max(0, Math.min(1, 1 - connector.freshness_hours / 24))
      : 0;

  return (
    <div className="rounded-[1.3rem] border border-[color:var(--border)] bg-white/74 px-3.5 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[13px] font-medium text-foreground">{connector.display_name}</p>
          <p className="mt-0.5 text-[11px] leading-5 text-[color:var(--foreground-soft)]">
            {connector.connector_type} • {connector.auth_mode}
          </p>
        </div>
        <StatusChip tone={connector.status_tone}>{connector.job_status ?? connector.status}</StatusChip>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <div className="rounded-[1rem] bg-[linear-gradient(180deg,#fbf8f1_0%,#ffffff_100%)] px-2.5 py-2">
          <p className="ink-muted text-[10px] uppercase tracking-[0.12em]">Records</p>
          <p className="mt-1 text-[15px] font-semibold text-foreground">{connector.record_count}</p>
        </div>
        <div className="rounded-[1rem] bg-[linear-gradient(180deg,#fbf8f1_0%,#ffffff_100%)] px-2.5 py-2">
          <p className="ink-muted text-[10px] uppercase tracking-[0.12em]">Inserted</p>
          <p className="mt-1 text-[15px] font-semibold text-foreground">{connector.inserted_count}</p>
        </div>
        <div className="rounded-[1rem] bg-[linear-gradient(180deg,#fbf8f1_0%,#ffffff_100%)] px-2.5 py-2">
          <p className="ink-muted text-[10px] uppercase tracking-[0.12em]">Freshness</p>
          <p className="mt-1 text-[15px] font-semibold text-foreground">
            {connector.freshness_hours !== null && connector.freshness_hours !== undefined
              ? `${connector.freshness_hours}h`
              : "Pending"}
          </p>
        </div>
      </div>
      <div className="mt-3">
        <div className="flex items-center justify-between gap-3 text-[11px]">
          <span className="text-[color:var(--foreground-soft)]">Freshness budget</span>
          <span className={cn("font-semibold", toneTextClass(connector.status_tone))}>
            {connector.freshness_hours !== null && connector.freshness_hours !== undefined
              ? connector.freshness_hours <= 24
                ? "within target"
                : "stale"
              : "awaiting sync"}
          </span>
        </div>
        <div className="mt-2 h-2 rounded-full bg-[rgba(23,22,19,0.08)]">
          <div
            className={cn("h-full rounded-full", toneBarClass(connector.status_tone))}
            style={{ width: `${freshnessRatio * 100}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function MetricTile({
  metric,
  accent = false,
}: {
  metric: DashboardMetric;
  accent?: boolean;
}) {
  return (
    <SurfaceCard
      className={cn(
        "overflow-hidden px-4 py-4",
        accent &&
          "border-transparent bg-[linear-gradient(165deg,#201d1b_0%,#2d6d53_100%)] text-white shadow-[0_24px_56px_rgba(24,53,37,0.22)]",
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p
            className={cn(
              "text-[11px] font-semibold uppercase tracking-[0.14em]",
              accent ? "text-white/72" : "text-[color:var(--foreground-muted)]",
            )}
          >
            {metric.label}
          </p>
          <p className={cn("mt-2 text-[30px] font-semibold tracking-[-0.06em]", accent ? "text-white" : "text-foreground")}>
            {metric.display_value}
          </p>
        </div>
        <div
          className={cn(
            "rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em]",
            accent
              ? "border-white/12 bg-white/10 text-white"
              : metric.status === "good"
                ? "border-[rgba(31,122,74,0.12)] bg-[rgba(31,122,74,0.08)] text-[color:var(--success)]"
                : metric.status === "attention"
                  ? "border-[rgba(210,167,66,0.14)] bg-[rgba(210,167,66,0.12)] text-[color:var(--warning)]"
                  : metric.status === "critical"
                    ? "border-[rgba(191,101,90,0.14)] bg-[rgba(191,101,90,0.1)] text-[color:var(--destructive)]"
                    : "border-[rgba(23,22,19,0.08)] bg-white/72 text-[color:var(--foreground-soft)]",
          )}
        >
          {metric.status}
        </div>
      </div>

      <p className={cn("mt-2 text-[12px] leading-5", accent ? "text-white/74" : "text-[color:var(--foreground-soft)]")}>
        {metric.detail ?? "Live dashboard metric."}
      </p>
      <div className="mt-3 flex items-end justify-between gap-3">
        {metric.delta_text ? (
          <p className={cn("inline-flex items-center gap-1 text-[11px] font-medium", accent ? "text-white" : "text-[color:var(--accent-strong)]")}>
            <ArrowUpRight className="size-3.5" />
            {metric.delta_text}
          </p>
        ) : (
          <span className={cn("text-[11px] font-medium", accent ? "text-white/72" : "text-[color:var(--foreground-muted)]")}>
            live metric
          </span>
        )}
        <div className="w-[7.25rem]">
          <SparklineArea
            points={metric.trend.length ? metric.trend : [{ label: "0", value: 0 }]}
            tone={metric.status}
            height={64}
          />
        </div>
      </div>
    </SurfaceCard>
  );
}

function DashboardLoadingState() {
  return (
    <div className="space-y-4">
      <div className="grid dense-grid xl:grid-cols-[1.3fr_0.7fr]">
        <SurfaceCard className="px-5 py-5">
          <ShimmerBlock className="h-4 w-28" />
          <ShimmerBlock className="mt-3 h-12 w-72" />
          <ShimmerBlock className="mt-2 h-4 w-full" />
          <ShimmerBlock className="mt-1 h-4 w-4/5" />
          <div className="mt-5 grid gap-3 md:grid-cols-3">
            <ShimmerBlock className="h-24" />
            <ShimmerBlock className="h-24" />
            <ShimmerBlock className="h-24" />
          </div>
        </SurfaceCard>
        <SurfaceCard className="px-5 py-5">
          <ShimmerBlock className="h-4 w-24" />
          <div className="mt-4 space-y-3">
            <ShimmerBlock className="h-16" />
            <ShimmerBlock className="h-16" />
            <ShimmerBlock className="h-16" />
          </div>
        </SurfaceCard>
      </div>
      <div className="grid dense-grid md:grid-cols-2 xl:grid-cols-4">
        <ShimmerBlock className="h-28" />
        <ShimmerBlock className="h-28" />
        <ShimmerBlock className="h-28" />
        <ShimmerBlock className="h-28" />
      </div>
      <div className="grid dense-grid lg:grid-cols-[0.95fr_0.95fr_0.7fr]">
        <ShimmerBlock className="h-[19rem]" />
        <ShimmerBlock className="h-[19rem]" />
        <ShimmerBlock className="h-[19rem]" />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const workspace = useWorkspaceContext();
  const [overview, setOverview] = useState<DashboardOverviewResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    if (!workspace) {
      setOverview(null);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${getApiBaseUrl()}${buildDashboardOverviewPath(workspace)}`, {
        headers: buildApiHeaders(workspace.tenantId),
      });
      const payload = await parseJsonOrThrow<DashboardOverviewResponse>(response);
      setOverview(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard overview.");
    } finally {
      setBusy(false);
    }
  }, [workspace]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  const headlineMetrics = useMemo(() => overview?.metrics.slice(0, 4) ?? [], [overview]);
  const spotlightMetrics = useMemo(() => overview?.metrics.slice(4) ?? [], [overview]);
  const qualityMetric = useMemo(
    () => overview?.metrics.find((metric) => metric.key === "report-quality") ?? null,
    [overview],
  );
  const packageReadiness = useMemo(() => {
    if (!overview || overview.run_queue.length === 0) return 0;
    const readyCount = overview.run_queue.filter((run) => run.publish_ready).length;
    return Math.round((readyCount / overview.run_queue.length) * 100);
  }, [overview]);
  const artifactCompletion = useMemo(() => {
    if (!overview || overview.artifact_health.length === 0) return 0;
    const total = overview.artifact_health.reduce((sum, item) => sum + item.completion_ratio, 0);
    return Math.round((total / overview.artifact_health.length) * 100);
  }, [overview]);
  const laneBarPoints = useMemo(
    () =>
      overview?.pipeline.map((lane) => ({
        label: shortLabel(lane.label),
        value: lane.count,
      })) ?? [],
    [overview],
  );
  const reportingCycle = useMemo(() => (overview ? inferReportingCycle(overview) : "Reporting cycle"), [overview]);
  const freshConnectorCount = useMemo(
    () =>
      overview?.connector_health.filter(
        (connector) =>
          connector.freshness_hours !== null &&
          connector.freshness_hours !== undefined &&
          connector.freshness_hours <= 24,
      ).length ?? 0,
    [overview],
  );
  const artifactReadyCount = useMemo(
    () => overview?.artifact_health.filter((artifact) => artifact.completion_ratio >= 1).length ?? 0,
    [overview],
  );
  const publishedCount = useMemo(
    () => overview?.run_queue.filter((run) => run.report_run_status === "published").length ?? 0,
    [overview],
  );
  const criticalRiskCount = useMemo(
    () => overview?.risks.filter((risk) => risk.severity === "critical" || risk.severity === "attention").length ?? 0,
    [overview],
  );
  const nextScheduleItem = useMemo(() => overview?.schedule[0] ?? null, [overview]);
  const currentRun = useMemo(() => overview?.run_queue[0] ?? null, [overview]);
  const connectorLoadPoints = useMemo(
    () =>
      overview?.connector_health.map((connector) => ({
        label:
          connector.display_name
            .replace(" Sustainability", "")
            .replace(" SQL View", "")
            .split(" ")
            .slice(0, 1)
            .join(" ") || connector.display_name,
        value: connector.record_count,
      })) ?? [],
    [overview],
  );

  return (
    <AppShell
      activePath="/dashboard"
      title="Executive Report Factory"
      subtitle="A premium operating surface for connector freshness, verification pressure, package quality, and controlled publish."
      actions={[
        { href: "/reports/new", label: "Launch New Run" },
        { href: "/approval-center", label: "Open Publish Board" },
      ]}
    >
      {!workspace ? (
        <SurfaceCard className="overflow-hidden px-5 py-6">
          <SectionHeading
            eyebrow="Workspace setup"
            title="Start with a configured tenant and project"
            description="Bootstrap a workspace first so the board can pull live connectors, evidence, and package telemetry."
          />
          <div className="mt-5 flex flex-wrap gap-3">
            <Button asChild>
              <Link href="/reports/new">Create workspace</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href="/evidence-center">Go to evidence center</Link>
            </Button>
          </div>
        </SurfaceCard>
      ) : null}

      {workspace ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2">
            {overview ? <StatChip label="project" value={overview.hero.project_code} tone="good" /> : null}
            {overview?.hero.blueprint_version ? <StatChip label="blueprint" value={overview.hero.blueprint_version} /> : null}
            {overview ? <StatChip label="updated" value={formatDateTime(overview.generated_at_utc)} /> : null}
          </div>
          <Button type="button" variant="outline" onClick={() => void loadOverview()} disabled={busy}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
            Refresh board
          </Button>
        </div>
      ) : null}

      {error ? (
        <SubtleAlert tone="critical" title="Dashboard unavailable">
          {error}
        </SubtleAlert>
      ) : null}

      {workspace && busy && !overview ? <DashboardLoadingState /> : null}

      {workspace && overview ? (
        <>
          <div className="grid dense-grid xl:grid-cols-[1.18fr_0.82fr]">
            <SurfaceCard className="overflow-hidden px-5 py-5 md:px-6 md:py-6">
              <div className="flex flex-col gap-5">
                <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
                  <div className="max-w-3xl">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="pill-dark">Executive desk</span>
                      <StatusChip
                        tone={
                          overview.hero.readiness_score >= 75
                            ? "good"
                            : overview.hero.readiness_score >= 50
                              ? "attention"
                              : "critical"
                        }
                      >
                        {overview.hero.readiness_label}
                      </StatusChip>
                      {overview.hero.primary_color ? (
                        <span className="pill-surface">
                          brand
                          <span
                            className="ml-2 inline-block size-2.5 rounded-full"
                            style={{ backgroundColor: overview.hero.primary_color }}
                          />
                          {overview.hero.accent_color ? (
                            <span
                              className="ml-1 inline-block size-2.5 rounded-full"
                              style={{ backgroundColor: overview.hero.accent_color }}
                            />
                          ) : null}
                        </span>
                      ) : null}
                    </div>
                    <h2 className="mt-4 text-[34px] font-semibold tracking-[-0.075em] text-foreground md:text-[42px]">
                      {reportingCycle}
                    </h2>
                    <p className="mt-2 flex flex-wrap items-center gap-2 text-[13px] font-medium text-[color:var(--foreground-soft)]">
                      <Building2 className="size-4 text-[color:var(--foreground-muted)]" />
                      <span>{overview.hero.company_name}</span>
                      {overview.hero.sector ? <span>• {overview.hero.sector}</span> : null}
                      {overview.hero.headquarters ? <span>• {overview.hero.headquarters}</span> : null}
                    </p>
                    <p className="mt-3 max-w-2xl text-[12px] leading-6 text-[color:var(--foreground-soft)]">
                      {overview.hero.summary}
                    </p>
                  </div>

                  <div className="metric-grid sm:grid-cols-3 xl:min-w-[23.5rem]">
                    <HeroStatCard
                      label="Readiness"
                      value={`${overview.hero.readiness_score}%`}
                      detail={overview.hero.readiness_label}
                    />
                    <HeroStatCard
                      label="Publish ready"
                      value={`${packageReadiness}%`}
                      detail="Runs already cleared for release."
                    />
                    <HeroStatCard
                      label="Artifacts ready"
                      value={`${artifactCompletion}%`}
                      detail="Mandatory package families materialized."
                    />
                  </div>
                </div>

                <div className="grid gap-4 xl:grid-cols-[1.08fr_0.92fr]">
                  <div className="rounded-[1.8rem] bg-[linear-gradient(165deg,#1f1d1b_0%,#2b2a27_100%)] px-4 py-4 text-white shadow-[0_24px_52px_rgba(31,27,24,0.18)]">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/70">
                          Cycle choreography
                        </p>
                        <p className="mt-1 text-[18px] font-semibold tracking-[-0.04em] text-white">
                          From sync to controlled publish
                        </p>
                      </div>
                      <p className="text-[11px] text-white/66">
                        {overview.pipeline.length} live lanes derived from run and package telemetry.
                      </p>
                    </div>
                    <div className="mt-4">
                      <SegmentedBar
                        segments={overview.pipeline.map((lane) => ({
                          label: lane.label,
                          value: Math.round(lane.ratio * 100),
                          tone: lane.status,
                        }))}
                      />
                    </div>
                    <div className="mt-4 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(11rem,1fr))]">
                      {overview.pipeline.map((lane) => (
                        <div
                          key={lane.lane_id}
                          className="rounded-[1.2rem] border border-white/10 bg-white/8 px-3 py-3"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-[12px] font-medium text-white">{lane.label}</p>
                            <span className="text-[16px] font-semibold tracking-[-0.04em] text-white">{lane.count}</span>
                          </div>
                          <p className="mt-1 text-[11px] leading-5 text-white/66">{lane.description}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-[1.8rem] border border-[rgba(23,22,19,0.06)] bg-[linear-gradient(180deg,#f7f1e6_0%,#ffffff_100%)] px-4 py-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="eyebrow">Board facts</p>
                        <p className="mt-1 text-[17px] font-semibold tracking-[-0.04em] text-foreground">
                          Quiet signal summary
                        </p>
                      </div>
                      <ShieldCheck className="size-4 text-[color:var(--accent-strong)]" />
                    </div>
                    <div className="mt-4 metric-grid sm:grid-cols-2">
                      <InlineProgressMetric
                        label="Connector freshness"
                        detail={`${freshConnectorCount}/${overview.connector_health.length} channels synced within 24h`}
                        value={`${freshConnectorCount}/${overview.connector_health.length}`}
                        ratio={overview.connector_health.length ? freshConnectorCount / overview.connector_health.length : 0}
                        tone={freshConnectorCount === overview.connector_health.length ? "good" : "attention"}
                      />
                      <InlineProgressMetric
                        label="Artifact manifest"
                        detail={`${artifactReadyCount}/${overview.artifact_health.length} mandatory families complete`}
                        value={`${artifactReadyCount}/${overview.artifact_health.length}`}
                        ratio={overview.artifact_health.length ? artifactReadyCount / overview.artifact_health.length : 0}
                        tone={artifactReadyCount === overview.artifact_health.length ? "good" : "attention"}
                      />
                      <InlineProgressMetric
                        label="Release posture"
                        detail={`${publishedCount} published • ${overview.run_queue.length - publishedCount} still in motion`}
                        value={`${publishedCount}`}
                        ratio={overview.run_queue.length ? publishedCount / overview.run_queue.length : 0}
                        tone={publishedCount > 0 ? "good" : "neutral"}
                      />
                      <InlineProgressMetric
                        label="Risk ledger"
                        detail={`${criticalRiskCount} active warning clusters across verifier and sync health`}
                        value={`${criticalRiskCount}`}
                        ratio={overview.risks.length ? criticalRiskCount / overview.risks.length : 0}
                        tone={criticalRiskCount === 0 ? "good" : "attention"}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </SurfaceCard>

            <div className="grid dense-grid">
              <SurfaceCard className="px-5 py-5">
                <SectionHeading
                  eyebrow="Release desk"
                  title="What ships next"
                  description="A denser control panel for package readiness, board actions, and next movement."
                  action={
                    <Button asChild variant="outline">
                      <Link href="/approval-center">
                        <FileStack className="size-4" />
                        Open board
                      </Link>
                    </Button>
                  }
                />
                <div className="mt-4 grid gap-4 md:grid-cols-[0.44fr_0.56fr] xl:grid-cols-1">
                  <div className="rounded-[1.55rem] border border-[color:var(--border)] bg-[linear-gradient(180deg,#faf7f0_0%,#ffffff_100%)] p-3">
                    <RadialMetricChart
                      value={packageReadiness}
                      label="publish ready"
                      tone={packageReadiness >= 70 ? "good" : packageReadiness >= 40 ? "attention" : "critical"}
                      height={214}
                    />
                  </div>
                  <div className="space-y-3">
                    <div className="rounded-[1.35rem] border border-[color:var(--border)] bg-white/76 px-3.5 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-[12px] font-medium text-foreground">
                            {nextScheduleItem?.title ?? "No scheduled actions"}
                          </p>
                          <p className="mt-1 text-[11px] leading-5 text-[color:var(--foreground-soft)]">
                            {nextScheduleItem?.subtitle ?? "New release activity will surface here once a run is active."}
                          </p>
                        </div>
                        <CalendarRange className="size-4 text-[color:var(--foreground-muted)]" />
                      </div>
                      <div className="mt-3 flex items-center justify-between gap-3 rounded-[1rem] bg-[linear-gradient(180deg,#f8f3ea_0%,#ffffff_100%)] px-3 py-2">
                        <span className="text-[11px] font-medium text-[color:var(--foreground-soft)]">Next slot</span>
                        <span className="text-[12px] font-semibold text-foreground">
                          {nextScheduleItem?.slot_label ?? "Pending"}
                        </span>
                      </div>
                    </div>

                    <ChecklistStack
                      items={[
                        {
                          label: "Connector channels within freshness budget",
                          detail: `${freshConnectorCount}/${overview.connector_health.length} live feeds are inside the 24h target.`,
                          done: freshConnectorCount === overview.connector_health.length,
                          tone: freshConnectorCount === overview.connector_health.length ? "good" : "attention",
                        },
                        {
                          label: "Verifier and sync blockers cleared",
                          detail: `${criticalRiskCount} warning clusters remain across risk surfaces.`,
                          done: criticalRiskCount === 0,
                          tone: criticalRiskCount === 0 ? "good" : "attention",
                        },
                        {
                          label: "Mandatory package artifacts materialized",
                          detail: `${artifactReadyCount}/${overview.artifact_health.length} package families are ready for release.`,
                          done: artifactReadyCount === overview.artifact_health.length,
                          tone: artifactReadyCount === overview.artifact_health.length ? "good" : "attention",
                        },
                      ]}
                    />
                  </div>
                </div>
              </SurfaceCard>

              <SurfaceCard className="px-5 py-5">
                <SectionHeading
                  eyebrow="Connector load"
                  title="ERP intake profile"
                  description="A quick visual read on data pulled from SAP, Logo Tiger, and Netsis."
                />
                {connectorLoadPoints.length === 0 ? (
                  <div className="mt-4">
                    <EmptyState title="No connector traffic" description="Sync connectors to activate the intake profile." />
                  </div>
                ) : (
                  <div className="mt-4 rounded-[1.55rem] border border-[color:var(--border)] bg-[linear-gradient(180deg,#faf7f0_0%,#ffffff_100%)] p-3">
                    <CapsuleBarChart
                      points={connectorLoadPoints}
                      highlightIndex={Math.max(0, connectorLoadPoints.length - 1)}
                      height={178}
                    />
                  </div>
                )}
              </SurfaceCard>
            </div>
          </div>

          <div className="grid dense-grid md:grid-cols-2 xl:grid-cols-4">
            {headlineMetrics.map((metric, index) => (
              <MetricTile key={metric.key} metric={metric} accent={index === 0} />
            ))}
          </div>

          <div className="grid dense-grid xl:grid-cols-[1.06fr_0.94fr_0.82fr]">
            <SurfaceCard className="px-5 py-5">
              <SectionHeading
                eyebrow="Factory analytics"
                title="Readiness, quality, and package motion"
                description="More editorial, less admin-table. The board reads as outcomes first."
              />
              <div className="mt-4 grid gap-4 lg:grid-cols-[0.58fr_0.42fr]">
                <div className="space-y-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <MetricPill
                      label="Report quality"
                      value={qualityMetric?.display_value ?? "-"}
                      detail={qualityMetric?.detail ?? "Average package quality across recent runs."}
                      tone={qualityMetric?.status ?? "good"}
                    />
                    <MetricPill
                      label="Published runs"
                      value={String(publishedCount)}
                      detail={`${overview.run_queue.length} tracked runs in the recent execution board.`}
                      tone={publishedCount > 0 ? "good" : "neutral"}
                    />
                  </div>
                  <div className="rounded-[1.55rem] border border-[color:var(--border)] bg-[linear-gradient(180deg,#faf7f0_0%,#ffffff_100%)] p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="eyebrow">Pipeline pressure</p>
                        <p className="mt-1 text-[16px] font-semibold tracking-[-0.03em] text-foreground">
                          Current lane distribution
                        </p>
                      </div>
                      <Waypoints className="size-4 text-[color:var(--foreground-muted)]" />
                    </div>
                    <div className="mt-4">
                      <CapsuleBarChart
                        points={laneBarPoints.length ? laneBarPoints : [{ label: "None", value: 0 }]}
                        highlightIndex={Math.max(0, laneBarPoints.length - 1)}
                        height={220}
                      />
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  {overview.pipeline.map((lane) => (
                    <InlineProgressMetric
                      key={lane.lane_id}
                      label={lane.label}
                      detail={lane.description}
                      value={`${Math.round(lane.ratio * 100)}%`}
                      ratio={lane.ratio}
                      tone={lane.status}
                    />
                  ))}
                </div>
              </div>
            </SurfaceCard>

            <SurfaceCard className="px-5 py-5">
              <SectionHeading
                eyebrow="Connector discipline"
                title="ERP channels stay readable"
                description="Each connector gets a calm, dense ledger rather than a raw status dump."
              />
              <div className="mt-4 space-y-3">
                {overview.connector_health.map((connector) => (
                  <ConnectorRow key={connector.connector_id} connector={connector} />
                ))}
              </div>
            </SurfaceCard>

            <SurfaceCard className="px-5 py-5">
              <SectionHeading
                eyebrow="Artifact manifest"
                title="Package anatomy"
                description="Final PDF plus the evidence-bearing files behind controlled publish."
              />
              <div className="mt-4 rounded-[1.55rem] border border-[color:var(--border)] bg-[linear-gradient(180deg,#faf7f0_0%,#ffffff_100%)] p-3">
                <StackedBarChart
                  data={overview.artifact_health.map((item) => ({
                    label: item.label.split(" ")[0],
                    values: [
                      Math.round(item.completion_ratio * 100),
                      Math.max(0, 100 - Math.round(item.completion_ratio * 100)),
                      0,
                    ],
                  }))}
                  height={188}
                />
              </div>
              <div className="mt-4 space-y-2.5">
                {overview.artifact_health.map((item) => (
                  <div
                    key={item.artifact_type}
                    className="flex items-center justify-between gap-3 rounded-[1.2rem] border border-[color:var(--border)] bg-white/74 px-3 py-2.5"
                  >
                    <div className="min-w-0">
                      <p className="text-[12px] font-medium text-foreground">{item.label}</p>
                      <p className="mt-0.5 text-[11px] text-[color:var(--foreground-soft)]">
                        {item.available}/{item.total_runs} runs
                      </p>
                    </div>
                    <StatusChip tone={item.completion_ratio >= 1 ? "good" : "attention"}>
                      {Math.round(item.completion_ratio * 100)}%
                    </StatusChip>
                  </div>
                ))}
              </div>
            </SurfaceCard>
          </div>

          <div className="grid dense-grid xl:grid-cols-[1.03fr_0.97fr_0.82fr]">
            <SurfaceCard className="px-5 py-5">
              <SectionHeading
                eyebrow="KPI spotlight"
                title="Infographic metric deck"
                description="Canonical KPI snapshots turned into compact signal cards."
              />
              {spotlightMetrics.length === 0 ? (
                <div className="mt-4">
                  <EmptyState
                    title="No KPI snapshots yet"
                    description="Sync connectors and run the factory once to light up the metric spotlight deck."
                  />
                </div>
              ) : (
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {spotlightMetrics.slice(0, 4).map((metric, index) => (
                    <div
                      key={metric.key}
                      className={cn(
                        "rounded-[1.45rem] border p-3",
                        index === 0
                          ? "border-transparent bg-[linear-gradient(165deg,#221f1c_0%,#325f4b_100%)] text-white shadow-[0_18px_42px_rgba(30,39,32,0.18)]"
                          : "border-[color:var(--border)] bg-white/68",
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className={cn("text-[13px] font-medium", index === 0 ? "text-white" : "text-foreground")}>
                          {metric.label}
                        </p>
                        <StatusChip tone={metric.status}>{metric.display_value}</StatusChip>
                      </div>
                      <p
                        className={cn(
                          "mt-1 text-[11px] leading-5",
                          index === 0 ? "text-white/72" : "text-[color:var(--foreground-soft)]",
                        )}
                      >
                        {metric.detail}
                      </p>
                      <div className="mt-3">
                        {index % 2 === 0 ? (
                          <SparklineArea
                            points={metric.trend.length ? metric.trend : [{ label: "0", value: 0 }]}
                            tone={metric.status}
                            height={94}
                          />
                        ) : (
                          <MiniBarChart
                            points={metric.trend.length ? metric.trend : [{ label: "0", value: 0 }]}
                            highlightIndex={(metric.trend.length || 1) - 1}
                            height={94}
                          />
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </SurfaceCard>

            <SurfaceCard className="px-5 py-5">
              <SectionHeading
                eyebrow="Risk and movement"
                title="What changed most recently"
                description="Risk clusters stay separate from operational activity, but live in the same board zone."
              />
              <div className="mt-4 space-y-3">
                {overview.risks.map((risk) => (
                  <SubtleAlert key={risk.risk_id} tone={risk.severity} title={`${risk.title} • ${risk.count}`}>
                    {risk.detail}
                  </SubtleAlert>
                ))}
              </div>
              <div className="soft-divider mt-4" />
              <div className="mt-4">
                <TimelineRail
                  items={overview.activity_feed.slice(0, 5).map((item) => ({
                    title: item.title,
                    subtitle: item.detail,
                    detail: `${item.category} • ${formatDateTime(item.occurred_at_utc)}`,
                    tone: item.status,
                  }))}
                />
              </div>
            </SurfaceCard>

            <SurfaceCard className="px-5 py-5">
              <SectionHeading
                eyebrow="Execution board"
                title="Recent runs"
                description="Run cards read better than a wide admin table at this density."
              />
              {overview.run_queue.length === 0 ? (
                <div className="mt-4">
                  <EmptyState
                    title="No runs yet"
                    description="Create a new factory run to populate the recent execution board."
                  />
                </div>
              ) : (
                <div className="mt-4 space-y-3">
                  {overview.run_queue.map((run) => (
                    <div
                      key={run.run_id}
                      className="rounded-[1.35rem] border border-[color:var(--border)] bg-[linear-gradient(180deg,#fbf8f1_0%,#ffffff_100%)] px-3.5 py-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-[13px] font-medium text-foreground">Run {run.run_id.slice(0, 8)}</p>
                          <p className="mt-0.5 text-[11px] leading-5 text-[color:var(--foreground-soft)]">
                            {run.active_node}
                          </p>
                        </div>
                        <StatusChip
                          tone={
                            run.report_run_status === "published"
                              ? "good"
                              : run.publish_ready
                                ? "attention"
                                : "neutral"
                          }
                        >
                          {run.report_run_status}
                        </StatusChip>
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-2">
                        <div className="rounded-[1rem] bg-white/80 px-2.5 py-2">
                          <p className="ink-muted text-[10px] uppercase tracking-[0.12em]">Package</p>
                          <p className="mt-1 text-[13px] font-semibold text-foreground">{run.package_status}</p>
                        </div>
                        <div className="rounded-[1rem] bg-white/80 px-2.5 py-2">
                          <p className="ink-muted text-[10px] uppercase tracking-[0.12em]">Approval</p>
                          <p className="mt-1 text-[13px] font-semibold text-foreground">{run.human_approval}</p>
                        </div>
                        <div className="rounded-[1rem] bg-white/80 px-2.5 py-2">
                          <p className="ink-muted text-[10px] uppercase tracking-[0.12em]">Quality</p>
                          <p className="mt-1 text-[13px] font-semibold text-foreground">
                            {run.report_quality_score !== null && run.report_quality_score !== undefined
                              ? run.report_quality_score.toFixed(1)
                              : "-"}
                          </p>
                        </div>
                        <div className="rounded-[1rem] bg-white/80 px-2.5 py-2">
                          <p className="ink-muted text-[10px] uppercase tracking-[0.12em]">Last sync</p>
                          <p className="mt-1 text-[13px] font-semibold text-foreground">
                            {formatDateTime(run.latest_sync_at_utc)}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {currentRun ? (
                <div className="mt-4 rounded-[1.3rem] border border-[rgba(45,109,83,0.14)] bg-[rgba(45,109,83,0.08)] px-3 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[12px] font-semibold text-[color:var(--accent-strong)]">Current leading run</p>
                      <p className="mt-0.5 text-[11px] leading-5 text-[color:var(--foreground-soft)]">
                        visual generation: {currentRun.visual_generation_status}
                      </p>
                    </div>
                    <ArrowRight className="size-4 text-[color:var(--accent-strong)]" />
                  </div>
                </div>
              ) : null}
            </SurfaceCard>
          </div>
        </>
      ) : null}
    </AppShell>
  );
}
