## 项目上下文摘要（运行趋势视图）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `apps/web/app/strategy-market/page.tsx`
  - 模式：已存在工厂运行态卡片、最近运行历史、运行详情展开、最近运行对比
  - 可复用：`factoryRunsQ`、`FactoryMetric`、`FactoryRunComparisonTable`
  - 需注意：趋势视图应直接复用已有历史数据，不新增接口

- **实现2**: `策略工厂/02-接口定义与数据模型.md`
  - 模式：已沉淀工厂运行摘要字段
  - 可复用：`status`、`candidates_spawned`、`submitted`、`passed_quality_gate`、`elapsed_seconds`
  - 需注意：趋势展示只使用当前已存在字段

- **实现3**: `策略工厂/03-模块功能方案.md`
  - 模式：当前文档把“运行历史对比/趋势”视为调度与运行态的短期方向
  - 可复用：当前/短期/中期表达方式
  - 需注意：不能把轻量趋势视图写成完整运维台

### 2. 项目约定
- **命名约定**: 前端趋势组件继续使用 `Factory*` 命名
- **文件组织**: 本轮只修改 `apps/web/app/strategy-market/page.tsx`
- **代码风格**: 不引入图表库，采用简单摘要卡 + 轻量柱状条

### 3. 可复用组件清单
- `factoryRunsQ`
- `FactoryMetric`
- `FactoryRunComparisonTable`
- `SectionCard`
- `FactoryRunDetailPanel`

### 4. 测试策略
- **验证方式**: `diagnostics` + `git diff --check`
- **阻塞说明**: 当前 Node 环境缺少 `next`，不重复触发已知失败的 build
- **关注点**:
  - 类型正确
  - 条件渲染安全
  - 趋势计算在空值场景下有兜底

### 5. 依赖和集成点
- **数据来源**: `/strategy-market/factory/runs?limit=5`
- **页面位置**: 策略超市页工厂运行态卡片内部
- **后端依赖**: 无新增

### 6. 技术选型理由
- 直接在前端计算成功率、平均耗时与指标变化，避免扩展后端口径
- 使用柱状条替代图表库，降低依赖和维护成本
- 维持“摘要 + 历史 + 详情 + 对比 + 趋势”的递进式展示结构

### 7. 关键风险点
- 小屏幕下趋势条信息密度较高，需要保持布局简单
- 某些历史记录可能缺字段，必须统一兜底
- 当前仍无前端交互自动化测试，只能以静态校验为主
