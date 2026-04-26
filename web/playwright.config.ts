import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  use: {
    baseURL: "http://localhost:8767",
    ...devices["Chromium"],
    viewport: { width: 390, height: 844 },
  },
  webServer: {
    command: "true",
    url: "http://localhost:8767/api/state",
    reuseExistingServer: true,
  },
});
