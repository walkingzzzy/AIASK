## 项目上下文摘要（策略工厂P1质量报告复检入口）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**：`packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:71-90,239-245,330-372`
  - 模式：manager 统一收口动作、保存质量报告、返回 `ok/fail`
  - 可复用：`_save_quality_report`、`submit`、`review_report`
  - 注意：当前 `review_report` 只读单份 `submission` 报告
- **实现2**：`packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:1270-1408`
  - 模式：服务层提交时生成质量报告并落库
  - 可复用：`StrategySubmitter.submit()` 的验证/风控/质检主链路
  - 注意：当前本地 `_build_quality_report` 与 manager 口径分叉
- **实现3**：`apps/web/app/strategy-market/[id]/page.tsx:133-141,442-555`
  - 模式：详情页通过 `useApiQuery` 拉工厂审查数据，`FactoryReviewPanel` 最小展示
  - 可复用：现有工厂审查 Tab 与 DataTable/KpiCard 结构
  - 注意：尚无复检按钮与历史摘要
- **实现4**：`apps/web/hooks/use-api-mutation.ts` + `apps/web/lib/query-keys.ts`
  - 模式：`useApiMutation` + `invalidateQueries` 前缀失效
  - 可复用：模块级 query key 失效刷新
  - 注意：根据 Context7 `/tanstack/query` 文档，`['api','strategy-market']` 前缀可批量失效该模块查询

### 2. 项目约定
- **命名约定**：manager action 使用 snake_case；BFF 路由使用 REST 风格；前端响应类型使用 `*Response`
- **文件组织**：`services -> storage -> tools/managers -> apps/bff -> apps/web`
- **返回约定**：MCP manager 统一 `ok/fail`；前端读取 envelope 中 `data`
- **代码风格**：优先小 helper 复用，避免引入新模块或重型抽象

### 3. 可复用组件清单
- `strategy_manager.py:_save_quality_report`：质量报告统一落库入口
- `strategy_manager.py:_run_quality_gate`：自动化质量门禁入口
- `strategy_factory.py:StrategySubmitter.submit`：工厂提交流程主链路
- `use-api-mutation.ts`：POST/失效刷新统一模式
- `query-keys.ts:apiKeys.strategy()`：`strategy-market` 模块级 query key 前缀

### 4. 测试策略
- **测试框架**：pytest + `AsyncMock` / `MagicMock` / monkeypatch
- **参考文件**：`packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
- **覆盖重点**：
  - 质量报告统一字段
  - `review_report` 默认返回最新报告与历史摘要
  - `review_report_recheck` 生成新报告并标准化失败原因
  - 工厂 submitter 继续正确落库 validation/risk/quality 报告

### 5. 依赖和集成点
- **后端依赖**：`strategy_manager.py` 复用验证/风控/状态流转逻辑
- **存储依赖**：`strategy_quality_reports` 现有唯一键 `(strategy_id, report_type)`，适合用 `recheck:<timestamp>` 承载历史
- **BFF 集成**：`StrategyMarketService.call()` 转发 MCP action
- **Web 集成**：策略详情工厂 Tab 复用 `useApiQuery/useApiMutation`

### 6. 技术选型理由
- 选择“共享 helper + 扩展既有表查询”而非改 schema，可最小改动闭环
- 选择 recheck 新 `report_type` 保留历史，避免覆盖 `submission`
- 选择前端最小增量展示，优先完成可复检、可解释、可回归

### 7. 关键风险点
- **状态副作用**：复检若直接改生命周期会放大风险，本轮选择“只生成新报告、不直接改状态”
- **历史兼容**：旧报告只有 `reasons/reason`，需要在读取与构造时统一标准化
- **前端失效刷新**：必须用模块级 query key 前缀，避免按钮成功后详情不刷新
- **工具限制**：当前环境无 GitHub `search_code` / desktop-commander，可复用仓库内现有模式替代，并在日志中留痕