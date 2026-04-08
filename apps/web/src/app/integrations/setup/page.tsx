"use client";

// Bu sayfa, ERP onboarding akisini setup yuzeyinde toplar.

import { useEffect, useMemo, useState } from "react";
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
import { getApiBaseUrl } from "@/lib/api/client";
import {
  buildIntegrationFormState,
  EMPTY_INTEGRATION_FORM,
  type ConnectorOperationResponse,
  type IntegrationDetailResponse,
  type IntegrationFormState,
  type WorkspaceIntegrationSummary as IntegrationSummary,
  useIntegrationDetailQuery,
  useIntegrationSummariesQuery,
  useRunConnectorOperationMutation,
  useSaveIntegrationProfileMutation,
} from "@/lib/api/integrations";
import { useWorkspaceContext } from "@/lib/api/workspace-store";

function toneFromBand(band: "green" | "amber" | "red") {
  if (band === "green") {
    return "good" as const;
  }
  if (band === "amber") {
    return "attention" as const;
  }
  return "critical" as const;
}

export default function IntegrationsSetupPage() {
  const workspace = useWorkspaceContext();
  const [selectedIntegrationId, setSelectedIntegrationId] = useState<string | null>(null);
  const [form, setForm] = useState<IntegrationFormState>(EMPTY_INTEGRATION_FORM);
  const [latestOperation, setLatestOperation] = useState<ConnectorOperationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const summariesQuery = useIntegrationSummariesQuery(workspace);
  const summaries = summariesQuery.data ?? [];
  const detailQuery = useIntegrationDetailQuery(workspace, selectedIntegrationId);
  const detail = detailQuery.data ?? null;
  const saveProfileMutation = useSaveIntegrationProfileMutation(workspace);
  const operationMutation = useRunConnectorOperationMutation(workspace);
  const busy =
    summariesQuery.isFetching ||
    detailQuery.isFetching ||
    saveProfileMutation.isPending ||
    operationMutation.isPending;
  const queryError =
    summariesQuery.error instanceof Error
      ? summariesQuery.error.message
      : detailQuery.error instanceof Error
        ? detailQuery.error.message
        : null;

  const selectedSummary = useMemo(
    () => summaries.find((item) => item.id === selectedIntegrationId) ?? null,
    [selectedIntegrationId, summaries],
  );

  useEffect(() => {
    if (!selectedIntegrationId && summaries[0]?.id) {
      setSelectedIntegrationId(summaries[0].id);
    }
  }, [selectedIntegrationId, summaries]);

  useEffect(() => {
    if (!selectedIntegrationId) {
      setForm(EMPTY_INTEGRATION_FORM);
      return;
    }
    if (detail) {
      setForm(buildIntegrationFormState(detail));
    }
  }, [detail, selectedIntegrationId]);

  async function runOperation(
    operation: "discover" | "preflight" | "preview-sync" | "replay" | "support-bundle",
    body: { limit?: number; mode?: "resume" | "reset_cursor" | "backfill_window" } = {},
  ) {
    if (!workspace || !selectedIntegrationId) {
      return;
    }
    setError(null);
    setNotice(null);
    try {
      const payload = await operationMutation.mutateAsync({
        integrationId: selectedIntegrationId,
        operation,
        body,
      });
      setLatestOperation(payload);
      setNotice(payload.operator_message ?? "Operation completed.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Connector operation failed.");
    }
  }

  async function handleSaveProfile() {
    if (!workspace || !detail) {
      return;
    }
    setError(null);
    setNotice(null);
    try {
      const payload = await saveProfileMutation.mutateAsync({
        detail,
        form,
      });
      setForm(buildIntegrationFormState(payload));
      setNotice("Connector profile saved. You can continue with discovery.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Connector profile could not be saved.");
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
                    <Button
                      type="button"
                      onClick={() => void handleSaveProfile()}
                      disabled={busy}
                      data-testid="connector-save-profile-button"
                    >
                      {busy ? <Loader2 className="size-4 animate-spin" /> : <Wrench className="size-4" />}
                      Save Profile
                    </Button>
                    <Button type="button" variant="outline" onClick={() => void detailQuery.refetch()} disabled={busy}>
                      <RefreshCw className="size-4" />
                      Refresh Detail
                    </Button>
                  </div>
                </SurfaceCard>

                <SurfaceCard className="space-y-4 p-5">
                  <SectionHeading eyebrow="Onboarding" title="Operational Gating" description="Discovery -> preflight -> 20-record preview sync -> activation readiness." />
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" variant="outline" onClick={() => void runOperation("discover")} disabled={busy} data-testid="connector-discover-button">
                      <PlayCircle className="size-4" />
                      Discover
                    </Button>
                    <Button type="button" variant="outline" onClick={() => void runOperation("preflight")} disabled={busy} data-testid="connector-preflight-button">
                      <ShieldCheck className="size-4" />
                      Preflight
                    </Button>
                    <Button type="button" onClick={() => void runOperation("preview-sync", { limit: 20 })} disabled={busy} data-testid="connector-preview-button">
                      {busy ? <Loader2 className="size-4 animate-spin" /> : <PlayCircle className="size-4" />}
                      Preview 20
                    </Button>
                    <Button type="button" variant="outline" onClick={() => void runOperation("replay", { mode: "reset_cursor" })} disabled={busy}>
                      <RefreshCw className="size-4" />
                      Reset Cursor
                    </Button>
                    <Button type="button" variant="outline" onClick={() => void runOperation("support-bundle")} disabled={busy} data-testid="connector-support-bundle-button">
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

            {error || queryError ? (
              <SubtleAlert tone="critical" title="Operation failed" data-testid="integrations-error">
                {error ?? queryError}
              </SubtleAlert>
            ) : null}
            {notice ? (
              <SubtleAlert tone="good" title="Status updated" data-testid="integrations-notice">
                {notice}
              </SubtleAlert>
            ) : null}
          </div>
        </div>
      )}
    </AppShell>
  );
}
