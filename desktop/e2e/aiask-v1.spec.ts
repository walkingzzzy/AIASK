import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const STORAGE_KEY = "aiask.desktop.connectionSettings.v1";
const isLive = process.env.AIASK_E2E_MODE === "live";
const agentBase = process.env.AIASK_E2E_AGENT_BASE || process.env.VITE_AIASK_API_BASE || "http://127.0.0.1:8765";
const apiToken = process.env.AIASK_E2E_API_TOKEN || "";
const controlToken = process.env.AIASK_E2E_CONTROL_TOKEN || "";
const e2eUserId = process.env.AIASK_E2E_USER_ID || "e2e-user";
const requireModelSmokeSuccess = process.env.AIASK_E2E_REQUIRE_MODEL_SMOKE_SUCCESS === "1";
const saveModelConfig = process.env.AIASK_E2E_SAVE_MODEL_CONFIG === "1";
const failedAgentResponses = new WeakMap<object, string[]>();

async function confirmDryRun(page: Page) {
  const preview = page.getByTestId("dry-run-preview");
  await expect(preview).toBeVisible();
  await page.getByTestId("dry-run-confirm").click();
}

async function confirmIntentPreview(page: Page) {
  const preview = page.getByTestId("intent-preview");
  await expect(preview).toBeVisible();
  await page.getByTestId("intent-preview-confirm").click();
}

function matchesAgent(path: string, method = "GET") {
  return (response: { url(): string; request(): { method(): string }; ok(): boolean }) => {
    const url = new URL(response.url());
    return response.url().startsWith(agentBase) && url.pathname === path && response.request().method() === method && response.ok();
  };
}

function matchesAgentPrefix(pathPrefix: string, method = "GET") {
  return (response: { url(): string; request(): { method(): string }; ok(): boolean }) => {
    const url = new URL(response.url());
    return response.url().startsWith(agentBase) && url.pathname.startsWith(pathPrefix) && response.request().method() === method && response.ok();
  };
}

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
  const failures: string[] = [];
  failedAgentResponses.set(page, failures);
  if (isLive) {
    page.on("response", (response) => {
      if (!response.url().startsWith(agentBase) || response.status() < 400) return;
      const url = new URL(response.url());
      failures.push(`${response.request().method()} ${url.pathname} -> ${response.status()}`);
    });
  }
  await page.addInitScript(
    ({ key, mode, baseUrl, token, control, userId }) => {
      window.localStorage.setItem(
        key,
        JSON.stringify({
          baseUrl,
          apiToken: token,
          controlToken: control,
          mode,
          userId
        })
      );
    },
    {
      key: STORAGE_KEY,
      mode: isLive ? "live" : "mock",
      baseUrl: agentBase,
      token: apiToken,
      control: controlToken,
      userId: e2eUserId
    }
  );
});

test.afterEach(async ({ page }) => {
  if (!isLive) return;
  expect(failedAgentResponses.get(page) || []).toEqual([]);
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

  const healthResponse = page.waitForResponse(matchesAgent("/health"));
  await page.goto("/");
  await healthResponse;
  await expect(page.getByText("Live Agent").first()).toBeVisible();
});

test("live workbench submits a response through Agent HTTP", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");

  await page.goto("/");
  await page.getByTestId("workbench-prompt").fill("AIASK live e2e smoke: reply briefly.");

  const response = page.waitForResponse(matchesAgent("/v1/responses", "POST"));
  await page.getByTestId("workbench-submit").click();
  const result = await response;
  expect(result.ok()).toBeTruthy();
  await expect(page.getByTestId("json-panel").last()).toBeVisible();
});

