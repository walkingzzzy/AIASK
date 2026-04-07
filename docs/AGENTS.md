# AIASK 项目 AGENTS 提示词（MCP + Skills）

> 适用目录：当前工作区中的 AIASK 股票项目（本次校对环境：`/Users/mac/Desktop/股票`）
> 文档角色：项目级代理执行规范
> 校准说明：本文保留“执行原则 / 路由规范 / 风险边界”作为当前规则；其中工具数、覆盖率、外部基线等必须区分“全量运行时注册面”和“Skill 覆盖审计切片”，不要把历史统计当作永久事实。

## 1. 项目事实基线

### 1.1 当前全量运行时注册面（2026-04-07 本地复核）

- MCP tools：`155`
- MCP resources：`3`
- MCP prompts：`6`
- 本地 skills：`19`
- Web 页面路由：`46`
- BFF 一级模块目录：`38`

上述统计分别通过以下路径复核：

1. `PYTHONPATH=packages/akshare-mcp/src:packages/strategy-factory/src python3 -c "import akshare_mcp.server as s; m=s.mcp; print(len(m._tool_manager.list_tools()), len(m._resource_manager.list_resources()), len(m._prompt_manager.list_prompts()))"`
2. `find .codex/skills -maxdepth 2 -name 'SKILL.md' | wc -l`
3. `find apps/web/app -name 'page.tsx' | wc -l`
4. `find apps/bff/src -mindepth 1 -maxdepth 1 -type d | wc -l`

### 1.2 当前 Skill 覆盖审计切片（`skill_tool_coverage_runtime.json`）

- 审计时间：`2026-04-06T17:01:46+00:00`
- 审计工具数：`113`
- Skills 总数：`19`
- Skill 工具引用覆盖率：`95.58%`
- Skill 执行器覆盖率：`100%`
- 当前缺口：`ai_workflow_artifact`、`analyze_research_report`、`get_research_summary`、`get_tool_contract`、`search_research_db`

说明：
1. `skill_tool_coverage_runtime.json` 是 Skill 覆盖审计切片，不是全量 MCP 工具总表。
2. 当前仓库里 “全量运行时工具数 155” 与 “Skill 覆盖审计工具数 113” 并不冲突，前者描述 MCP 注册面，后者描述 Skill 治理覆盖面。
3. `coverage` 代表 Skill 文档对这 113 个审计工具的引用覆盖率，不等价于“所有运行时工具都已纳入 Skill 路由”。
4. `executors` 代表 Skill 执行器覆盖率；当前 19 个 Skill 都有执行器，但不代表每个业务场景都不需要 manager/tool 级补充。
5. Windows-only 原生桌面集成能力当前不作为默认执行路径，任何流程都必须先以通用 MCP 工具链可用为前提。

技能/工具注册变更时的预检命令：
1. `PYTHONPATH=packages/akshare-mcp/src:packages/strategy-factory/src python3 -c "import akshare_mcp.server as s; m=s.mcp; print('tools', len(m._tool_manager.list_tools())); print('resources', len(m._resource_manager.list_resources())); print('prompts', len(m._prompt_manager.list_prompts()))"`
2. `python scripts/skill_coverage_audit.py --output-json skill_tool_coverage_runtime.json --output-gap skill_tool_gap_list.txt`
3. `python scripts/skill_coverage_audit.py --check-thresholds`

说明：
1. 第 1 条用于复核“全量注册面”，第 2/3 条用于复核“Skill 审计切片”。
2. 这组检查主要用于 skills/tool registry 变更、覆盖率治理和 CI 门禁，不应机械套用到所有业务功能任务。
3. 当前阈值基线文件 `.codex/skills/_meta/coverage_baseline.json` 仍记录旧基线；若运行时工具数继续扩容，应先重校准基线，再把 `--check-thresholds` 结果当作硬门禁。
4. 日常业务开发至少应重新生成 `skill_tool_coverage_runtime.json` 与 `skill_tool_gap_list.txt`，避免引用过期统计。

