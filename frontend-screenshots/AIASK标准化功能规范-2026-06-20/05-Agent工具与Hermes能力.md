# Agent 工具与 Hermes 能力

## 文档信息

| 项目 | 内容 |
|---|---|
| 项目名称 | AIASK V1 前端产品化 |
| 功能名称 | Agent 工具与 Hermes 能力 |
| 功能编号前缀 | `TOOL` |
| 文档版本 | 1.0.0 |
| 更新日期 | 2026-06-21 |
| V1 状态 | P0 必做 |
| 代码基准 | `packages/agent/src/aiask_agent/tools/policy.py`、`tools/catalog.py`、`tools/schemas.py`、`tool_registry.py`、`capabilities.py`、`desktop/src/components/ToolCatalog.tsx` |

### 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|---|---|---|---|
| 1.0.0 | 2026-06-21 | 按 L4 模板补齐工具目录、toolset、side effect、门禁和测试 | Codex |

### 术语定义

| 术语 | 定义 | 代码证据 |
|---|---|---|
| `finance_safe` | 默认工具集，以只读和受控金融流程为主 | `tools/policy.py` |
| `general_full` | 高权限工具集，需要显式启用和 control token | `tools/policy.py` |
| Side Effect | 工具是否读、写、外部投递或金融风险 | `ToolEnvelope.meta.side_effect` |

## 1. 功能设计

### 1.1 需求背景与价值

| 项 | 内容 |
|---|---|
| 问题陈述 | Agent 能力很多，如果不区分只读、full mode、intent、approval，用户会误认为所有工具都可直接执行。 |
| 解决方案 | 工具目录展示 `agent_*` 名称、toolset、schema、side_effect、interaction_mode、blocked_reason。 |
| 业务价值 | 让工具能力可解释、可治理、可审计。 |

### 1.2 用户故事

| 编号 | 优先级 | 用户故事 | 成功标准 |
|---|---|---|---|
| TOOL-US-001 | P0 | 作为用户，我希望知道工具是只读还是高权限，以便避免误操作。 | 工具卡显示 side effect 和门禁。 |
| TOOL-US-002 | P0 | 作为开发者，我希望所有模型可见工具以 `agent_*` 开头，以便防止 raw manager 暴露。 | 工具目录扫描通过。 |
| TOOL-US-003 | P0 | 作为 QA，我希望 blocked 工具显示原因，以便验证安全策略。 | `blocked_reason` 可见。 |

### 1.3 功能分解与优先级

| 功能编号 | 功能点 | 优先级 | 当前代码依据 | 待开发事项 | 验收标准 |
|---|---|---|---|---|---|
| TOOL-F001 | 工具目录 | P0 | `/v1/tools`、`catalog.py` | 前端字段完整展示 | name/schema/side_effect 可见 |
| TOOL-F002 | Toolset 状态 | P0 | `/v1/hermes/toolsets`、`policy.py` | finance_safe/general_full 说明 | full mode 未启用时 gated |
| TOOL-F003 | 工具调用 envelope | P0 | `tool_registry.py`、`routes/tools.py` | 错误展示 | error_code/meta 可见 |
| TOOL-F004 | 能力 parity | P1 | `capabilities.py`、`/v1/capabilities/parity` | 缺口解释 | missing/implemented 可见 |

### 1.4 业务规则与边界

| 规则 | 说明 | 验收 |
|---|---|---|
| 模型可见工具必须 `agent_*` | 禁止 raw manager 名称 | `rg`/测试扫描 |
| Full mode 受控 | 文件/终端/浏览器/外部平台需要 full mode/control token | UI gated |
| 状态动作走 intent | 金融和外部副作用不得直接执行 | ActionIntent 可见 |

## 2. 流程设计

| 步骤 | 行为 | 前端 | Agent/API | 异常 |
|---|---|---|---|---|
| 1 | 加载工具目录 | 展示分组和门禁 | `/v1/tools` | 缺字段显示 degraded |
| 2 | 查看工具详情 | 展开 schema/example | catalog/schemas | schema 缺失 |
| 3 | 调用工具 | 只读工具可执行 | `/v1/tools/{tool_name}` | stateful 工具转 intent/gated |
| 4 | 查看 parity | 展示覆盖缺口 | `/v1/capabilities/parity` | missing 显示原因 |

状态机：`loading -> ready -> invoking -> success|failed|gated|blocked`。

## 3. 架构设计

Agent policy 是工具命名和 toolset 权威；Desktop 只展示目录和调用受控 route，不自行决定后端能否执行。

## 4. 功能说明：接口与数据

| 操作 | Endpoint | Method | Token | 关键字段 |
|---|---|---|---|---|
| 工具目录 | `/v1/tools` | GET | API | `name`、`input_schema`、`side_effect` |
| 调用工具 | `/v1/tools/{tool_name}` | POST | API/control | `success`、`data`、`error_code` |
| Hermes 工具 | `/v1/hermes/tools` | GET | API | `toolset`、`visibility` |
| Toolsets | `/v1/hermes/toolsets` | GET | API | `finance_safe`、`general_full` |

