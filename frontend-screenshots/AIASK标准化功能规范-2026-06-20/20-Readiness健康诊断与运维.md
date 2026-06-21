# Readiness 健康诊断与运维

## 文档信息

| 项目 | 内容 |
|---|---|
| 项目名称 | AIASK V1 前端产品化 |
| 功能名称 | Readiness 健康诊断与运维 |
| 功能编号前缀 | `OPS` |
| 文档版本 | 1.0.0 |
| 更新日期 | 2026-06-21 |
| V1 状态 | P0 必做 |
| 代码基准 | `desktop/src/features/agent-pages/ReadinessHealthPage.tsx`、`packages/agent/src/aiask_agent/routes/health.py`、`hermes_status.py`、`desktop/src/services/aiaskApi.ts` |

### 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|---|---|---|---|
| 1.0.0 | 2026-06-21 | 按 L4 模板补齐健康、准备度、next action、四工厂 deferred 和测试 | Codex |

### 术语定义

| 术语 | 定义 | 代码证据 |
|---|---|---|
| Health | 基础运行状态 | `/health`、`/health/detailed` |
| Readiness | 业务/金融系统准备度 | `/v1/hermes/readiness`、`/v1/financial-system/readiness` |
| Next Action | 修复建议和目标页面 | readiness payload |

## 1. 功能设计

### 1.1 需求背景与价值

| 项 | 内容 |
|---|---|
| 问题陈述 | 用户需要知道为什么功能不可用，是 Agent、模型、数据、MCP、token 还是金融系统缺配置。 |
| 解决方案 | Readiness 页面展示 health、detailed health、Hermes readiness、financial readiness、next actions。 |
| 业务价值 | 提供发布和运维排障入口。 |

### 1.2 用户故事

| 编号 | 优先级 | 用户故事 | 成功标准 |
|---|---|---|---|
| OPS-US-001 | P0 | 作为交付人员，我希望看到系统健康状态。 | health/detailed 可见。 |
| OPS-US-002 | P0 | 作为用户，我希望知道下一步如何修复。 | next actions 指向 V1 页面。 |
| OPS-US-003 | P0 | 作为 PM，我希望 readiness 不跳四工厂。 | strategy/factor/incubation 显示 deferred。 |

### 1.3 功能分解与优先级

| 功能编号 | 功能点 | 优先级 | 当前代码依据 | 待开发事项 | 验收标准 |
|---|---|---|---|---|---|
| OPS-F201 | Health | P0 | `/health`、`/health/detailed` | 错误分类 | status/control/tools 可见 |
| OPS-F202 | Hermes readiness | P0 | `/v1/hermes/readiness` | 缺口解释 | ready/degraded 可见 |
| OPS-F203 | Financial readiness | P0 | `/v1/financial-system/readiness` | next action 映射 | 不跳四工厂 |
| OPS-F204 | Capability parity | P1 | `/v1/capabilities/parity` | 缺口摘要 | implemented/missing 可见 |

### 1.4 业务规则与边界

Readiness 是诊断入口，不是绕过门禁的入口；所有 next action 必须指向 V1 页面或标记 deferred。

## 2. 流程设计

状态机：`loading -> ready|degraded|error -> action_selected -> routed|deferred|blocked`。

## 3. 架构设计

Readiness 页面聚合 Agent health/hermes/financial routes；不直接读取后端内部数据库或执行修复。

## 4. 功能说明：接口与数据

| 操作 | Endpoint | Token | 字段 |
|---|---|---|---|
| Health | `/health`、`/health/detailed` | API | status/runtime/control |
| Hermes readiness | `/v1/hermes/readiness` | API | readiness/issues |
| Financial readiness | `/v1/financial-system/readiness` | API | gates/next_actions |
| Parity | `/v1/capabilities/parity` | API | matrix/status |

## 5. 前端设计

组件：`ReadinessHealthPage -> HealthSummary -> GateTable -> NextActionList -> DiagnosticRawPanel`。

## 6. 开发规范

新增 readiness gate 必须提供 target_page、error_code、env vars、fix guidance，并处理 deferred 页面。

## 7. 错误说明

