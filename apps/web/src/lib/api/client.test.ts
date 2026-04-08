// Bu test dosyasi, client davranisini dogrular.

import { afterEach, describe, expect, it, vi } from "vitest";

type MockWindow = {
  dispatchEvent: ReturnType<typeof vi.fn>;
  localStorage: {
    getItem: ReturnType<typeof vi.fn>;
    setItem: ReturnType<typeof vi.fn>;
    removeItem: ReturnType<typeof vi.fn>;
  };
  location: {
    protocol: string;
    hostname: string;
  };
};

function createMockWindow(seed: Record<string, string> = {}): MockWindow {
  const store = new Map(Object.entries(seed));

  return {
    dispatchEvent: vi.fn(),
    localStorage: {
      getItem: vi.fn((key: string) => store.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => {
        store.set(key, value);
      }),
      removeItem: vi.fn((key: string) => {
        store.delete(key);
      }),
    },
    location: {
      protocol: "http:",
      hostname: "127.0.0.1",
    },
  };
}

async function loadClientModule() {
  vi.resetModules();
  return import("./client");
}

describe("client api helpers", () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    delete process.env.NEXT_PUBLIC_DEFAULT_TENANT_ID;
    delete process.env.NEXT_PUBLIC_DEFAULT_PROJECT_ID;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("prefers explicit NEXT_PUBLIC_API_BASE_URL", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.example.test";

    const { getApiBaseUrl } = await loadClientModule();

    expect(getApiBaseUrl()).toBe("http://api.example.test");
  });

  it("derives the fallback origin from the current browser hostname", async () => {
    const mockWindow = createMockWindow();
    mockWindow.location.protocol = "https:";
    mockWindow.location.hostname = "workspace.example.test";
    vi.stubGlobal("window", mockWindow);

    const { getApiBaseUrl } = await loadClientModule();

    expect(getApiBaseUrl()).toBe("https://workspace.example.test:8000");
  });

  it("falls back to loopback in non-browser contexts", async () => {
    const { getApiBaseUrl } = await loadClientModule();

    expect(getApiBaseUrl()).toBe("http://127.0.0.1:8000");
  });

  it("returns the validated workspace fallback pair from env", async () => {
    process.env.NEXT_PUBLIC_DEFAULT_TENANT_ID = "tenant-demo";
    process.env.NEXT_PUBLIC_DEFAULT_PROJECT_ID = "project-demo";

    const { getEnvWorkspaceFallback, getInitialWorkspaceContext } = await loadClientModule();

    expect(getEnvWorkspaceFallback()).toEqual({
      tenantId: "tenant-demo",
      projectId: "project-demo",
    });
    expect(getInitialWorkspaceContext()).toEqual({
      tenantId: "tenant-demo",
      projectId: "project-demo",
    });
  });

  it("ignores invalid localStorage payloads", async () => {
    const mockWindow = createMockWindow();
    vi.stubGlobal("window", mockWindow);

    const { WORKSPACE_STORAGE_KEY, readWorkspaceContext } = await loadClientModule();
    mockWindow.localStorage.setItem(WORKSPACE_STORAGE_KEY, "{not-json");

    expect(readWorkspaceContext()).toBeNull();
  });

  it("validates and persists workspace context before writing", async () => {
    const mockWindow = createMockWindow();
    vi.stubGlobal("window", mockWindow);

    const { WORKSPACE_STORAGE_KEY, persistWorkspaceContext, readWorkspaceContext } =
      await loadClientModule();

    persistWorkspaceContext({
      tenantId: "tenant-1",
      projectId: "project-1",
    });

    expect(mockWindow.localStorage.setItem).toHaveBeenCalledWith(
      WORKSPACE_STORAGE_KEY,
      JSON.stringify({
        tenantId: "tenant-1",
        projectId: "project-1",
      }),
    );
    expect(readWorkspaceContext()).toEqual({
      tenantId: "tenant-1",
      projectId: "project-1",
    });
    expect(mockWindow.dispatchEvent).toHaveBeenCalledTimes(1);
  });
});
