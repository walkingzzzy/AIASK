# 策略工厂独立包迁移方案

## 0. 最小可执行版

**结论**：方案可行，但前提是按“兼容优先、逐步迁移”的方式推进，不做一次性大搬家。

### 0.1 先只做这 6 步

#### Step 1：冻结当前行为
- 固定最小回归集：
  - `test_strategy_factory_module_compat.py`
  - `test_strategy_factory_gate_report.py`
  - `test_backtest_filter_concurrency.py`
  - `test_concurrency_optimization.py`
  - `test_strategy_factory_and_marketplace.py`
- 额外输出两份清单：
  - `StrategyFactoryRepository` 最小方法表
  - 旧路径 patch-point 清单
- 完成标准：
  - 先知道“现在什么不能坏”，再开始迁移

#### Step 2：创建新包，但先不搬核心实现
- 新建：
  - `packages/strategy-factory/pyproject.toml`
  - `packages/strategy-factory/src/strategy_factory/...`
- 同时补齐导入链路：
  - 让 `packages/akshare-mcp/` 开发环境能直接 `import strategy_factory`
  - 不依赖临时 `PYTHONPATH`
- 完成标准：
  - 新包能被 `akshare-mcp` 稳定导入

#### Step 3：先抽稳定门面，不急着分层做“漂亮”
- 首批只抽：
  - `api/facade.py`
  - `api/contracts.py`
- facade 先暴露最少能力：
  - `get_strategy_factory_scheduler()`
  - `run_submission_quality_gate()`
  - `build_strategy_panels()`
  - `extract_event_context()`
  - `get_factory_constants()`
- 完成标准：
  - 兼容层后续只依赖 facade

#### Step 4：先迁低耦合模块
- 先迁：
  - `constants.py`
  - `naming.py`
  - `targets.py`
  - `spawner.py`
  - `quality_reporting.py`
- 旧路径先保留 shim / re-export
- 完成标准：
  - 相关兼容测试通过
  - 外部调用方无需修改

#### Step 5：再迁真正卡脖子的流程模块
- 优先顺序：
  1. `backtest_filter.py`
  2. `deduplicator.py`
  3. `submitter.py` / `submission_gate.py`
  4. `factory_scheduler.py`
- 这一步才开始逐步引入：
  - `VectorSearchGateway`
  - `IncubationGateway`
  - 必要的 Repository / Validation / Risk adapter
- 完成标准：
  - 旧测试里的 patch 路径继续有效
  - `get_strategy_factory_scheduler()` 单例语义不变

#### Step 6：最后再清理反向依赖
- 目标对象：
  - `strategy_autonomy.py`
  - `strategy_generators.py`
  - `strategy_pipeline.py`
  - `vector_platform.py`
  - `strategy_stages.py`
- 做法：
  - 全部从“直接 import 内部文件”改为依赖 facade 或公共 contracts
- 完成标准：
  - 外部模块不再依赖 `strategy_factory` 内部目录结构

### 0.2 现在先不要做的事

- 不要一开始就迁 `collect.py`、`opportunity.py`、`event_engine.py` 全家桶
- 不要一开始就强行把所有调用方切到新包路径
- 不要在第一阶段删除旧目录实现
- 不要把“导入兼容”误判成“patch 兼容”
- 不要追求一步到位的完美分层，先保证运行语义不变

### 0.3 一句话实施顺序

先建基线和兼容清单，再建新包和 facade，然后只迁低耦合模块；等兼容层站稳后，再迁 `backtest_filter`、`submitter`、`factory_scheduler`，最后才清理外部反向依赖。

---

## 1. 背景与目标

当前策略工厂代码位于 `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory/`，但其职责已经超出“单纯服务层子模块”：
- 内含完整的工厂流水线编排（`factory_scheduler.py`）
- 内含候选生成、回测过滤、去重、提交、淘汰、因子研究、事件研究等领域逻辑
- 已被 `server.py`、`tools/managers/strategy_mgr_lifecycle.py`、`strategy_autonomy.py`、`vector_platform.py`、`strategy_pipeline.py`、`strategy_lifecycle_shared.py` 以及多组测试直接依赖

