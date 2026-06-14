# AIASK 应用端非技术用户前端细化测试报告

生成时间：2026-06-12 21:12（Asia/Shanghai）

## 结论

本轮继续围绕“非技术人员使用时，前端显示必须更细致、更可理解”做真实页面验证和修复。应用端 Web 已在 `http://127.0.0.1:1420` 运行，使用 MCP 浏览器真实点击验证了工作台、设置、模型配置、股票数据源、MCP / 连接器、Gateway、准备度 / 健康、金融实验室和策略工厂等关键路径。

已修复一个本轮 MCP 点击发现的新问题：右侧检查器里的设置页能显示“打开模型配置页”，但按钮因为漏传导航函数而不可点击。现在该入口可直接跳转到模型配置页，非技术用户不会卡在不可操作的说明卡上。

## 本轮真实 MCP 点击证据

MCP 点击证据文件：

- `output/playwright/nontechnical-mcp-final-20260612/mcp-live-click-evidence.json`

实际点击覆盖：

- 右侧设置入口 -> 模型配置页：点击“打开模型配置页”，确认进入“LLM 提供方、模型获取与测试”，并看到“获取模型”“测试模型”。
- 模型配置动作：点击“获取模型”“测试模型”，失败时显示“模型请求被服务商或网络策略拦截；请检查 Base URL、密钥权限、模型名或网络出口”，不再把底层异常直接扔给用户。
- 设置 -> 股票数据源：点击“股票数据源”，确认页面显示“建议先选择预设”“密钥脱敏”“DuckDuckGo fallback”等普通用户可理解引导。
- 股票数据源搜索：点击“DuckDuckGo HTML Search”和“调用搜索”，确认显示“搜索调用成功”“就绪”“样本数”。
- 设置 -> MCP 管理入口 -> MCP / 连接器：点击“打开 MCP / 连接器”，确认主页面显示“需要控制令牌”“连接器管理受限”，高级 MCP 操作默认折叠。
- Gateway：点击 Gateway，确认缺少控制令牌时显示“需要控制令牌后刷新”“管理详情需要控制令牌”，发送预览说明仍保留 ActionIntent 审批链路。
- 准备度 / 健康：点击准备度，确认默认展示“检查清单状态”和“日常使用只需要看状态和检查数”，技术联调清单和完整模式控制台默认折叠。
- 金融实验室：点击“打开金融实验室”，确认工厂接力显示“部分就绪”，并给出因子、策略、孵化各自原因与下一步按钮。
- 策略工厂：从金融实验室点击“打开策略工厂”，确认显示“受限”“需要控制令牌”“本地数据库”，没有裸露原始控制令牌错误。

## 截图产物

既有完整前后截图目录：

- `output/playwright/nontechnical-detail-20260612-continuation/`
- `output/playwright/mcp-playwright/`
- `output/playwright/mcp-playwright-after-fix/`
- `output/playwright/mcp-playwright-final/`
- `output/playwright/manual-full-frontend-20260612/`

本轮 MCP 截图说明：

- `output/playwright/nontechnical-mcp-final-20260612/00-mcp-screenshot-probe.png`：空白页截图探针成功。
- AIASK 页面在 MCP `Page.captureScreenshot` 上超时，但同一 MCP 浏览器 DOM 与点击验证正常；因此本轮以 `mcp-live-click-evidence.json` 作为 MCP 实际点击证据，并沿用前述目录中的实际页面截图作为视觉附件。

关键截图参考：

- `output/playwright/nontechnical-detail-20260612-continuation/15-workbench-live-after.png`
- `output/playwright/nontechnical-detail-20260612-continuation/16-models-live-after.png`
- `output/playwright/nontechnical-detail-20260612-continuation/17-stock-data-sources-live-after.png`
- `output/playwright/nontechnical-detail-20260612-continuation/18-stock-search-live-after.png`
- `output/playwright/nontechnical-detail-20260612-continuation/19-mcp-connectors-live-after.png`
- `output/playwright/nontechnical-detail-20260612-continuation/20-gateway-live-after.png`
- `output/playwright/nontechnical-detail-20260612-continuation/21-readiness-health-live-after.png`
- `output/playwright/nontechnical-detail-20260612-continuation/22-strategy-factory-live-after.png`

## 已修复的非技术用户问题

1. 右侧检查器设置入口的跳转按钮不可点击。
   - 问题：在右侧检查器打开设置后，“打开模型配置页”显示为入口，但实际 disabled。
   - 修复：`InspectorPanel` 现在接收并传递 `onOpenView`，`App` 将 `selectView` 传入检查器。
   - 结果：MCP 点击“打开模型配置页”后成功进入模型配置页。

2. 技术状态码和异常裸露。
   - 模型、股票数据源、MCP、Gateway、准备度、策略工厂等页面使用中文可读状态。
   - 原始技术细节进入折叠详情或原始载荷面板，不作为主路径信息。

3. 设置入口不够细。
   - 模型配置、MCP 管理入口、股票数据源都补充了“为什么要这样做、下一步点哪里、密钥不会回显”的说明。
   - 股票数据源支持 DuckDuckGo fallback，非技术用户无 API Key 也能先验证搜索链路。

4. 工作台摘要不够人话。
   - 最近会话、最近运行显示可读时间、状态和短 ID。
   - 按钮增加明确可访问名称，例如“打开会话：…”和“查看运行：…”。

5. 受控功能缺少下一步解释。
   - MCP / Gateway / 策略工厂在缺少控制令牌时明确提示需要控制令牌，不显示原始 401/invalid token 作为主信息。

## 最新验证结果

从 `desktop/` 执行：

```powershell
npm run typecheck
npm test
npm run build
npm run test:e2e:mock
```

最新结果：

- `npm run typecheck`：通过
- `npm test`：33 files passed，130 tests passed
- `npm run build`：通过
- `npm run test:e2e:mock`：11 passed，3 skipped（3 个 live smoke 需要显式开启 live 环境变量，按设计跳过）

## 仍需真实环境配置的项

- 当前 live 环境缺少控制令牌时，MCP、Gateway、策略工厂等管理动作会正确受限。
- MCP 授权变量仍需在 Agent 启动环境中配置，例如 `AIASK_MCP_AKSHARE_LOCAL_AUTHORIZATION`。
- 模型测试受服务商或网络策略影响时，前端已经给出可理解说明；这不等于外部模型服务已经可用。

## 结论性判断

当前应用端前端已经从“技术状态展示”推进到“操作员可理解展示”：页面能说明当前状态、为什么受限、下一步点哪里、哪些动作需要控制令牌，且测试覆盖了主路径点击、mock e2e、类型检查和生产构建。
