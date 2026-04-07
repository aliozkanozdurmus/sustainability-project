// Bu yardimci, Playwright kosumu oncesi docker ve ortam hazirligini yonetir.

import { constants as fsConstants } from "node:fs";
import { access, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));

export const WEB_DIR = path.resolve(scriptDir, "../..");
export const REPO_ROOT = path.resolve(scriptDir, "../../../..");
export const PLAYWRIGHT_OUTPUT_ROOT = path.join(REPO_ROOT, "output", "playwright");
export const PLAYWRIGHT_DOWNLOAD_ROOT = path.join(PLAYWRIGHT_OUTPUT_ROOT, "downloads");
export const PLAYWRIGHT_MANUAL_ROOT = path.join(PLAYWRIGHT_OUTPUT_ROOT, "manual-smoke");
export const DEFAULT_SERVICES = ["postgres", "redis", "api", "worker", "web"];

function quoteWindowsArg(value) {
  if (value.length === 0) {
    return '""';
  }
  if (!/[ \t"&()<>^|]/.test(value)) {
    return value;
  }

  let escaped = '"';
  let backslashCount = 0;
  for (const char of value) {
    if (char === "\\") {
      backslashCount += 1;
      continue;
    }
    if (char === '"') {
      escaped += `${"\\".repeat((backslashCount * 2) + 1)}"`;
      backslashCount = 0;
      continue;
    }
    escaped += `${"\\".repeat(backslashCount)}${char}`;
    backslashCount = 0;
  }
  escaped += `${"\\".repeat(backslashCount * 2)}"`;
  return escaped;
}

export async function runCommand(command, args, options = {}) {
  return await new Promise((resolve, reject) => {
    const stdio = options.stdio ?? ["ignore", "pipe", "pipe"];
    const child =
      process.platform === "win32"
        ? spawn(
            process.env.ComSpec ?? "cmd.exe",
            ["/d", "/s", "/c", [command, ...args].map(quoteWindowsArg).join(" ")],
            {
              cwd: options.cwd ?? REPO_ROOT,
              env: { ...process.env, ...(options.env ?? {}) },
              stdio,
              windowsHide: true,
            },
          )
        : spawn(command, args, {
            cwd: options.cwd ?? REPO_ROOT,
            env: { ...process.env, ...(options.env ?? {}) },
            stdio,
          });

    let stdout = "";
    let stderr = "";

    child.stdout?.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr?.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0 || options.allowFailure) {
        resolve({ code: code ?? 0, stdout, stderr });
        return;
      }
      reject(
        new Error(
          [
            `Command failed: ${command} ${args.join(" ")}`,
            stdout.trim(),
            stderr.trim(),
          ]
            .filter(Boolean)
            .join("\n"),
        ),
      );
    });
  });
}

async function ensureCommand(command, versionArgs = ["--version"]) {
  await runCommand(command, versionArgs);
}

