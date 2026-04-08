import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { loadRootEnv } from "./load-root-env.mjs";

const ROOT_ENV_TEST_KEY = "ROOT_ENV_TEST_VALUE";
const ROOT_ENV_PUBLIC_TEST_KEY = "NEXT_PUBLIC_ROOT_ENV_TEST_VALUE";

describe("loadRootEnv", () => {
  afterEach(() => {
    delete process.env[ROOT_ENV_TEST_KEY];
    delete process.env[ROOT_ENV_PUBLIC_TEST_KEY];
  });

  it("loads variables from the provided repository root", async () => {
    const tempRoot = await mkdtemp(path.join(os.tmpdir(), "web-root-env-"));

    try {
      await writeFile(
        path.join(tempRoot, ".env"),
        `${ROOT_ENV_TEST_KEY}=loaded-from-root\n${ROOT_ENV_PUBLIC_TEST_KEY}=public-from-root\n`,
        "utf-8",
      );

      loadRootEnv({ projectDir: tempRoot, forceReload: true, dev: true });

      expect(process.env[ROOT_ENV_TEST_KEY]).toBe("loaded-from-root");
      expect(process.env[ROOT_ENV_PUBLIC_TEST_KEY]).toBe("public-from-root");
    } finally {
      await rm(tempRoot, { recursive: true, force: true });
    }
  });

  it("reloads values from a new root when forceReload is enabled", async () => {
    const firstRoot = await mkdtemp(path.join(os.tmpdir(), "web-root-env-"));
    const secondRoot = await mkdtemp(path.join(os.tmpdir(), "web-root-env-"));

    try {
      await writeFile(
        path.join(firstRoot, ".env"),
        `${ROOT_ENV_PUBLIC_TEST_KEY}=value-from-first-root\n`,
        "utf-8",
      );
      await writeFile(
        path.join(secondRoot, ".env"),
        `${ROOT_ENV_PUBLIC_TEST_KEY}=value-from-second-root\n`,
        "utf-8",
      );

      loadRootEnv({ projectDir: firstRoot, forceReload: true, dev: true });
      expect(process.env[ROOT_ENV_PUBLIC_TEST_KEY]).toBe("value-from-first-root");

      loadRootEnv({ projectDir: secondRoot, forceReload: true, dev: true });
      expect(process.env[ROOT_ENV_PUBLIC_TEST_KEY]).toBe("value-from-second-root");
    } finally {
      await rm(firstRoot, { recursive: true, force: true });
      await rm(secondRoot, { recursive: true, force: true });
    }
  });
});
