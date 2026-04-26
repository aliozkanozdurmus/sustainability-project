import { describe, expect, it } from "vitest";

import {
  buildNotificationSessionStorageKey,
  countUnreadNotifications,
  formatUnreadBadgeCount,
  markNotificationsSeen,
  readSeenNotificationIds,
} from "./notification-center";

function createMemoryStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));

  return {
    getItem(key: string) {
      return values.get(key) ?? null;
    },
    setItem(key: string, value: string) {
      values.set(key, value);
    },
  };
}

describe("notification center session helpers", () => {
  it("builds a workspace-scoped session key", () => {
    expect(
      buildNotificationSessionStorageKey({
        tenantId: "tenant-1",
        projectId: "project-1",
      }),
    ).toBe("veni_notification_center_seen_v1:tenant-1:project-1");
  });

  it("tracks seen notifications and unread counts per session", () => {
    const storage = createMemoryStorage();
    const storageKey = "notifications:test";
    const notifications = [
      {
        notification_id: "n-1",
        title: "One",
        detail: "First",
        category: "publish",
        status: "good",
        priority: "medium",
        surface: "publish_board",
        action_path: "/approval-center?runId=run-1",
        sort_rank: 20,
        occurred_at_utc: "2026-04-08T10:00:00Z",
        source_ref: null,
      },
      {
        notification_id: "n-2",
        title: "Two",
        detail: "Second",
        category: "verification",
        status: "attention",
        priority: "high",
        surface: "verifier_triage",
        action_path: "/approval-center?runId=run-2",
        sort_rank: 11,
        occurred_at_utc: "2026-04-08T10:01:00Z",
        source_ref: null,
      },
    ] as const;

    expect(countUnreadNotifications([...notifications], [])).toBe(2);

    const seenIds = markNotificationsSeen(storage, storageKey, ["n-1"]);

    expect(seenIds).toEqual(["n-1"]);
    expect(readSeenNotificationIds(storage, storageKey)).toEqual(["n-1"]);
    expect(countUnreadNotifications([...notifications], seenIds)).toBe(1);
    expect(formatUnreadBadgeCount(12)).toBe("9+");
  });
});
