import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const nextEnv = require("@next/env");

const loadEnvConfig =
  nextEnv.loadEnvConfig ??
  nextEnv.default?.loadEnvConfig;

if (typeof loadEnvConfig !== "function") {
  throw new TypeError("loadEnvConfig could not be resolved from @next/env.");
}

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));

export const WEB_DIR = path.resolve(MODULE_DIR, "..", "..");
export const REPO_ROOT = path.resolve(WEB_DIR, "..", "..");

const silentLog = {
  info: () => {},
  error: (...args) => {
    if (args.length > 0) {
      console.error(...args);
    }
  },
};

export function loadRootEnv(options = {}) {
  const dev = options.dev ?? process.env.NODE_ENV !== "production";
  const forceReload = options.forceReload ?? false;
  const projectDir = options.projectDir ?? REPO_ROOT;

  return loadEnvConfig(projectDir, dev, silentLog, forceReload);
}
