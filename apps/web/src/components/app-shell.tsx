"use client";

import { useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import {
  Bell,
  ChartLine,
  Database,
  FileStack,
  ListChecks,
  PanelLeft,
  SearchCode,
  Search,
  ShieldCheck,
  UserCircle2,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

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
  { href: "/reports/new", label: "New Report", icon: FileStack },
  { href: "/evidence-center", label: "Evidence Center", icon: Database },
  { href: "/retrieval-lab", label: "Retrieval Lab", icon: SearchCode },
  { href: "/approval-center", label: "Approval Center", icon: ListChecks },
];

function isActivePath(activePath: string, href: string): boolean {
  if (href === "/dashboard") {
    return activePath === "/dashboard";
  }
  return activePath.startsWith(href);
}

function normalizeSegment(segment: string): string {
  return segment
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

type AppShellProps = {
  activePath: string;
  title: string;
  subtitle: string;
  children: ReactNode;
  actions?: HeaderAction[];
};

function SidebarNav({
  activePath,
  compact = false,
  onNavigate,
}: {
  activePath: string;
  compact?: boolean;
  onNavigate?: () => void;
}) {
  return (
    <nav className="space-y-1">
      <p className="px-2 pb-2 text-xs font-medium tracking-wide text-sidebar-foreground/70">
        Overview
      </p>
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const isActive = isActivePath(activePath, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            className={cn(
              "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground flex items-center gap-2 rounded-md px-2 py-2 text-sm text-sidebar-foreground transition-colors",
              isActive && "bg-sidebar-accent text-sidebar-accent-foreground",
              compact && "justify-center px-0",
            )}
          >
            <Icon className="size-4 shrink-0" />
            {!compact ? <span>{item.label}</span> : null}
          </Link>
        );
      })}
    </nav>
  );
}

export function AppShell({
  activePath,
  title,
  subtitle,
  children,
  actions = [],
}: AppShellProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const breadcrumbs = useMemo(() => {
    const segments = activePath.split("/").filter(Boolean);
    if (segments.length === 0) {
      return ["Dashboard"];
    }
    return segments.map(normalizeSegment);
  }, [activePath]);

  const sidebarWidthClass = collapsed ? "w-16" : "w-64";

  return (
    <div className="group/sidebar-wrapper bg-sidebar flex min-h-svh w-full md:flex-row-reverse">
      <aside
        className={cn(
          "border-sidebar-border bg-sidebar text-sidebar-foreground hidden border-l transition-[width] duration-200 ease-linear md:flex md:flex-col",
          sidebarWidthClass,
        )}
      >
        <div className="border-sidebar-border border-b p-2">
          <Link
            href="/dashboard"
            className="hover:bg-sidebar-accent flex items-center gap-2 rounded-md px-2 py-2 transition-colors"
          >
            <ShieldCheck className="size-5 shrink-0" />
            {!collapsed ? (
              <div>
                <p className="text-sm font-semibold">Veni AI Sustainability Cockpit</p>
                <p className="text-xs text-sidebar-foreground/70">Board-ready ESG</p>
              </div>
            ) : null}
          </Link>
        </div>

        <div className="flex-1 overflow-auto p-2">
          <SidebarNav activePath={activePath} compact={collapsed} />
        </div>

        <div className="border-sidebar-border border-t p-2">
          <div
            className={cn(
              "rounded-md border border-sidebar-border bg-background/70 p-2 text-xs text-muted-foreground",
              collapsed && "p-1 text-center",
            )}
          >
            {!collapsed ? "Verifier gate active" : "VG"}
          </div>
        </div>
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/50"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          />
          <aside className="bg-sidebar text-sidebar-foreground border-sidebar-border relative z-10 ml-auto h-full w-[18rem] border-l p-2">
            <div className="mb-2 flex items-center justify-between rounded-md px-2 py-2">
              <div>
                <p className="text-sm font-semibold">Veni AI Sustainability Cockpit</p>
                <p className="text-xs text-sidebar-foreground/70">Board-ready ESG</p>
              </div>
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                onClick={() => setMobileOpen(false)}
              >
                <X className="size-4" />
              </Button>
            </div>
            <SidebarNav activePath={activePath} onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      ) : null}

      <main className="bg-background relative flex w-full flex-1 flex-col">
        <header className="border-border bg-background/95 supports-[backdrop-filter]:bg-background/60 sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between gap-2 border-b px-4 backdrop-blur">
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="-ml-1"
              onClick={() => {
                if (window.matchMedia("(max-width: 767px)").matches) {
                  setMobileOpen(true);
                  return;
                }
                setCollapsed((previous) => !previous);
              }}
            >
              <PanelLeft className="size-4" />
            </Button>
            <div className="bg-border h-4 w-px" />
            <div className="text-muted-foreground flex items-center gap-1 text-sm">
              <Link href="/dashboard" className="hover:text-foreground transition-colors">
                Home
              </Link>
              {breadcrumbs.map((crumb, index) => (
                <span key={`${crumb}-${index}`} className="flex items-center gap-1">
                  <span>/</span>
                  <span className="text-foreground">{crumb}</span>
                </span>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative hidden md:block">
              <Search className="text-muted-foreground absolute top-1/2 left-2 size-4 -translate-y-1/2" />
              <input
                type="search"
                placeholder="Search"
                className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring h-9 w-56 rounded-md border pl-8 text-sm outline-none focus-visible:ring-2"
              />
            </div>
            <Button type="button" size="icon-sm" variant="outline">
              <Bell className="size-4" />
            </Button>
            <Button type="button" variant="outline" size="sm" className="gap-2">
              <UserCircle2 className="size-4" />
              Admin
            </Button>
          </div>
        </header>

        <div className="h-[calc(100dvh-4rem)] overflow-auto">
          <div className="flex flex-1 flex-col p-4 md:px-6">
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
                <p className="text-muted-foreground mt-1 text-sm">{subtitle}</p>
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
            {children}
          </div>
        </div>
      </main>
    </div>
  );
}
