## 编码前检查 - 策略工厂P0状态语义统一
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-策略工厂P0状态语义统一.md`
- 将使用以下可复用组件：
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:_validate_transition`：统一状态校验入口
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:_lifecycle_scan`：验证孵化失败真实流转口径
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:update_strategy_status`：状态落库与事件审计统一收口
  - `apps/bff/src/strategy/strategy.service.ts:fetchRankingWithCache`：BFF 默认查询口径收口
- 将遵循命名约定：生命周期状态以 `listed` 为唯一上架态，`published` 仅保留兼容别名
- 将遵循代码风格：使用轻量 helper 进行状态归一，避免引入额外抽象层
- 确认不重复造轮子：已检查 `strategy_manager.py`、`storage/timescaledb/strategy.py`、`strategy.service.ts`、`apps/web/app/strategy-market/[id]/page.tsx`

## 编码后声明 - 策略工厂P0状态语义统一
时间：2026-03-06

### 1. 复用了以下既有组件
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:_validate_transition`：继续作为生命周期合法性校验入口
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:_lifecycle_scan`：保持真实扫描语义 `incubating -> deprecated`
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:update_strategy_status`：统一承接状态归一、落库与事件写入
- `apps/bff/src/strategy/strategy.service.ts:fetchRankingWithCache`：仅收口默认 ranking 状态，不扩散 BFF 改动面

### 2. 遵循了以下项目约定
- 命名约定：统一以 `listed` 为唯一上架态，`published` 仅作为兼容别名输入
- 代码风格：通过轻量 helper 归一状态，没有引入新的抽象层或旁路服务
- 文件组织：业务收口仍保持 `manager -> storage -> BFF -> test` 既有分层

### 3. 对比了以下相似实现
- `strategy_manager.py:_lifecycle_scan`：我保留了既有扫描逻辑，仅把常量表修正为与真实扫描一致
- `signal_tracker.py`：其本就只消费 `listed/incubating`，本轮实现与既有运行口径一致
- `schema.py`：沿用现有 `published -> listed` 迁移思路，并补齐状态事件表历史数据归一

### 4. 未重复造轮子的证明
- 检查了 `strategy_manager.py`、`storage/timescaledb/strategy.py`、`strategy.service.ts`、`test_strategy_factory_and_marketplace.py`
- 确认仓库中不存在更高层统一状态别名组件，因此在存储层新增最小归一 helper 是当前最收敛方案

### 5. 本地验证结果
- `pytest -o addopts='' packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py -q` → `74 passed`
- `diagnostics apps/bff/src/strategy/strategy.service.ts` → 无诊断问题

## 编码前检查 - 方案缺失补齐
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-方案缺失补齐.md`
- 将优先复用以下组件：
  - `packages/akshare-mcp/src/akshare_mcp/services/screen_engine.py`：条件评估
  - `packages/akshare-mcp/src/akshare_mcp/services/screen_conditions.py`：条件注册
  - `packages/akshare-mcp/src/akshare_mcp/tools/decision.py:get_investment_analysis`：数据汇聚
  - `packages/akshare-mcp/src/akshare_mcp/tools/factor_profile.py`：工具注册模板
- 将遵循命名约定：MCP 工具使用 `get_*` 风格，返回 `ok/fail`
- 将遵循代码风格：`register(mcp)` + `@mcp.tool()` 异步函数，工具层薄封装
- 确认不重复造轮子：已检查 `decision.py`、`factor_profile.py`、`vector.py`、`screen_engine.py`

## 当前实施计划
1. 在现有模块中补齐 `get_conditional_returns`
2. 将 `get_investment_analysis` 暴露为 MCP 工具
3. 补充测试覆盖工具注册与返回结构

## 编码后声明 - 第一批实现
时间：2026-03-06

### 1. 复用了以下既有组件
- `services/screen_engine.py`：用于条件评估
- `services/screen_conditions.py`：用于条件注册表加载
- `tools/decision.py:get_investment_analysis`：直接作为 MCP 工具暴露
- `tools/factor_profile.py` / `tools/vector.py`：沿用 `register(mcp)` 与 `ok/fail` 结构

### 2. 遵循了以下项目约定
- 命名约定：新增工具命名为 `get_conditional_returns`
- 代码风格：工具层薄封装，核心统计放入 `services/conditional_returns.py`
- 文件组织：服务逻辑在 `services/`，MCP 暴露在 `tools/`

### 3. 对比了以下相似实现
- `tools/factor_profile.py`：参考其工具注册与结构化返回
- `tools/vector.py`：参考其“工具层调服务层”的职责划分
- `tools/decision.py`：复用现有纯数据汇聚函数，而非新增重复入口

### 4. 未重复造轮子的证明
- 已检查 `decision.py`、`factor_profile.py`、`vector.py`、`screen_engine.py`
- 条件统计没有重复实现条件 DSL，而是直接复用选股条件引擎

### 5. 本地验证记录
- `pytest -o addopts='' packages/akshare-mcp/tests/test_prediction_enhancement.py -q` → `37 passed`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_tool_contract_check.py -q` → `8 passed`
- 说明：默认 `pytest.ini` 中存在 `--benchmark-disable`，本地缺少 benchmark 插件，因此通过 `-o addopts=''` 覆盖参数进行验证

## 编码后声明 - 第二批实现
时间：2026-03-06

### 1. 本批新增能力
- `tools/sentiment.py:get_market_sentiment_context`
- `tools/decision.py:should_i_buy` 在 `explain` 模式下附带 `analysis_context`

### 2. 复用了以下既有组件
- `tools/fund_flow.py:get_north_fund`
- `tools/fund_flow.py:get_margin_data`
- `tools/fund_flow.py:get_sector_fund_flow`
- `services.sentiment.sentiment_analyzer.calculate_fear_greed_index`
- `tools/decision.py:get_investment_analysis`

### 3. 遵循的项目约定
- 新增 MCP 工具继续使用 `register(mcp)` + `@mcp.tool()`
- 返回结构继续使用 `ok/fail`
- 聚合型工具以 best-effort 为原则，局部失败写入 `warnings/failed_modules`

### 4. 本地验证记录
- `pytest -o addopts='' packages/akshare-mcp/tests/test_prediction_enhancement.py -q` → `38 passed`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_tool_contract_check.py -q` → `8 passed`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_p0_regressions.py -q -k 'should_i_buy_industry_median_pe_path or should_i_buy_pe_expansion_fallback_when_peers_insufficient'` → `2 passed`

## 编码后声明 - 第三批实现
时间：2026-03-06

### 1. 本批新增能力
- `tools/sentiment.py:get_stock_text_signals`
- `services/backtest/engine.py` 新增高级绩效指标与基准对比指标
- `docs/metrics-contract.md` 同步扩展高级指标契约

### 2. 复用了以下既有组件
- `tools/news/news_feed.py:get_stock_news`

## 编码前检查 - 策略工厂文档更新
时间：2026-03-07

- 已查阅上下文摘要文件：`.claude/context-summary-策略工厂文档更新.md`
- 将使用以下既有证据来源：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py`：工厂主链路、AI 候选接入、提交后孵化/向量接线
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`：质量报告、事件流、孵化概览、向量/AI 查询动作
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py`：质量报告、状态事件、工厂运行历史、孵化与向量画像落库
  - `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`：本地测试侧证
- 将遵循命名约定：文档统一使用“已实现 / 部分实现 / 远期研究”口径，不把蓝图写成现状
- 将遵循文档风格：尽量保持原有结构，只修正过时陈述与排期优先级
- 确认不重复造轮子：本次只更新 `策略工厂/` 既有 MD 文档，不新增平行说明文档

## 编码后声明 - 策略工厂文档更新
时间：2026-03-07

### 1. 本批交付物
- `策略工厂/README.md`
- `策略工厂/01-系统架构设计文档.md`
- `策略工厂/03-模块功能方案.md`
- `策略工厂/04-策略生命周期管理流程图.md`
- `策略工厂/05-向量设计方案.md`
- `.claude/context-summary-策略工厂文档更新.md`
- `.claude/verification-report.md`

### 2. 复用了以下既有组件与证据
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py`：确认工厂主链路已含 `Autonomy`、向量复筛、提交后孵化/画像接线
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`：确认 `review_report`、`events`、`incubation_overview`、`factory_status`、`factory_runs` 等对外事实边界
- `packages/akshare-mcp/src/akshare_mcp/services/incubation.py`：确认孵化已不止“绑定账户”
- `packages/akshare-mcp/src/akshare_mcp/services/vector_platform.py`：确认策略画像与索引登记已存在
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py`：确认质量报告、状态事件、运行历史、孵化、向量画像已持久化

### 3. 遵循了以下项目约定
- 文档统一使用“当前已实现 / 部分实现 / 远期研究”口径
- 生命周期状态统一以 `listed` 为主状态，`published` 仅作为兼容别名说明
- 不把 `pgvector/HNSW`、完整 Event Sourcing、完整模拟盘 NAV 闭环、工业级 RL/LLM 自治工厂写成当前已实现

### 4. 未重复造轮子的证明
- 已检查 `strategy_factory.py`、`strategy_manager.py`、`incubation.py`、`vector_platform.py`、`strategy.py` 与对应测试
- 本轮仅收敛既有 `策略工厂/` 文档口径，没有新增平行方案文档或重复实现说明

### 5. 本地验证结果
- `pytest -o addopts='' tests/test_strategy_factory_and_marketplace.py -q` → `82 passed in 2.88s`
- `diagnostics 策略工厂/README.md 策略工厂/01-系统架构设计文档.md 策略工厂/03-模块功能方案.md 策略工厂/04-策略生命周期管理流程图.md 策略工厂/05-向量设计方案.md` → 无诊断问题

### 6. 当前结论
- `README/01/03/04/05` 已统一收敛为“代码事实优先”的现状口径
- 当前可表述为“轻量可运行工厂闭环 + 质量治理 + 生命周期管理 + 基础孵化/向量/AI 扩展层”
- 蓝图级能力仍保留为远期研究，不再混写成现状
- `tools/news/notices.py:get_stock_notices`
- `tools/news/research.py:get_research_reports`
- `services/llm_alpha.TextSignalPipeline`
- `services/backtest/engine.py` 既有权益曲线与核心指标口径

### 3. 本地验证记录
- `pytest -o addopts='' packages/akshare-mcp/tests/test_prediction_enhancement.py -q` → `39 passed`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_backtest_baselines.py -q` → `19 passed`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_tool_contract_check.py -q` → `8 passed`

### 4. 当前剩余缺口
- `should_i_buy / should_i_sell` 仍保留较多硬编码评分逻辑
- 当前已转为“混合模式”：评分结果 + analysis_context，但尚未完全达到纯数据汇聚式入口

## 编码后声明 - 第四批实现
时间：2026-03-06

### 1. 本批新增能力
- `should_i_sell` 追加 `decision_mode` 与 `analysis_context`
- 生成 `.claude/verification-report.md` 验证报告

### 2. 本地验证记录
- `pytest -o addopts='' packages/akshare-mcp/tests/test_prediction_enhancement.py -q` → `40 passed`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_p0_regressions.py -q -k 'should_i_buy_industry_median_pe_path or should_i_buy_pe_expansion_fallback_when_peers_insufficient'` → `2 passed`

## 编码后声明 - 第五批实现
时间：2026-03-06

### 1. 本批新增能力
- `should_i_buy` 改为优先使用 `analysis_context` 中的估值、基本面、技术、动量数据进行评分
- `should_i_sell` 改为优先使用 `analysis_context` 中的技术、风险数据进行评分
- 新增回归测试，验证在 SQL 明细查询不可用时，`should_i_buy` 仍可凭 `analysis_context` 正常给出建议

### 2. 本地验证记录
- `pytest -o addopts='' packages/akshare-mcp/tests/test_prediction_enhancement.py -q` → `41 passed`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_p0_regressions.py -q -k 'should_i_buy_industry_median_pe_path or should_i_buy_pe_expansion_fallback_when_peers_insufficient'` → `2 passed`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_tool_contract_check.py -q` → `8 passed`

