import { expect, type Page } from "@playwright/test";
import { viewToRoute } from "../../src/routes";
import type { MainView } from "../../src/types";

export const CONTROL_TOKEN = "secret";

const VIEW_LABELS: Record<string, string> = {
  Overview: "总览",
  Agent: "工作台",
  Workbench: "工作台",
  Sessions: "会话",
  "Runs / Events": "运行 / 事件",
  "Coverage Matrix": "覆盖矩阵",
  Models: "模型配置",
  "Data & Sync": "数据",
  MCP: "MCP / 连接器",
  Skills: "插件 / 技能",
  "Projects / Contexts": "项目 / 上下文",
  Approvals: "审批",
  "Finance Lab": "金融实验室",
  Integrations: "集成",
  Automation: "自动化",
  Readiness: "准备度 / 健康",
  "Financial Manager": "金融经理台",
  "Market Temperature": "市场温度",
  "Quant Research": "量化研究",
  "Strategy Factory": "策略工厂",
  "Factor Factory": "因子工厂",
  Incubation: "孵化工厂",
  "Local User": "本地用户",
  Tools: "工具",
  Capabilities: "能力中心",
  "Event Console": "事件控制台",
  "Factory Events": "工厂事件",
  Diagnostics: "诊断",
  "Agent Status": "智能体",
  Workflows: "工作流",
  Settings: "设置"
};

const TAB_LABELS: Record<string, string> = {
  Overview: "总览",
  "Coverage Matrix": "覆盖矩阵",
  Connectors: "连接器",
  Hermes: "Hermes",
  MCP: "MCP",
  "Strategy Factory": "策略工厂",
  Incubation: "孵化",
  Skills: "技能",
  Plugins: "插件",
  "AI Tests": "AI 测试"
};

const CONTROL_LABELS: Record<string, string> = {
  "Sync QMT read-only": "Sync QMT read-only",
  Connect: "连接 AIASK",
  Refresh: "刷新",
  Run: "运行线程任务",
  Search: "搜索",
  "Sync Agent state": "同步 AIASK 状态",
  "Finance safe mode": "Finance safe",
  "Finance safe": "金融安全",
  "Hermes full mode": "Hermes full 模式",
  "Hermes full": "Hermes full",
  "Run thread task": "运行线程任务",
  "Load run events": "加载运行事件",
  "Load run events for selected task": "Load events for the selected run",
  "Generate sync plan": "生成同步计划",
  "Create approval intent": "创建审批意图",
  "Run research": "运行研究",
  "Run read-only workflow": "运行只读工作流",
  "Run query": "运行查询",
  "Refresh capability review": "刷新能力评审",
  "Register local MCP server": "注册本地 MCP 服务",
  "Discover or refresh MCP server": "发现或刷新 MCP 服务",
  "Run MCP read-only smoke": "运行 MCP 只读冒烟测试",
  "Read MCP resource": "读取 MCP 资源",
  "Get MCP prompt": "获取 MCP 提示词",
  "Start MCP OAuth flow": "启动 MCP OAuth 流程",
  Install: "安装",
  Update: "更新",
  Delete: "删除",
  "Create job": "创建任务",
  Inspect: "查看",
  Pause: "暂停",
  Resume: "恢复",
  "Create run intent": "创建运行意图",
  "Maintenance intent": "创建维护意图",
  "Run intent": "创建运行意图",
  "Dry-run intent": "创建试运行意图",
  "Save profile": "保存画像",
  "Save local profile": "保存画像",
  "Run safe probe": "运行安全探测",
  "Run safe probe for agent_": "运行安全探测 agent_",
  "Fill example": "填充示例",
  "Fill example for agent_": "为 agent_",
  Disable: "禁用",
  "Disable plugin": "禁用插件",
  Enable: "启用",
  Configure: "配置",
  "Test tool": "测试",
  "Self-test": "自检",
  "Save plugin": "保存插件",
  "Run AI Smoke": "运行 AI 冒烟测试",
  "List Models": "列出模型",
  "Test connection": "测试连接",
  "Reset endpoint to default Agent endpoint": "恢复默认 Agent 端点",
  "Refresh connectors": "刷新连接器",
  "Load terminal sessions": "加载终端会话",
  "Connector detail": "详情",
  "Connector test": "测试",
  Reauthorize: "重新认证",
  "risk-review Risk review": "risk-review Risk review",
  "Projects / Contexts": "项目 / 上下文",
  "Plugins / Skills gated": "插件 / 技能 受限",
  "Plugins / Skills ready": "插件 / 技能 就绪",
  Approvals: "审批",
  "Finance Lab": "金融实验室",
  Integrations: "集成",
  "Load messages": "加载消息",
  "Preview Export/Delete": "Preview Export/Delete",
  "Preview Aggregate Governance": "Preview Aggregate Governance",
  "Run the first registered plugin tool": "运行第一个已注册插件工具",
  "Load plugin commands": "加载插件命令",
  "Test plugin command": "测试插件命令",
  "Disable plugin audit-plugin": "禁用插件 audit-plugin",
  "Enable plugin audit-plugin": "启用插件 audit-plugin",
  "Configure plugin audit-plugin": "配置插件 audit-plugin",
  "Test plugin audit-plugin": "测试插件 audit-plugin",
  "Test first plugin tool audit-plugin": "测试插件首个工具 audit-plugin",
  "Load commands for plugin audit-plugin": "加载插件命令 audit-plugin",
  "Inspect job 每日研究监控": "查看任务 每日研究监控",
  "Pause job 每日研究监控": "暂停任务 每日研究监控",
  "Run job 每日研究监控": "运行任务 每日研究监控",
  "Delete job 每日研究监控": "删除任务 每日研究监控",
  "Search tools input": "搜索工具输入",
  "初始化 Bootstrap": "初始化引导",
  "排空 outbox": "排空出站队列"
};

