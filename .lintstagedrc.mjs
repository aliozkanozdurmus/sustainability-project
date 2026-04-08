import path from "node:path";

const webRoot = path.resolve("apps/web");

const quote = (value) => `"${value.replaceAll('"', '\\"')}"`;

const toWebRelativePath = (file) =>
  path.relative(webRoot, path.resolve(file)).replaceAll("\\", "/");

const runWebEslint = (files) => {
  const relativeFiles = files.map(toWebRelativePath).map(quote).join(" ");

  return `pnpm --dir apps/web exec eslint --fix ${relativeFiles}`;
};

const config = {
  "**/*.{md,mdx,json,yml,yaml}": "prettier --write",
  "**/*.{js,jsx,ts,tsx,mjs,cjs}": "prettier --write",
  "apps/web/**/*.{js,jsx,ts,tsx,mjs,cjs}": runWebEslint,
  "apps/web/**/*.css": ["prettier --write", "stylelint --fix"],
};

export default config;