function parseComposePsOutput(rawOutput) {
  const trimmed = rawOutput.trim();
  if (!trimmed) {
    return [];
  }

  try {
    const parsed = JSON.parse(trimmed);
    return Array.isArray(parsed) ? parsed : [parsed];
  } catch {
    return trimmed
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        try {
          return JSON.parse(line);
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  }
}

async function readComposeServiceStatus() {
  const response = await runCommand(
    "docker",
    ["compose", "ps", "--all", "--format", "json"],
    { cwd: REPO_ROOT, allowFailure: true },
  );
  const rows = parseComposePsOutput(response.stdout);
  return rows.map((row) => {
    const stateText = String(row.State ?? "").toLowerCase();
    const statusText = String(row.Status ?? row.State ?? "").toLowerCase();
    const healthText =
      String(row.Health ?? "").toLowerCase() ||
      (statusText.includes("healthy")
        ? "healthy"
        : statusText.includes("unhealthy")
          ? "unhealthy"
          : "");
    return {
      service: String(row.Service ?? row.Name ?? ""),
      statusText,
      running:
        stateText === "running" ||
        statusText.includes("running") ||
        statusText.startsWith("up "),
      health: healthText,
    };
  });
}

async function waitForCondition(label, fn, { timeoutMs = 240_000, intervalMs = 2_000 } = {}) {
  const start = Date.now();
  let lastError = null;
  while (Date.now() - start <= timeoutMs) {
    try {
      const result = await fn();
      if (result) {
        return result;
      }
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  if (lastError instanceof Error) {
    throw new Error(`${label} timed out. ${lastError.message}`);
  }
  throw new Error(`${label} timed out.`);
}

async function waitForServicesHealthy(services) {
  await waitForCondition("Docker services to become healthy", async () => {
    const rows = await readComposeServiceStatus();
    const serviceMap = new Map(rows.map((row) => [row.service, row]));
    const unhealthy = services
      .map((service) => {
        const row = serviceMap.get(service);
        const healthy = row?.running && (!row.health || row.health === "healthy");
        return healthy ? null : `${service}=${row?.statusText || "missing"}`;
      })
      .filter(Boolean);
    if (unhealthy.length === 0) {
      return true;
    }
    return false;
  });
}

async function waitForHttp(url, label) {
  await waitForCondition(label, async () => {
    const response = await fetch(url, { method: "GET", cache: "no-store" });
    return response.ok;
  });
}

function parseLastJsonLine(rawOutput) {
  const lastLine = rawOutput
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .at(-1);
  if (!lastLine) {
    throw new Error("Expected JSON output but command returned no stdout.");
  }
  return JSON.parse(lastLine);
}

export async function ensurePlaywrightPrerequisites() {
  await ensureCommand("docker");
  await runCommand("docker", ["compose", "version"]);
  await ensureCommand("pnpm");
  await ensureCommand("node");

  const playwrightPackagePath = path.join(
    WEB_DIR,
    "node_modules",
    "@playwright",
    "test",
  );
  try {
    await access(playwrightPackagePath, fsConstants.F_OK);
  } catch {
    throw new Error(
      "Playwright dependency is missing under apps/web/node_modules. Run `pnpm install` before `pnpm e2e`.",
    );
  }
}

export async function ensurePlaywrightOutputDirectories() {
  await mkdir(PLAYWRIGHT_OUTPUT_ROOT, { recursive: true });
  await mkdir(PLAYWRIGHT_DOWNLOAD_ROOT, { recursive: true });
  await mkdir(PLAYWRIGHT_MANUAL_ROOT, { recursive: true });
}

export function buildPlaywrightEnv(workspace) {
  return {
    PLAYWRIGHT_DEMO_TENANT_ID: workspace.tenant_id,
    PLAYWRIGHT_DEMO_PROJECT_ID: workspace.project_id,
    PLAYWRIGHT_WEB_BASE_URL:
      process.env.PLAYWRIGHT_WEB_BASE_URL ?? "http://127.0.0.1:3000",
    PLAYWRIGHT_API_BASE_URL:
      process.env.PLAYWRIGHT_API_BASE_URL ?? "http://127.0.0.1:8000",
  };
}

export async function preparePlaywrightEnvironment(options = {}) {
  const services = options.services ?? DEFAULT_SERVICES;

  await ensurePlaywrightPrerequisites();
  await ensurePlaywrightOutputDirectories();

  if (!options.skipDocker) {
    await runCommand("docker", ["compose", "up", "-d", ...services], { cwd: REPO_ROOT });
  }

  await waitForServicesHealthy(services);
  await waitForHttp(
    `${process.env.PLAYWRIGHT_API_BASE_URL ?? "http://127.0.0.1:8000"}/health/live`,
    "API /health/live",
  );
  await waitForHttp(
    `${process.env.PLAYWRIGHT_API_BASE_URL ?? "http://127.0.0.1:8000"}/health/ready`,
    "API /health/ready",
  );
  await waitForHttp(
    process.env.PLAYWRIGHT_WEB_BASE_URL ?? "http://127.0.0.1:3000",
    "Web application root",
  );

  const seedResponse = await runCommand(
    "docker",
    ["compose", "exec", "-T", "api", "python", "/workspace/scripts/setup_demo_workspace.py"],
    { cwd: REPO_ROOT },
  );
  return parseLastJsonLine(seedResponse.stdout);
}