const PLACEHOLDER_LABELS: Record<string, string> = {
  "resource uri": "资源 URI",
  "prompt name": "提示词名称",
  "OAuth server name": "OAuth 服务名称",
  "Ask AIASK to research, code, inspect tools, or continue a session...": "让 AIASK 研究、检查工具、生成报告，或继续当前线程...",
  "Search local sessions, responses, and memory": "搜索本地会话、回复和记忆",
  "Search tools": "搜索工具",
  "Search area, tool, platform...": "搜索领域、工具、平台...",
  "payload text": "载荷文本"
};

const EXPECTED_TEXT_LABELS: Record<string, string> = {
  BROKER_SYNCED: "BROKER_SYNCED",
  AGENT_STATUS_LOADED: "智能体状态已加载",
  AGGREGATE_GOVERNANCE_PREVIEWED: "AGGREGATE_GOVERNANCE_PREVIEWED",
  AIASK_ONLINE: "在线",
  CONNECTORS_LOADED: "连接器已加载",
  DATA_STATUS_LOADED: "数据状态已加载",
  EVENTS_LOADED: "事件已加载",
  FACTOR_FACTORY_LOADED: "因子工厂已加载",
  FACTOR_MAINTENANCE_INTENT_CREATED: "因子维护意图已创建",
  FACTOR_RUN_INTENT_CREATED: "因子运行意图已创建",
  FACTORY_RELAY_LOADED: "接力状态已加载",
  INCUBATION_DRY_RUN_INTENT_CREATED: "孵化试运行意图已创建",
  INCUBATION_LOADED: "孵化状态已加载",
  INCUBATION_MAINTENANCE_INTENT_CREATED: "孵化维护意图已创建",
  INCUBATION_RUN_ONCE_INTENT_CREATED: "孵化运行意图已创建",
  JOBS_LOADED: "任务已加载",
  LOCAL_PROFILE_LOADED: "本地画像已加载",
  LOCAL_PROFILE_SAVED: "本地画像已保存",
  MARKET_TEMPERATURE_LOADED: "快照已加载",
  MODELS_LOADED: "模型列表已加载",
  MODEL_STATUS_LOADED: "模型状态已加载",
  RADAR_LOADED: "雷达已加载",
  STOCK_DATA_SOURCE_TEST_PASSED: "数据源测试通过",
  STRATEGY_FACTORY_INTENT_CREATED: "策略工厂意图已创建",
  SYNC_INTENT_CREATED: "同步审批意图已创建",
  SYNC_PLAN_READY: "同步计划已生成",
  USER_DATA_EXPORT_PREVIEWED: "USER_DATA_EXPORT_PREVIEWED",
  USER_DATA_SEARCHED: "用户数据已搜索",
  WEB_SEARCH_PASSED: "搜索调用成功"
};

