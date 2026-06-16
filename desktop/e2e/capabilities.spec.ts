import { expect, test, type Page } from "@playwright/test";
import { API_ORIGIN, setupApiMocks } from "./support/capabilitiesMockServer";
import { runFullFrontendMatrix } from "./support/capabilitiesFullMatrix";
import { collectMainInventory, expectCleanInventory } from "./support/capabilitiesInventory";
import {
  CONTROL_TOKEN,
  clickSettingsPanelRefresh,
  controlLabel,
  expectedTextLabel,
  expandAdvancedMcpOperations,
  openCapabilityTab,
  openMainView,
  openOverview,
  openSettings,
  openSettingsSection,
  placeholderLabel,
  settingsReturnButton,
  setControlToken,
  tabLabel,
} from "./support/capabilitiesNavigation";

test.beforeEach(async ({ page }) => {
  const consoleMessages: string[] = [];
  const failedResponses: string[] = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleMessages.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("response", (response) => {
    const status = response.status();
    if (status >= 400 && !response.url().includes("/@vite")) {
      failedResponses.push(`${status} ${response.url()}`);
    }
  });
  page.on("dialog", async (dialog) => {
    await dialog.accept();
  });
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("aiask.e2e.initialized")) {
      sessionStorage.clear();
      sessionStorage.setItem("aiask.e2e.initialized", "1");
    }
    localStorage.clear();
    localStorage.setItem("aiask.endpoint", "http://127.0.0.1:8767");
    localStorage.setItem("aiask.endpoint.verified", "1");
    localStorage.setItem("aiask.endpoint.autoconnect", "1");
  });
  (page as Page & { _aiaskConsoleMessages?: string[] })._aiaskConsoleMessages = consoleMessages;
  (page as Page & { _aiaskFailedResponses?: string[] })._aiaskFailedResponses = failedResponses;
});

test.afterEach(async ({ page }) => {
  const consoleMessages = (page as Page & { _aiaskConsoleMessages?: string[] })._aiaskConsoleMessages || [];
  const failedResponses = (page as Page & { _aiaskFailedResponses?: string[] })._aiaskFailedResponses || [];
  expect(consoleMessages).toEqual([]);
  expect(failedResponses).toEqual([]);
});

test("MCP panel gates controls without token and executes resource, prompt, and OAuth calls with token", async ({ page }) => {
  await setupApiMocks(page);
  await openOverview(page);

  await openMainView(page, "Capabilities");
  await openCapabilityTab(page, "MCP");
  await expect(page.getByText(/缺少控制令牌|需要控制令牌/).first()).toBeVisible();
  await expect(page.getByRole("button", { name: controlLabel("Read MCP resource"), exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: controlLabel("Get MCP prompt"), exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: controlLabel("Start MCP OAuth flow"), exact: true })).toBeDisabled();

  await setControlToken(page);
  await openMainView(page, "Capabilities");
  await openCapabilityTab(page, "MCP");
  await expect(page.getByText("完整 MCP 运行时数据已加载。")).toBeVisible();
  await expect(page.getByText("1 个已配置")).toBeVisible();
  await expect(page.getByText("agent_mcp_finance_demo_quote")).toBeVisible();
  await expect(page.getByText("可用资源 1 个")).toBeVisible();
  await expect(page.getByText("可用提示词 1 个")).toBeVisible();
  await expect(page.getByText("OAuth 条目 1 个")).toBeVisible();

  await page.getByPlaceholder(placeholderLabel("resource uri")).fill("aiask://quotes");
  await page.getByRole("button", { name: controlLabel("Read MCP resource"), exact: true }).click();
  await expect(page.getByText("quote resource ok")).toBeVisible();

  await page.getByPlaceholder(placeholderLabel("prompt name")).fill("risk-review");
  await page.getByRole("button", { name: controlLabel("Get MCP prompt"), exact: true }).click();
  await expect(page.getByText("risk prompt ok")).toBeVisible();

  await page.getByPlaceholder(placeholderLabel("OAuth server name")).fill("finance-demo");
  await page.getByRole("button", { name: controlLabel("Start MCP OAuth flow"), exact: true }).click();
  await expect(page.getByText("oauth_required")).toBeVisible();
});

test("Strategy Factory panel renders success envelopes and structured degraded readiness", async ({ page }) => {
  await setupApiMocks(page, { factoryMode: "success" });
  await openOverview(page);
  await setControlToken(page);
  await openMainView(page, "Capabilities");
  await openCapabilityTab(page, "Strategy Factory");

  await expect(page.getByRole("heading", { name: "调度器、运行和晋升评审" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "工厂状态" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "最近运行" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "评审快照" })).toBeVisible();
  await expect(page.getByText("已实现").first()).toBeVisible();

  await page.unroute(`${API_ORIGIN}/**`);
  await setupApiMocks(page, { factoryMode: "degraded" });
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText("数据库已配置，但 strategy manager 返回错误。", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("STRATEGY_FACTORY_UNAVAILABLE").first()).toBeVisible();
  await expect(page.getByText("部分就绪").first()).toBeVisible();
});