## 编码后声明 - 第六批实现
时间：2026-03-06

### 1. 本批新增能力
- `should_i_buy / should_i_sell` 输出新增 `score_breakdown`、`signal_breakdown`
- 买卖决策入口进一步从“黑盒打分”收敛为“结构化证据聚合 + 轻量建议”
- `should_i_buy` 也将 `analysis_context` 作为稳定返回字段，不再仅在 explain 模式下附带

### 2. 本地验证记录
- `pytest -o addopts='' packages/akshare-mcp/tests/test_prediction_enhancement.py -q` → `41 passed`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_p0_regressions.py -q -k 'should_i_buy_industry_median_pe_path or should_i_buy_pe_expansion_fallback_when_peers_insufficient'` → `2 passed`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_tool_contract_check.py -q` → `8 passed`

## 编码后声明 - 第七批实现
时间：2026-03-06

### 1. 本批新增能力
- 修复 `.codex/skills/*/SKILL.md` 对新增工具和缺失管理器的引用，恢复 skill/tool 覆盖审计门禁
- 新增 `.claude/plan-implementation-mapping.md`，建立“方案条目 → 实现文件/测试文件/验证结果”映射

### 2. 本地验证记录
- `python scripts/skill_coverage_audit.py --check-thresholds` → `coverage=100.0%`、`missing=0`、`tdx=36/36`、`manager=32/32`
- `python scripts/skill_coverage_audit.py --output-json skill_tool_coverage_runtime.json --output-gap skill_tool_gap_list.txt` → 已生成最新审计产物

### 3. 当前注意事项
- 该批次结束时仍存在 `managers.py` 与 `tools/managers/__init__.py` 的模块命名冲突告警 1 条，后续已在第八批清理

## 编码后声明 - 第八批实现
时间：2026-03-06

### 1. 本批新增能力
- 删除历史兼容 shim：`packages/akshare-mcp/src/akshare_mcp/tools/managers.py`
- 保留 `packages/akshare-mcp/src/akshare_mcp/tools/managers/` 作为唯一 manager 注册入口，消除模块命名冲突