export const SETTINGS_STRUCTURE_BUTTONS = [
  "返回对话",
  "关闭设置",
  "常规",
  "外观",
  "连接",
  "令牌与权限",
  "API Keys",
  "技能管理",
  "自动化管理",
  "应用集成",
  "Webhook",
  "插件与技能包",
  "模型配置",
  "MCP 管理入口",
  "工作流入口",
  "市场温度配置",
  "股票数据源",
  "数据路径",
  "学习 / RL",
  "安全扫描",
  "高级诊断入口",
  "关于"
];

export const LEGACY_REPLACEMENT_BUTTONS = [
  "前往工作台",
  "前往 工作台",
  "前往设置",
  "前往 设置",
  "前往 审批",
  "前往 MCP / 连接器",
  "前往 运行 / 事件",
  "前往 准备度 / 健康",
  "前往 插件 / 技能",
  "前往审批",
  "前往 审批",
  "前往集成",
  "前往 集成",
];

export const WORKBENCH_SAFE_PATH_BUTTONS = [
  "打开准备度",
  "打开 MCP",
  "打开本地用户",
  "打开金融经理台",
  "打开数据",
  "打开金融实验室",
];

export function viewLabel(name: string) {
  return VIEW_LABELS[name] || name;
}

export function tabLabel(name: string) {
  return TAB_LABELS[name] || name;
}

export function controlLabel(name: string) {
  return CONTROL_LABELS[name] || name;
}

export function placeholderLabel(name: string) {
  return PLACEHOLDER_LABELS[name] || name;
}

export function expectedTextLabel(text: string) {
  return EXPECTED_TEXT_LABELS[text] || text;
}

export async function expandAdvancedMcpOperations(page: Page) {
  const advanced = page.locator("details.mcp-operations-panel");
  if (await advanced.count()) {
    await advanced.evaluate((node) => {
      if (node instanceof HTMLDetailsElement) node.open = true;
    });
  }
}

Object.assign(VIEW_LABELS, {
  Overview: "总览",
  Agent: "工作台",
  Workbench: "工作台",
  Sessions: "会话",
  "Runs / Events": "运行 / 事件",
  "Coverage Matrix": "覆盖矩阵",
  Models: "模型配置",
  "Data & Sync": "数据",
  MCP: "MCP / 连接器",
  Skills: "插件 / 技能",
  "Projects / Contexts": "项目 / 上下文",
  Approvals: "审批",
  "Finance Lab": "金融实验室",
  Integrations: "集成",
  Automation: "自动化",
  "Financial Manager": "金融经理台",
  "Market Temperature": "市场温度",
  "Quant Research": "量化研究",
  "Strategy Factory": "策略工厂",
  "Factor Factory": "因子工厂",
  Incubation: "孵化工厂",
  "Local User": "本地用户",
  Tools: "工具",
  Capabilities: "能力中心",
  "Event Console": "事件控制台",
  "Factory Events": "工厂事件",
  Diagnostics: "诊断",
  "Agent Status": "智能体",
  Workflows: "工作流",
  Settings: "设置"
});

