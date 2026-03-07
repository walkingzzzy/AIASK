## 项目上下文摘要（规则命中统计）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `apps/web/app/strategy-market/page.tsx`
  - 模式：`FactoryRunFailurePanel` 已完成失败率、错误指纹 Top、失败阶段 Top 展示
  - 可复用：`FactoryMetric`、`failedRuns`、`getFactoryRunErrorFingerprint()`、`normalizeFactoryRunError()`
  - 需注意：当前只展示指纹标签与示例，未暴露规则是否命中、未分类数量与覆盖率

- **实现2**: `.claude/context-summary-错误指纹标准化.md`
  - 模式：上一轮已经确认错误指纹是前端轻量规则，不扩后端、不引入依赖
  - 可复用：规则分类边界、验证策略、风险说明
  - 需注意：本轮必须保持“规则统计”仍是页面聚合，不伪装为服务端审计指标

- **实现3**: `策略工厂/03-模块功能方案.md`
  - 模式：接口与展示当前能力已包含失败原因聚合与错误指纹标准化
  - 可复用：当前能力/短期重点的分期表达
  - 需注意：本轮应记为聚合看板继续增强，而不是新增接口能力

### 2. 项目约定
- **命名约定**: 继续在 `page.tsx` 内使用 `Factory*` 与 `*ErrorFingerprint` 命名
- **文件组织**: 代码仍集中在 `apps/web/app/strategy-market/page.tsx`
- **代码风格**: 采用轻量统计与文本列表，不引入图表库和第三方分类库

### 3. 可复用组件清单
- `FactoryRunFailurePanel`
- `FactoryMetric`
- `getFactoryRunErrorFingerprint()`
- `normalizeFactoryRunError()`
- `failedRuns`

### 4. 测试策略
- **现有测试模式**: `apps/web/e2e/core-flows.spec.ts` 使用 Playwright `test.describe/test/expect`
- **当前验证方式**: `diagnostics` + `git diff --check`
- **阻塞说明**: 当前环境缺少 `next`，不重复执行已知失败的 Web build/E2E
- **关注点**:
  - 指纹函数能区分“命中规则 / 未分类”
  - 未分类示例列表有去重与数量控制
  - 新统计不破坏现有失败原因与阶段分布展示

### 5. 依赖和集成点
- **数据来源**: `/strategy-market/factory/runs?limit=5`
- **页面位置**: `FactoryRunFailurePanel` 内部新增规则命中统计区块
- **外部依赖**: 无新增

### 6. 技术选型理由
- 在前端补 `matched` 元信息即可低成本得到规则命中率与未分类数量
- 继续复用现有失败聚合面板，避免再造一层平行分析组件
- 用未分类示例列表反向指导后续扩规则，收益直接且风险低

### 7. 关键风险点
- 样本窗口只有最近 5 次运行，统计结果更偏即时观测而非长期结论
- 若把“未分类错误”也算入覆盖指纹，需要在文案上明确口径
- 当前仍缺前端自动化交互测试，只能依赖静态验证与代码审查
