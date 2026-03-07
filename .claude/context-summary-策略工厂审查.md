## 项目上下文摘要（策略工厂审查）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py`
  - 模式：调度器串联采集、生成、回测筛选、去重、提交、淘汰的流水线
  - 可复用：`DataCollector`、`StrategySpawner`、`BacktestFilter`、`Deduplicator`、`StrategySubmitter`、`EliminationChecker`
  - 需注意：当前去重仍以参数级规则为主，非持久化向量召回
- **实现2**: `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`
  - 模式：生命周期状态机 + 质量门禁 + 定期扫描
  - 可复用：`LIFECYCLE_TRANSITIONS`、`_run_quality_gate()`、`_lifecycle_scan()`
  - 需注意：状态推进存在，但事件审计流未独立落库
- **实现3**: `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py`
  - 模式：策略、指标、血缘、淘汰日志、快照的持久化
  - 可复用：`save_strategy()`、`save_strategy_metrics()`、`save_strategy_lineage()`、`save_elimination_log()`、`save_daily_snapshot()`
  - 需注意：未见独立质量报告表、审计事件表
- **实现4**: `apps/bff/src/strategy/strategy.controller.ts`
  - 模式：NestJS Controller/Service 分层，对外暴露策略超市接口
  - 可复用：列表、排行、详情、提交、订阅、评价、信号、前向收益、生命周期扫描
  - 需注意：未暴露工厂运行态、审查报告、事件流接口

### 2. 项目约定
- **命名约定**: Python 用 snake_case，TypeScript 类与 DTO 用 PascalCase，REST 路由用短横线
- **文件组织**: Python 核心能力在 `packages/akshare-mcp`，BFF 在 `apps/bff`，Web 在 `apps/web`
- **代码风格**: BFF 为 NestJS 常规分层，Python 侧以服务/存储/mixin 组合为主

### 3. 可复用组件清单
- `services/strategy_factory.py`: 工厂主链路
- `tools/managers/strategy_manager.py`: 生命周期与质检
- `storage/timescaledb/strategy.py`: 策略存储
- `services/signal_tracker.py`: 信号与前向收益跟踪
- `services/validation.py`: WalkForward / PurgedKFold / Bootstrap

### 4. 测试策略
- **测试框架**: pytest
- **参考文件**: `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
- **覆盖重点**: 工厂组件、策略超市、生命周期、质检链路

### 5. 依赖和集成点
- **外部依赖**: NestJS、Next.js、asyncpg、numpy、scikit-learn
- **内部依赖**: BFF 调 MCP 工具，MCP 调 TimescaleDB 适配层
- **配置来源**: 根 `package.json`、`packages/akshare-mcp/pyproject.toml`、`pytest.ini`

### 6. 技术选型理由
- 以现有 MCP + BFF + Web 单体仓结构增量演进，成本低且复用高
- 文档已把“研究蓝图”和“现状/演进方案”分层，降低误判风险

### 7. 关键风险点
- 工厂运行态缺少上层接口和观测面板
- 质量报告未独立持久化，复盘与追责能力不足
- 无 append-only 事件流，生命周期审计有限
- 模拟盘与孵化晋级尚未闭环
- 向量去重仍未正式接入工厂主路径
