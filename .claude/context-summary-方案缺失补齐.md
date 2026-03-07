## 项目上下文摘要（方案缺失补齐）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `packages/akshare-mcp/src/akshare_mcp/tools/factor_profile.py:128-206`
  - 模式：`register(mcp)` 内声明 `@mcp.tool()` 异步函数
  - 可复用：`ok` / `fail` 返回结构、`db.get_klines()` 数据获取模式
  - 注意：工具返回结构化字典，错误分支保持字段稳定

- **实现2**: `packages/akshare-mcp/src/akshare_mcp/tools/vector.py:182-281`
  - 模式：工具层做参数解析 + 数据获取，核心算法委托服务层
  - 可复用：失败即 `return fail(...)`，成功统一 `return ok({...})`
  - 注意：先做输入校验，再聚合结果字段

- **实现3**: `packages/akshare-mcp/src/akshare_mcp/services/screen_engine.py:63-123`
  - 模式：条件注册表 + `evaluate` / `evaluate_multi` 组合评估
  - 可复用：条件收益工具可直接复用条件表达能力
  - 注意：`condition_ids` 支持字符串与字典两种格式

- **实现4**: `packages/akshare-mcp/src/akshare_mcp/tools/decision.py:776-919`
  - 模式：已存在 `get_investment_analysis(code)` 纯数据汇聚函数
  - 可复用：价格上下文、估值、基本面、技术面、动量、风险字段组织方式
  - 注意：当前尚未作为 MCP 工具暴露

### 2. 项目约定
- **工具注册**: `server.py` 统一导入模块并调用 `xxx.register(mcp)`
- **返回约定**: 使用 `ok({...})` / `fail("...")`
- **工具风格**: 工具层尽量薄，服务层承载核心算法
- **命名约定**: MCP 工具使用 `get_*` / `search_*` / 动词短语

### 3. 可复用组件清单
- `services/screen_engine.py`: 条件评估引擎
- `services/screen_conditions.py`: 已注册的技术/形态/量价条件
- `tools/decision.py:get_investment_analysis`: 纯数据分析聚合函数
- `storage/timescaledb/signal_tracking.py:get_signal_stats`: 命中率/前向 IC/前向 Sharpe 统计参考
- `tools/factor_profile.py`: 工具注册与返回结构模板

### 4. 测试策略
- **测试框架**: pytest
- **参考文件1**: `tests/test_prediction_enhancement.py`
- **参考文件2**: `tests/test_tool_contract_check.py`
- **测试重点**:
  - 工具注册后可被 `_DummyMCP` 捕获
  - 返回结构字段完整
  - 条件收益统计覆盖正常与空结果分支

### 5. 依赖和集成点
- **工具层**: `tools/decision.py`、`tools/quant.py`
- **服务层**: `screen_engine`、`screen_conditions`
- **存储层**: `get_db()` 提供 `get_klines` / `get_stock_info` / 可能的资金流与财务接口
- **注册层**: `server.py` 已注册 `decision`、`quant`

### 6. 技术选型理由
- 条件收益优先复用 `screen_engine`，避免重复实现条件解析
- 数据汇聚优先复用现成 `get_investment_analysis`，避免重复造轮子
- 测试优先补工具契约测试，确保 MCP 暴露真实可用

### 7. 关键风险点
- `screen_conditions` 需要被导入后条件才会注册
- `decision.py` 中部分 DB 接口名可能与实际存储实现存在差异
- 条件收益工具的数据窗口、前向收益计算口径需要稳定，避免测试脆弱

### 8. 本轮最终落地摘要
- **因子画像**：`tools/factor_profile.py` 已补 `industry_rank`、`industry_total`、`market_percentile`、`historical_oversold_recovery`
- **条件统计复用**：新增 `services/data_pipeline/condition_stats.py` 与 `cross_section.py`
- **量化工具**：`tools/quant.py` 已补 `list_factors`、`find_similar_patterns`、`get_signal_hit_rate`
- **决策重构**：`tools/decision.py` 增强 `get_investment_analysis`，`tools/semantic/diagnosis.py` 改为结构化证据输出
- **策略接线**：`services/strategy_factory.py` 已接入 `FactorValidationPipeline` 与 `RiskModel`
- **回测增强**：`services/backtest/advanced.py` 已把仓位管理改为仿真循环内动态控制
- **验收文件**：已通过 `tests/test_prediction_enhancement.py`、`tests/test_strategy_factory_and_marketplace.py`、`tests/test_backtest_baselines.py`、`tests/test_tool_contract_check.py` 与技能覆盖审计