test("live sessions and runs page loads run evidence and steers a run", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");
  test.skip(!controlToken, "control token is required for run steering");

  const runsResponse = page.waitForResponse(matchesAgent("/v1/desktop/runs"));
  await page.goto("/sessions-runs");
  const runsPayload = await (await runsResponse).json();
  const runRows = Array.isArray(runsPayload.data) ? runsPayload.data : Array.isArray(runsPayload.runs) ? runsPayload.runs : [];
  const firstRun = runRows[0] || {};
  const runId = String(firstRun.id || firstRun.run_id || "");
  test.skip(!runId, "no run is available to steer");

  await page.getByTestId("run-id-input").fill(runId);
  await page.getByTestId("run-steer-instruction").fill("AIASK V1 live e2e steer: record safe progress only.");

  const steerResponse = page.waitForResponse(matchesAgent(`/v1/runs/${runId}/steer`, "POST"));
  await page.getByTestId("run-steer").click();
  await confirmDryRun(page);
  const steerPayload = await (await steerResponse).json();
  expect(steerPayload.object).toBe("run.steer");
  expect(steerPayload.run_id).toBe(runId);
});

test("live data sync plan returns a dry-run intent envelope", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");

  await page.goto("/data-sync");
  await page.getByTestId("data-sync-codes").fill("600519,000001");

  const response = page.waitForResponse(matchesAgent("/v1/desktop/data/sync-plan", "POST"));
  await page.getByTestId("data-sync-plan").click();
  const result = await response;
  expect(result.ok()).toBeTruthy();

  const payload = await result.json();
  expect(JSON.stringify(payload)).toContain("data_sync.sync");
  await expect(page.getByTestId("json-panel").last()).toBeVisible();
});

test("live tools page creates confirms and denies gated ActionIntents", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");
  test.skip(!controlToken, "control token is required for intent creation");

  await page.goto("/tools-approvals");

  const response = page.waitForResponse(matchesAgent("/intents", "POST"));
  await page.getByTestId("create-safe-intent").click();
  await confirmIntentPreview(page);
  const result = await response;
  expect(result.ok()).toBeTruthy();

  const payload = await result.json();
  expect(JSON.stringify(payload)).toContain("data_sync.sync");

  const createdIntent = payload.data?.intent || payload.intent || payload.data || {};
  const intentId = String(createdIntent.intent_id || createdIntent.id || "");
  expect(intentId).not.toBe("");

  const confirmResponse = page.waitForResponse(matchesAgent(`/intents/${intentId}/confirm`, "POST"));
  await page.getByTestId("intent-confirm-first").click();
  const confirmPayload = await (await confirmResponse).json();
  expect(JSON.stringify(confirmPayload)).toMatch(/confirmed|executed|success/i);

  const denyCreateResponse = page.waitForResponse(matchesAgent("/intents", "POST"));
  await page.getByTestId("create-safe-intent").click();
  await confirmIntentPreview(page);
  const denyCreatePayload = await (await denyCreateResponse).json();
  const denyIntent = denyCreatePayload.data?.intent || denyCreatePayload.intent || denyCreatePayload.data || {};
  const denyIntentId = String(denyIntent.intent_id || denyIntent.id || "");
  expect(denyIntentId).not.toBe("");
  await expect(page.getByTestId("pending-intent-id")).toHaveText(denyIntentId);

  const denyResponse = page.waitForResponse(matchesAgent(`/intents/${denyIntentId}/deny`, "POST"));
  await page.getByTestId("intent-deny-first").click();
  const denyPayload = await (await denyResponse).json();
  expect(JSON.stringify(denyPayload)).toMatch(/denied|success/i);
});

