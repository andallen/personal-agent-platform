import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": "http://localhost:8767",
      "/ws": { target: "ws://localhost:8767", ws: true },
    },
  },
  build: { outDir: "dist", target: "es2020", sourcemap: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    css: true,
  },
});
