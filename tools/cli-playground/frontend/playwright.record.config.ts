import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e-record",
  outputDir: process.env.CLI_RECORD_OUTPUT,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 240_000,
  use: {
    permissions: ["clipboard-read", "clipboard-write"],
    baseURL: process.env.CLI_RECORD_URL,
    viewport: { width: 1360, height: 820 },
    video: { mode: "on", size: { width: 1360, height: 820 } },
  },
});
