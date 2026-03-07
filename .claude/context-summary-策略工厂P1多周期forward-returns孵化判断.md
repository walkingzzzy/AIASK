## 项目上下文摘要（策略工厂P1多周期forward-returns孵化判断）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**：`packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:219-288,778-825`
  - 模式：`_build_incubation_overview()` 汇总孵化指标，`_lifecycle_scan()` 只消费概览结果做状态流转
  - 可复用：`_metric_bucket_value()`、`overview["promotion_ready"]`、`overview["deprecation_risk"]`
  - 注意：当前仅消费 5D 命中率/前向 IC/前向 Sharpe
- **实现2**：`packages/akshare-mcp/src/akshare_mcp/services/signal_tracker.py:23,142-160`
  - 模式：Phase B 已按 `FORWARD_DAYS = [1, 5, 10, 20]` 逐周期落库 forward returns，Phase C 调用 `_lifecycle_scan()`
  - 可复用：现有多周期来源与生命周期扫描主流程
  - 注意：本轮无需改 tracker 主流程，只需消费已有多周期结果
- **实现3**：`packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py:685-733,952-986`
  - 模式：fake DB 通过 `_signal_stats` 直接向 manager 注入 `hit_rate / forward_ic / forward_sharpe / total_signals`
  - 可复用：`test_review_report_events_and_incubation_overview()`、生命周期状态事件记录
  - 注意：现有测试只喂 5D，需要扩成多周期场景
- **实现4**：`apps/web/app/strategy-market/[id]/page.tsx:132-145,603-635`
  - 模式：详情页工厂 Tab 通过 `IncubationOverviewResponse` 展示孵化 KPI、阻塞项和风险提示
  - 可复用：`FactoryReviewPanel`、`KpiCard`、`DataTable`
  - 注意：当前 UI 仅展示 5D 前向指标，尚无多周期明细

### 2. 项目约定
- **命名约定**：Python helper 使用下划线命名；前端响应类型使用 `*Response`
- **文件组织**：`services -> tools/managers -> apps/bff -> apps/web -> tests`
- **返回约定**：manager 统一返回 `ok/fail`，前端读取 `/strategy-market/:id/incubation-overview`
- **代码风格**：优先补轻量 helper 和 dict 契约，不新建旁路模块

### 3. 可复用组件清单
- `strategy_manager.py:_metric_bucket_value`：读取多周期桶指标
- `strategy_manager.py:_build_incubation_overview`：孵化概览唯一构造入口
- `strategy_manager.py:_lifecycle_scan`：状态流转执行入口
- `signal_tracker.py:FORWARD_DAYS`：多周期 forward returns 数据来源
- `page.tsx:FactoryReviewPanel`：工厂 Tab 展示容器

### 4. 测试策略
- **测试框架**：pytest + `AsyncMock` / `MagicMock` / monkeypatch
- **参考文件**：`packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
- **覆盖重点**：
  - `incubation_overview` 返回多周期 `forward_returns`
  - 多周期全部满足时 `promotion_ready=True`
  - 任一周期不达标时进入 `blockers_by_period`
  - 任一周期跌破淘汰阈值时 `deprecation_risk=True`
  - `_lifecycle_scan()` 在新规则下驱动 `listed/deprecated`

### 5. 依赖和集成点
- **数据来源**：`db.get_signal_stats()` 已返回多周期 `hit_rate / forward_ic / forward_sharpe`
- **生命周期集成**：`signal_tracker.run_once()` Phase C 调用 `_lifecycle_scan()`
- **前端集成**：详情页工厂 Tab 消费 `incubation_overview`
- **日志留痕**：需同步更新 `.claude/operations-log.md` 与 `.claude/verification-report.md`

### 6. 技术选型理由
- 选择在 `strategy_manager.py` 内新增多周期 helper，而不是改 `_lifecycle_scan()` 主流程，可把状态逻辑继续收口在概览层
- 保留 `hit_rate_5d / forward_ic_5d / forward_sharpe_5d` 兼容字段，避免破坏既有调用方
- 选择在前端最小增量展示多周期明细，优先满足“判定可解释”目标

### 7. 关键风险点
- **样本噪声**：样本量不足时不能因为缺少长周期窗口而误判淘汰，因此仅在达到最小信号数后要求完整观察窗口
- **兼容性**：5D 兼容字段需继续保留，避免影响既有 KPI 展示
- **工具限制**：当前环境无 GitHub `search_code` / desktop-commander，本轮以仓库内既有模式和真实磁盘源码替代，并在日志中留痕