const VIEW_IDS: Record<string, string> = {
  Overview: "overview",
  Agent: "workbench",
  Workbench: "workbench",
  "Runs / Events": "runs-events",
  "Coverage Matrix": "coverage",
  Models: "models",
  "Data & Sync": "data",
  MCP: "mcp-connectors",
  Skills: "plugins-skills",
  "Projects / Contexts": "projects-contexts",
  Approvals: "tools-intents-approvals",
  "Finance Lab": "finance-lab",
  Integrations: "integrations",
  Automation: "automation",
  Readiness: "readiness-health",
  "Financial Manager": "financial-manager",
  "Market Temperature": "market-temperature",
  "Quant Research": "quant",
  "Strategy Factory": "strategy-factory",
  "Factor Factory": "factor-factory",
  Incubation: "incubation",
  "Local User": "user",
  Tools: "tools",
  Capabilities: "capabilities",
  "Event Console": "event-console",
  "Factory Events": "factory-events",
  Diagnostics: "diagnostics",
  "Agent Status": "agent",
  Workflows: "workflows",
  Settings: "settings"
};

const VIEW_GROUP_IDS: Record<string, string> = {
  workbench: "primary",
  "projects-contexts": "primary",
  "runs-events": "primary",
  "tools-intents-approvals": "primary",
  "finance-lab": "primary",
  integrations: "primary",
  automation: "primary",
  settings: "primary",
  "financial-manager": "advanced-finance",
  "market-temperature": "advanced-finance",
  quant: "advanced-finance",
  "strategy-factory": "advanced-finance",
  "factor-factory": "advanced-finance",
  incubation: "advanced-finance",
  data: "advanced-finance",
  workflows: "advanced-finance",
  "factory-events": "advanced-finance",
  "plugins-skills": "advanced-ops",
  "mcp-connectors": "advanced-ops",
  gateway: "advanced-ops",
  "readiness-health": "advanced-ops",
  "extensions-pilot": "advanced-ops",
  models: "advanced-ops",
  overview: "legacy",
  agent: "legacy",
  capabilities: "legacy",
  coverage: "legacy",
  tools: "legacy",
  mcp: "legacy",
  diagnostics: "legacy",
  "event-console": "legacy",
  skills: "legacy",
  user: "legacy"
};

// View → finance-lab card label (FinanceLabPage financeTemplates aria-label).
const FINANCE_LAB_CARD_LABELS: Record<string, string> = {
  "financial-manager": "财务管理",
  quant: "量化研究",
  "strategy-factory": "策略工厂",
  "factor-factory": "因子工厂",
  incubation: "孵化工厂",
  data: "数据",
  "factory-events": "事件工厂",
  "market-temperature": "市场温度",
  workflows: "工作流"
};

// View → integrations card label (IntegrationsPage aria-label is `打开 ${label}`).
const INTEGRATIONS_CARD_LABELS: Record<string, string> = {
  "mcp-connectors": "MCP / 连接器",
  gateway: "Gateway",
  "plugins-skills": "插件 / 技能",
  "tools-intents-approvals": "审批",
  "readiness-health": "准备度 / 健康"
};

Object.assign(CONTROL_LABELS, {
  Refresh: "刷新",
  "Sync Agent state": "同步 AIASK 状态",
  "Test connection": "测试连接",
  "Reset endpoint to default Agent endpoint": "恢复默认 Agent 端点",
  "Save profile": "保存画像",
  "Update snapshot": "更新快照",
  "Load terminal sessions": "加载终端会话",
  "Refresh radar": "刷新雷达",
  "Create radar run intent": "创建雷达运行意图",
  "Create radar push preview intent": "创建推送预览意图",
  "Create radar schedule intent": "创建调度意图",
  "Run MCP read-only smoke": "运行 MCP 只读冒烟测试",
  "初始化 Bootstrap": "初始化引导",
  "排空 outbox": "排空出站队列"
});

export async function openOverview(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "AIASK 工作台" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "线程优先工作台" })).toBeVisible();
  await expect(page.getByPlaceholder(placeholderLabel("Ask AIASK to research, code, inspect tools, or continue a session..."))).toBeVisible();
}