目标：将策略工厂逐步迁移为与 `packages/akshare-mcp/` 同级的独立包 `packages/strategy-factory/`，同时保留现有 `akshare_mcp.services.strategy_factory` 导入路径的兼容层，避免一次性大重构。

---

## 2. 基于当前代码的现状盘点

### 2.1 现有核心模块

目录：`packages/akshare-mcp/src/akshare_mcp/services/strategy_factory/`

核心模块包括：
- 编排与入口：`__init__.py`、`factory_scheduler.py`、`scheduler.py`、`runtime.py`
- 数据与机会：`collect.py`、`opportunity.py`、`event_engine.py`、`factor_research.py`
- 候选生成：`spawner.py`、`candidate.py`
- 筛选与分析：`backtest_filter.py`、`deduplicator.py`、`analysis.py`
- 提交与执行：`submitter.py`、`submission_gate.py`、`elimination.py`、`execution.py`
- 共享能力：`constants.py`、`targets.py`、`naming.py`、`panels.py`、`quality_gates.py`、`quality_reporting.py`、`utils.py`

### 2.2 当前包级导出

`__init__.py` 直接导出以下对象并提供单例入口：
- 组件：`DataCollector`、`MarketOpportunityScanner`、`StrategySpawner`、`BacktestFilter`、`Deduplicator`、`StrategySubmitter`、`EliminationChecker`、`FactorResearchBuilder`、`StrategyFactoryScheduler`
- 工具函数：`run_gated_filter`、`run_gated_submission_pipeline`、`run_submission_quality_gate`、`_auto_name`、`_build_strategy_panels`、`_run_validation_report`、`_run_risk_report`
- 单例入口：`get_strategy_factory_scheduler()`

这意味着当前 `strategy_factory` 既是“领域实现”，又是“外部 API 门面层”。

---

## 3. 当前真实依赖关系

### 3.1 策略工厂依赖的 MCP 服务

从当前 import 可见，策略工厂直接依赖以下 MCP 服务：
- `..strategy_autonomy_lifecycle`：`factory_scheduler.py`
- `..factor_scheduler`：`factor_research.py`
- `..vector_search.VectorSearchEngine`：`deduplicator.py`
- `..backtest.strategy_registry`、`..data_pipeline.normalize_klines`、`..risk_model.RiskModel`、`..validation.FactorValidationPipeline`：`panels.py`
- 运行时动态依赖：
  - `strategy_autonomy.py` 中的自治生成服务，由 `factory_scheduler.py` 在运行时调用
  - `incubation.py`、`incubation_pipeline.py`，由 `submitter.py` 在提交后处理孵化

### 3.2 策略工厂依赖的存储能力

策略工厂没有只依赖单一 `storage/timescaledb/strategy.py`，而是依赖一个“聚合式 db 接口”。实际调用的方法分散在：
- 策略实体相关：`save_strategy`、`save_strategy_lineage`
- 运行记录：`save_strategy_factory_run`、`list_strategy_factory_runs`、`get_strategy_factory_run`、`get_latest_strategy_factory_run`
- 事件与市场内部数据：对应 `storage/timescaledb/strategy_ai.py` 与 `schema_strategy.py` 中的 `strategy_factory_*` 表

结论：未来独立包不应直接依赖 `akshare_mcp.storage.timescaledb.strategy.py` 的具体实现，而应依赖一个显式的 `StrategyFactoryRepository` 协议/接口。

### 3.3 MCP 服务层如何调用策略工厂

