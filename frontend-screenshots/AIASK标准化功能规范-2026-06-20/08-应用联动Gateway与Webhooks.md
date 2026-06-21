# 应用联动 Gateway 与 Webhooks

## 文档信息

| 项目 | 内容 |
|---|---|
| 项目名称 | AIASK V1 前端产品化 |
| 功能名称 | 应用联动 Gateway 与 Webhooks |
| 功能编号前缀 | `GATEWAY` |
| 文档版本 | 1.0.0 |
| 更新日期 | 2026-06-21 |
| V1 状态 | P1 必做，外部投递必须受控 |
| 代码基准 | `desktop/src/features/agent-pages/GatewayPage.tsx`、`desktop/src/services/api/integrations.ts`、`desktop/src/services/aiaskApi.ts`、`packages/agent/src/aiask_agent/routes/gateway.py`、`routes/webhooks.py` |

### 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|---|---|---|---|
| 1.0.0 | 2026-06-21 | 按 L4 模板补齐平台、消息、目录、Webhook、发送意图和测试 | Codex |

### 术语定义

| 术语 | 定义 | 代码证据 |
|---|---|---|
| Gateway | 外部平台状态、消息、目录和投递控制面 | `routes/gateway.py` |
| Webhook | 外部事件订阅和触发入口 | `routes/webhooks.py` |
| Send Intent | 外部发送预览创建的审批意图 | `gatewaySendIntent()` |

## 1. 功能设计

### 1.1 需求背景与价值

| 项 | 内容 |
|---|---|
| 问题陈述 | 外部平台投递如果一键发送，容易误发消息或触发外部副作用。 |
| 解决方案 | Gateway 展示平台、daemon、消息、目录、健康和重试；发送/触发必须 preview -> ActionIntent -> approval。 |
| 业务价值 | 外部投递可预览、可审批、可追踪、可回滚排查。 |

### 1.2 用户故事

| 编号 | 优先级 | 用户故事 | 成功标准 |
|---|---|---|---|
| GATEWAY-US-001 | P1 | 作为运营用户，我希望看到外部平台是否在线，以便判断能否投递。 | platforms/daemon/status 可见。 |
| GATEWAY-US-002 | P1 | 作为用户，我希望发送前预览并创建审批，以便避免误发。 | send 只创建 intent。 |
| GATEWAY-US-003 | P1 | 作为运维，我希望失败消息可重试并有错误码。 | messages/retry 状态可见。 |

### 1.3 功能分解与优先级

| 功能编号 | 功能点 | 优先级 | 当前代码依据 | 待开发事项 | 验收标准 |
|---|---|---|---|---|---|
| GATEWAY-F001 | 状态/daemon/platforms | P1 | `/v1/gateway/status`、`daemon/status`、`platforms` | 空态细化 | 平台在线/缺配置可见 |
| GATEWAY-F002 | messages/directory/retry | P1 | messages/directory/retry routes | 失败分类 | retry 不绕过门禁 |
| GATEWAY-F003 | send intent | P1 | `gatewaySendIntent()` -> `/intents` | 预览 UI | 不直接外部投递 |
| GATEWAY-F004 | Webhooks | P1 | `/v1/webhooks`、trigger | trigger intent | 创建/删除/触发受控 |

### 1.4 业务规则与边界

| 规则 | 说明 | 验收 |
|---|---|---|
| 外部发送受控 | send/direct-deliver 不作为普通按钮直接执行 | intent id 可见 |
| 平台凭据 redacted | 只显示 missing/configured | 不展示 token |
| Webhook trigger 受控 | 触发外部事件必须有确认或 intent | 无 token gated |

## 2. 流程设计