### 2. 本地验证记录
- `python scripts/skill_coverage_audit.py --check-thresholds` → `coverage=100.0%`、`missing=0`、`tdx=36/36`、`manager=32/32`、`collisions=0`
- `python scripts/skill_coverage_audit.py --output-json skill_tool_coverage_runtime.json --output-gap skill_tool_gap_list.txt` → 已生成最新审计产物，`module_name_collisions_count=0`
- `python - <<'PY' ... import akshare_mcp.server ... PY` → `server_import_ok True`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_tool_contract_check.py -q` → `8 passed`

### 3. 当前注意事项
- 导入 `akshare_mcp.server` 时仍会打印 TDX 插件路径缺失的环境警告，但不影响本轮命名冲突清理与工具注册验证

## 编码前检查 - 策略工厂P1质量报告复检入口
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-策略工厂P1质量报告复检入口.md`
- 将使用以下可复用组件：
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:_save_quality_report`：统一质量报告落库
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:_run_quality_gate`：统一质量门禁执行入口
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:StrategySubmitter.submit`：工厂提交主链路
  - `apps/web/hooks/use-api-mutation.ts`：POST + invalidate 现有模式
  - `apps/web/lib/query-keys.ts:apiKeys.strategy()`：`strategy-market` 模块级 query key 前缀
- 将遵循命名约定：manager action 使用 snake_case；新增报告类型使用 `recheck:<timestamp>`
- 将遵循代码风格：通过共享 helper 收口质量报告，不新增旁路服务或新表
- 确认不重复造轮子：已检查 `strategy_manager.py`、`strategy_factory.py`、`storage/timescaledb/strategy.py`、`apps/bff/src/strategy/*`、`apps/web/app/strategy-market/[id]/page.tsx`
- 说明：当前工具集中无 GitHub `search_code` 与 desktop-commander，本轮以仓库内相似实现和 Context7 官方文档替代，并在此留痕

## 编码后声明 - 方案缺口收口批次
时间：2026-03-06

### 1. 本批新增能力
- `tools/factor_profile.py`：补齐行业排名、市场分位、超卖恢复统计
- `tools/quant.py`：新增 `list_factors`、`find_similar_patterns`、`get_signal_hit_rate`
- `tools/decision.py`：增强 `get_investment_analysis`，`should_i_buy` 改为以 `analysis_context` 优先
- `tools/semantic/diagnosis.py`：从硬编码总分重构为证据聚合输出
- `services/strategy_factory.py`：接入 `FactorValidationPipeline` 与 `RiskModel`
- `services/backtest/advanced.py`：仓位管理改为回测循环内动态下单规模控制
- `.codex/skills/akshare-quant/*`：补齐新增工具映射，恢复审计通过

### 2. 复用了以下既有组件
- `services/validation.py:FactorValidationPipeline`
- `services/risk_model.py:RiskModel`
- `services/factor_calculator.*`
- `tools/vector.py` 的窗口相似度思想
- `tools/decision.py:get_investment_analysis` 既有数据汇聚结构

### 3. 差异与取舍
- `find_similar_patterns` 采用“同一股票历史窗口匹配”实现，优先保证可验证性与稳定返回
- 数据管道目录采用轻量实现，仅抽取当前重复最明显的截面统计与信号统计能力
- 验证/风险接线采用策略工厂内最小闭环方案，避免在本轮引入更大的离线任务系统

### 4. 本地验证记录
- `PYTHONPATH=src /opt/miniconda3/bin/pytest -o addopts='' tests/test_prediction_enhancement.py::TestPredictionEnhancementCompletion -q` → `4 passed`
- `PYTHONPATH=src /opt/miniconda3/bin/pytest -o addopts='' tests/test_strategy_factory_and_marketplace.py -q -k 'validation_and_risk_flags_can_trigger_elimination or submitter_persists_validation_and_risk_metrics'` → `2 passed`
- `PYTHONPATH=src /opt/miniconda3/bin/pytest -o addopts='' tests/test_prediction_enhancement.py -q` → `44 passed`
- `PYTHONPATH=src /opt/miniconda3/bin/pytest -o addopts='' tests/test_strategy_factory_and_marketplace.py -q` → `47 passed`
- `PYTHONPATH=src /opt/miniconda3/bin/pytest -o addopts='' tests/test_backtest_baselines.py -q` → `19 passed`
- `PYTHONPATH=src /opt/miniconda3/bin/pytest -o addopts='' tests/test_tool_contract_check.py -q` → `8 passed`
- `python scripts/skill_coverage_audit.py --check-thresholds` → `coverage=100.0%`, `missing=0`
- `python scripts/skill_coverage_audit.py --output-json skill_tool_coverage_runtime.json --output-gap skill_tool_gap_list.txt` → `coverage=100.0%`, `missing=0`

### 5. 未重复造轮子的证明
- 已优先检查并复用 `factor_profile.py`、`vector.py`、`validation.py`、`risk_model.py`、`factor_analysis.py`
- 新增逻辑尽量沉到 `services/data_pipeline/` 与策略工厂私有辅助函数，未再复制一套平行实现

## 编码前检查 - 虚拟盘方案补齐
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-虚拟盘方案补齐.md`
- 将优先复用以下组件：
  - `apps/web/app/market/layout.tsx`：页面 layout 元数据模板
  - `apps/web/app/factor/layout.tsx`：页面 layout 元数据模板
  - `apps/bff/src/portfolio/portfolio.controller.ts`：BFF 控制器风格模板
  - `packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py:get_batch_quotes_compat`：批量行情刷新
- 将遵循命名约定：MCP manager 继续使用 action 分发，返回 `ok/fail`
- 将遵循代码风格：Web layout 轻量透传、BFF 内联 DTO、测试沿用 `_DummyMCP + _FakeDB`
- 确认不重复造轮子：已检查 `paper_trading_manager.py`、`paper-trading.service.ts`、`market/layout.tsx`、`factor/layout.tsx`

## 编码前检查 - 修复171工具测试问题
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-修复171工具测试问题.md`
- 将优先复用以下组件：
  - `packages/akshare-mcp/src/akshare_mcp/tools/news/__init__.py`：统一新闻/公告/研报工具出口
  - `packages/akshare-mcp/src/akshare_mcp/tools/news/news_feed.py`：个股新闻降级链
  - `packages/akshare-mcp/src/akshare_mcp/tools/vector.py:search_by_kline`：行业优先、全市场回退候选池模式

## 编码前检查 - 策略工厂文档收敛
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-策略工厂文档收敛.md`
- 将优先复用以下组件：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py`：现有工厂闭环基线
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`：生命周期与质检口径
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py`：当前可持久化的数据边界
  - `packages/akshare-mcp/src/akshare_mcp/services/vector_search.py`：向量检索现状与演进边界
  - `apps/bff/src/strategy/strategy.controller.ts`：BFF 端点现状
- 将遵循命名约定：文档中区分“当前已实现 / 建议新增 / 中长期规划”，不把草案写成现状
- 将遵循代码风格：所有判断均以仓库现有实现为证据，外部资料仅用于说明演进可行性与边界
- 确认不重复造轮子：已检查 `strategy_factory.py`、`strategy_manager.py`、`strategy.py`、`vector_search.py`、`signal_tracker.py`、BFF strategy 模块
  - `packages/akshare-mcp/tests/archive/test_p1_relative_valuation_peer_filters.py`：估值类 FakeDB/monkeypatch 测试写法
- 将遵循命名约定：工具继续保持 `register(mcp)` / `register_xxx_manager(mcp)`，返回结构保持 `ok/fail`
- 将遵循代码风格：最小修复、不新增第三方依赖、回归测试继续沿用 `_DummyMCP + monkeypatch + _Acquire`
- 确认不重复造轮子：已检查 `search.py`、`vector.py`、`event_manager.py`、`valuation.py`、`news/news_feed.py`

## 当前实施计划 - 虚拟盘方案补齐
1. 补 `apps/web/app/paper-trading/layout.tsx` 与 `middleware.ts`
2. 修正前端页面中与方案冲突的卖出整手校验
3. 补 `paper_trading_manager.py` 的整手、T+1、涨跌停、`accounts` 别名、`update_prices`
4. 扩展 `test_p0_regressions.py` 并执行本地验证

## 编码后声明 - 虚拟盘方案补齐
时间：2026-03-06

## 编码前检查 - 修复171工具测试问题
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-修复171工具测试问题.md`
- 将优先复用以下组件：
  - `packages/akshare-mcp/src/akshare_mcp/tools/vector.py:search_by_kline`：候选池降级策略
  - `packages/akshare-mcp/src/akshare_mcp/tools/quant.py:SUPPORTED_FACTORS`：因子别名元数据
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/*`：kwargs 归一与 action 分发模式
  - `packages/akshare-mcp/tests/test_p0_regressions.py`：`_DummyMCP + monkeypatch + FakeDB` 回归测试模式
- 将遵循命名约定：继续使用 `register(mcp)` / `register_xxx_manager(mcp)` 与 `ok/fail`
- 将遵循代码风格：最小补丁修复契约偏差，不扩散到无关模块
- 确认不重复造轮子：已检查 `vector.py`、`valuation.py`、`quant.py`、`research_manager.py`、`sector_manager.py`、`market_insight_manager.py`、`comprehensive_manager.py`、`alerts_manager.py`

### 1. 本批新增能力
- `apps/web/app/paper-trading/layout.tsx`：补齐页面元数据布局
- `apps/web/middleware.ts`：补齐 `/paper-trading` 路由保护与 matcher
- `apps/web/app/paper-trading/page.tsx`：修正卖出也强制整手的前端校验偏差
- `paper_trading_manager.py`：补齐整手校验、T+1 `sellable`、卖出 T+1 限制、涨跌停校验、`accounts` 别名、`update_prices`
- `test_p0_regressions.py`：新增虚拟盘专项回归，覆盖 T+1、涨跌停、整手与价格刷新

### 2. 复用了以下既有组件
- `apps/web/app/market/layout.tsx`
- `apps/web/app/factor/layout.tsx`
- `apps/bff/src/portfolio/portfolio.controller.ts`
- `packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py:get_batch_quotes_compat`

### 3. 遵循了以下项目约定
- Next.js 页面元数据继续使用 `layout.tsx + Metadata`
- MCP manager 继续使用单工具 `action + kwargs` 分发模式
- 测试继续使用 `_DummyMCP + _FakeDB + monkeypatch` 风格

### 4. 未重复造轮子的证明
- 未新增新的虚拟盘服务层，而是在 `paper_trading_manager.py` 内补齐规则
- 批量价格刷新直接复用现有 `get_batch_quotes_compat`
- 页面元数据与路由保护沿用现有 Web 项目模式

### 5. 本地验证记录
- `PYTHONPATH=src /opt/miniconda3/bin/pytest -o addopts='' tests/test_p0_regressions.py -q -k paper_trading` → `4 passed, 15 deselected`
- `npm run typecheck -w apps/web` → `EXIT:0`
- `npm run build -w apps/web` → `EXIT:0`

### 6. 当前残余风险
- 尚未补 BFF 层 paper-trading 专项自动化测试
- `update_prices` 已在 MCP 动作层落地，但当前未新增显式 BFF API 暴露

## 继续补齐 - 虚拟盘价格刷新链路
时间：2026-03-06

### 1. 继续补齐范围
- BFF 新增 `POST /paper-trading/update-prices`
- 前端 `/paper-trading` 页面新增“刷新价格”按钮
- 刷新成功后自动失效 paper-trading 相关查询
- 页面持仓表显示 `sellable`

### 2. 改动文件
- `apps/bff/src/paper-trading/paper-trading.controller.ts`
- `apps/bff/src/paper-trading/paper-trading.service.ts`
- `apps/web/app/paper-trading/page.tsx`

### 3. 复用证明
- BFF 继续复用 `PaperTradingService.call()` 的统一 manager 调用封装
- 前端继续复用 `useApiMutation` 的 `invalidates` 机制
- 页面展示继续沿用 `DataTable` 与现有 KPI/Badge 风格

### 4. 本地验证结果
- `npm run build -w apps/bff` → `EXIT:0`
- `npm run typecheck -w apps/web` → `EXIT:0`
- `npm run build -w apps/web` → `EXIT:0`
- `PYTHONPATH=src /opt/miniconda3/bin/pytest -o addopts='' tests/test_p0_regressions.py -q -k paper_trading` → `4 passed, 15 deselected`

### 5. 更新后的残余风险
- 价格刷新链路已可用，但仍缺少 BFF 层契约测试
- 当前前端为手动刷新，尚未把 `update-prices` 纳入自动轮询策略

## 继续补齐 - 虚拟盘自动价格轮询
时间：2026-03-06

### 1. 目标
- 在 `/paper-trading` 页面接入交易时段内自动刷新价格
- 自动刷新保持静默，不弹成功提示
- 页面不可见时暂停自动刷新，降低无效请求

### 2. 实现方式
- 复用 `apps/web/lib/trading-hours.ts:isTradingHours`
- 保留手动刷新按钮的成功提示
- 新增静默 `autoRefreshPricesApi`，每 15 秒调用 `/paper-trading/update-prices`
- 使用 `ref` 同步最新 `accountId` 和刷新状态，避免 effect 反复重建 interval

### 3. 修改文件
- `apps/web/app/paper-trading/page.tsx`

### 4. 本地验证
- `npm run typecheck -w apps/web` → `EXIT:0`
- `npm run build -w apps/web` → `EXIT:0`

### 5. 当前效果
- 交易时段内页面自动刷新持仓价格
- 非交易时段保留手动刷新
- 页面顶部已展示自动刷新提示

## 编码前检查 - 个人功能方案补齐
时间：2026-03-06

### 1. 已查阅上下文摘要
- `.claude/context-summary-个人功能方案补齐.md`

### 2. 将复用的既有组件
- `apps/bff/src/auth/preferences.service.ts`：用户 preferences 持久化
- `apps/bff/src/audit/audit.store.ts`：审计日志 DB/内存双模式
- `apps/bff/src/watchlist/watchlist.service.ts`：按用户缓存与 MCP 调用模式
- `apps/web/lib/export.ts`：CSV 导出
- `apps/web/hooks/use-dashboard-prefs.ts`：本地 + 远端偏好同步模式
- `apps/web/components/notification-bell.tsx`：通知下拉 UI 骨架

### 3. 将遵循的项目约定
- BFF：NestJS `controller -> service -> storage/cache/MCP`
- Web：`PageContainer`、`SectionCard`、`KpiGrid`、`DataTable`、`useApiQuery/useApiMutation`
- 验证：优先 `npm run build -w apps/bff`、`npm run typecheck -w apps/web`、`npm run build -w apps/web`

### 4. 不重复造轮子的证明
- 已核对 `auth`、`watchlist`、`notification`、`audit`、`user`、`chat-store`、`export` 现状
- 已确认当前缺口主要为方案未落地，而非已有实现未复用

### 5. 五大任务拆分
- 认证与个人档案补齐
- 自选股与个人首页重构
- 通知与虚拟盘绩效补齐
- 安全日志与会话管理补齐
- 数据导出与聊天云同步及最终验证

## 编码后声明 - 个人功能方案补齐
时间：2026-03-06 10:55

### 1. 本批落地能力
- `apps/bff/src/auth/*`：补齐 profile 持久化、修改密码、会话列表与吊销。
- `apps/bff/src/audit/*`：新增 `GET /audit/my-logs`，支持按用户查看安全日志。
- `apps/bff/src/notification/*`：通知读写与列表按 `userId` 隔离。
- `apps/bff/src/paper-trading/*`：新增 `GET /paper-trading/performance`。
- `apps/bff/src/export/*`：新增 `GET /export/my-data`、`GET /export/report`。
- `apps/bff/src/chat/chat.controller.ts`：新增 `GET /chat/conversations`、`POST /chat/conversations/sync`。
- `apps/web/app/page.tsx`、`settings/page.tsx`、`paper-trading/page.tsx`：补齐个人首页、设置中心、绩效分析。
- `apps/web/store/chat-store.ts`：接入 `persist + createJSONStorage`，支持本地/云端会话合并与回传。
- `apps/web/components/onboarding.tsx` + `app-shell.tsx`：补齐首次登录轻量引导和 `data-tour` 锚点。

### 2. 复用了以下既有组件
- `PreferencesService`：承载 profile 与 chatHistory 持久化。
- `AuditStore`：扩展为 `listByUser`，沿用 DB/内存双模式。
- `PaperTradingService.call()`：统一复用 manager 调用封装。
- `useApiQuery / useApiMutation / authedFetch`：沿用前端既有请求与 token 刷新模式。
- `exportCSV`、`PageContainer`、`SectionCard`、`KpiGrid`、`DataTable`：保持页面风格一致。

### 3. 文档与实现依据
- 已对照 `docs/plans/个人功能开发方案.md` 的 P0-P3 缺口逐项补齐。
- 已参考 Context7 中 `zustand` 官方文档，按 `persist + createJSONStorage + onRehydrateStorage` 模式收敛 `chat-store.ts` 实现。

### 4. 本地验证记录
- `npm run build -w apps/bff; echo EXIT:$?` → `EXIT:0`
- `npm run typecheck -w apps/web; echo EXIT:$?` → `EXIT:0`
- `npm run build -w apps/web; echo EXIT:$?` → `EXIT:0`
- `node .claude/personal-feature-smoke.mjs` → 登录后成功验证 `chat sync`、`profile`、`sessions`、`audit`、`chat conversations`、`notifications`、`paper performance`、`export my-data`、`export report`

### 5. 残余风险
- `onboarding` 当前通过构建验证和代码审查确认，尚未补浏览器自动化测试。
- 通知推送链路已可用，但仍缺少专门的 WebSocket 自动化测试。

## 继续补充 - 个人功能方案验收映射
时间：2026-03-06 11:00

### 1. 新增交付物
- `.claude/plan-implementation-mapping-个人功能方案.md`

### 2. 用途
- 将 `docs/plans/个人功能开发方案.md` 的 2.1-2.12 条目逐项映射到实现文件与验证证据。
- 作为后续 Git 提交、人工复核或方案验收时的快速索引。

## 对话式测试收口 - akshare-stock 171工具专项
时间：2026-03-06 11:45

### 1. 本轮收口动作
- 再次调用 `available_tools` 核对当前工具总数，确认 `count=171`。
- 读取并回填 `.claude/akshare-stock-171工具对话式测试报告.md`。
- 追加 `.claude/verification-report.md` 的专项审查结论。
- 同步任务列表，将 171 工具测试相关子任务全部收口。

### 2. 工具级统计口径
- 通过：151
- 受限通过：18
- 失败：2
- 备注：以上按“工具级主调用口径”统计；manager/action 级契约偏差不重复计入失败。

### 3. 关键结论
- 非 TDX 主链路整体可用，行情、公告、研报、回测、组合、manager 等大部分工具可直接返回结构化结果。
- TDX 原生依赖链当前不可用，统一诊断为 `TDX plugin path does not exist: C:\new_tdx_test\PYPlugins\user`；相关工具按受限通过处理。
- `run_skill` 已覆盖三种真实行为：
  - `akshare-market`：编排成功
  - `akshare-fund-manager-pro`：六环闭环成功
  - `akshare-fundamental`：注册存在但 `no_handler`

### 4. 明确缺陷
- `get_historical_valuation`：字段 `pe` 缺失导致失败。
- `search_similar_stocks`：`industry=None` 导致失败。

### 5. 重要契约偏差
- `relative_valuation` 默认同行路径失败，但显式 `peers` 可成功。
- `paper_trading_manager(update_prices)` 失败时 `error` 为空。
- `research_manager(get_reports)` 未尊重 `limit`。
- `sector_manager(sector_rotation)` 返回周期与请求不一致。
- `market_insight_manager(sector_analysis)` 命中质量不足。
- `comprehensive_manager(quick_scan)` 扫描范围超出指定代码。
- `alerts_manager(update)` 状态流转不透明。

### 6. 收口补测
- `clear_cache()`：成功，`cleared_count=0`。
- `clear_dead_letters()`：成功，`removed=0`。
- `get_cache_stats()`：复核空缓存状态正常，`file_count=0`。

## 修复171工具测试发现问题 - 编码后声明
时间：2026-03-06 12:20

### 1. 本轮完成的修复
- `get_historical_valuation`：`stock_quotes` 查询异常不再中断主流程，改为保留 `fallback_reason` 并继续走降级链。
- `search_similar_stocks`：`industry` 为空或无同业候选时，回退到全市场候选池，并补充 `candidate_scope` 审计字段。
- `calculate_factor`：补齐 `rsi`、`momentum_20d` 等别名归一，恢复常见口语化因子名兼容。
- `paper_trading_manager(update_prices)`：失败时补默认错误文案，避免 `error` 为空字符串。
- `research_manager(get_reports)`：补 `limit` 归一与边界控制。
- `sector_manager`：兼容 `days/period` 参数映射。
- `market_insight_manager(sector_analysis)`：兼容 JSON `kwargs`，支持按 `sector/block_name/name` 过滤，并修复 `matchedCount` 重复计数。
- `comprehensive_manager(quick_scan)`：单个 `code` 输入现在会被优先识别，不再错误扩散到默认样本池。
- `alerts_manager(update)`：未显式传状态时保持原状态，避免隐式改为 `inactive`。
- `decision.should_i_buy`：仅当当前推荐为 `hold/wait` 时才允许 `analysis_context` 覆盖，避免弱上下文压制强买入信号。
- `test_p0_regressions.py`：同步修正 `tdx_get_financial_snapshot` 的异步测试契约。

### 2. 复用了以下既有组件
- `packages/akshare-mcp/src/akshare_mcp/tools/vector.py::search_by_kline` 的候选池降级模式。
- `packages/akshare-mcp/src/akshare_mcp/tools/valuation.py` 既有的 `source_chain / fallback_reason / data_quality` 审计结构。
- `packages/akshare-mcp/src/akshare_mcp/tools/quant.py::SUPPORTED_FACTORS` 的 canonical/aliases 元数据。
- 各 manager 文件既有的 `_normalize_kwargs` / `ok(...)` / `fail(...)` 轻量兼容模式。

### 3. 遵循的项目约定
- 返回结构保持 `ok(...) / fail(...)`，未改动工具对外主协议。
- 继续沿用 `register(mcp)` / `register_xxx_manager(mcp)` 的工具注册模式。
- manager 入口继续兼容 `kwargs="{}"` 的 JSON 字符串形态。
- 测试沿用 `pytest + monkeypatch + _DummyMCP/FakeDB` 的现有模式，没有引入新测试框架。

### 4. 与相似实现的差异说明
- `search_similar_stocks` 并未新造检索方案，而是直接借用 `search_by_kline` 的“行业优先、全市场兜底”思路，只补充候选范围标记。
- `get_historical_valuation` 未重写数据库访问层，只在 `stock_quotes` 查询点做最小异常捕获，保持现有降级链和返回结构不变。
- manager 契约修复均采用局部归一函数收敛，不改变各 manager 的 action 协议。
- `should_i_buy` 仅调整“上下文结论覆盖优先级”，保留原有 `analysis_context` 证据合并能力。

### 5. 未重复造轮子的证明
- 已对 `vector.py`、`valuation.py`、`quant.py`、`market_insight_manager.py`、`research_manager.py`、`sector_manager.py`、`alerts_manager.py` 的相似模式做复用比对。
- 本轮未新增新的公共基类、工具层框架或第三方依赖；全部为既有实现上的最小补丁。

### 6. 本地验证结果
- `pytest -o addopts='' packages/akshare-mcp/tests/test_p0_regressions.py -q -k 'test_p0_3b_paper_trading_update_prices_should_fill_default_error or test_p0_7b_historical_valuation_should_fallback_when_db_query_breaks or test_p0_10_search_similar_stocks_should_fallback_to_market_candidates or test_p0_11_calculate_factor_should_accept_aliases or test_p0_12_research_manager_should_normalize_limit or test_p0_13_sector_manager_should_accept_days_alias or test_p0_14_market_insight_sector_analysis_should_filter_requested_sector or test_p0_15_comprehensive_manager_quick_scan_should_honor_single_code or test_p0_16_alerts_manager_update_should_preserve_status_when_status_missing'` → `9 passed, 19 deselected`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_p0_regressions.py -q -k 'test_p0_5_tdx_financial_snapshot_fallback_from_empty_tdx or test_p0_8_should_i_buy_industry_median_pe_path or test_p0_8b_should_i_buy_pe_expansion_fallback_when_peers_insufficient'` → `3 passed, 25 deselected`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_p0_regressions.py -q` → `28 passed`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_prediction_enhancement.py -q -k 'test_should_i_buy_can_score_from_analysis_context_when_sql_unavailable or test_should_i_sell_contains_analysis_context'` → `2 passed, 43 deselected`

### 7. 当前结论
- 171 工具对话式测试暴露的 2 个明确失败项已完成修复并通过本地回归。
- 已列出的 manager/action 契约偏差本轮已完成主要收口。
- 当前残余风险主要集中于本地 TDX 原生环境缺失；`relative_valuation` 默认同行选择仍可作为后续低优先级兼容性优化项。


## 编码后声明 - 修复171工具测试问题（真实场景缺陷批次）
时间：2026-03-06

### 1. 本批修复内容
- `tools/search.py`：补齐 `search_stocks` 的行业字段召回，并同步修复 Tushare fallback 的行业匹配
- `tools/vector.py`：调整 `semantic_stock_search` 打分，降低“龙头”等泛化词导致的名称误配
- `tools/managers/event_manager.py`：为 `get_by_code/get_events` 增加新闻/公告/研报聚合降级链
- `tools/valuation.py`：为 `relative_valuation` 增加“行业为空或同行业为空 → 全市场市值近邻回退”

### 2. 复用了以下既有组件
- `tools/news/__init__.py`：统一新闻/公告/研报工具出口
- `tools/news/news_feed.py`：沿用新闻→公告→研报的降级链路
- `tools/vector.py:search_by_kline`：沿用行业优先、全市场回退的候选池策略
- `tests/archive/test_p1_relative_valuation_peer_filters.py`：沿用估值类 FakeDB/monkeypatch 回归模式

### 3. 遵循的项目约定
- 工具与 manager 继续保持 `register(mcp)` / `register_xxx_manager(mcp)` 模式
- 返回结构继续保持 `ok/fail`
- 新增测试继续收敛到 `packages/akshare-mcp/tests/test_p0_regressions.py`

### 4. 本地验证记录
- `pytest -o addopts='' tests/test_p0_regressions.py -q -k 'p0_17 or p0_18 or p0_19 or p0_20 or p0_21'` → `5 passed, 28 deselected`
- `pytest -o addopts='' tests/test_p0_regressions.py -q` → `33 passed`
- `pytest -o addopts='' tests/test_tool_contract_check.py -q` → `8 passed`

### 5. 剩余风险
- `semantic_stock_search` 当前已显著降低“泛化词误配”，但仍属于规则加权排序，不是更重型的语义检索方案
- `event_manager` 现阶段优先保障“按代码查询时至少有资讯内容可用”，不同事件类型的字段统一仍有继续细化空间

## 编码前检查 - 修复 semantic_stock_search 行业词召回
时间：2026-03-06

□ 已查阅上下文摘要文件：`.claude/context-summary-修复171工具测试问题.md`
□ 将使用以下可复用组件：
  - `packages/akshare-mcp/src/akshare_mcp/tools/search.py::_search_stocks_tushare_fallback`：复用现有行业关键词 fallback 召回
  - `packages/akshare-mcp/src/akshare_mcp/tools/vector.py::_GENERIC_SEMANTIC_HINTS`：继续沿用泛化词降权约束
  - `packages/akshare-mcp/src/akshare_mcp/tools/semantic/industry_chain.py`：参考行业关键词匹配思路
□ 将遵循命名约定：保持工具函数与局部 helper 的英文命名，返回结构继续使用 `ok/fail`
□ 将遵循代码风格：延续当前工具文件内局部 helper + 小步降级策略，不引入新依赖
□ 确认不重复造轮子，证明：已检查 `search.py`、`vector.py`、`industry_chain.py`、`query_parser.py`，当前不存在可直接复用的“行业词 + 泛化词”组合召回实现

## 编码后声明 - 修复 semantic_stock_search 行业词召回
时间：2026-03-06

### 1. 本次修复内容
- `packages/akshare-mcp/src/akshare_mcp/tools/vector.py`：为 `semantic_stock_search` 增加“泛化词场景下的行业词提取”
- `packages/akshare-mcp/src/akshare_mcp/tools/vector.py`：增加行业专用 DB 召回、Tushare fallback 召回、板块成分股补召回，并与原结果统一去重
- `packages/akshare-mcp/tests/test_p0_regressions.py`：将 `p0_19` 调整为更贴近 live 问题的回归场景

### 2. 复用了以下既有组件
- `packages/akshare-mcp/src/akshare_mcp/tools/search.py::_search_stocks_tushare_fallback`：复用现有行业关键词回退能力，避免重复实现 Tushare 股票列表过滤
- `packages/akshare-mcp/src/akshare_mcp/tools/vector.py::_GENERIC_SEMANTIC_HINTS`：继续使用既有泛化词集合约束召回策略
- `packages/akshare-mcp/src/akshare_mcp/tools/semantic/industry_chain.py`：参考行业关键词匹配的轻量模式

### 3. 遵循的项目约定
- 工具注册与返回结构未变，继续保持 `register(mcp)` 与 `ok/fail`
- 新逻辑仅在 `semantic_stock_search` 内部追加局部 helper，不扩散到其他工具
- 测试继续收敛在 `packages/akshare-mcp/tests/test_p0_regressions.py`

### 4. 本地验证记录
- `pytest -o addopts='' tests/test_p0_regressions.py -q -k 'p0_19'` → `1 passed, 32 deselected`
- `pytest -o addopts='' tests/test_p0_regressions.py -q` → `33 passed`
- `pytest -o addopts='' tests/test_tool_contract_check.py -q` → `8 passed`

### 5. 当前结论
- `semantic_stock_search` 已补齐“行业词 + 泛化词”场景的行业优先召回路径
- 本地回归已证明 `白酒龙头` 不再只依赖名称中“龙头”的误召回路径
- 仍需在你重启最新 MCP 服务后再做一次 live 复测，确认运行实例已加载本轮新逻辑

## 编码后声明 - 策略工厂文档收敛
时间：2026-03-06

### 1. 本批交付物
- `策略工厂/README.md`
- `策略工厂/01-系统架构设计文档.md`
- `策略工厂/02-接口定义与数据模型.md`
- `策略工厂/03-模块功能方案.md`
- `策略工厂/04-策略生命周期管理流程图.md`
- `策略工厂/策略工厂系统设计与实现.md`（仅补定位说明）
- `.claude/context-summary-策略工厂文档收敛.md`
- `.claude/verification-report.md`

### 2. 复用了以下既有组件与证据
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py`：工厂闭环、调度状态、去重与淘汰基线
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`：生命周期状态机、质量门禁、生命周期扫描
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py`：当前持久化对象边界
- `packages/akshare-mcp/src/akshare_mcp/services/vector_search.py`：向量检索现状与中期演进边界
- `packages/akshare-mcp/src/akshare_mcp/services/signal_tracker.py`：信号与前向收益链路
- `apps/bff/src/strategy/strategy.controller.ts` / `strategy.service.ts`：当前 BFF 端点事实边界

### 3. 遵循的项目约定
- 文档统一区分“当前已实现 / 运行时对象 / 草案 / 中长期规划”
- 生命周期状态口径统一以 `LIFECYCLE_TRANSITIONS` 为准
- 研究报告保留为蓝图，不再与实施说明混写
- 外部资料只用于说明可行性与演进边界，不倒逼代码事实

### 4. 对比的相似实现
- `strategy_factory.py`：确认工厂主链路已经存在
- `strategy_manager.py`：确认质量门禁和生命周期规则已实现
- `strategy.py`：确认已持久化与未持久化对象边界
- `vector_search.py`：确认向量检索已有基础但尚未接入工厂
- `strategy.controller.ts`：确认当前已暴露端点与缺失端点

### 5. 未重复造轮子的证明
- 已检查工厂、生命周期、存储、向量检索、信号跟踪、BFF strategy 模块
- 本轮没有新增任何并行“自研状态机 / 自研工厂接口体系”，只是在既有边界上重写文档口径

### 6. 本地验证记录
- `git diff --check -- 策略工厂 .claude/context-summary-策略工厂文档收敛.md .claude/operations-log.md .claude/verification-report.md` → 无格式错误输出
- `git status --short -- 策略工厂 .claude/context-summary-策略工厂文档收敛.md .claude/operations-log.md .claude/verification-report.md` → `.claude/operations-log.md`、`.claude/verification-report.md` 为修改态；`策略工厂/` 目录与 `.claude/context-summary-策略工厂文档收敛.md` 为未跟踪项
- `python3` 文件存在性校验 → 目标 9 个文件全部存在
- `python3` 文档口径校验 → `01/03/04` 未出现研究报告状态别名；`02` 仅在“文档中不再使用这些状态名”的说明中提及

### 7. 当前结论
- `README` 与 `01-04` 已统一收敛为“现状 + 缺口 + 分期演进”口径
- `策略工厂系统设计与实现.md` 已增加“研究蓝图”定位说明
- 当前主要残余风险不是文档内容本身，而是 `策略工厂/` 在仓库中仍属于未跟踪目录，后续若要正式纳入版本管理，需由你决定是否加入 git 跟踪

## 编码前检查 - 向量设计方案
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-向量设计方案.md`
- 将优先复用以下组件：
  - `策略工厂/README.md`：文档分层与现状边界
  - `策略工厂/02-接口定义与数据模型.md`：已实现/运行时对象/草案写法
  - `策略工厂/03-模块功能方案.md`：短期/中期/远期表达方式
  - `packages/akshare-mcp/src/akshare_mcp/services/vector_search.py`：向量能力现状证据
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py`：工厂去重接入点
- 将遵循命名约定：文档统一使用简体中文，明确区分“已实现 / 运行时对象 / 草案 / 中长期规划”
- 将遵循代码风格：以代码事实优先，不把 `pgvector/HNSW` 和策略行为向量写成当前已实现
- 确认不重复造轮子：已检查 `README`、`02`、`03`、`vector_search.py`、`tools/vector.py`、`strategy_factory.py`

## 编码后声明 - 向量设计方案
时间：2026-03-06

### 1. 本批交付物
- `策略工厂/05-向量设计方案.md`
- `.claude/context-summary-向量设计方案.md`
- `.claude/operations-log.md`
- `.claude/verification-report.md`

### 2. 复用了以下既有组件与证据
- `策略工厂/README.md`：沿用文档分层，明确新文档属于落地方案
- `策略工厂/02-接口定义与数据模型.md`：沿用对象分层和草案字段表达
- `策略工厂/03-模块功能方案.md`：沿用“当前/短期/中期/远期”分期结构
- `packages/akshare-mcp/src/akshare_mcp/services/vector_search.py`：确认当前是行情形态向量 + 进程内索引 + DTW
- `packages/akshare-mcp/src/akshare_mcp/tools/vector.py`：确认当前对外返回字段与后端标识

### 3. 遵循了以下项目约定
- 文档没有把研究蓝图写成现状说明
- 明确区分“当前已实现 / 运行时对象 / 草案 / 中长期规划”
- 统一把向量能力落脚到工厂去重接线，而不是泛泛讨论向量数据库

### 4. 未重复造轮子的证明
- 已检查 `策略工厂/` 现有 6 份文档与 `vector_search.py`、`tools/vector.py`
- 新文档没有新造并行架构，而是直接围绕现有 `Deduplicator` 和 `vector_search.py` 做增量设计

### 5. 本地验证记录
- `git diff --check -- 策略工厂/05-向量设计方案.md .claude/context-summary-向量设计方案.md .claude/operations-log.md .claude/verification-report.md` → 无格式错误输出
- `python3` 文件存在性校验 → `EXISTS_OK 4`
- `python3` 文档口径校验 → `has_current_boundary=True`、`has_pgvector_future=True`、`has_deduplicator=True`、`has_pattern_cache=True`

## 编码前检查 - 完整实现策略工厂
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-完整实现策略工厂.md`
- 将优先复用以下组件：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py`：工厂主链路与 `_build_strategy_panels()`
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`：质量门禁与生命周期口径
  - `packages/akshare-mcp/src/akshare_mcp/services/vector_search.py`：进程内向量检索复筛
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py`：策略域持久化入口
- 将遵循命名约定：继续沿用 `action + kwargs`、`ok/fail`、BFF `controller -> service`、Web `useApiQuery/useApiMutation`
- 将遵循代码风格：增量补齐，不脱离现状大重构
- 确认不重复造轮子：已检查 `strategy_factory.py`、`strategy_manager.py`、`strategy.py`、`schema.py`、`vector_search.py`、BFF/Web 策略页面

## 编码后声明 - 完整实现策略工厂
时间：2026-03-06

### 1. 本批新增能力
- `strategy_quality_reports`：质量门禁结果、验证摘要、风险摘要、去重说明独立落库
- `strategy_status_events`：状态流转 append-only 事件审计
- `Deduplicator`：结构化重复原因 + 向量复筛接线
- `StrategyFactoryScheduler`：结构化运行摘要、失败结果、手动触发返回对象
- `strategy_manager`：新增 `factory_status`、`factory_run_once`、`review_report`、`events`、`incubation_overview`
- BFF/Web：新增工厂状态、审查报告、事件流、孵化概览展示

### 2. 复用了以下既有组件
- `strategy_factory.py:_build_strategy_panels()`：复用为行为向量序列基础
- `strategy_manager.py:_run_quality_gate()`：继续作为统一质量门禁实现
- `vector_search.py:VectorSearchEngine`：复用进程内索引和 fallback 机制
- `test_strategy_factory_and_marketplace.py`：沿用 `_DummyMCP + _StrategyDB + monkeypatch` 测试模式

### 3. 遵循了以下项目约定
- 第一阶段不引入 `pgvector/HNSW`、完整 Event Sourcing、模拟盘闭环
- 向量去重明确采用“参数筛疑点 + 行为向量复筛”的渐进方案
- BFF/Web 只做增量端点和页面补齐，不重写现有策略超市架构

### 4. 未重复造轮子的证明
- 已优先检查并复用 `strategy_factory.py`、`strategy_manager.py`、`vector_search.py`、`strategy.py`
- 质量报告未再塞回固定指标表，而是新增独立报告对象，避免重复和错配

### 5. 本地验证记录
- `PYTHONPATH=src /opt/miniconda3/bin/pytest -o addopts='' tests/test_strategy_factory_and_marketplace.py -q` → `72 passed`
- `npm run build -w apps/bff` → `EXIT:0`
- `npm run typecheck -w apps/web` → `EXIT:0`
- `npm run build -w apps/web` → `EXIT:0`

## 编码前检查 - 工厂运行历史持久化
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-工厂运行历史持久化.md`
- 将优先复用以下组件：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py`：`run_once()` 结构化结果对象
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py`：JSONB 持久化模式
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`：`action + kwargs` 分发
  - `apps/bff/src/strategy/*`：factory 路由转发模式
  - `apps/web/app/strategy-market/page.tsx`：工厂运行态卡片渲染点
- 将遵循命名约定：继续沿用 `save_* / list_* / get_*` 与 `factory_*` action 命名
- 将遵循代码风格：只补运行历史持久化与查询，不重构调度主链路
- 确认不重复造轮子：已检查 `run_once()`、`save_daily_snapshot()`、`save_strategy_quality_report()`、`list_strategy_status_events()`、factory BFF/Web 现有实现

## 编码后声明 - 工厂运行历史持久化
时间：2026-03-06

### 1. 本批新增能力
- `strategy_factory_runs`：持久化工厂运行历史，保存 `run_id/status/summary/stages/snapshot_summary/error`
- `StrategyFactoryScheduler.run_once()`：结束后自动写入运行历史
- `strategy_manager`：新增 `factory_runs` action；`factory_status` 可回退读取最近一次落库记录
- BFF：新增 `GET /strategy-market/factory/runs`
- Web：策略超市页新增“最近运行历史”列表

### 2. 复用了以下既有组件
- `strategy.py` 中既有 JSONB 持久化模式，未另造一套运行历史存储框架
- `strategy_factory.py` 现有 `results` 对象结构，直接复用为落库对象
- `test_strategy_factory_and_marketplace.py` 既有 fake DB / monkeypatch 测试模式

### 3. 遵循了以下项目约定
- 继续采用增量式 DDL + `StrategyMixin` 读写方法
- BFF 沿用 `controller -> service -> manager action` 结构
- Web 继续沿用 `useApiQuery` 与列表页卡片扩展模式

### 4. 未重复造轮子的证明
- 没有新建独立运行日志子系统，而是复用现有策略域存储层扩展 `strategy_factory_runs`
- 没有把历史查询塞进 `status()` 本体做同步 DB 访问，而是在 manager 层做回退拼装

### 5. 本地验证记录
- `PYTHONPATH=src /opt/miniconda3/bin/pytest -o addopts='' tests/test_strategy_factory_and_marketplace.py -q` → `73 passed`
- `git diff --check -- ...` → 通过
- IDE `diagnostics`（strategy_factory / strategy_manager / strategy.py / BFF / Web / tests）→ 无诊断问题
- `npm run build -w apps/bff` → 失败，环境缺少本地模块 `commander`
- `npm run build -w apps/web` → 失败，环境缺少本地命令 `next`

### 6. 阻塞与补偿计划
- 阻塞原因：当前本地 Node 依赖环境不完整，无法完成 BFF/Web 构建验证
- 补偿措施：已用 IDE diagnostics + Python 回归 + diff 检查确认本轮代码层面无静态问题
- 后续动作：若需要完整前端/中间层构建验证，需在获得许可后恢复依赖环境再重跑构建

## 编码前检查 - 工厂运行历史详情展示
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-工厂运行历史详情展示.md`
- 将优先复用以下组件：
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py`：`list_strategy_factory_runs()` 与 `_decode_factory_run()`
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`：factory action 分发模式
  - `apps/bff/src/strategy/strategy.controller.ts` / `strategy.service.ts`：factory 路由转发模式
  - `apps/web/app/strategy-market/page.tsx`：最近运行历史卡片位置
- 将遵循命名约定：采用 `factory_run_detail` action 与 `factory/runs/:runId` 路由
- 将遵循代码风格：优先增量展开详情，不新增独立重页面
- 确认不重复造轮子：已检查 `review_report`、`events`、`factory_runs` 与策略详情页展示模式

## 编码后声明 - 工厂运行历史详情展示
时间：2026-03-06

### 1. 本批新增能力
- `get_strategy_factory_run(run_id)`：支持按 `run_id` 读取单次工厂运行记录
- `factory_run_detail`：manager 单次运行详情 action
- `GET /strategy-market/factory/runs/:runId`：BFF 详情端点
- 策略超市页：最近运行历史支持“查看详情/收起详情”，展示 `snapshot_summary`、`stages` 与 `error`

### 2. 复用了以下既有组件
- `StrategyMixin._decode_factory_run()`：继续作为运行历史 JSON 解码入口
- `factory_runs` 已有列表接口：详情展示与列表并行，不重造另一套历史体系
- `useApiQuery`：按 `expandedRunId` 条件查询详情

### 3. 遵循了以下项目约定
- 保持 `schema -> strategy.py -> manager -> BFF -> Web` 的既有分层
- Web 侧仅在现有列表页增量增加展开详情，不新建重路由
- 测试继续沿用 fake DB + manager action 模式

### 4. 未重复造轮子的证明
- 没有新增运行详情专用表，而是直接复用 `strategy_factory_runs`
- 没有复制策略详情页整套页面结构，而是做轻量展开卡片

### 5. 本地验证记录
- `PYTHONPATH=src /opt/miniconda3/bin/pytest -o addopts='' tests/test_strategy_factory_and_marketplace.py -q` → `73 passed`
- `git diff --check -- ...` → 通过
- IDE `diagnostics` → 无问题

### 6. 阻塞与补偿计划
- 本轮未重复执行 BFF/Web build：前一轮已确认本地 Node 依赖环境缺失会阻塞构建
- 补偿措施：继续采用 Python 回归 + diagnostics + diff 检查作为本轮最小验证闭环

## 编码前检查 - 运行历史对比视图
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-运行历史对比视图.md`
- 将优先复用以下组件：
  - `apps/web/app/strategy-market/page.tsx`：现有最近运行历史与详情展开区域
  - `factoryRunsQ`：最近运行历史数据源
  - `策略工厂/02-接口定义与数据模型.md`：摘要字段权威清单
  - `策略工厂/03-模块功能方案.md`：运行态短期方向表达
- 将遵循命名约定：继续使用 `Factory*` 组件命名
- 将遵循代码风格：不引入图表库，仅用轻量表格补对比视图
- 确认不重复造轮子：已检查当前历史列表、详情展开与文档中摘要字段定义

## 编码后声明 - 运行历史对比视图
时间：2026-03-06

### 1. 本批新增能力
- 策略超市页新增“最近运行对比”表格
- 基于最近 5 次 `factory/runs` 结果横向对比：状态、候选生成、去重后、提交数、质检通过、淘汰数、耗时

### 2. 复用了以下既有组件
- `factoryRunsQ`：直接复用历史列表数据，不新增后端接口
- `SectionCard`：继续承载工厂运行态区域
- `FactoryRunDetailPanel`：与对比视图并存，保持摘要/详情/对比三层结构

### 3. 遵循了以下项目约定
- 仅修改 `apps/web/app/strategy-market/page.tsx`，未扩散到新页面或新依赖
- 对比字段严格使用 `02` 文档里已存在的运行摘要字段

### 4. 未重复造轮子的证明
- 没有新增趋势接口或图表数据模型，直接复用已有 `factory/runs` 返回值
- 没有引入外部图表库，保持轻量实现

### 5. 本地验证记录
- `git diff --check -- '.claude/context-summary-运行历史对比视图.md' apps/web/app/strategy-market/page.tsx` → 通过
- IDE `diagnostics apps/web/app/strategy-market/page.tsx` → 仅发现 1 处样式提示，已修正

### 6. 阻塞与补偿计划
- 本轮未执行 Web build：当前 Node 环境缺少 `next`，重复执行只会命中已知阻塞
- 补偿措施：使用 diagnostics + diff 检查完成本轮最小静态验证

## 编码前检查 - 运行趋势视图
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-运行趋势视图.md`
- 将优先复用以下组件：
  - `apps/web/app/strategy-market/page.tsx`：已有运行历史、详情、对比区块
  - `factoryRunsQ`：趋势数据源
  - `FactoryMetric`：摘要卡样式
  - `FactoryRunComparisonTable`：可复用的运行历史展示上下文
- 将遵循命名约定：趋势组件继续使用 `Factory*` 命名
- 将遵循代码风格：不引入图表库，仅增加轻量柱状条趋势视图
- 确认不重复造轮子：已检查现有历史列表、详情展开、对比表与文档摘要字段定义

## 编码后声明 - 运行趋势视图
时间：2026-03-06

### 1. 本批新增能力
- 策略超市页新增“运行趋势”面板
- 基于最近 5 次 `factory/runs` 历史数据展示：成功率、平均耗时、最新候选数、最新质检通过
- 针对候选生成、提交数、质检通过、耗时增加轻量柱状趋势条

### 2. 复用了以下既有组件
- `factoryRunsQ`：直接复用历史列表数据，不新增接口
- `FactoryMetric`：继续承载趋势摘要卡
- `FactoryRunComparisonTable`：与趋势视图并存，保持对比和趋势分层

### 3. 遵循了以下项目约定
- 本轮只修改 `apps/web/app/strategy-market/page.tsx`
- 趋势字段严格复用 `factory/runs` 已有摘要字段
- 保持轻量实现，不引入图表依赖和新页面

### 4. 未重复造轮子的证明
- 没有新增趋势接口，也没有复制另一套数据模型
- 直接在前端基于最近多次历史结果做计算和渲染

### 5. 本地验证记录
- `diagnostics apps/web/app/strategy-market/page.tsx` → 无问题
- `git diff --check -- '.claude/context-summary-运行趋势视图.md' apps/web/app/strategy-market/page.tsx` → 通过

### 6. 阻塞与补偿计划
- 本轮未执行 Web build：当前 Node 环境缺少 `next`，重复执行会命中已知阻塞
- 补偿措施：采用 diagnostics + diff 检查完成最小静态验证闭环

## 编码前检查 - 策略工厂P1快照结构化
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-策略工厂P1快照结构化.md`
- 将使用以下可复用组件：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:DataCollector.collect`：快照采集与落库主入口
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:StrategyFactoryScheduler.run_once`：消费快照摘要的下游入口
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:_decode_json_field`：JSONB 解码模式
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:_decode_factory_run`：结构化查询读回模式
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`：`action + kwargs` 查询分发模板
- 将遵循命名约定：沿用 `save_* / get_* / list_*`，manager action 使用 `daily_snapshot / daily_snapshots`
- 将遵循代码风格：以轻量 JSONB 扩列补齐 `summary/completeness/sources/failure_reasons/missing_fields/degraded`，不引入并行快照体系
- 确认不重复造轮子：已检查 `strategy_factory.py`、`strategy.py`、`schema.py`、`strategy_manager.py`、`test_strategy_factory_and_marketplace.py`
- 本地预检记录：
  - `python scripts/skill_coverage_audit.py --check-thresholds` → `coverage=100.0%`、`missing=0`、`tdx=36/36`、`manager=32/32`、`collisions=0`
  - `python scripts/skill_coverage_audit.py --output-json skill_tool_coverage_runtime.json --output-gap skill_tool_gap_list.txt` → `coverage=100.0%`、`missing=0`

## 编码前检查 - 错误指纹标准化
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-错误指纹标准化.md`
- 将优先复用以下组件：
  - `apps/web/app/strategy-market/page.tsx`：现有失败原因聚合面板与 `normalizeFactoryRunError()`
  - `factoryRunsQ`：最近运行历史数据源
  - `策略工厂/02-接口定义与数据模型.md`：`status/error/stages` 字段口径
  - `策略工厂/03-模块功能方案.md`：失败原因标准化方向记录
- 将遵循命名约定：错误指纹辅助函数保持在 `page.tsx` 内部，采用轻量 `*ErrorFingerprint` 命名
- 将遵循代码风格：仅做规则匹配和示例保留，不引入第三方分类库或新接口
- 确认不重复造轮子：已检查当前失败聚合逻辑，确认只需升级归一化函数和面板展示

## 编码后声明 - 错误指纹标准化
时间：2026-03-06

### 1. 本批新增能力
- 将失败原因聚合从原始错误字符串计数升级为规则化错误指纹聚合
- 新增错误指纹类别：超时、网络连接、数据库、权限、配置缺失、输入校验、依赖加载、未分类
- 每个指纹桶保留一条示例错误，兼顾聚合稳定性与排查可读性

### 2. 复用了以下既有组件
- `FactoryRunFailurePanel`：继续作为失败聚合承载面板
- `normalizeFactoryRunError()`：升级为“标准化示例文本”函数
- 现有 `failedRuns`：继续作为失败样本来源

### 3. 遵循了以下项目约定
- 本轮仅修改 `apps/web/app/strategy-market/page.tsx`
- 错误标准化仍然只基于 `error` 字段，不扩后端或存储模型
- 明确保留“示例错误”，避免聚合后完全失去上下文

### 4. 未重复造轮子的证明
- 没有引入统一服务端错误码体系，而是对现有前端聚合做轻量增强
- 没有新增错误统计接口，仍直接复用 `factory/runs`

### 5. 本地验证记录
- `diagnostics apps/web/app/strategy-market/page.tsx` → 无问题
- `git diff --check -- '.claude/context-summary-错误指纹标准化.md' apps/web/app/strategy-market/page.tsx` → 通过

### 6. 阻塞与补偿计划
- 本轮未执行 Web build：当前 Node 环境缺少 `next`，重复执行会命中已知阻塞
- 补偿措施：采用 diagnostics + diff 检查完成最小静态验证闭环

## 编码前检查 - 失败原因聚合
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-失败原因聚合.md`
- 将优先复用以下组件：
  - `apps/web/app/strategy-market/page.tsx`：现有运行历史、趋势与筛选区域
  - `factoryRunsQ`：最近运行历史数据源
  - `run_once()` 的既有阶段顺序：`collect -> spawn -> backtest -> deduplicate -> submit -> elimination`
  - `策略工厂/02-接口定义与数据模型.md`：`status/error/stages` 字段口径
- 将遵循命名约定：失败聚合组件继续使用 `Factory*` 命名
- 将遵循代码风格：只做轻量统计与文本聚合，不引入新接口或新依赖
- 确认不重复造轮子：已检查当前运行历史详情、趋势和筛选能力，确认失败聚合可直接复用现有数据

## 编码后声明 - 失败原因聚合
时间：2026-03-06

### 1. 本批新增能力
- 策略超市页新增“失败原因聚合”面板
- 展示最近失败次数、失败率、最近失败阶段、最近失败时间
- 聚合最近失败运行的错误原因 Top 与失败阶段分布 Top

### 2. 复用了以下既有组件
- `factoryRunsQ`：直接复用最近运行历史，不新增统计接口
- 现有运行趋势/筛选区域：失败聚合作为同一卡片内增量区块
- `run_once()` 既有阶段顺序：用于保守推断失败阶段

### 3. 遵循了以下项目约定
- 本轮仅修改 `apps/web/app/strategy-market/page.tsx`
- 失败分析仅使用 `status`、`error`、`stages` 现有字段，不扩后端
- 明确将阶段判断写成“保守推断”，不伪装成强审计

### 4. 未重复造轮子的证明
- 没有新增失败统计接口或独立分析页
- 直接在前端基于最近运行历史做轻量聚合

### 5. 本地验证记录
- `diagnostics apps/web/app/strategy-market/page.tsx` → 无问题
- `git diff --check -- '.claude/context-summary-失败原因聚合.md' apps/web/app/strategy-market/page.tsx` → 通过

### 6. 阻塞与补偿计划
- 本轮未执行 Web build：当前 Node 环境缺少 `next`，重复执行会命中已知阻塞
- 补偿措施：采用 diagnostics + diff 检查完成最小静态验证闭环

## 编码前检查 - 规则命中统计
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-规则命中统计.md`
- 将优先复用以下组件：
  - `apps/web/app/strategy-market/page.tsx`：`FactoryRunFailurePanel`、`FactoryMetric`、`getFactoryRunErrorFingerprint()`
  - `.claude/context-summary-错误指纹标准化.md`：错误指纹规则边界与风险说明
  - `策略工厂/02-接口定义与数据模型.md`：失败聚合与错误指纹字段口径
  - `策略工厂/03-模块功能方案.md`：接口与展示阶段表达方式
- 将遵循命名约定：继续在 `page.tsx` 内使用 `Factory*` 与 `*ErrorFingerprint` 命名
- 将遵循代码风格：只在前端做轻量统计与文本聚合，不引入新接口、新依赖或新页面
- 确认不重复造轮子：已检查当前失败聚合与错误指纹实现，确认本轮只需扩展 `matched` 元信息与面板展示

## 编码后声明 - 规则命中统计
时间：2026-03-06

### 1. 本批新增能力
- 失败聚合面板新增“规则命中统计”区块
- 展示规则命中失败数、规则命中率、未分类错误数量、覆盖指纹种类数
- 新增未分类错误示例列表，用于反向识别后续待补规则

### 2. 复用了以下既有组件
- `FactoryRunFailurePanel`：继续作为失败聚合主面板
- `FactoryMetric`：继续承载轻量统计卡片
- `getFactoryRunErrorFingerprint()`：扩展为返回 `matched` 元信息
- `normalizeFactoryRunError()`：继续作为未分类示例标准化文本入口

### 3. 遵循了以下项目约定
- 本轮仅修改 `apps/web/app/strategy-market/page.tsx` 与配套文档留痕
- 统计逻辑继续完全基于 `/strategy-market/factory/runs?limit=5` 返回值
- 不新增后端接口、不引入新依赖、不新增页面路由

### 4. 未重复造轮子的证明
- 没有新增独立错误统计接口，而是在现有错误指纹结果上补 `matched` 元信息
- 没有新建平行分析组件，而是在 `FactoryRunFailurePanel` 内增量扩展规则统计与示例展示

### 5. 本地验证记录
- `diagnostics apps/web/app/strategy-market/page.tsx` → 无问题
- `git diff --check -- '.claude/context-summary-规则命中统计.md' '.claude/operations-log.md' '策略工厂/02-接口定义与数据模型.md' '策略工厂/03-模块功能方案.md' apps/web/app/strategy-market/page.tsx` → 通过

### 6. 阻塞与补偿计划
- 本轮未执行 Web build / Playwright：当前 Node 环境缺少 `next`，无法启动 `apps/web` 完成前端构建或 E2E
- 补偿措施：继续采用 `diagnostics + git diff --check` 完成最小本地静态验证闭环，并在上下文摘要中记录现有 Playwright 测试模式

## 编码前检查 - 运行历史筛选与细粒度趋势
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-运行历史筛选与细粒度趋势.md`
- 将优先复用以下组件：
  - `apps/web/app/strategy-market/page.tsx`：现有运行历史、详情、对比、趋势面板
  - `factoryRunsQ`：单一运行历史数据源
  - `FactoryRunComparisonTable` / `FactoryRunTrendPanel`：现有展示组件
  - `策略工厂/02-接口定义与数据模型.md`：运行摘要字段定义
- 将遵循命名约定：使用轻量前端状态，不新增模块和接口
- 将遵循代码风格：筛选与趋势切换均使用简单按钮，不引入复杂状态管理
- 确认不重复造轮子：已检查当前历史列表、对比表、趋势视图与文档中的短期方向

## 编码后声明 - 运行历史筛选与细粒度趋势
时间：2026-03-06

### 1. 本批新增能力
- 增加运行历史状态筛选：全部 / 成功 / 失败
- 增加趋势指标切换：候选生成 / 提交数 / 质检通过 / 耗时
- 历史列表、对比表与趋势图已统一基于同一份筛选结果渲染

### 2. 复用了以下既有组件
- `factoryRunsQ`：直接作为筛选前原始数据源
- `FactoryRunComparisonTable`：继续承载筛选后的横向对比
- `FactoryRunTrendPanel`：扩展为支持指标切换

### 3. 遵循了以下项目约定
- 本轮仅修改 `apps/web/app/strategy-market/page.tsx`
- 继续只使用已存在的运行摘要字段，不扩后端
- 保持轻量实现，不增加依赖

### 4. 未重复造轮子的证明
- 没有增加新接口或新数据模型，完全复用现有 `factory/runs`
- 没有新建独立筛选面板页面，仅在现有卡片内增量补齐

### 5. 本地验证记录
- `diagnostics apps/web/app/strategy-market/page.tsx` → 无问题
- `git diff --check -- '.claude/context-summary-运行历史筛选与细粒度趋势.md' apps/web/app/strategy-market/page.tsx` → 通过

### 6. 阻塞与补偿计划
- 本轮未执行 Web build：当前 Node 环境缺少 `next`，重复执行会命中已知阻塞
- 补偿措施：采用 diagnostics + diff 检查完成最小静态验证闭环

## 编码后声明 - 策略工厂P1快照结构化
时间：2026-03-06

### 1. 本批新增能力
- 为 `DataCollector.collect()` 补齐结构化快照契约：`summary`、`completeness`、`sources`、`failure_reasons`、`missing_fields`、`degraded`
- 为 `daily_snapshot_history` 增加对应 JSONB / BOOLEAN 持久化字段，并补幂等扩列迁移
- 为存储层补齐 `get_daily_snapshot()` / `list_daily_snapshots()`，并通过 manager 暴露 `daily_snapshot` / `daily_snapshots`
- 为 scheduler 摘要补齐快照降级和完整性汇总字段，便于运行历史直接消费

### 2. 复用了以下既有组件
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:DataCollector.collect`：继续作为快照采集主入口
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:StrategyFactoryScheduler.run_once`：继续承接快照摘要
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:_decode_json_field`：沿用 JSONB 解码模式
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:_decode_factory_run`：沿用结构化对象读回风格
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`：沿用 `action + kwargs` / `ok/fail` 查询分发模式

### 3. 遵循了以下项目约定
- 命名继续沿用 `save_* / get_* / list_*`，manager action 使用 `daily_snapshot / daily_snapshots`
- 结构化快照采用轻量 JSONB 扩列，不新建平行快照体系
- 测试继续沿用 `_DummyMCP + _StrategyDB + monkeypatch + AsyncMock` 模式

### 4. 对比了以下相似实现
- `Deduplicator.last_report`：本轮借用其 `summary + 明细` 的结构化报告思路，但对象从去重报告换成每日快照契约
- `strategy.py` 既有 `save_strategy_factory_run() / list_strategy_factory_runs()`：本轮按同类 save/get/list 模式扩展 daily snapshot 查询
- `strategy_manager.py` 既有 `factory_runs / factory_run_detail`：本轮沿用相同 action 暴露快照查询，不新增额外层次

### 5. 未重复造轮子的证明
- 已检查 `strategy_factory.py`、`strategy.py`、`schema.py`、`strategy_manager.py`、`test_strategy_factory_and_marketplace.py`，确认此前不存在稳定的 daily snapshot 查询闭环
- 没有新增独立快照服务或额外接口层，而是在既有工厂与 manager 体系内增量补齐

### 6. 本地验证记录
- `python scripts/skill_coverage_audit.py --check-thresholds` → `coverage=100.0%`、`missing=0`
- `python scripts/skill_coverage_audit.py --output-json skill_tool_coverage_runtime.json --output-gap skill_tool_gap_list.txt` → `coverage=100.0%`、`missing=0`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py -q` → `75 passed`
- `diagnostics packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py` → 无诊断问题

### 7. 阻塞与补偿计划
- 本轮未扩散到 BFF / Web；这是任务边界控制，不是阻塞
- 补偿措施：后续在“工厂聚合看板与增强趋势分析”等下游任务中消费新快照契约

## 编码前检查 - 策略工厂P1候选生成显式输出
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-策略工厂P1候选生成显式输出.md`
- 将使用以下可复用组件：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:StrategySpawner._make`：统一候选输出入口
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:Deduplicator.get_last_report`：结构化报告模式参考
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:StrategyFactoryScheduler.run_once`：阶段摘要落库入口
  - `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py:TestStrategySpawner`：现有候选生成测试模式
- 将遵循命名约定：保留 `spawn_reason`，新增字段以 `generation_reason`、`trigger_signal`、`trigger_thresholds`、`quota_fill` 为主
- 将遵循代码风格：轻量 dict 契约 + 最小范围汇总，不引入新模块或新依赖
- 确认不重复造轮子：已检查 `StrategySpawner`、`Deduplicator`、scheduler `stages.spawn` 与现有 pytest，确认只需增量补结构化字段与 summary

## 编码后声明 - 策略工厂P1候选生成显式输出
时间：2026-03-06

### 1. 复用了以下既有组件
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:StrategySpawner._make`：继续作为候选输出统一收口点
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:Deduplicator.get_last_report`：复用 `summary + 明细` 的结构化报告模式
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:StrategyFactoryScheduler.run_once`：复用阶段摘要落库入口，不新增并行运行报告体系
- `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py:TestStrategySpawner`：沿用既有生成器单测风格补齐字段断言

### 2. 遵循了以下项目约定
- 命名约定：保留 `spawn_reason` 作为兼容字段，新增 `generation_reason`、`trigger_signal`、`trigger_thresholds`、`quota_fill`
- 代码风格：通过轻量 dict 契约增量补字段，不引入额外 DTO、模块或依赖
- 文件组织：改动仍限定在 `strategy_factory.py + pytest`，暂不扩散到 BFF / Web

### 3. 对比了以下相似实现
- `StrategySpawner._make`：我保持其“统一构造候选”职责，只在同一出口补结构化原因字段
- `Deduplicator.last_report`：借用其结构化 summary 模式，为 `StrategySpawner` 增加 `last_report`
- `StrategyFactoryScheduler.run_once`：沿用现有 `results["stages"]` 汇总结构，仅把 `spawn` 从 count 扩展为结构化 summary

### 4. 未重复造轮子的证明
- 已检查 `StrategySpawner`、`Deduplicator`、scheduler `stages.spawn` 与现有 pytest
- 确认仓库中不存在单独的候选原因契约层，因此本轮选择在 `_make()` 和 `spawn()` 内最小收口

### 5. 本地验证结果
- `pytest -o addopts='' packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py -q -k 'TestStrategySpawner or test_run_once_persists_factory_run_history'` → `10 passed, 65 deselected`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py -q` → `75 passed`
- `diagnostics packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py` → 无诊断问题

## 编码前检查 - 策略工厂P1初筛失败原因标准化与分层阈值
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-策略工厂P1初筛失败标准化.md`
- 将使用以下可复用组件：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:BacktestFilter`：当前初筛回测主入口
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:Deduplicator.get_last_report`：结构化阶段报告参考模式
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:StrategyFactoryScheduler.run_once`：回测阶段摘要落库入口
  - `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py:TestBacktestFilter`：现有回测筛选测试入口
- 将遵循命名约定：候选级字段使用 `backtest_result` / `backtest_metrics`，阶段汇总保持 `summary + passed + failed`
- 将遵循代码风格：在现有回测循环中补充结构化信息，不新增并行服务或额外依赖
- 确认不重复造轮子：已检查 `BacktestFilter`、`Deduplicator`、`StrategySubmitter`、`run_once()` 与现有 pytest，确认只需在 `strategy_factory.py + pytest` 内最小收口

## 编码后声明 - 策略工厂P1初筛失败原因标准化与分层阈值
时间：2026-03-06

### 1. 复用了以下既有组件
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:BacktestFilter`：继续作为初筛回测唯一入口，在原有循环内补结构化结果
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:Deduplicator.get_last_report`：复用 `summary + passed + failed` 的阶段报告模式
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:StrategyFactoryScheduler.run_once`：复用阶段摘要落库入口，把 backtest 报告写入运行历史
- `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py:TestBacktestFilter`：沿用既有回测筛选测试入口扩关键路径

### 2. 遵循了以下项目约定
- 命名约定：候选级结果统一使用 `backtest_result`，通过候选额外保留 `backtest_metrics`
- 代码风格：以轻量 dict 契约扩展失败原因、阈值和样本信息，不引入新模块或新依赖
- 文件组织：改动仍限定在 `strategy_factory.py + pytest`，暂不扩散到 BFF / Web / manager

### 3. 对比了以下相似实现
- `BacktestFilter._test_one()`：我保留其“逐代表股票回测并汇总”的主体结构，仅把 `None` 返回改为结构化结果对象
- `Deduplicator.last_report`：借用其阶段报告模式，为 backtest 阶段新增 `last_report`
- `StrategyFactoryScheduler.run_once`：沿用现有 `results["stages"]` 结构，只把 `backtest` 从计数摘要扩展为结构化汇总

### 4. 未重复造轮子的证明
- 已检查 `BacktestFilter`、`Deduplicator`、`StrategySubmitter`、`run_once()` 与现有 pytest
- 确认仓库中不存在独立的回测失败原因契约层，因此本轮选择在 `BacktestFilter` 内最小收口并直接复用 scheduler 摘要链路

### 5. 本地验证结果
- `pytest -o addopts='' packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py -q -k 'TestBacktestFilter or test_run_once_persists_factory_run_history'` → `4 passed, 72 deselected`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py -q` → `76 passed`
- `diagnostics packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py` → 无诊断问题

## 编码后声明 - 策略工厂P1质量报告复检入口
时间：2026-03-06

### 1. 复用了以下既有组件
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:_save_quality_report`：继续作为质量报告统一落库入口，并在此基础上扩展 latest/list/recheck 能力
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:StrategySubmitter.submit`：沿用既有提交主链路，仅把质量报告构造收口到共享 helper
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:get_strategy_quality_report`：复用既有表与 JSON 解码模式，扩展 `get_latest_strategy_quality_report` / `list_strategy_quality_reports`
- `apps/web/hooks/use-api-mutation.ts` + `apps/web/lib/query-keys.ts`：复用 POST + query 前缀失效刷新模式接入“重新复检”按钮

### 2. 遵循了以下项目约定
- 命名约定：manager action 使用 snake_case，新增复检动作命名为 `review_report_recheck`，历史报告类型使用 `recheck:<timestamp>`
- 代码风格：通过共享 helper 标准化 `quality_gate` 与 `summary` 字段，不新增旁路服务或新表
- 文件组织：改动沿 `tools/managers -> services -> storage -> apps/bff -> apps/web -> tests` 既有分层推进

### 3. 对比了以下相似实现
- `strategy_manager.py:submit`：保留“提交后自动质检并落库”的主链路，只把散落的报告拼装改为 `_build_quality_report()`
- `strategy_factory.py:StrategySubmitter._build_quality_report`：保留其输入输出契约，但改为复用 manager 的统一构造逻辑
- `apps/web` 既有 `useApiMutation + invalidate` 模式：沿用模块级 query key 前缀失效，不单独发明前端刷新机制

### 4. 未重复造轮子的证明
- 已检查 `strategy_manager.py`、`strategy_factory.py`、`storage/timescaledb/strategy.py`、`apps/bff/src/strategy/*`、`apps/web/app/strategy-market/[id]/page.tsx` 与既有 pytest
- 确认仓库内不存在现成的“质量报告复检入口”或“历史质量报告列表”封装，因此本轮在既有表和既有页面中做最小扩展
- 整份 pytest 回归中额外暴露出 `publish/listed`、生命周期转换、`daily_snapshot(s)` 动作残留，本轮已顺手最小修正并重新通过全量回归

### 5. 本地验证结果
- `pytest -o addopts='' packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py -q -k 'test_submitter_persists_validation_and_risk_metrics or test_review_report_events_and_incubation_overview or test_review_report_recheck_persists_latest_report'` → `3 passed, 74 deselected`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py -q` → `77 passed`
- `diagnostics apps/bff/src/strategy/strategy.service.ts apps/bff/src/strategy/strategy.controller.ts apps/web/app/strategy-market/[id]/page.tsx` → 无诊断问题

## 编码前检查 - 策略工厂P1多周期forward-returns孵化判断
时间：2026-03-06

- 已查阅上下文摘要文件：`.claude/context-summary-策略工厂P1多周期forward-returns孵化判断.md`
- 将使用以下可复用组件：
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:_build_incubation_overview`：孵化概览唯一入口
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:_lifecycle_scan`：生命周期状态扫描主链路
  - `packages/akshare-mcp/src/akshare_mcp/services/signal_tracker.py:FORWARD_DAYS`：多周期 forward returns 来源
  - `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py:get_signal_stats`：fake DB 多周期指标注入入口
- 将遵循命名约定：继续保留 `hit_rate_5d / forward_ic_5d / forward_sharpe_5d` 兼容字段，新增明细字段使用 `forward_returns / blockers_by_period / risk_flags_by_period`
- 将遵循代码风格：只在现有 manager helper 和详情页工厂 Tab 内做最小增量，不改 signal_tracker 主流程、不新增依赖
- 确认不重复造轮子：已检查 `strategy_manager.py`、`signal_tracker.py`、`page.tsx` 与既有 pytest，确认多周期数据源和生命周期入口已存在，仅缺消费与解释层
- 约束留痕：当前环境无 GitHub `search_code` / desktop-commander，本轮以真实磁盘源码分析替代

## 编码后声明 - 策略工厂P1多周期forward-returns孵化判断
时间：2026-03-07

### 1. 复用了以下既有组件
- `packages/akshare-mcp/src/akshare_mcp/services/signal_tracker.py:FORWARD_DAYS`：沿用既有 `1/5/10/20` 周期口径，不新增并行周期定义
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:_lifecycle_scan`：继续作为生命周期扫描统一入口，仅升级其消费的孵化判断依据
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:StrategySubmitter.submit`：继续复用 manager 侧质量报告 helper，顺手收口磁盘回退导致的 helper 缺口
- `apps/web/hooks/use-api-mutation.ts` 与 `apps/web/lib/query-keys.ts`：沿用既有复检按钮接线与 query 失效模式

### 2. 遵循了以下项目约定
- 命名约定：继续使用 `daily_snapshot / daily_snapshots / review_report_recheck`、`save_* / get_* / list_*` 与 `recheck:<timestamp>` 报告类型
- 代码风格：以最小 helper 收口回退缺口，没有新增并行 service 或新的存储表
- 文件组织：保持 `manager -> storage -> BFF -> Web -> pytest` 既有分层，只在当前任务需要的边界内增量修改

### 3. 对比了以下相似实现
- `signal_tracker.py`：我保持其多周期前向收益采集事实，只把 manager 端从“仅 5D”升级为消费完整周期集合
- `strategy_manager.py` 既有 `review_report / events / incubation_overview`：本轮沿用同一 action 分发体系补齐 `review_report_recheck`、`daily_snapshot(s)` 与多周期解释输出
- `storage/timescaledb/strategy.py` 既有 `save_strategy_factory_run / get_strategy_quality_report`：本轮按相同 `save/get/list + decode` 模式扩展 daily snapshot 与质量报告历史查询

### 4. 未重复造轮子的证明
- 已检查 `strategy_manager.py`、`strategy_factory.py`、`signal_tracker.py`、`storage/timescaledb/strategy.py`、`apps/bff/src/strategy/*`、`apps/web/app/strategy-market/[id]/page.tsx`
- 确认仓库内不存在现成的“多周期孵化概览聚合器”或“质量报告复检历史查询层”，因此本轮在既有 manager / storage 上做最小闭环补齐是最收敛方案

### 5. 本地验证结果
- `pytest -o addopts='' packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py -q -k 'test_help_action or test_publish_and_archive or test_list_and_rank_keep_published_alias_compatible or test_review_report_events_and_incubation_overview or test_incubation_overview_surfaces_multi_period_blockers or test_lifecycle_scan_uses_multi_period_forward_returns or test_review_report_recheck_persists_latest_report or test_factory_status_and_run_once_actions'` → `8 passed, 71 deselected`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py -q` → `79 passed`
- `diagnostics packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py apps/bff/src/strategy/strategy.controller.ts apps/web/app/strategy-market/[id]/page.tsx` → 无诊断问题

### 6. 当前结论
- 本轮 P1-5 已达到“多周期孵化判断落地 + 生命周期扫描切换 + 质量报告复检与快照查询缺口一并收口 + 本地自动回归通过”的交付标准，结论为**通过**。

## 编码前检查 - 策略工厂P1事件筛选查询
时间：2026-03-07

- 已查阅上下文摘要文件：`.claude/context-summary-策略工厂P1事件筛选查询.md`
- 将使用以下可复用组件：
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/signal_tracking.py:get_signals`：动态 SQL 条件拼接模板
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:_decode_json_field`：事件 `metadata` 解码
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py` 现有 `events` action：复用 action 分发入口
  - `apps/web/app/strategy-market/[id]/page.tsx:FactoryReviewPanel`：复用现有工厂页签与表格承载区块
- 将遵循命名约定：筛选字段统一使用 `event_type/from_status/to_status/actor_id/start_time/end_time/limit`
- 将遵循代码风格：后端使用轻量 helper 与最小签名扩展；BFF 使用内联 DTO；Web 使用 `useState + URLSearchParams + 原生表单`
- 确认不重复造轮子：已检查 `strategy.py`、`signal_tracking.py`、`strategy_manager.py`、`strategy.controller.ts`、`strategy.service.ts`、`apps/web/app/strategy-market/[id]/page.tsx`
- 说明：当前工具集中无 GitHub `search_code` 与 desktop-commander，本轮以仓库内相似实现和 Context7 官方文档替代，并在此留痕

## 编码后声明 - 策略工厂P1事件筛选查询
时间：2026-03-07

### 1. 复用了以下既有组件
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/signal_tracking.py:get_signals`：复用动态 SQL 条件拼接模式，承接事件多条件筛选
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:_decode_json_field`：继续作为事件 `metadata` JSON 解码入口
- `apps/bff/src/strategy/strategy.controller.ts:EventsQueryDto`：沿用 NestJS controller 内联 DTO 扩展 query 字段
- `apps/web/app/strategy-market/[id]/page.tsx:FactoryReviewPanel`：继续复用既有工厂页签、`SectionCard` 与 `DataTable` 展示骨架

### 2. 遵循了以下项目约定
- 命名约定：查询字段统一使用 `event_type/from_status/to_status/actor_id/start_time/end_time/limit`
- 代码风格：后端保持轻量 helper 和最小签名扩展；前端使用 `useState + useMemo + URLSearchParams`，不引入额外状态库
- 文件组织：改动继续沿 `storage -> manager -> BFF -> Web` 分层收口，没有旁路实现

### 3. 对比了以下相似实现
- `signal_tracking.py:get_signals`：我沿用其 `sql + params + idx` 动态过滤方式，而不是重写另一套查询拼接逻辑
- `strategy.controller.ts:EventsQueryDto`：我保留其内联 DTO 写法，只增量补齐筛选参数和复检路由
- `apps/web/app/strategy-market/[id]/page.tsx` 既有 `FactoryReviewPanel`：我保留现有工厂页签布局，只补筛选表单、metadata 摘要、报告历史和多周期表格

### 4. 未重复造轮子的证明
- 已检查 `strategy.py`、`signal_tracking.py`、`strategy_manager.py`、`strategy.controller.ts`、`strategy.service.ts`、`apps/web/app/strategy-market/[id]/page.tsx`
- 确认仓库内不存在现成的“事件筛选表单 + metadata 摘要 + 多周期孵化明细”复合展示组件，因此本轮在既有详情页工厂 Tab 中做最小增量补齐

### 5. 本地验证结果
- `pytest -o addopts='' packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py -q -k 'test_review_report_events_and_incubation_overview or test_incubation_overview_surfaces_multi_period_blockers or test_lifecycle_scan_uses_multi_period_forward_returns or test_review_report_recheck_persists_latest_report'` → `4 passed, 75 deselected`
- `diagnostics apps/web/app/strategy-market/[id]/page.tsx apps/bff/src/strategy/strategy.controller.ts apps/bff/src/strategy/strategy.service.ts` → 无诊断问题

### 6. 当前结论
- 本轮 P1-6 已达到“事件 metadata 完整回传 + 多条件筛选查询 + BFF query 透传 + Web 消费层可见”的交付标准，结论为**通过**。

## 编码前检查 - 策略工厂P1细粒度运行日志持久化与查询
时间：2026-03-07

□ 已查阅上下文摘要文件：`.claude/context-summary-策略工厂P1细粒度运行日志持久化与查询.md`
□ 将使用以下可复用组件：
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:_decode_json_field`：复用工厂运行 JSONB 解码
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:StrategyFactoryScheduler.run_once`：复用单次运行聚合边界
  - `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:factory_runs/factory_run_detail`：复用 action 分发模式
  - `apps/web/app/strategy-market/page.tsx:FactoryRunDetailPanel`：复用详情卡片展示骨架
□ 将遵循命名约定：新增字段统一使用 `run_logs`、`error_context`、`failure_stage`，日志过滤参数使用 `run_id/stage/limit`
□ 将遵循代码风格：继续按 `schema -> storage -> service -> manager -> BFF -> Web -> tests` 分层做最小增量补丁
□ 确认不重复造轮子，证明：已检查 `strategy.py`、`schema.py`、`strategy_factory.py`、`strategy_manager.py`、`strategy.controller.ts`、`strategy.service.ts`、`page.tsx`、`test_strategy_factory_and_marketplace.py`，确认不存在现成的工厂细粒度日志持久化与查询能力

## 审查记录 - 策略工厂缺口复审
时间：2026-03-07

### 1. 本轮审查范围
- 复查 `策略工厂/` 全部核心文档是否已同步最新实现
- 复查 autonomy / incubation / vector platform / scheduler / manager / BFF / Web 是否形成闭环
- 复查 `test_strategy_factory_and_marketplace.py` 是否覆盖新增能力

### 2. 关键复用与证据
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py`：确认 autonomy、incubation、vector platform 已进入主链路
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`：确认新增 action 已统一对外收口
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py`：确认 incubation / vector / experiment / task run 持久化接口存在
- `apps/bff/src/strategy/strategy.controller.ts`、`strategy.service.ts`：确认 BFF 已暴露新增 API
- `apps/web/app/strategy-market/page.tsx`、`[id]/page.tsx`：确认 Web 已展示工厂运行态、审查报告、孵化概览、事件流，但尚未全量可视化
- `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`：确认已有 `submit/incubation/capabilities/ai_generate/factory run` 相关测试

### 3. 本地验证记录
- `python3 -m pytest ...` → 失败：系统 Python 缺少 `pytest`
- `PYTHONPATH=src .venv/bin/python -m pytest ...` → 失败：项目 `.venv` 同样缺少 `pytest`
- 补偿验证：`PYTHONPATH=src .venv/bin/python - <<'PY' ... importlib.import_module(...) ... PY` → 通过，关键模块与符号导入成功

### 4. 当前结论
- 旧缺口中“主链路未接线”的部分已大幅补齐，不能再沿用上一轮“AI/孵化/向量仍未接入”的旧判断
- 但若按“蓝图级全部完善”口径，仍存在高级自治、成熟向量平台、全量 Web 展示、文档同步等未完成项
- 本轮最终口径：**大部分缺口已补齐，但尚未达到全部完善**