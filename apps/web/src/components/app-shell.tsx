"use client";

// Bu bilesen, app shell arayuz parcasini kurar.

import {
  startTransition,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import {
  Bell,
  ChartLine,
  CircleDot,
  Command,
  Database,
  FileStack,
  ListChecks,
  Menu,
  Search,
  SearchCode,
  Settings2,
  X,
} from "lucide-react";

import { NotificationCenterPanel } from "@/components/notification-center";
import { DEFAULT_BRAND_LOGO_PATH } from "@/lib/brand";
import { useDashboardNotificationsQuery } from "@/lib/api/dashboard";
import {
  buildNotificationSessionStorageKey,
  countUnreadNotifications,
  formatUnreadBadgeCount,
  markNotificationsSeen,
  readSeenNotificationIds,
} from "@/lib/notification-center";
import { useWorkspaceContext } from "@/lib/api/workspace-store";
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

type SearchTarget = NavItem & {
  groupLabel: string;
  description: string;
  keywords: string[];
  testId: string;
};

const NAV_GROUPS: Array<{ label: string; items: NavItem[] }> = [
  {
    label: "Workspace",
    items: [{ href: "/dashboard", label: "Dashboard", icon: ChartLine }],
  },
  {
    label: "Factory",
    items: [
      { href: "/integrations/setup", label: "Integrations", icon: Settings2 },
      { href: "/reports/new", label: "Report Factory", icon: FileStack },
      { href: "/evidence-center", label: "Evidence", icon: Database },
      { href: "/retrieval-lab", label: "Retrieval Lab", icon: SearchCode },
      { href: "/approval-center", label: "Publish Board", icon: ListChecks },
    ],
  },
];

const SEARCH_TARGET_METADATA: Record<string, { description: string; keywords: string[] }> = {
  "/dashboard": {
    description: "Connector freshness, KPI strip, and package lane overview",
    keywords: [
      "dashboard",
      "overview",
      "kpi",
      "connector",
      "connectors",
      "pipeline",
      "genel bakis",
    ],
  },
  "/reports/new": {
    description: "Create a new reporting run with blueprint, profile, and connector scope",
    keywords: [
      "report",
      "new report",
      "run",
      "create",
      "factory",
      "rapor",
      "raporlama",
      "yeni rapor",
    ],
  },
  "/integrations/setup": {
    description: "Discover, preflight, preview, and activate certified ERP connectors",
    keywords: ["integrations", "erp", "setup", "connector", "sap", "logo", "netsis", "onboarding"],
  },
  "/evidence-center": {
    description: "Inspect evidence inventory, source documents, and extraction quality",
    keywords: [
      "evidence",
      "document",
      "citation",
      "source",
      "artifact",
      "kanit",
      "dokuman",
      "atif",
    ],
  },
  "/retrieval-lab": {
    description: "Run hybrid evidence search with semantic diagnostics and scoring",
    keywords: ["retrieval", "search", "semantic", "hybrid", "vector", "arama", "erişim", "lab"],
  },
  "/approval-center": {
    description: "Review run queue, package progress, and controlled publish readiness",
    keywords: [
      "approval",
      "publish",
      "review",
      "runs",
      "package",
      "artifacts",
      "onay",
      "yayin",
      "kuyruk",
    ],
  },
};

const SEARCH_TARGETS: SearchTarget[] = NAV_GROUPS.flatMap((group) =>
  group.items.map((item) => {
    const metadata = SEARCH_TARGET_METADATA[item.href] ?? {
      description: `${group.label} surface`,
      keywords: [],
    };
    return {
      ...item,
      groupLabel: group.label,
      description: metadata.description,
      keywords: metadata.keywords,
      testId: `global-search-result-${item.href.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "") || "root"}`,
    };
  }),
);

function isActivePath(activePath: string, href: string): boolean {
  if (href === "/dashboard") {
    return activePath === "/dashboard";
  }
  return activePath.startsWith(href);
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

function normalizeSearchValue(value: string): string {
  return value.trim().toLocaleLowerCase();
}

function scoreSearchTarget(target: SearchTarget, normalizedQuery: string): number {
  if (!normalizedQuery) {
    return 1;
  }

  const label = normalizeSearchValue(target.label);
  const description = normalizeSearchValue(target.description);
  const groupLabel = normalizeSearchValue(target.groupLabel);
  const href = normalizeSearchValue(target.href);
  const keywords = target.keywords.map((keyword) => normalizeSearchValue(keyword));
  const combined = [label, description, groupLabel, href, ...keywords].join(" ");
  const tokens = normalizedQuery.split(/\s+/).filter(Boolean);

  let score = 0;

  if (label === normalizedQuery) {
    score = Math.max(score, 120);
  }
  if (keywords.includes(normalizedQuery)) {
    score = Math.max(score, 110);
  }
  if (label.startsWith(normalizedQuery)) {
    score = Math.max(score, 100);
  }
  if (keywords.some((keyword) => keyword.startsWith(normalizedQuery))) {
    score = Math.max(score, 92);
  }
  if (label.includes(normalizedQuery)) {
    score = Math.max(score, 84);
  }
  if (keywords.some((keyword) => keyword.includes(normalizedQuery))) {
    score = Math.max(score, 72);
  }
  if (
    description.includes(normalizedQuery) ||
    groupLabel.includes(normalizedQuery) ||
    href.includes(normalizedQuery)
  ) {
    score = Math.max(score, 64);
  }
  if (tokens.length > 1 && tokens.every((token) => combined.includes(token))) {
    score = Math.max(score, 58);
  }

  return score;
}

function NavigationColumn({
  activePath,
  onNavigate,
}: {
  activePath: string;
  onNavigate?: () => void;
}) {
  return (
    <div className="space-y-6">
      {NAV_GROUPS.map((group) => (
        <div key={group.label} className="space-y-2.5">
          <p className="eyebrow px-2">{group.label}</p>
          <div className="space-y-1">
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = isActivePath(activePath, item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onNavigate}
                  className={cn(
                    "flex items-center justify-between rounded-[1.15rem] px-3 py-2.5 text-[13px] font-medium transition-all",
                    active
                      ? "bg-[color:var(--primary)] text-[color:var(--primary-foreground)] shadow-[0_14px_30px_rgba(29,27,25,0.16)]"
                      : "hover:text-foreground text-[color:var(--foreground-soft)] hover:bg-white/72",
                  )}
                >
                  <span className="flex items-center gap-3">
                    <span
                      className={cn(
                        "flex size-8 items-center justify-center rounded-full border",
                        active
                          ? "border-white/12 bg-white/10"
                          : "border-[rgba(23,22,19,0.06)] bg-white/74",
                      )}
                    >
                      <Icon className="size-4" />
                    </span>
                    <span>{item.label}</span>
                  </span>
                  {active ? (
                    <span className="size-2 rounded-full bg-[color:var(--accent)]" />
                  ) : null}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function SidebarContent({
  activePath,
  onNavigate,
}: {
  activePath: string;
  onNavigate?: () => void;
}) {
  return (
    <>
      <div className="rounded-[1.7rem] border border-white/55 bg-white/46 px-3.5 py-3.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.78)]">
        <div className="flex items-center gap-3">
          <div className="flex size-12 items-center justify-center overflow-hidden rounded-[1.1rem] bg-[linear-gradient(135deg,var(--accent-soft),white)] shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={DEFAULT_BRAND_LOGO_PATH}
              alt="Veni AI brand logo"
              data-testid="app-shell-brand-logo"
              className="size-10 object-contain"
            />
          </div>
          <div>
            <p className="text-foreground text-[18px] font-semibold tracking-[-0.04em]">Veni AI</p>
            <p className="text-[12px] text-[color:var(--foreground-muted)]">
              Sustainability cockpit
            </p>
          </div>
        </div>
      </div>

      <div className="mt-8 flex-1">
        <NavigationColumn activePath={activePath} onNavigate={onNavigate} />
      </div>

      <div className="space-y-3">
        <div className="rounded-[1.8rem] bg-[linear-gradient(160deg,#201d1b_0%,#2d6d53_100%)] px-4 py-4 text-white shadow-[0_20px_48px_rgba(24,44,33,0.22)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[11px] tracking-[0.18em] text-white/72 uppercase">Factory pulse</p>
              <p className="mt-2 text-[22px] font-semibold tracking-[-0.05em]">
                Controlled publish
              </p>
            </div>
            <span className="rounded-full border border-white/14 bg-white/8 px-2.5 py-1 text-[10px] font-semibold tracking-[0.12em] text-white/82 uppercase">
              Live
            </span>
          </div>
          <p className="mt-2 text-[12px] leading-5 text-white/76">
            Connector freshness, verification discipline, and artifact completeness stay in one
            quiet surface.
          </p>
          <div className="mt-4 grid gap-2">
            {["Sync", "Generate", "Review", "Package", "Publish"].map((label, index) => (
              <div
                key={label}
                className="flex items-center justify-between rounded-[1rem] border border-white/10 bg-white/8 px-3 py-2"
              >
                <span className="text-[11px] font-medium text-white/82">{label}</span>
                <span className="flex items-center gap-1 text-[10px] tracking-[0.12em] text-white/66 uppercase">
                  <CircleDot
                    className={cn("size-3", index >= 3 ? "text-white/50" : "text-[#9fe0b9]")}
                  />
                  stage
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-[1.5rem] border border-[rgba(23,22,19,0.06)] bg-white/74 px-3.5 py-3">
          <p className="text-[11px] font-semibold tracking-[0.16em] text-[color:var(--foreground-muted)] uppercase">
            Trust mode
          </p>
          <div className="mt-2 grid gap-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-foreground text-[13px] font-medium">Verified facts only</span>
              <span className="pill-surface">Fail closed</span>
            </div>
            <p className="text-[11px] leading-5 text-[color:var(--foreground-soft)]">
              Claims, calculations, and package artifacts stay bound to evidence before release.
            </p>
          </div>
        </div>

        <div className="px-1 text-[10px] leading-4 text-[color:var(--foreground-muted)]">
          <p>
            {
              "Bu proje Ali \u00d6zkan \u00d6zdurmu\u015f taraf\u0131ndan haz\u0131rlanm\u0131\u015ft\u0131r."
            }
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
            <a
              href="https://github.com/aliozkanozdurmus"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-[color:var(--accent-strong)] transition hover:text-[color:var(--accent)]"
            >
              GitHub
            </a>
            <span aria-hidden="true" className="text-[color:var(--border-strong)]">
              •
            </span>
            <a
              href="https://www.linkedin.com/in/aliozkanozdurmus/"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-[color:var(--accent-strong)] transition hover:text-[color:var(--accent)]"
            >
              LinkedIn
            </a>
          </div>
        </div>
      </div>
    </>
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
  const router = useRouter();
  const workspace = useWorkspaceContext();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [seenNotificationsVersion, setSeenNotificationsVersion] = useState(0);
  const searchContainerRef = useRef<HTMLDivElement | null>(null);
  const notificationContainerRef = useRef<HTMLDivElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const deferredSearchQuery = useDeferredValue(searchQuery);
  const {
    data: notificationsData,
    error: notificationsError,
    isLoading: notificationsLoading,
    isFetching: notificationsFetching,
    refetch: refetchNotifications,
  } = useDashboardNotificationsQuery(workspace);

  const breadcrumbs = useMemo(
    () => breadcrumbsFromPath(pathname || activePath),
    [activePath, pathname],
  );
  const normalizedSearchQuery = normalizeSearchValue(deferredSearchQuery);
  const notificationItems = useMemo(() => notificationsData?.items ?? [], [notificationsData]);
  const notificationIds = useMemo(
    () => notificationItems.map((item) => item.notification_id),
    [notificationItems],
  );
  const notificationStorageKey = useMemo(
    () => (workspace ? buildNotificationSessionStorageKey(workspace) : null),
    [workspace],
  );
  const seenNotificationIds = useMemo(() => {
    void seenNotificationsVersion;

    if (!notificationStorageKey || typeof window === "undefined") {
      return [];
    }

    return readSeenNotificationIds(window.sessionStorage, notificationStorageKey);
  }, [notificationStorageKey, seenNotificationsVersion]);
  const unreadNotificationCount = useMemo(
    () => countUnreadNotifications(notificationItems, seenNotificationIds),
    [notificationItems, seenNotificationIds],
  );
  const unreadNotificationBadge = useMemo(
    () => formatUnreadBadgeCount(unreadNotificationCount),
    [unreadNotificationCount],
  );
  const searchResults = useMemo(() => {
    return SEARCH_TARGETS.map((target) => ({
      target,
      score: scoreSearchTarget(target, normalizedSearchQuery),
    }))
      .filter((entry) => entry.score > 0)
      .sort(
        (left, right) =>
          right.score - left.score || left.target.label.localeCompare(right.target.label),
      )
      .slice(0, 5)
      .map((entry) => entry.target);
  }, [normalizedSearchQuery]);

  function navigateToSearchTarget(target: SearchTarget) {
    setSearchOpen(false);
    setNotificationOpen(false);
    setSearchQuery("");
    startTransition(() => {
      router.push(target.href);
    });
  }

  function handleNotificationToggle() {
    setSearchOpen(false);

    const nextOpen = !notificationOpen;
    if (
      nextOpen &&
      notificationStorageKey &&
      typeof window !== "undefined" &&
      notificationIds.length > 0
    ) {
      markNotificationsSeen(window.sessionStorage, notificationStorageKey, notificationIds);
      setSeenNotificationsVersion((current) => current + 1);
    }

    setNotificationOpen(nextOpen);
  }

  useEffect(() => {
    if (!notificationOpen || !workspace) {
      return;
    }

    void refetchNotifications();
  }, [notificationOpen, refetchNotifications, workspace]);

  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      if (
        searchContainerRef.current &&
        event.target instanceof Node &&
        !searchContainerRef.current.contains(event.target)
      ) {
        setSearchOpen(false);
      }
      if (
        notificationContainerRef.current &&
        event.target instanceof Node &&
        !notificationContainerRef.current.contains(event.target)
      ) {
        setNotificationOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === "f") {
        event.preventDefault();
        setNotificationOpen(false);
        setSearchOpen(true);
        searchInputRef.current?.focus();
        searchInputRef.current?.select();
        return;
      }

      if (event.key === "Escape") {
        setSearchOpen(false);
        setNotificationOpen(false);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  return (
    <div className="bg-canvas min-h-screen px-3 py-4 md:px-5 md:py-6">
      <div className="workbench-shell mx-auto max-w-[1540px] p-3 md:p-4">
        <div className="grid gap-3 xl:grid-cols-[232px_minmax(0,1fr)]">
          <aside className="rail-surface hidden min-h-[calc(100vh-4rem)] flex-col p-4 xl:flex">
            <SidebarContent activePath={activePath} />
          </aside>

          <section className="content-surface min-h-[calc(100vh-4rem)] p-3 md:p-4">
            <div className="rounded-[1.75rem] border border-white/70 bg-white/52 px-3 py-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.84)]">
              <div className="flex items-center gap-3">
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

                <div ref={searchContainerRef} className="relative flex-1">
                  <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-[color:var(--foreground-muted)]" />
                  <input
                    ref={searchInputRef}
                    type="search"
                    placeholder="Search runs, artifacts, connectors"
                    value={searchQuery}
                    data-testid="global-search-input"
                    autoComplete="off"
                    spellCheck={false}
                    className="search-field"
                    aria-label="Global search"
                    onFocus={() => setSearchOpen(true)}
                    onChange={(event) => {
                      setSearchQuery(event.target.value);
                      setSearchOpen(true);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && searchResults.length > 0) {
                        event.preventDefault();
                        navigateToSearchTarget(searchResults[0]);
                      }
                    }}
                  />
                  <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 rounded-full border border-[rgba(23,22,19,0.06)] bg-[color:var(--surface)] px-2 py-1 text-[10px] font-semibold text-[color:var(--foreground-muted)]">
                    <Command className="mr-1 inline size-3" />F
                  </span>

                  {searchOpen ? (
                    <div
                      id="global-search-results"
                      data-testid="global-search-results"
                      className="absolute inset-x-0 top-[calc(100%+0.55rem)] z-30 rounded-[1.5rem] border border-[rgba(23,22,19,0.08)] bg-white/96 p-2 shadow-[0_18px_48px_rgba(32,29,23,0.12)] backdrop-blur-md"
                    >
                      {searchResults.length > 0 ? (
                        <div className="space-y-1">
                          {searchResults.map((target, index) => {
                            const Icon = target.icon;
                            const current = isActivePath(pathname || activePath, target.href);
                            return (
                              <button
                                key={target.href}
                                type="button"
                                data-testid={target.testId}
                                className="flex w-full items-start gap-3 rounded-[1.15rem] px-3 py-2.5 text-left transition hover:bg-[color:var(--surface)]"
                                onClick={() => navigateToSearchTarget(target)}
                              >
                                <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full border border-[rgba(23,22,19,0.06)] bg-[color:var(--surface)] text-[color:var(--accent-strong)]">
                                  <Icon className="size-4" />
                                </span>
                                <span className="min-w-0 flex-1">
                                  <span className="flex items-center gap-2">
                                    <span className="text-foreground text-[13px] font-semibold">
                                      {target.label}
                                    </span>
                                    {current ? <span className="pill-surface">Current</span> : null}
                                    {index === 0 ? <span className="pill-dark">Enter</span> : null}
                                  </span>
                                  <span className="mt-1 block text-[12px] leading-5 text-[color:var(--foreground-soft)]">
                                    {target.description}
                                  </span>
                                  <span className="mt-1.5 block text-[10px] font-semibold tracking-[0.12em] text-[color:var(--foreground-muted)] uppercase">
                                    {target.groupLabel}
                                  </span>
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="rounded-[1.15rem] bg-[color:var(--surface)] px-3 py-3 text-[12px] text-[color:var(--foreground-soft)]">
                          No matching surface for{" "}
                          <span className="font-semibold">{searchQuery.trim()}</span>.
                        </div>
                      )}
                    </div>
                  ) : null}
                </div>

                <div ref={notificationContainerRef} className="relative">
                  <Button
                    type="button"
                    variant="outline"
                    size="icon-sm"
                    aria-label="Notifications"
                    aria-expanded={notificationOpen}
                    aria-controls="notification-center-panel"
                    data-testid="notification-bell-button"
                    className="relative"
                    onClick={handleNotificationToggle}
                  >
                    <Bell className="size-4" />
                    {unreadNotificationCount > 0 ? (
                      <span
                        data-testid="notification-badge"
                        className="absolute -top-1.5 -right-1.5 inline-flex min-w-5 items-center justify-center rounded-full bg-[color:var(--accent-strong)] px-1.5 py-0.5 text-[9px] leading-none font-semibold text-white"
                      >
                        {unreadNotificationBadge}
                      </span>
                    ) : null}
                  </Button>

                  {notificationOpen ? (
                    <div
                      id="notification-center-panel"
                      className="absolute top-[calc(100%+0.55rem)] right-0 z-30"
                    >
                      <NotificationCenterPanel
                        workspaceReady={Boolean(workspace)}
                        notifications={notificationItems}
                        isLoading={notificationsLoading || notificationsFetching}
                        errorMessage={
                          notificationsError instanceof Error ? notificationsError.message : null
                        }
                      />
                    </div>
                  ) : null}
                </div>

                <div className="hidden items-center gap-3 rounded-full border border-[rgba(23,22,19,0.06)] bg-white/86 px-2 py-1.5 shadow-[0_10px_24px_rgba(31,29,26,0.05)] md:flex">
                  <div className="flex size-9 items-center justify-center rounded-full bg-[linear-gradient(135deg,#efe8db,#d7e8dc)] text-[13px] font-semibold text-[color:var(--accent-strong)]">
                    A
                  </div>
                  <div className="pr-2">
                    <p className="text-foreground text-[12px] font-semibold">Admin Operator</p>
                    <p className="text-[11px] text-[color:var(--foreground-muted)]">
                      ali.ozdurmus1@gmail.com
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {mobileOpen ? (
              <div className="fixed inset-0 z-50 bg-[rgba(20,19,18,0.22)] backdrop-blur-sm xl:hidden">
                <div className="rail-surface ml-auto h-full w-[18.5rem] rounded-none rounded-l-[2rem] p-4 shadow-[0_30px_80px_rgba(25,24,22,0.28)]">
                  <div className="flex items-center justify-between">
                    <p className="text-foreground text-[16px] font-semibold">Navigation</p>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon-sm"
                      onClick={() => setMobileOpen(false)}
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                  <div className="mt-5 flex h-[calc(100%-3rem)] flex-col">
                    <SidebarContent
                      activePath={activePath}
                      onNavigate={() => setMobileOpen(false)}
                    />
                  </div>
                </div>
              </div>
            ) : null}

            <div className="mt-4 overflow-hidden rounded-[1.95rem] border border-[rgba(23,22,19,0.06)] bg-white/76 shadow-[0_14px_36px_rgba(41,38,31,0.05)]">
              <div className="grid gap-0 xl:grid-cols-[1fr_auto]">
                <div className="px-4 py-4 md:px-5">
                  <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2 text-[11px] text-[color:var(--foreground-muted)]">
                        <span className="pill-dark">Control room</span>
                        {breadcrumbs.map((crumb, index) => (
                          <span
                            key={`${crumb}-${index}`}
                            className="inline-flex items-center gap-2"
                          >
                            {index === 0 ? null : <span>/</span>}
                            <span>{crumb}</span>
                          </span>
                        ))}
                      </div>
                      <div>
                        <h1 className="text-foreground text-[30px] font-semibold tracking-[-0.06em] md:text-[36px]">
                          {title}
                        </h1>
                        <p className="mt-2 max-w-3xl text-[13px] leading-6 text-[color:var(--foreground-soft)]">
                          {subtitle}
                        </p>
                      </div>
                    </div>

                    {actions.length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {actions.map((action, index) => (
                          <Button
                            key={action.href}
                            asChild
                            variant={index === 0 ? "default" : "outline"}
                          >
                            <Link href={action.href}>{action.label}</Link>
                          </Button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
                <div className="hidden min-w-[16rem] border-l border-[rgba(23,22,19,0.06)] bg-[linear-gradient(180deg,#f5efe5_0%,#f9f5ee_100%)] px-5 py-4 xl:block">
                  <p className="eyebrow">Working model</p>
                  <div className="mt-3 space-y-2.5">
                    <div className="rounded-[1.1rem] border border-white/80 bg-white/74 px-3 py-2.5">
                      <p className="text-[11px] font-semibold tracking-[0.12em] text-[color:var(--foreground-muted)] uppercase">
                        Signal
                      </p>
                      <p className="text-foreground mt-1 text-[14px] font-semibold">
                        Verified ESG operations
                      </p>
                    </div>
                    <div className="rounded-[1.1rem] border border-white/80 bg-white/74 px-3 py-2.5">
                      <p className="text-[11px] font-semibold tracking-[0.12em] text-[color:var(--foreground-muted)] uppercase">
                        Delivery
                      </p>
                      <p className="text-foreground mt-1 text-[14px] font-semibold">
                        Queued package pipeline
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-4 space-y-4">{children}</div>
          </section>
        </div>
      </div>
    </div>
  );
}
