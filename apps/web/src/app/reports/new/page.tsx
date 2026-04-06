"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileText,
  Loader2,
  Rocket,
  Settings2,
} from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  buildApiHeaders,
  getApiBaseUrl,
  parseJsonOrThrow,
  persistWorkspaceContext,
} from "@/lib/api/client";
import { useWorkspaceContext } from "@/lib/api/workspace-store";

type WizardState = {
  legalName: string;
  taxId: string;
  framework: "TSRS" | "CSRD" | "TSRS+CSRD";
  reportingYear: string;
  operationCountries: string;
  includeScope3: boolean;
  sustainabilityOwner: string;
  boardApprover: string;
  approvalSlaDays: string;
};

type WorkspaceContextResponse = {
  tenant: {
    id: string;
    name: string;
    slug: string;
    status: string;
  };
  project: {
    id: string;
    tenant_id: string;
    name: string;
    code: string;
    reporting_currency: string;
    status: string;
  };
  company_profile: {
    id: string;
    legal_name: string;
  };
  brand_kit: {
    id: string;
    brand_name: string;
    primary_color: string;
    secondary_color: string;
    accent_color: string;
  };
  integrations: Array<{
    id: string;
    connector_type: string;
    display_name: string;
    status: string;
  }>;
  blueprint_version: string;
};

type WorkspaceBootstrapResponse = WorkspaceContextResponse & {
  tenant_created: boolean;
  project_created: boolean;
};

type RunCreateResponse = {
  run_id: string;
  report_run_id: string;
};

type FactoryContext = {
  companyProfileId: string;
  brandKitId: string;
  blueprintVersion: string;
  integrations: Array<{
    id: string;
    connectorType: string;
    displayName: string;
    status: string;
  }>;
};

const STEP_TITLES = [
  "Şirket Profili",
  "Raporlama Kapsamı",
  "Yönetişim ve Onay",
] as const;

const INITIAL_STATE: WizardState = {
  legalName: "",
  taxId: "",
  framework: "TSRS+CSRD",
  reportingYear: "2025",
  operationCountries: "Turkiye",
  includeScope3: true,
  sustainabilityOwner: "",
  boardApprover: "",
  approvalSlaDays: "5",
};

function resolveFrameworkTargets(form: WizardState): string[] {
  if (form.framework === "TSRS+CSRD") {
    return ["TSRS1", "TSRS2", "CSRD"];
  }
  if (form.framework === "TSRS") {
    return ["TSRS1", "TSRS2"];
  }
  return ["CSRD"];
}

function buildRetrievalTasks(form: WizardState, frameworkTarget: string[]) {
  return frameworkTarget.map((framework, index) => {
    if (framework === "TSRS1") {
      return {
        task_id: `task_${index + 1}_tsrs1`,
        framework,
        section_target: "TSRS1 Governance and Risk Management",
        query_text: `TSRS1 governance and risk management sustainability committee oversight ${form.reportingYear}`,
        retrieval_mode: "hybrid" as const,
        top_k: 3,
      };
    }
    if (framework === "TSRS2") {
      return {
        task_id: `task_${index + 1}_tsrs2`,
        framework,
        section_target: "TSRS2 Climate and Energy",
        query_text: `TSRS2 climate and energy scope 2 electricity emissions renewable electricity ${form.reportingYear}`,
        retrieval_mode: "hybrid" as const,
        top_k: 3,
      };
    }
    return {
      task_id: `task_${index + 1}_csrd`,
      framework,
      section_target: "CSRD Workforce and Supply Chain",
      query_text: `CSRD workforce supply chain lost time injury supplier screening ${form.reportingYear}`,
      retrieval_mode: "hybrid" as const,
      top_k: 3,
    };
  });
}

function completionScore(form: WizardState): number {
  const checklist = [
    form.legalName.trim().length > 1,
    form.taxId.trim().length > 5,
    form.framework.length > 0,
    form.reportingYear.trim().length === 4,
    form.operationCountries.trim().length > 1,
    form.sustainabilityOwner.trim().length > 1,
    form.boardApprover.trim().length > 1,
    Number(form.approvalSlaDays) > 0,
  ];
  const done = checklist.filter(Boolean).length;
  return Math.round((done / checklist.length) * 100);
}

