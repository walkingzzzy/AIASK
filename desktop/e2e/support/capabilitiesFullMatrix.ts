import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { expect, type Page } from "@playwright/test";
import { API_ORIGIN, setupApiMocks } from "./capabilitiesMockServer";
import {
  assertMainButtonCoverage,
  clickAndRecord,
  collectMainInventory,
  expectDisabledAndRecord,
  recordInventory,
  type MatrixReport,
} from "./capabilitiesInventory";
import {
  CONTROL_TOKEN,
  LEGACY_REPLACEMENT_BUTTONS,
  SETTINGS_STRUCTURE_BUTTONS,
  WORKBENCH_SAFE_PATH_BUTTONS,
  controlLabel,
  expectedTextLabel,
  expandAdvancedMcpOperations,
  openCapabilityTab,
  openMainView,
  openOverview,
  openSettings,
  placeholderLabel,
  settingsReturnButton,
  setControlToken,
} from "./capabilitiesNavigation";

export async function runFullFrontendMatrix(page: Page) {
  await setupApiMocks(page);
  const report: MatrixReport = {
    generated_at: new Date().toISOString(),
    mode: "mock_safe",
    command_results: [
      "npm.cmd run typecheck: run separately by acceptance workflow",
      "npm.cmd test: run separately by acceptance workflow",
      "npm.cmd run test:e2e:mock: this matrix is part of the mock suite"
    ],
    pages: [],
    actions: [],
    gated: [],
    layout: [],
    screenshots: [],
    assumptions: [
      "Mock API intercepts all http://127.0.0.1:8767 calls.",
      "State-changing controls are clicked only against the mock backend.",
      "Live Agent validation is limited to the optional read-only smoke test."
    ]
  };
  const reportDir = path.join(process.cwd(), "test-results", "full-frontend");
  await mkdir(reportDir, { recursive: true });

  await page.setViewportSize({ width: 1440, height: 960 });
  await openOverview(page);

  await page.screenshot({ path: path.join(reportDir, "desktop-workbench.png"), fullPage: true });
  report.screenshots.push(path.join(reportDir, "desktop-workbench.png"));

  const workbenchInventory = await recordInventory(report, page, "Workbench");
  await expect(page.getByRole("region", { name: "金融 Agent 安全链路" })).toBeVisible();
  await expect(page.getByText("现在可以复核什么")).toBeVisible();
  report.actions.push({ page: "Workbench", control: "金融 Agent 安全链路", result: "visible", note: "Workbench surfaces read-only mode, MCP, memory, financial manager, data, and factory navigation" });
  await clickAndRecord(report, page, "Workbench", "Sync Agent state", "AIASK_ONLINE");
  assertMainButtonCoverage(workbenchInventory, [
    "Sync Agent state",
    "Finance safe mode",
    "Finance safe",
    "Hermes full",
    "Run thread task",
    "打开会话：E2E session 已完成 · 2026-05-21 16:00",
    "查看运行：运行已完成 工具 0 次 · 审批 0 项 · 错误 0 个",
    ...WORKBENCH_SAFE_PATH_BUTTONS,
    "准备度",
    "Readiness",
    "Projects / Contexts",
    "Approvals",
    "Finance Lab",
    "Integrations",
    "Gateway",
    "Gateway gated",
    "Gateway 受限",
    "Plugins / Skills gated",
    "扩展 内部",
    "Extensions internal",
    "Open evidence",
    "source_e2e_run",
  ]);

  await openMainView(page, "Data & Sync");
  await page.getByRole("button", { name: controlLabel("Generate sync plan") }).click();
  await expect(page.getByText(expectedTextLabel("SYNC_PLAN_READY"))).toBeVisible();
  report.actions.push({ page: "Data & Sync gated", control: "Generate sync plan", result: "clicked", note: "plan generated without write intent" });
  await expectDisabledAndRecord(report, page, "Data & Sync gated", "Create approval intent", "control token required");

  await openMainView(page, "MCP");
  await expandAdvancedMcpOperations(page);
  await expectDisabledAndRecord(report, page, "MCP gated", "Register local MCP server", "control token required or already registered");
  await expectDisabledAndRecord(report, page, "MCP gated", "Discover or refresh MCP server", "control token required");
  await expectDisabledAndRecord(report, page, "MCP gated", "Run MCP read-only smoke", "control token required");
  await expectDisabledAndRecord(report, page, "MCP gated", "Read MCP resource", "control token and resource uri required");
  await expectDisabledAndRecord(report, page, "MCP gated", "Get MCP prompt", "control token and prompt name required");
  await expectDisabledAndRecord(report, page, "MCP gated", "Start MCP OAuth flow", "control token and server required");

  await openMainView(page, "Finance Lab");
  await expect(page.getByRole("heading", { name: "工厂接力总览" })).toBeVisible();
  await expect(page.locator("body")).toContainText("因子工厂");
  await expect(page.locator("body")).toContainText("策略工厂");
  await expect(page.locator("body")).toContainText("孵化工厂");

  await openMainView(page, "Skills");
  await expect(page.getByText("需要控制令牌", { exact: false }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: controlLabel("Install"), exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: controlLabel("Update"), exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: controlLabel("Delete"), exact: true })).toHaveCount(0);
  report.gated.push(
    { page: "Skills gated", control: "Install", result: "absent", note: "control form hidden until authorized" },
    { page: "Skills gated", control: "Update", result: "absent", note: "control form hidden until authorized" },
    { page: "Skills gated", control: "Delete", result: "absent", note: "control form hidden until authorized" }
  );

  await openMainView(page, "Capabilities");
  await openCapabilityTab(page, "Plugins");
  await expect(page.getByRole("button", { name: controlLabel("Disable"), exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: controlLabel("Test tool"), exact: true })).toHaveCount(0);
  report.gated.push(
    { page: "Plugins gated", control: "Disable", result: "absent", note: "plugin rows hidden until authorized" },
    { page: "Plugins gated", control: "Test tool", result: "absent", note: "plugin rows hidden until authorized" }
  );

  await setControlToken(page);

  await openMainView(page, "Agent");
  const agentInventory = await recordInventory(report, page, "Agent");
  await clickAndRecord(report, page, "Agent", "Sync Agent state", "AIASK_ONLINE");
  await clickAndRecord(report, page, "Agent", "Hermes full");
  await page.getByPlaceholder(placeholderLabel("Ask AIASK to research, code, inspect tools, or continue a session...")).fill("请只回复 AIASK_OK");
  await clickAndRecord(report, page, "Agent", "Run", "AIASK_OK");
  await clickAndRecord(report, page, "Agent inspector", "Load run events for selected task", "run.completed");
  assertMainButtonCoverage(agentInventory, [
    "Sync Agent state",
    "Finance safe mode",
    "Finance safe",
    "Hermes full",
    "Hermes full mode",
    "Run thread task",
    "打开会话：E2E session 已完成 · 2026-05-21 16:00",
    "查看运行：运行已完成 工具 0 次 · 审批 0 项 · 错误 0 个",
    ...WORKBENCH_SAFE_PATH_BUTTONS,
    "准备度",
    "Readiness",
    "Projects / Contexts",
    "Approvals",
    "Finance Lab",
    "Integrations",
    "Gateway",
    "Gateway ready",
    "Gateway 就绪",
    "插件 / 技能 就绪",
    "扩展 内部",
    "Extensions internal",
    "Open evidence",
    "source_e2e_run",
  ]);

  await openMainView(page, "Models");
  const modelsInventory = await recordInventory(report, page, "Models");
  const matrixProviderSection = page.locator(".capability-section").filter({ has: page.getByRole("heading", { name: "已配置提供方" }) });
  await expect(matrixProviderSection).toBeVisible();
  await expect(matrixProviderSection.locator("strong", { hasText: "openai" }).first()).toBeVisible();
  report.actions.push({ page: "Models", control: "Provider status", result: "visible", note: "modelProviderStatus payload visible" });
  await clickAndRecord(report, page, "Models", "Refresh", "MODEL_STATUS_LOADED");
  await clickAndRecord(report, page, "Models", "获取模型", "MODELS_LOADED");
  await clickAndRecord(report, page, "Models", "测试模型", "AIASK model smoke ok.");
  assertMainButtonCoverage(modelsInventory, ["Refresh", "保存配置", "获取模型", "测试模型"], {
    allowedPrefixes: [
      "OpenAI",
      "DeepSeek",
      "通义千问 / DashScope 北京",
      "Qwen / DashScope 美国弗吉尼亚",
      "Anthropic Claude",
      "自定义 OpenAI 兼容",
      "本地 Mock"
    ]
  });

  await openMainView(page, "Readiness");
  const readinessInventory = await recordInventory(report, page, "Readiness");
  await expect(page.getByRole("heading", { name: "真实金融流程前置检查" })).toBeVisible();
  await expect(page.getByText("1. 模式与模型")).toBeVisible();
  await expect(page.getByText("2. MCP 与连接器")).toBeVisible();
  await expect(page.getByText("3. 记忆与搜索")).toBeVisible();
  await expect(page.getByText("4. 金融 Agent 流程")).toBeVisible();
  await expect(page.getByText("5. 数据与量化研究")).toBeVisible();
  await expect(page.getByText("6. 工厂接力")).toBeVisible();
  report.actions.push({ page: "Readiness", control: "运行前检查", result: "visible", note: "mode, MCP, memory, financial agent, data, and factory relay path visible" });
  assertMainButtonCoverage(readinessInventory, [
    "Refresh",
    "刷新完整控制台"
  ], {
    allowedPrefixes: [
      "前往",
      "打开设置",
      "打开MCP / 连接器",
      "打开本地用户 / 记忆",
      "打开金融经理台",
      "打开数据",
      "打开金融实验室"
    ]
  });

  await openMainView(page, "Data & Sync");
  const dataInventory = await recordInventory(report, page, "Data & Sync");
  await expect(page.getByRole("heading", { name: "数据闸门复核" })).toBeVisible();
  await expect(page.locator("strong", { hasText: "agent_quant_data_gate" }).first()).toBeVisible();
  report.actions.push({ page: "Data & Sync", control: "Data gate evidence", result: "visible", note: "agent_quant_data_gate read-only result visible" });
  await page.locator("label.field-row").filter({ hasText: "证券代码" }).locator("textarea").fill("600519, 000001");
  await clickAndRecord(report, page, "Data & Sync", "Refresh", "DATA_STATUS_LOADED");
  await clickAndRecord(report, page, "Data & Sync", "Generate sync plan", "SYNC_PLAN_READY");
  const dataInventoryWithPlan = await collectMainInventory(page, "Data & Sync with plan");
  await clickAndRecord(report, page, "Data & Sync", "Create approval intent", "SYNC_INTENT_CREATED");
  assertMainButtonCoverage(dataInventoryWithPlan, ["Refresh", "Generate sync plan", "Create approval intent"]);
  assertMainButtonCoverage(dataInventory, ["Refresh", "Generate sync plan"]);

  await openMainView(page, "Financial Manager");
  const financialManagerInventory = await recordInventory(report, page, "Financial Manager");
  await expect(page.getByRole("heading", { name: "金融 Agent 只读工作流" })).toBeVisible();
  await clickAndRecord(report, page, "Financial Manager", "Run read-only workflow", "FINANCIAL_WORKFLOW_DONE");
  await expect(page.getByText("agent_portfolio_risk").first()).toBeVisible();
  await expect(page.getByText("agent_analyze_stock").first()).toBeVisible();
  await expect(page.getByText("agent_quant_data_gate").first()).toBeVisible();
  await expect(page.getByText("agent_session_search").first()).toBeVisible();
  await expect(page.getByText("agent_memory_search").first()).toBeVisible();
  await expect(page.locator("body")).toContainText("AIASK_OK search result");
  await expect(page.locator("body")).toContainText("mock memory hit");
  await expect(page.locator("body")).toContainText("quote resource ok");
  await expect(page.locator("body")).toContainText("risk prompt ok");
  report.actions.push({ page: "Financial Manager", control: "Read-only Agent workflow evidence", result: "visible", note: "portfolio, quant, session search, memory search, and MCP evidence visible" });
  await page.getByRole("button", { name: "市场与研究", exact: true }).click();
  await page.getByRole("button", { name: /个股分析/ }).click();
  await page.getByLabel("stock analysis code").fill("300750");
  await page.getByLabel("include stock decision").check();
  await clickAndRecord(report, page, "Financial Manager", "Run query", "mock_watch");
  await expect(page.locator("body")).toContainText("300750");
  await expect(page.locator("body")).toContainText("observe_only");
  const stockSummary = page.getByLabel("stock analysis summary");
  const stockSummaryValues = await stockSummary.locator(".metric-card strong").filter({ hasText: /mock_watch|observe_only/ }).all();
  expect(stockSummaryValues).toHaveLength(2);
  for (const value of stockSummaryValues) {
    const box = await value.evaluate((element) => {
      const style = window.getComputedStyle(element);
      const lineHeight = Number.parseFloat(style.lineHeight);
      return { height: element.getBoundingClientRect().height, lineHeight: Number.isFinite(lineHeight) ? lineHeight : 24 };
    });
    expect(box.height).toBeLessThan(box.lineHeight * 1.35);
  }
  report.actions.push({ page: "Financial Manager", control: "Stock analysis query", result: "visible", note: "agent_analyze_stock read-only query accepts a stock code and renders summary evidence" });
  assertMainButtonCoverage(financialManagerInventory, ["Refresh", "Run read-only workflow", "Run query"], {
    allowedPrefixes: ["总览", "市场与研究", "风险与绩效", "组合与自选", "券商只读", "组合风险", "个股分析", "量化数据门禁", "创建组合意图", "实盘下单"]
  });

  await openMainView(page, "MCP");
  const mcpInventory = await recordInventory(report, page, "MCP");
  await clickAndRecord(report, page, "MCP", "Refresh", "连接器已加载");
  const firstConnector = page.locator(".connector-item").first();
  await firstConnector.getByRole("button", { name: controlLabel("Connector detail"), exact: true }).click();
  await expect(page.locator("body")).toContainText("连接器详情已加载");
  report.actions.push({ page: "MCP", control: "Connector detail", result: "clicked", note: "连接器详情已加载" });
  await firstConnector.getByRole("button", { name: controlLabel("Connector test"), exact: true }).click();
  await expect(page.locator("body")).toContainText("连接器测试完成");
  report.actions.push({ page: "MCP", control: "Connector test", result: "clicked", note: "连接器测试完成" });
  await expandAdvancedMcpOperations(page);
  await expectDisabledAndRecord(report, page, "MCP", "Register local MCP server", "already registered in mock");
  await clickAndRecord(report, page, "MCP", "Discover or refresh MCP server", "finance-demo");
  await clickAndRecord(report, page, "MCP", "Run MCP read-only smoke", "只读冒烟测试已完成");
  await expect(page.locator("body")).toContainText("quote resource ok");
  await expect(page.locator("body")).toContainText("risk prompt ok");
  await page.getByPlaceholder(placeholderLabel("resource uri")).fill("aiask://quotes");
  await clickAndRecord(report, page, "MCP", "Read MCP resource", "quote resource ok");
  await page.getByPlaceholder(placeholderLabel("prompt name")).fill("risk-review");
  await clickAndRecord(report, page, "MCP", "Get MCP prompt", "risk prompt ok");
  await page.getByPlaceholder(placeholderLabel("OAuth server name")).fill("finance-demo");
  await clickAndRecord(report, page, "MCP", "Start MCP OAuth flow", "oauth_required");
  assertMainButtonCoverage(mcpInventory, [
    "Refresh",
    "Connector detail",
    "Connector test",
    "Register local MCP server",
    "Discover or refresh MCP server",
    "Run MCP read-only smoke",
    "Read MCP resource",
    "Get MCP prompt",
    "Start MCP OAuth flow",
    "Reauthorize"
  ]);

  await openMainView(page, "Skills");
  const skillsInventory = await recordInventory(report, page, "Skills");
  await clickAndRecord(report, page, "Skills", "risk-review Risk review");
  await page.getByRole("button", { name: "应用到对话" }).click();
  await expect(page.getByPlaceholder(placeholderLabel("Ask AIASK to research, code, inspect tools, or continue a session..."))).toHaveValue(/risk-review/);
  report.actions.push({ page: "Skills", control: "应用到对话", result: "clicked", note: "recommended prompt copied to composer" });
  assertMainButtonCoverage(skillsInventory, [
    "Refresh",
    "risk-review Risk review",
    "应用到对话",
    "Install",
    "Update",
    "Delete",
    "Disable plugin audit-plugin",
    "Configure plugin audit-plugin",
    "Test plugin audit-plugin",
    "Test first plugin tool audit-plugin",
    "Load commands for plugin audit-plugin",
    "Save plugin"
  ]);

  await openSettings(page);
  await page.getByRole("button", { name: "技能管理", exact: true }).click();
  const skillsManagementInventory = await recordInventory(report, page, "Skills management");
  const skillSection = page.locator(".capability-section").filter({ hasText: "安装或更新技能" });
  await skillSection.getByRole("textbox").first().fill("e2e-skill");
  await clickAndRecord(report, page, "Skills management", "Install", "installed");
  await clickAndRecord(report, page, "Skills management", "Update", "updated");
  await clickAndRecord(report, page, "Skills management", "Delete", "deleted");
  assertMainButtonCoverage(skillsManagementInventory, ["Refresh", "risk-review Risk review", "Install", "Update", "Delete"], {
    structural: SETTINGS_STRUCTURE_BUTTONS
  });

  await openMainView(page, "Automation");
  const automationInventory = await recordInventory(report, page, "Automation");
  await clickAndRecord(report, page, "Automation", "Refresh", "JOBS_LOADED");
  await clickAndRecord(report, page, "Automation", "Create job", "created");
  const jobRow = page.locator(".job-row").filter({ hasText: "每日研究监控" });
  await clickAndRecord(report, page, "Automation", "Inspect job 每日研究监控", "每日研究监控", jobRow);
  await clickAndRecord(report, page, "Automation", "Pause job 每日研究监控", "updated", jobRow);
  await clickAndRecord(report, page, "Automation", "Run job 每日研究监控", "completed", jobRow);
  await expect(jobRow.getByRole("button", { name: controlLabel("Delete") })).toHaveCount(0);
  assertMainButtonCoverage(automationInventory, ["Refresh", "Create job", "Inspect job 每日研究监控", "Pause job 每日研究监控", "Run job 每日研究监控"]);

  await openSettings(page);
  await page.getByRole("button", { name: "自动化管理", exact: true }).click();
  const automationManagementInventory = await recordInventory(report, page, "Automation management");
  const managedJobRow = page.locator(".job-row").filter({ hasText: "每日研究监控" });
  await clickAndRecord(report, page, "Automation management", "Delete job 每日研究监控", "deleted", managedJobRow);
  assertMainButtonCoverage(automationManagementInventory, ["Refresh", "Create job", "Inspect job 每日研究监控", "Pause job 每日研究监控", "Run job 每日研究监控", "Delete job 每日研究监控"], {
    structural: SETTINGS_STRUCTURE_BUTTONS
  });

  await openMainView(page, "Finance Lab");
  await expect(page.locator("body")).toContainText(expectedTextLabel("FACTORY_RELAY_LOADED"));
  const financeLabInventory = await recordInventory(report, page, "Finance Lab");
  await page.getByLabel(/我确认本次只读测试可读取/).check();
  await clickAndRecord(report, page, "Finance Lab", "Sync QMT read-only", "BROKER_SYNCED");
  await clickAndRecord(report, page, "Finance Lab", "刷新接力状态", "FACTORY_RELAY_LOADED");
  await expect(page.locator("body")).toContainText("20d momentum");
  await expect(page.locator("body")).toContainText("risk-review");
  await expect(page.locator("body")).toContainText("completed");
  assertMainButtonCoverage(financeLabInventory, [
    "Sync QMT read-only",
    "检查环境",
    "运行只读测试并生成分析",
    "刷新接力状态",
    "查看因子池",
    "打开策略评审",
    "查看孵化看板",
    "打开因子工厂",
    "打开策略工厂",
    "打开孵化工厂",
    "财务管理",
    "量化研究",
    "策略工厂",
    "因子工厂",
    "孵化工厂",
    "数据",
    "事件工厂",
    "市场温度",
    "工作流",
    "事件工厂"
  ], {
    allowedPrefixes: ["QMT / MiniQMT", "同花顺"]
  });
  await clickAndRecord(report, page, "Finance Lab", "查看因子池", "因子挖掘与活跃池");

  await openMainView(page, "Market Temperature");
  await expect(page.getByRole("heading", { name: "缓存就绪" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "前向验证" })).toBeVisible();
  await expect(page.locator("main")).not.toContainText("Cache readiness");
  const marketTemperatureInventory = await recordInventory(report, page, "Market Temperature");
  await clickAndRecord(report, page, "Market Temperature", "Update snapshot", "MARKET_TEMPERATURE_LOADED");
  assertMainButtonCoverage(marketTemperatureInventory, ["Refresh", "Update snapshot"]);

  await openMainView(page, "Strategy Factory");
  const strategyInventory = await recordInventory(report, page, "Strategy Factory");
  await clickAndRecord(report, page, "Strategy Factory", "Refresh capability review", "Mock 数据");
  await clickAndRecord(report, page, "Strategy Factory", "Create run intent", "STRATEGY_FACTORY_INTENT_CREATED");
  await expect(page.locator("[aria-label='strategy factory intent summary']")).toContainText("intent_e2e_approved_path");
  await expect(page.locator("[aria-label='strategy factory intent summary']")).toContainText("agent_action_intent_create");
  assertMainButtonCoverage(strategyInventory, ["Refresh capability review", "Create run intent"], {
    structural: ["Overview", "Coverage Matrix", "Connectors", "Hermes", "MCP", "Strategy Factory", "Incubation", "Skills", "Plugins", "AI Tests"]
  });

  await openMainView(page, "Factor Factory");
  const factorInventory = await recordInventory(report, page, "Factor Factory");
  await clickAndRecord(report, page, "Factor Factory", "Refresh", "FACTOR_FACTORY_LOADED");
  await clickAndRecord(report, page, "Factor Factory", "Create run intent", "FACTOR_RUN_INTENT_CREATED");
  await clickAndRecord(report, page, "Factor Factory", "Maintenance intent", "FACTOR_MAINTENANCE_INTENT_CREATED");
  assertMainButtonCoverage(factorInventory, ["Refresh", "Create run intent", "Maintenance intent"]);

  await openMainView(page, "Incubation");
  const incubationInventory = await recordInventory(report, page, "Incubation");
  await clickAndRecord(report, page, "Incubation", "Refresh", "INCUBATION_LOADED");
  await clickAndRecord(report, page, "Incubation", "Run intent", "INCUBATION_RUN_ONCE_INTENT_CREATED");
  await clickAndRecord(report, page, "Incubation", "Dry-run intent", "INCUBATION_DRY_RUN_INTENT_CREATED");
  await clickAndRecord(report, page, "Incubation", "Maintenance intent", "INCUBATION_MAINTENANCE_INTENT_CREATED");
  assertMainButtonCoverage(incubationInventory, ["Refresh", "Run intent", "Dry-run intent", "Maintenance intent"]);

  await openMainView(page, "Factory Events");
  await page.getByRole("tab", { name: "雷达", exact: true }).click();
  await expect(page.getByRole("heading", { name: "股票雷达观察池" })).toBeVisible();
  await expect(page.locator("strong", { hasText: "北方稀土" }).first()).toBeVisible();
  const factoryEventsRadarInventory = await recordInventory(report, page, "Factory Events / Radar");
  await clickAndRecord(report, page, "Factory Events / Radar", "Refresh radar", "RADAR_LOADED");
  await clickAndRecord(report, page, "Factory Events / Radar", "Create radar run intent", "股票雷达运行 意图");
  await expect(page.getByRole("button", { name: controlLabel("Create radar run intent"), exact: true })).toBeEnabled();
  await clickAndRecord(report, page, "Factory Events / Radar", "Create radar push preview intent", "股票雷达推送预览 意图");
  await expect(page.getByRole("button", { name: controlLabel("Create radar push preview intent"), exact: true })).toBeEnabled();
  await clickAndRecord(report, page, "Factory Events / Radar", "Create radar schedule intent", "股票雷达调度预览 意图");
  await page.getByRole("tab", { name: "事件", exact: true }).click();
  await expect(page.getByRole("heading", { name: "当前生效的事件注入" })).toBeVisible();
  await page.getByRole("button", { name: controlLabel("Pause"), exact: true }).click();
  await expect(page.getByRole("heading", { name: "最近意图派发" })).toBeVisible();
  await expect(page.locator("main")).toContainText("意图 intent_e2e_approved_path 已确认");
  assertMainButtonCoverage(factoryEventsRadarInventory, [
    "Refresh",
    "刷新状态",
    "初始化 Bootstrap",
    "刷新暴露",
    "排空 outbox",
    "运行回归",
    "Refresh radar",
    "Create radar run intent",
    "Create radar push preview intent",
    "Create radar schedule intent"
  ], {
    structural: ["雷达", "事件", "创建", "预览", "血缘"]
  });

  await openMainView(page, "Local User");
  const userInventory = await recordInventory(report, page, "Local User");
  await expect(page.getByRole("heading", { name: "记忆状态" })).toBeVisible();
  report.actions.push({ page: "Local User", control: "Memory status", result: "visible", note: "memoryStatus payload visible" });
  await clickAndRecord(report, page, "Local User", "Refresh", "LOCAL_PROFILE_LOADED");
  await clickAndRecord(report, page, "Local User", "Save local profile", "LOCAL_PROFILE_SAVED");
  await expectDisabledAndRecord(report, page, "Local User", "Search", "query required");
  await page.getByPlaceholder(placeholderLabel("Search local sessions, responses, and memory")).fill("AIASK");
  await clickAndRecord(report, page, "Local User", "Search", "USER_DATA_SEARCHED");
  await clickAndRecord(report, page, "Local User", "Preview Export/Delete", "USER_DATA_EXPORT_PREVIEWED");
  await clickAndRecord(report, page, "Local User", "Preview Aggregate Governance", "AGGREGATE_GOVERNANCE_PREVIEWED");
  assertMainButtonCoverage(userInventory, ["Refresh", "Load messages", "Save local profile", "Search", "Preview Export/Delete", "Preview Aggregate Governance"], {
    structural: LEGACY_REPLACEMENT_BUTTONS
  });

  await openMainView(page, "Tools");
  const toolsInventory = await recordInventory(report, page, "Tools");
  await page.getByPlaceholder(placeholderLabel("Search tools")).fill("factory");
  await expect(page.getByText("agent_factory_status")).toBeVisible();
  report.actions.push({ page: "Tools", control: "Search tools input", result: "typed", note: "agent_factory_status visible" });
  assertMainButtonCoverage(toolsInventory, [], {
    allowedPrefixes: ["Fill example for agent_", "Run safe probe for agent_"],
    structural: LEGACY_REPLACEMENT_BUTTONS
  });

  await openMainView(page, "Capabilities");
  const capabilitiesInventory = await recordInventory(report, page, "Capabilities");
  await clickAndRecord(report, page, "Capabilities", "Refresh capability review", "Mock 数据");
  assertMainButtonCoverage(capabilitiesInventory, ["Refresh capability review"], {
    structural: ["Overview", "Coverage Matrix", "Connectors", "Hermes", "MCP", "Strategy Factory", "Incubation", "Skills", "Plugins", "AI Tests"]
  });

  await openCapabilityTab(page, "Connectors");
  const connectorsInventory = await recordInventory(report, page, "Capabilities / Connectors");
  await clickAndRecord(report, page, "Capabilities / Connectors", "Refresh connectors", "CONNECTORS_LOADED");
  assertMainButtonCoverage(connectorsInventory, ["Refresh connectors"], {
    structural: ["Refresh capability review", "Overview", "Coverage Matrix", "Connectors", "Hermes", "MCP", "Strategy Factory", "Incubation", "Skills", "Plugins", "AI Tests"]
  });

  await openCapabilityTab(page, "Hermes");
  const hermesInventory = await recordInventory(report, page, "Capabilities / Hermes");
  await page.locator(".capability-section").filter({ hasText: "Hermes 工具映射" }).getByPlaceholder(placeholderLabel("Search area, tool, platform...")).fill("discord_server");
  await expect(page.getByText("agent_discord_server").first()).toBeVisible();
  report.actions.push({ page: "Capabilities / Hermes", control: "Hermes search and status filters", result: "typed", note: "agent_discord_server visible" });
  assertMainButtonCoverage(hermesInventory, [], {
    structural: ["Refresh capability review", "Overview", "Coverage Matrix", "Connectors", "Hermes", "MCP", "Strategy Factory", "Incubation", "Skills", "Plugins", "AI Tests"]
  });

  await openCapabilityTab(page, "Plugins");
  const pluginsInventory = await recordInventory(report, page, "Capabilities / Plugins");
  await clickAndRecord(report, page, "Capabilities / Plugins", "Test plugin audit-plugin");
  await expect(page.locator(".raw-details").filter({ hasText: "原始插件 payload" })).toContainText("plugin_tool_tested");
  await clickAndRecord(report, page, "Capabilities / Plugins", "Disable plugin audit-plugin");
  await expect(page.locator(".raw-details").filter({ hasText: "原始插件 payload" })).toContainText("plugin_updated");
  assertMainButtonCoverage(pluginsInventory, [
    "Disable plugin audit-plugin",
    "Configure plugin audit-plugin",
    "Test plugin audit-plugin",
    "Test first plugin tool audit-plugin",
    "Load commands for plugin audit-plugin",
    "Save plugin"
  ], {
    structural: ["Refresh capability review", "Overview", "Coverage Matrix", "Connectors", "Hermes", "MCP", "Strategy Factory", "Incubation", "Skills", "Plugins", "AI Tests"]
  });

  await openCapabilityTab(page, "AI Tests");
  const aiTestsInventory = await recordInventory(report, page, "Capabilities / AI Tests");
  await clickAndRecord(report, page, "Capabilities / AI Tests", "Refresh");
  await expect(page.getByRole("heading", { name: "gpt-5.4" })).toBeVisible();
  await clickAndRecord(report, page, "Capabilities / AI Tests", "Run AI Smoke", "AI_SMOKE_PASSED");
  await clickAndRecord(report, page, "Capabilities / AI Tests", "List Models", "AI_MODELS_LOADED");
  assertMainButtonCoverage(aiTestsInventory, ["Refresh", "Run AI Smoke", "List Models"], {
    structural: ["Refresh capability review", "Overview", "Coverage Matrix", "Connectors", "Hermes", "MCP", "Strategy Factory", "Incubation", "Skills", "Plugins", "AI Tests"]
  });

  await openMainView(page, "Event Console");
  const eventInventory = await recordInventory(report, page, "Event Console");
  await page.getByPlaceholder(placeholderLabel("payload text")).fill("mock");
  await clickAndRecord(report, page, "Event Console", "Refresh", "EVENTS_LOADED");
  assertMainButtonCoverage(eventInventory, ["Refresh"], {
    structural: LEGACY_REPLACEMENT_BUTTONS
  });

  await openMainView(page, "Diagnostics");
  await clickAndRecord(report, page, "Diagnostics", "Refresh", "系统健康中心");
  await page.locator(".subsystem-row").filter({ has: page.locator("summary", { hasText: "终端" }) }).locator("summary").click();
  await expect(page.getByText("local-powershell").first()).toBeVisible();
  const diagnosticsInventory = await recordInventory(report, page, "Diagnostics");
  await clickAndRecord(report, page, "Diagnostics", "Load terminal sessions", "TERMINAL_BACKEND_SESSIONS_LOADED");
  assertMainButtonCoverage(diagnosticsInventory, ["Refresh", "Load terminal sessions"], {
    structural: LEGACY_REPLACEMENT_BUTTONS
  });

  await openMainView(page, "Agent Status");
  const agentStatusInventory = await recordInventory(report, page, "Agent Status");
  await clickAndRecord(report, page, "Agent Status", "Refresh", "AGENT_STATUS_LOADED");
  assertMainButtonCoverage(agentStatusInventory, ["Refresh"], {
    structural: LEGACY_REPLACEMENT_BUTTONS
  });

  await openMainView(page, "Settings");
  const settingsInventory = await recordInventory(report, page, "Settings");
  await page.getByRole("button", { name: "连接", exact: true }).click();
  await page.locator("label.settings-row").filter({ hasText: "Agent 端点" }).locator("input").fill(API_ORIGIN);
  await page.getByRole("button", { name: "令牌与权限", exact: true }).click();
  await page.locator("label.settings-row").filter({ hasText: "API 令牌" }).locator("input").fill("api-token-mock");
  await page.locator("label.settings-row").filter({ hasText: "控制令牌" }).locator("input").fill(CONTROL_TOKEN);
  await clickAndRecord(report, page, "Settings", "Refresh");
  await page.getByRole("button", { name: "模型配置", exact: true }).click();
  await expect(page.getByText("进入模型页选择提供方")).toBeVisible();
  await page.getByRole("button", { name: "股票数据源", exact: true }).click();
  const stockDataSourcesInventory = await recordInventory(report, page, "Settings / Stock data sources");
  await expect(page.getByRole("button", { name: /Tushare 主账号/ }).first()).toBeVisible();
  await clickAndRecord(report, page, "Settings / Stock data sources", "测试连接", expectedTextLabel("STOCK_DATA_SOURCE_TEST_PASSED"));
  await page.getByRole("button", { name: /DuckDuckGo fallback/ }).click();
  await clickAndRecord(report, page, "Settings / Stock data sources", "调用搜索", expectedTextLabel("WEB_SEARCH_PASSED"));
  assertMainButtonCoverage(stockDataSourcesInventory, ["Refresh", "打开官方文档", "保存数据源", "测试连接", "调用搜索"], {
    structural: SETTINGS_STRUCTURE_BUTTONS,
    allowedPrefixes: ["AKShare / AKTools", "Tushare Pro", "TongDaXin HQ", "DuckDuckGo HTML Search", "Tavily Search", "E2E AKShare", "Tushare 主账号", "DuckDuckGo fallback"]
  });
  await page.getByRole("button", { name: "常规", exact: true }).click();
  await clickAndRecord(report, page, "Settings", "Save profile");
  await expect(page.locator("label.settings-row").filter({ hasText: "画像名称" }).locator("input")).toHaveValue("E2E 本地操作者");
  await page.getByRole("button", { name: "连接", exact: true }).click();
  await clickAndRecord(report, page, "Settings", "Test connection", "AIASK_ONLINE");
  assertMainButtonCoverage(settingsInventory, ["Refresh", "Reset endpoint to default Agent endpoint", "Save profile", "Test connection"], {
    structural: SETTINGS_STRUCTURE_BUTTONS
  });
  await settingsReturnButton(page).click();

  await page.setViewportSize({ width: 980, height: 760 });
  await openMainView(page, "Overview");
  const narrowOverview = await recordInventory(report, page, "Overview narrow");
  assertMainButtonCoverage(narrowOverview, ["Refresh"]);
  await page.screenshot({ path: path.join(reportDir, "narrow-overview.png"), fullPage: true });
  report.screenshots.push(path.join(reportDir, "narrow-overview.png"));

  await writeFile(path.join(reportDir, "playwright-full-matrix-report.json"), JSON.stringify(report, null, 2), "utf8");
}
