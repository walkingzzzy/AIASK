# Connectors 统一连接器

## 文档信息

| 项目 | 内容 |
|---|---|
| 项目名称 | AIASK V1 前端产品化 |
| 功能名称 | Connectors 统一连接器 |
| 功能编号前缀 | `MCP` |
| 文档版本 | 1.0.0 |
| 更新日期 | 2026-06-21 |
| V1 状态 | P1 必做 |
| 代码基准 | `desktop/src/features/agent-pages/McpConnectorsPage.tsx`、`desktop/src/services/api/integrations.ts`、`packages/agent/src/aiask_agent/routes/connectors.py` |

### 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|---|---|---|---|
| 1.0.0 | 2026-06-21 | 按 L4 模板补齐连接器 summary/list/detail/test、门禁和测试 | Codex |

### 术语定义

| 术语 | 定义 | 代码证据 |
|---|---|---|
| Connector | 统一连接器对象 | `/v1/connectors` |
| Connector Test | 连接器连通性/配置测试 | `/v1/connectors/{type}/{name}/test` |
| Summary | 连接器聚合摘要 | `/v1/connectors/summary` |

## 1. 功能设计

### 1.1 需求背景与价值

| 项 | 内容 |
|---|---|
| 问题陈述 | 外部连接器如果分散在不同页面，用户难以判断哪些已配置、可连接、缺权限。 |
| 解决方案 | 在 MCP/Connectors 页聚合 summary、list、detail、test，区分 read-only 与受控测试。 |
| 业务价值 | 提供统一集成健康入口。 |

### 1.2 用户故事

| 编号 | 优先级 | 用户故事 | 成功标准 |
|---|---|---|---|
| MCP-US-C001 | P1 | 作为用户，我希望查看连接器列表。 | type/name/status 可见。 |
| MCP-US-C002 | P1 | 作为管理员，我希望测试连接器。 | test 结果和错误可见。 |
| MCP-US-C003 | P1 | 作为运维，我希望知道缺哪些 env。 | missing_env 可见，不展示 secret。 |

### 1.3 功能分解与优先级

| 功能编号 | 功能点 | 优先级 | 当前代码依据 | 待开发事项 | 验收标准 |
|---|---|---|---|---|---|
| MCP-F201 | Summary/List | P1 | `/v1/connectors/summary`、`/v1/connectors` | 筛选 | 状态可见 |
| MCP-F202 | Detail | P1 | `/v1/connectors/{type}/{name}` | 抽屉 | 配置/缺失可见 |
| MCP-F203 | Test | P1 | `/test` | 结果态 | control token 或 gated |

### 1.4 业务规则与边界

测试可能访问外部平台，必须显示 token/权限/错误；secret 只显示 env 名和 configured。

## 2. 流程设计

状态机：`loading -> ready|empty|error -> detail_open -> testing -> success|failed|gated`。

## 3. 架构设计

Desktop McpConnectorsPage 聚合 connectors routes；Agent connectors service 负责平台细节和 redaction。

## 4. 功能说明：接口与数据

| 操作 | Endpoint | Method | Token |
|---|---|---|---|
| Summary | `/v1/connectors/summary` | GET | API/control |
| List | `/v1/connectors` | GET | API/control |
| Detail | `/v1/connectors/{connector_type}/{name}` | GET | control |
| Test | `/v1/connectors/{connector_type}/{name}/test` | POST | control |

## 5. 前端设计

组件：`McpConnectorsPage -> ConnectorSummary -> ConnectorTable -> ConnectorDetailDrawer -> ConnectorTestResult`。

## 6. 开发规范

新增 connector 必须补 type、category、missing_env、test result、外部文档来源和 redaction。

## 7. 错误说明

| 错误码 | 用户提示 | 技术原因 | 处理 |
|---|---|---|---|
| MCP-C-201 | 连接器未配置 | missing env | 显示 env 名 |
| MCP-C-401 | 测试需要控制令牌 | control missing | 禁用测试 |
| MCP-C-501 | 连接器测试失败 | external/platform error | 显示 error_code |

## 8. 功能测试

| 用例编号 | 场景 | 预期 |
|---|---|---|
| TC-CONN-001 | list | 连接器状态可见 |
| TC-CONN-002 | detail | missing_env 可见 |
| TC-CONN-003 | test | 成功/失败可见 |
| TC-CONN-004 | secret | 不展示值 |

## 9. 不做什么

- 不把连接器测试当作启用外部动作。
- 不展示 secret。
- 不让前端直连外部平台。

## 10. 代码实证与成熟实现补强

### 10.1 当前代码审计

| 对象 | 代码证据 | 当前行为 | 文档结论 |
|---|---|---|---|
| 独立面板 | `desktop/src/features/connectors/ConnectorsPanel.tsx` | 读取 connectors summary，显示 loading/message/status icon | Connectors 有独立 panel，不只在 MCP 页面里露出 |
| Wizard | `ConnectorWizard.tsx` | 分步骤填写连接器类型/配置，required missing 时 disabled | 新增连接器要 schema/step 驱动 |
| 集成页 | `McpConnectorsPage.tsx` | connectors summary/list/detail/test 与 MCP 能力同屏 | 统一连接器和 MCP 要区分职责 |
| Agent routes | `routes/connectors.py` | summary/list/detail/test | 测试动作需要 control token |
| 测试 | `ConnectorsPanel.test.tsx`、`McpConnectorsPage.test.tsx` | 覆盖 summary、forbidden gate、detail/test | QA 要测 failure scoped |

### 10.2 功能细节

