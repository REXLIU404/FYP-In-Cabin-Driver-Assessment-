import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Where the dev server forwards /api. scripts/dev.sh sets DRA_DEV_BACKEND_URL when it runs the
// backend on another port; otherwise it is the backend's usual 127.0.0.1:8000. (Read through
// globalThis because the project has no @types/node.)
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env;
const backendUrl = env?.DRA_DEV_BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  root: "frontend",
  plugins: [react()],
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
  server: {
    proxy: { "/api": backendUrl },
    fs: {
      allow: [".."],
    },
  },
});
