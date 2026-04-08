"use client";

// Bu sayfa, ERP onboarding akisini setup yuzeyinde toplar.

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, Loader2, PlayCircle, RefreshCw, ShieldCheck, Wrench } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  FormField,
  SectionHeading,
  StatusChip,
  SubtleAlert,
  SurfaceCard,
  fieldClassName,
} from "@/components/workbench-ui";
import { buildApiHeaders, getApiBaseUrl, parseJsonOrThrow } from "@/lib/api/client";
import { useWorkspaceContext } from "@/lib/api/workspace-store";

type HealthMetric = {
  key: string;
  label: string;
  score: number;
  status: string;
  detail: string;
};

type IntegrationSummary = {
  id: string;
  connector_type: string;
  display_name: string;
  status: string;
  support_tier: "certified" | "beta" | "unsupported";
  certified_variant: string | null;
  product_version: string | null;
  health_band: "green" | "amber" | "red";
  last_discovered_at: string | null;
  last_preflight_at: string | null;
  last_preview_sync_at: string | null;
  last_synced_at: string | null;
  assigned_agent_status: string | null;
};

type WorkspaceContextResponse = {
  integrations: IntegrationSummary[];
};

type IntegrationDetailResponse = {
  id: string;
  connector_type: string;
  display_name: string;
  auth_mode: string;
  base_url: string | null;
  resource_path: string | null;
  status: string;
  mapping_version: string;
  certified_variant: string | null;
  product_version: string | null;
  support_tier: "certified" | "beta" | "unsupported";
  connectivity_mode: string;
  credential_ref: string | null;
  health_band: "green" | "amber" | "red";
  health_status: {
    score: number;
    band: "green" | "amber" | "red";
    metrics: HealthMetric[];
    operator_message: string;
    support_hint: string;
    recommended_action: string;
    retryable: boolean;
    support_matrix_version: string;
  } | null;
  assigned_agent_id: string | null;
  normalization_policy: Record<string, unknown>;
  connection_profile: Record<string, unknown>;
};

type ConnectorOperationResponse = {
  operation_id: string;
  operation_type: string;
  status: string;
  current_stage: string;
  support_tier: "certified" | "beta" | "unsupported";
  health_band: "green" | "amber" | "red";
  operator_message: string | null;
  support_hint: string | null;
  recommended_action: string | null;
  retryable: boolean;
  error_code: string | null;
  error_message: string | null;
  result: Record<string, unknown>;
  diagnostics: Record<string, unknown>;
  artifact: {
    artifact_id: string;
    filename: string;
    download_path: string;
  } | null;
};

type IntegrationFormState = {
  credentialRef: string;
  certifiedVariant: string;
  productVersion: string;
  serviceUrl: string;
  resourcePath: string;
  host: string;
  companyCode: string;
  firmCode: string;
  databaseName: string;
  sqlViewName: string;
  viewSchema: string;
  authMethod: string;
  username: string;
  instanceName: string;
};

const EMPTY_FORM: IntegrationFormState = {
  credentialRef: "",
  certifiedVariant: "",
  productVersion: "",
  serviceUrl: "",
  resourcePath: "",
  host: "",
  companyCode: "",
  firmCode: "",
  databaseName: "",
  sqlViewName: "",
  viewSchema: "",
  authMethod: "",
  username: "",
  instanceName: "",
};

function toneFromBand(band: "green" | "amber" | "red") {
  if (band === "green") {
    return "good" as const;
  }
  if (band === "amber") {
    return "attention" as const;
  }
  return "critical" as const;
}

function buildFormState(detail: IntegrationDetailResponse): IntegrationFormState {
  const profile = detail.connection_profile ?? {};
  return {
    credentialRef: detail.credential_ref ?? "",
    certifiedVariant: detail.certified_variant ?? "",
    productVersion: detail.product_version ?? "",
    serviceUrl: String(profile.service_url ?? ""),
    resourcePath: String(profile.resource_path ?? detail.resource_path ?? ""),
    host: String(profile.host ?? ""),
    companyCode: String(profile.company_code ?? ""),
    firmCode: String(profile.firm_code ?? ""),
    databaseName: String(profile.database_name ?? ""),
    sqlViewName: String(profile.sql_view_name ?? ""),
    viewSchema: String(profile.view_schema ?? ""),
    authMethod: String(profile.auth_method ?? detail.auth_mode ?? ""),
    username: String(profile.username ?? ""),
    instanceName: String(profile.instance_name ?? ""),
  };
}

