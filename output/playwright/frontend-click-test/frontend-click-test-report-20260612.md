# AIASK Desktop Web 前端真实点击测试报告

测试日期：2026-06-12  
测试入口：`http://127.0.0.1:1420/`  
Agent 后端：`http://127.0.0.1:8767/health` 返回 `{"status":"ok","service":"aiask-agent"}`  
测试方式：启动真实 Vite Web 端后，通过 MCP 驱动 Playwright 打开实际页面、展开导航、逐页点击、页面内点击、截图留证。未用单元测试或脚本输出替代页面点击。

## 结论

本轮共覆盖侧边栏 33 个唯一页面入口，并补充测试工作台快捷入口、集成卡片入口、设置中心全部分类、金融实验室入口、审批页和在线刷新状态。修复后，核心页面没有白屏、路由崩溃或主要按钮不可达问题；所有复测关键路径均通过。

本次已修复：

1. 侧边栏重复目标：`自动化` 和 `设置` 同时出现在主工作区与高级分组，导致同名按钮重复、辅助技术和点击定位歧义。
2. 集成页卡片可访问名称：卡片按钮与侧边栏同名，例如 `MCP / 连接器`、`Gateway`，全局可访问名称重复。已改为 `打开 MCP / 连接器`、`打开 Gateway`。

仍建议后续优化：

1. 初始打开时若后端已在线但页面显示离线，应更明确展示“正在连接/点击同步”状态，避免非技术用户误以为系统不可用。
2. 旧入口 / 高级诊断页仍展示原始 JSON 中的 `null` 字段，适合诊断人员，但对普通用户不友好。建议默认折叠原始 JSON 或格式化为空值说明。
3. 控制令牌缺失时多数运维按钮被禁用，这是安全预期；当前提示基本清楚，但可以在每个禁用按钮旁提供统一“去设置令牌”的入口。

## 启动与环境

已启动前端：

```text
npm run dev -- --host 127.0.0.1 --port 1420
```

Vite 日志：

```text
VITE v6.4.2 ready
Local: http://127.0.0.1:1420/
```

截图目录：

```text
output/playwright/frontend-click-test/screenshots/
```

原始点击状态与复测结果：

```text
output/playwright/frontend-click-test/page-states-raw.json
output/playwright/frontend-click-test/advanced-page-states-raw-2.json
output/playwright/frontend-click-test/interaction-results.json
output/playwright/frontend-click-test/postfix-interaction-results.json
output/playwright/frontend-click-test/integration-retest-results.json
output/playwright/frontend-click-test/final-smoke-results.json
```

## 页面覆盖

已真实点击并截图的页面入口：

| 序号 | 页面 | 结果 | 截图 |
|---:|---|---|---|
| 1 | 工作台 | 通过 | `screenshots/02-workbench.png` |
| 2 | 项目 / 上下文 | 通过 | `screenshots/03-projects-contexts.png` |
| 3 | 运行 / 事件 | 通过 | `screenshots/04-runs-events.png` |
| 4 | 审批 | 通过 | `screenshots/05-tools-intents-approvals.png` |
| 5 | 金融实验室 | 通过 | `screenshots/06-finance-lab.png` |
| 6 | 集成 | 通过 | `screenshots/07-integrations.png` |
| 7 | 自动化 | 通过 | `screenshots/08-automation.png` |
| 8 | 设置 | 通过 | `screenshots/09-settings.png` |
| 9 | 金融经理台 | 通过 | `screenshots/10-financial-manager.png` |
| 10 | 市场温度 | 通过 | `screenshots/11-market-temperature.png` |
| 11 | 量化研究 | 通过 | `screenshots/12-quant.png` |
| 12 | 策略工厂 | 通过 | `screenshots/13-strategy-factory.png` |
| 13 | 因子工厂 | 通过 | `screenshots/14-factor-factory.png` |
| 14 | 孵化工厂 | 通过 | `screenshots/15-incubation.png` |
| 15 | 数据 | 通过 | `screenshots/16-data.png` |
| 16 | 工作流 | 通过 | `screenshots/17-workflows.png` |
| 17 | 工厂事件 | 通过 | `screenshots/18-factory-events.png` |
| 18 | 模型配置 | 通过 | `screenshots/19-models.png` |
| 19 | 插件 / 技能 | 通过 | `screenshots/20-plugins-skills.png` |
| 20 | MCP / 连接器 | 通过 | `screenshots/21-mcp-connectors.png` |
| 21 | Gateway | 通过 | `screenshots/22-gateway.png` |
| 22 | 准备度 / 健康 | 通过 | `screenshots/23-readiness-health.png` |
| 23 | 扩展注册表 | 通过 | `screenshots/24-extensions-pilot.png` |
| 24 | 总览 | 通过 | `screenshots/25-overview.png` |
| 25 | 智能体 | 通过，诊断 JSON 有 `null` | `screenshots/26-agent.png` |
| 26 | 能力中心 | 通过 | `screenshots/27-capabilities.png` |
| 27 | 覆盖矩阵 | 通过 | `screenshots/28-coverage.png` |
| 28 | 工具 | 通过，工具说明有 `dict|null` 文案 | `screenshots/29-tools.png` |
| 29 | MCP | 通过 | `screenshots/30-mcp.png` |
| 30 | 诊断 | 通过 | `screenshots/31-diagnostics.png` |
| 31 | 事件控制台 | 通过 | `screenshots/32-event-console.png` |
| 32 | 技能 | 通过 | `screenshots/33-skills.png` |
| 33 | 本地用户 | 通过 | `screenshots/34-user.png` |