test("live models page runs the configured model smoke test", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");

  await page.goto("/models");
  await expect.poll(async () => page.getByTestId("model-name").inputValue(), { timeout: 15_000 }).not.toBe("");

  if (controlToken && saveModelConfig) {
    const saveResponse = page.waitForResponse(matchesAgent("/v1/ai/config", "PATCH"));
    await page.getByTestId("model-save-config").click();
    const savePayload = await (await saveResponse).json();
    expect(savePayload.saved || savePayload.configured).toBeTruthy();
    expect(savePayload.secrets_redacted).toBeTruthy();
  }

  const response = page.waitForResponse(matchesAgent("/v1/ai/smoke", "POST"));
  await page.getByTestId("model-smoke").click();
  const result = await response;
  const payload = await result.json();

  expect(payload.configured).toBeTruthy();
  expect(payload.secrets_redacted).toBeTruthy();
  if (requireModelSmokeSuccess) {
    expect(payload.success).toBeTruthy();
  }
  if (payload.success !== true) {
    expect(String(payload.error_code || "")).toMatch(/AUTH_FAILED|TIMEOUT|NETWORK_ERROR|AI_SMOKE_FAILED/);
    expect(String(payload.error || "")).not.toBe("");
  }
  await expect(page.getByTestId("json-panel").last()).toBeVisible();
});

test("live stock data source test uses the Agent provider contract", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");
  test.skip(!controlToken, "control token is required for stock source testing");

  await page.goto("/stock-data-sources");
  await page.getByTestId("stock-source-provider").selectOption("akshare");

  const response = page.waitForResponse(matchesAgent("/v1/desktop/stock-data-sources/test", "POST"));
  await page.getByTestId("stock-source-test").click();
  const payload = await (await response).json();

  expect(payload.provider).toBe("akshare");
  expect(payload.error_code || "").not.toBe("UNSUPPORTED_PROVIDER");
  expect(payload.secrets_redacted).toBeTruthy();
  expect(payload.success).toBeTruthy();

  const saveResponse = page.waitForResponse(matchesAgent("/v1/desktop/stock-data-sources", "POST"));
  await page.getByTestId("stock-source-save").click();
  const savePayload = await (await saveResponse).json();
  expect(savePayload.source.provider).toBe("akshare");
  expect(savePayload.secrets_redacted).toBeTruthy();
});

test("live quant research creates a dry-run research run and loads its report", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");

  await page.goto("/quant-research");
  await page.getByTestId("quant-symbol").fill("600519");

  const createResponse = page.waitForResponse(matchesAgent("/v1/desktop/quant/research-runs", "POST"));
  await page.getByTestId("quant-create-run").click();
  const createPayload = await (await createResponse).json();
  expect(createPayload.success).toBeTruthy();
  expect(JSON.stringify(createPayload)).toContain("research_id");

  const reportResponse = page.waitForResponse(matchesAgentPrefix("/v1/desktop/quant/research-runs/", "GET"));
  await page.getByTestId("quant-load-report").click();
  const reportPayload = await (await reportResponse).json();
  expect(JSON.stringify(reportPayload)).toMatch(/backtest|report|metrics/i);
});

test("live financial manager performs read-only query and creates a controlled intent", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");
  test.skip(!controlToken, "control token is required for financial intent creation");

  await page.goto("/financial-manager");
  await page.getByTestId("financial-query").fill("AIASK live e2e: read-only portfolio risk.");

  const queryResponse = page.waitForResponse(matchesAgent("/v1/desktop/financial-manager/query", "POST"));
  await page.getByTestId("financial-run-query").click();
  const queryPayload = await (await queryResponse).json();
  expect(queryPayload.success).toBeTruthy();
  expect(queryPayload.tool).toBe("agent_portfolio_risk");

  const intentResponse = page.waitForResponse(matchesAgent("/v1/desktop/financial-manager/intent", "POST"));
  await page.getByTestId("financial-create-intent").click();
  await confirmDryRun(page);
  const intentPayload = await (await intentResponse).json();
  expect(intentPayload.success).toBeTruthy();
  expect(JSON.stringify(intentPayload)).toContain("portfolio_manager.create");

  const brokerRunResponse = page.waitForResponse(matchesAgent("/v1/desktop/broker/analytics/run", "POST"));
  await page.getByTestId("broker-analytics-run").click();
  await confirmDryRun(page);
  const brokerRunPayload = await (await brokerRunResponse).json();
  expect(JSON.stringify(brokerRunPayload)).toMatch(/analytics|broker|dry/i);

  const brokerLatestResponse = page.waitForResponse(matchesAgent("/v1/desktop/broker/analytics/latest", "GET"));
  await page.getByTestId("broker-analytics-latest").click();
  expect((await brokerLatestResponse).ok()).toBeTruthy();
});

