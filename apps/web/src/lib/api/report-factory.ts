import { z } from "zod";

import { resolveBrandLogoUri } from "@/lib/brand";
import type { WorkspaceContextResponse } from "./catalog";

export const reportFrameworkSchema = z.enum(["TSRS", "CSRD", "TSRS+CSRD"]);

export const launchpadWizardStateSchema = z.object({
  legalName: z.string(),
  taxId: z.string(),
  framework: reportFrameworkSchema,
  reportingYear: z.string(),
  operationCountries: z.string(),
  includeScope3: z.boolean(),
  sustainabilityOwner: z.string(),
  boardApprover: z.string(),
  approvalSlaDays: z.string(),
});

export const workspaceSetupStateSchema = z.object({
  legalName: z.string(),
  sector: z.string(),
  headquarters: z.string(),
  description: z.string(),
  ceoName: z.string(),
  ceoMessage: z.string(),
  sustainabilityApproach: z.string(),
  brandName: z.string(),
  logoUri: z.string(),
  primaryColor: z.string(),
  secondaryColor: z.string(),
  accentColor: z.string(),
  headingFont: z.string(),
  bodyFont: z.string(),
  toneName: z.string(),
});

export const workspaceBootstrapFormSchema = z.object({
  tenantName: z.string().trim().min(2),
  tenantSlug: z.string().trim().min(2),
  projectName: z.string().trim().min(2),
  projectCode: z.string().trim().min(2),
  workspaceCurrency: z.string().trim().min(1),
  workspaceSetup: workspaceSetupStateSchema,
});

export const factoryContextSchema = z.object({
  companyProfileId: z.string(),
  brandKitId: z.string(),
  blueprintVersion: z.string(),
  integrations: z.array(
    z.object({
      id: z.string(),
      connectorType: z.string(),
      displayName: z.string(),
      status: z.string(),
      supportTier: z.enum(["certified", "beta", "unsupported"]),
      certifiedVariant: z.string().nullable().optional(),
      productVersion: z.string().nullable().optional(),
      healthBand: z.enum(["green", "amber", "red"]),
      assignedAgentStatus: z.string().nullable().optional(),
    }),
  ),
  readiness: z.object({
    is_ready: z.boolean(),
    company_profile_ready: z.boolean(),
    brand_kit_ready: z.boolean(),
    blockers: z.array(
      z.object({
        code: z.string(),
        message: z.string(),
      }),
    ),
  }),
});

export type LaunchpadWizardState = z.infer<typeof launchpadWizardStateSchema>;
export type WorkspaceSetupState = z.infer<typeof workspaceSetupStateSchema>;
export type WorkspaceBootstrapForm = z.infer<typeof workspaceBootstrapFormSchema>;
export type FactoryContext = z.infer<typeof factoryContextSchema>;

export const STEP_TITLES = [
  "Workspace Context",
  "Report Scope",
  "Governance",
] as const;

export const INITIAL_LAUNCHPAD_STATE: LaunchpadWizardState = {
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

export const INITIAL_WORKSPACE_SETUP: WorkspaceSetupState = {
  legalName: "",
  sector: "",
  headquarters: "",
  description: "",
  ceoName: "",
  ceoMessage: "",
  sustainabilityApproach: "",
  brandName: "",
  logoUri: resolveBrandLogoUri(null),
  primaryColor: "#f07f13",
  secondaryColor: "#262421",
  accentColor: "#d2b24a",
  headingFont: "Inter",
  bodyFont: "Inter",
  toneName: "editorial-corporate",
};

export function resolveFrameworkTargets(form: LaunchpadWizardState): string[] {
  if (form.framework === "TSRS+CSRD") {
    return ["TSRS1", "TSRS2", "CSRD"];
  }
  if (form.framework === "TSRS") {
    return ["TSRS1", "TSRS2"];
  }
  return ["CSRD"];
}

export function buildRetrievalTasks(form: LaunchpadWizardState, frameworkTarget: string[]) {
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

export function completionScore(form: LaunchpadWizardState): number {
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

export function isConnectorLaunchReady(integration: {
  status: string;
  supportTier: "certified" | "beta" | "unsupported";
  healthBand: "green" | "amber" | "red";
}) {
  return (
    integration.status === "active" &&
    integration.supportTier === "certified" &&
    integration.healthBand === "green"
  );
}

export function buildFactoryContext(
  payload: WorkspaceContextResponse,
): FactoryContext {
  return factoryContextSchema.parse({
    companyProfileId: payload.company_profile.id,
    brandKitId: payload.brand_kit.id,
    blueprintVersion: payload.blueprint_version,
    integrations: payload.integrations.map((item) => ({
      id: item.id,
      connectorType: item.connector_type,
      displayName: item.display_name,
      status: item.status,
      supportTier: item.support_tier,
      certifiedVariant: item.certified_variant ?? null,
      productVersion: item.product_version ?? null,
      healthBand: item.health_band,
      assignedAgentStatus: item.assigned_agent_status ?? null,
    })),
    readiness: payload.factory_readiness,
  });
}

export function buildWorkspaceSetupState(
  payload: WorkspaceContextResponse,
): WorkspaceSetupState {
  return workspaceSetupStateSchema.parse({
    legalName: payload.company_profile.legal_name ?? "",
    sector: payload.company_profile.sector ?? "",
    headquarters: payload.company_profile.headquarters ?? "",
    description: payload.company_profile.description ?? "",
    ceoName: payload.company_profile.ceo_name ?? "",
    ceoMessage: payload.company_profile.ceo_message ?? "",
    sustainabilityApproach: payload.company_profile.sustainability_approach ?? "",
    brandName: payload.brand_kit.brand_name ?? "",
    logoUri: resolveBrandLogoUri(payload.brand_kit.logo_uri),
    primaryColor: payload.brand_kit.primary_color,
    secondaryColor: payload.brand_kit.secondary_color,
    accentColor: payload.brand_kit.accent_color,
    headingFont: payload.brand_kit.font_family_headings,
    bodyFont: payload.brand_kit.font_family_body,
    toneName: payload.brand_kit.tone_name ?? "",
  });
}