export async function openSettings(page: Page) {
  if (await settingsReturnButton(page).count()) return;
  const mainShortcut = page.getByRole("region", { name: "主工作区" }).getByRole("button", { name: viewLabel("Settings"), exact: true });
  if ((await mainShortcut.count()) && (await mainShortcut.first().isVisible())) {
    await mainShortcut.first().click();
    return;
  }
  const gearButton = page.locator('[data-view-id="settings"]');
  await expect(gearButton.first(), "Settings gear button should be visible").toBeVisible({ timeout: 15_000 });
  await gearButton.first().click();
}

export function settingsReturnButton(page: Page) {
  return page.locator(".settings-shell").getByRole("button", { name: /^(返回对话|返回工作台|关闭设置)$/ });
}

export async function closeSettingsOverlay(page: Page) {
  if (!(await settingsReturnButton(page).count())) return;
  await page.evaluate(() => {
    window.location.hash = "#/";
  });
  await expect(settingsReturnButton(page)).toHaveCount(0, { timeout: 15_000 });
}

export async function openSettingsSection(page: Page, sectionLabel: string) {
  await openSettings(page);
  const sectionButton = page.getByRole("navigation", { name: "设置导航" }).getByRole("button", { name: sectionLabel, exact: true });
  await expect(sectionButton.first()).toBeVisible({ timeout: 15_000 });
  await sectionButton.first().dispatchEvent("click");
}

export async function clickSettingsPanelRefresh(page: Page) {
  await page.locator(".settings-section-stack").getByRole("button", { name: controlLabel("Refresh"), exact: true }).last().click();
}

export async function setControlToken(page: Page, token = CONTROL_TOKEN) {
  await openSettings(page);
  await page.getByRole("button", { name: "令牌与权限", exact: true }).click();
  const controlTokenInput = page.locator("label.settings-row").filter({ hasText: "控制令牌" }).locator("input");
  await expect(controlTokenInput).toHaveCount(1);
  await controlTokenInput.fill(token);
  await expect(controlTokenInput).toHaveValue(token);
  const tokenStatusGrid = page.locator(".settings-static-grid").filter({ hasText: "令牌验证" });
  await expect(tokenStatusGrid).toContainText("已填写", { timeout: 15_000 });
  await expect(tokenStatusGrid).toContainText("已通过", { timeout: 15_000 });
  await page.getByRole("button", { name: "连接", exact: true }).click();
  await page.getByRole("button", { name: controlLabel("Test connection") }).click();
  await expect(page.getByText(expectedTextLabel("AIASK_ONLINE")).first()).toBeVisible();
  await closeSettingsOverlay(page);
}

const WORKFLOW_ENTRY_VIEWS = new Set<string>(["Automation"]);
const SETTINGS_MODEL_VIEWS = new Set<string>(["Models"]);
const SETTINGS_MCP_VIEWS = new Set<string>();
const SETTINGS_ADVANCED_VIEWS = new Set<string>([
  "Overview",
  "Coverage Matrix",
  "Tools",
  "Capabilities",
  "Diagnostics",
  "Agent Status",
  "Local User",
  "Event Console"
]);

const SETTINGS_ADVANCED_SHORTCUT_LABELS: Record<string, string> = {
  Overview: "运行概览",
  "Coverage Matrix": "能力覆盖矩阵",
  Tools: "工具目录",
  Capabilities: "能力中心",
  Diagnostics: "诊断",
  "Agent Status": "智能体状态",
  "Local User": "本地用户",
  "Event Console": "事件控制台"
};

async function clickShortcutByLabel(page: Page, label: string) {
  const shortcut = page.locator("button.settings-shortcut, article.workflow-hub-card button, .workflow-hub-card button").filter({ hasText: label });
  await expect(shortcut.first()).toBeVisible();
  await shortcut.first().click();
}