test("Hermes capability tables expose v0.14 tool, platform, and feature parity with search and status filters", async ({ page }) => {
  await setupApiMocks(page);
  await openOverview(page);
  await setControlToken(page);
  await openMainView(page, "Capabilities");
  await openCapabilityTab(page, "Hermes");

  await expect(page.getByText("运行时为 AIASK-native。是否嵌入 vendor runtime：false")).toBeVisible();
  await expect(page.getByText("54 项")).toBeVisible();
  await expect(page.getByText("原始 Hermes payload")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hermes 工具映射" })).toBeVisible();

  const featureSection = page.locator(".capability-section").filter({ hasText: "功能映射" });
  const toolSection = page.locator(".capability-section").filter({ hasText: "Hermes 工具映射" });
  const platformSection = page.locator(".capability-section").filter({ hasText: "网关平台映射" });

  await expect(platformSection).toContainText("22 项");

  await featureSection.getByPlaceholder(placeholderLabel("Search area, tool, platform...")).fill("gateway_direct_delivery");
  await expect(featureSection).toContainText("agent_gateway_direct_deliver");

  await toolSection.getByPlaceholder(placeholderLabel("Search area, tool, platform...")).fill("discord_server");
  await expect(toolSection).toContainText("agent_discord_server");
  await toolSection.getByPlaceholder(placeholderLabel("Search area, tool, platform...")).fill("feishu_drive_list_comment_replies");
  await expect(toolSection).toContainText("agent_feishu_drive_list_comment_replies");
  await toolSection.getByPlaceholder(placeholderLabel("Search area, tool, platform...")).fill("rl_start_training");
  await expect(toolSection).toContainText("agent_rl_start_training");

  await toolSection.locator("select").selectOption("live_unverified");
  await expect(toolSection).toContainText("rl_start_training");
  await toolSection.locator("select").selectOption("missing");
  await expect(toolSection).toContainText("没有符合筛选条件的记录。");
});

test("AI Tests panel runs model status, smoke, model list, and Workbench response flow", async ({ page }) => {
  await setupApiMocks(page);
  await openOverview(page);
  await setControlToken(page);
  await openMainView(page, "Capabilities");
  await openCapabilityTab(page, "AI Tests");

  await expect(page.getByRole("heading", { name: "gpt-5.4" })).toBeVisible();
  await expect(page.getByText("提供方 openai / 真实后端 / 基础 URL 已配置")).toBeVisible();
  await expect(page.getByText("API 密钥")).toBeVisible();
  await expect(page.locator("body")).not.toContainText("sk-");

  await page.getByRole("button", { name: controlLabel("Run AI Smoke") }).click();
  await expect(page.getByText("AI_SMOKE_PASSED")).toBeVisible();
  await expect(page.locator(".capability-section").filter({ hasText: "冒烟测试结果" })).toContainText("AIASK model smoke ok.");
  await expect(page.getByText("123ms")).toBeVisible();

  await page.getByRole("button", { name: controlLabel("List Models") }).click();
  await expect(page.getByText("AI_MODELS_LOADED")).toBeVisible();
  const modelsSection = page.locator(".capability-section").filter({ has: page.getByRole("heading", { name: "模型", exact: true }) });
  await expect(modelsSection).toContainText("gpt-5.4");
  await expect(modelsSection).toContainText("gpt-5.2");

  await openMainView(page, "Agent");
  await page.getByPlaceholder(placeholderLabel("Ask AIASK to research, code, inspect tools, or continue a session...")).fill("请只回复 AIASK_OK");
  await page.getByRole("button", { name: controlLabel("Run"), exact: true }).click();
  await expect(page.getByRole("heading", { name: "智能体回复" })).toBeVisible();
  await expect(page.getByText("AIASK_OK").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "run.started" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "model.started" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "model.completed" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "model.delta" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "run.completed" }).first()).toBeVisible();

  await page.getByRole("button", { name: controlLabel("Load run events for selected task"), exact: true }).click();
  await expect(page.getByRole("heading", { name: "run.completed" }).first()).toBeVisible();
});

test("Capabilities workspace remains usable at desktop and narrow widths without raw JSON walls", async ({ page }) => {
  await setupApiMocks(page);
  await page.setViewportSize({ width: 1200, height: 829 });
  await openOverview(page);
  await setControlToken(page);
  await openMainView(page, "Capabilities");
  await expect(page.getByRole("heading", { name: "运行时评审", exact: true })).toBeVisible();
  await expect(page.getByText("Mock 数据").first()).toBeVisible();
  await expect(page.locator(".capabilities-workspace")).toBeVisible();
  await expect(page.locator(".capability-banner")).toContainText("后端对齐");
  await expect(page.locator(".raw-details").first()).toContainText("原始能力中心数据");

  await page.setViewportSize({ width: 980, height: 760 });
  await expect(page.locator(".capabilities-workspace")).toBeVisible();
  await expect(page.getByRole("button", { name: tabLabel("AI Tests") })).toBeVisible();
});

test("Market Temperature workspace renders localized cache panels and stays single-column on mobile", async ({ page }) => {
  await setupApiMocks(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await openOverview(page);
  await openMainView(page, "Market Temperature");

  await expect(page.getByRole("heading", { name: "市场温度" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "缓存就绪" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "缓存历史" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "行业历史" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "前向验证" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "行业成分股" })).toBeVisible();
  await expect(page.locator("main")).not.toContainText("Cache readiness");
  await expect(page.locator("main")).not.toContainText("Forward validation");
  await page.getByRole("button", { name: controlLabel("Update snapshot"), exact: true }).click();
  await expect(page.getByText(expectedTextLabel("MARKET_TEMPERATURE_LOADED"))).toBeVisible();

  const inventory = await collectMainInventory(page, "Market Temperature mobile");
  expectCleanInventory(inventory);
});

test("Data & Sync workspace renders database preflight and creates a gated sync intent in mock mode", async ({ page }) => {
  await setupApiMocks(page);
  await openOverview(page);
  await openMainView(page, "Data & Sync");
  await expect(page.getByRole("heading", { name: "数据库质量与同步审批" })).toBeVisible();
  await expect(page.getByText("/tmp/akshare_mcp.sqlite3").first()).toBeAttached();
  await expect(page.getByRole("heading", { name: "数据闸门复核" })).toBeVisible();
  await expect(page.locator("strong", { hasText: "agent_quant_data_gate" }).first()).toBeVisible();

  await page.getByRole("button", { name: controlLabel("Generate sync plan") }).click();
  await expect(page.getByText(expectedTextLabel("SYNC_PLAN_READY"))).toBeVisible();
  await expect(page.getByText("data_sync.run_once", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: controlLabel("Create approval intent") })).toBeDisabled();

  await setControlToken(page);
  await openMainView(page, "Data & Sync");
  await page.getByRole("button", { name: controlLabel("Generate sync plan") }).click();
  await expect(page.getByText(expectedTextLabel("SYNC_PLAN_READY"))).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Create approval intent") }).click();
  await expect(page.getByText(expectedTextLabel("SYNC_INTENT_CREATED"))).toBeVisible();
  await expect(page.getByText("intent_e2e_approved_path", { exact: true })).toBeVisible();
});

