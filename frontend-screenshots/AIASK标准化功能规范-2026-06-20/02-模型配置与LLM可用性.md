# 模型配置与 LLM 可用性

## 文档信息

| 项目 | 内容 |
|---|---|
| 项目名称 | AIASK V1 前端产品化 |
| 功能名称 | 模型配置与 LLM 可用性 |
| 功能编号前缀 | `MODEL` |
| 文档版本 | 1.0.0 |
| 更新日期 | 2026-06-21 |
| V1 状态 | P0 必做 |
| 代码基准 | `desktop/src/features/models/ModelsWorkspace.tsx`、`desktop/src/services/api/ai.ts`、`desktop/src/services/aiaskApi.ts`、`packages/agent/src/aiask_agent/routes/ai.py` |

### 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|---|---|---|---|
| 1.0.0 | 2026-06-21 | 按 L4 模板补齐模型配置的用户故事、接口、字段、错误和测试 | Codex |

### 术语定义

| 术语 | 定义 | 代码证据 |
|---|---|---|
| Provider | OpenAI-compatible 或其他 LLM 服务提供方 | `/v1/ai/status` |
| Smoke Test | 用于验证配置可用性的轻量请求 | `POST /v1/ai/smoke` |
| Secret Redaction | 密钥只显示配置状态，不回显真实值 | `secrets_redacted` |

## 1. 功能设计

### 1.1 需求背景与价值

| 项 | 内容 |
|---|---|
| 问题陈述 | 模型配置不可用会直接导致 Workbench 不能发送任务，用户需要知道是 key、base URL、model 还是服务异常。 |
| 解决方案 | Models 页面提供 provider、base URL、model、key 配置、模型列表和 smoke test，并把状态反馈到 Workbench。 |
| 业务价值 | 降低配置排障成本，避免 secret 泄露。 |

### 1.2 用户故事

| 编号 | 优先级 | 用户故事 | 成功标准 |
|---|---|---|---|
| MODEL-US-001 | P0 | 作为用户，我希望看到当前 provider 和 model 是否可用，以便知道能否发送任务。 | `/v1/ai/status` 状态清楚。 |
| MODEL-US-002 | P0 | 作为配置用户，我希望保存 key 后不被回显，以便保护凭据。 | 响应和 UI 只显示 configured/missing。 |
| MODEL-US-003 | P0 | 作为 QA，我希望 smoke test 能分类失败原因，以便验证 auth、timeout、model not found。 | 错误码和用户提示可见。 |

### 1.3 功能分解与优先级

| 功能编号 | 功能点 | 优先级 | 当前代码依据 | 待开发事项 | 验收标准 |
|---|---|---|---|---|---|
| MODEL-F001 | AI 状态展示 | P0 | `GET /v1/ai/status` | 与 Workbench 状态联动 | ready/missing/error 可见 |
| MODEL-F002 | 配置读取/保存 | P0 | `GET/PATCH /v1/ai/config` | 保存时提示 control token | secret 不回显 |
| MODEL-F003 | 模型列表 | P0 | `GET /v1/ai/models` | 错误分类 | 列表、空态、失败态可见 |
| MODEL-F004 | Smoke Test | P0 | `POST /v1/ai/smoke` | 分类错误码 | auth/timeout/provider 错误清楚 |

### 1.4 业务规则与边界

| 规则 | 说明 | 验收 |
|---|---|---|
| Secret 不回显 | key/token 只提交，不展示值 | UI 和响应 `secrets_redacted` |
| 配置写入受控 | 保存配置需要 control token 或后端明确策略 | 无 token 时 gated |
| Workbench 预检 | 模型不可用不能静默发送 | 发送按钮显示原因 |

## 2. 流程设计

| 步骤 | 用户操作 | 前端行为 | Agent/API | 异常 |
|---|---|---|---|---|
| 1 | 打开 Models | 加载状态和配置摘要 | `/v1/ai/status`、`/v1/ai/config` | 缺配置进入 gated/missing |
| 2 | 修改配置 | 编辑 provider/base URL/model/key | 本地表单 | key 不回显 |
| 3 | 保存 | 调用 PATCH | `/v1/ai/config` | 无 control token 显示 MODEL-201 |
| 4 | 获取模型 | 调用 models | `/v1/ai/models` | provider 失败显示 MODEL-301 |
| 5 | 冒烟测试 | 调用 smoke | `/v1/ai/smoke` | 按 auth/timeout/model 分类 |

状态机：`unconfigured -> editing -> saving -> configured -> smoke_running -> ready|failed|degraded`。

## 3. 架构设计

