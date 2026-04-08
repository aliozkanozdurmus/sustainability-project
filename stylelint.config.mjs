const config = {
  extends: ["stylelint-config-standard"],
  ignoreFiles: ["**/node_modules/**", "**/.next/**", "output/**"],
  rules: {
    "alpha-value-notation": null,
    "at-rule-no-unknown": [
      true,
      {
        ignoreAtRules: ["apply", "custom-variant", "layer", "theme"],
      },
    ],
    "color-function-alias-notation": null,
    "color-function-notation": null,
    "color-hex-length": null,
    "custom-property-pattern": null,
    "declaration-empty-line-before": null,
    "import-notation": null,
    "keyframes-name-pattern": null,
    "selector-class-pattern": null,
  },
};

export default config;
