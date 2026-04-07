"use client";

// Bu sayfa, reports new ekraninin ana deneyimini kurar.

import { useCallback, useEffect, useMemo, useState } from "react";
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
    sector: string | null;
    headquarters: string | null;
    description: string | null;
    ceo_name: string | null;
    ceo_message: string | null;
    sustainability_approach: string | null;
    is_configured: boolean;
  };
  brand_kit: {
    id: string;
    brand_name: string;
    logo_uri: string | null;
    primary_color: string;
    secondary_color: string;
    accent_color: string;
    font_family_headings: string;
    font_family_body: string;
    tone_name: string | null;
    is_configured: boolean;
  };
  integrations: Array<{
    id: string;
    connector_type: string;
    display_name: string;
    status: string;
  }>;
  blueprint_version: string;
  factory_readiness: {
    is_ready: boolean;
    company_profile_ready: boolean;
    brand_kit_ready: boolean;
    blockers: Array<{
      code: string;
      message: string;
    }>;
  };
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
  readiness: WorkspaceContextResponse["factory_readiness"];
};

type WorkspaceSetupState = {
  legalName: string;
  sector: string;
  headquarters: string;
  description: string;
  ceoName: string;
  ceoMessage: string;
  sustainabilityApproach: string;
  brandName: string;
  logoUri: string;
  primaryColor: string;
  secondaryColor: string;
  accentColor: string;
  headingFont: string;
  bodyFont: string;
  toneName: string;
};

