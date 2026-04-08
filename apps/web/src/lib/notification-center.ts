import type { WorkspaceContext } from "@/lib/api/client";
import type { DashboardNotificationItem } from "@/lib/api/dashboard";

export const NOTIFICATION_SESSION_STORAGE_PREFIX = "veni_notification_center_seen_v1";

export type SessionStorageLike = Pick<Storage, "getItem" | "setItem">;

export function buildNotificationSessionStorageKey(workspace: WorkspaceContext): string {
  return `${NOTIFICATION_SESSION_STORAGE_PREFIX}:${workspace.tenantId}:${workspace.projectId}`;
}

export function readSeenNotificationIds(storage: SessionStorageLike, storageKey: string): string[] {
  try {
    const raw = storage.getItem(storageKey);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((value): value is string => typeof value === "string");
  } catch {
    return [];
  }
}

export function writeSeenNotificationIds(
  storage: SessionStorageLike,
  storageKey: string,
  ids: string[],
): string[] {
  const normalized = Array.from(new Set(ids.filter(Boolean)));
  try {
    storage.setItem(storageKey, JSON.stringify(normalized));
  } catch {
    return normalized;
  }
  return normalized;
}

export function markNotificationsSeen(
  storage: SessionStorageLike,
  storageKey: string,
  notificationIds: string[],
): string[] {
  const existing = readSeenNotificationIds(storage, storageKey);
  return writeSeenNotificationIds(storage, storageKey, [...existing, ...notificationIds]);
}

export function countUnreadNotifications(
  items: DashboardNotificationItem[],
  seenNotificationIds: Iterable<string>,
): number {
  const seen = new Set(seenNotificationIds);
  return items.reduce((count, item) => count + (seen.has(item.notification_id) ? 0 : 1), 0);
}

export function formatUnreadBadgeCount(count: number): string {
  if (count <= 0) {
    return "0";
  }
  return count > 9 ? "9+" : String(count);
}
