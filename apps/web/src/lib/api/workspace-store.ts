"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import {
  getEnvWorkspaceFallback,
  readWorkspaceContext,
  WORKSPACE_STORAGE_EVENT,
  WORKSPACE_STORAGE_KEY,
  type WorkspaceContext,
} from "./client";

function fallbackWorkspaceContext(): WorkspaceContext | null {
  const fallback = getEnvWorkspaceFallback();
  if (fallback.tenantId && fallback.projectId) {
    return {
      tenantId: fallback.tenantId,
      projectId: fallback.projectId,
    };
  }
  return null;
}

function getWorkspaceClientSnapshot(): WorkspaceContext | null {
  return readWorkspaceContext() ?? fallbackWorkspaceContext();
}

function getWorkspaceServerSnapshot(): WorkspaceContext | null {
  return fallbackWorkspaceContext();
}

function subscribeWorkspaceContext(callback: () => void): () => void {
  if (typeof window === "undefined") {
    return () => undefined;
  }

  const handleStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === WORKSPACE_STORAGE_KEY) {
      callback();
    }
  };
  const handleLocalUpdate = () => callback();

  window.addEventListener("storage", handleStorage);
  window.addEventListener(WORKSPACE_STORAGE_EVENT, handleLocalUpdate);

  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(WORKSPACE_STORAGE_EVENT, handleLocalUpdate);
  };
}

export function useWorkspaceContext(): WorkspaceContext | null {
  const [hydrated, setHydrated] = useState(false);
  const workspace = useSyncExternalStore(
    subscribeWorkspaceContext,
    getWorkspaceClientSnapshot,
    getWorkspaceServerSnapshot,
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setHydrated(true);
  }, []);

  return hydrated ? workspace : getWorkspaceServerSnapshot();
}