| 步骤 | 用户操作 | 前端行为 | Agent/API | 异常 |
|---|---|---|---|---|
| 1 | 打开 Gateway | 加载 status/platform/messages/directory | `/v1/gateway/*` | 平台缺配置 degraded |
| 2 | 预览发送 | 填写目标和内容 | 本地预览 | 目标缺失 GATEWAY-101 |
| 3 | 创建审批 | 调用 `gatewaySendIntent()` | `/intents` | 无 control token gated |
| 4 | 重试消息 | 点击 retry | `/v1/gateway/messages/{id}/retry` | 失败保留错误 |
| 5 | Webhook trigger | 点击触发 | `/intents` 或 trigger route | 不直接触发 |

状态机：`loading -> ready|degraded|error -> previewing -> intent_created|failed|gated -> approved|denied`。

## 3. 架构设计

Desktop Gateway 页面只调用 Agent；Agent Gateway daemon/platform adapters 负责外部平台；投递类动作进入 ActionIntent/approval。

## 4. 功能说明：接口与数据

| 操作 | Endpoint | Method | Token | 前端方法 |
|---|---|---|---|---|
| 状态 | `/v1/gateway/status`、`/v1/gateway/daemon/status` | GET | API/control | `gatewayStatus()`、`gatewayDaemonStatus()` |
| 平台/消息/目录 | `/v1/gateway/platforms|messages|directory` | GET | control | `gatewayPlatforms()` 等 |
| 目录刷新/重试/平台控制 | gateway POST routes | POST | control | refresh/retry/start/stop |
| 发送意图 | `/intents` | POST | control | `gatewaySendIntent()` |
| Webhooks | `/v1/webhooks` | GET/POST/DELETE | control | `webhooks*()` |

## 5. 前端设计

组件：`GatewayPage -> PlatformStatusGrid -> MessageTable -> DirectoryPanel -> SendPreviewPanel -> WebhookPanel -> ApprovalLink`。

## 6. 开发规范

新增外部平台必须补官方文档来源、授权状态、缺 env 提示、失败重试和 ActionIntent 边界。

## 7. 错误说明

| 错误码 | 用户提示 | 技术原因 | 处理 |
|---|---|---|---|
| GATEWAY-101 | 投递目标不完整 | target missing | 表单提示 |
| GATEWAY-201 | 平台未授权 | env/OAuth missing | 引导配置 |
| GATEWAY-401 | 外部投递需要审批 | intent required | 创建 intent |
| GATEWAY-302 | 平台不可用 | offline/rate limit | 显示 retry |

## 8. 功能测试

| 用例编号 | 场景 | 预期 |
|---|---|---|
| TC-GATEWAY-001 | 平台状态 | configured/missing/connected 可见 |
| TC-GATEWAY-002 | 发送预览 | 只创建 intent |
| TC-GATEWAY-003 | 无 control token | 投递/trigger disabled |
| TC-GATEWAY-004 | message retry | retry 结果和错误可见 |

## 9. 不做什么

- 不提供无审批的一键外部发送。
- 不展示平台 secret。
- 不把平台离线写成 ready。

## 10. 代码实证与成熟实现补强

### 10.1 当前代码审计

| 对象 | 代码证据 | 当前行为 | 文档结论 |
|---|---|---|---|
| Gateway 页面 | `GatewayPage.tsx` | 加载 status、daemon、platforms、messages、directory，支持 retry、directory refresh、platform health、send intent | Gateway 是外部投递控制台，不是聊天按钮 |
| Webhook 面板 | `WebhooksPanel.tsx` | list/create/delete/trigger intent，缺 control token 禁用写入 | Webhook trigger 也必须审批 |
| Agent routes | `routes/gateway.py`、`routes/webhooks.py` | `/v1/gateway/*`、`/v1/webhooks/*` | 每个外部动作要写 endpoint 和 token |
| UI 门禁 | `confirmAction()`、`controlToken`、`StatusBadge gated` | 发送、目录刷新、retry、平台 start/stop/trigger 都受控 | 不允许无确认的一键外部投递 |

### 10.2 外部平台功能细节

