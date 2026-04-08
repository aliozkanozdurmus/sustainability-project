const config = {
  "**/*.{md,mdx,json,yml,yaml}": "prettier --write",
  "**/*.{js,jsx,ts,tsx,mjs,cjs}": "prettier --write",
  "apps/web/**/*.{js,jsx,ts,tsx,mjs,cjs}": "eslint --fix",
  "apps/web/**/*.css": ["prettier --write", "stylelint --fix"],
};

export default config;
