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

## 当前实施计划 - 虚拟盘方案补齐
1. 补 `apps/web/app/paper-trading/layout.tsx` 与 `middleware.ts`
2. 修正前端页面中与方案冲突的卖出整手校验
3. 补 `paper_trading_manager.py` 的整手、T+1、涨跌停、`accounts` 别名、`update_prices`
4. 扩展 `test_p0_regressions.py` 并执行本地验证

## 编码后声明 - 虚拟盘方案补齐
时间：2026-03-06

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

