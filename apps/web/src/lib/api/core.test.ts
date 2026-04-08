import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { getResponseErrorMessage } from "./client";
import { downloadBlob, parseOpenApiResult } from "./core";

function jsonResponse(payload: unknown, status = 200, headers?: HeadersInit) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json",
      ...headers,
    },
  });
}

describe("api core helpers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("normalizes string detail errors", async () => {
    const response = jsonResponse({ detail: "Publish blocked." }, 409);

    await expect(getResponseErrorMessage(response)).resolves.toBe("Publish blocked.");
  });

  it("normalizes object detail errors into pretty JSON", async () => {
    const response = jsonResponse(
      { detail: { code: "WORKFLOW_NOT_PUBLISH_READY", message: "Verifier failed." } },
      409,
    );

    await expect(getResponseErrorMessage(response)).resolves.toBe(
      JSON.stringify(
        {
          code: "WORKFLOW_NOT_PUBLISH_READY",
          message: "Verifier failed.",
        },
        null,
        2,
      ),
    );
  });

  it("parses successful openapi results with a zod schema", async () => {
    await expect(
      parseOpenApiResult(
        {
          data: {
            ok: true,
          },
          response: jsonResponse({ ok: true }),
        },
        z.object({
          ok: z.boolean(),
        }),
      ),
    ).resolves.toEqual({ ok: true });
  });

  it("prefers the parsed openapi error payload when an openapi result fails", async () => {
    await expect(
      parseOpenApiResult(
        {
          error: {
            detail: "Verifier failed.",
          },
          response: jsonResponse({ detail: "Ignored because payload is already parsed." }, 422),
        },
        z.object({
          ok: z.boolean(),
        }),
      ),
    ).rejects.toThrow("Verifier failed.");
  });

  it("prefers the parsed openapi error payload when the response body is already consumed", async () => {
    const response = jsonResponse({ detail: "Publish blocked." }, 409);
    await response.text();

    await expect(
      parseOpenApiResult(
        {
          error: {
            detail: "Publish blocked.",
          },
          response,
        },
        z.object({
          ok: z.boolean(),
        }),
      ),
    ).rejects.toThrow("Publish blocked.");
  });

  it("downloads blobs and extracts the suggested filename", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Blob(["pdf-bytes"]), {
        status: 200,
        headers: {
          "content-disposition": 'attachment; filename="report-1.pdf"',
          "content-type": "application/pdf",
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      downloadBlob("/runs/run-1/report-pdf", {
        tenantId: "tenant-1",
      }),
    ).resolves.toMatchObject({
      filename: "report-1.pdf",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
