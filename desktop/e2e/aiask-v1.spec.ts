import { expect, test } from "@playwright/test";

const STORAGE_KEY = "aiask.desktop.connectionSettings.v1";
const isLive = process.env.AIASK_E2E_MODE === "live";
const agentBase = process.env.AIASK_E2E_AGENT_BASE || process.env.VITE_AIASK_API_BASE || "http://127.0.0.1:8765";
const apiToken = process.env.AIASK_E2E_API_TOKEN || "";
const controlToken = process.env.AIASK_E2E_CONTROL_TOKEN || "";

const pages = [
  "/",
  "/models",
  "/projects",
  "/sessions-runs",
  "/tools-approvals",
  "/integrations",
  "/mcp-connectors",
  "/plugins-skills",
  "/gateway-webhooks",
  "/stock-data-sources",
  "/data-sync",
  "/finance",
  "/stock-radar",
  "/market-temperature",
  "/quant-research",
  "/financial-manager",
  "/automation",
  "/workflows",
  "/settings",
  "/readiness",
  "/local-user-memory",
  "/learning-rl",
  "/native-diagnostics"
] as const;

test.beforeEach(async ({ page }) => {
  await page.addInitScript(
    ({ key, mode, baseUrl, token, control }) => {
      window.localStorage.setItem(
        key,
        JSON.stringify({
          baseUrl,
          apiToken: token,
          controlToken: control,
          mode,
          userId: "e2e-user"
        })
      );
    },
    {
      key: STORAGE_KEY,
      mode: isLive ? "live" : "mock",
      baseUrl: agentBase,
      token: apiToken,
      control: controlToken
    }
  );
});

for (const path of pages) {
  test(`opens V1 page ${path}`, async ({ page }) => {
    test.skip(isLive, "page matrix runs in mock mode; live mode runs focused backend loops");
    await page.goto(path);
    await expect(page.getByTestId("page-shell")).toBeVisible();
    await expect(page.getByTestId("page-title")).not.toHaveText("");
    await expect(page.getByText(/Strategy Factory|Factor Factory|Factory Events|Incubation/i)).toHaveCount(0);
  });
}

test("old deferred factory route redirects to V1 finance workspace", async ({ page }) => {
  test.skip(isLive, "deferred route matrix runs in mock mode");
  await page.goto("/strategy-factory");
  await expect(page).toHaveURL(/\/finance$/);
  await expect(page.getByTestId("page-shell")).toBeVisible();
  await expect(page.getByText(/Strategy Factory|Factor Factory|Factory Events|Incubation/i)).toHaveCount(0);
});

test("live mode reaches Agent health", async ({ page, request }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");

  const directHealth = await request.get(`${agentBase}/health`);
  expect(directHealth.ok()).toBeTruthy();

  const healthResponse = page.waitForResponse((response) => response.url().startsWith(`${agentBase}/health`) && response.ok());
  await page.goto("/");
  await healthResponse;
  await expect(page.getByText("Live Agent").first()).toBeVisible();
});

test("live workbench submits a response through Agent HTTP", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");

  await page.goto("/");
  await page.getByTestId("workbench-prompt").fill("AIASK live e2e smoke: reply briefly.");

  const response = page.waitForResponse((item) => item.url() === `${agentBase}/v1/responses` && item.request().method() === "POST");
  await page.getByTestId("workbench-submit").click();
  const result = await response;
  expect(result.ok()).toBeTruthy();
  await expect(page.getByTestId("json-panel").last()).toBeVisible();
});

test("live data sync plan returns a dry-run intent envelope", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");

  await page.goto("/data-sync");
  await page.getByTestId("data-sync-codes").fill("600519,000001");

  const response = page.waitForResponse((item) => item.url() === `${agentBase}/v1/desktop/data/sync-plan` && item.request().method() === "POST");
  await page.getByTestId("data-sync-plan").click();
  const result = await response;
  expect(result.ok()).toBeTruthy();

  const payload = await result.json();
  expect(JSON.stringify(payload)).toContain("data_sync.sync");
  await expect(page.getByTestId("json-panel").last()).toBeVisible();
});

test("live tools page creates a gated ActionIntent", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");
  test.skip(!controlToken, "control token is required for intent creation");

  await page.goto("/tools-approvals");

  const response = page.waitForResponse((item) => item.url() === `${agentBase}/intents` && item.request().method() === "POST");
  await page.getByTestId("create-safe-intent").click();
  const result = await response;
  expect(result.ok()).toBeTruthy();

  const payload = await result.json();
  expect(JSON.stringify(payload)).toContain("data_sync.sync");
});