test("live stock radar creates a gated run intent from its product page", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");
  test.skip(!controlToken, "control token is required for radar intent creation");

  await page.goto("/stock-radar");

  const response = page.waitForResponse(matchesAgent("/intents", "POST"));
  await page.getByTestId("stock-radar-run-intent").click();
  const payload = await (await response).json();

  expect(JSON.stringify(payload)).toContain("stock_radar.run_once");

  const deliverResponse = page.waitForResponse(matchesAgent("/intents", "POST"));
  await page.getByTestId("stock-radar-deliver-intent").click();
  const deliverPayload = await (await deliverResponse).json();
  expect(JSON.stringify(deliverPayload)).toContain("stock_radar.push_digest");
});

test("live market temperature page loads tool-backed snapshot and readiness", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");

  const snapshotResponse = page.waitForResponse(matchesAgent("/v1/tools/agent_market_temperature_snapshot", "POST"));
  const readinessResponse = page.waitForResponse(matchesAgent("/v1/tools/agent_market_temperature_cache_readiness", "POST"));
  await page.goto("/market-temperature");
  const snapshotPayload = await (await snapshotResponse).json();
  const readinessPayload = await (await readinessResponse).json();

  expect(JSON.stringify(snapshotPayload)).toMatch(/temperature|market|success/i);
  expect(JSON.stringify(readinessPayload)).toMatch(/readiness|cache|success/i);
});

test("live MCP connectors exercise available gated resource prompt and connector actions", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");
  test.skip(!controlToken, "control token is required for MCP connector actions");

  await page.goto("/mcp-connectors");

  const resourceButton = page.getByTestId("mcp-read-first-resource");
  if (await resourceButton.isEnabled()) {
    const response = page.waitForResponse(matchesAgent("/v1/mcp/resources/read", "POST"));
    await resourceButton.click();
    expect((await response).ok()).toBeTruthy();
  }

  const promptButton = page.getByTestId("mcp-get-first-prompt");
  if (await promptButton.isEnabled()) {
    const response = page.waitForResponse(matchesAgent("/v1/mcp/prompts/get", "POST"));
    await promptButton.click();
    expect((await response).ok()).toBeTruthy();
  }

  const connectorButton = page.getByTestId("connector-test-first");
  if (await connectorButton.isEnabled()) {
    const response = page.waitForResponse(matchesAgentPrefix("/v1/connectors/", "POST"));
    await connectorButton.click();
    expect((await response).ok()).toBeTruthy();
  }
});

test("live plugins and skills create and delete an isolated sample skill", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");
  test.skip(!controlToken, "control token is required for skill mutation");

  await page.goto("/plugins-skills");

  const createResponse = page.waitForResponse(matchesAgent("/v1/skills", "POST"));
  await page.getByTestId("skill-create-sample").click();
  await confirmDryRun(page);
  const createPayload = await (await createResponse).json();
  expect(createPayload.success).toBeTruthy();
  expect(JSON.stringify(createPayload)).toContain("desktop-v1-smoke-skill");

  const deleteResponse = page.waitForResponse(matchesAgentPrefix("/v1/skills/", "DELETE"));
  await page.getByTestId("skill-delete-sample").click();
  await confirmDryRun(page);
  const deletePayload = await (await deleteResponse).json();
  expect(deletePayload.success).toBeTruthy();
  expect(JSON.stringify(deletePayload)).toContain("deleted");

  const selfTestButton = page.getByTestId("plugin-self-test-first");
  if (await selfTestButton.isEnabled()) {
    const selfTestResponse = page.waitForResponse(matchesAgentPrefix("/v1/plugins/", "POST"));
    await selfTestButton.click();
    expect((await selfTestResponse).ok()).toBeTruthy();
  }

  const toggleButton = page.getByTestId("plugin-toggle-first");
  if (await toggleButton.isEnabled()) {
    const toggleResponse = page.waitForResponse(matchesAgentPrefix("/v1/plugins/", "PATCH"));
    await toggleButton.click();
    await confirmDryRun(page);
    expect((await toggleResponse).ok()).toBeTruthy();

    if (await toggleButton.isEnabled()) {
      const restoreResponse = page.waitForResponse(matchesAgentPrefix("/v1/plugins/", "PATCH"));
      await toggleButton.click();
      await confirmDryRun(page);
      expect((await restoreResponse).ok()).toBeTruthy();
    }
  }
});