Desktop `ModelsWorkspace` 只调用 `AiaskApi`；Agent `routes/ai.py` 负责 provider 配置、模型列表和 smoke；任何真实 provider 错误不得泄露 secret。

## 4. 功能说明：接口与数据

| 操作 | Endpoint | Method | Token | 前端方法 | 关键字段 |
|---|---|---|---|---|---|
| 状态 | `/v1/ai/status` | GET | API | `aiStatus()` | `configured`、`provider`、`model` |
| 配置 | `/v1/ai/config` | GET/PATCH | API/control | `aiConfig()`、`aiConfigSave()` | `secrets_redacted` |
| 模型列表 | `/v1/ai/models` | GET | API | `aiModels()` | `models`、`error_code` |
| 冒烟 | `/v1/ai/smoke` | POST | API/control | `aiSmoke()` | `success`、`latency_ms`、`error_code` |

## 5. 前端设计

页面组件：`ModelsWorkspace -> ProviderForm -> ModelListPanel -> SmokeTestPanel -> ConfigStatusSummary`。所有字段显示 configured/missing/expired，不显示真实 key。

## 6. 开发规范

新增 provider 必须更新 `services/api/ai.ts`、mock、模型页测试和 Workbench 预检文案。

## 7. 错误说明

| 错误码 | 用户提示 | 技术原因 | 处理 |
|---|---|---|---|
| MODEL-201 | 模型密钥未配置或无效 | missing/auth failed | 引导配置 |
| MODEL-301 | 模型服务不可用 | provider timeout/down | 可重试或切换 provider |
| MODEL-401 | 保存配置需要控制令牌 | control token missing | 禁用保存 |

## 8. 功能测试

| 用例编号 | 场景 | 预期 |
|---|---|---|
| TC-MODEL-001 | 未配置 key | 显示 missing，不泄露 secret |
| TC-MODEL-002 | 保存配置 | 使用 control token，保存后 redacted |
| TC-MODEL-003 | smoke auth fail | 显示 auth 错误和修复入口 |
| TC-MODEL-004 | Workbench 联动 | 模型不可用时不能发送 |

## 9. 不做什么

- 不展示 key/token 原值。
- 不在前端直接调用 LLM provider。
- 不把 smoke 失败隐藏成通用错误。

## 10. 代码实证与成熟实现补强

### 10.1 当前前端事实

| 对象 | 代码证据 | 当前行为 | 文档结论 |
|---|---|---|---|
| 模型页面 | `desktop/src/features/models/ModelsWorkspace.tsx` | 支持 provider preset、base_url、model、api_key 替换、prompt cache、模型列表、smoke test | 文档不能只写“配置模型”，要写 provider 分组和保存/测试流程 |
| API 方法 | `services/api/ai.ts` 的 `aiConfig()`、`aiConfigSave()`、`aiModels()`、`aiSmoke()` | 对应 `/v1/ai/config`、`/v1/ai/models`、`/v1/ai/smoke` | 保存配置和冒烟测试是两个不同验收点 |
| secret 处理 | 页面保存后清空 `api_key`，`ModelsWorkspace.test.tsx` 验证 redaction | 已保存 key 不回显 | 文档只能写 env 名和 configured/missing，不写 key 值 |
| 运行状态 | `settingsStatus()` 聚合 LLM status，`AiTestingPanel.tsx` 显示 mock/live | 模型状态影响 Workbench 发送 | PM 演示必须区分 mock 模型和真实 provider |

### 10.2 具体功能清单

| 小功能 | 产品说明 | 开发落点 | QA 验收 |
|---|---|---|---|
| provider preset | 国产、国际、本地、自定义、Mock 分组，选择后填充 provider/base_url/model 默认值 | `ModelsWorkspace.tsx` 的 `groupPresets()`、`applyPreset()` | preset 切换不泄露旧 key |
| 保存配置 | 需要 control token；支持只更新模型/base_url 或替换 key | `PATCH /v1/ai/config` | 无 control token 不发 PATCH |
| 列出模型 | 从 provider 或兼容接口获取模型列表，支持搜索 | `GET /v1/ai/models` | provider 未配置时显示 unconfigured |
| 冒烟测试 | 使用默认 prompt 或用户输入 prompt 调 `/v1/ai/smoke` | `aiSmoke()` | 成功显示 PASSED，失败显示 error_code |

### 10.3 成熟技术采用

OpenAI API 文档提供 Tools/Conversation State 的模型调用上下文；Pydantic/FastAPI 官方文档用于后端配置 payload 校验；OWASP API Security 要求认证配置错误和敏感数据暴露进入验收。AIASK 采用“OpenAI-compatible provider + redacted secret + smoke test”的模式，不采用在前端保存或显示密钥原值。

