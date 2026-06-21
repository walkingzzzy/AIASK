# MCP 服务管理

## 文档信息

| 项目 | 内容 |
|---|---|
| 项目名称 | AIASK V1 前端产品化 |
| 功能名称 | MCP 服务管理 |
| 功能编号前缀 | `MCP` |
| 文档版本 | 1.0.0 |
| 更新日期 | 2026-06-21 |
| V1 状态 | P0 必做 |
| 代码基准 | `desktop/src/features/agent-pages/McpConnectorsPage.tsx`、`desktop/src/services/api/integrations.ts`、`desktop/src/services/aiaskApi.ts`、`packages/agent/src/aiask_agent/routes/mcp.py` |

### 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|---|---|---|---|
| 1.0.0 | 2026-06-21 | 按 L4 模板补齐 MCP 的分层、OAuth、资源读取、错误和测试 | Codex |

### 术语定义

| 术语 | 定义 | 代码证据 |
|---|---|---|
| MCP Server | 提供 tools/resources/prompts 的外部或本地服务 | `routes/mcp.py` |
| Resource | MCP 暴露的可读取资源 | `/v1/mcp/resources` |
| Prompt | MCP 暴露的提示词模板 | `/v1/mcp/prompts` |
| OAuth | 外部授权流程 | `/v1/mcp/oauth/start` |

## 1. 功能设计

### 1.1 需求背景与价值

| 项 | 内容 |
|---|---|
| 问题陈述 | MCP 不能只展示 server 列表，用户需要知道 tools、resources、prompts、OAuth 哪一层可用或失败。 |
| 解决方案 | MCP 页面分层展示 servers/tools/resources/prompts/OAuth，并对资源读取和授权启动使用 control token。 |
| 业务价值 | 外部上下文接入可解释、可测试、可排障。 |

### 1.2 用户故事

| 编号 | 优先级 | 用户故事 | 成功标准 |
|---|---|---|---|
| MCP-US-001 | P0 | 作为用户，我希望看到每个 MCP server 的 tools/resources/prompts，以便判断能否接入任务。 | 分层 tab/表格可见。 |
| MCP-US-002 | P0 | 作为用户，我希望资源读取失败时看到 server、uri 和错误码。 | resource row 显示错误详情。 |
| MCP-US-003 | P1 | 作为管理员，我希望 OAuth 启动受控，以便避免外部授权误触发。 | 无 control token 时禁用。 |

### 1.3 功能分解与优先级

| 功能编号 | 功能点 | 优先级 | 当前代码依据 | 待开发事项 | 验收标准 |
|---|---|---|---|---|---|
| MCP-F001 | server/tool/resource/prompt 列表 | P0 | `/v1/mcp/servers|tools|resources|prompts` | 空态和错误态细化 | 分层可见 |
| MCP-F002 | resource read | P0 | `POST /v1/mcp/resources/read` | 错误摘要 | control token 或 gated |
| MCP-F003 | prompt get | P1 | `POST /v1/mcp/prompts/get` | 参数表单 | 返回内容或错误可见 |
| MCP-F004 | OAuth start/callback | P1 | `/v1/mcp/oauth/start|callback` | 授权状态说明 | 外部授权受控 |

### 1.4 业务规则与边界

| 规则 | 说明 | 验收 |
|---|---|---|
| 不暴露 raw MCP stateful tool | MCP 工具若进入模型可见面，必须由 Agent `agent_*` 包装 | 工具目录检查 |
| 资源读取受控 | 读取可能访问外部/本地资源 | 使用 control token 或明确门禁 |
| OAuth 受控 | 启动外部授权必须可见 | 无 token 禁用 |

## 2. 流程设计

| 步骤 | 用户操作 | 前端行为 | Agent/API | 异常 |
|---|---|---|---|---|
| 1 | 打开 MCP 页面 | 加载 servers/tools/resources/prompts/oauth | `/v1/mcp/*` | partial_success 显示 degraded |
| 2 | 读取资源 | 选择 server/uri | `/v1/mcp/resources/read` | 失败显示 MCP-302 |
| 3 | 获取 prompt | 输入参数 | `/v1/mcp/prompts/get` | 参数错误显示 MCP-101 |
| 4 | 启动 OAuth | 点击授权 | `/v1/mcp/oauth/start` | 无 token 显示 MCP-201 |

