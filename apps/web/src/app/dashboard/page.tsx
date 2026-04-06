"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowUpRight,
  FileStack,
  Loader2,
  RefreshCw,
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
  MiniBarChart,
  RadialMetricChart,
  SparklineArea,
  StackedBarChart,
} from "@/components/workbench-charts";

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
  const router = useRouter();
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
  const progressMetric = useMemo(
    () => overview?.metrics.find((metric) => metric.key === "publish-ready") ?? null,
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
            <StatChip label="tenant" value={workspace.tenantId} />
            <StatChip label="project" value={workspace.projectId} />
            {overview ? <StatChip label="updated" value={formatDateTime(overview.generated_at_utc)} tone="good" /> : null}
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
          <div className="grid dense-grid xl:grid-cols-[1.3fr_0.7fr]">
            <SurfaceCard className="relative overflow-hidden px-5 py-5 md:px-6 md:py-6">
              <div className="absolute inset-y-0 right-0 hidden w-[36%] overflow-hidden rounded-l-[2rem] lg:block">
                <Image
                  src="/images/dashboard-hero.png"
                  alt="Dashboard editorial scene"
                  fill
                  sizes="40vw"
                  className="object-cover opacity-28 saturate-[0.84]"
                  priority
                />
                <div className="absolute inset-0 bg-gradient-to-l from-[rgba(228,199,100,0.22)] via-transparent to-transparent" />
              </div>
              <div className="relative max-w-[62%] space-y-5 lg:max-w-[58%]">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="pill-dark">Dashboard</span>
                  <StatusChip tone={overview.hero.readiness_score >= 100 ? "good" : "attention"}>
                    {overview.hero.readiness_label}
                  </StatusChip>
                  <span className="pill-surface">{overview.hero.project_code}</span>
                </div>
                <div>
                  <p className="eyebrow">Controlled publish cockpit</p>
                  <h2 className="mt-2 text-[42px] font-semibold tracking-[-0.08em] text-foreground">
                    Welcome in, {overview.hero.company_name}
                  </h2>
                  <p className="mt-3 max-w-[42rem] text-[14px] leading-6 text-[color:var(--foreground-soft)]">
                    {overview.hero.summary}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {overview.hero.sector ? <StatChip label="sector" value={overview.hero.sector} /> : null}
                  {overview.hero.headquarters ? <StatChip label="hq" value={overview.hero.headquarters} /> : null}
                  <StatChip label="currency" value={overview.hero.reporting_currency} />
                  {overview.hero.blueprint_version ? (
                    <StatChip label="blueprint" value={overview.hero.blueprint_version} tone="attention" />
                  ) : null}
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  <MetricPill
                    label="Factory readiness"
                    value={`${overview.hero.readiness_score}%`}
                    detail="Brand kit, company profile, and launch context health."
                    tone={overview.hero.readiness_score >= 100 ? "good" : "attention"}
                  />
                  <MetricPill
                    label="Package motion"
                    value={`${Math.round((overview.pipeline.find((item) => item.lane_id === "package")?.ratio ?? 0) * 100)}%`}
                    detail="Share of runs inside package generation lanes."
                    tone="attention"
                  />
                  <MetricPill
                    label="Artifact discipline"
                    value={`${overview.artifact_health.filter((item) => item.available > 0).length}/${overview.artifact_health.length}`}
                    detail="Mandatory artifact families already materialized."
                    tone="good"
                  />
                </div>
              </div>
            </SurfaceCard>

            <SurfaceCard className="px-5 py-5">
              <SectionHeading
                eyebrow="Operator schedule"
                title="What needs action now"
                description="Derived from live run state, package status, and approval pressure."
              />
              <div className="mt-5">
                <TimelineRail
                  items={overview.schedule.map((item) => ({
                    title: item.title,
                    subtitle: item.subtitle,
                    detail: item.slot_label,
                    tone: item.status,
                  }))}
                />
              </div>
            </SurfaceCard>
          </div>

          <div className="grid dense-grid md:grid-cols-2 xl:grid-cols-4">
            {headlineMetrics.map((metric) => (
              <SurfaceCard key={metric.key} className="px-4 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="eyebrow">{metric.label}</p>
                    <p className="mt-3 text-[32px] font-semibold tracking-[-0.06em] text-foreground">{metric.display_value}</p>
                  </div>
                  <StatusChip tone={metric.status}>{metric.status}</StatusChip>
                </div>
                <p className="mt-2 text-[12px] text-[color:var(--foreground-soft)]">{metric.detail ?? "Live board metric."}</p>
                {metric.delta_text ? (
                  <p className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-[color:var(--accent-strong)]">
                    <ArrowUpRight className="size-3.5" />
                    {metric.delta_text}
                  </p>
                ) : null}
              </SurfaceCard>
            ))}
          </div>

          <div className="grid dense-grid lg:grid-cols-[0.96fr_0.96fr_0.74fr]">
            <SurfaceCard className="px-5 py-5">
              <SectionHeading
                eyebrow="Pipeline"
                title="Controlled publish progression"
                description="A compact read on where the cycle is healthy and where it is congested."
              />
              <div className="mt-5">
                <SegmentedBar
                  segments={overview.pipeline.map((lane) => ({
                    label: lane.label,
                    value: Math.round(lane.ratio * 100),
                    tone: lane.status,
                  }))}
                />
              </div>
              <div className="mt-5 space-y-3">
                {overview.pipeline.map((lane) => (
                  <div key={lane.lane_id} className="rounded-[1.3rem] border border-[color:var(--border)] bg-white/60 px-3.5 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-[13px] font-medium text-foreground">{lane.label}</p>
                        <p className="mt-1 text-[12px] text-[color:var(--foreground-soft)]">{lane.description}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-[20px] font-semibold tracking-[-0.05em] text-foreground">{Math.round(lane.ratio * 100)}%</p>
                        <p className="text-[11px] text-[color:var(--foreground-muted)]">
                          {lane.count}/{lane.total}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </SurfaceCard>

            <SurfaceCard className="px-5 py-5">
              <SectionHeading
                eyebrow="Quality trend"
                title="Run quality and launch rhythm"
                description="Recent quality evolution and throughput rhythm stay readable at a glance."
              />
              <div className="mt-4 grid gap-3 md:grid-cols-[0.58fr_0.42fr]">
                <div className="rounded-[1.35rem] border border-[color:var(--border)] bg-white/62 p-3">
                  <p className="text-[12px] font-medium text-[color:var(--foreground-soft)]">
                    {qualityMetric?.label ?? "Report quality"}
                  </p>
                  <p className="mt-1 text-[28px] font-semibold tracking-[-0.06em] text-foreground">
                    {qualityMetric?.display_value ?? "-"}
                  </p>
                  <div className="mt-3">
                    <SparklineArea points={qualityMetric?.trend.length ? qualityMetric.trend : [{ label: "0", value: 0 }]} tone={qualityMetric?.status ?? "attention"} />
                  </div>
                </div>
                <div className="rounded-[1.35rem] border border-[color:var(--border)] bg-white/62 p-3">
                  <RadialMetricChart
                    value={Math.round((progressMetric?.display_value ? Number(progressMetric.display_value) : 0) * 10)}
                    label="Publish-ready density"
                    tone="attention"
                    height={214}
                  />
                </div>
              </div>
              <div className="mt-4 rounded-[1.35rem] border border-[color:var(--border)] bg-white/62 p-3">
                <p className="text-[12px] font-medium text-[color:var(--foreground-soft)]">Launch cadence</p>
                <MiniBarChart
                  points={headlineMetrics[0]?.trend.length ? headlineMetrics[0].trend : [{ label: "0", value: 0 }]}
                  highlightIndex={(headlineMetrics[0]?.trend.length ?? 0) - 1}
                  height={128}
                />
              </div>
            </SurfaceCard>

            <SurfaceCard className="px-5 py-5">
              <SectionHeading
                eyebrow="Publish discipline"
                title="Checklist before release"
                description="The board should feel strict, not noisy."
              />
              <div className="mt-5">
                <ChecklistStack
                  items={[
                    {
                      label: "Connector sync completed",
                      detail: `${overview.connector_health.filter((item) => item.job_status === "completed").length}/${overview.connector_health.length} connectors have a completed latest job.`,
                      done: overview.connector_health.every((item) => item.job_status === "completed"),
                    },
                    {
                      label: "Verification blockers cleared",
                      detail: `${overview.risks.find((item) => item.risk_id === "verification")?.count ?? 0} FAIL items remain across recent runs.`,
                      done: (overview.risks.find((item) => item.risk_id === "verification")?.count ?? 0) === 0,
                      tone: "critical",
                    },
                    {
                      label: "Artifact families materialized",
                      detail: `${overview.artifact_health.filter((item) => item.available > 0).length} artifact types already produced.`,
                      done: overview.artifact_health.filter((item) => item.available > 0).length >= 3,
                    },
                  ]}
                />
              </div>
              <div className="mt-4">
                <SubtleAlert tone="attention" title="Publish remains controlled">
                  This board surfaces risk, freshness, and artifact completeness before a run enters the final package stage.
                </SubtleAlert>
              </div>
            </SurfaceCard>
          </div>

          <div className="grid dense-grid xl:grid-cols-[0.92fr_0.92fr_0.8fr]">
            <SurfaceCard className="px-5 py-5">
              <SectionHeading
                eyebrow="KPI spotlight"
                title="Infographic trend cards"
                description="Real metrics from the canonical layer, without invented demo values."
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
                  {spotlightMetrics.map((metric, index) => (
                    <div key={metric.key} className="rounded-[1.35rem] border border-[color:var(--border)] bg-white/62 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-[13px] font-medium text-foreground">{metric.label}</p>
                        <StatusChip tone={metric.status}>{metric.display_value}</StatusChip>
                      </div>
                      <p className="mt-1 text-[12px] text-[color:var(--foreground-soft)]">{metric.detail}</p>
                      {metric.delta_text ? (
                        <p className="mt-2 text-[11px] font-medium text-[color:var(--accent-strong)]">{metric.delta_text}</p>
                      ) : null}
                      <div className="mt-3">
                        {index % 2 === 0 ? (
                          <SparklineArea points={metric.trend.length ? metric.trend : [{ label: "0", value: 0 }]} tone={metric.status} height={98} />
                        ) : (
                          <MiniBarChart points={metric.trend.length ? metric.trend : [{ label: "0", value: 0 }]} highlightIndex={(metric.trend.length ?? 1) - 1} height={98} />
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </SurfaceCard>

            <SurfaceCard className="px-5 py-5">
              <SectionHeading
                eyebrow="Connector health"
                title="ERP ingestion discipline"
                description="SAP, Logo Tiger, and Netsis all stay visible as operational channels."
              />
              <div className="mt-4 space-y-3">
                {overview.connector_health.map((connector) => (
                  <div key={connector.connector_id} className="rounded-[1.35rem] border border-[color:var(--border)] bg-white/62 px-3.5 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[13px] font-medium text-foreground">{connector.display_name}</p>
                        <p className="mt-1 text-[12px] text-[color:var(--foreground-soft)]">
                          {connector.connector_type} • {connector.auth_mode}
                        </p>
                      </div>
                      <StatusChip tone={connector.status_tone}>{connector.job_status ?? connector.status}</StatusChip>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-[12px]">
                      <div className="rounded-[1rem] bg-white/75 px-2.5 py-2">
                        <p className="ink-muted">Records</p>
                        <p className="mt-1 font-semibold text-foreground">{connector.record_count}</p>
                      </div>
                      <div className="rounded-[1rem] bg-white/75 px-2.5 py-2">
                        <p className="ink-muted">Inserted</p>
                        <p className="mt-1 font-semibold text-foreground">{connector.inserted_count}</p>
                      </div>
                      <div className="rounded-[1rem] bg-white/75 px-2.5 py-2">
                        <p className="ink-muted">Freshness</p>
                        <p className="mt-1 font-semibold text-foreground">
                          {connector.freshness_hours !== null && connector.freshness_hours !== undefined
                            ? `${connector.freshness_hours}h`
                            : "Pending"}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </SurfaceCard>

            <div className="space-y-4">
              <SurfaceCard className="px-5 py-5">
                <SectionHeading
                  eyebrow="Risk pulse"
                  title="Verifier and freshness pressure"
                  description="Dense, quiet, and immediately readable."
                />
                <div className="mt-4 space-y-3">
                  {overview.risks.map((risk) => (
                    <SubtleAlert key={risk.risk_id} tone={risk.severity} title={`${risk.title} • ${risk.count}`}>
                      {risk.detail}
                    </SubtleAlert>
                  ))}
                </div>
              </SurfaceCard>

              <SurfaceCard className="px-5 py-5">
                <SectionHeading
                  eyebrow="Artifact readiness"
                  title="Package output mix"
                  description="Availability by mandatory artifact family."
                />
                <div className="mt-4">
                  <StackedBarChart
                    data={overview.artifact_health.map((item) => ({
                      label: item.label.split(" ")[0],
                      values: [
                        Math.round(item.completion_ratio * 100),
                        Math.max(0, 100 - Math.round(item.completion_ratio * 100)),
                        0,
                      ],
                    }))}
                    height={180}
                  />
                </div>
              </SurfaceCard>
            </div>
          </div>

          <div className="grid dense-grid xl:grid-cols-[0.78fr_1.22fr]">
            <SurfaceCard className="px-5 py-5">
              <SectionHeading
                eyebrow="Recent activity"
                title="Fresh operator signals"
                description="Sync jobs, evidence ingestion, and other live movement."
              />
              <div className="mt-5">
                <TimelineRail
                  items={overview.activity_feed.map((item) => ({
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
                eyebrow="Run queue"
                title="Recent execution board"
                description="A compact view of status, package motion, and quality score."
                action={
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => router.push("/approval-center")}
                  >
                    <FileStack className="size-4" />
                    Open board
                  </Button>
                }
              />
              {overview.run_queue.length === 0 ? (
                <div className="mt-4">
                  <EmptyState
                    title="No runs yet"
                    description="Create a new factory run to populate the recent execution board."
                  />
                </div>
              ) : (
                <div className="mt-4 overflow-x-auto soft-scrollbar">
                  <table className="min-w-full text-left text-[12px]">
                    <thead>
                      <tr className="border-b border-[color:var(--border)] text-[11px] uppercase tracking-[0.12em] text-[color:var(--foreground-muted)]">
                        <th className="px-2 py-2 font-medium">Run</th>
                        <th className="px-2 py-2 font-medium">Status</th>
                        <th className="px-2 py-2 font-medium">Package</th>
                        <th className="px-2 py-2 font-medium">Approval</th>
                        <th className="px-2 py-2 font-medium">Quality</th>
                        <th className="px-2 py-2 font-medium">Last sync</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview.run_queue.map((run) => (
                        <tr key={run.run_id} className="border-b border-[color:rgba(37,35,31,0.06)] last:border-b-0">
                          <td className="px-2 py-3">
                            <div>
                              <p className="font-medium text-foreground">{run.run_id.slice(0, 8)}</p>
                              <p className="mt-0.5 text-[11px] text-[color:var(--foreground-muted)]">{run.active_node}</p>
                            </div>
                          </td>
                          <td className="px-2 py-3">
                            <StatusChip tone={run.report_run_status === "published" ? "good" : run.publish_ready ? "attention" : "neutral"}>
                              {run.report_run_status}
                            </StatusChip>
                          </td>
                          <td className="px-2 py-3 text-[color:var(--foreground-soft)]">{run.package_status}</td>
                          <td className="px-2 py-3 text-[color:var(--foreground-soft)]">{run.human_approval}</td>
                          <td className="px-2 py-3 text-foreground">
                            {run.report_quality_score !== null && run.report_quality_score !== undefined
                              ? run.report_quality_score.toFixed(1)
                              : "-"}
                          </td>
                          <td className="px-2 py-3 text-[color:var(--foreground-soft)]">{formatDateTime(run.latest_sync_at_utc)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SurfaceCard>
          </div>

          <div className="grid dense-grid md:grid-cols-3">
            <SubtleAlert tone="good" title="Evidence-connected">
              This dashboard reads live connector jobs, documents, facts, and package outcomes instead of decorative placeholder KPI cards.
            </SubtleAlert>
            <SubtleAlert tone="attention" title="Light-only first delivery">
              Density, type scale, and shadows are tuned for the premium light experience requested in the reference direction.
            </SubtleAlert>
            <SubtleAlert tone="neutral" title="Next operation surface">
              Move into Report Factory, Evidence, Retrieval Lab, or the Publish Board without leaving the same design language.
            </SubtleAlert>
          </div>
        </>
      ) : null}
    </AppShell>
  );
}
