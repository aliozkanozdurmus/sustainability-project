import { describe, expect, it, vi } from "vitest";

import { parseWebEnv } from "./web-env";

describe("parseWebEnv", () => {
  it("accepts optional public env values when the workspace fallback pair is complete", () => {
    expect(
      parseWebEnv({
        NEXT_PUBLIC_API_BASE_URL: "https://api.example.test",
        NEXT_PUBLIC_DEFAULT_TENANT_ID: "tenant-demo",
        NEXT_PUBLIC_DEFAULT_PROJECT_ID: "project-demo",
      }),
    ).toMatchObject({
      NEXT_PUBLIC_API_BASE_URL: "https://api.example.test",
      NEXT_PUBLIC_DEFAULT_TENANT_ID: "tenant-demo",
      NEXT_PUBLIC_DEFAULT_PROJECT_ID: "project-demo",
    });
  });

  it("rejects partial tenant/project fallback configuration", () => {
    expect(() =>
      parseWebEnv({
        NEXT_PUBLIC_DEFAULT_TENANT_ID: "tenant-only",
      }),
    ).toThrow(/must be provided together/i);
  });

  it("rejects invalid public api base urls", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    expect(() =>
      parseWebEnv({
        NEXT_PUBLIC_API_BASE_URL: "not-a-url",
      }),
    ).toThrow();
  });
});