## 11. 前端页面设计与布局细化

### 11.1 页面布局

| 区域 | 布局与内容 | 代码依据 | 交互要求 |
|---|---|---|---|
| 状态指标区 | provider、API key configured、base URL、provider pool、prompt cache、config source | `desktop/src/features/models/ModelsWorkspace.tsx`、`MetricCard` | secret 只显示“已配置/缺失/Mock”，不显示值 |
| Provider 表单 | provider preset、base URL、model、temperature/timeout 等配置项 | `ModelsWorkspace.tsx`、`/v1/ai/config` | 保存配置需要 control token；无 token 显示 gated |
| 模型列表 | `/v1/ai/models` 返回模型按 provider/source 分组 | `aiaskApi.ts`、`services/api/ai.ts` | 支持刷新、当前模型标记、fallback 标记 |
| Smoke 结果 | `/v1/ai/smoke` 成功/失败、延迟、错误摘要、raw JSON | `StatusBadge`、`JsonPanel` | 失败显示 auth/timeout/rate limit 分类和下一步 |

### 11.2 组件树

```text
ModelsWorkspace
├── ModelStatusSummary
├── ProviderConfigForm
├── ProviderPoolPanel
├── ModelListPanel
└── SmokeResultPanel
```

### 11.3 状态和响应式

- `empty`：没有模型时说明 provider 未配置或接口不可用，并给出配置入口。
- `error/degraded`：展示 HTTP status、provider、error_code；不要求用户查看控制台。
- 窄屏下表单、模型列表、smoke 结果按 stepper/折叠段落排列，主动作固定为“保存配置”或“运行冒烟测试”之一。

## 原有内容保留

## 功能目标

模型配置页要让产品经理和用户一眼知道：当前有没有可用 LLM、用的是官方直连还是中转商、模型列表能不能拉取、smoke test 是否通过、保存配置是否需要 control token。

## 外部参考

OpenAI 官方文档强调工具调用与会话状态需要稳定模型能力支撑。AIASK 前端应把 provider 状态、模型选择、工具调用兼容性和失败原因做成明确红黄绿状态。

## 代码证据

| 能力 | 代码位置 |
|---|---|
| 模型 provider | `packages/agent/src/aiask_agent/model_providers.py` |
| 模型 client | `packages/agent/src/aiask_agent/model_client.py` |
| AI 路由 | `packages/agent/src/aiask_agent/routes/ai.py` |
| AI payload | `packages/agent/src/aiask_agent/ai_payloads.py` |
| 前端页面 | `desktop/src/features/models/ModelsWorkspace.tsx` |
| API client | `desktop/src/services/aiaskApi.ts` 的 `aiStatus`、`aiConfig`、`aiConfigSave`、`aiModels`、`aiSmoke` |

## 用户流程

1. 打开模型配置，页面自动读取 `/v1/ai/status`、`/v1/ai/config`、`/v1/ai/models`。
2. 用户选择 provider：官方直连、中转商/OpenAI-compatible、本地/mock。
3. 官方直连只要求 key 和模型；中转商要求 base_url、key、模型、兼容协议。
4. 点击“保存配置”必须使用 control token；无 control token 按钮禁用。
5. 点击“获取模型列表”，只读请求拉取 provider 可用模型。
6. 点击“LLM 测试”，调用 `/v1/ai/smoke`，返回绿/红状态。

## 前端展现

| 状态 | UI |
|---|---|
| 绿色 | provider 已配置、models 拉取成功、smoke 通过 |
| 黄色 | 使用 mock/fallback、模型列表不可拉取但可手填、prompt cache 部分启用 |
| 红色 | key 缺失、认证失败、网络失败、rate limit、timeout |
| 灰色 | provider 未启用或 full mode 不需要 |

页面需要显示 provider 类型、当前模型、base_url 主机名、是否 redacted、最近测试时间、错误分类。绝不能显示 API key 原文。

## API 合约

| 操作 | Endpoint | Method | Token |
|---|---|---|---|
| 状态 | `/v1/ai/status` | GET | API token |
| 读取配置 | `/v1/ai/config` | GET | API token |
| 保存配置 | `/v1/ai/config` | PATCH | control token |
| 获取模型 | `/v1/ai/models` | GET | API token |
| smoke test | `/v1/ai/smoke` | POST | API token |

## 验收规则

1. 保存配置时 body 包含 provider/model/base_url/api_key/replace_api_key 等字段，但 UI 不显示 secret。
2. 缺 control token 时保存按钮 disabled，且不会发出 PATCH。
3. smoke test 成功显示绿灯，失败按 auth/rate_limit/timeout/network/provider 分类。
4. 模型切换后 Workbench 模型选择同步更新。

