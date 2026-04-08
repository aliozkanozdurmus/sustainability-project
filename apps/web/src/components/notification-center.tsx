"use client";

import { Bell, Loader2 } from "lucide-react";

import type { DashboardNotificationItem } from "@/lib/api/dashboard";
import { cn } from "@/lib/utils";

const CATEGORY_LABELS: Record<DashboardNotificationItem["category"], string> = {
  connector_sync: "Connector sync",
  report_run: "Report run",
  document_upload: "Upload",
  document_extraction: "Extraction",
  document_indexing: "Indexing",
  verification: "Verification",
  publish: "Publish",
  system: "System",
};

const TONE_DOT_CLASS: Record<DashboardNotificationItem["status"], string> = {
  good: "bg-[color:var(--success)]",
  attention: "bg-[color:var(--warning)]",
  critical: "bg-[color:var(--destructive)]",
  neutral: "bg-[color:var(--foreground-muted)]",
};

function formatNotificationTime(value: string | null | undefined): string {
  if (!value) {
    return "Pending";
  }

  return new Date(value).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function NotificationCenterPanel({
  workspaceReady,
  notifications,
  isLoading = false,
  errorMessage = null,
}: {
  workspaceReady: boolean;
  notifications: DashboardNotificationItem[];
  isLoading?: boolean;
  errorMessage?: string | null;
}) {
  return (
    <div
      data-testid="notification-center-panel"
      className="w-[min(24rem,calc(100vw-2rem))] rounded-[1.65rem] border border-[rgba(23,22,19,0.08)] bg-white/96 p-2.5 shadow-[0_22px_54px_rgba(32,29,23,0.14)] backdrop-blur-md"
    >
      <div className="flex items-center justify-between gap-3 px-2 py-1">
        <div>
          <p className="text-[12px] font-semibold tracking-[0.14em] text-[color:var(--foreground-muted)] uppercase">
            Notification center
          </p>
          <p className="text-foreground mt-1 text-[15px] font-semibold tracking-[-0.03em]">
            Operational activity
          </p>
        </div>
        <span className="rounded-full border border-[rgba(23,22,19,0.06)] bg-[color:var(--surface)] px-2.5 py-1 text-[10px] font-semibold tracking-[0.12em] text-[color:var(--foreground-muted)] uppercase">
          {notifications.length} items
        </span>
      </div>

      <div className="soft-divider my-2" />

      {!workspaceReady ? (
        <div className="rounded-[1.25rem] bg-[color:var(--surface)] px-4 py-5 text-center">
          <Bell className="mx-auto size-5 text-[color:var(--foreground-muted)]" />
          <p className="text-foreground mt-2 text-[13px] font-semibold">Workspace required</p>
          <p className="mt-1 text-[12px] leading-5 text-[color:var(--foreground-soft)]">
            Select or bootstrap a workspace before loading notifications.
          </p>
        </div>
      ) : errorMessage ? (
        <div className="rounded-[1.25rem] border border-[rgba(191,101,90,0.14)] bg-[rgba(191,101,90,0.08)] px-4 py-4">
          <p className="text-[13px] font-semibold text-[color:var(--destructive)]">
            Notification feed unavailable
          </p>
          <p className="mt-1 text-[12px] leading-5 text-[color:var(--foreground-soft)]">
            {errorMessage}
          </p>
        </div>
      ) : isLoading && notifications.length === 0 ? (
        <div className="flex items-center justify-center gap-2 rounded-[1.25rem] bg-[color:var(--surface)] px-4 py-5 text-[12px] text-[color:var(--foreground-soft)]">
          <Loader2 className="size-4 animate-spin" />
          Loading operational activity...
        </div>
      ) : notifications.length === 0 ? (
        <div className="rounded-[1.25rem] bg-[color:var(--surface)] px-4 py-5 text-center">
          <Bell className="mx-auto size-5 text-[color:var(--foreground-muted)]" />
          <p className="text-foreground mt-2 text-[13px] font-semibold">No notifications yet</p>
          <p className="mt-1 text-[12px] leading-5 text-[color:var(--foreground-soft)]">
            New sync, verification, and publish events will appear here.
          </p>
        </div>
      ) : (
        <div className="soft-scrollbar max-h-[24rem] space-y-2 overflow-y-auto px-1 py-1">
          {notifications.map((item) => (
            <div
              key={item.notification_id}
              data-testid={`notification-item-${item.notification_id}`}
              className="rounded-[1.2rem] border border-[rgba(23,22,19,0.06)] bg-[linear-gradient(180deg,#fbf8f1_0%,#ffffff_100%)] px-3.5 py-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={cn("size-2 rounded-full", TONE_DOT_CLASS[item.status])} />
                    <span className="text-[10px] font-semibold tracking-[0.12em] text-[color:var(--foreground-muted)] uppercase">
                      {CATEGORY_LABELS[item.category]}
                    </span>
                  </div>
                  <p className="text-foreground mt-2 text-[13px] font-semibold">{item.title}</p>
                  <p className="mt-1 text-[12px] leading-5 text-[color:var(--foreground-soft)]">
                    {item.detail}
                  </p>
                </div>
                <span className="shrink-0 text-[10px] font-medium text-[color:var(--foreground-muted)]">
                  {formatNotificationTime(item.occurred_at_utc)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
