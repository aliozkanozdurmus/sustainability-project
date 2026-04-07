// Bu runner, web E2E suite'inin standart Playwright kosumunu baslatir.

import { buildPlaywrightEnv, preparePlaywrightEnvironment, runCommand, WEB_DIR } from "./playwright-env.mjs";

const PLAYWRIGHT_CONFIG_PATH = "./e2e/playwright.config.ts";

async function main() {
  const args = process.argv.slice(2);
  const skipDocker = args.includes("--skip-docker");
  const forwardedArgs = args.filter((arg) => arg !== "--skip-docker");

  const workspace = await preparePlaywrightEnvironment({ skipDocker });
  const env = buildPlaywrightEnv(workspace);

  await runCommand(
    "pnpm",
    ["exec", "playwright", "test", "--config", PLAYWRIGHT_CONFIG_PATH, ...forwardedArgs],
    {
      cwd: WEB_DIR,
      env,
      stdio: "inherit",
    },
  );
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
