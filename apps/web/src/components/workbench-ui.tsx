"use client";

// Bu bilesen, workbench ui arayuz parcasini kurar.

import type { HTMLAttributes, ReactNode } from "react";
import { AlertTriangle, CheckCircle2, CircleDashed } from "lucide-react";

import { cn } from "@/lib/utils";

type Tone = "good" | "attention" | "critical" | "neutral";

const TONE_STYLES: Record<Tone, string> = {
  good: "border-[rgba(31,122,74,0.12)] bg-[rgba(31,122,74,0.08)] text-[color:var(--success)]",
  attention: "border-[rgba(210,167,66,0.14)] bg-[rgba(210,167,66,0.13)] text-[color:var(--warning)]",
  critical: "border-[rgba(191,101,90,0.14)] bg-[rgba(191,101,90,0.1)] text-[color:var(--destructive)]",
  neutral: "border-[rgba(23,22,19,0.08)] bg-white/72 text-[color:var(--foreground-soft)]",
};

export function SectionHeading({
  eyebrow,
  title,
  description,
  action,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-3", className)}>
      <div className="space-y-1.5">
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <div className="space-y-1">
          <h2 className="text-[19px] font-semibold tracking-[-0.04em] text-foreground">{title}</h2>
          {description ? (
            <p className="max-w-2xl text-[13px] leading-5 text-[color:var(--foreground-soft)]">{description}</p>
          ) : null}
        </div>
      </div>
      {action}
    </div>
  );
}

export function SurfaceCard({
  className,
  children,
  elevated = false,
}: HTMLAttributes<HTMLDivElement> & { elevated?: boolean }) {
  return (
    <div className={cn(elevated ? "panel-surface-elevated" : "panel-surface", className)}>
      {children}
    </div>
  );
}

export function StatusChip({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em]",
        TONE_STYLES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function MetricPill({
  label,
  value,
  detail,
  tone = "neutral",
  className,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-[1.55rem] border border-[color:var(--border)] bg-white/82 px-3.5 py-3.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.84)]",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[color:var(--foreground-muted)]">
            {label}
          </p>
          <p className="mt-2 text-[28px] font-semibold tracking-[-0.06em] text-foreground">{value}</p>
        </div>
        <span
          className={cn(
            "mt-1 size-2.5 rounded-full",
            tone === "good" && "bg-[color:var(--success)]",
            tone === "attention" && "bg-[color:var(--warning)]",
            tone === "critical" && "bg-[color:var(--destructive)]",
            tone === "neutral" && "bg-[color:var(--foreground-muted)]",
          )}
        />
      </div>
      {detail ? <p className="mt-2 text-[12px] leading-5 text-[color:var(--foreground-soft)]">{detail}</p> : null}
    </div>
  );
}

export function StatChip({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="flex items-center gap-2 rounded-full border border-[rgba(23,22,19,0.06)] bg-white/82 px-3 py-2">
      <StatusChip tone={tone} className="shrink-0">
        {label}
      </StatusChip>
      <span className="text-[13px] font-medium text-foreground">{value}</span>
    </div>
  );
}

