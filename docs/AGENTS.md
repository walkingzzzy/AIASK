# AIASK 项目 AGENTS 提示词（MCP + Skills + TDX）

> 适用目录：`c:\Users\1\Desktop\股票`  
> 更新时间：2026-02-12  
> 目标：让代理在本项目内稳定执行“投研 -> 组合 -> 执行 -> 风控 -> 复盘 -> TDX联动”闭环，并保持可审计、可回退、可复核。

## 1. 项目事实基线（本地审计结果）
- MCP 工具总数：`153`
- Skills 总数：`20`
- Skills 覆盖率：`100%`（`153/153`）
- TDX 工具覆盖：`36/36`
- Manager 工具覆盖：`31/31`
- 审计时间（文件）：`skill_tool_coverage_runtime.json` 中 `2026-02-12T08:24:34+00:00`

强制预检命令：
1. `python scripts/skill_coverage_audit.py --check-thresholds`
2. `python scripts/skill_coverage_audit.py --output-json skill_tool_coverage_runtime.json --output-gap skill_tool_gap_list.txt`

若阈值检查失败，先修复 skills/tool 映射、未知引用和缺口，再执行业务任务。

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
- TDX 运行态诊断：`akshare-tdx-runtime-ops`
- TDX 公式验证/条件选股：`akshare-tdx-formula-research`
- TDX 前端同步/推送：`akshare-tdx-front-sync`

多 skill 命中时的顺序：
1. 全局编排：`akshare-fund-manager-pro`
2. 领域 skill：`market/fundamental/fund-news/quant`
3. TDX 专项：`runtime-ops -> formula-research -> front-sync`

## 4. MCP 调用标准流程
1. 任务确认：标的、周期、时间窗口、复权口径、输出格式。
2. 标的归一：优先 `search_stocks` / `semantic_stock_search`。
3. 数据前置：`sync_trading_calendar` -> `get_trading_dates` -> 必要时 `batch_sync_klines`。
4. 分析执行：先 manager，再原子工具。
5. 风险合规：
   - 交易建议前必须执行 `compliance_manager(action=check_order)` 或同等合规检查。
   - 组合建议必须附 `risk_manager` 或 `analyze_portfolio_risk` 结果。
6. 结果留痕：结论写入日报/周报/月报模板，包含限制条件与回退说明。

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

## 7. TDX 交互强化规范（重点）
### 7.1 预检必做
任何 TDX 任务先执行 `akshare-tdx-runtime-ops`。

必须确认：
1. 客户端已启动并登录。
2. 插件路径和依赖可用（如 `TDX_PLUGIN_PATH`）。
3. 本地盘后数据包就绪（涉及 GP/BK/SC 字段时）。

### 7.2 推荐调用链
1. 运行态：`tdx_refresh_data`、`tdx_manage_subscription`、`tdx_list_available_fields`
2. 研究态：`tdx_get_formula_data` / `tdx_calculate_indicator` / `tdx_screen_stocks`
3. 联动态：`push_warn`、`send_backtest_result`、`send_backtest_trades`、`tdx_send_file`

### 7.3 失败补偿链
- TDX 失败时，降级到非 TDX 路径：`watchlist_manager` + `alerts_manager` + 市场数据工具。
- 保留待补发队列，客户端恢复后补发消息/回测可视化。
- 不将“TDX 不可用”解释为“无交易机会”。

场景模板：`.codex/skills/akshare-tdx-front-sync/references/scenario_templates.md`

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
2. TDX API 规则与版本变化
3. 交易监管、披露规则、绩效展示规范
4. 回测成本、滑点、执行细节的规范化定义

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
1. 跑覆盖审计并确认阈值通过。
2. 根据任务语义命中最小 skill 集合。
3. 先 manager 后原子工具，失败走 fallback。
4. 涉及 TDX 必先做 runtime-ops 预检。
5. 输出时附数据窗口、来源、风险、限制与下一步。

## 12. 外部依据（本次联网检索）
- MCP Transports（2025-06-18）：https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- MCP Tools（2025-11-05）：https://modelcontextprotocol.io/specification/2025-11-05/server/tools
- MCP Prompts（2025-11-05）：https://modelcontextprotocol.io/specification/2025-11-05/server/prompts
- MCP Authorization（2025-11-05）：https://modelcontextprotocol.io/specification/2025-11-05/basic/authorization
- MCP Security Best Practices：https://modelcontextprotocol.io/docs/tutorials/security/security-best-practices
- TdxQuant 简介：https://help.tdx.com.cn/quant/docs/markdown/mindoc-1cfsjkbf8f3is
- TdxQuant 常见问题：https://help.tdx.com.cn/quant/docs/markdown/mindoc-tdxpy.html
- TdxQuant 常量字典（市场/周期/复权）：https://help.tdx.com.cn/quant/docs/markdown/Dict.html
- TdxQuant 公式相关文档：https://help.tdx.com.cn/quant/docs/markdown/mindoc-u6th34v7x4h5ed7d.html
- TdxQuant 公式系统数据：https://help.tdx.com.cn/quant/docs/markdown/mindoc-7j4jq8x47d3rxvrl.html
- QuantConnect Algorithm Framework：https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview
- Backtrader Commission Schemes：https://www.backtrader.com/docu/commission-schemes/commission-schemes/
- Backtrader Slippage：https://www.backtrader.com/docu/slippage/slippage/
- GIPS Standards for Firms：https://www.gipsstandards.org/standards/gips-standards-for-firms/
- IOSCO Public Reports：https://www.iosco.org/publications/?subsection=public-reports

## 13. 本地依据（项目事实）
- `README.md`
- `skill_tool_coverage_runtime.json`
- `MCP_增强改造技术架构图与API改造清单.md`
- `MCP_股票分析能力测试用例清单_v1.md`
- `scripts/skill_coverage_audit.py`