## 页面内点击

已执行的关键页面内交互：

| 交互 | 初测结果 | 修复 / 复测 |
|---|---|---|
| 工作台 -> 打开准备度 | 通过 | `screenshots/36-open-readiness-from-workbench.png` |
| 工作台 -> 打开 MCP | 通过 | `screenshots/36-open-mcp-from-workbench.png` |
| 工作台输入任务，运行按钮变可用 | 通过 | `screenshots/36-workbench-prompt-enables-run.png` |
| 金融实验室 -> 打开策略工厂 | 通过 | `screenshots/36-finance-lab-open-strategy-factory.png` |
| 集成 -> MCP / 连接器卡片 | 初测可访问名称歧义 | 修复后通过：`screenshots/39-integrations-open-mcp-after-aria.png` |
| 集成 -> Gateway 卡片 | 初测可访问名称歧义 | 修复后通过：`screenshots/39-integrations-open-gateway-after-aria.png` |
| 设置中心切换全部分类 | 初测受重复设置入口影响 | 修复后通过：`screenshots/38-settings-tabs-after-fix.png` |
| 设置中心 -> 返回工作台 | 通过 | `screenshots/38-settings-return-after-fix.png` |

## 发现与修复

### P1：侧边栏重复导航目标

现象：展开高级分组后，`自动化` 和 `设置` 在侧边栏出现两次，且两个按钮的可访问名称、标题和 `data-view-id` 完全相同。  
影响：非技术用户不清楚两个入口是否不同；屏幕阅读器和自动化点击也无法唯一定位。  
证据：`screenshots/01-navigation-expanded.png`、`screenshots/debug-after-nav-issue.png`。  
修复：从高级金融中移除重复的 `automation`，从高级运维中移除重复的 `settings`，保留主工作区入口。  
回归：新增 `views.test.ts` 用例，保证侧边栏分组中同一 `MainView` 不会重复出现。  
复测：`screenshots/37-navigation-after-dedupe.png`，所有导航目标计数均为 1。

### P2：集成页卡片按钮可访问名称与侧边栏冲突

现象：集成页面卡片按钮使用 `aria-label={entry.label}`，导致页面按钮和侧边栏按钮同名，例如两个 `MCP / 连接器`、两个 `Gateway`。  
影响：辅助技术无法区分“导航侧边栏”与“打开卡片”，自动化点击需额外限定作用域；对非技术用户虽可视觉识别，但语义不够清晰。  
证据：`screenshots/36-debug-integrations-buttons.png`、`screenshots/38-integrations-mcp-entry-error.png`。  
修复：集成卡片 `aria-label` 改为 `打开 ${entry.label}`。  
复测：`screenshots/39-integrations-open-mcp-after-aria.png`、`screenshots/39-integrations-open-gateway-after-aria.png`。

### P3：设置中心是独立布局，需确认返回路径

现象：进入设置后，主侧边栏隐藏，只展示设置中心左侧分类导航。  
影响：如果没有明显返回按钮，用户会迷路。  
结论：页面提供 `返回工作台`，且点击有效。  
证据：`screenshots/09-settings.png`、`screenshots/38-settings-return-after-fix.png`。  
状态：通过，无需修复。

### P3：旧诊断页出现原始 `null`

现象：`智能体` 旧入口的原始 JSON 中展示 `"notes": null`、`"introduced_in": null` 等；`工具`页工具说明中出现 `dict|null`。  
影响：普通用户可能误认为页面异常；诊断人员可接受。  
证据：`screenshots/40-agent-null-inspection.png`、`screenshots/40-tools-null-inspection.png`。  
状态：未改代码，建议后续把旧入口的原始 JSON 默认折叠，或把空值渲染为“无”。

## 最终复测

最终复测 6 条关键路径全部通过：

| 路径 | 截图 |
|---|---|
| 在线工作台 | `screenshots/41-workbench-online-final.png` |
| 展开后导航唯一 | `screenshots/41-nav-expanded-final.png` |
| 集成卡片打开 MCP | `screenshots/41-integration-mcp-final.png` |
| 设置分类“关于” | `screenshots/41-settings-about-final.png` |
| 金融实验室 | `screenshots/41-finance-lab-final.png` |
| 审批页 | `screenshots/41-approvals-final.png` |

## 代码验证

已运行并通过：

```text
npm run typecheck
npm test -- views.test.ts
```

实际结果：

```text
tsc --noEmit 通过
34 个前端测试文件通过，134 个测试通过
```

## 修改文件

```text
desktop/src/views.ts
desktop/src/views.test.ts
desktop/src/features/workspace/IntegrationsPage.tsx
```

## 面向非技术用户的可用性判断

修复后，主入口更清晰：常用页面集中在主工作区，高级页面需要主动展开，且同一路由不再重复出现。页面遇到控制令牌缺失、完整模式未开启、后端未加载时，基本都给出了“受限 / 需要控制令牌 / 等待加载”状态，而不是静默失败。工作台输入任务后运行按钮能从禁用变为可用，设置中心有明确返回路径，集成卡片能直接打开对应页面。

当前可认为 Web 前端核心导航和主要只读/受控工作流入口真实可用；需要控制令牌的运维动作在未配置令牌环境下保持安全禁用，符合金融安全边界。