## 2. 总体执行原则（必须遵守）
1. 工具优先：能通过 MCP 工具获取结果时，不做主观臆测。
2. 编排优先：优先 manager 和流程化 skill，避免直接跳原子工具。
3. 证据优先：所有结论必须绑定工具输出、时间窗口、数据源。
4. 回退不停机：任一工具失败时，按 fallback 链继续推进并标注降级原因。
5. 安全边界：不伪造实盘成交、不绕过合规校验、不承诺收益。

## 3. Skills 路由规范
用户提到 skill，或请求语义明显命中 skill 描述时，必须走对应 skill。

常用路由：
- 行情/K线/盘口/涨停：`akshare-market`
- 基本面/估值/诊断/情绪：`akshare-fundamental`
- 资金流/新闻/公告/研报：`akshare-fund-news`
- 量化研究：`akshare-quant` + `akshare-quant-research-process`
- 顶级基金经理闭环：`akshare-fund-manager-pro`（必要时叠加 `akshare-portfolio-manager-core`）
- 宏观/期权/预警：`akshare-macro-options-alerts`
- 组合管理：`akshare-portfolio`

多 skill 命中时的顺序：
1. 全局编排：`akshare-fund-manager-pro`
2. 领域 skill：`market/fundamental/fund-news/quant`
3. 风险与组合：`portfolio/portfolio-manager-core/macro-options-alerts`

## 4. MCP 调用标准流程
1. 任务确认：标的、周期、时间窗口、复权口径、输出格式。
2. 标的归一：优先 `search_stocks` / `semantic_stock_search`。
3. 数据前置：涉及交易日对齐、时间窗口校验或批量 K 线准备时，再使用 `sync_trading_calendar` -> `get_trading_dates` -> 必要时 `batch_sync_klines`。
4. 分析执行：先 manager，再原子工具。
5. 风险合规：
   - 给出具体下单/执行建议前，必须执行 `compliance_manager(action=check_order)` 或同等合规检查；若仍处于研究/观察阶段，至少应说明尚未进入可下单状态。
   - 组合建议必须附 `risk_manager` 或 `analyze_portfolio_risk` 结果。
6. 结果留痕：需要沉淀日报/周报/月报或复盘材料时，按模板记录限制条件与回退说明；普通即时问答不要求强制落模板。

## 5. 顶级基金经理闭环门禁（强制）
“组合建议/调仓建议/实盘监控”类任务，至少覆盖以下 6 环：
1. 研究：`research_manager` / `event_manager`
2. 组合构建：`optimize_portfolio`
3. 风险评估：`risk_manager` 或 `analyze_portfolio_risk` + `stress_test_portfolio`
4. 合规检查：`compliance_manager`
5. 执行计划：`execution_manager`
6. 绩效复盘：`performance_manager` / `backtest_manager`

未满足 6 环，不得输出“可直接执行”的结论。

## 6. 量化研究门禁（强制）
按 `akshare-quant-research-process` 走阶段门禁：
1. 数据门禁（完整性/可交易性/口径一致）
2. 信号构建（指标/因子/特征）
3. 有效性检验（IC、分组、稳健性）
4. 组合构建与权重约束
5. 回测（含成本）
6. OOS 或滚动验证
7. 风险归因与压力测试
8. 报告留痕

成本参数（手续费、滑点、冲击、调仓频率）必须显式披露。

## 7. 失败补偿与降级规范
1. 外部数据源失败时，优先使用已实现的通用降级链，不因单源不可用直接终止任务。
2. 原生桌面集成或平台相关能力不可用时，统一降级到通用 MCP 路径：`watchlist_manager`、`alerts_manager`、市场数据工具与报告输出。
3. 不将“某个上游不可用”解释为“无交易机会”或“无法继续分析”。
4. 所有降级输出都必须显式写明 `fallback_reason`、可用数据窗口与影响范围。