| 功能 | 产品说明 | 技术实现 | 验收 |
|---|---|---|---|
| Platform health | 查看飞书、Discord、Home Assistant 等平台状态 | `/v1/gateway/platforms/{platform}/health` | 失败不影响页面其他平台 |
| Message retry | 失败消息可单条/批量重试 | `GatewayRetryPanel` + `/messages/{id}/retry` | retry 显示 retrying/failed/error |
| Directory | 平台目录可刷新和筛选 | `/directory`、`/directory/refresh` | refresh 需要确认和 control token |
| Send intent | 发送消息只创建审批意图 | `gatewaySendIntent()` | 未 approval 不实际投递 |
| Webhook trigger | Webhook 触发进入 ActionIntent | `webhookTriggerIntent()` | 无 token disabled |

### 10.3 联网成熟方案采用

飞书、Discord、Home Assistant 官方文档都强调应用凭据、权限范围、回调和平台错误处理。AIASK 采用 Gateway daemon + platform adapters + ActionIntent/approval，不采用“前端按钮直接发消息”。外部投递的验收必须包含：缺凭据、缺权限、限流、失败重试、目录缺失、secret redaction。

## 11. 前端页面设计与布局细化

### 11.1 页面布局

| 区域 | 布局与内容 | 代码依据 | 交互要求 |
|---|---|---|---|
| Gateway 指标 | daemon、platforms、messages、directory、failed/retry | `GatewayPage.tsx`、`gatewayStatus()` | 平台离线不影响消息历史查看 |
| 平台列表 | Feishu/Discord/Home Assistant 等 platform 状态、health、start/stop | `routes/gateway.py` | start/stop 需要 control token |
| 消息与目录 | message table、retry、directory contacts/channels | `GatewayRetryPanel.tsx` | retry 显示原 message id 和失败原因 |
| Webhooks | subscription list、create/delete、trigger intent | `WebhooksPanel.tsx`、`routes/webhooks.py` | trigger/send 只创建 ActionIntent，不直接投递 |

### 11.2 组件树

```text
GatewayPage
├── GatewayMetricStrip
├── PlatformHealthTable
├── GatewayMessagesTable
├── GatewayDirectoryPanel
├── GatewayRetryPanel
└── WebhooksPanel
```

### 11.3 状态和响应式

- `gated`：send、trigger、start、stop、delete 类动作必须禁用或进入 intent。
- `error`：平台限流、授权失败、消息投递失败分别显示，不只写“失败”。
- 窄屏拆成 Platform、Messages、Directory、Webhooks 四个 tabs；send/trigger 表单置于对应 tab 顶部。

## 原有内容保留

## 功能目标

AIASK 需要连接外部应用：飞书、Discord、Home Assistant、Webhook 以及后续微信/企业微信等平台。第一版应把绑定、健康检查、消息历史、目录、投递、重试和 Webhook 管理做成可审计流程。

## 外部参考

飞书、Discord、Home Assistant 官方文档都强调应用凭据、权限范围和回调/REST API 的边界。AIASK 前端必须显示配置状态与权限，不展示 secret。

## 代码证据

| 能力 | 代码位置 |
|---|---|
| Gateway routes | `packages/agent/src/aiask_agent/routes/gateway.py` |
| Gateway runtime | `packages/agent/src/aiask_agent/gateway/*`、`gateway_daemon.py` |
| Platform APIs | `packages/agent/src/aiask_agent/platform_apis.py`、`homeassistant.py` |
| Webhooks | `packages/agent/src/aiask_agent/routes/webhooks.py`、`webhooks.py` |
| Capabilities | `packages/agent/src/aiask_agent/capabilities.py` 的 `agent_feishu_*`、`agent_discord_*`、`agent_ha_*`、`agent_gateway_*` |
| 前端页面 | `desktop/src/features/agent-pages/GatewayPage.tsx`、Settings Webhooks/Integrations panels |

## 用户流程

