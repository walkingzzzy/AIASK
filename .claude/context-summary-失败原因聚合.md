## 项目上下文摘要（失败原因聚合）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `apps/web/app/strategy-market/page.tsx`
  - 模式：已存在运行历史列表、详情、对比、趋势、状态筛选与指标切换
  - 可复用：`factoryRunsQ`、`FactoryRunTrendPanel`、运行历史区域布局
  - 需注意：失败聚合应与现有卡片风格一致，不新增页面

- **实现2**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py`
  - 模式：`run_once()` 会写入 `status`、`error`、`stages`
  - 可复用：阶段顺序 `collect -> spawn -> backtest -> deduplicate -> submit -> elimination`
  - 需注意：失败时不一定显式记录 `ok: false`，阶段分析要保守推断

- **实现3**: `策略工厂/02-接口定义与数据模型.md`
  - 模式：已明确 `status`、`error`、`stages` 都属于可复用运行摘要/详情对象
  - 可复用：工厂运行摘要字段权威口径
  - 需注意：失败聚合只使用当前已有字段，不扩接口

### 2. 项目约定
- **命名约定**: 失败聚合组件继续使用 `Factory*` 命名
- **文件组织**: 本轮只修改 `apps/web/app/strategy-market/page.tsx`
- **代码风格**: 轻量文本聚合 + 小列表，不引入复杂图表或统计库

### 3. 可复用组件清单
- `factoryRunsQ`
- `FactoryMetric`
- 现有运行历史卡片区域
- `run_once()` 的既有阶段顺序

### 4. 测试策略
- **验证方式**: `diagnostics` + `git diff --check`
- **阻塞说明**: 当前 Node 环境缺少 `next`，不重复触发已知失败的 Web build
- **关注点**:
  - `stages` 缺失时推断逻辑不报错
  - 失败原因为空时有兜底文案
  - 无失败记录时正确空态

### 5. 依赖和集成点
- **数据来源**: `/strategy-market/factory/runs?limit=5`
- **页面位置**: 工厂运行态卡片内部，趋势区块之后
- **后端依赖**: 无新增

### 6. 技术选型理由
- 直接前端聚合失败原因，避免新增统计接口
- 通过阶段顺序推断失败阶段，满足当前轻量分析需求
- 继续沿用最近 5 次运行窗口，保持页面复杂度可控

### 7. 关键风险点
- 阶段失败推断不是强审计，只能做“最近失败聚合”参考
- 错误信息可能过长，需要规范化后再聚合
- 当前仍无前端交互自动化测试，只能依赖静态校验