test("live gateway sends a local controlled delivery request", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");
  test.skip(!controlToken, "control token is required for gateway send");

  await page.goto("/gateway-webhooks");
  await page.getByTestId("gateway-message").fill("AIASK V1 live gateway local smoke.");

  const response = page.waitForResponse(matchesAgent("/v1/gateway/send", "POST"));
  await page.getByTestId("gateway-send-local").click();
  await confirmDryRun(page);
  const payload = await (await response).json();

  expect(payload.data.adapter.ok).toBeTruthy();
  expect(payload.data.message.platform).toBe("local");

  const refreshResponse = page.waitForResponse(matchesAgent("/v1/gateway/directory/refresh", "POST"));
  await page.getByTestId("gateway-refresh-directory").click();
  await confirmDryRun(page);
  expect((await refreshResponse).ok()).toBeTruthy();

  const retryButton = page.getByTestId("gateway-retry-first");
  if (await retryButton.isEnabled()) {
    const retryResponse = page.waitForResponse(matchesAgentPrefix("/v1/gateway/messages/", "POST"));
    await retryButton.click();
    await confirmDryRun(page);
    expect((await retryResponse).ok()).toBeTruthy();
  }

  const healthButton = page.getByTestId("gateway-platform-health");
  if (await healthButton.isEnabled()) {
    const healthResponse = page.waitForResponse(matchesAgentPrefix("/v1/gateway/platforms/", "GET"));
    await healthButton.click();
    expect((await healthResponse).ok()).toBeTruthy();
  }
});

test("live automation creates disables and deletes an isolated sample job", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");
  test.skip(!controlToken, "control token is required for job mutation");

  await page.goto("/automation");

  const createResponse = page.waitForResponse(matchesAgent("/v1/jobs", "POST"));
  await page.getByTestId("job-create-sample").click();
  await confirmDryRun(page);
  const createPayload = await (await createResponse).json();
  expect(createPayload.job_id).toBeTruthy();
  await expect(page.getByRole("cell", { name: createPayload.name })).toBeVisible();

  const patchResponse = page.waitForResponse(matchesAgentPrefix(`/v1/jobs/${createPayload.job_id}`, "PATCH"));
  await page.getByTestId("job-disable-sample").click();
  await confirmDryRun(page);
  expect((await patchResponse).ok()).toBeTruthy();

  const deleteResponse = page.waitForResponse(matchesAgentPrefix(`/v1/jobs/${createPayload.job_id}`, "DELETE"));
  await page.getByTestId("job-delete-sample").click();
  await confirmDryRun(page);
  const deletePayload = await (await deleteResponse).json();
  expect(deletePayload.deleted).toBeTruthy();
});