## 5. 前端设计

组件：`ToolCatalog -> ToolGroup -> ToolCard -> SchemaPanel -> SideEffectBadge -> InvocationResult`。

## 6. 开发规范

新增模型可见工具必须改 catalog、schema、registry、policy、tests 和 Desktop capability inventory。

## 7. 错误说明

| 错误码 | 用户提示 | 技术原因 | 处理 |
|---|---|---|---|
| TOOL-201 | 工具不可用 | toolset disabled | 显示启用条件 |
| TOOL-401 | 工具被策略阻断 | blocked by policy | 显示 blocked reason |
| TOOL-501 | 工具执行失败 | adapter/MCP error | 展示 error_code |

## 8. 功能测试

| 用例编号 | 场景 | 预期 |
|---|---|---|
| TC-TOOL-001 | 工具名扫描 | 全部模型可见工具为 `agent_*` |
| TC-TOOL-002 | full mode disabled | 高权限工具 gated |
| TC-TOOL-003 | 工具失败 | error_code 和 meta 可见 |
| TC-TOOL-004 | raw manager token | 不出现在模型可见目录 |

## 9. 不做什么

- 不展示 raw manager 作为模型工具。
- 不把 full mode 当默认可用。
- 不隐藏 side effect。

## 10. 代码实证与成熟实现补强

### 10.1 当前代码审计

| 对象 | 代码证据 | 当前行为 | 文档结论 |
|---|---|---|---|
| 工具策略 | `packages/agent/src/aiask_agent/tools/policy.py` | 工具名必须 `agent_*`；`finance_safe` 默认，`general_full` 需显式启用 | 文档不得出现 raw manager 作为模型可见工具 |
| 工具目录 | `catalog.py`、`schemas.py`、`tool_registry.py` | 描述工具、input schema、side_effect、interaction_mode | 工具页面要展示 schema、side effect、blocked reason |
| 前端过滤 | `desktop/src/v1Scope.ts` | 过滤 deferred factory 工具和 capability marker | 四工厂工具不能在 V1 常驻目录出现 |
| 前端页面 | `ToolsIntentsApprovalsPage.tsx`、`ToolCatalog.tsx`、`InspectorPanels.tsx` | 支持工具筛选、read-only probe、intent/approval 列表、blocked 详情 | QA 要测 read_only、intent、approval、blocked 四类 |

### 10.2 工具展示最低字段

| 字段 | 来源 | UI 要求 | 验收 |
|---|---|---|---|
| `name` | `ToolCatalogItem.name` | 必须以 `agent_` 开头 | 扫描无 raw manager |
| `input_schema` / `output_schema` | `tools/schemas.py` | 可折叠展示 | 新工具不允许无 schema |
| `side_effect` | tool metadata | read_only/stateful/external/trade-risk 可见 | 有副作用则不可一键执行 |
| `blocked_reason` | policy/route response | localize 后展示 | blocked 不提供绕过 |
| `toolset` | health/Hermes | finance_safe/general_full 可见 | full mode 缺失显示 gated |

### 10.3 成熟技术采用

OpenAI Tools 指导“工具可见、参数可解释、结果可追踪”；JSON Schema 指导输入输出字段定义；OWASP 指导权限和对象访问控制。AIASK 采用 `agent_*` facade + schema + ToolEnvelope + ActionIntent，不采用把 MCP/manager 原始方法直接暴露给模型。

## 11. 前端页面设计与布局细化

### 11.1 页面布局

| 区域 | 布局与内容 | 代码依据 | 交互要求 |
|---|---|---|---|
| 工具目录 | 搜索、category、capability、side_effect、V1 visible 状态 | `ToolsIntentsApprovalsPage.tsx`、`v1Scope.ts` | 默认过滤四工厂 deferred 工具，只展示 `agent_*` |
| 意图队列 | intent id、action、status、created_at、requires approval | `routes/intents.py`、`AiaskApi.createActionIntent()` | 选中后显示 payload 和审批链路 |
| 审批队列 | approval id、risk、requested_by、confirm/deny | `routes/approvals.py` | confirm/deny 需要 control token 和确认文案 |
| 详情区 | tool JSON schema、参数样例、blocked reason、audit | `JsonPanel`、`StatusBadge` | raw manager 名称不作为模型可见工具展示 |

### 11.2 组件树

```text
ToolsIntentsApprovalsPage
├── ToolCatalogFilterBar
├── ToolCatalogTable
├── IntentQueueTable
├── ApprovalQueueTable
└── SchemaIntentApprovalDetail
```

### 11.3 状态和响应式

- `gated`：审批确认、拒绝、受控执行按钮 disabled；只读工具详情仍可查看。
- `mock`：mock e2e 页面必须标记来源，不能当 live readiness。
- 窄屏三列改为 tabs，详情区在当前 tab 下方展开；schema 长字段换行并支持复制。

## 原有内容保留

## 功能目标

