import { afterEach, describe, expect, it, vi } from "vitest";

import { getApiBaseUrl } from "./client";


describe("getApiBaseUrl", () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    vi.unstubAllGlobals();
  });

  it("prefers explicit NEXT_PUBLIC_API_BASE_URL", () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.example.test";

    expect(getApiBaseUrl()).toBe("http://api.example.test");
  });

  it("derives the fallback origin from the current browser hostname", () => {
    vi.stubGlobal("window", {
      location: {
        protocol: "http:",
        hostname: "127.0.0.1",
      },
    });

    expect(getApiBaseUrl()).toBe("http://127.0.0.1:8000");
  });

  it("falls back to loopback in non-browser contexts", () => {
    expect(getApiBaseUrl()).toBe("http://127.0.0.1:8000");
  });
});
