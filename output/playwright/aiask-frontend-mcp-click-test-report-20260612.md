# AIASK 前端真实点击测试报告

生成时间：2026-06-12 18:04（Asia/Shanghai）

## 结论

本轮已启动并复用项目 Web 前端 `http://127.0.0.1:1420`，使用真实 Chromium 页面逐步点击覆盖 Desktop 前端页面矩阵，并将截图保存到项目 `output/playwright/` 目录。

初始 MCP 点击扫测覆盖 50 张页面/视口截图，发现侧栏折叠按钮点击高度不足、移动端摘要卡片文字竖排溢出、受控运维页面缺少控制令牌时反馈生硬、模型配置与股票数据源配置链路不够直接等问题。相关问题已修复，并完成修复后截图复测与代码回归验证。

## 测试方式

- 前端地址：`http://127.0.0.1:1420/?mock=1`
- 前端服务：Vite dev server on `127.0.0.1:1420`
- 主测试方式：Playwright MCP / Browser MCP 真实 Chromium 点击与截图
- 主扫记录：`output/playwright/mcp-playwright/mcp-playwright-click-sweep-report.json`
- 主扫记录方法字段：`mcp__node_repl + Playwright real Chromium clicks`
- 补充验证：`npm run typecheck`、Vitest、production build、Playwright mock e2e、Agent/Strategy targeted pytest

自动化回归只作为补充验证，不替代真实页面点击截图证据。

## 截图产物

主截图目录：

- `output/playwright/mcp-playwright/`：50 张全页面/移动端 MCP 点击截图
- `output/playwright/mcp-playwright-after-fix/`：17 张修复后专项复测截图
- `output/playwright/mcp-playwright-final/`：12 张最终关键链路复测截图
- `output/playwright/manual-full-frontend-20260612/`：43 张真实页面矩阵与修复前后对比截图

覆盖页面包括：

- 主工作区：工作台、项目 / 上下文、运行 / 事件、审批、金融实验室、集成、自动化、设置
- 设置页：常规、连接、令牌与权限、技能管理、自动化管理、应用集成、Webhook、插件与技能包、模型配置、MCP 管理入口、工作流入口、股票数据源、数据路径、学习 / RL、安全扫描、高级诊断入口、关于
- 金融页：金融经理台、市场温度、量化研究、策略工厂、因子工厂、孵化工厂、数据、工作流、工厂事件
- 运维页：插件 / 技能、MCP / 连接器、Gateway、准备度 / 健康、扩展注册表
- 旧入口 / 高级诊断：总览、智能体、能力中心、覆盖矩阵、工具、MCP、诊断、事件控制台、技能、本地用户、模型
- 响应式：390x844 移动端工作台、移动端设置页

关键复测截图：

- 模型页冒烟通过：`output/playwright/mcp-playwright-final/06-models-smoke-passed.png`
- 股票数据源本地测试通过：`output/playwright/mcp-playwright-final/08-stock-data-test-passed.png`
- 股票数据源搜索通过：`output/playwright/mcp-playwright-final/09-stock-data-search-passed.png`
- 移动端工作台无横向溢出：`output/playwright/mcp-playwright-final/10-mobile-workbench.png`
- 移动端设置页无横向溢出：`output/playwright/mcp-playwright-final/11-mobile-settings.png`
- MCP 连接器缺令牌降级态：`output/playwright/manual-full-frontend-20260612/40-fixed-mcp-connectors-gated-no-401.png`
- Gateway 缺令牌降级态：`output/playwright/manual-full-frontend-20260612/41-fixed-gateway-gated-no-401.png`

## 发现并修复的问题

| 编号 | 问题 | 影响 | 修复结果 |
| --- | --- | --- | --- |
| P1 | 移动端工作台最近会话/最近运行卡片被压成窄列，文字竖排并溢出。 | 非技术用户在手机宽度下难以阅读与点击。 | 调整响应式布局与摘要按钮尺寸，最终 390px 视口 `scrollWidth=390`，无横向溢出。 |
| P1 | 侧栏分组按钮点击高度过小，初始扫测多页记录 tiny click targets。 | 分组折叠/展开不符合普通用户点击习惯。 | 增加稳定高度、移动端网格约束和按钮布局；mock e2e layout gate 通过。 |
| P1 | MCP / Gateway / Readiness 等受控页面在缺少控制令牌时容易显示 401/生硬失败态。 | 用户不知道下一步该填写控制令牌还是后端异常。 | 改为清晰 gated / `CONTROL_TOKEN_REQUIRED` 状态，禁用危险按钮并保留只读信息。 |
| P1 | 模型状态仍藏在旧入口，模型获取与冒烟测试链路不直观。 | 非技术用户难以完成“配置提供方、获取模型、测试模型”的实际流程。 | 模型配置提升到高级运维入口，新增提供方预设、状态卡、模型列表与冒烟测试。 |
| P1 | 股票数据源配置、保存、测试、搜索入口不完整。 | 用户无法在设置页完成行情/搜索数据源配置验证。 | 新增股票数据源设置面板、Agent API、mock 数据与测试；保存、测试、搜索均有状态反馈。 |
| P2 | 设置页返回按钮文案演进后，e2e helper 仍只识别旧“返回对话”。 | 回归测试误报超时。 | helper 改为限定在 `.settings-shell` 内识别“返回对话 / 返回工作台”，并同步模型入口分组。 |
| P2 | 策略工厂质量/所有权/纸上交易桥接状态展示不够结构化。 | 用户难以判断工厂运行是否可继续或是否只是降级。 | 补充工厂状态、质量会话、所有权与 paper bridge DTO/展示/测试。 |

