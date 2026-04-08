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
import { persistWorkspaceContext } from "@/lib/api/client";
import {
  syncIntegrations,
  type WorkspaceContextResponse,
  useBootstrapWorkspaceMutation,
  useWorkspaceContextQuery,
} from "@/lib/api/catalog";
import { createRun } from "@/lib/api/runs";
import {
  INITIAL_LAUNCHPAD_STATE,
  INITIAL_WORKSPACE_SETUP,
  STEP_TITLES,
  buildFactoryContext,
  buildRetrievalTasks,
  buildWorkspaceSetupState,
  completionScore,
  isConnectorLaunchReady,
  launchpadWizardStateSchema,
  resolveFrameworkTargets,
  workspaceBootstrapFormSchema,
  type FactoryContext,
  type LaunchpadWizardState,
  type WorkspaceSetupState,
} from "@/lib/api/report-factory";
import { resolveBrandLogoUri } from "@/lib/brand";
import { useWorkspaceContext } from "@/lib/api/workspace-store";

const INITIAL_WORKSPACE_SETUP_STATE: WorkspaceSetupState = {
  ...INITIAL_WORKSPACE_SETUP,
  logoUri: resolveBrandLogoUri(null),
};

function toUiErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export default function NewReportPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<LaunchpadWizardState>(INITIAL_LAUNCHPAD_STATE);
  const workspace = useWorkspaceContext();
  const [workspaceTenantName, setWorkspaceTenantName] = useState("");
  const [workspaceTenantSlug, setWorkspaceTenantSlug] = useState("");
  const [workspaceProjectName, setWorkspaceProjectName] = useState("");
  const [workspaceProjectCode, setWorkspaceProjectCode] = useState("");
  const [workspaceCurrency, setWorkspaceCurrency] = useState("TRY");
  const [workspaceSetup, setWorkspaceSetup] = useState<WorkspaceSetupState>(INITIAL_WORKSPACE_SETUP_STATE);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitNotice, setSubmitNotice] = useState<string | null>(null);
  const [factoryContext, setFactoryContext] = useState<FactoryContext | null>(null);
  const [connectorScope, setConnectorScope] = useState<string[]>([
    "sap_odata",
    "logo_tiger_sql_view",
    "netsis_rest",
  ]);
  const workspaceContextQuery = useWorkspaceContextQuery(workspace);
  const bootstrapWorkspaceMutation = useBootstrapWorkspaceMutation();
  const workspaceBusy = bootstrapWorkspaceMutation.isPending;
  const contextBusy = workspaceContextQuery.isPending || workspaceContextQuery.isFetching;
  const pageError =
    submitError ??
    (workspaceContextQuery.isError
      ? toUiErrorMessage(workspaceContextQuery.error, "Workspace context could not be loaded.")
      : null);
  const score = useMemo(() => completionScore(form), [form]);
  const isLastStep = step === STEP_TITLES.length - 1;
  const selectedIntegrations = useMemo(
    () =>
      factoryContext?.integrations.filter((item) =>
        connectorScope.includes(item.connectorType),
      ) ?? [],
    [connectorScope, factoryContext],
  );
  const blockedSelectedIntegrations = useMemo(
    () => selectedIntegrations.filter((item) => !isConnectorLaunchReady(item)),
    [selectedIntegrations],
  );

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
      setFactoryContext(buildFactoryContext(payload));
      const nextWorkspaceSetup = buildWorkspaceSetupState(payload);
      setWorkspaceSetup({
        ...nextWorkspaceSetup,
        logoUri: resolveBrandLogoUri(payload.brand_kit.logo_uri),
      });
      setConnectorScope(payload.integrations.map((item) => item.connector_type));
      setForm((prev) => ({
        ...prev,
        legalName: prev.legalName || payload.company_profile.legal_name,
      }));
    },
    [workspace?.projectId, workspace?.tenantId],
  );

  useEffect(() => {
    if (!workspaceContextQuery.data) {
      return;
    }
    applyWorkspaceContext(workspaceContextQuery.data);
  }, [applyWorkspaceContext, workspaceContextQuery.data]);

  useEffect(() => {
    if (!workspaceContextQuery.isError) {
      return;
    }
    setFactoryContext(null);
  }, [workspaceContextQuery.isError]);

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
    selectedIntegrations.length > 0 &&
    blockedSelectedIntegrations.length === 0 &&
    !contextBusy;

  async function handleBootstrapWorkspace() {
    setSubmitError(null);
    setSubmitNotice(null);
    const parsedBootstrapForm = workspaceBootstrapFormSchema.safeParse({
      tenantName: workspaceTenantName,
      tenantSlug: workspaceTenantSlug,
      projectName: workspaceProjectName,
      projectCode: workspaceProjectCode,
      workspaceCurrency,
      workspaceSetup,
    });

    if (!parsedBootstrapForm.success) {
      setSubmitError(parsedBootstrapForm.error.issues[0]?.message ?? "Tenant and project fields are required.");
      return;
    }

    try {
      const payload = await bootstrapWorkspaceMutation.mutateAsync({
        tenantHeader: workspace?.tenantId ?? "dev-tenant",
        tenant_name: parsedBootstrapForm.data.tenantName.trim(),
        tenant_slug: parsedBootstrapForm.data.tenantSlug.trim(),
        project_name: parsedBootstrapForm.data.projectName.trim(),
        project_code: parsedBootstrapForm.data.projectCode.trim(),
        reporting_currency: parsedBootstrapForm.data.workspaceCurrency.trim().toUpperCase(),
        company_profile: {
          legal_name: parsedBootstrapForm.data.workspaceSetup.legalName.trim(),
          sector: parsedBootstrapForm.data.workspaceSetup.sector.trim(),
          headquarters: parsedBootstrapForm.data.workspaceSetup.headquarters.trim(),
          description: parsedBootstrapForm.data.workspaceSetup.description.trim(),
          ceo_name: parsedBootstrapForm.data.workspaceSetup.ceoName.trim(),
          ceo_message: parsedBootstrapForm.data.workspaceSetup.ceoMessage.trim(),
          sustainability_approach: parsedBootstrapForm.data.workspaceSetup.sustainabilityApproach.trim(),
        },
        brand_kit: {
          brand_name: parsedBootstrapForm.data.workspaceSetup.brandName.trim(),
          logo_uri: parsedBootstrapForm.data.workspaceSetup.logoUri.trim(),
          primary_color: parsedBootstrapForm.data.workspaceSetup.primaryColor.trim(),
          secondary_color: parsedBootstrapForm.data.workspaceSetup.secondaryColor.trim(),
          accent_color: parsedBootstrapForm.data.workspaceSetup.accentColor.trim(),
          font_family_headings: parsedBootstrapForm.data.workspaceSetup.headingFont.trim(),
          font_family_body: parsedBootstrapForm.data.workspaceSetup.bodyFont.trim(),
          tone_name: parsedBootstrapForm.data.workspaceSetup.toneName.trim(),
        },
      });
      applyWorkspaceContext(payload);
      setSubmitNotice(
        payload.factory_readiness.is_ready
          ? `Workspace ready. Tenant ${payload.tenant.slug} and project ${payload.project.code} are configured for the Report Factory.`
          : "Workspace created, but the Report Factory still needs profile or brand confirmation.",
      );
    } catch (error) {
      setSubmitError(toUiErrorMessage(error, "Workspace bootstrap failed."));
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
    if (selectedIntegrations.length === 0) {
      setSubmitError("Select at least one ERP connector.");
      return;
    }
    if (blockedSelectedIntegrations.length > 0) {
      setSubmitError(
        `Selected connectors are not launch-ready: ${blockedSelectedIntegrations
          .map((item) => item.displayName)
          .join(", ")}. Complete Integrations Setup first.`,
      );
      return;
    }

    setIsSubmitting(true);
    try {
      const validatedForm = launchpadWizardStateSchema.parse(form);
      const frameworkTarget = resolveFrameworkTargets(validatedForm);
      const activeConnectorIds = selectedIntegrations.map((item) => item.id);

      if (activeConnectorIds.length === 0) {
        setSubmitError("Select at least one active ERP connector.");
        return;
      }

      await syncIntegrations({
        tenant_id: workspace.tenantId,
        project_id: workspace.projectId,
        connector_ids: activeConnectorIds,
      });

      const payload = await createRun({
        tenant_id: workspace.tenantId,
        project_id: workspace.projectId,
        framework_target: frameworkTarget,
        active_reg_pack_version: "core-pack-v1",
        report_blueprint_version: factoryContext.blueprintVersion,
        company_profile_ref: factoryContext.companyProfileId,
        brand_kit_ref: factoryContext.brandKitId,
        connector_scope: connectorScope,
        scope_decision: {
          reporting_year: validatedForm.reportingYear,
          include_scope3: validatedForm.includeScope3,
          operation_countries: validatedForm.operationCountries,
          sustainability_owner: validatedForm.sustainabilityOwner,
          board_approver: validatedForm.boardApprover,
          approval_sla_days: Number(validatedForm.approvalSlaDays),
          retrieval_tasks: buildRetrievalTasks(validatedForm, frameworkTarget),
        },
      });
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
      actions={[
        { href: "/integrations/setup", label: "Open Integrations Setup" },
        { href: "/dashboard", label: "Back to Dashboard" },
      ]}
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
                      className="flex items-center gap-3 rounded-xl border bg-background px-3 py-3 text-sm"
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
                      <div className="min-w-0">
                        <p className="font-medium">{integration.displayName}</p>
                        <p className="text-xs text-muted-foreground">
                          {integration.supportTier} | {integration.healthBand} | {integration.status}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {integration.certifiedVariant ?? "variant pending"} | agent {integration.assignedAgentStatus ?? "unassigned"}
                        </p>
                      </div>
                    </label>
                  );
                })}
              </div>
              {blockedSelectedIntegrations.length > 0 ? (
                <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">
                  Launch stays locked until selected connectors are `active`, `certified`, and `green`. Use Integrations Setup to clear onboarding blockers.
                </p>
              ) : null}
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
                      framework: event.target.value as LaunchpadWizardState["framework"],
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

          {pageError ? (
            <div
              className="mt-4 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              data-testid="new-report-error"
            >
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <p>{pageError}</p>
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