| 错误码 | 用户提示 | 技术原因 | 处理 |
|---|---|---|---|
| OPS-301 | 准备度不足 | gate failed | 显示 evidence |
| OPS-302 | 修复目标不在 V1 | target deferred | 显示 deferred |
| OPS-501 | 健康检查失败 | route error | 可重试 |

## 8. 功能测试

| 用例编号 | 场景 | 预期 |
|---|---|---|
| TC-OPS-001 | health ready | 状态可见 |
| TC-OPS-002 | gate failed | evidence 和 next action |
| TC-OPS-003 | 工厂 next action | 不打开四工厂 |
| TC-OPS-004 | live skipped | 标记 skipped_missing_credentials |

## 9. 不做什么

- 不自动执行修复。
- 不把 deferred gate 变成产品入口。
- 不隐藏缺配置原因。

## 10. 代码实证与成熟实现补强

### 10.1 当前代码审计

| 对象 | 代码证据 | 当前行为 | 文档结论 |
|---|---|---|---|
| Readiness 页面 | `ReadinessHealthPage.tsx` | 加载 health、detailed health、desktop capabilities、Hermes status/readiness、financial readiness | 准备度不是单一绿灯，要分维度 |
| Agent routes | `health.py`、`hermes_status.py` | `/health`、`/health/detailed`、`/v1/desktop/capabilities`、`/v1/hermes/readiness`、`/v1/financial-system/readiness` | 每类 readiness 要写 endpoint |
| next action | `ReadinessHealthPage.tsx` 的 action 映射 | 可跳转 MCP/Data/Settings 等 V1 页面 | readiness 不跳四工厂 |
| 测试 | `ReadinessHealthPage.test.tsx` | 覆盖 token、refresh、维度、live smoke coverage、MCP remediation | 运维验收要含修复路径 |

### 10.2 诊断维度

| 维度 | 必须显示 | 失败时下一步 |
|---|---|---|
| Agent health | online/offline/version/toolset | Settings/endpoint |
| Hermes readiness | model/toolset/full mode/parity | Models/Tools |
| MCP readiness | servers/tools/resources/prompts/OAuth | MCP/Connectors |
| Data readiness | database/freshness/missing/stale | Data & Sync |
| Finance readiness | manager/quant/radar/broker read-only | Finance Lab 非工厂模块 |

### 10.3 成熟技术采用

RFC 9457 的 Problem Details 思想用于结构化错误；OpenAPI 用于 endpoint 透明；Playwright live smoke 用于真实后端冒烟。AIASK 不采用“一个总状态灯代表系统可发布”的方式，必须分维度给出原因和修复入口。

## 11. 前端页面设计与布局细化

### 11.1 页面布局

| 区域 | 布局与内容 | 代码依据 | 交互要求 |
|---|---|---|---|
| 健康指标 | AI provider、Gateway、Plugins、MCP、Financial、Memory/Search、Mode/Token | `ReadinessHealthPage.tsx`、`MetricCard` | 每个维度显示 ready/partial/gated/error |
| 运行前检查 | step、status、required、evidence、next action | `/v1/hermes/readiness`、`/v1/financial-system/readiness` | next action 跳 V1 页面或标记 deferred |
| 修复建议 | priority、label、description、target view | `ReadinessHealthPage.tsx` | 不能跳四工厂；旧建议回 `finance-lab` |
| Live smoke | 前置凭据、skipped_missing_credentials、结果摘要 | `capabilities.spec.ts` live smoke | mock/live 明确分离 |

### 11.2 组件树

```text
ReadinessHealthPage
├── ReadinessMetricStrip
├── PreflightChecklist
├── NextActionPanel
├── LiveSmokePanel
└── ReadinessRawEvidencePanel
```

### 11.3 状态和响应式

- `degraded`：单个维度失败不让全页空白；保留可用维度和修复建议。
- `gated`：缺 token/full mode/OAuth 时展示配置路径，但不展示 secret。
- 窄屏 next actions 置顶，检查清单分组折叠。

## 原有内容保留

## 功能目标

Readiness/Health 是 AIASK 发布和日常运维的状态中心。用户和开发团队需要知道 Agent 是否在线、Hermes 能力是否对齐、模型/MCP/数据/金融/Gateway 是否可用，以及哪些功能只是 mock、degraded 或 blocked。

## 代码证据