当前主要调用点：
- `packages/akshare-mcp/src/akshare_mcp/server.py`
  - 启动时 `from .services.strategy_factory import get_strategy_factory_scheduler`
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_mgr_lifecycle.py`
  - `handle_factory_status()` / `handle_factory_run_once()` 通过 `get_strategy_factory_scheduler()` 调度
- 其他服务反向依赖：
  - `strategy_autonomy.py`：使用 `strategy_factory.utils`，并导入 `StrategySubmitter`
  - `strategy_autonomy_components.py`：使用 `strategy_factory.utils._extract_event_context`
  - `strategy_generators.py`：依赖 `strategy_factory.constants` 和 `utils`
  - `strategy_pipeline.py`、`strategy_lifecycle_shared.py`：依赖 `strategy_factory.constants`
  - `vector_platform.py`：依赖 `_build_strategy_panels`
  - `strategy_stages.py`：依赖 `event_engine`、`runtime`、`constants`

结论：当前已经存在明显的“反向耦合”——不只是工厂依赖 MCP，MCP 也在消费工厂内部工具。

---

## 4. 重构总体设计

### 4.1 新包目录建议

建议新增：`packages/strategy-factory/src/strategy_factory/`

建议结构：
- `api/`
  - `facade.py`：对外稳定入口（`get_scheduler`、`run_submission_quality_gate` 等）
  - `contracts.py`：Repository / Service / Gateway 协议定义
- `application/`
  - `scheduler.py`
  - `submission_pipeline.py`
  - `quality_gates.py`
- `domain/`
  - `candidates.py`
  - `research.py`
  - `dedup.py`
  - `naming.py`
  - `targets.py`
  - `constants.py`
- `infrastructure/`
  - `mcp_adapters.py`：适配 `strategy_autonomy` / `factor_scheduler` / `vector_search` / `incubation`
  - `db_repository.py`：适配现有 TimescaleDB 聚合 db
- `compat/`
  - 兼容旧模块名的转发层

### 4.2 分层原则

- `domain`：纯领域逻辑，不 import `akshare_mcp.services.*`
- `application`：编排流程，只依赖 `contracts`
- `infrastructure`：适配 MCP 现有服务与 DB
- `api/facade`：提供稳定对外 API，供 `akshare_mcp` 兼容层复用

### 4.3 循环依赖处理策略

必须拆掉以下方向：
- `strategy_autonomy*` / `strategy_generators` / `strategy_pipeline` / `vector_platform` 直接 import 工厂内部 utils/constants

处理办法：
1. 把真正通用的常量和 helper 提升到新包稳定 API，禁止外部引用内部文件路径
2. 为外部依赖定义更窄的 facade，例如：
   - `strategy_factory.api.get_factory_constants()`
   - `strategy_factory.api.extract_event_context()`
   - `strategy_factory.api.build_strategy_panels()`
3. 工厂编排中对 MCP 服务的访问改为“注入 gateway”而不是直接 import
4. `get_strategy_factory_package()` 这类 monkeypatch 机制逐步替换为显式依赖注入

---

## 5. 向后兼容方案

保留现有路径：`akshare_mcp.services.strategy_factory`

兼容方式：
- 第一阶段不删除旧目录
- 旧目录文件改为薄封装：
  - `from strategy_factory.api.facade import ...`
  - `from strategy_factory.application.scheduler import StrategyFactoryScheduler`
- `get_strategy_factory_scheduler()` 继续保留在 `akshare_mcp.services.strategy_factory.__init__`，内部改为调用新包
- 继续保留 `analysis.py` / `data.py` / `execution.py` / `candidate.py` / `scheduler.py` 这些兼容导出模块

这样可保证以下导入暂时不变：
- `from akshare_mcp.services.strategy_factory import ...`
- `from akshare_mcp.services.strategy_factory.scheduler import StrategyFactoryScheduler`
- 测试中的 monkeypatch 路径可继续工作

---

## 6. 分阶段迁移计划

### 阶段 0：建立安全网
- 补强并固定当前测试基线：
  - `tests/test_strategy_factory_and_marketplace.py`
  - `tests/test_strategy_factory_gate_report.py`
  - `tests/test_strategy_factory_module_compat.py`
  - `tests/test_backtest_filter_concurrency.py`
- 新增“兼容导出契约测试”：验证旧导入路径和新导入路径返回同一对象或等价对象

### 阶段 1：先抽接口，不搬代码
- 在新包定义 `contracts.py`
- 为 db、vector search、autonomy、factor research、incubation 建立协议接口
- 在 `akshare-mcp` 内实现 adapter，但旧逻辑仍在原目录运行

### 阶段 2：迁移纯领域模块
- 优先迁移低耦合文件：`constants.py`、`naming.py`、`targets.py`、`spawner.py`
- 再迁移中耦合文件：`quality_reporting.py`、`quality_gates.py`、`backtest_filter.py`
- 旧目录改为 re-export

### 阶段 3：迁移重耦合流程模块
- 迁移 `collect.py`、`opportunity.py`、`event_engine.py`、`factor_research.py`、`deduplicator.py`、`submitter.py`、`elimination.py`
- 将对 `factor_scheduler`、`vector_search`、`incubation*` 的调用改为 adapter 注入

### 阶段 4：迁移编排入口
- 迁移 `factory_scheduler.py` 到新包 `application/scheduler.py`
- `akshare_mcp.services.strategy_factory.get_strategy_factory_scheduler()` 仅保留兼容门面
- `server.py` 与 `strategy_mgr_lifecycle.py` 后续可逐步切换到新包 facade

### 阶段 5：收敛反向依赖
- 清理 `strategy_autonomy.py`、`strategy_generators.py`、`strategy_pipeline.py`、`vector_platform.py`、`strategy_stages.py` 对工厂内部模块路径的直接 import
- 全部改为依赖新包 facade / contracts

### 阶段 6：最终收尾
- 当所有调用点切至新包后，旧目录只保留兼容层
- 观察 1~2 个版本周期后，再评估是否移除旧兼容模块

---

## 7. 风险与落地建议

主要风险：
- monkeypatch 路径变化导致测试失效
- db 能力是“鸭子类型接口”，抽象不当会引入隐藏回归
- `strategy_autonomy` 与工厂互相引用，容易形成迁移中间态循环依赖
- 新包虽然位于 monorepo 的 `packages/` 下，但当前仓库没有根级 Python workspace；若不补齐依赖/安装链路，新包目录存在也无法被 `akshare-mcp` 稳定导入

建议：
- 先保留旧 import 路径，避免大面积改调用方
- 先抽 facade + contracts，再迁移实现
- 每迁移一批模块，就运行策略工厂相关测试全套回归
- 对 `get_strategy_factory_scheduler()` 保持单例语义不变，避免服务启动行为变化
- compat 设计时同时验证“导出兼容”和“patch 兼容”，不要把 `import 能成功` 误当成 `兼容层完成`

## 8. 建议的首批实施清单

1. 新建 `packages/strategy-factory/`
2. 抽出 `contracts.py`、`api/facade.py`
3. 首批迁移 `constants.py`、`naming.py`、`targets.py`、`spawner.py`
4. 在 `akshare_mcp.services.strategy_factory` 建立 re-export 兼容层
5. 增加新旧路径兼容测试
6. 再迁移 `factory_scheduler.py` 与 `submitter.py`


## 9. 可执行 Todo 清单（按阶段拆分）

> 建议执行原则：每完成一个小阶段，就先跑兼容测试，再进入下一阶段；不要先迁完再统一修。

### Phase 0：建立基线与迁移保护网

**目标**：先把“现在能工作的状态”冻结下来，避免迁移过程中出现静默回归。

#### Todo 0.1：固化当前策略工厂测试入口
- 涉及文件：
  - `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
  - `packages/akshare-mcp/tests/test_strategy_factory_gate_report.py`
  - `packages/akshare-mcp/tests/test_strategy_factory_module_compat.py`
  - `packages/akshare-mcp/tests/test_backtest_filter_concurrency.py`
  - `packages/akshare-mcp/tests/test_concurrency_optimization.py`
