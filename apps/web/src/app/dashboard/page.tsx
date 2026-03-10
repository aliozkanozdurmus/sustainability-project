"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, Clock3, Leaf, Loader2 } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  buildApiHeaders,
  getApiBaseUrl,
  getInitialWorkspaceContext,
  persistWorkspaceContext,
  type WorkspaceContext,
} from "@/lib/api/client";

type RunListItem = {
  run_id: string;
  report_run_status: string;
  publish_ready: boolean;
  active_node: string;
  triage_required: boolean;
  started_at_utc: string | null;
  completed_at_utc: string | null;
  human_approval: string;
};

type RunListResponse = {
  items: RunListItem[];
};

function useWorkspace(): WorkspaceContext | null {
  const [workspace, setWorkspace] = useState<WorkspaceContext | null>(null);

  useEffect(() => {
    const initialWorkspace = getInitialWorkspaceContext();
    setWorkspace(initialWorkspace);
    if (initialWorkspace) {
      persistWorkspaceContext(initialWorkspace);
    }
  }, []);

  return workspace;
}

export default function DashboardPage() {
  const router = useRouter();
  const workspace = useWorkspace();
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRuns = useCallback(async () => {
    if (!workspace) {
      setRuns([]);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const apiBase = getApiBaseUrl();
      const response = await fetch(
        `${apiBase}/runs?tenant_id=${encodeURIComponent(workspace.tenantId)}&project_id=${encodeURIComponent(workspace.projectId)}&page=1&size=20`,
        { headers: buildApiHeaders(workspace.tenantId) },
      );
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as RunListResponse;
      setRuns(payload.items ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load runs.");
    } finally {
      setBusy(false);
    }
  }, [workspace]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  const metrics = useMemo(() => {
    const total = runs.length;
    const completed = runs.filter((item) =>
      item.report_run_status === "completed" || item.report_run_status === "published"
    ).length;
    const publishReady = runs.filter((item) => item.publish_ready).length;
    const triageRisk = runs.filter((item) => item.triage_required).length;
    return { total, completed, publishReady, triageRisk };
  }, [runs]);

  return (
    <AppShell
      activePath="/dashboard"
      title="Executive Sustainability Cockpit"
      subtitle="Operational run status, verifier risk, and publish readiness in a single control surface."
      actions={[
        { href: "/reports/new", label: "Create New Report" },
        { href: "/evidence-center", label: "Evidence Center" },
        { href: "/retrieval-lab", label: "Retrieval Lab" },
        { href: "/approval-center", label: "Open Approval Center" },
      ]}
    >
      <article className="relative overflow-hidden rounded-xl border shadow-sm">
        <div className="absolute inset-0">
          <Image
            src="/images/dashboard-hero.png"
            alt="Executive sustainability boardroom scene"
            fill
            sizes="100vw"
            className="object-cover opacity-30"
            priority
          />
          <div className="absolute inset-0 bg-gradient-to-r from-background/92 via-background/78 to-background/65" />
        </div>
        <div className="relative flex min-h-[250px] flex-col justify-end p-5 md:min-h-[310px] md:p-6">
          <p className="text-muted-foreground text-xs uppercase tracking-[0.16em]">
            Board Intelligence Layer
          </p>
          <p className="mt-2 max-w-2xl text-sm md:text-base">
            Live operations view is powered from backend run state, not demo KPI stubs.
          </p>
        </div>
      </article>

      {!workspace ? (
        <div className="mt-4 rounded-xl border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
          Workspace not selected. Open &quot;Create New Report&quot; and configure tenant/project first.
        </div>
      ) : (
        <div className="mt-4 rounded-xl border bg-card px-4 py-3 text-xs text-muted-foreground">
          tenant_id={workspace.tenantId} | project_id={workspace.projectId}
        </div>
      )}

      {error ? (
        <div className="mt-4 rounded-xl border border-destructive/35 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article className="rounded-xl border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <p className="text-muted-foreground text-xs uppercase tracking-[0.16em]">Total Runs</p>
            <Leaf className="text-muted-foreground h-4 w-4" />
          </div>
          <p className="mt-3 text-2xl font-semibold">{metrics.total}</p>
          <p className="mt-1 text-sm text-muted-foreground">Current workspace run count</p>
        </article>
        <article className="rounded-xl border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <p className="text-muted-foreground text-xs uppercase tracking-[0.16em]">Completed</p>
            <CheckCircle2 className="text-muted-foreground h-4 w-4" />
          </div>
          <p className="mt-3 text-2xl font-semibold">{metrics.completed}</p>
          <p className="mt-1 text-sm text-emerald-600 dark:text-emerald-300">Execution finished</p>
        </article>
        <article className="rounded-xl border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <p className="text-muted-foreground text-xs uppercase tracking-[0.16em]">Publish Ready</p>
            <Clock3 className="text-muted-foreground h-4 w-4" />
          </div>
          <p className="mt-3 text-2xl font-semibold">{metrics.publishReady}</p>
          <p className="mt-1 text-sm text-sky-600 dark:text-sky-300">Ready for publish gate</p>
        </article>
        <article className="rounded-xl border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <p className="text-muted-foreground text-xs uppercase tracking-[0.16em]">Triage Required</p>
            <AlertTriangle className="text-muted-foreground h-4 w-4" />
          </div>
          <p className="mt-3 text-2xl font-semibold">{metrics.triageRisk}</p>
          <p className="mt-1 text-sm text-amber-600 dark:text-amber-300">Verifier intervention needed</p>
        </article>
      </div>

      <article className="mt-4 rounded-xl border bg-card p-5 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Recent Runs</h2>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" onClick={() => void loadRuns()} disabled={busy || !workspace}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Refresh"}
            </Button>
            <Button
              type="button"
              onClick={() => {
                if (!workspace) {
                  router.push("/reports/new");
                  return;
                }
                router.push(
                  `/approval-center?tenantId=${encodeURIComponent(workspace.tenantId)}&projectId=${encodeURIComponent(workspace.projectId)}`,
                );
              }}
            >
              Manage Runs
            </Button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full border-separate border-spacing-y-2 text-left text-sm">
            <thead className="text-muted-foreground text-xs uppercase tracking-[0.16em]">
              <tr>
                <th className="px-3 py-2">Run ID</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Node</th>
                <th className="px-3 py-2">Human Approval</th>
                <th className="px-3 py-2">Publish Ready</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((item) => (
                <tr key={item.run_id} className="bg-muted/35">
                  <td className="rounded-l-lg px-3 py-3 text-xs">{item.run_id}</td>
                  <td className="px-3 py-3">{item.report_run_status}</td>
                  <td className="px-3 py-3">{item.active_node}</td>
                  <td className="px-3 py-3">{item.human_approval}</td>
                  <td className="rounded-r-lg px-3 py-3">{item.publish_ready ? "yes" : "no"}</td>
                </tr>
              ))}
              {runs.length === 0 ? (
                <tr>
                  <td className="rounded-lg px-3 py-4 text-sm text-muted-foreground" colSpan={5}>
                    No run data yet for this workspace.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </article>
    </AppShell>
  );
}
