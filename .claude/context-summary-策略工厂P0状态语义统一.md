## 项目上下文摘要（策略工厂P0状态语义统一）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:47-61,193-213,296-326,581-628`
  - 模式：生命周期常量、`publish/list/rank` 动作与 `lifecycle_scan` 统一在 manager 收口
  - 可复用：`_validate_transition()`、`_update_status()`、`_lifecycle_scan()`
  - 需注意：当前 `published/listed` 与 `incubating` 失败流转存在语义分叉

- **实现2**: `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:84-142,451-457`
  - 模式：存储层负责状态查询、状态更新与事件落库
  - 可复用：`update_strategy_status()`、`list_strategies()`、`count_strategies_by_type()`
  - 需注意：这里是状态别名归一与事件去噪的最佳落点

- **实现3**: `apps/bff/src/strategy/strategy.service.ts:116-132`
  - 模式：BFF 排名接口通过 `fetchRankingWithCache()` 固定默认状态
  - 可复用：现有缓存键与转发结构无需重写，只需替换默认查询口径
  - 需注意：如果不改这里，前端仍会继续请求历史 `published`

- **实现4**: `apps/web/app/strategy-market/[id]/page.tsx:180-183`
  - 模式：前端状态徽标已兼容 `published/listed`
  - 可复用：可暂时保留双识别，避免历史脏数据导致 UI 异常
  - 需注意：前端展示可兼容，后端状态必须先统一

### 2. 项目约定
- **命名约定**: 生命周期状态使用小写英文字符串；manager 通过 `action` 分发
- **文件组织**: 业务语义在 `tools/managers`，持久化在 `storage/timescaledb`，BFF 仅做转发与缓存
- **代码风格**: Python 使用轻量 helper 归一输入；TypeScript 尽量只改默认参数，不扩散改动

### 3. 可复用组件清单
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:_validate_transition`
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:_lifecycle_scan`
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:update_strategy_status`
- `apps/bff/src/strategy/strategy.service.ts:fetchRankingWithCache`

### 4. 测试策略
- **测试框架**: `pytest`
- **参考文件**: `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
- **验证方式**: 先跑该测试文件，再跑 `diagnostics` 检查 BFF / Web 改动
- **覆盖重点**:
  - `publish` 动作写入 canonical `listed`
  - `published` 查询别名仍可读到 `listed`
  - 生命周期合法迁移不再接受 `incubating -> rejected`

### 5. 依赖和集成点
- **内部依赖**: manager → storage mixin → `strategy_status_events`
- **BFF 集成**: `strategy.service.ts` 的 ranking 缓存默认值依赖 manager `rank`
- **前端集成**: 详情页状态徽标依赖 BFF 返回的 `strategy.status`

### 6. 技术选型理由
- 使用“canonical 状态 + 兼容别名归一”方案，而不是保留双状态长期共存
- 在存储层统一别名，可最小化上层改动并避免历史数据造成读写分叉

### 7. 关键风险点
- **事件噪声**: 历史 `published` 数据被归一时不能错误地产生真实业务迁移事件
- **测试桩漂移**: `_StrategyDB` 若不同步归一，会导致兼容测试与真实存储语义不一致
- **前端残留**: BFF 默认排名若未切到 `listed`，页面仍会走旧口径