## 8. 输出模板与质量要求
模板路径：
- 日报：`.codex/skills/akshare-fund-manager-pro/assets/templates/daily_report_template.md`
- 周报：`.codex/skills/akshare-fund-manager-pro/assets/templates/weekly_report_template.md`
- 月报：`.codex/skills/akshare-fund-manager-pro/assets/templates/monthly_report_template.md`

填写规则：`.codex/skills/akshare-fund-manager-pro/references/reporting_rules.md`

强制字段：
1. 数据窗口与交易日口径
2. 数据源与降级链说明
3. 核心风险指标（回撤、波动、VaR/CVaR 或等价指标）
4. 关键异常与处理动作
5. 下一步动作与触发条件

## 9. 深度联网检索规范（强制）
以下场景必须联网且优先官方一手来源：
1. MCP 协议/传输/授权/工具规范
2. 交易监管、披露规则、绩效展示规范
3. 回测成本、滑点、执行细节的规范化定义
4. 第三方数据源、SDK 或部署要求发生明显变化的场景

检索深度要求：
1. 单一主题至少交叉 `>=6` 个页面。
2. 至少 `>=3` 个官方一手来源（标准组织/监管机构/官方文档）。
3. 记录发布日期与访问日期；涉及“最新”必须核对日期。
4. 若来源冲突，采用“官方规范 > 官方文档 > 社区资料”的优先级。

禁止“浅搜即结论”。

## 10. MCP 安全与合规要求
结合 MCP 官方安全建议：
1. HTTP 传输默认仅绑定 `127.0.0.1`。
2. 启用来源校验（`Origin`）和鉴权；避免匿名高权限工具调用。
3. 禁止 token passthrough，访问令牌必须是签发给当前 MCP 服务的受众。
4. 高风险工具（交易、告警推送、文件下发）保留人工确认点。
5. 关键调用链可审计（参数、时间、返回状态、降级路径）。

金融表达规范：
- 明确“信息与分析辅助”定位，不承诺收益。
- 对高风险结论附前提条件、适用边界和反例风险。

## 11. 快速执行清单（给代理）
1. 若任务涉及 skills/tool registry 变更，先跑覆盖审计；普通业务任务至少刷新运行时审计结果。
2. 根据任务语义命中最小 skill 集合。
3. 先 manager 后原子工具，失败走 fallback。
4. 遇到平台相关原生能力时，默认走通用 MCP 替代链。
5. 输出时附数据窗口、来源、风险、限制与下一步。

## 12. 外部依据（本次联网检索）
- MCP Transports（2025-06-18）：https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- MCP Tools（2025-11-05）：https://modelcontextprotocol.io/specification/2025-11-05/server/tools
- MCP Prompts（2025-11-05）：https://modelcontextprotocol.io/specification/2025-11-05/server/prompts
- MCP Authorization（2025-11-05）：https://modelcontextprotocol.io/specification/2025-11-05/basic/authorization
- MCP Security Best Practices：https://modelcontextprotocol.io/docs/tutorials/security/security-best-practices
- QuantConnect Algorithm Framework：https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview
- Backtrader Commission Schemes：https://www.backtrader.com/docu/commission-schemes/commission-schemes/
- Backtrader Slippage：https://www.backtrader.com/docu/slippage/slippage/
- GIPS Standards for Firms：https://www.gipsstandards.org/standards/gips-standards-for-firms/
- IOSCO Public Reports：https://www.iosco.org/publications/?subsection=public-reports

## 13. 本地依据（项目事实）
- `README.md`
- `docs/README.md`
- `skill_tool_coverage_runtime.json`
- `skill_tool_gap_list.txt`
- `docs/171工具全量对话式深度测试任务.md`
- `packages/akshare-mcp/README.md`
- `packages/strategy-factory/README.md`
- `packages/akshare-mcp/start_server.py`
- `packages/akshare-mcp/src/akshare_mcp/server.py`
- `packages/akshare-mcp/src/akshare_mcp/tool_registry.py`
- `scripts/skill_coverage_audit.py`
