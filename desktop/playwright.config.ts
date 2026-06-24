import { defineConfig, devices } from "@playwright/test";

const isLive = process.env.AIASK_E2E_MODE === "live";

export default defineConfig({
  testDir: "./e2e",
  timeout: isLive ? 180_000 : 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: !isLive,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:1420",
    trace: "retain-on-failure"
  },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:1420",
    reuseExistingServer: true,
    timeout: 120_000
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ]
});