test("Settings advanced management panels execute integrations, webhooks, RL, security, and automation flows", async ({ page }) => {
  test.setTimeout(90_000);
  const requestedPaths: string[] = [];
  page.on("request", (request) => {
    if (request.url().startsWith(API_ORIGIN)) {
      const url = new URL(request.url());
      requestedPaths.push(`${request.method()} ${url.pathname}`);
    }
  });

  await setupApiMocks(page);
  await openOverview(page);
  await setControlToken(page);

  await openSettingsSection(page, "应用集成");
  await clickSettingsPanelRefresh(page);
  await expect(page.getByText("INTEGRATIONS_LOADED")).toBeVisible();
  const connectorRow = page.locator(".connector-item").filter({ hasText: "tongdaxin" }).first();
  await connectorRow.getByRole("button", { name: "详情", exact: true }).click();
  await connectorRow.getByRole("button", { name: "测试连接", exact: true }).click();
  await expect(page.getByText("连接器测试完成")).toBeVisible();
  await connectorRow.getByRole("button", { name: /生成配置片段/ }).click();
  await page.locator(".wizard-panel input").first().fill("119.147.212.81");
  await page.locator(".wizard-panel input").nth(1).fill("7709");
  await page.getByRole("button", { name: /下一步/ }).click();
  await page.locator(".wizard-panel").getByRole("button", { name: "完成", exact: true }).click();
  await expect(page.locator(".env-block")).toContainText("TDX_SERVER_IP=119.147.212.81");
  const platformRow = page.locator(".capability-section").filter({ hasText: "Gateway 平台" }).locator(".job-row").first();
  await platformRow.getByRole("button", { name: "健康", exact: true }).click();
  await platformRow.getByRole("button", { name: "启动", exact: true }).click();
  await platformRow.getByRole("button", { name: "停止", exact: true }).click();
  await page.locator("form").filter({ hasText: "消息发送预览" }).getByLabel("目标").fill("ops-room");
  await page.locator("form").filter({ hasText: "消息发送预览" }).getByRole("button", { name: "创建发送审批" }).click();
  await expect(page.getByText("GATEWAY_INTENT_CREATED")).toBeVisible();
  expect(requestedPaths).toContain("GET /v1/gateway/platforms/local/health");
  expect(requestedPaths).toContain("POST /v1/gateway/platforms/local/start");
  expect(requestedPaths).toContain("POST /v1/gateway/platforms/local/stop");

  await openSettingsSection(page, "Webhook");
  await clickSettingsPanelRefresh(page);
  await expect(page.locator(".capability-section").filter({ hasText: "订阅列表" })).toContainText("Mock Webhook");
  await page.getByRole("button", { name: "创建 Webhook", exact: true }).click();
  expect(requestedPaths).toContain("POST /v1/webhooks");
  await expect(page.locator(".capability-section").filter({ hasText: "订阅列表" })).toContainText("codex-mcp-test-webhook");
  await page.getByRole("button", { name: "创建触发审批", exact: true }).click();
  await expect(page.getByText("WEBHOOK_TRIGGER_INTENT_CREATED")).toBeVisible();
  const webhookRow = page.locator(".job-row").filter({ hasText: "Mock Webhook" }).first();
  await webhookRow.getByRole("button", { name: "删除", exact: true }).click();
  expect(requestedPaths).toContain("DELETE /v1/webhooks/webhook_fixture");
  await expect(page.locator(".capability-section").filter({ hasText: "订阅列表" })).not.toContainText("Mock Webhook");

  await openSettingsSection(page, "学习 / RL");
  await clickSettingsPanelRefresh(page);
  await expect(page.getByText("LEARNING_RL_LOADED")).toBeVisible();
  const configBox = page.locator(".capability-section").filter({ hasText: "RL 配置" }).locator("textarea");
  await configBox.fill("{");
  await page.getByRole("button", { name: "保存配置", exact: true }).click();
  await expect(page.getByText("RL_CONFIG_JSON_INVALID")).toBeVisible();
  await configBox.fill("{\"max_steps\":5}");
  await page.getByRole("button", { name: "保存配置", exact: true }).click();
  await expect(page.locator(".raw-details")).toContainText("updated");
  const proposalRow = page.locator(".job-row").filter({ hasText: "Mock 学习建议" }).first();
  await proposalRow.getByRole("button", { name: "应用", exact: true }).click();
  await expect(page.locator(".raw-details")).toContainText("applied");
  await page.getByRole("button", { name: "启动训练", exact: true }).click();
  await expect(page.locator(".raw-details")).toContainText("rl_fixture_new");
  const runRow = page.locator(".job-row").filter({ hasText: "finance_safe_eval" }).first();
  await runRow.getByRole("button", { name: /详情/ }).click();
  await expect(page.getByText("RL_RUN_DETAIL_LOADED")).toBeVisible();
  await runRow.getByRole("button", { name: "结果", exact: true }).click();
  await expect(page.locator(".raw-details")).toContainText("reward");
  await runRow.getByRole("button", { name: "日志", exact: true }).click();
  await expect(page.locator(".raw-details")).toContainText("mock rl log");
  await runRow.getByRole("button", { name: /停止/ }).click();
  await expect(page.locator(".raw-details")).toContainText("stopped");

  await openSettingsSection(page, "安全扫描");
  await page.getByLabel("文本片段").fill("password=secret\nAIASK_AGENT_CONTROL_TOKEN=token");
  await page.getByRole("button", { name: "运行扫描", exact: true }).click();
  await expect(page.getByText("SECURITY_SCAN_COMPLETED")).toBeVisible();
  await expect(page.locator(".raw-details")).toContainText("[redacted]");
  await expect(page.locator(".raw-details")).not.toContainText("password=secret");
  await expect(page.locator(".raw-details")).not.toContainText("AIASK_AGENT_CONTROL_TOKEN=token");

  await openSettingsSection(page, "股票数据源");
  await expect(page.getByRole("button", { name: /Tushare 主账号/ }).first()).toBeVisible();
  await page.getByRole("button", { name: "测试连接", exact: true }).click();
  await expect(page.getByText(expectedTextLabel("STOCK_DATA_SOURCE_TEST_PASSED"))).toBeVisible();
  await page.getByRole("button", { name: /DuckDuckGo fallback/ }).click();
  await page.getByRole("button", { name: "调用搜索", exact: true }).click();
  await expect(page.getByText(expectedTextLabel("WEB_SEARCH_PASSED"))).toBeVisible();
  await expect(page.locator(".raw-details")).toContainText("[redacted]");
  await expect(page.locator(".raw-details")).not.toContainText("mock-stock-token");

  await openSettingsSection(page, "自动化管理");
  await clickSettingsPanelRefresh(page);
  const managedJobRow = page.locator(".job-row").filter({ hasText: "每日研究监控" }).first();
  await managedJobRow.getByRole("button", { name: /查看任务/ }).click();
  await expect(page.locator(".raw-details").filter({ hasText: "已选任务" })).toContainText("run_job_e2e");
  await managedJobRow.getByRole("button", { name: /运行任务/ }).click();
  await expect(page.locator(".capability-section").filter({ hasText: "运行输出" })).toContainText("job ok");
  await managedJobRow.getByRole("button", { name: /删除任务/ }).click();
  await expect(page.locator(".capability-section").filter({ hasText: "运行输出" })).toContainText("deleted");
});