状态机：`loading -> ready|partial|error -> reading_resource|getting_prompt|oauth_starting -> success|failed|gated`。

## 3. 架构设计

Desktop MCP 页面只调 Agent MCP aggregation route；Agent 负责发现、OAuth、资源读取和错误封装；动态 MCP 工具不得绕过 Agent tool policy。

## 4. 功能说明：接口与数据

| 操作 | Endpoint | Method | Token | 前端方法 | 关键字段 |
|---|---|---|---|---|---|
| MCP servers | `/v1/mcp/servers` | GET | API/control | `mcpServers()` | `name`、`configured`、`warnings` |
| MCP tools | `/v1/mcp/tools` | GET | API/control | `mcpTools()` | `name`、`server`、`description` |
| Resource read | `/v1/mcp/resources/read` | POST | control | `mcpResourceRead()` | `uri`、`content`、`error_code` |
| Prompt get | `/v1/mcp/prompts/get` | POST | control | `mcpPromptGet()` | `name`、`arguments`、`messages` |
| OAuth start | `/v1/mcp/oauth/start` | POST | control | `mcpOauthStart()` | `server`、`auth_url`、`status` |

## 5. 前端设计

组件：`McpConnectorsPage -> ServerList -> ToolTable -> ResourceTable -> PromptTable -> OAuthPanel -> RawPayloadDetails`。

## 6. 开发规范

新增 MCP 能力必须同步 `routes/mcp.py`、`AiaskApi`、mock、MCP 页面测试，并检查 tool poisoning/name confusion。

## 7. 错误说明

| 错误码 | 用户提示 | 技术原因 | 处理 |
|---|---|---|---|
| MCP-101 | 参数不完整 | missing server/uri/prompt args | 表单提示 |
| MCP-201 | 需要授权或控制令牌 | OAuth/control missing | 引导授权 |
| MCP-302 | MCP 资源读取失败 | server/resource error | 显示 server/uri/error |

## 8. 功能测试

| 用例编号 | 场景 | 预期 |
|---|---|---|
| TC-MCP-001 | 列表加载 | servers/tools/resources/prompts 分层显示 |
| TC-MCP-002 | resource read 缺 token | 按钮禁用或 gated |
| TC-MCP-003 | OAuth start | 创建受控授权流程 |
| TC-MCP-004 | partial success | 显示 degraded 和 warnings |

## 9. 不做什么

- 不把 MCP server 列表当成全部管理能力。
- 不让动态 MCP 工具直接成为模型可见工具。
- 不在无授权时假装资源可读。

## 10. 代码实证与成熟实现补强

### 10.1 当前前端和 Agent 事实

| 对象 | 代码证据 | 当前行为 | 文档结论 |
|---|---|---|---|
| MCP 页面 | `desktop/src/features/agent-pages/McpConnectorsPage.tsx` | 聚合 capability payload、MCP counts、OAuth、connectors summary/list/detail/test、只读 smoke | MCP 不是只列 server，而是 servers/tools/resources/prompts/OAuth/connector 一体化页 |
| 轻量 MCP 面板 | `desktop/src/features/mcp/McpPanel.tsx` | 支持 register-local、discover、resource read、prompt get、OAuth start | 管理动作必须区分 read-only 和 control gated |
| Agent routes | `packages/agent/src/aiask_agent/routes/mcp.py` | 暴露 `/v1/mcp/servers/tools/resources/prompts/oauth_status/register-local/discover/oauth/start/callback/resources/read/prompts/get` | 每个功能必须写 endpoint 而不是“调用 MCP” |
| 动态工具边界 | `tools/policy.py`、`v1Scope.ts` | 模型可见工具必须 `agent_*`，deferred factory 工具被过滤 | raw MCP stateful tool 不可直接进入模型工具 |

### 10.2 具体功能清单

| 小功能 | 产品说明 | 开发落点 | QA 验收 |
|---|---|---|---|
| 服务清单 | 展示 server、transport、discovery status、missing auth env | `McpConnectorsPage.tsx` + `/v1/mcp/servers` | 无 server 显示 empty，不写 ready |
| 工具/资源/Prompt | tools/resources/prompts 分区计数和表格 | `/v1/mcp/tools`、`/resources`、`/prompts` | 资源读取和 Prompt 获取有错误态 |
| OAuth | 显示 authenticated/expired/missing/error | `McpOAuthStatus.tsx`、`/v1/mcp/oauth_status` | expired/missing 提供重新授权入口且受控 |
| 连接器测试 | connector detail/test 需要 control token | `routes/connectors.py` | 无 token gated，不展示 secret |