| 功能 | 字段 | 验收 |
|---|---|---|
| Summary | total、connected、configured、healthy/degraded/failed | 无 token 时说明 gate |
| List | type、name、category、status、configured、connected、last_checked | 可筛选、状态灯准确 |
| Detail | config schema、missing_env、redacted secret、health checks | secret 值不可见 |
| Test | latency、success、error_code、next_steps | 单连接失败不影响其他项 |
| Wizard | required fields、secret fields、review step | 缺必填不能下一步 |

### 10.3 成熟技术采用

连接器采用 schema-driven form 和独立 health check 模式，参考 OpenAPI/JSON Schema 的契约清晰性。AIASK 不采用“连接器测试等于业务工具调用”的混淆方式；工具暴露仍走 MCP/Plugin/Agent tool policy。

## 11. 前端页面设计与布局细化

### 11.1 页面布局

| 区域 | 布局与内容 | 代码依据 | 交互要求 |
|---|---|---|---|
| 连接器摘要 | total、connected、configured、failed、category breakdown | `ConnectorsPanel.tsx`、`connectorsSummary()` | failed/缺凭据可筛选 |
| 连接器列表 | type、name、category、status、configured、connected、last_checked | `connectorsList()` | 点击行加载详情 |
| 详情面板 | endpoints、required env、capabilities、errors、health | `connectorDetail()` | env 只显示名称和配置状态 |
| 测试/向导 | connector test、local register、OAuth 或配置引导 | `connectorTest()`、`ConnectorWizard.tsx` | 测试需要 control token；失败给出下一步 |

### 11.2 组件树

```text
ConnectorsPanel
├── ConnectorsSummaryStrip
├── ConnectorTypeFilter
├── ConnectorsTable
├── ConnectorDetailPanel
└── ConnectorWizard
```

### 11.3 状态和响应式

- `empty`：没有 connector 时显示配置向导入口，不显示空表。
- `degraded`：部分 connector 失败不阻塞其他 connector 查看。
- 窄屏列表卡片化，详情和测试结果在卡片下方展开。

## 原有内容保留

## 功能目标

Connectors 是 MCP、Gateway、外部平台和本地服务之外的统一连接器管理层。用户要能看到 connector 类型、名称、类别、配置状态、测试结果和错误原因。

## 代码证据

| 能力 | 代码位置 |
|---|---|
| Connector routes | `packages/agent/src/aiask_agent/routes/connectors.py` |
| Connector manager | `packages/agent/src/aiask_agent/connector_manager.py` |
| Connectors | `packages/agent/src/aiask_agent/connectors.py`、`connector_health.py` |
| 前端 panel | `desktop/src/features/connectors/ConnectorsPanel.tsx`、`ConnectorWizard.tsx` |
| API client | `connectorsSummary`、`connectorsList`、`connectorDetail`、`connectorTest` |

## 用户流程

1. 打开 Connectors，加载 summary 和列表。
2. 按类型/类别筛选，如 model、data、gateway、mcp、platform。
3. 点击 connector 查看详情、配置项、redacted secrets。
4. 点击测试连接，显示成功/失败和诊断。
5. 需要新增连接器时使用 wizard，保存动作需要 control token。

## 前端展现

| 区域 | 内容 |
|---|---|
| Summary | total、healthy、degraded、failed、not configured |
| 列表 | type、name、category、status、last_checked |
| 详情 | config schema、secret redaction、health checks |
| 测试结果 | latency、error_code、message、next steps |

## API 合约

| 操作 | Endpoint |
|---|---|
| Summary | `GET /v1/connectors/summary` |
| 列表 | `GET /v1/connectors` |
| 详情 | `GET /v1/connectors/{connector_type}/{name}` |
| 测试 | `POST /v1/connectors/{connector_type}/{name}/test` |

## 验收规则

1. Connector 测试失败不影响页面其他连接器。
2. secret 只显示 redacted。
3. 状态灯与 Gateway/MCP/Models 页面保持一致。
4. 新增/修改连接器必须 control token。
5. Connector 不替代 MCP 工具审核，不直接暴露动态工具给模型。

## 详细落地规范

### 问题场景与技术方案

| 问题 | 表现 | 技术方案 | 代码落点 | 验收 |
|---|---|---|---|---|
| 连接器太多 | 按 type/category/status 筛选 | connectors summary/list | `routes/connectors.py` | 筛选可用 |
| 单个连接器失败 | 当前卡红灯，其他卡不受影响 | 独立 test endpoint | `connector_manager.py` | failure scoped |
| secret 风险 | 配置显示 redacted | payload redaction | `connectors.py` | 无 secret 原文 |
| 用户要新增连接器 | wizard 分步骤 | schema-driven form | `ConnectorWizard.tsx` | 保存需 token |
| MCP/Connector 混淆 | Connector 只管连接健康，不直接暴露工具 | MCP 工具仍走 MCP 管理 | routes/connectors + routes/mcp | 文案区分清楚 |

### 代码生成/修改步骤

1. 新 connector 类型先定义 manager/health check。
2. route 返回 summary/list/detail/test 四类能力。
3. 前端 wizard 用 schema 渲染，不散落硬编码字段。
4. mock 覆盖 healthy/degraded/failed/not_configured。
5. 测试覆盖 redaction、test failure、control token gate。

### 不做什么

- 不把 connector test 当成业务工具调用。
- 不展示 secret。
- 不让 connector 绕过 MCP/Plugin 工具审核。

### 状态机补充

`summary_loading -> list_ready -> connector_selected -> detail_loading -> testing -> healthy/degraded/failed`

新增连接器为 `wizard_started -> config_validating -> saving -> saved/save_failed -> test_required`。