test("Quant Research workspace explains staged blockers and next actions in mock mode", async ({ page }) => {
  await setupApiMocks(page);
  await openOverview(page);
  await openMainView(page, "Quant Research");
  await expect(page.getByRole("heading", { name: "数据、因子、回测与组合风险" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "阶段结论与下一步" })).toBeVisible();

  await page.getByRole("button", { name: controlLabel("Run research") }).click();
  await expect(page.getByText("RESEARCH_RUN_CREATED")).toBeVisible();
  await expect(page.getByText("research_e2e_quant_1", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("LOCAL_DATABASE_REQUIRED").first()).toBeVisible();
  await expect(page.getByText("配置可写 SQLite 数据库并完成行情同步，然后重新运行研究。")).toBeVisible();
  await expect(page.getByText("数据闸门 原始证据")).toBeVisible();
});

test("Unified control console opens every primary page and exercises safe mock controls", async ({ page }) => {
  test.setTimeout(120_000);
  await setupApiMocks(page);
  await openOverview(page);

  await page.getByRole("button", { name: controlLabel("Sync Agent state") }).click();
  await expect(page.getByText(expectedTextLabel("AIASK_ONLINE")).first()).toBeVisible();
  await setControlToken(page);

  await openMainView(page, "Agent");
  await expect(page.getByRole("heading", { name: "AIASK 工作台" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Sync Agent state") }).click();
  await expect(page.getByText(expectedTextLabel("AIASK_ONLINE")).first()).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Hermes full") }).click();
  await expect(page.getByRole("button", { name: controlLabel("Hermes full") })).toHaveAttribute("aria-pressed", "true");

  await openMainView(page, "Models");
  await expect(page.getByRole("heading", { name: "LLM 提供方、模型获取与测试" })).toBeVisible();
  const providerSection = page.locator(".capability-section").filter({ has: page.getByRole("heading", { name: "已配置提供方" }) });
  await expect(providerSection).toBeVisible();
  await expect(providerSection.locator("strong", { hasText: "openai" }).first()).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText(expectedTextLabel("MODEL_STATUS_LOADED"))).toBeVisible();

  await openMainView(page, "Data & Sync");
  await expect(page.getByRole("heading", { name: "数据库质量与同步审批" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Generate sync plan") }).click();
  await page.getByRole("button", { name: controlLabel("Create approval intent") }).click();
  await expect(page.getByText(expectedTextLabel("SYNC_INTENT_CREATED"))).toBeVisible();

  await openMainView(page, "MCP");
  await expandAdvancedMcpOperations(page);
  await expect(page.getByRole("heading", { name: "连接器评审队列" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Discover or refresh MCP server") }).click();
  await expect(page.locator("body")).toContainText("finance-demo");
  await page.getByPlaceholder(placeholderLabel("resource uri")).fill("aiask://quotes");
  await page.getByRole("button", { name: controlLabel("Read MCP resource") }).click();
  await expect(page.getByText("quote resource ok")).toBeVisible();
  await page.getByPlaceholder(placeholderLabel("prompt name")).fill("risk-review");
  await page.getByRole("button", { name: controlLabel("Get MCP prompt") }).click();
  await expect(page.getByText("risk prompt ok")).toBeVisible();
  await page.getByPlaceholder(placeholderLabel("OAuth server name")).fill("finance-demo");
  await page.getByRole("button", { name: controlLabel("Start MCP OAuth flow") }).click();
  await expect(page.getByText("oauth_required")).toBeVisible();

  await openMainView(page, "Skills");
  await expect(page.getByRole("heading", { name: "已安装 1 个技能" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("risk-review Risk review") }).click();
  await page.getByRole("button", { name: "应用到对话" }).click();
  await expect(page.getByRole("heading", { name: "AIASK 工作台" })).toBeVisible();
  await expect(page.getByPlaceholder(placeholderLabel("Ask AIASK to research, code, inspect tools, or continue a session..."))).toHaveValue(/risk-review/);
  await openSettings(page);
  await page.getByRole("button", { name: "技能管理", exact: true }).click();
  const skillControl = page.locator(".capability-section").filter({ hasText: "安装或更新技能" });
  const skillResult = page.locator(".capability-section").filter({ hasText: "结果" });
  await skillControl.getByRole("textbox").first().fill("e2e-skill");
  await skillControl.getByRole("button", { name: controlLabel("Install"), exact: true }).click();
  await expect(skillResult).toContainText("installed");
  await skillControl.getByRole("button", { name: controlLabel("Update"), exact: true }).click();
  await expect(skillResult).toContainText("updated");
  await skillControl.getByRole("button", { name: controlLabel("Delete"), exact: true }).click();
  await expect(skillResult).toContainText("deleted");

  await openMainView(page, "Automation");
  await expect(page.getByRole("heading", { name: "AI 自动化任务" })).toBeVisible();
  const automationResult = page.locator(".capability-section").filter({ hasText: "运行输出" });
  await page.getByRole("button", { name: controlLabel("Create job") }).click();
  await expect(automationResult).toContainText("created");
  const jobRow = page.locator(".job-row").filter({ hasText: "每日研究监控" });
  await jobRow.getByRole("button", { name: controlLabel("Inspect job 每日研究监控") }).click();
  await jobRow.getByRole("button", { name: controlLabel("Pause job 每日研究监控") }).click();
  await expect(automationResult).toContainText("updated");
  await jobRow.getByRole("button", { name: controlLabel("Run job 每日研究监控") }).click();
  await expect(automationResult).toContainText("completed");
  await expect(jobRow.getByRole("button", { name: controlLabel("Delete") })).toHaveCount(0);

  await openSettings(page);
  await page.getByRole("button", { name: "自动化管理", exact: true }).click();
  await expect(page.getByRole("heading", { name: "自动化管理" }).first()).toBeVisible();
  const managedAutomationResult = page.locator(".capability-section").filter({ hasText: "运行输出" });
  const managedJobRow = page.locator(".job-row").filter({ hasText: "每日研究监控" });
  await expect(managedJobRow.getByRole("button", { name: controlLabel("Delete job 每日研究监控") })).toHaveCount(1);
  await managedJobRow.getByRole("button", { name: controlLabel("Delete job 每日研究监控") }).click();
  await expect(managedAutomationResult).toContainText("deleted");

  await openMainView(page, "Strategy Factory");
  await expect(page.getByRole("heading", { name: "调度器、运行和晋升评审" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Create run intent") }).click();
  await expect(page.getByText(expectedTextLabel("STRATEGY_FACTORY_INTENT_CREATED"))).toBeVisible();

  await openMainView(page, "Factor Factory");
  await expect(page.getByRole("heading", { name: "因子挖掘与活跃池" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Create run intent") }).click();
  await expect(page.getByText(expectedTextLabel("FACTOR_RUN_INTENT_CREATED"))).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Maintenance intent") }).click();
  await expect(page.getByText(expectedTextLabel("FACTOR_MAINTENANCE_INTENT_CREATED"))).toBeVisible();

  await openMainView(page, "Incubation");
  await expect(page.getByRole("heading", { name: "生命周期与命中率控制" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Run intent"), exact: true }).click();
  await expect(page.getByText(expectedTextLabel("INCUBATION_RUN_ONCE_INTENT_CREATED"))).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Dry-run intent") }).click();
  await expect(page.getByText(expectedTextLabel("INCUBATION_DRY_RUN_INTENT_CREATED"))).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Maintenance intent") }).click();
  await expect(page.getByText(expectedTextLabel("INCUBATION_MAINTENANCE_INTENT_CREATED"))).toBeVisible();

  await openMainView(page, "Local User");
  await expect(page.getByRole("heading", { name: "画像与本地数据范围" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "记忆状态" })).toBeVisible();
  await expect(page.getByText("Agent 记忆")).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Save local profile") }).click();
  await expect(page.getByText(expectedTextLabel("LOCAL_PROFILE_SAVED"))).toBeVisible();
  await page.getByPlaceholder(placeholderLabel("Search local sessions, responses, and memory")).fill("AIASK");
  await page.getByRole("button", { name: controlLabel("Search"), exact: true }).click();
  await expect(page.getByText(expectedTextLabel("USER_DATA_SEARCHED"))).toBeVisible();

  await openMainView(page, "Tools");
  await expect(page.getByRole("heading", { name: "可用操作与安全探测" })).toBeVisible();
  await page.getByPlaceholder(placeholderLabel("Search tools")).fill("factory");
  await expect(page.getByText("agent_factory_status")).toBeVisible();

  await openMainView(page, "Capabilities");
  await expect(page.getByRole("heading", { name: "运行时评审", exact: true })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh capability review") }).click();
  await expect(page.getByText("Mock 数据").first()).toBeVisible();
  await openCapabilityTab(page, "Connectors");
  await expect(page.getByRole("heading", { name: "应用绑定与集成" })).toBeVisible();
  await openCapabilityTab(page, "Plugins");
  await expect(page.getByRole("heading", { name: "原生插件与技能包治理" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Test plugin audit-plugin"), exact: true }).click();
  await expect(page.locator(".raw-details").filter({ hasText: "原始插件 payload" })).toContainText("plugin_tool_tested");
  await page.getByRole("button", { name: controlLabel("Disable plugin audit-plugin") }).click();
  await expect(page.locator(".raw-details").filter({ hasText: "原始插件 payload" })).toContainText("plugin_updated");

  await openMainView(page, "Event Console");
  await expect(page.getByRole("heading", { name: "生命周期、风险与孵化事件" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText(expectedTextLabel("EVENTS_LOADED"))).toBeVisible();

  await openMainView(page, "Diagnostics");
  await expect(page.getByRole("heading", { name: "Hermes 原生对齐" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText("系统健康中心")).toBeVisible();

  await openMainView(page, "Agent Status");
  await expect(page.getByRole("heading", { name: "运行状态" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await expect(page.getByText(expectedTextLabel("AGENT_STATUS_LOADED"))).toBeVisible();

  await openMainView(page, "Settings");
  await expect(page.getByRole("heading", { name: "设置中心" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Refresh") }).click();
  await page.getByRole("button", { name: "模型配置", exact: true }).click();
  await expect(page.getByText("进入模型页选择提供方")).toBeVisible();
  await page.getByRole("button", { name: "股票数据源", exact: true }).click();
  await expect(page.getByText("配置行情、K 线、基本面和搜索类数据源")).toBeVisible();
  await expect(page.getByRole("button", { name: /Tushare 主账号/ }).first()).toBeVisible();
  await page.getByRole("button", { name: "测试连接", exact: true }).click();
  await expect(page.getByText(expectedTextLabel("STOCK_DATA_SOURCE_TEST_PASSED"))).toBeVisible();
  await page.getByRole("button", { name: "常规", exact: true }).click();
  await page.getByRole("button", { name: controlLabel("Save profile") }).click();
  await expect(page.locator("label.settings-row").filter({ hasText: "画像名称" }).locator("input")).toHaveValue("E2E 本地操作者");
  await page.getByRole("button", { name: "连接", exact: true }).click();
  await page.getByRole("button", { name: controlLabel("Test connection") }).click();
  await expect(page.getByText(expectedTextLabel("AIASK_ONLINE")).first()).toBeVisible();
  await settingsReturnButton(page).click();
});

test("Full frontend matrix inventories every page, classifies every button, and validates Codex-style layout in mock mode", async ({ page }) => {
  test.setTimeout(180_000);
  await runFullFrontendMatrix(page);
});

async function liveBodyText(page: Page): Promise<string> {
  return page.locator("body").evaluate((body) => (body as HTMLElement).innerText);
}

async function expectLiveBodyToMatch(page: Page, pattern: RegExp, message: string, timeout = 10_000) {
  await expect
    .poll(async () => liveBodyText(page), { message, timeout })
    .toMatch(pattern);
}

async function clickLiveButtonWhenEnabled(page: Page, buttonName: string, timeout = 15_000) {
  const button = page.getByRole("button", { name: controlLabel(buttonName), exact: true });
  await expect(button, `${buttonName} should resolve once`).toHaveCount(1);
  await expect(button, `${buttonName} should be enabled`).toBeEnabled({ timeout });
  await button.click();
}

async function clickLiveButtonIfEnabled(page: Page, buttonName: string) {
  const button = page.getByRole("button", { name: controlLabel(buttonName), exact: true }).first();
  if ((await button.count()) === 0) return false;
  await expect(button).toBeVisible();
  if (await button.isDisabled()) return false;
  await button.click();
  return true;
}

async function clickFirstVisibleButtonContaining(page: Page, text: string) {
  const button = page.getByRole("button").filter({ hasText: text }).first();
  if ((await button.count()) === 0) return false;
  await expect(button).toBeVisible();
  await button.click();
  return true;
}

async function openLastRawEvidencePanel(page: Page) {
  const panels = page.locator("main details.raw-evidence-panel, main details.raw-details");
  const count = await panels.count();
  if (!count) return false;
  const panel = panels.nth(count - 1);
  if ((await panel.getAttribute("open")) === null) {
    await panel.locator("summary").click();
  }
  return true;
}

async function expectNoLiveSecretLeak(page: Page) {
  await expect(page.locator("body")).not.toContainText(/(^|[^A-Za-z0-9_])sk-[A-Za-z0-9_-]{20,}/);
  await expect(page.locator("body")).not.toContainText(/api[_-]?key\s*[:=]\s*[^,\s}]+/i);
}

async function assertLivePageHealth(page: Page, name: string, bodyPattern: RegExp, timeout = 30_000) {
  await openMainView(page, name);
  await expectLiveBodyToMatch(page, bodyPattern, `live ${name} should render expected domain content`, timeout);
  const inventory = await collectMainInventory(page, `Live ${name}`);
  expectCleanInventory(inventory);
  await expectNoLiveSecretLeak(page);
}

async function assertLiveSettingsSectionHealth(page: Page, sectionLabel: string, bodyPattern: RegExp, timeout = 30_000) {
  await openSettings(page);
  const settingsNav = page.getByRole("navigation", { name: "设置导航" });
  const sectionButton = settingsNav.getByRole("button", { name: sectionLabel, exact: true });
  await expect(sectionButton, `settings section ${sectionLabel} should be available`).toHaveCount(1);
  await sectionButton.click();
  await expectLiveBodyToMatch(page, bodyPattern, `live settings section ${sectionLabel} should render expected content`, timeout);
  const inventory = await collectMainInventory(page, `Live Settings / ${sectionLabel}`);
  expectCleanInventory(inventory);
  await expectNoLiveSecretLeak(page);
}

test.describe("optional live desktop smoke", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(process.env.AIASK_DESKTOP_RUN_LIVE !== "1", "set AIASK_DESKTOP_RUN_LIVE=1 and run a real backend on 127.0.0.1:8767");
  test.setTimeout(150_000);

  test("covers real backend model, Hermes, MCP, factory, financial, and status pages", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("main")).toBeVisible();
    const connectButton = page.getByRole("button", { name: controlLabel("Connect") });
    if ((await connectButton.count()) === 1) {
      await connectButton.click();
    }
    const token = process.env.AIASK_AGENT_CONTROL_TOKEN || CONTROL_TOKEN;
    await setControlToken(page, token);

    await openMainView(page, "Capabilities");
    await openCapabilityTab(page, "AI Tests");
    await expect(page.locator(".capability-banner").filter({ hasText: tabLabel("AI Tests") })).toBeVisible();
    await clickLiveButtonWhenEnabled(page, "Run AI Smoke", 30_000);
    await expectLiveBodyToMatch(page, /AI_SMOKE_PASSED|aiask\.ai_smoke|true/, "live AI smoke result should render", 30_000);
    await clickLiveButtonWhenEnabled(page, "List Models", 30_000);
    await expectLiveBodyToMatch(page, /AI_MODELS_LOADED|mock-live-model|aiask_mock|"object":\s*"list"/, "live model list should render", 30_000);
    await expectNoLiveSecretLeak(page);

    await openMainView(page, "Agent");
    await page.getByPlaceholder(placeholderLabel("Ask AIASK to research, code, inspect tools, or continue a session...")).fill("Return exactly AIASK_LIVE_OK.");
    await page.getByRole("button", { name: controlLabel("Run"), exact: true }).click();
    await expectLiveBodyToMatch(page, /AIASK_LIVE_OK|run\.completed|model\.completed/, "live workbench response should render", 45_000);
    await expectNoLiveSecretLeak(page);

    await openMainView(page, "Capabilities");
    await openCapabilityTab(page, "Hermes");
    await expect(page.locator(".capability-section").first()).toBeVisible();
    await expectLiveBodyToMatch(page, /Hermes|agent_[a-z0-9_]+|baseline/i, "live Hermes capability tables should render", 30_000);

    await openMainView(page, "MCP");
    await expectLiveBodyToMatch(page, /MCP|not_registered|discovered|unconfigured|gated/i, "live MCP page should render a clear state", 30_000);
    await clickLiveButtonWhenEnabled(page, "Refresh", 30_000);
    await expectLiveBodyToMatch(page, /CONNECTORS_LOADED|杩炴帴鍣ㄥ凡鍔犺浇|connector|MCP/i, "live MCP connectors should refresh visibly", 30_000);
    const liveConnectorItems = page.locator(".connector-item");
    const liveConnectorCount = await liveConnectorItems.count();
    if (liveConnectorCount > 0) {
      const firstConnector = liveConnectorItems.first();
      const detailButton = firstConnector.getByRole("button", { name: controlLabel("Connector detail"), exact: true });
      if ((await detailButton.count()) === 1 && !(await detailButton.isDisabled())) {
        await detailButton.click();
        await expectLiveBodyToMatch(page, /CONNECTOR_DETAIL_LOADED|杩炴帴鍣ㄨ鎯呭凡鍔犺浇|connector_detail|configured|connected/i, "live connector detail should render", 30_000);
      }
      const testButton = firstConnector.getByRole("button", { name: controlLabel("Connector test"), exact: true });
      if ((await testButton.count()) === 1 && !(await testButton.isDisabled())) {
        await testButton.click();
        await expectLiveBodyToMatch(page, /CONNECTOR_TESTED|连接器测试完成|杩炴帴鍣ㄦ祴璇曞畬鎴?|connector\.test|last_test_status|passed|failed|disconnected|connected|未配置|就绪/i, "live connector test should render", 45_000);
      }
    }
    const ranMcpSmoke = await clickLiveButtonIfEnabled(page, "Run MCP read-only smoke");
    if (ranMcpSmoke) {
      await expectLiveBodyToMatch(page, /MCP_SMOKE_DONE|鍙鍐掔儫娴嬭瘯宸插畬鎴?|success|blocked|failed|\/v1\/mcp\/resources\/read|\/v1\/mcp\/prompts\/get|MCP/i, "live MCP read-only smoke should finish visibly", 45_000);
    }
    await expectNoLiveSecretLeak(page);

    await openMainView(page, "Strategy Factory");
    await expect(page.locator(".capability-card")).toHaveCount(3, { timeout: 30_000 });
    await expectLiveBodyToMatch(page, /strategy_factory|agent_factory_status|CONTROL_TOKEN_REQUIRED|DESKTOP_TOOL_UNAVAILABLE|true|false/, "live Strategy Factory cards should render structured envelopes", 30_000);
    const createdFactoryIntent = await clickLiveButtonIfEnabled(page, "Create run intent");
    if (createdFactoryIntent) {
      await expectLiveBodyToMatch(page, /STRATEGY_FACTORY_INTENT_CREATED|STRATEGY_FACTORY_INTENT_FAILED|factory_run_once|desktop_strategy_factory|intent_id|awaiting_confirmation|CONTROL_TOKEN/i, "live Strategy Factory intent result should render", 30_000);
    }

    await openMainView(page, "Financial Manager");
    await expectLiveBodyToMatch(page, /agent_analyze_stock|stock-analysis|read_only_plus_intents/, "live Financial Manager catalog should expose stock analysis", 30_000);
    await expect(page.getByRole("button", { name: controlLabel("Refresh"), exact: true }).first()).toBeEnabled({ timeout: 30_000 });
    if ((await page.getByLabel("stock analysis code").count()) === 0) {
      expect(await clickFirstVisibleButtonContaining(page, "stock-analysis")).toBe(true);
    }
    await expect(page.getByLabel("stock analysis code")).toBeVisible({ timeout: 30_000 });
    await page.getByLabel("stock analysis code").fill("600519");
    const includeDecision = page.getByLabel("include stock decision");
    if (await includeDecision.isChecked()) {
      await includeDecision.uncheck();
    }
    await page.getByLabel("financial action params").fill(JSON.stringify({
      code: "600519",
      include_decision: false,
      include_financials: false,
      include_kline: false,
      kline_limit: 20
    }, null, 2));
    await clickLiveButtonWhenEnabled(page, "Run query", 20_000);
    await expectLiveBodyToMatch(page, /FINANCIAL_ACTION_OK|FINANCIAL_ACTION_FAILED|INTERNAL_ERROR|agent_analyze_stock|stock-analysis|600519/, "live stock analysis query should render a structured result", 60_000);
    await openLastRawEvidencePanel(page);
    const liveStockSummary = page.getByLabel("stock analysis summary");
    if ((await liveStockSummary.count()) > 0) {
      await expect(liveStockSummary).toBeVisible({ timeout: 30_000 });
      await expectLiveBodyToMatch(page, /600519|agent_analyze_stock|read_only|confirmation_required|not_requested|observe_only/i, "live stock summary should include code, tool, and read-only evidence", 30_000);
    } else {
      await expectLiveBodyToMatch(page, /FINANCIAL_ACTION_FAILED|INTERNAL_ERROR|error_code|availability|agent_analyze_stock|stock-analysis/i, "live stock failure should remain structured and diagnosable", 30_000);
    }
    await expectNoLiveSecretLeak(page);

    await openMainView(page, "Readiness");
    await expectLiveBodyToMatch(page, /AIASK|MCP|Hermes|financial|factory|ready|gated|unconfigured/i, "live readiness and frontend status should render", 30_000);
  });

  test("connects to the real backend and runs the visible AI smoke path", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "AIASK 工作台" })).toBeVisible();
    const connectButton = page.getByRole("button", { name: controlLabel("Connect") });
    if ((await connectButton.count()) === 1) {
      await connectButton.click();
    }
    const token = process.env.AIASK_AGENT_CONTROL_TOKEN || CONTROL_TOKEN;
    await setControlToken(page, token);
    await openSettings(page);
    await page.getByRole("button", { name: "令牌与权限", exact: true }).click();
    await page.locator("label.settings-row").filter({ hasText: "控制令牌" }).locator("input").fill(token);
    await settingsReturnButton(page).click();
    await openMainView(page, "Capabilities");
    await openCapabilityTab(page, "AI Tests");
    await expect(page.locator(".capability-banner").filter({ hasText: "AI 测试" })).toBeVisible();
    await page.getByRole("button", { name: controlLabel("Run AI Smoke") }).click();
    await expect(page.locator(".capability-section").filter({ hasText: "冒烟测试结果" })).toContainText("true", { timeout: 30_000 });
  });

  test("renders the expanded live frontend matrix without layout regressions", async ({ page }) => {
    test.setTimeout(300_000);
    await page.goto("/");
    await expect(page.locator("main")).toBeVisible();
    const connectButton = page.getByRole("button", { name: controlLabel("Connect") });
    if ((await connectButton.count()) === 1) {
      await connectButton.click();
    }
    const token = process.env.AIASK_AGENT_CONTROL_TOKEN || CONTROL_TOKEN;
    await setControlToken(page, token);

    const livePages: Array<{ name: string; pattern: RegExp; timeout?: number }> = [
      { name: "Projects / Contexts", pattern: /Agent|端点|上下文|finance_safe|AIASK/i },
      { name: "Sessions", pattern: /会话|session|消息|full|控制|暂无/i },
      { name: "Runs / Events", pattern: /运行|事件|run|timeline|暂无/i },
      { name: "Approvals", pattern: /审批|意图|approval|intent|工具/i },
      { name: "Finance Lab", pattern: /金融实验室|因子|策略工厂|孵化|数据|接力/i },
      { name: "Market Temperature", pattern: /市场温度|market_temperature|MARKET_TEMPERATURE|数据质量|热行业|冷行业|DESKTOP_TOOL_UNAVAILABLE|INTERNAL_ERROR/i, timeout: 45_000 },
      { name: "Quant Research", pattern: /量化研究|quant|数据|因子|research|SQLite/i },
      { name: "Data & Sync", pattern: /数据|agent_quant_data_gate|同步|新鲜度|DATA_STATUS/i },
      { name: "Factor Factory", pattern: /因子|FACTOR_FACTORY|活跃池|维护|DESKTOP_TOOL_UNAVAILABLE|CONTROL_TOKEN/i, timeout: 45_000 },
      { name: "Incubation", pattern: /INCUBATION_LOADED|孵化状态已加载|INCUBATION_DEGRADED|DESKTOP_TOOL_UNAVAILABLE/i, timeout: 45_000 },
      { name: "Automation", pattern: /自动化|任务|job|cron|JOBS|调度/i },
      { name: "Workflows", pattern: /工作流|workflow|金融|任务|Agent/i },
      { name: "Factory Events", pattern: /工厂事件|雷达|event|outbox|FACTORY|事件/i, timeout: 45_000 },
      { name: "Integrations", pattern: /集成|MCP|Gateway|插件|技能|连接器/i },
      { name: "Skills", pattern: /插件|技能|plugin|skill|受限|就绪/i },
      { name: "Gateway", pattern: /Gateway|平台|daemon|消息|目录|受限|就绪/i },
      { name: "Models", pattern: /模型|provider|AI|status|提供方|mock-live-model/i },
      { name: "Settings", pattern: /设置|Agent 端点|令牌|模型配置|连接/i },
      { name: "Overview", pattern: /总览|运行概览|系统|健康|Agent/i },
      { name: "Coverage Matrix", pattern: /覆盖矩阵|能力|implemented|partial|Hermes/i },
      { name: "Tools", pattern: /工具|agent_|safe|probe|目录/i },
      { name: "Capabilities", pattern: /能力中心|Hermes|MCP|策略工厂|AI 测试/i },
      { name: "Diagnostics", pattern: /诊断|系统健康中心|子系统|终端|Gateway/i },
      { name: "Agent Status", pattern: /智能体|Agent|工具集|状态|健康/i },
      { name: "Local User", pattern: /本地用户|画像|搜索|local|memory|记忆/i },
      { name: "Event Console", pattern: /事件控制台|事件|payload|刷新|event/i }
    ];

    for (const item of livePages) {
      await assertLivePageHealth(page, item.name, item.pattern, item.timeout);
    }

    const settingsSections: Array<{ label: string; pattern: RegExp; timeout?: number }> = [
      { label: "常规", pattern: /默认行为|默认模式|画像名称|本地用户/i },
      { label: "连接", pattern: /Agent 连接|Agent 端点|测试连接|默认本地 Agent/i },
      { label: "令牌与权限", pattern: /令牌与完整模式|API 令牌|控制令牌|完整模式/i },
      { label: "技能管理", pattern: /技能管理|安装或更新技能|已安装|原始技能/i },
      { label: "自动化管理", pattern: /自动化管理|任务|调度|工具集|删除/i },
      { label: "应用集成", pattern: /应用集成|连接器|Gateway|平台|消息/i },
      { label: "Webhook", pattern: /Webhook|订阅|触发|受控/i },
      { label: "插件与技能包", pattern: /插件与技能包|插件|skill pack|技能包/i },
      { label: "模型配置", pattern: /模型配置|提供方|模型|密钥|冒烟测试/i },
      { label: "MCP 管理入口", pattern: /MCP 管理入口|MCP 服务|资源|提示词|OAuth/i },
      { label: "工作流入口", pattern: /工作流入口|数据与同步|策略工厂|因子工厂|孵化/i },
      { label: "股票数据源", pattern: /股票数据源|数据源配置|Tushare|DuckDuckGo|测试连接/i },
      { label: "数据路径", pattern: /数据路径|数据库|Agent|量化|AKShare/i },
      { label: "学习 / RL", pattern: /学习|RL|环境|运行|结果/i },
      { label: "安全扫描", pattern: /安全扫描|扫描|修复建议|环境变量/i },
      { label: "高级诊断入口", pattern: /高级诊断入口|运行概览|工具目录|能力中心|诊断/i },
      { label: "关于", pattern: /关于 AIASK Desktop|Agent HTTP API|桌面端|版本/i }
    ];

    for (const section of settingsSections) {
      await assertLiveSettingsSectionHealth(page, section.label, section.pattern, section.timeout);
    }
  });
});
