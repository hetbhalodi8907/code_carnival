/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // The backend has no CORS middleware, so the browser talks to the Vite origin and
  // /api is forwarded to FastAPI. One setting controls the backend location.
  const proxy = {
    "/api": { target: env.VITE_DEV_PROXY_TARGET || "http://localhost:8000", changeOrigin: false },
  };

  return {
    plugins: [react(), tailwindcss()],
    resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
    server: { port: 5173, strictPort: true, proxy },
    preview: { port: 4173, strictPort: true, proxy },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      restoreMocks: true,
      env: { VITE_USE_MOCK_API: "false", VITE_API_BASE_URL: "" },
    },
  };
});
