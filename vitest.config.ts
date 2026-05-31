import { defineConfig } from "vitest/config";

// Tests live in ai/src (shared risk-logic layer). Use the repo root, not the
// Vite `frontend` root, so the unit tests are discovered.
export default defineConfig({
  test: {
    root: ".",
    include: ["ai/src/**/*.test.ts", "frontend/src/**/*.test.ts"],
    environment: "node",
  },
});