- 动作：
  - 整理一组“迁移最小回归集”
  - 在文档或 CI 脚本中固定执行顺序
- 验收标准：
  - 能单独运行这组测试
  - 失败时能快速定位是兼容层问题、调度器问题还是依赖注入问题

#### Todo 0.2：新增兼容导出契约测试
- 建议新增文件：
  - `packages/akshare-mcp/tests/test_strategy_factory_package_migration_contract.py`
- 动作：
  - 验证旧路径与新路径导出的核心符号一致或等价：
    - `StrategyFactoryScheduler`
    - `StrategySpawner`
    - `BacktestFilter`
    - `Deduplicator`
    - `StrategySubmitter`
    - `EliminationChecker`
    - `get_strategy_factory_scheduler`
- 验收标准：
  - 旧路径导入不变
  - 新旧路径可同时工作

#### Todo 0.3：梳理 DB 最小能力清单
- 涉及文件：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory/*.py`
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy_ai.py`
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py`
- 动作：
  - 统计工厂真实调用的 db 方法，形成接口清单
- 交付物：
  - 一份 `StrategyFactoryRepository` 方法列表
- 验收标准：
  - 后续抽象接口时不再靠人工猜测补方法

#### Todo 0.4：梳理兼容层 monkeypatch/patch-point 清单
- 涉及文件：
  - `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
  - `packages/akshare-mcp/tests/test_strategy_factory_gate_report.py`
  - `packages/akshare-mcp/tests/test_backtest_filter_concurrency.py`
  - `packages/akshare-mcp/tests/test_concurrency_optimization.py`
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory/runtime.py`
- 动作：
  - 统计哪些旧路径正在被 `patch()` / `monkeypatch.setattr()` 直接命中
  - 区分“仅导入兼容”与“必须保留可 patch 的模块级符号”两类兼容要求
  - 明确以下典型 patch 点是否需要继续保留：
    - `akshare_mcp.services.strategy_factory.asyncio.to_thread`
    - `akshare_mcp.services.strategy_factory.factory_scheduler.get_strategy_factory_package`
    - `akshare_mcp.services.strategy_factory.factory_scheduler._call_optional_async`
    - `akshare_mcp.services.strategy_factory.*` 包级组件类导出
- 交付物：
  - 一份“兼容 patch-point 清单”，作为 compat 层设计输入
- 验收标准：
  - 后续兼容设计不只保证 import 成功，还保证旧 patch 路径继续生效

### Phase 1：创建新包骨架，但暂不搬实现

**目标**：先把独立包目录、协议层和 facade 搭出来，让迁移有承载体。

#### Todo 1.1：创建独立包目录
- 建议新增目录：
  - `packages/strategy-factory/pyproject.toml`
  - `packages/strategy-factory/src/strategy_factory/__init__.py`
  - `packages/strategy-factory/src/strategy_factory/api/`
  - `packages/strategy-factory/src/strategy_factory/application/`
  - `packages/strategy-factory/src/strategy_factory/domain/`
  - `packages/strategy-factory/src/strategy_factory/infrastructure/`
  - `packages/strategy-factory/src/strategy_factory/compat/`
- 动作：
  - 为新包补齐 `pyproject.toml`，确保 `strategy_factory` 可被独立安装
  - 明确本仓库内的 Python 导入链路如何生效：
    - 更新 `packages/akshare-mcp/pyproject.toml`，声明对新包的开发依赖或本地路径依赖
    - 如继续使用当前 `uv`/本地开发环境，补充 `uv.lock` 或开发安装说明
    - 明确 CI / 本地测试时 `pytest packages/strategy-factory/tests -q` 的执行前提
- 验收标准：
  - 在当前 `akshare-mcp` 开发环境中可直接 `import strategy_factory`
  - 旧包兼容层可稳定导入新包，而不是依赖临时 `PYTHONPATH`

#### Todo 1.2：定义 contracts 协议层
- 建议新增文件：
  - `packages/strategy-factory/src/strategy_factory/api/contracts.py`
- 需要抽象的接口：
  - `StrategyFactoryRepository`
  - `VectorSearchGateway`
  - `AutonomyGateway`
  - `FactorResearchGateway`
  - `IncubationGateway`
  - `ValidationGateway`
  - `RiskGateway`
- 验收标准：
  - `application` 层代码不再需要直接 import `akshare_mcp.services.*`

#### Todo 1.3：建立 facade 稳定入口
- 建议新增文件：
  - `packages/strategy-factory/src/strategy_factory/api/facade.py`
- 首批暴露接口：
  - `get_strategy_factory_scheduler()`
  - `run_submission_quality_gate()`
  - `build_strategy_panels()`
  - `extract_event_context()`
  - `get_factory_constants()`
- 验收标准：
  - 兼容层未来只依赖 facade，不依赖新包内部实现路径

### Phase 2：迁移低耦合纯领域模块

**目标**：先搬最容易搬的模块，快速验证新包路径与兼容层模式可行。

#### Todo 2.1：迁移 constants / naming / targets
- 当前文件：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory/constants.py`
  - `.../naming.py`
  - `.../targets.py`
- 新位置建议：
  - `packages/strategy-factory/src/strategy_factory/domain/constants.py`
  - `.../domain/naming.py`
  - `.../domain/targets.py`
- 动作：
  - 原样迁移逻辑
  - 旧路径改为 re-export
- 验收标准：
  - `test_strategy_factory_module_compat.py` 通过
  - 旧 import 路径不变

#### Todo 2.2：迁移 `spawner.py`
- 新位置建议：
  - `packages/strategy-factory/src/strategy_factory/domain/spawner.py`
- 依赖处理：
  - 仅保留对 `domain.constants` 的依赖
- 验收标准：
  - `StrategySpawner` 相关测试全部通过
  - `candidate.py` 继续作为兼容导出层存在

#### Todo 2.3：迁移 `quality_reporting.py`
- 新位置建议：
  - `packages/strategy-factory/src/strategy_factory/application/quality_reporting.py`
- 验收标准：
  - 原提交质检结果结构不变

### Phase 3：迁移中耦合模块并引入 adapter

**目标**：把依赖 MCP 服务的模块迁移出去，但通过 adapter 隔离耦合。

#### Todo 3.1：迁移 `backtest_filter.py`
- 新位置建议：
  - `packages/strategy-factory/src/strategy_factory/application/backtest_filter.py`
- 依赖点：
  - `get_strategy_factory_package()`
  - 目标股票解析 helper
- 动作：
  - 先保留行为兼容
  - 再把 package 级 monkeypatch 改为显式注入 runner / helper
- 验收标准：
  - `test_backtest_filter_concurrency.py` 不回归

#### Todo 3.2：迁移 `deduplicator.py`
- 新位置建议：
  - `packages/strategy-factory/src/strategy_factory/application/deduplicator.py`
- 依赖点：
  - `VectorSearchEngine`
- 动作：
  - 新增 `VectorSearchGateway` adapter
  - 由 `akshare-mcp` 提供默认实现
- 验收标准：
  - 去重结果结构不变
  - 向量回退逻辑不变

#### Todo 3.3：迁移 `factor_research.py` / `event_engine.py`
- 新位置建议：
  - `application/factor_research.py`
  - `application/event_engine.py`
- 依赖点：
  - `factor_scheduler`
- 动作：
  - 用 `FactorResearchGateway` 取代对 `get_factor_scheduler()` 的直接 import
- 验收标准：
  - 因子 artifact 输出结构不变

#### Todo 3.4：迁移 `collect.py` / `opportunity.py`
- 新位置建议：
  - `application/collect.py`
  - `application/opportunity.py`
- 依赖点：
  - 当前运行时通过 `get_strategy_factory_package()` 读取可 monkeypatch 导出
- 动作：
  - 先保留现有行为
  - 再把 collector / scanner 所需外部能力拆到 gateway 或 facade
- 验收标准：
  - `DataCollector` 和 `MarketOpportunityScanner` 的输出结构不变
  - 调度器对这两个组件的调用方式保持兼容

#### Todo 3.5：迁移 `submitter.py` / `submission_gate.py` / `elimination.py`
- 新位置建议：
  - `application/submitter.py`
  - `application/submission_gate.py`
  - `application/elimination.py`
- 依赖点：
  - `incubation.py`
  - `incubation_pipeline.py`
  - 策略状态更新与质量报告
- 动作：
  - 抽 `IncubationGateway`
  - 抽 `StrategyStatusWriter` 或并入 Repository 接口
- 验收标准：
  - 提交后状态流转不变
  - `run_submission_quality_gate()` 输出字段不变

### Phase 4：迁移编排入口与单例调度器

**目标**：把真正的“工厂主入口”迁到独立包，但不破坏现有启动方式。

#### Todo 4.1：迁移 `factory_scheduler.py`
- 当前文件：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory/factory_scheduler.py`
- 新位置建议：
  - `packages/strategy-factory/src/strategy_factory/application/scheduler.py`
- 动作：
  - 先原样迁移逻辑
  - 把内部对包级导出的动态访问收敛为 facade / 注入对象
- 验收标准：
  - `StrategyFactoryScheduler.run_once()` 输出结构不变
  - `status()` / `start()` / `stop()` 行为不变

#### Todo 4.2：保留旧单例入口兼容
- 需要修改文件：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory/__init__.py`
- 动作：
  - 旧的 `_factory_scheduler` 和 `get_strategy_factory_scheduler()` 保持存在
  - 实际底层实例改由新包创建
- 验收标准：
  - `server.py` 无需修改即可启动策略工厂
  - `strategy_mgr_lifecycle.py` 无需修改即可查询状态/运行一次

#### Todo 4.3：保留叶子兼容模块
- 需要保留的兼容文件：
  - `analysis.py`
  - `candidate.py`
  - `data.py`
  - `execution.py`
  - `scheduler.py`
  - `utils.py`
- 动作：
  - 默认做 re-export，但对存在 patch 点的模块保留 shim 层
  - shim 层需要继续暴露旧的模块级符号，尤其是：
    - `asyncio`
    - `get_strategy_factory_package`
    - `_call_optional_async`
    - 旧测试直接 patch 的类/函数名
  - 如无法仅靠 re-export 保留 patch 语义，则在 compat 层显式转发调用，而不是让测试/运行时直接落到新模块对象
- 验收标准：
  - `test_strategy_factory_module_compat.py` 继续通过
  - 现有依赖旧 patch 路径的测试继续通过

### Phase 5：清理反向依赖并收敛 API

**目标**：不再让 MCP 其他服务直接依赖工厂内部文件路径。

#### Todo 5.1：替换对 `strategy_factory.utils` 的直接依赖
- 当前调用点：
  - `strategy_autonomy.py`
  - `strategy_autonomy_components.py`
  - `strategy_generators.py`
- 动作：
  - 改为从新包 facade 导入：
    - `extract_event_context`
    - `auto_name`
    - 其他需要公开的 helper
- 验收标准：
  - MCP 侧不再 import `akshare_mcp.services.strategy_factory.utils`

#### Todo 5.2：替换对 `strategy_factory.constants` 的直接依赖
- 当前调用点：
  - `strategy_generators.py`
  - `strategy_pipeline.py`
  - `strategy_lifecycle_shared.py`
  - `strategy_stages.py`
  - `tools/managers/strategy_mgr_helpers.py`
- 动作：
  - 改为依赖：
    - 新包 facade 暴露的常量对象
    - 或单独的公共 constants 模块
- 验收标准：
  - 常量来源收敛到稳定路径

#### Todo 5.3：替换对 `panels.py` / `event_engine.py` / `runtime.py` 的内部路径依赖
- 当前调用点：
  - `vector_platform.py`
  - `strategy_stages.py`
- 动作：
  - 新包 facade 暴露：
    - `build_strategy_panels`
    - `call_optional_async`
    - `get_local_event_engine`
- 验收标准：
  - 外部模块不再依赖新包内部目录结构

### Phase 6：收尾、观测与正式切换

**目标**：完成迁移后的稳定运行与清理。

#### Todo 6.1：增加迁移完成标记与弃用说明
- 需要修改文件：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory/__init__.py`
  - 相关开发文档
- 动作：
  - 注释说明旧路径为兼容层
  - 标明后续统一迁往 `packages/strategy-factory/`
- 验收标准：
  - 新同学能一眼看出真正实现所在位置

#### Todo 6.2：补充回归验证清单
- 建议至少验证：
  - 服务启动后 `get_strategy_factory_scheduler().start()` 正常
  - `run_once()` 能完整跑通
  - `save_strategy_factory_run()` 正常持久化
  - gate report / dedup / submit / elimination 关键字段不变
- 验收标准：
  - 线上/预发 smoke test 无明显功能偏差

#### Todo 6.3：观察 1~2 个迭代周期后再裁剪旧实现
- 动作：
  - 先保留兼容层
  - 等调用方全部切换完成后，再评估是否删除旧目录中的实现代码
- 验收标准：
  - 不在迁移当期做激进清理

## 10. 建议的实际实施顺序（最小风险版）

按这个顺序做，风险最低：

1. 建立测试基线与兼容契约测试
2. 创建 `packages/strategy-factory/` 包骨架
3. 抽 `contracts.py` 和 `facade.py`
4. 迁移 `constants.py`、`naming.py`、`targets.py`
5. 迁移 `spawner.py`
6. 迁移 `quality_reporting.py`
7. 迁移 `backtest_filter.py`
8. 迁移 `deduplicator.py`
9. 迁移 `factor_research.py`、`event_engine.py`
10. 迁移 `collect.py`、`opportunity.py`
11. 迁移 `submitter.py`、`submission_gate.py`、`elimination.py`
12. 迁移 `factory_scheduler.py`
13. 最后再收敛 `strategy_autonomy.py`、`vector_platform.py`、`strategy_pipeline.py` 等外部调用方

## 11. 每个阶段完成后的建议验证命令

可在项目根目录执行，作为人工回归最小集：

```bash
cd /Users/mac/Desktop/股票
pytest packages/akshare-mcp/tests/test_strategy_factory_module_compat.py -q
pytest packages/akshare-mcp/tests/test_strategy_factory_gate_report.py -q
pytest packages/akshare-mcp/tests/test_backtest_filter_concurrency.py -q
pytest packages/akshare-mcp/tests/test_concurrency_optimization.py -q
pytest packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py -q
```

如果后面创建了新包自己的测试，也建议追加：

```bash
pytest packages/strategy-factory/tests -q
```

## 12. 推荐的第一周实施拆分

### Day 1
- 建测试基线
- 新增兼容契约测试
- 梳理 Repository / Gateway 方法表

### Day 2
- 创建 `packages/strategy-factory/` 骨架
- 创建 `contracts.py`、`facade.py`
- 打通最小导入链路

### Day 3
- 迁移 `constants.py`、`naming.py`、`targets.py`
- 做旧路径 re-export
- 跑兼容测试

### Day 4
- 迁移 `spawner.py`、`quality_reporting.py`
- 修复兼容导出
- 跑核心测试

### Day 5
- 评估并开始迁移 `backtest_filter.py` / `deduplicator.py`
- 明确 adapter 注入方案
- 输出第二周实施计划