1. 打开集成/Gateway，查看平台列表和状态灯。
2. 绑定平台时只填写 env var 名称或授权状态，不显示 secret 原值。
3. 点击平台健康检查，显示连接、权限、最近错误。
4. 查看消息历史和目录，如频道、用户、群、设备实体。
5. 发送消息或 direct deliver 必须先创建意图或显示确认。
6. Webhook 可创建、删除、触发；触发属于外部副作用，需要门禁。
7. 失败消息可重试，页面显示 retry 次数和错误。

## 前端展现

| 区域 | 展示内容 |
|---|---|
| 平台卡片 | Feishu/Lark、Discord、Home Assistant、Webhook、后续微信 |
| 健康状态 | configured、authorized、reachable、last_error |
| 消息历史 | platform、target、status、retry_count、created_at |
| Directory | channel/user/group/entity 列表 |
| Webhooks | url redacted、event、enabled、last_trigger |

## API 合约

| 操作 | Endpoint |
|---|---|
| Gateway 状态 | `GET /v1/gateway/status` |
| Daemon 状态 | `GET /v1/gateway/daemon/status` |
| 平台列表 | `GET /v1/gateway/platforms` |
| start/stop/health | `/v1/gateway/platforms/{platform}/start|stop|health` |
| 消息 | `GET /v1/gateway/messages` |
| 目录 | `GET /v1/gateway/directory`、`POST /directory/refresh` |
| 发送 | `POST /v1/gateway/send`、`POST /direct-deliver` |
| 重试 | `POST /v1/gateway/messages/{id}/retry` |
| Webhooks | `GET/POST/DELETE /v1/webhooks`、`POST /trigger` |

## 验收规则

1. 外部投递不允许无确认静默执行。
2. 平台缺凭据显示黄色/红色，不报成功。
3. Webhook URL 和 token 必须 redacted。
4. 目录刷新和消息重试要显示结果和错误。
5. 对话里的“发送到飞书/Discord”等动作必须进入审批或确认流。

## 详细落地规范

### 问题场景与技术方案

| 问题 | 表现 | 技术方案 | 代码落点 | 验收 |
|---|---|---|---|---|
| 平台没绑定 | 平台卡灰/黄灯 | status/platform health | `routes/gateway.py` | 显示缺少配置 |
| 用户想发消息 | 先预览内容和目标 | Gateway send intent | `gatewaySendIntent` | 未确认不发送 |
| 发送失败 | 消息历史显示 failed 和 retry | messages/retry route | `gateway_daemon.py` | retry 结果可见 |
| Webhook 误触发 | trigger 必须门禁 | webhook trigger intent | `routes/webhooks.py` | 缺 token 禁用 |
| 飞书/Discord 权限不足 | 平台 health 显示 permission error | platform APIs 分类错误 | `platform_apis.py` | 不显示成功 |
| Home Assistant 服务调用有副作用 | 读取实体和调用服务分区 | `agent_ha_*` 工具分 read/call | `capabilities.py` | call_service 需要确认 |

### 投递流程

1. 选择平台和目标。
2. 预览消息内容。
3. 检查平台状态和权限。
4. 创建 ActionIntent 或确认。
5. 后端执行投递。
6. 消息进入 history，可 retry。

### 代码生成/修改步骤

1. 新平台先补 platform health 和 directory，不先做 send。
2. 外部发送必须通过 Gateway route 或 `agent_gateway_*`。
3. 前端 GatewayPage 拆分 PlatformList、MessageHistory、DirectoryPanel、SendPreview。
4. mock 覆盖 configured、permission denied、send failed、retry success。
5. e2e 覆盖外部投递门禁和 secret redaction。

### 不做什么

- 不在对话中直接发外部消息。
- 不展示 webhook token 或平台 secret。
- 不把平台健康检查成功等同于发送权限成功。

### 状态机补充

平台状态：`not_configured -> configured -> health_checking -> healthy/degraded/failed`

投递状态：`draft -> preview -> intent_created -> approved -> sending -> sent/failed -> retrying -> retried/failed`

Webhook 状态：`created -> enabled -> triggered -> delivered/failed -> disabled/deleted`。