async function openCollapsedNavGroup(page: Page, groupName: string, targetLabel: string) {
  const navigation = page.getByRole("navigation");
  const group = navigation.locator(`section[aria-label="${groupName}"]`);
  if (!(await group.count())) return false;
  const groupToggle = group.getByRole("button", { name: groupName, exact: true });
  const groupTarget = group.getByRole("link", { name: targetLabel, exact: true }).or(group.getByRole("button", { name: targetLabel, exact: true }));
  if (!(await groupTarget.count())) {
    if (!(await groupToggle.count()) || !(await groupToggle.first().isVisible())) return false;
    await groupToggle.click();
  }
  const target = group.getByRole("link", { name: targetLabel, exact: true }).or(group.getByRole("button", { name: targetLabel, exact: true }));
  if (!(await target.count())) return false;
  await target.click();
  return true;
}

async function waitForViewHash(page: Page, viewId: string) {
  const expectedHash = `#${viewToRoute(viewId as MainView)}`;
  await expect
    .poll(() => new URL(page.url()).hash || "#/", {
      message: `URL hash should route to ${viewId}`,
      timeout: 15_000,
    })
    .toBe(expectedHash);
}

export async function openMainViewById(page: Page, name: string) {
  const viewId = VIEW_IDS[name];
  if (!viewId) return false;
  const navigation = page.getByRole("navigation");
  const selector = `[data-view-id="${viewId}"]`;
  let target = navigation.locator(selector);
  const groupId = VIEW_GROUP_IDS[viewId];
  const group = groupId ? navigation.locator(`section[data-view-group-id="${groupId}"]`) : null;
  if (!(await target.count()) && group && (await group.count())) {
    const toggle = group.getByRole("button").first();
    if ((await toggle.count()) && (await toggle.isVisible())) await toggle.click();
    target = navigation.locator(selector);
  }
  if (!(await target.count())) return false;
  await expect(target.first(), `Sidebar view ${name} should be visible`).toBeVisible({ timeout: 15_000 });
  await target.first().click();
  await waitForViewHash(page, viewId);
  await waitForMainViewReady(page, name);
  return true;
}

export async function waitForMainViewReady(page: Page, context: string) {
  await expect(page.getByLabel("Loading view"), `${context} loading fallback should finish`).toHaveCount(0, { timeout: 15_000 });
  await expect(page.locator("main h1, main h2, main h3").first(), `${context} should render a heading`).toBeVisible({ timeout: 15_000 });
}