const STEP_TITLES = [
  "Workspace Context",
  "Report Scope",
  "Governance",
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

const INITIAL_WORKSPACE_SETUP: WorkspaceSetupState = {
  legalName: "",
  sector: "",
  headquarters: "",
  description: "",
  ceoName: "",
  ceoMessage: "",
  sustainabilityApproach: "",
  brandName: "",
  logoUri: "",
  primaryColor: "#f07f13",
  secondaryColor: "#262421",
  accentColor: "#d2b24a",
  headingFont: "Inter",
  bodyFont: "Inter",
  toneName: "editorial-corporate",
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
  const workspaceKey = workspace
    ? `${workspace.tenantId}:${workspace.projectId}`
    : null;
  const [workspaceTenantName, setWorkspaceTenantName] = useState("");
  const [workspaceTenantSlug, setWorkspaceTenantSlug] = useState("");
  const [workspaceProjectName, setWorkspaceProjectName] = useState("");
  const [workspaceProjectCode, setWorkspaceProjectCode] = useState("");
  const [workspaceCurrency, setWorkspaceCurrency] = useState("TRY");
  const [workspaceSetup, setWorkspaceSetup] = useState<WorkspaceSetupState>(INITIAL_WORKSPACE_SETUP);
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

  const applyWorkspaceContext = useCallback(
    (payload: WorkspaceContextResponse) => {
      const nextWorkspace = {
        tenantId: payload.tenant.id,
        projectId: payload.project.id,
      };
      if (
        !workspace ||
        workspace.tenantId !== nextWorkspace.tenantId ||
        workspace.projectId !== nextWorkspace.projectId
      ) {
        persistWorkspaceContext(nextWorkspace);
      }
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
        readiness: payload.factory_readiness,
      });
      setWorkspaceSetup({
        legalName: payload.company_profile.legal_name ?? "",
        sector: payload.company_profile.sector ?? "",
        headquarters: payload.company_profile.headquarters ?? "",
        description: payload.company_profile.description ?? "",
        ceoName: payload.company_profile.ceo_name ?? "",
        ceoMessage: payload.company_profile.ceo_message ?? "",
        sustainabilityApproach: payload.company_profile.sustainability_approach ?? "",
        brandName: payload.brand_kit.brand_name ?? "",
        logoUri: payload.brand_kit.logo_uri ?? "",
        primaryColor: payload.brand_kit.primary_color,
        secondaryColor: payload.brand_kit.secondary_color,
        accentColor: payload.brand_kit.accent_color,
        headingFont: payload.brand_kit.font_family_headings,
        bodyFont: payload.brand_kit.font_family_body,
        toneName: payload.brand_kit.tone_name ?? "",
      });
      setConnectorScope(payload.integrations.map((item) => item.connector_type));
      setForm((prev) => ({
        ...prev,
        legalName: prev.legalName || payload.company_profile.legal_name,
      }));
    },
    [workspace],
  );

  useEffect(() => {
    if (!workspace || !workspaceKey) {
      return;
    }
    const currentWorkspace = workspace;
    const controller = new AbortController();
    let active = true;

    async function loadWorkspaceContext() {
      setContextBusy(true);
      setSubmitError(null);
      try {
        const apiBase = getApiBaseUrl();
        const response = await fetch(
          `${apiBase}/catalog/workspace-context?tenant_id=${encodeURIComponent(currentWorkspace.tenantId)}&project_id=${encodeURIComponent(currentWorkspace.projectId)}`,
          {
            headers: buildApiHeaders(currentWorkspace.tenantId),
            signal: controller.signal,
          },
        );
        const payload = await parseJsonOrThrow<WorkspaceContextResponse>(response);
        if (active) {
          applyWorkspaceContext(payload);
        }
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        if (active) {
          setFactoryContext(null);
          setSubmitError(
            error instanceof Error
              ? error.message
              : "Workspace context could not be loaded.",
          );
        }
      } finally {
        if (active) {
          setContextBusy(false);
        }
      }
    }

    void loadWorkspaceContext();

    return () => {
      active = false;
      controller.abort();
    };
  }, [applyWorkspaceContext, workspace, workspaceKey]);

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
    Boolean(factoryContext?.readiness.is_ready) &&
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
      setSubmitError("Tenant and project fields are required.");
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
          company_profile: {
            legal_name: workspaceSetup.legalName.trim(),
            sector: workspaceSetup.sector.trim(),
            headquarters: workspaceSetup.headquarters.trim(),
            description: workspaceSetup.description.trim(),
            ceo_name: workspaceSetup.ceoName.trim(),
            ceo_message: workspaceSetup.ceoMessage.trim(),
            sustainability_approach: workspaceSetup.sustainabilityApproach.trim(),
          },
          brand_kit: {
            brand_name: workspaceSetup.brandName.trim(),
            logo_uri: workspaceSetup.logoUri.trim(),
            primary_color: workspaceSetup.primaryColor.trim(),
            secondary_color: workspaceSetup.secondaryColor.trim(),
            accent_color: workspaceSetup.accentColor.trim(),
            font_family_headings: workspaceSetup.headingFont.trim(),
            font_family_body: workspaceSetup.bodyFont.trim(),
            tone_name: workspaceSetup.toneName.trim(),
          },
        }),
      });
      const payload = await parseJsonOrThrow<WorkspaceBootstrapResponse>(response);
      applyWorkspaceContext(payload);
      setSubmitNotice(
        payload.factory_readiness.is_ready
          ? `Workspace ready. Tenant ${payload.tenant.slug} and project ${payload.project.code} are configured for the Report Factory.`
          : "Workspace created, but the Report Factory still needs profile or brand confirmation.",
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
      setSubmitError("Select or create a workspace first.");
      return;
    }
    if (!factoryContext) {
      setSubmitError("Workspace context must finish loading before launch.");
      return;
    }
    if (!factoryContext.readiness.is_ready) {
      setSubmitError("Clear profile and brand readiness blockers before starting a Report Factory run.");
      return;
    }
    if (!canSubmit) {
      setSubmitError("Complete the required launch fields before creating the run.");
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
        setSubmitError("Select at least one active ERP connector.");
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
      title="Report Factory Launchpad"
      subtitle="Configure the tenant workspace, align brand and company identity, and launch a governed sustainability reporting run."
      actions={[{ href: "/dashboard", label: "Back to Dashboard" }]}
    >
      <section className="mb-4 rounded-[1.75rem] border border-[color:var(--border)] bg-white/72 p-5 shadow-[var(--shadow-soft)]">
        <div className="mb-3 flex items-center gap-2">
          <Settings2 className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-base font-semibold">Workspace Bootstrap (Tenant + Project)</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Tenant Name</span>
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
            <span className="text-muted-foreground">Project Name</span>
            <input
              aria-label="Project Name"
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={workspaceProjectName}
              onChange={(event) => setWorkspaceProjectName(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Project Code</span>
            <input
              aria-label="Project Code"
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={workspaceProjectCode}
              onChange={(event) => setWorkspaceProjectCode(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Currency</span>
            <input
              aria-label="Currency"
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={workspaceCurrency}
              onChange={(event) => setWorkspaceCurrency(event.target.value)}
            />
          </label>
        </div>
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <div className="rounded-[1.5rem] border border-[color:var(--border)] bg-white/50 p-4">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Company Profile</p>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <label className="space-y-1 text-sm md:col-span-2">
                <span className="text-muted-foreground">Legal Entity Name</span>
                <input
                  aria-label="Workspace Legal Name"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.legalName}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, legalName: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Sector</span>
                <input
                  aria-label="Workspace Sector"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.sector}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, sector: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Headquarters</span>
                <input
                  aria-label="Workspace Headquarters"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.headquarters}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, headquarters: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-1 text-sm md:col-span-2">
                <span className="text-muted-foreground">Company Description</span>
                <textarea
                  aria-label="Workspace Company Description"
                  className="border-input bg-background min-h-24 w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.description}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, description: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">CEO Name</span>
                <input
                  aria-label="Workspace CEO Name"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.ceoName}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, ceoName: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Tone / Style</span>
                <input
                  aria-label="Workspace Tone Name"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.toneName}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, toneName: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-1 text-sm md:col-span-2">
                <span className="text-muted-foreground">CEO Message</span>
                <textarea
                  aria-label="Workspace CEO Message"
                  className="border-input bg-background min-h-24 w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.ceoMessage}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, ceoMessage: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-1 text-sm md:col-span-2">
                <span className="text-muted-foreground">Sustainability Approach</span>
                <textarea
                  aria-label="Workspace Sustainability Approach"
                  className="border-input bg-background min-h-24 w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.sustainabilityApproach}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, sustainabilityApproach: event.target.value }))
                  }
                />
              </label>
            </div>
          </div>
          <div className="rounded-[1.5rem] border border-[color:var(--border)] bg-white/50 p-4">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Brand Kit</p>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Brand Name</span>
                <input
                  aria-label="Workspace Brand Name"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.brandName}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, brandName: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Logo URI</span>
                <input
                  aria-label="Workspace Logo URI"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.logoUri}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, logoUri: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Primary Color</span>
                <input
                  aria-label="Workspace Primary Color"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.primaryColor}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, primaryColor: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Secondary Color</span>
                <input
                  aria-label="Workspace Secondary Color"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.secondaryColor}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, secondaryColor: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Accent Color</span>
                <input
                  aria-label="Workspace Accent Color"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.accentColor}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, accentColor: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Heading Font</span>
                <input
                  aria-label="Workspace Heading Font"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.headingFont}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, headingFont: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-1 text-sm md:col-span-2">
                <span className="text-muted-foreground">Body Font</span>
                <input
                  aria-label="Workspace Body Font"
                  className="border-input bg-background w-full rounded-md border px-3 py-2"
                  value={workspaceSetup.bodyFont}
                  onChange={(event) =>
                    setWorkspaceSetup((prev) => ({ ...prev, bodyFont: event.target.value }))
                  }
                />
              </label>
            </div>
          </div>
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
            {workspaceBusy ? "Configuring..." : "Bootstrap Workspace"}
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
              No workspace selected yet.
            </p>
          )}
        </div>
        {contextBusy && !factoryContext ? (
          <p
            className="mt-2 text-xs text-muted-foreground"
            data-testid="factory-context-loading"
        >
            Loading Report Factory context for the current workspace...
          </p>
        ) : null}
        {factoryContext ? (
          <div
            className="mt-4 grid gap-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/8 p-4 md:grid-cols-[0.8fr_1.2fr]"
            data-testid="factory-context-panel"
          >
            <div>
              <p className="text-xs uppercase tracking-[0.16em] text-emerald-700 dark:text-emerald-300">
                Report Factory Context
              </p>
              <p className="mt-2 text-sm">
                Blueprint: <strong>{factoryContext.blueprintVersion}</strong>
              </p>
              <p className="mt-1 text-sm">
                Provisioned connector count: <strong>{factoryContext.integrations.length}</strong>
              </p>
              <div className="mt-3 rounded-xl border border-emerald-500/20 bg-background/80 px-3 py-3 text-sm" data-testid="factory-readiness-panel">
                <p className="font-medium">
                  Readiness: {factoryContext.readiness.is_ready ? "ready" : "blocked"}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Company profile: {factoryContext.readiness.company_profile_ready ? "ok" : "missing"} | Brand kit: {factoryContext.readiness.brand_kit_ready ? "ok" : "missing"}
                </p>
                {factoryContext.readiness.blockers.length > 0 ? (
                  <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                    {factoryContext.readiness.blockers.map((blocker) => (
                      <li key={`${blocker.code}-${blocker.message}`}>{blocker.code}: {blocker.message}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Connector Scope</p>
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
        <section className="rounded-[1.75rem] border border-[color:var(--border)] bg-white/72 p-5 shadow-[var(--shadow-soft)]">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <p className="text-muted-foreground text-xs uppercase tracking-[0.16em]">
                Step {step + 1} / {STEP_TITLES.length}
              </p>
              <h2 className="mt-1 text-xl font-semibold">{STEP_TITLES[step]}</h2>
            </div>
            <p className="text-muted-foreground rounded-full border px-3 py-1 text-xs">
              Completion {score}%
            </p>
          </div>

          {step === 0 ? (
            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-2 text-sm">
                <span className="text-muted-foreground">Legal Entity Name</span>
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
                <span className="text-muted-foreground">Tax / Registry ID</span>
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
                <span className="text-muted-foreground">Framework Target</span>
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
                <span className="text-muted-foreground">Reporting Year</span>
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
                <span className="text-muted-foreground">Operation Countries</span>
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
                Include the Scope 3 calculation cycle for this run
              </label>
            </div>
          ) : null}

          {step === 2 ? (
            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-2 text-sm">
                <span className="text-muted-foreground">Sustainability Owner</span>
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
                <span className="text-muted-foreground">Board Approver</span>
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
                <span className="text-muted-foreground">Approval SLA (days)</span>
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
              Back
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
                {isSubmitting ? "Creating run..." : "Create report run"}
              </Button>
            ) : (
              <Button
                type="button"
                onClick={() =>
                  setStep((prev) => Math.min(STEP_TITLES.length - 1, prev + 1))
                }
                data-testid="wizard-next-button"
              >
                Next
                <ChevronRight className="h-4 w-4" />
              </Button>
            )}
          </div>

          {factoryContext && !factoryContext.readiness.is_ready ? (
            <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">
              The create run action stays locked until the readiness blockers are cleared.
            </p>
          ) : null}

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

        <aside className="relative overflow-hidden rounded-[1.75rem] border border-[color:var(--border)] bg-white/72 p-5 shadow-[var(--shadow-soft)]">
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
              Factory Summary
            </p>
            <h3 className="text-base font-semibold">Run Summary</h3>
            <p className="text-muted-foreground mt-1 text-sm">
              Inputs collected in the wizard are written directly into the run state and used for connector sync and retrieval planning.
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
                Payload preview
              </div>
              <p>Framework: {form.framework}</p>
              <p>Year: {form.reportingYear}</p>
              <p>Scope 3: {form.includeScope3 ? "Included" : "Excluded"}</p>
              <p>SLA: {form.approvalSlaDays} days</p>
              <p>
                Workspace: {workspace ? `${workspace.tenantId} / ${workspace.projectId}` : "not selected"}
              </p>
            </div>
          </div>
        </aside>
      </div>
    </AppShell>
  );
}
