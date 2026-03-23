# Repo-Local Skills Sync Checklist

日期：2026-03-23

## 范围

- 只审查 repo-local skills：`.codex/skills/*/SKILL.md`
- 以代码为准对照：
  - `packages/akshare-mcp/src/akshare_mcp/tools/`
  - `packages/akshare-mcp/src/akshare_mcp/services/`
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/`
  - `packages/strategy-factory/src/strategy_factory/`
  - `apps/bff/src/`
  - `apps/web/app/`
- 不把文档、README 或 Skill 自述当成已实现能力

## 当前快照

- repo-local skills：19
- 现场审计结果：142/142 MCP tools 被覆盖，32/32 managers 被覆盖；19 个 repo-local skills 已全部与项目 runtime executors 对齐
- 已修正文档错配：
  - `akshare-portfolio-manager-core` 中错误的 `watchlist_manager(action=add)` 已改为 `watchlist_manager(action=add_stocks)`
  - `akshare-fund-manager-pro` 已补入真实存在但此前无人引用的统一决策工具链
  - `akshare-investor-protection`、`akshare-ips-discipline`、`akshare-macro-options-alerts` 已补充“仅有分域能力/缺少系统承载”的校准说明
  - 已新增 repo-local skills：`akshare-strategy-factory`、`akshare-factor-mining`
  - `.codex/skills/_meta/coverage_baseline.json` 已从旧的 20-skill / 153-tool 基线校准到当前真实的 19-skill / 142-tool / 32-manager 基线

## 状态定义

- `fully_implemented`：Skill 的核心流程已能在代码中找到对应 MCP 工具，并且主要 BFF / Web / 存储落点齐备
- `partially_implemented`：核心工具存在，但仍缺少统一入口、前端页面、持久化或某些关键步骤的产品化承载
- `not_implemented`：主要还是文本模板或人工流程，仓库里没有对应的数据模型、控制器或前端承载

## 同步清单

| Skill | 状态 | 主要代码证据 | 缺失组件 | 建议优先级 | 建议修改文件 |
| --- | --- | --- | --- | --- | --- |
| `akshare-market` | `fully_implemented` | MCP 市场工具齐全；BFF `apps/bff/src/market/market.controller.ts`；Web `apps/web/app/market/page.tsx`；存储 `schema_market.py` 含 `kline_1d` / `stock_quotes` / `market_blocks` / `block_stocks` | 无明显硬缺口 | 保持 | `apps/bff/src/market/market.controller.ts`, `apps/web/app/market/page.tsx`, `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/schema_market.py` |
| `akshare-portfolio` | `fully_implemented` | MCP 组合/回测/风险/压力测试工具齐全；BFF `portfolio` / `backtest` / `risk`；Web `apps/web/app/portfolio/page.tsx`, `apps/web/app/backtest/page.tsx`, `apps/web/app/risk/page.tsx`；存储 `schema_market.py` 含 `portfolios` / `holdings` / `backtest_*` | 无明显硬缺口 | 保持 | `apps/bff/src/portfolio/portfolio.controller.ts`, `apps/bff/src/backtest/backtest.controller.ts`, `apps/web/app/portfolio/page.tsx` |
| `akshare-asset-allocation` | `partially_implemented` | `optimize_portfolio` / `analyze_portfolio_risk` / `stress_test_portfolio` / `portfolio_manager` / `alerts_manager` 均存在 | 缺少资产配置/再平衡专用 BFF 入口；无再平衡计划持久化；前端无专页 | P2 | `apps/bff/src/portfolio/portfolio.controller.ts`, `apps/web/app/portfolio/page.tsx`, `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/schema_market.py` |
| `akshare-fee-costs` | `partially_implemented` | `run_simple_backtest` / `run_batch_backtest` / `backtest_manager` 存在 | 缺少费率敏感性专用接口与对比 UI；无成本情景结果留痕模型 | P2 | `apps/bff/src/backtest/backtest.controller.ts`, `apps/web/app/backtest/page.tsx`, `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/schema_market.py` |
| `akshare-factor-mining` | `partially_implemented` | `quant_manager` 已支持候选生成/验证/研究记忆/候选池治理；`packages/strategy-factory/src/strategy_factory/application/factor_research.py` 已构建研究 artifact；BFF `apps/bff/src/factor/factor.controller.ts` 已补齐挖掘类 API；Web 已有 `factor` / `factor-analysis` 页面 | 前端未形成候选生成 -> 验证 -> 入池 -> 研究记忆闭环；产品面仍以普通因子研究为主 | P1 | `apps/bff/src/factor/factor.controller.ts`, `apps/web/app/factor/page.tsx`, `apps/web/app/factor-analysis/page.tsx`, `packages/akshare-mcp/src/akshare_mcp/tools/managers/quant_manager.py`, `packages/strategy-factory/src/strategy_factory/application/factor_research.py` |
| `akshare-fund-manager-pro` | `partially_implemented` | 60 个引用工具均可在 MCP 注册中找到；Web 已有 `assistant`, `decision`, `strategy-market`, `portfolio`, `risk`, `paper-trading` 等分域页面 | 无统一“基金经理闭环”前端；BFF 无单一聚合控制器；`user_manager` / `event_manager` / `execution_manager` / `live_trading_manager` / `data_sync_manager` 仍是 MCP 直连或间接包装 | P1 | `apps/bff/src/skills/skills.controller.ts`, `apps/bff/src/assistant/assistant.controller.ts`, `apps/web/app/assistant/page.tsx`, `apps/web/app/decision/page.tsx`, `apps/web/app/strategy-market/page.tsx` |
| `akshare-fund-news` | `partially_implemented` | MCP 资金流/新闻/研报/公告工具存在；BFF `fund-flow` 与 `research` 控制器、Web `fund-flow` 与 `research` 页面存在 | `get_stock_text_signals`、`get_market_sentiment_context` 无直接 BFF/UI；未见新闻/公告专用持久化表 | P1 | `apps/bff/src/research/research.controller.ts`, `apps/bff/src/sentiment/sentiment.controller.ts`, `apps/web/app/research/page.tsx`, `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/schema_market.py` |
| `akshare-fundamental` | `partially_implemented` | MCP 基本面/估值/情绪/诊断工具存在；BFF `fundamental` / `valuation` / `assistant`；Web `fundamental`, `valuation`, `assistant`, `decision` 页面存在 | `parse_selection_query`、`get_investment_analysis`、`smart_stock_diagnosis` 没有统一落到基本面页面；能力散落在多个入口 | P1 | `apps/bff/src/fundamental/fundamental.controller.ts`, `apps/bff/src/assistant/assistant.controller.ts`, `apps/web/app/fundamental/page.tsx`, `apps/web/app/assistant/page.tsx` |
| `akshare-investor-protection` | `not_implemented` | 仅 `log_recommendation_audit` 有明确代码落点，且存储 `recommendation_audit_log` 已存在 | 无投资者保护专用服务、规则知识库、BFF 控制器、前端页面 | P2 | `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/schema_market.py`, `apps/bff/src/assistant/`, `apps/web/app/user/page.tsx` 或新增专页 |
| `akshare-ips-discipline` | `not_implemented` | `portfolio_manager` 只能提供持仓上下文 | 无 IPS 表结构、版本化、约束执行、BFF 控制器、Web 编辑器 | P1 | `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/schema_market.py`, `apps/bff/src/portfolio/`, `apps/web/app/user/page.tsx` 或新增 IPS 页面 |
| `akshare-macro-options-alerts` | `partially_implemented` | MCP 宏观/期权/情绪/告警工具存在；Web 有 `/macro`, `/data`, `/options`, `/alerts`, `/sentiment` 分域页面 | 缺少组合编排入口；BFF `alerts` 只覆盖 create/list/delete，未直接覆盖 combo/check 巡检 | P1 | `apps/bff/src/alerts/alerts.controller.ts`, `apps/bff/src/macro/macro.controller.ts`, `apps/bff/src/options/options.controller.ts`, `apps/web/app/data/page.tsx`, `apps/web/app/alerts/page.tsx` |
| `akshare-performance-attribution` | `partially_implemented` | `performance_manager` / `benchmark_manager` / `analyze_portfolio_risk` / `portfolio_manager` 工具存在；BFF 有 `risk` / `backtest` / `portfolio` | 无专门的 performance BFF 控制器与 Web 页面；绩效、归因、基准对比分散在多处 | P1 | `apps/bff/src/risk/risk.controller.ts`, `apps/bff/src/backtest/backtest.controller.ts`, `apps/web/app/portfolio/page.tsx`, `apps/web/app/risk/page.tsx` 或新增 performance 页面 |
| `akshare-portfolio-manager-core` | `partially_implemented` | 组合、风险、告警、纸面交易、策略市场均有代码落点；`watchlist_manager(action=add_stocks)` 已校正 | 无统一总控页；`user_manager` / `event_manager` / `execution_manager` / `live_trading_manager` / `data_sync_manager` 未在 BFF/Web 形成闭环 | P1 | `apps/bff/src/paper-trading/paper-trading.controller.ts`, `apps/bff/src/strategy/`, `apps/web/app/user/page.tsx`, `apps/web/app/paper-trading/page.tsx`, `apps/web/app/strategy-market/page.tsx` |
| `akshare-quant` | `partially_implemented` | MCP 技术/因子/相似检索工具存在；BFF `factor` / `technical` / `search`；Web `factor`, `technical`, `search` 页面存在 | `get_factor_profile`、`get_conditional_returns`、`get_signal_hit_rate`、`find_similar_patterns` 没有完整 BFF/UI 承载 | P1 | `apps/bff/src/factor/factor.controller.ts`, `apps/bff/src/search/search.controller.ts`, `apps/web/app/factor/page.tsx`, `apps/web/app/search/page.tsx` |
| `akshare-quant-data-engineering` | `partially_implemented` | `data_warmup` / `sync_kline_data` / `batch_sync_klines` / `data_sync_manager` 工具存在；存储含 `data_quality_issues` / `sync_tasks` / `sync_schedules` | Web `data` 页未覆盖数据质量/调度；BFF 无同步调度与质量问题视图 | P2 | `apps/bff/src/data/data.controller.ts`, `apps/web/app/data/page.tsx`, `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/schema_market.py` |
| `akshare-quant-methods-foundation` | `partially_implemented` | `analyze_portfolio_risk` / `optimize_portfolio` / `risk_manager` 可用 | 无相关性/协方差专门接口和前端；当前更多是风险摘要而非方法论面板 | P2 | `apps/bff/src/risk/risk.controller.ts`, `apps/web/app/risk/page.tsx` |
| `akshare-quant-ml-signals` | `partially_implemented` | 量化因子/指标/回测工具存在 | 仓库未见真正 ML 训练/特征仓/模型服务；当前更像“因子代理研究”而不是完整 ML signal pipeline | P2 | `packages/akshare-mcp/src/akshare_mcp/services/`, `apps/bff/src/factor/factor.controller.ts`, `apps/web/app/factor-analysis/page.tsx` |
| `akshare-quant-research-process` | `partially_implemented` | `quant_manager`, `technical_analysis_manager`, `validate_factor_oos`, `factor_robustness_check`, `backtest_manager` 等存在 | 无单一研究流水线控制器或前端；实验卡片/阶段通过结果没有统一展示 | P1 | `apps/bff/src/factor/factor.controller.ts`, `apps/web/app/factor-analysis/page.tsx`, `packages/strategy-factory/src/strategy_factory/application/factor_research.py` |
| `akshare-strategy-factory` | `partially_implemented` | BFF `apps/bff/src/strategy/strategy-factory.controller.ts`；Web `apps/web/app/strategy-market/page.tsx`；MCP `strategy_manager`；主实现 `packages/strategy-factory/src/strategy_factory/`；runtime skill executor 已映射 | 工厂运行、孵化、风控、向量治理仍分散在多个控制器/页面；尚无单一 skill 专属总控 UI | P1 | `.codex/skills/akshare-strategy-factory/SKILL.md`, `apps/bff/src/strategy/strategy-factory.controller.ts`, `apps/bff/src/strategy/strategy.service.ts`, `apps/web/app/strategy-market/page.tsx`, `packages/strategy-factory/src/strategy_factory/` |

## 横向专题：策略工厂

- 状态：`partially_implemented`
- 代码证据：
  - BFF 已有专门控制器：`apps/bff/src/strategy/strategy-factory.controller.ts`
  - BFF 另有配套控制器：`apps/bff/src/strategy/strategy.controller.ts`、`apps/bff/src/strategy/strategy-incubation.controller.ts`、`apps/bff/src/strategy/strategy-risk.controller.ts`、`apps/bff/src/strategy/strategy-vector.controller.ts`
  - Web 已有产品页：`apps/web/app/strategy-market/page.tsx` 与详情页目录 `apps/web/app/strategy-market/[id]/`
  - MCP/后端编排已落在 `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`
  - 主实现已沉淀到 `packages/strategy-factory/src/strategy_factory/`
- 当前结论：
  - 策略工厂在“项目代码”层面不是缺失，而是已经形成一套真实的 BFF/Web/MCP/包内实现。
  - 本次已补出独立 repo-local skill：`akshare-strategy-factory`，并已映射进项目 runtime `packages/akshare-mcp/src/akshare_mcp/tools/skills.py`。
  - 当前最接近的 project-side 高层承载仍是 `akshare-fund-manager-pro` 与 `akshare-portfolio-manager-core`，但现在“工厂专项 skill”已经存在。
- 缺失组件：
  - 缺少面向 skill 的工厂运行约束说明自动落到产品层，当前仍需从产品页面和 `strategy_manager` 反推
  - 缺少“skill -> strategy-market 页面 / BFF 接口 / MCP action” 的显式映射说明
- 建议优先级：`P1`
- 建议修改文件：
  - `.codex/skills/akshare-fund-manager-pro/SKILL.md`
  - `.codex/skills/akshare-portfolio-manager-core/SKILL.md`
  - `.codex/skills/akshare-strategy-factory/SKILL.md`
  - `apps/bff/src/strategy/strategy-factory.controller.ts`
  - `apps/web/app/strategy-market/page.tsx`

## 横向专题：因子挖掘

- 状态：`partially_implemented`
- 代码证据：
  - MCP 量化管理器已支持候选生成与治理：`packages/akshare-mcp/src/akshare_mcp/tools/managers/quant_manager.py`
  - 其中已存在 `llm_factor_mining`、`validate_factor_candidate`、`factor_research_memory`、`factor_candidate_registry`、`scheduler_status`、`scheduler_run_now`
  - 策略工厂内部已有因子研究 artifact 构建：`packages/strategy-factory/src/strategy_factory/application/factor_research.py`
  - BFF 已暴露因子研究基础接口：`apps/bff/src/factor/factor.controller.ts`
  - Web 已有因子研究页面：`apps/web/app/factor/page.tsx`、`apps/web/app/factor-analysis/page.tsx`
- 当前结论：
  - 因子挖掘在“底层研究能力”上是真实存在的，尤其是 MCP 与 `strategy_factory` 内部已经具备候选生成、验证、研究记忆和候选池治理。
  - 本次已补出独立 repo-local skill：`akshare-factor-mining`，并已映射进项目 runtime `packages/akshare-mcp/src/akshare_mcp/tools/skills.py`。
  - BFF 也已补出挖掘相关入口，但 Web 仍主要承载“普通因子研究”，当前最接近的既有 skill 仍是 `akshare-quant` 与 `akshare-quant-research-process`。
  - BFF/Web 目前主要承载“因子库、因子计算、IC、回测、OOS、稳健性检查”，还没有把 AI 因子挖掘、候选治理、研究记忆、调度控制完整产品化。
- 缺失组件：
  - 前端尚未直接承载 `llm_factor_mining`、`validate_factor_candidate`、`factor_research_memory`、`factor_candidate_registry` 的闭环交互
  - `apps/web/app/factor/page.tsx` / `apps/web/app/factor-analysis/page.tsx` 未形成“候选生成 -> 验证 -> 入池 -> 研究记忆”闭环 UI
  - 缺少与 `因子挖掘/` 目录文档一一对应的代码化产品入口
- 建议优先级：`P1`
- 建议修改文件：
  - `.codex/skills/akshare-quant-research-process/SKILL.md`
  - `.codex/skills/akshare-factor-mining/SKILL.md`
  - `apps/bff/src/factor/factor.controller.ts`
  - `apps/web/app/factor/page.tsx`
  - `apps/web/app/factor-analysis/page.tsx`
  - `packages/strategy-factory/src/strategy_factory/application/factor_research.py`
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/quant_manager.py`

## 建议实施顺序

1. P0 文档同步已完成：修正错 action、更新统一决策工具覆盖、刷新基线
2. P1 产品化补齐：优先收敛“高层编排 skill 但没有统一入口”的问题
   - `akshare-strategy-factory`
   - `akshare-factor-mining`
   - `akshare-fund-manager-pro`
   - `akshare-portfolio-manager-core`
   - `akshare-fund-news`
   - `akshare-fundamental`
   - `akshare-performance-attribution`
   - `akshare-quant`
   - `akshare-quant-research-process`
   - `akshare-ips-discipline`
3. P2 主题增强：再考虑流程型或教育型 skill 的产品化承载
   - `akshare-asset-allocation`
   - `akshare-fee-costs`
   - `akshare-investor-protection`
   - `akshare-macro-options-alerts`
   - `akshare-quant-data-engineering`
   - `akshare-quant-methods-foundation`
   - `akshare-quant-ml-signals`
