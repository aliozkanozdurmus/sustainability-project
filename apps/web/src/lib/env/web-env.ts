import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

const optionalClientString = z.string().trim().min(1).optional();

const workspaceFallbackPairSchema = z
  .object({
    NEXT_PUBLIC_DEFAULT_TENANT_ID: optionalClientString,
    NEXT_PUBLIC_DEFAULT_PROJECT_ID: optionalClientString,
  })
  .superRefine((value, context) => {
    const hasTenant = Boolean(value.NEXT_PUBLIC_DEFAULT_TENANT_ID);
    const hasProject = Boolean(value.NEXT_PUBLIC_DEFAULT_PROJECT_ID);

    if (hasTenant === hasProject) {
      return;
    }

    context.addIssue({
      code: z.ZodIssueCode.custom,
      message:
        "NEXT_PUBLIC_DEFAULT_TENANT_ID and NEXT_PUBLIC_DEFAULT_PROJECT_ID must be provided together.",
      path: hasTenant
        ? ["NEXT_PUBLIC_DEFAULT_PROJECT_ID"]
        : ["NEXT_PUBLIC_DEFAULT_TENANT_ID"],
    });
  });

export type WebEnv = {
  NEXT_PUBLIC_API_BASE_URL?: string;
  NEXT_PUBLIC_APP_BASE_URL?: string;
  NEXT_PUBLIC_DEFAULT_TENANT_ID?: string;
  NEXT_PUBLIC_DEFAULT_PROJECT_ID?: string;
};

export function parseWebEnv(runtimeEnv: Record<string, string | undefined> = process.env): WebEnv {
  const env = createEnv({
    server: {},
    client: {
      NEXT_PUBLIC_API_BASE_URL: z.string().url().optional(),
      NEXT_PUBLIC_APP_BASE_URL: z.string().url().optional(),
      NEXT_PUBLIC_DEFAULT_TENANT_ID: optionalClientString,
      NEXT_PUBLIC_DEFAULT_PROJECT_ID: optionalClientString,
    },
    runtimeEnv: {
      NEXT_PUBLIC_API_BASE_URL: runtimeEnv.NEXT_PUBLIC_API_BASE_URL,
      NEXT_PUBLIC_APP_BASE_URL: runtimeEnv.NEXT_PUBLIC_APP_BASE_URL,
      NEXT_PUBLIC_DEFAULT_TENANT_ID: runtimeEnv.NEXT_PUBLIC_DEFAULT_TENANT_ID,
      NEXT_PUBLIC_DEFAULT_PROJECT_ID: runtimeEnv.NEXT_PUBLIC_DEFAULT_PROJECT_ID,
    },
    emptyStringAsUndefined: true,
  });

  workspaceFallbackPairSchema.parse({
    NEXT_PUBLIC_DEFAULT_TENANT_ID: env.NEXT_PUBLIC_DEFAULT_TENANT_ID,
    NEXT_PUBLIC_DEFAULT_PROJECT_ID: env.NEXT_PUBLIC_DEFAULT_PROJECT_ID,
  });

  return env;
}

export const webEnv = parseWebEnv();
