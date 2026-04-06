"use client";

import { useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import {
  Bell,
  ChartLine,
  Database,
  FileStack,
  ListChecks,
  Menu,
  Search,
  SearchCode,
  ShieldCheck,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { SectionHeading, StatusChip, SurfaceCard } from "@/components/workbench-ui";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

type HeaderAction = {
  href: string;
  label: string;
};

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: ChartLine },
  { href: "/reports/new", label: "Report Factory", icon: FileStack },
  { href: "/evidence-center", label: "Evidence", icon: Database },
  { href: "/retrieval-lab", label: "Retrieval Lab", icon: SearchCode },
  { href: "/approval-center", label: "Publish Board", icon: ListChecks },
];

function isActivePath(activePath: string, href: string): boolean {
  if (href === "/dashboard") {
    return activePath === "/dashboard";
  }
  return activePath.startsWith(href);
}

function NavigationBar({
  activePath,
  onNavigate,
  compact = false,
}: {
  activePath: string;
  onNavigate?: () => void;
  compact?: boolean;
}) {
  return (
    <nav className={cn("flex items-center gap-1 overflow-x-auto soft-scrollbar", compact && "flex-col items-stretch")}>
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const active = isActivePath(activePath, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            className={cn(
              "inline-flex items-center gap-2 rounded-full px-3 py-2 text-[12px] font-medium transition-all",
              compact && "justify-start rounded-[1rem] px-3.5 py-3",
              active
                ? "bg-primary text-primary-foreground shadow-[inset_0_-1px_0_rgba(255,255,255,0.08)]"
                : "text-[color:var(--foreground-soft)] hover:bg-white/65 hover:text-foreground",
            )}
          >
            <Icon className="size-4" />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

function breadcrumbsFromPath(activePath: string) {
  return activePath
    .split("/")
    .filter(Boolean)
    .map((segment) =>
      segment
        .split("-")
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" "),
    );
}

export function AppShell({
  activePath,
  title,
  subtitle,
  children,
  actions = [],
}: {
  activePath: string;
  title: string;
  subtitle: string;
  children: ReactNode;
  actions?: HeaderAction[];
}) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const breadcrumbs = useMemo(() => breadcrumbsFromPath(pathname || activePath), [activePath, pathname]);

  return (
    <div className="min-h-screen bg-canvas px-3 py-4 md:px-5 md:py-6">
      <div className="mx-auto max-w-[1480px] workbench-shell px-3 py-3 md:px-5 md:py-5">
        <SurfaceCard className="px-3 py-3 md:px-4 md:py-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <Link href="/dashboard" className="inline-flex items-center gap-2 rounded-full border border-black/6 bg-white/75 px-3 py-2 text-[13px] font-semibold text-foreground">
                <ShieldCheck className="size-4" />
                <span>Veni AI</span>
              </Link>
              <div className="hidden xl:block">
                <NavigationBar activePath={activePath} />
              </div>
            </div>

            <div className="hidden items-center gap-2 lg:flex">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[color:var(--foreground-muted)]" />
                <input
                  type="search"
                  placeholder="Search runs, artifacts, connectors"
                  className="h-10 w-72 rounded-full border border-[color:var(--border)] bg-white/70 pl-9 pr-3 text-[13px] text-foreground outline-none transition focus:border-[color:var(--accent-strong)] focus:ring-4 focus:ring-ring"
                />
              </div>
              <Button type="button" variant="outline" size="icon-sm" aria-label="Notifications">
                <Bell className="size-4" />
              </Button>
              <div className="pill-surface gap-2 px-3.5 py-2">
                <span className="font-semibold text-foreground">Admin</span>
                <StatusChip tone="good">Gate active</StatusChip>
              </div>
            </div>

            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              className="xl:hidden"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <Menu className="size-4" />
            </Button>
          </div>
        </SurfaceCard>

        {mobileOpen ? (
          <div className="fixed inset-0 z-50 bg-[rgba(24,22,19,0.28)] backdrop-blur-sm xl:hidden">
            <div className="ml-auto h-full w-[18rem] bg-[color:var(--workbench)] px-4 py-4 shadow-2xl">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[12px] uppercase tracking-[0.18em] text-[color:var(--foreground-muted)]">Navigation</p>
                  <p className="mt-1 text-[18px] font-semibold text-foreground">Report Factory</p>
                </div>
                <Button type="button" variant="outline" size="icon-sm" onClick={() => setMobileOpen(false)}>
                  <X className="size-4" />
                </Button>
              </div>
              <div className="mt-4">
                <NavigationBar activePath={activePath} onNavigate={() => setMobileOpen(false)} compact />
              </div>
            </div>
          </div>
        ) : null}

        <div className="mt-4 flex flex-col gap-4">
          <SurfaceCard className="px-4 py-4 md:px-5 md:py-5">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2 text-[12px] text-[color:var(--foreground-muted)]">
                  <span className="pill-surface">Command deck</span>
                  {breadcrumbs.map((crumb, index) => (
                    <span key={`${crumb}-${index}`} className="inline-flex items-center gap-2">
                      {index === 0 ? null : <span>/</span>}
                      <span>{crumb}</span>
                    </span>
                  ))}
                </div>
                <SectionHeading title={title} description={subtitle} />
              </div>

              {actions.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {actions.map((action, index) => (
                    <Button key={action.href} asChild variant={index === 0 ? "default" : "outline"}>
                      <Link href={action.href}>{action.label}</Link>
                    </Button>
                  ))}
                </div>
              ) : null}
            </div>
          </SurfaceCard>

          <div className="space-y-4">{children}</div>
        </div>
      </div>
    </div>
  );
}
