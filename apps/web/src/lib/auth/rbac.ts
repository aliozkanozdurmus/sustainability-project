export type AppRole =
  | "admin"
  | "compliance_manager"
  | "analyst"
  | "board_member"
  | "committee_secretary"
  | "auditor_readonly";

export const routeRoleMatrix: Record<string, AppRole[]> = {
  "/app/dashboard/executive": [
    "admin",
    "compliance_manager",
    "analyst",
    "board_member",
    "committee_secretary",
  ],
  "/app/dashboard/board-cockpit": [
    "admin",
    "compliance_manager",
    "board_member",
    "committee_secretary",
  ],
  "/app/dashboard/operations-sla": [
    "admin",
    "compliance_manager",
    "committee_secretary",
  ],
  "/app/projects/[projectId]/verify": [
    "admin",
    "compliance_manager",
    "analyst",
    "auditor_readonly",
  ],
  "/app/projects/[projectId]/publish": [
    "admin",
    "compliance_manager",
    "board_member",
  ],
  "/app/approval-center": [
    "admin",
    "compliance_manager",
    "committee_secretary",
    "board_member",
  ],
};

export function canAccessRoute(role: AppRole, route: string): boolean {
  const allowed = routeRoleMatrix[route] ?? [];
  return allowed.includes(role);
}

export function getAccessibleRoutes(role: AppRole): string[] {
  return Object.keys(routeRoleMatrix).filter((route) => canAccessRoute(role, route));
}