export async function openMainView(page: Page, name: string) {
  const backToChat = settingsReturnButton(page);
  if (name !== "Settings" && (await backToChat.count())) {
    await closeSettingsOverlay(page);
  }

  if (name === "Agent" || name === "Workbench") {
    if (await openMainViewById(page, "Workbench")) return;
  }

  if (name === "Settings") {
    await openSettings(page);
    await waitForMainViewReady(page, name);
    return;
  }

  if (await openMainViewById(page, name)) return;

  const viewId = VIEW_IDS[name];
  if (viewId && FINANCE_LAB_CARD_LABELS[viewId]) {
    if (await openMainViewById(page, "Finance Lab")) {
      const card = page.getByRole("button", { name: FINANCE_LAB_CARD_LABELS[viewId], exact: true });
      await expect(card.first(), `Finance Lab card ${name} should be visible`).toBeVisible({ timeout: 15_000 });
      await card.first().click();
      await waitForViewHash(page, viewId);
      await waitForMainViewReady(page, name);
      return;
    }
  }
  if (viewId && INTEGRATIONS_CARD_LABELS[viewId]) {
    if (await openMainViewById(page, "Integrations")) {
      const card = page.getByRole("button", { name: `打开 ${INTEGRATIONS_CARD_LABELS[viewId]}`, exact: true });
      await expect(card.first(), `Integrations card ${name} should be visible`).toBeVisible({ timeout: 15_000 });
      await card.first().click();
      await waitForViewHash(page, viewId);
      await waitForMainViewReady(page, name);
      return;
    }
  }

  if (name === "Sessions") {
    const sessionsButton = page.getByRole("button").filter({ hasText: viewLabel("Sessions") }).first();
    await expect(sessionsButton, "Sessions sidebar button should be visible").toBeVisible({ timeout: 15_000 });
    await sessionsButton.click();
    await waitForMainViewReady(page, name);
    return;
  }

  if (WORKFLOW_ENTRY_VIEWS.has(name)) {
    await openMainView(page, "Workflows");
    await clickShortcutByLabel(page, viewLabel(name));
    await waitForMainViewReady(page, name);
    return;
  }

  if (SETTINGS_MODEL_VIEWS.has(name)) {
    await openSettings(page);
    await page.getByRole("button", { name: "模型配置", exact: true }).click();
    await clickShortcutByLabel(page, "打开模型配置页");
    await waitForViewHash(page, "models");
    await expect(settingsReturnButton(page)).toHaveCount(0, { timeout: 15_000 });
    await waitForMainViewReady(page, name);
    return;
  }

  if (SETTINGS_MCP_VIEWS.has(name)) {
    await openSettings(page);
    await page.getByRole("button", { name: "MCP 管理入口", exact: true }).click();
    await clickShortcutByLabel(page, "打开 MCP / 连接器");
    await waitForViewHash(page, "mcp-connectors");
    await expect(settingsReturnButton(page)).toHaveCount(0, { timeout: 15_000 });
    await waitForMainViewReady(page, name);
    return;
  }

  if (SETTINGS_ADVANCED_VIEWS.has(name)) {
    await openSettings(page);
    await page.getByRole("button", { name: "高级诊断入口", exact: true }).click();
    await clickShortcutByLabel(page, SETTINGS_ADVANCED_SHORTCUT_LABELS[name] || viewLabel(name));
    await waitForViewHash(page, VIEW_IDS[name]);
    await expect(settingsReturnButton(page)).toHaveCount(0, { timeout: 15_000 });
    await waitForMainViewReady(page, name);
    return;
  }

  const label = viewLabel(name);
  const navigationButton = page
    .getByRole("navigation")
    .getByRole("link", { name: label, exact: true })
    .or(page.getByRole("navigation").getByRole("button", { name: label, exact: true }));
  const navigationButtonCount = await navigationButton.count();
  if (navigationButtonCount) {
    await navigationButton.first().click();
    await waitForMainViewReady(page, name);
    return;
  }
  const navigationTextButton = page
    .getByRole("navigation")
    .getByRole("link")
    .filter({ hasText: label })
    .or(page.getByRole("navigation").getByRole("button").filter({ hasText: label }));
  const navigationTextButtonCount = await navigationTextButton.count();
  if (navigationTextButtonCount) {
    await navigationTextButton.first().click();
    await waitForMainViewReady(page, name);
    return;
  }
  for (const groupName of ["高级金融", "高级运维", "旧入口 / 高级诊断"]) {
    if (await openCollapsedNavGroup(page, groupName, label)) {
      await waitForMainViewReady(page, name);
      return;
    }
  }
  // No sidebar/aggregator entry (legacy/diagnostic-only view): deep-link via HashRouter.
  // Keep the existing API origin/route interception intact — do NOT switch to the
  // built-in front-end mock (?mock=1), which serves a different fixture set.
  const directId = VIEW_IDS[name];
  if (directId) {
    await page.goto(`/#${viewToRoute(directId as MainView)}`);
    await waitForViewHash(page, directId);
    await waitForMainViewReady(page, name);
    return;
  }
  await page.getByRole("button", { name: label, exact: true }).click();
  await waitForMainViewReady(page, name);
}

export async function openCapabilityTab(page: Page, name: string) {
  const tab = page.locator(".capabilities-tabs").getByRole("button", { name: tabLabel(name), exact: true });
  await expect(tab, `Capability tab ${name} should be visible`).toBeVisible({ timeout: 15_000 });
  await tab.click();
  await expect(tab, `Capability tab ${name} should become active`).toHaveAttribute("aria-pressed", "true", { timeout: 15_000 });
  await waitForMainViewReady(page, `Capabilities / ${name}`);
}
