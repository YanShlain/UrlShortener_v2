/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const api = process.env.API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: api, changeOrigin: false },
      "^/[0-9A-Za-z]{7}$": { target: api, changeOrigin: false },
    },
  },
  test: { environment: "jsdom" },
});