## 关键功能复测

模型配置：

- 页面可从设置和高级运维进入。
- 当前提供方、API key、Base URL、配置来源、提供方池展示正常。
- 点击“获取模型”后可选择 `gpt-5.4`。
- 点击“测试模型”后显示 `AI_SMOKE_PASSED` 与“通过”状态。

股票数据源：

- 设置页可进入“股票数据源”。
- 表单可保存本地 mock/akshare/duckduckgo 等数据源配置。
- 点击“测试连接”后显示 `ready`、样本数和延迟。
- 点击“调用搜索”后显示搜索 provider、样本数和只读调用示例。
- 未发现密钥回显泄漏。

受控运维页面：

- 缺少控制令牌时 MCP / Gateway / Connector / Skills 等页面显示 gated 原因和下一步说明。
- 只读数据仍可见，受控操作按钮保持禁用。
- 没有再出现原始 401 墙或对非技术用户不可理解的错误空白页。

响应式：

- 390x844 移动端工作台无横向溢出。
- 移动端设置页无横向溢出。
- 最近会话/最近运行按钮恢复正常宽度和高度。

## 验证命令

已通过：

```powershell
cd C:\Users\walking\Desktop\aiask\desktop
npm run typecheck
npm test -- --run src/features/models/ModelsWorkspace.test.tsx src/features/settings/SettingsWorkspace.test.tsx src/features/settings/StockDataSourcesPanel.test.tsx src/features/agent-pages/McpConnectorsPage.test.tsx src/features/agent-pages/GatewayPage.test.tsx
npm run build
npm run test:e2e:mock
```

结果：

- `npm run typecheck`：通过
- targeted Vitest：33 files passed, 127 tests passed
- `npm run build`：通过
- `npm run test:e2e:mock`：11 passed, 3 skipped（3 个 live smoke 需要显式 `AIASK_DESKTOP_RUN_LIVE=1`，按设计跳过）

后端/契约补充验证：

```powershell
uv run pytest packages/agent/tests/test_ai_status_and_smoke.py packages/agent/tests/test_desktop_ops_api.py packages/agent/tests/test_live_readiness_smoke_script.py packages/agent/tests/test_native_full_parity.py
uv run pytest packages/strategy-factory/tests/test_public_contracts.py packages/strategy-factory/tests/test_paper_trading_bridge.py packages/akshare-mcp/tests/test_strategy_factory_ownership.py
```

结果：

- Agent targeted pytest：29 passed, 1 skipped
- Strategy / AKShare targeted pytest：17 passed

## 主要改动范围

前端：

- `desktop/src/views.ts`
- `desktop/src/App.tsx`
- `desktop/src/features/models/ModelsWorkspace.tsx`
- `desktop/src/features/settings/SettingsWorkspace.tsx`
- `desktop/src/features/settings/StockDataSourcesPanel.tsx`
- `desktop/src/features/agent-pages/McpConnectorsPage.tsx`
- `desktop/src/features/agent-pages/GatewayPage.tsx`
- `desktop/src/features/factory/StrategyFactoryPanel.tsx`
- `desktop/src/services/aiaskApi.ts`
- `desktop/src/mockApi.ts`
- `desktop/src/types.ts`
- `desktop/src/styles.css`
- `desktop/e2e/capabilities.spec.ts`

后端/API 契约：

- `packages/agent/src/aiask_agent/server.py`
- `packages/agent/src/aiask_agent/env_config.py`
- `packages/agent/src/aiask_agent/capabilities.py`
- `packages/agent/src/aiask_agent/native_capabilities.py`
- `packages/agent/src/aiask_agent/stock_data_sources.py`
- `packages/strategy-factory/`
- `packages/akshare-mcp/`

## 注意事项

- 本轮未执行真实 live trading 或外部平台发送动作；交易风险、外部平台、状态型操作均保持 ActionIntent / control token 门控。
- `output/playwright/mcp-playwright-final/final-mcp-retest.json` 中早期 `modelsLoaded/modelSmokePassed/stockTestPassed=false` 是旧检查器文案匹配误判；对应最终截图和后续 e2e 均证明模型冒烟、股票数据源测试和搜索已通过。
- 3 个 live smoke e2e 按环境变量跳过，不代表失败；需要真实后端 live 验证时再设置 `AIASK_DESKTOP_RUN_LIVE=1` 单独运行。