### 10.3 成熟技术采用

MCP 官方文档强调 MCP 连接应用上下文和 tools/resources/prompts。AIASK 采用 MCP 分层管理，但不采用“发现到的动态工具自动暴露给模型”的模式；动态能力必须进入 Agent `agent_*` facade、工具策略和安全审核。

## 11. 前端页面设计与布局细化

### 11.1 页面布局

| 区域 | 布局与内容 | 代码依据 | 交互要求 |
|---|---|---|---|
| 指标条 | MCP 状态、server、tool、resource、prompt、OAuth、connector 数量 | `McpConnectorsPage.tsx`、`MetricCard` | offline/authorization required 显示黄灯或红灯 |
| MCP tabs | servers、tools、resources、prompts、OAuth 分层表格 | `routes/mcp.py`、`AiaskApi.mcp*` | 每行显示 server/name/status/auth/side_effect |
| 连接器区 | connector summary、列表、详情、测试结果 | `ConnectorsPanel.tsx`、`ConnectorWizard.tsx` | 测试需要 control token；结果写入详情区 |
| 右侧详情 | 选中 server/tool/resource/prompt/connector 的 schema、参数、raw JSON | `RawEvidencePanel`、`JsonPanel` | resource read、prompt get 错误保留 server/uri/name |

### 11.2 组件树

```text
McpConnectorsPage
├── McpMetricStrip
├── McpTabs
│   ├── ServersTable
│   ├── ToolsTable
│   ├── ResourcesTable
│   ├── PromptsTable
│   └── OAuthStatusTable
├── ConnectorsPanel
└── SelectedItemEvidencePanel
```

### 11.3 状态和响应式

- `gated`：register/discover/OAuth/read resource/test connector 无 control token 时禁用并显示 `GatedState`。
- `degraded`：单个 server 失败不清空全页，失败行保留错误徽标。
- `<768px`：tabs 改为下拉或横向滚动，详情面板下置；资源 URI 长文本必须换行或 tooltip。

## 原有内容保留

## 功能目标

MCP 服务管理用于把内置股票 MCP 和用户新增 MCP 服务接入 Agent。用户需要能看到服务器、工具、资源、Prompt、OAuth 状态，并能执行添加、发现、资源读取、Prompt 获取和测试。

## 外部参考

MCP 官方说明将上下文能力分为 tools、resources、prompts 等。AIASK 前端也应分层展示，不把“服务在线”误写成“所有工具可安全调用”。

## 代码证据

| 能力 | 代码位置 |
|---|---|
| Agent MCP client | `packages/agent/src/aiask_agent/mcp_client.py` |
| MCP HTTP routes | `packages/agent/src/aiask_agent/routes/mcp.py` |
| AKShare MCP server | `packages/akshare-mcp/src/akshare_mcp/server.py` |
| MCP tools/resources/prompts | `packages/akshare-mcp/src/akshare_mcp/tools/*`、`resources/*`、`prompts/*` |
| 前端页面 | `desktop/src/features/agent-pages/McpConnectorsPage.tsx`、`desktop/src/features/mcp/McpPanel.tsx` |
| API client | `mcpRegisterLocal`、`mcpDiscover`、`mcpResourceRead`、`mcpPromptGet`、`mcpOauthStart` |

## 用户流程

1. 打开 MCP 页面，读取 `/v1/mcp/servers`、`/v1/mcp/tools`、`/v1/mcp/resources`、`/v1/mcp/prompts`。
2. 内置股票 MCP 应显示为系统预置服务，标注 AKShare/TDX/Tushare/local 数据能力。
3. 用户添加本地 MCP，填写名称、命令、参数、工作目录、环境变量名。
4. 点击发现，调用 `/v1/mcp/discover` 拉取工具/资源/Prompt。
5. 用户读取资源或获取 Prompt 时展示参数、返回摘要、错误。
6. OAuth 服务显示授权状态和重新授权入口。

## 前端展现

MCP 页面建议使用四个 Tab：服务器、工具、资源、Prompt。每个服务有状态灯：