export function SegmentedBar({
  segments,
  className,
}: {
  segments: Array<{ label: string; value: number; tone?: Tone }>;
  className?: string;
}) {
  const total = segments.reduce((sum, segment) => sum + Math.max(0, segment.value), 0) || 1;
  const activeSegments = segments
    .map((segment) => ({
      ...segment,
      safeValue: Math.max(0, segment.value),
      width: (Math.max(0, segment.value) / total) * 100,
    }))
    .filter((segment) => segment.safeValue > 0);

  return (
    <div className={cn("space-y-2.5", className)}>
      <div className="flex h-10 overflow-hidden rounded-full bg-[color:var(--muted)] p-1">
        {activeSegments.length > 0 ? (
          activeSegments.map((segment) => {
            const showInlineLabel = segment.width >= 18;

            return (
              <div
                key={segment.label}
                className={cn(
                  "flex h-full items-center justify-center overflow-hidden rounded-full text-[11px] font-semibold text-foreground transition-all",
                  showInlineLabel ? "px-2" : "px-0",
                  segment.tone === "good" && "bg-[rgba(31,122,74,0.16)]",
                  segment.tone === "attention" && "bg-[rgba(210,167,66,0.24)]",
                  segment.tone === "critical" && "bg-[rgba(191,101,90,0.18)]",
                  (!segment.tone || segment.tone === "neutral") && "bg-[rgba(23,22,19,0.08)]",
                )}
                style={{ width: `${segment.width}%` }}
                title={`${segment.label}: ${segment.value}%`}
                aria-label={`${segment.label}: ${segment.value}%`}
              >
                {showInlineLabel ? segment.label : null}
              </div>
            );
          })
        ) : (
          <div className="flex h-full w-full items-center justify-center rounded-full bg-[rgba(23,22,19,0.08)] text-[11px] font-medium text-[color:var(--foreground-soft)]">
            No active lanes
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {segments.map((segment) => (
          <div key={`${segment.label}-legend`} className="pill-surface">
            <span className="font-semibold text-foreground">{segment.value}%</span>
            <span className="ml-1">{segment.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ChecklistStack({
  items,
  className,
}: {
  items: Array<{ label: string; detail?: string; done?: boolean; tone?: Tone }>;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2.5", className)}>
      {items.map((item) => (
        <div
          key={item.label}
          className="flex items-start gap-3 rounded-[1.4rem] border border-[color:var(--border)] bg-white/82 px-3.5 py-3"
        >
          <div className="mt-0.5 shrink-0">
            {item.done ? (
              <CheckCircle2 className="size-4 text-[color:var(--success)]" />
            ) : item.tone === "critical" ? (
              <AlertTriangle className="size-4 text-[color:var(--destructive)]" />
            ) : (
              <CircleDashed className="size-4 text-[color:var(--foreground-muted)]" />
            )}
          </div>
          <div>
            <p className="text-[13px] font-medium text-foreground">{item.label}</p>
            {item.detail ? <p className="mt-1 text-[12px] leading-5 text-[color:var(--foreground-soft)]">{item.detail}</p> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

export function TimelineRail({
  items,
  className,
}: {
  items: Array<{ title: string; subtitle: string; detail?: string; tone?: Tone }>;
  className?: string;
}) {
  return (
    <div className={cn("space-y-3", className)}>
      {items.map((item, index) => (
        <div key={`${item.title}-${index}`} className="flex gap-3">
          <div className="flex flex-col items-center">
            <span
              className={cn(
                "mt-1 size-2.5 rounded-full",
                item.tone === "critical" && "bg-[color:var(--destructive)]",
                item.tone === "good" && "bg-[color:var(--success)]",
                item.tone === "attention" && "bg-[color:var(--warning)]",
                (!item.tone || item.tone === "neutral") && "bg-[color:var(--foreground-muted)]",
              )}
            />
            {index < items.length - 1 ? <span className="mt-1 h-full w-px bg-[color:var(--border)]" /> : null}
          </div>
          <div className="pb-3">
            <p className="text-[13px] font-medium text-foreground">{item.title}</p>
            <p className="mt-0.5 text-[12px] leading-5 text-[color:var(--foreground-soft)]">{item.subtitle}</p>
            {item.detail ? <p className="mt-1 text-[11px] text-[color:var(--foreground-muted)]">{item.detail}</p> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

export function SubtleAlert({
  tone = "neutral",
  title,
  children,
  className,
  ...props
}: HTMLAttributes<HTMLDivElement> & {
  tone?: Tone;
  title: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn("rounded-[1.5rem] border px-3.5 py-3 text-[13px]", TONE_STYLES[tone], className)}
      {...props}
    >
      <p className="font-semibold">{title}</p>
      <div className="mt-1 text-[12px] leading-5 opacity-92">{children}</div>
    </div>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-[1.5rem] border border-dashed border-[color:var(--border-strong)] bg-white/62 px-4 py-6 text-center">
      <p className="text-[13px] font-semibold text-foreground">{title}</p>
      <p className="mt-1 text-[12px] leading-5 text-[color:var(--foreground-soft)]">{description}</p>
    </div>
  );
}

export function ShimmerBlock({ className }: { className?: string }) {
  return <div className={cn("shimmer rounded-[1.2rem] bg-white/68", className)} />;
}

export function FormField({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[12px] font-medium text-[color:var(--foreground-soft)]">{label}</span>
        {hint ? <span className="text-[11px] text-[color:var(--foreground-muted)]">{hint}</span> : null}
      </div>
      {children}
    </label>
  );
}

export function fieldClassName(className?: string) {
  return cn(
    "h-11 w-full rounded-[1.1rem] border border-[color:var(--border)] bg-[color:var(--input)] px-3 text-[13px] text-foreground shadow-[inset_0_1px_0_rgba(255,255,255,0.72)] transition-colors outline-none focus:border-[rgba(31,122,74,0.26)] focus:ring-4 focus:ring-ring",
    className,
  );
}
