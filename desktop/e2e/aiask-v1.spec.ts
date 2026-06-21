import { expect, test } from "@playwright/test";

const pages = [
  ["/", "AI 对话工作台"],
  ["/models", "模型配置与 LLM 可用性"],
  ["/projects", "项目与上下文"],
  ["/sessions-runs", "会话、运行、事件与产物"],
  ["/tools-approvals", "Agent 工具、Intent 与审批"],
  ["/integrations", "集成能力总览"],
  ["/mcp-connectors", "MCP 服务与统一连接器"],
  ["/plugins-skills", "Skills 与 Plugins 管理"],
  ["/gateway-webhooks", "Gateway 与 Webhooks"],
  ["/stock-data-sources", "股票数据源配置与测试"],
  ["/data-sync", "数据库状态与数据同步"],
  ["/finance", "金融工作台"],
  ["/stock-radar", "股票雷达"],
  ["/market-temperature", "热力图与市场温度"],
  ["/quant-research", "量化研究与报告"],
  ["/financial-manager", "Financial Manager 与 Broker 只读"],
  ["/automation", "自动化盯盘与任务处理"],
  ["/workflows", "V1 工作流"],
  ["/settings", "设置、安全与门禁"],
  ["/readiness", "Readiness 健康诊断与运维"],
  ["/local-user-memory", "记忆与个人能力"],
  ["/learning-rl", "Learning / RL / MoA 学习能力"],
  ["/native-diagnostics", "Native 文件、代码、终端、浏览器能力"]
] as const;

for (const [path, title] of pages) {
  test(`opens ${path}`, async ({ page }) => {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await expect(page.getByText(/策略工厂|四工厂|Strategy Factory|Factor Factory|Factory Events|Incubation/i)).toHaveCount(0);
  });
}

test("old deferred route does not open a product page", async ({ page }) => {
  await page.goto("/strategy-factory");
  await expect(page.getByRole("heading", { level: 1, name: "金融工作台" })).toBeVisible();
  await expect(page).toHaveURL(/\/finance$/);
});