test("live local user memory exports data and previews delete as dry-run", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");
  test.skip(!controlToken, "control token is required for user data actions");

  await page.goto("/local-user-memory");

  const exportResponse = page.waitForResponse(matchesAgentPrefix(`/v1/desktop/users/${e2eUserId}/export`, "GET"));
  await page.getByTestId("user-export-data").click();
  await confirmDryRun(page);
  const exportPayload = await (await exportResponse).json();
  expect(exportPayload.secrets_redacted).toBeTruthy();

  const deleteResponse = page.waitForResponse(matchesAgentPrefix(`/v1/desktop/users/${e2eUserId}/delete`, "POST"));
  await page.getByTestId("user-delete-dry-run").click();
  await confirmDryRun(page);
  const deletePayload = await (await deleteResponse).json();
  expect(deletePayload.dry_run).toBeTruthy();
  expect(deletePayload.secrets_redacted).toBeTruthy();

  const saveResponse = page.waitForResponse(matchesAgentPrefix(`/v1/desktop/users/${e2eUserId}/data-policy`, "PATCH"));
  await page.getByTestId("user-save-policy").click();
  await confirmDryRun(page);
  const savePayload = await (await saveResponse).json();
  expect(savePayload.object).toBe("aiask.user_data_policy");
  expect(savePayload.data.user_id).toBe(e2eUserId);
  expect(savePayload.data.allow_learning).toBe(false);
});

test("live ops diagnostic pages load readiness native learning and RL backends", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");
  test.skip(!controlToken, "control token is required for full-mode diagnostics");

  const readiness = [
    page.waitForResponse(matchesAgent("/health/detailed")),
    page.waitForResponse(matchesAgent("/v1/hermes/readiness")),
    page.waitForResponse(matchesAgent("/v1/financial-system/readiness"))
  ];
  await page.goto("/readiness");
  await Promise.all(readiness);

  const native = [
    page.waitForResponse(matchesAgent("/v1/processes")),
    page.waitForResponse(matchesAgent("/v1/terminal/backends")),
    page.waitForResponse(matchesAgent("/v1/browser/sessions"))
  ];
  await page.goto("/native-diagnostics");
  await Promise.all(native);

  const learning = [page.waitForResponse(matchesAgent("/v1/learning/status")), page.waitForResponse(matchesAgent("/v1/rl/environments"))];
  await page.goto("/learning-rl");
  await Promise.all(learning);
});

test("live learning and RL page exercises available gated actions", async ({ page }) => {
  test.skip(!isLive, "live smoke only runs with AIASK_E2E_MODE=live");
  test.skip(!controlToken, "control token is required for learning and RL actions");

  await page.goto("/learning-rl");

  const applyButton = page.getByTestId("learning-apply-first");
  if (await applyButton.isEnabled()) {
    const response = page.waitForResponse(matchesAgent("/v1/learning/apply", "POST"));
    await applyButton.click();
    await confirmDryRun(page);
    expect((await response).ok()).toBeTruthy();
  }

  const startButton = page.getByTestId("rl-start-first");
  if (await startButton.isEnabled()) {
    const response = page.waitForResponse(matchesAgent("/v1/rl/runs", "POST"));
    await startButton.click();
    await confirmDryRun(page);
    expect((await response).ok()).toBeTruthy();
  }

  const resultsButton = page.getByTestId("rl-load-results");
  if (await resultsButton.isEnabled()) {
    const response = page.waitForResponse(matchesAgentPrefix("/v1/rl/runs/", "GET"));
    await resultsButton.click();
    const payload = await (await response).json();
    expect(payload.object).toBe("rl.results");
  }

  const logsButton = page.getByTestId("rl-load-logs");
  if (await logsButton.isEnabled()) {
    const response = page.waitForResponse(matchesAgentPrefix("/v1/rl/runs/", "GET"));
    await logsButton.click();
    const payload = await (await response).json();
    expect(payload.object).toBe("rl.logs");
  }

  const stopButton = page.getByTestId("rl-stop-first");
  if (await stopButton.isEnabled()) {
    const response = page.waitForResponse(matchesAgentPrefix("/v1/rl/runs/", "POST"));
    await stopButton.click();
    await confirmDryRun(page);
    const payload = await (await response).json();
    expect(payload.object).toBe("rl.run");
  }
});