AIASK 的 AI 回复要参考 Hermes Agent 的能力表达：能读写文件、编辑代码、运行终端/代码、调用浏览器、搜索网页、调用金融工具、保存/搜索记忆、使用 Skills/MCP/插件。但这些能力必须通过 Agent `agent_*` 工具和安全门禁，不允许前端或模型直接调用 raw manager。

## 代码证据

| 能力 | 代码位置 |
|---|---|
| Hermes 能力映射 | `packages/agent/src/aiask_agent/capabilities.py` |
| 工具目录 | `packages/agent/src/aiask_agent/tools/catalog.py` |
| 工具注册 | `packages/agent/src/aiask_agent/tool_registry.py` |
| 工具调用路由 | `packages/agent/src/aiask_agent/routes/tools.py` |
| full controls | `packages/agent/src/aiask_agent/routes/full_controls.py` |
| 前端工具页 | `desktop/src/features/agent-pages/ToolsIntentsApprovalsPage.tsx`、`desktop/src/components/ToolCatalog.tsx` |

## 工具能力分层

| 层级 | 示例 | 前端规则 |
|---|---|---|
| finance_safe | `agent_analyze_stock`、`agent_quant_data_gate`、`agent_market_temperature_snapshot` | 默认可见，仍需显示只读/降级 |
| ActionIntent | `agent_action_intent_create` | 生成意图，不直接写入 |
| general_full | `agent_file_write`、`agent_terminal`、`agent_browser_*`、`agent_plugin_manage` | 需要 full mode/control token/确认 |
| 外部平台 | `agent_feishu_*`、`agent_discord_*`、`agent_gateway_*`、`agent_ha_*` | 需要平台配置和副作用提示 |

## 前端展现

工具目录必须显示：工具名、分类、是否只读、是否需要 full mode、是否需要 token、输入 schema、最近调用、失败率。AI 回复中的工具调用卡片必须显示参数摘要和结果摘要，raw JSON 放折叠区。

## 安全规则

1. 模型可见工具必须以 `agent_` 开头。
2. `strategy_manager`、`live_trading_manager`、`execution_manager` 等 raw manager 名称不得出现在模型工具列表。
3. 文件写入、patch、终端、浏览器控制、外部消息、插件变更必须受门禁保护。
4. 工具失败要返回结构化错误，不展示堆栈和 secret。

## 验收规则

1. 工具目录过滤四工厂 deferred 工具，不作为 V1 常驻入口。
2. Tool call card 能看到 tool name、status、duration、side effect。
3. full mode 关闭时，高权限工具按钮不可点击且说明原因。
4. 对话中工具调用与 runs/events/tool-invocations 可互相追踪。

## 详细落地规范

### 问题场景与技术方案

| 问题 | 表现 | 技术方案 | 代码落点 | 验收 |
|---|---|---|---|---|
| 工具名太多用户看不懂 | 工具目录按场景分类 | catalog 增加 category/description | `tools/catalog.py` | 搜索/筛选可用 |
| 工具有副作用 | 工具卡显示 side_effect 和门禁 | schema/catalog 暴露 side_effect | `tools/schemas.py`、`tool_registry.py` | 写入工具不能直接执行 |
| Hermes 能力与 AIASK 对不上 | parity 页面显示 reference 与 `agent_*` | capabilities mapping | `capabilities.py` | 缺口有状态和说明 |
| raw manager 泄漏 | 工具目录不出现 manager 原始名 | policy forbid list | `tools/policy.py` | 测试断言不存在 |
| full mode 关闭 | 工具显示 gated | toolset policy + desktop mode | `useAppConnectionSettings.ts` | 按钮禁用 |

### 工具卡字段

| 字段 | 说明 |
|---|---|
| `tool_name` | 必须是 `agent_*` |
| `category` | finance_safe/general_full/platform/native |
| `input_summary` | 参数摘要，不能泄露 secret |
| `status` | pending/running/success/error/gated |
| `side_effect` | read_only/stateful/external/local_high_risk |
| `duration_ms` | 调用耗时 |
| `result_summary` | 用户可读结果 |
| `raw_payload` | 折叠展示 |

### 代码生成/修改步骤

1. 新增工具必须先改 `tools/catalog.py` 和 `tools/schemas.py`。
2. `tool_registry.py` 注册时必须返回结构化 envelope。
3. 如果工具可能写入或外部投递，不能直接作为普通按钮，必须走 ActionIntent 或 full/control gate。
4. Desktop ToolCatalog 只读取 `/v1/tools`，不硬编码工具列表。
5. 测试覆盖 tool name、schema、side_effect、raw manager 负向。

### 不做什么

- 不暴露 `strategy_manager`、`live_trading_manager` 等 raw 名称。
- 不用自然语言描述替代工具 schema。
- 不把 high-risk 工具放在默认推荐动作。

### 状态机补充

`catalog_loading -> catalog_ready -> tool_selected -> tool_preflight -> tool_running -> tool_success/tool_error`

门禁状态包括 `gated_full_mode`、`gated_control_token`、`blocked_raw_manager`、`deferred_v1`。