| 能力 | 代码位置 |
|---|---|
| Health routes | `packages/agent/src/aiask_agent/routes/health.py` |
| Hermes status | `packages/agent/src/aiask_agent/routes/hermes_status.py` |
| Capabilities payload | `packages/agent/src/aiask_agent/desktop_capabilities_payloads.py` |
| Financial readiness | `packages/agent/src/aiask_agent/financial_readiness.py` |
| 前端页面 | `desktop/src/features/agent-pages/ReadinessHealthPage.tsx`、`DiagnosticsPanel.tsx`、`CapabilitiesWorkspace.tsx` |
| API client | `health`、`capabilities`、`hermesStatus`、`capabilityParity`、`hermesReadiness` |

## 用户流程

1. 打开 Readiness/Health，自动加载系统健康。
2. 页面展示 Agent、Hermes、模型、MCP、数据、金融、Gateway、Jobs、RL 等状态。
3. 每个模块显示 status、reason、last_checked、修复入口。
4. 用户可以刷新诊断。
5. mock 与 live 状态分开，不混淆。

## 前端展现

| 状态 | 说明 |
|---|---|
| green | live 可用 |
| yellow | degraded、mock、缺可选依赖、部分数据源不可用 |
| red | offline、auth failed、route missing、严重错误 |
| gray | disabled、not configured、V1 deferred |

## API 合约

| 操作 | Endpoint |
|---|---|
| 基础健康 | `GET /health` |
| 详细健康 | `GET /health/detailed` |
| 工具目录 | `GET /v1/tools` |
| 桌面能力 | `GET /v1/desktop/capabilities` |
| 能力对齐 | `GET /v1/capabilities/parity` |
| Hermes 状态 | `GET /v1/hermes/status` |
| Hermes readiness | `GET /v1/hermes/readiness` |
| 金融 readiness | `GET /v1/financial-system/readiness` |

## 验收规则

1. 页面不能只显示“正常”，必须按模块显示。
2. mock/live/degraded/blocked 必须区分。
3. 四工厂显示为 deferred，不给产品入口。
4. 每个红灯必须有错误摘要或修复路径。
5. 发布前 readiness 页面不能有乱码、横向溢出或 raw JSON 墙。

## 详细落地规范

### 问题场景与技术方案

| 问题 | 表现 | 技术方案 | 代码落点 | 验收 |
|---|---|---|---|---|
| 用户只看到“正常”但功能不可用 | 模块级状态卡 | health detailed + capabilities | `routes/health.py` | 模型/MCP/数据分开 |
| mock 被误认为 live | mode badge 明确显示 | settings/mode/status | `useAppConnectionSettings.ts` | mock/live 可区分 |
| 金融系统缺数据 | 金融 readiness 红/黄灯 | financial readiness | `financial_readiness.py` | 修复入口到 Data |
| Hermes parity 有缺口 | parity 表显示缺项 | capability parity | `capabilities.py` | 缺口不隐藏 |
| 四工厂存在后端能力 | readiness 标 deferred | V1 scope metadata | `routes.ts`、`v1Scope.ts` | 不提供入口 |

### 页面结构

| 区域 | 内容 |
|---|---|
| System | Agent online、version、mode |
| AI | provider、model、smoke |
| Tools | toolset、full mode、parity |
| Data | database、sources、freshness |
| Finance | financial readiness、broker read-only |
| Integrations | MCP、Gateway、Connectors、Webhooks |
| Deferred | 四工厂 deferred 状态 |

### 代码生成/修改步骤

1. 新 readiness 字段必须在 Agent payload 和 Desktop 类型同时更新。
2. Readiness 页面不直接调用各模块细节接口做推断，优先读聚合状态。
3. 每个红灯给修复入口，不给空文案。
4. 测试覆盖 mock/live、degraded、deferred、secret redaction。

### 不做什么

- 不用 raw JSON 代替状态卡。
- 不把 optional dependency 缺失写成系统失败。
- 不把 deferred 当错误，也不把 deferred 当入口。

### 状态机补充

`health_loading -> health_ready -> module_refreshing -> module_ready/module_degraded/module_failed`

发布验收状态为 `unchecked -> checking -> passed/failed/skipped`。`skipped` 必须写明原因，例如缺 live backend。