## 详细落地规范

### 问题场景与技术方案

| 问题 | 前端表现 | 技术方案 | 代码落点 | 验收 |
|---|---|---|---|---|
| 用户没有配置 key | provider 红灯，保存区提示只展示 env/key 状态 | `/v1/ai/status` 返回 missing/configured，不返回 key | `model_providers.py`、`routes/ai.py` | 页面不出现 key 原文 |
| 官方直连配置 | 表单只要求 provider、model、api_key | 使用 OpenAI official preset，base_url 使用默认 | `ai_payloads.py`、`ModelsWorkspace.tsx` | 保存后 smoke 通过显示绿灯 |
| 中转商配置 | 表单显示 base_url、模型名、兼容协议 | OpenAI-compatible client，错误按 provider/network 分类 | `model_client.py` | base_url 错误显示红灯和 endpoint 主机 |
| 模型列表拉取失败 | 模型列表黄灯，允许手动输入 | `/v1/ai/models` 失败不阻断保存 | `routes/ai.py`、前端 fallback | 用户仍可保存手填模型 |
| smoke test 超时 | 按钮恢复可点击，状态红灯 timeout | `/v1/ai/smoke` 设置超时和错误分类 | `model_client.py` | 不出现无限 loading |
| Workbench 模型切换不同步 | 顶部模型与配置页状态不一致 | 模型配置保存后刷新 app connection/settings | `useAppConnectionSettings.ts` | Workbench 显示新 provider/model |

### 配置类型设计

| 类型 | 用户要填 | 系统自动处理 | 风险 |
|---|---|---|---|
| 官方直连 | API key、model | 默认 base_url、官方模型列表 | key 错误、限流 |
| 中转商 | base_url、API key、model、协议兼容 | OpenAI-compatible request | 证书、网络、协议差异 |
| 本地/内网 | base_url、model、可选 key | 不访问公网 | 模型能力不足 |
| mock/fallback | 无需 key | 只用于开发/演示 | 不能当 live |

### 状态机

| 状态 | 说明 |
|---|---|
| `unconfigured` | 没有 provider 或 key |
| `configured_unverified` | 已保存但未 smoke |
| `models_loading` | 正在拉模型列表 |
| `models_failed` | 模型列表失败但可手填 |
| `smoke_running` | 正在 LLM 测试 |
| `available` | smoke 成功 |
| `degraded` | mock/fallback/部分能力不可用 |
| `failed_auth` | key 错误 |
| `failed_network` | base_url、DNS、代理失败 |
| `failed_rate_limit` | 限流 |
| `failed_timeout` | 超时 |

### 前端表单字段

| 字段 | 必填 | 显示规则 |
|---|---|---|
| `provider` | 是 | select，包含 official/openai-compatible/local/mock |
| `model` | 是 | 可选择也可手填 |
| `base_url` | 中转商/本地必填 | 显示主机和路径，不保存空字符串 |
| `api_key` | official/中转商必填 | 输入后只显示 `[redacted]` 或已配置 |
| `replace_api_key` | 否 | 用户明确勾选才替换 |
| `prompt_cache_enabled` | 否 | 显示说明和默认值 |
| `prompt_cache_recent_messages` | 否 | 数字输入，需上限 |

### 代码生成/修改步骤

1. 后端新增 provider 时，先扩展 `model_providers.py` 的 provider spec 和错误分类。
2. `routes/ai.py` 必须提供 status/config/models/smoke，不让前端猜测可用性。
3. `desktop/src/services/api/ai.ts` 或 `aiaskApi.ts` 增加 client 方法。
4. `desktop/src/features/models/ModelsWorkspace.tsx` 增加表单字段、状态灯、错误分类。
5. `desktop/src/mockApi.ts` 增加成功、auth failed、timeout、models failed 四类 mock。
6. 测试必须覆盖无 control token 禁用保存、secret redaction、smoke 分类、Workbench 同步。

### API 响应字段要求

`/v1/ai/status` 至少应能表达：

- `configured`
- `provider`
- `model`
- `mode`
- `last_error`
- `last_smoke_at`
- `secrets_redacted`
- `capabilities`

`/v1/ai/smoke` 至少应能表达：

- `success`
- `provider`
- `model`
- `latency_ms`
- `error_code`
- `error_class`
- `message`

### 不做什么

- 不显示 API key 原文。
- 不把 mock 状态显示成生产可用。
- 不在缺 control token 时保存配置。
- 不让 Workbench 在模型红灯时静默发送失败。
