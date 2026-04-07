// Bu yapilandirma, web birim testlerinin kosum varsayimlarini belirler.

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});