export default function IntegrationsSetupPage() {
  const workspace = useWorkspaceContext();
  const [summaries, setSummaries] = useState<IntegrationSummary[]>([]);
  const [selectedIntegrationId, setSelectedIntegrationId] = useState<string | null>(null);
  const [detail, setDetail] = useState<IntegrationDetailResponse | null>(null);
  const [form, setForm] = useState<IntegrationFormState>(EMPTY_FORM);
  const [latestOperation, setLatestOperation] = useState<ConnectorOperationResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selectedSummary = useMemo(
    () => summaries.find((item) => item.id === selectedIntegrationId) ?? null,
    [selectedIntegrationId, summaries],
  );

  const loadWorkspaceContext = useCallback(async (selectFirst = false) => {
    if (!workspace) {
      return;
    }
    const apiBase = getApiBaseUrl();
    const payload = await parseJsonOrThrow<WorkspaceContextResponse>(
      await fetch(
        `${apiBase}/catalog/workspace-context?tenant_id=${encodeURIComponent(workspace.tenantId)}&project_id=${encodeURIComponent(workspace.projectId)}`,
        { headers: buildApiHeaders(workspace.tenantId) },
      ),
    );
    setSummaries(payload.integrations);
    if (selectFirst) {
      setSelectedIntegrationId((current) => current ?? payload.integrations[0]?.id ?? null);
    }
  }, [workspace]);

  const loadIntegrationDetail = useCallback(async (integrationId: string) => {
    if (!workspace) {
      return;
    }
    const apiBase = getApiBaseUrl();
    const payload = await parseJsonOrThrow<IntegrationDetailResponse>(
      await fetch(
        `${apiBase}/integrations/connectors/${encodeURIComponent(integrationId)}?tenant_id=${encodeURIComponent(workspace.tenantId)}&project_id=${encodeURIComponent(workspace.projectId)}`,
        { headers: buildApiHeaders(workspace.tenantId) },
      ),
    );
    setDetail(payload);
    setForm(buildFormState(payload));
  }, [workspace]);

  useEffect(() => {
    if (!workspace) {
      return;
    }
    void loadWorkspaceContext(true).catch((cause: unknown) => {
      setError(cause instanceof Error ? cause.message : "Workspace context could not be loaded.");
    });
  }, [loadWorkspaceContext, workspace]);

  useEffect(() => {
    if (!selectedIntegrationId) {
      setDetail(null);
      setForm(EMPTY_FORM);
      return;
    }
    void loadIntegrationDetail(selectedIntegrationId).catch((cause: unknown) => {
      setError(cause instanceof Error ? cause.message : "Integration detail could not be loaded.");
    });
  }, [loadIntegrationDetail, selectedIntegrationId, workspace]);

  async function runOperation(path: string, body: Record<string, unknown>) {
    if (!workspace || !selectedIntegrationId) {
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const apiBase = getApiBaseUrl();
      const payload = await parseJsonOrThrow<ConnectorOperationResponse>(
        await fetch(`${apiBase}${path}`, {
          method: "POST",
          headers: buildApiHeaders(workspace.tenantId),
          body: JSON.stringify(body),
        }),
      );
      setLatestOperation(payload);
      await loadWorkspaceContext();
      await loadIntegrationDetail(selectedIntegrationId);
      setNotice(payload.operator_message ?? "Operation completed.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Connector operation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveProfile() {
    if (!workspace || !detail) {
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const apiBase = getApiBaseUrl();
      const payload = await parseJsonOrThrow<IntegrationDetailResponse>(
        await fetch(`${apiBase}/integrations/connectors`, {
          method: "POST",
          headers: buildApiHeaders(workspace.tenantId),
          body: JSON.stringify({
            tenant_id: workspace.tenantId,
            project_id: workspace.projectId,
            connector_type: detail.connector_type,
            display_name: detail.display_name,
            auth_mode: detail.auth_mode,
            base_url: detail.base_url,
            resource_path: detail.resource_path,
            mapping_version: detail.mapping_version,
            certified_variant: form.certifiedVariant,
            product_version: form.productVersion,
            connectivity_mode: detail.connectivity_mode,
            credential_ref: form.credentialRef,
            assigned_agent_id: detail.assigned_agent_id,
            connection_profile: {
              service_url: form.serviceUrl || undefined,
              resource_path: form.resourcePath || undefined,
              host: form.host || undefined,
              company_code: form.companyCode || undefined,
              firm_code: form.firmCode || undefined,
              database_name: form.databaseName || undefined,
              sql_view_name: form.sqlViewName || undefined,
              view_schema: form.viewSchema || undefined,
              auth_method: form.authMethod || undefined,
              username: form.username || undefined,
              instance_name: form.instanceName || undefined,
            },
          }),
        }),
      );
      setDetail(payload);
      setForm(buildFormState(payload));
      await loadWorkspaceContext();
      setNotice("Connector profile saved. You can continue with discovery.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Connector profile could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  const previewRows = Array.isArray(latestOperation?.result.preview_rows)
    ? (latestOperation?.result.preview_rows as Array<Record<string, unknown>>)
    : [];

  return (
    <AppShell
      activePath="/integrations/setup"
      title="ERP Integrations Setup"
      subtitle="Discover topology, run auth preflight, validate 20-record preview sync, and activate certified ERP connectors without raw JSON."
      actions={[{ href: "/reports/new", label: "Back to Launchpad" }]}
    >
      {!workspace ? (
        <EmptyState
          title="Workspace gerekli"
          description="Önce bir tenant/project seçin veya reports/new ekranından workspace bootstrap işlemini tamamlayın."
        />
      ) : (
        <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
          <SurfaceCard className="space-y-4 p-5">
            <SectionHeading eyebrow="Connectors" title="Certified Support Surface" description="SAP OData, Logo Tiger SQL View ve Netsis REST onboarding durumlari." />
            <div className="space-y-3">
              {summaries.map((integration) => (
                <button
                  key={integration.id}
                  type="button"
                  onClick={() => setSelectedIntegrationId(integration.id)}
                  className="w-full rounded-[1.4rem] border border-[color:var(--border)] bg-white/82 px-4 py-3 text-left"
                  data-testid={`integration-card-${integration.connector_type}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[13px] font-semibold text-foreground">{integration.display_name}</p>
                      <p className="mt-1 text-[12px] text-[color:var(--foreground-soft)]">
                        {integration.certified_variant ?? "variant pending"} | {integration.product_version ?? "version pending"}
                      </p>
                    </div>
                    <StatusChip tone={toneFromBand(integration.health_band)}>{integration.health_band}</StatusChip>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-[color:var(--foreground-muted)]">
                    <span>tier: {integration.support_tier}</span>
                    <span>status: {integration.status}</span>
                    <span>agent: {integration.assigned_agent_status ?? "unassigned"}</span>
                  </div>
                </button>
              ))}
            </div>
          </SurfaceCard>

          <div className="space-y-4">
            {!detail || !selectedSummary ? (
              <EmptyState title="Connector secin" description="Kurulum ayrintilarini gormek ve onboarding adimlarini calistirmak icin bir connector secin." />
            ) : (
              <>
                <SurfaceCard className="space-y-4 p-5">
                  <SectionHeading eyebrow="Profile" title={detail.display_name} description="Secret literal yerine sadece credential_ref ve semantik alanlar saklanir." />
                  <div className="flex flex-wrap gap-2">
                    <StatusChip tone={toneFromBand(selectedSummary.health_band)}>{selectedSummary.health_band}</StatusChip>
                    <StatusChip tone={detail.support_tier === "certified" ? "good" : "attention"}>{detail.support_tier}</StatusChip>
                    <StatusChip tone={detail.status === "active" ? "good" : "attention"}>{detail.status}</StatusChip>
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <FormField label="Credential Ref"><input className={fieldClassName()} value={form.credentialRef} onChange={(event) => setForm((prev) => ({ ...prev, credentialRef: event.target.value }))} /></FormField>
                    <FormField label="Certified Variant"><input className={fieldClassName()} value={form.certifiedVariant} onChange={(event) => setForm((prev) => ({ ...prev, certifiedVariant: event.target.value }))} /></FormField>
                    <FormField label="Product Version"><input className={fieldClassName()} value={form.productVersion} onChange={(event) => setForm((prev) => ({ ...prev, productVersion: event.target.value }))} /></FormField>
                    <FormField label="Auth Method"><input className={fieldClassName()} value={form.authMethod} onChange={(event) => setForm((prev) => ({ ...prev, authMethod: event.target.value }))} /></FormField>
                    {(detail.connector_type === "sap_odata" || detail.connector_type === "netsis_rest") ? (
                      <>
                        <FormField label="Service URL"><input className={fieldClassName()} value={form.serviceUrl} onChange={(event) => setForm((prev) => ({ ...prev, serviceUrl: event.target.value }))} /></FormField>
                        <FormField label="Resource Path"><input className={fieldClassName()} value={form.resourcePath} onChange={(event) => setForm((prev) => ({ ...prev, resourcePath: event.target.value }))} /></FormField>
                      </>
                    ) : null}
                    {detail.connector_type === "sap_odata" ? (
                      <FormField label="Company Code"><input className={fieldClassName()} value={form.companyCode} onChange={(event) => setForm((prev) => ({ ...prev, companyCode: event.target.value }))} /></FormField>
                    ) : null}
                    {detail.connector_type === "logo_tiger_sql_view" ? (
                      <>
                        <FormField label="SQL Host"><input className={fieldClassName()} value={form.host} onChange={(event) => setForm((prev) => ({ ...prev, host: event.target.value }))} /></FormField>
                        <FormField label="Database Name"><input className={fieldClassName()} value={form.databaseName} onChange={(event) => setForm((prev) => ({ ...prev, databaseName: event.target.value }))} /></FormField>
                        <FormField label="SQL View"><input className={fieldClassName()} value={form.sqlViewName} onChange={(event) => setForm((prev) => ({ ...prev, sqlViewName: event.target.value }))} /></FormField>
                        <FormField label="View Schema"><input className={fieldClassName()} value={form.viewSchema} onChange={(event) => setForm((prev) => ({ ...prev, viewSchema: event.target.value }))} /></FormField>
                      </>
                    ) : null}
                    {detail.connector_type === "netsis_rest" ? (
                      <FormField label="Firm Code"><input className={fieldClassName()} value={form.firmCode} onChange={(event) => setForm((prev) => ({ ...prev, firmCode: event.target.value }))} /></FormField>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" onClick={() => void handleSaveProfile()} disabled={busy}>
                      {busy ? <Loader2 className="size-4 animate-spin" /> : <Wrench className="size-4" />}
                      Save Profile
                    </Button>
                    <Button type="button" variant="outline" onClick={() => void loadIntegrationDetail(detail.id)} disabled={busy}>
                      <RefreshCw className="size-4" />
                      Refresh Detail
                    </Button>
                  </div>
                </SurfaceCard>

                <SurfaceCard className="space-y-4 p-5">
                  <SectionHeading eyebrow="Onboarding" title="Operational Gating" description="Discovery -> preflight -> 20-record preview sync -> activation readiness." />
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" variant="outline" onClick={() => void runOperation(`/integrations/connectors/${detail.id}/discover`, { tenant_id: workspace.tenantId, project_id: workspace.projectId })} disabled={busy} data-testid="connector-discover-button">
                      <PlayCircle className="size-4" />
                      Discover
                    </Button>
                    <Button type="button" variant="outline" onClick={() => void runOperation(`/integrations/connectors/${detail.id}/preflight`, { tenant_id: workspace.tenantId, project_id: workspace.projectId })} disabled={busy} data-testid="connector-preflight-button">
                      <ShieldCheck className="size-4" />
                      Preflight
                    </Button>
                    <Button type="button" onClick={() => void runOperation(`/integrations/connectors/${detail.id}/preview-sync`, { tenant_id: workspace.tenantId, project_id: workspace.projectId, limit: 20 })} disabled={busy} data-testid="connector-preview-button">
                      {busy ? <Loader2 className="size-4 animate-spin" /> : <PlayCircle className="size-4" />}
                      Preview 20
                    </Button>
                    <Button type="button" variant="outline" onClick={() => void runOperation(`/integrations/connectors/${detail.id}/replay`, { tenant_id: workspace.tenantId, project_id: workspace.projectId, mode: "reset_cursor" })} disabled={busy}>
                      <RefreshCw className="size-4" />
                      Reset Cursor
                    </Button>
                    <Button type="button" variant="outline" onClick={() => void runOperation(`/integrations/connectors/${detail.id}/support-bundle`, { tenant_id: workspace.tenantId, project_id: workspace.projectId })} disabled={busy} data-testid="connector-support-bundle-button">
                      <Download className="size-4" />
                      Support Bundle
                    </Button>
                  </div>

                  {detail.health_status ? (
                    <div className="grid gap-3 md:grid-cols-2">
                      {detail.health_status.metrics.map((metric) => (
                        <div key={metric.key} className="rounded-[1.2rem] border border-[color:var(--border)] bg-white/82 px-3 py-3">
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-[12px] font-semibold text-foreground">{metric.label}</p>
                            <StatusChip tone={metric.score >= 85 ? "good" : metric.score >= 60 ? "attention" : "critical"}>{metric.score}</StatusChip>
                          </div>
                          <p className="mt-2 text-[12px] leading-5 text-[color:var(--foreground-soft)]">{metric.detail}</p>
                        </div>
                      ))}
                    </div>
                  ) : null}

                  {previewRows.length > 0 ? (
                    <div className="overflow-hidden rounded-[1.2rem] border border-[color:var(--border)]">
                      <div className="grid grid-cols-[1.4fr_0.8fr_0.6fr_0.8fr] gap-0 bg-[color:var(--surface)] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[color:var(--foreground-muted)]">
                        <span>Metric</span>
                        <span>Period</span>
                        <span>Unit</span>
                        <span>Value</span>
                      </div>
                      {previewRows.map((row, index) => (
                        <div key={`${String(row.metric_code)}-${index}`} className="grid grid-cols-[1.4fr_0.8fr_0.6fr_0.8fr] gap-0 border-t border-[color:var(--border)] px-3 py-2 text-[12px]">
                          <span>{String(row.metric_code)}</span>
                          <span>{String(row.period_key)}</span>
                          <span>{String(row.unit ?? "-")}</span>
                          <span>{String(row.value_numeric ?? row.value_text ?? "-")}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </SurfaceCard>

                {detail.health_status ? (
                  <SubtleAlert tone={toneFromBand(detail.health_status.band)} title={detail.health_status.operator_message}>
                    {detail.health_status.support_hint} {detail.health_status.recommended_action}
                  </SubtleAlert>
                ) : null}

                {latestOperation?.artifact ? (
                  <SurfaceCard className="flex items-center justify-between gap-3 p-4">
                    <div>
                      <p className="text-[13px] font-semibold text-foreground">{latestOperation.artifact.filename}</p>
                      <p className="mt-1 text-[12px] text-[color:var(--foreground-soft)]">Tek tik support paketi uretildi.</p>
                    </div>
                    <Button asChild variant="outline">
                      <a href={`${getApiBaseUrl()}${latestOperation.artifact.download_path}`} target="_blank" rel="noreferrer">
                        <Download className="size-4" />
                        Download
                      </a>
                    </Button>
                  </SurfaceCard>
                ) : null}
              </>
            )}

            {error ? <SubtleAlert tone="critical" title="Operation failed">{error}</SubtleAlert> : null}
            {notice ? <SubtleAlert tone="good" title="Status updated">{notice}</SubtleAlert> : null}
          </div>
        </div>
      )}
    </AppShell>
  );
}
