## 项目上下文摘要（策略工厂P1初筛失败标准化）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:721-772`
  - 模式：`BacktestFilter` 当前采用统一阈值、黑盒 `return None` 过滤
  - 可复用：`filter()` 的候选遍历与 `asyncio.to_thread()` 回测执行方式
  - 需注意：当前没有 `last_report`、没有失败原因、没有按 `strategy_type` 分层阈值

- **实现2**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:782-837`
  - 模式：`Deduplicator.last_report` 使用 `summary + kept + dropped` 的结构化报告
  - 可复用：`get_last_report()`、阶段汇总落入 scheduler 的方式
  - 需注意：P1-3 应复用这种报告风格，不另造平行报告体系

- **实现3**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:1102-1128`
  - 模式：`StrategySubmitter._build_quality_report()` 已消费 `backtest_metrics`
  - 可复用：通过候选继续保留结构化 `backtest_metrics`
  - 需注意：本轮不提前改质量报告存储层，只补 `backtest_result` 与 scheduler 摘要

- **实现4**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:1455-1502`
  - 模式：`run_once()` 已把 `spawn`、`deduplicate`、`submit` 等阶段写入 `results["stages"]`
  - 可复用：`stages["backtest"]` 继续沿用阶段化汇总写法
  - 需注意：当前 `backtest` 只有 count 摘要，需扩为结构化 summary

### 2. 项目约定
- **命名约定**：阶段报告使用 `last_report` / `get_last_report()`；候选附加字段采用轻量 dict，如 `generation_reason`、`dedup_result`
- **文件组织**：本轮只改 `strategy_factory.py` 与 `test_strategy_factory_and_marketplace.py`
- **导入顺序**：保持标准库、第三方、项目内模块顺序，不新增依赖
- **代码风格**：优先最小补丁；沿用 dict 契约和 scheduler `summary/stages` 聚合风格

### 3. 可复用组件清单
- `StrategySpawner._make()`：候选对象统一构造出口
- `Deduplicator.get_last_report()`：结构化阶段报告模式
- `StrategyFactoryScheduler.run_once()`：运行历史摘要落库入口
- `StrategySubmitter._build_quality_report()`：通过候选的回测指标消费入口

### 4. 测试策略
- **测试框架**：`pytest`
- **测试模式**：`AsyncMock + MagicMock + monkeypatch`
- **参考文件**：`packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
- **覆盖要求**：正常通过、样本不足、Sharpe 不达标、按策略类型阈值差异、scheduler 汇总

### 5. 依赖和集成点
- **外部依赖**：`BacktestEngine.run_backtest()`
- **内部依赖**：`BacktestFilter -> StrategyFactoryScheduler -> strategy_factory_runs`
- **集成方式**：`run_once()` 读取 `bt_filter.get_last_report()` 写入 `results["stages"]["backtest"]`
- **配置来源**：`strategy_factory.py` 顶部常量区

### 6. 技术选型理由
- **为什么用这个方案**：直接在 `BacktestFilter` 内补结构化结果，改动最小、测试面最集中、能立即进入运行历史
- **优势**：不扩散到 BFF/Web；与现有 `Deduplicator` 报告模式一致；后续 P1-4 可继续消费
- **劣势和风险**：阈值仍是代码内常量；质量报告层本轮还不消费失败候选细节

### 7. 关键风险点
- **边界条件**：无 K 线、样本不足、回测异常、回测成功但任一指标不达标
- **一致性风险**：`backtest_result` 字段命名和 `summary` 聚合必须与现有 `spawn/deduplicate` 风格一致
- **性能风险**：不能增加额外回测次数；只在现有循环里补记录逻辑
- **验证重点**：确保 `scheduler` 落库摘要包含失败原因分布和分层阈值信息