- 绿色：连接成功且发现完成。
- 黄色：服务存在但部分工具失败/OAuth 未授权。
- 红色：启动失败、连接失败、协议错误。
- 灰色：未启用或未发现。

动态工具必须展示来源服务和 side-effect 分类，不能直接进入模型工具列表，除非 Agent 侧通过 `agent_*` facade 审核。

## API 合约

| 操作 | Endpoint |
|---|---|
| 服务列表 | `GET /v1/mcp/servers` |
| 工具列表 | `GET /v1/mcp/tools` |
| 资源列表 | `GET /v1/mcp/resources` |
| Prompt 列表 | `GET /v1/mcp/prompts` |
| 注册本地服务 | `POST /v1/mcp/register-local` |
| 发现 | `POST /v1/mcp/discover` |
| OAuth | `POST /v1/mcp/oauth/start`、`POST /v1/mcp/oauth/callback` |
| 读取资源 | `POST /v1/mcp/resources/read` |
| 获取 Prompt | `POST /v1/mcp/prompts/get` |

## 验收规则

1. 添加/注册服务需要 control token 或明确管理门禁。
2. 工具列表必须显示服务名、工具名、参数 schema、风险分类。
3. 内置股票 MCP 与外部新增 MCP 分区展示。
4. MCP 失败不可吞掉，要显示 stderr/错误码摘要和修复建议。

## 详细落地规范

### 问题场景与技术方案

| 问题 | 前端表现 | 技术方案 | 代码落点 | 验收 |
|---|---|---|---|---|
| 用户不知道内置股票 MCP 是否可用 | 内置服务卡显示 AKShare/TDX/Tushare 状态灯 | Agent 聚合 `/v1/mcp/servers` 和 AKShare readiness | `routes/mcp.py`、`akshare_mcp/server.py` | 内置服务与外部服务分区 |
| 新增 MCP 配置错误 | 注册后红灯，显示命令/连接错误摘要 | `register-local` 保存配置，`discover` 负责验证 | `mcp_client.py` | 错误不影响其他 MCP |
| MCP 工具太多看不懂 | 工具表按 server/category/side_effect 筛选 | `/v1/mcp/tools` 返回 schema 和来源 | `mcp_payloads.py` | 每个工具可查看参数 |
| MCP resource 读取失败 | 资源行显示失败状态和错误码 | `resources/read` 返回 structured error | `routes/mcp.py` | URI、server、error 可见 |
| OAuth 未授权 | 黄色状态和授权按钮 | `oauth_status/start/callback` | `routes/mcp.py` | 未授权不允许读取受限资源 |
| 动态工具有安全风险 | 不直接进入模型工具列表 | 通过 `agent_mcp_manage` 或专用 `agent_*` facade | `tools/policy.py` | 模型工具目录无 raw MCP stateful action |

### 页面信息架构

| Tab | 字段 | 操作 |
|---|---|---|
| Servers | name、type、transport、status、last_error、builtin | register、discover、health |
| Tools | server、tool、description、schema、side_effect、enabled | view schema、copy contract |
| Resources | uri、server、mime、status、last_read | read resource |
| Prompts | name、arguments schema、server | get prompt |
| OAuth | server、authorized、scopes、expires_at | start OAuth、callback status |

### 状态机

`unregistered -> registered -> discovering -> discovered -> ready`

异常状态：

- `spawn_failed`
- `protocol_error`
- `oauth_required`
- `resource_failed`
- `tool_schema_invalid`
- `disabled`

### 代码生成/修改步骤

1. 新增 MCP 管理功能时先改 `packages/agent/src/aiask_agent/routes/mcp.py`，保持 Desktop 只走 HTTP。
2. 如果涉及动态工具进入模型可见工具，必须先改 `tools/policy.py`、`tools/catalog.py`、`tool_registry.py`。
3. 前端只在 `AiaskApi` 增加方法，不在组件里拼 URL。
4. mock 需要覆盖：内置 MCP 可用、外部 MCP 失败、OAuth required、resource read success。
5. e2e 需要覆盖：无 token 时管理按钮 gated，有 token 时 register/discover/resource/prompt/OAuth 路径可走。

### 不做什么

- 不让 Desktop 直接启动 MCP 进程。
- 不把 raw MCP 工具静默暴露给模型。
- 不把服务在线等同于工具可安全调用。
- 不展示环境变量或 token 原值。