export default function NewReportPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<WizardState>(INITIAL_STATE);
  const workspace = useWorkspaceContext();
  const [workspaceTenantName, setWorkspaceTenantName] = useState("");
  const [workspaceTenantSlug, setWorkspaceTenantSlug] = useState("");
  const [workspaceProjectName, setWorkspaceProjectName] = useState("");
  const [workspaceProjectCode, setWorkspaceProjectCode] = useState("");
  const [workspaceCurrency, setWorkspaceCurrency] = useState("TRY");
  const [workspaceBusy, setWorkspaceBusy] = useState(false);
  const [contextBusy, setContextBusy] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitNotice, setSubmitNotice] = useState<string | null>(null);
  const [factoryContext, setFactoryContext] = useState<FactoryContext | null>(null);
  const [connectorScope, setConnectorScope] = useState<string[]>([
    "sap_odata",
    "logo_tiger_sql_view",
    "netsis_rest",
  ]);
  const score = useMemo(() => completionScore(form), [form]);
  const isLastStep = step === STEP_TITLES.length - 1;

  function applyWorkspaceContext(payload: WorkspaceContextResponse) {
    const nextWorkspace = {
      tenantId: payload.tenant.id,
      projectId: payload.project.id,
    };
    persistWorkspaceContext(nextWorkspace);
    setWorkspaceTenantName(payload.tenant.name);
    setWorkspaceTenantSlug(payload.tenant.slug);
    setWorkspaceProjectName(payload.project.name);
    setWorkspaceProjectCode(payload.project.code);
    setWorkspaceCurrency(payload.project.reporting_currency);
    setFactoryContext({
      companyProfileId: payload.company_profile.id,
      brandKitId: payload.brand_kit.id,
      blueprintVersion: payload.blueprint_version,
      integrations: payload.integrations.map((item) => ({
        id: item.id,
        connectorType: item.connector_type,
        displayName: item.display_name,
        status: item.status,
      })),
    });
    setConnectorScope(payload.integrations.map((item) => item.connector_type));
    setForm((prev) => ({
      ...prev,
      legalName: prev.legalName || payload.company_profile.legal_name,
    }));
  }

  useEffect(() => {
    if (!workspace || factoryContext || contextBusy) {
      return;
    }
    const currentWorkspace = workspace;

    let cancelled = false;

    async function loadWorkspaceContext() {
      setContextBusy(true);
      try {
        const apiBase = getApiBaseUrl();
        const response = await fetch(
          `${apiBase}/catalog/workspace-context?tenant_id=${encodeURIComponent(currentWorkspace.tenantId)}&project_id=${encodeURIComponent(currentWorkspace.projectId)}`,
          {
            headers: buildApiHeaders(currentWorkspace.tenantId),
          },
        );
        const payload = await parseJsonOrThrow<WorkspaceContextResponse>(response);
        if (!cancelled) {
          applyWorkspaceContext(payload);
        }
      } catch (error) {
        if (!cancelled) {
          setSubmitError(
            error instanceof Error
              ? error.message
              : "Workspace context could not be loaded.",
          );
        }
      } finally {
        if (!cancelled) {
          setContextBusy(false);
        }
      }
    }

    void loadWorkspaceContext();

    return () => {
      cancelled = true;
    };
  }, [contextBusy, factoryContext, workspace]);

  const canSubmit =
    form.legalName.trim().length > 1 &&
    form.taxId.trim().length > 5 &&
    form.reportingYear.trim().length === 4 &&
    form.operationCountries.trim().length > 1 &&
    form.sustainabilityOwner.trim().length > 1 &&
    form.boardApprover.trim().length > 1 &&
    Number(form.approvalSlaDays) > 0;
  const canCreateRun =
    canSubmit &&
    Boolean(workspace) &&
    Boolean(factoryContext) &&
    !contextBusy;

  async function handleBootstrapWorkspace() {
    setSubmitError(null);
    setSubmitNotice(null);
    if (
      workspaceTenantName.trim().length < 2 ||
      workspaceTenantSlug.trim().length < 2 ||
      workspaceProjectName.trim().length < 2 ||
      workspaceProjectCode.trim().length < 2
    ) {
      setSubmitError("Tenant ve proje alanları zorunlu.");
      return;
    }

    setWorkspaceBusy(true);
    try {
      const apiBase = getApiBaseUrl();
      const tenantHeader = workspace?.tenantId ?? "dev-tenant";
      const response = await fetch(`${apiBase}/catalog/bootstrap-workspace`, {
        method: "POST",
        headers: buildApiHeaders(tenantHeader),
        body: JSON.stringify({
          tenant_name: workspaceTenantName.trim(),
          tenant_slug: workspaceTenantSlug.trim(),
          project_name: workspaceProjectName.trim(),
          project_code: workspaceProjectCode.trim(),
          reporting_currency: workspaceCurrency.trim().toUpperCase(),
        }),
      });
      const payload = await parseJsonOrThrow<WorkspaceBootstrapResponse>(response);
      applyWorkspaceContext(payload);
      setSubmitNotice(
        `Workspace hazır. Tenant: ${payload.tenant.slug}, Proje: ${payload.project.code}. Rapor fabrikası bağlamı kuruldu.`,
      );
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Workspace bootstrap failed.");
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function handleCreateRun() {
    setSubmitError(null);
    setSubmitNotice(null);

    if (!workspace) {
      setSubmitError("Önce bir workspace seç veya oluştur.");
      return;
    }
    if (!factoryContext) {
      setSubmitError("Devam etmeden önce workspace context yüklenmeli.");
      return;
    }
    if (!canSubmit) {
      setSubmitError("Run oluşturmadan önce zorunlu alanları tamamla.");
      return;
    }

    setIsSubmitting(true);
    try {
      const apiBase = getApiBaseUrl();
      const frameworkTarget = resolveFrameworkTargets(form);
      const activeConnectorIds = factoryContext.integrations
        .filter((item) => connectorScope.includes(item.connectorType))
        .map((item) => item.id);

      if (activeConnectorIds.length === 0) {
        setSubmitError("En az bir aktif ERP connector seç.");
        return;
      }

      await parseJsonOrThrow(
        await fetch(`${apiBase}/integrations/sync`, {
          method: "POST",
          headers: buildApiHeaders(workspace.tenantId),
          body: JSON.stringify({
            tenant_id: workspace.tenantId,
            project_id: workspace.projectId,
            connector_ids: activeConnectorIds,
          }),
        }),
      );

      const response = await fetch(`${apiBase}/runs`, {
        method: "POST",
        headers: buildApiHeaders(workspace.tenantId),
        body: JSON.stringify({
          tenant_id: workspace.tenantId,
          project_id: workspace.projectId,
          framework_target: frameworkTarget,
          active_reg_pack_version: "core-pack-v1",
          report_blueprint_version: factoryContext.blueprintVersion,
          company_profile_ref: factoryContext.companyProfileId,
          brand_kit_ref: factoryContext.brandKitId,
          connector_scope: connectorScope,
          scope_decision: {
            reporting_year: form.reportingYear,
            include_scope3: form.includeScope3,
            operation_countries: form.operationCountries,
            sustainability_owner: form.sustainabilityOwner,
            board_approver: form.boardApprover,
            approval_sla_days: Number(form.approvalSlaDays),
            retrieval_tasks: buildRetrievalTasks(form, frameworkTarget),
          },
        }),
      });

      const payload = await parseJsonOrThrow<RunCreateResponse>(response);
      router.push(
        `/approval-center?created=1&mode=api&runId=${encodeURIComponent(payload.run_id)}&tenantId=${encodeURIComponent(workspace.tenantId)}&projectId=${encodeURIComponent(workspace.projectId)}`,
      );
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unknown error during run creation.";
      setSubmitError(`Run could not be created. ${message}`);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AppShell
      activePath="/reports/new"
      title="Rapor Fabrikası Çalıştır"
      subtitle="Report context kur, ERP connector'larını senkronize et ve kontrollü sürdürülebilirlik raporu hattını başlat."
      actions={[{ href: "/dashboard", label: "Dashboard'a Dön" }]}
    >
      <section className="mb-4 rounded-xl border bg-card p-4 shadow-sm">
        <div className="mb-3 flex items-center gap-2">
          <Settings2 className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-base font-semibold">Workspace Kurulumu (Tenant + Proje)</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Tenant Adı</span>
            <input
              aria-label="Tenant Name"
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={workspaceTenantName}
              onChange={(event) => setWorkspaceTenantName(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Tenant Slug</span>
            <input
              aria-label="Tenant Slug"
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={workspaceTenantSlug}
              onChange={(event) => setWorkspaceTenantSlug(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Proje Adı</span>
            <input
              aria-label="Project Name"
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={workspaceProjectName}
              onChange={(event) => setWorkspaceProjectName(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Proje Kodu</span>
            <input
              aria-label="Project Code"
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={workspaceProjectCode}
              onChange={(event) => setWorkspaceProjectCode(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Para Birimi</span>
            <input
              aria-label="Currency"
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={workspaceCurrency}
              onChange={(event) => setWorkspaceCurrency(event.target.value)}
            />
          </label>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={handleBootstrapWorkspace}
            disabled={workspaceBusy}
            data-testid="workspace-bootstrap-button"
          >
            {workspaceBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Settings2 className="h-4 w-4" />}
            {workspaceBusy ? "Hazırlanıyor..." : "Workspace Oluştur / Seç"}
          </Button>
          {workspace ? (
            <p
              className="text-xs text-emerald-700 dark:text-emerald-300"
              data-testid="workspace-context-status"
            >
              tenant_id={workspace.tenantId} - project_id={workspace.projectId}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground" data-testid="workspace-context-status">
              Henüz workspace seçilmedi.
            </p>
          )}
        </div>
        {contextBusy && !factoryContext ? (
          <p
            className="mt-2 text-xs text-muted-foreground"
            data-testid="factory-context-loading"
          >
            Mevcut workspace için rapor fabrikası bağlamı yükleniyor...
          </p>
        ) : null}
        {factoryContext ? (
          <div
            className="mt-4 grid gap-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/8 p-4 md:grid-cols-[0.8fr_1.2fr]"
            data-testid="factory-context-panel"
          >
            <div>
              <p className="text-xs uppercase tracking-[0.16em] text-emerald-700 dark:text-emerald-300">
                Rapor Fabrikası Bağlamı
              </p>
              <p className="mt-2 text-sm">
                Blueprint: <strong>{factoryContext.blueprintVersion}</strong>
              </p>
              <p className="mt-1 text-sm">
                Provision edilen connector sayısı: <strong>{factoryContext.integrations.length}</strong>
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Connector Kapsamı</p>
              <div className="mt-2 grid gap-2 md:grid-cols-3">
                {factoryContext.integrations.map((integration) => {
                  const checked = connectorScope.includes(integration.connectorType);
                  return (
                    <label
                      key={integration.id}
                      className="flex items-center gap-2 rounded-xl border bg-background px-3 py-2 text-sm"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(event) => {
                          setConnectorScope((prev) => {
                            if (event.target.checked) {
                              return Array.from(new Set([...prev, integration.connectorType]));
                            }
                            return prev.filter((item) => item !== integration.connectorType);
                          });
                        }}
                      />
                      <span>{integration.displayName}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          </div>
        ) : null}
      </section>

      <div className="grid gap-4 lg:grid-cols-[1.3fr_0.7fr]">
        <section className="rounded-xl border bg-card p-5 shadow-sm">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <p className="text-muted-foreground text-xs uppercase tracking-[0.16em]">
                Adım {step + 1} / {STEP_TITLES.length}
              </p>
              <h2 className="mt-1 text-xl font-semibold">{STEP_TITLES[step]}</h2>
            </div>
            <p className="text-muted-foreground rounded-full border px-3 py-1 text-xs">
              Tamamlanma {score}%
            </p>
          </div>

          {step === 0 ? (
            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-2 text-sm">
                <span className="text-muted-foreground">Tüzel Kişi Adı</span>
                <input
                  aria-label="Legal Entity Name"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={form.legalName}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, legalName: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-2 text-sm">
                <span className="text-muted-foreground">Vergi / Sicil No</span>
                <input
                  aria-label="Tax / Registry ID"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={form.taxId}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, taxId: event.target.value }))
                  }
                />
              </label>
            </div>
          ) : null}

          {step === 1 ? (
            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-2 text-sm">
                <span className="text-muted-foreground">Hedef Framework</span>
                <select
                  aria-label="Framework Target"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={form.framework}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      framework: event.target.value as WizardState["framework"],
                    }))
                  }
                >
                  <option value="TSRS">TSRS</option>
                  <option value="CSRD">CSRD</option>
                  <option value="TSRS+CSRD">TSRS + CSRD</option>
                </select>
              </label>
              <label className="space-y-2 text-sm">
                <span className="text-muted-foreground">Raporlama Yılı</span>
                <input
                  aria-label="Reporting Year"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={form.reportingYear}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      reportingYear: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="space-y-2 text-sm md:col-span-2">
                <span className="text-muted-foreground">Faaliyet Ülkeleri</span>
                <input
                  aria-label="Operation Countries"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={form.operationCountries}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      operationCountries: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="flex items-center gap-3 text-sm md:col-span-2">
                <input
                  type="checkbox"
                  aria-label="Include Scope 3 calculation cycle for this run"
                  checked={form.includeScope3}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      includeScope3: event.target.checked,
                    }))
                  }
                />
                Bu run için Scope 3 hesaplama çevrimini dahil et
              </label>
            </div>
          ) : null}

          {step === 2 ? (
            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-2 text-sm">
                <span className="text-muted-foreground">Sürdürülebilirlik Sorumlusu</span>
                <input
                  aria-label="Sustainability Owner"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={form.sustainabilityOwner}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      sustainabilityOwner: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="space-y-2 text-sm">
                <span className="text-muted-foreground">Yönetim Kurulu Onaylayıcısı</span>
                <input
                  aria-label="Board Approver"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={form.boardApprover}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      boardApprover: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="space-y-2 text-sm md:col-span-2">
                <span className="text-muted-foreground">Onay SLA (gün)</span>
                <input
                  aria-label="Approval SLA (days)"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={form.approvalSlaDays}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      approvalSlaDays: event.target.value,
                    }))
                  }
                />
              </label>
            </div>
          ) : null}

          <div className="mt-6 flex items-center justify-between">
            <Button
              type="button"
              variant="outline"
              onClick={() => setStep((prev) => Math.max(0, prev - 1))}
              disabled={step === 0}
              data-testid="wizard-back-button"
            >
              <ChevronLeft className="h-4 w-4" />
              Geri
            </Button>

            {isLastStep ? (
              <Button
                type="button"
                onClick={handleCreateRun}
                disabled={!canCreateRun || isSubmitting}
                data-testid="create-report-run-button"
              >
                {isSubmitting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Rocket className="h-4 w-4" />
                )}
                {isSubmitting ? "Oluşturuluyor..." : "Report Run Oluştur"}
              </Button>
            ) : (
              <Button
                type="button"
                onClick={() =>
                  setStep((prev) => Math.min(STEP_TITLES.length - 1, prev + 1))
                }
                data-testid="wizard-next-button"
              >
                İleri
                <ChevronRight className="h-4 w-4" />
              </Button>
            )}
          </div>

          {submitError ? (
            <div
              className="mt-4 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              data-testid="new-report-error"
            >
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <p>{submitError}</p>
              </div>
            </div>
          ) : null}

          {submitNotice ? (
            <div
              className="mt-4 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300"
              data-testid="new-report-notice"
            >
              {submitNotice}
            </div>
          ) : null}
        </section>

        <aside className="relative overflow-hidden rounded-xl border bg-card p-5 shadow-sm">
          <div className="absolute inset-0">
            <Image
              src="/images/wizard-hero.png"
              alt="Industrial sustainability operations scene"
              fill
              sizes="(min-width: 1024px) 35vw, 100vw"
              className="object-cover opacity-30"
            />
            <div className="absolute inset-0 bg-gradient-to-b from-background/86 via-background/90 to-background/95" />
          </div>

          <div className="relative">
            <p className="text-muted-foreground mb-4 text-xs tracking-[0.12em] uppercase">
              Kanıt Hazır Intake
            </p>
            <h3 className="text-base font-semibold">Run Özeti</h3>
            <p className="text-muted-foreground mt-1 text-sm">
              Wizard üzerinde toplanan girdiler doğrudan LangGraph execution state&apos;ine yazılır.
            </p>
            <ul className="mt-4 space-y-3 text-sm">
              {STEP_TITLES.map((title, index) => (
                <li key={title} className="flex items-center gap-2">
                  <CheckCircle2
                    className={[
                      "h-4 w-4",
                      index <= step ? "text-emerald-600 dark:text-emerald-300" : "text-muted-foreground",
                    ].join(" ")}
                  />
                  {title}
                </li>
              ))}
            </ul>
            <div className="bg-muted/45 mt-5 rounded-lg border p-3 text-xs">
              <div className="mb-2 flex items-center gap-2">
                <FileText className="h-3.5 w-3.5" />
                Payload önizleme
              </div>
              <p>Framework: {form.framework}</p>
              <p>Year: {form.reportingYear}</p>
              <p>Scope 3: {form.includeScope3 ? "Dahil" : "Hariç"}</p>
              <p>SLA: {form.approvalSlaDays} gün</p>
              <p>
                Workspace: {workspace ? `${workspace.tenantId} / ${workspace.projectId}` : "seçilmedi"}
              </p>
            </div>
          </div>
        </aside>
      </div>
    </AppShell>
  );
}
