# Native 文件、代码、终端、浏览器能力

## 文档信息

| 项目 | 内容 |
|---|---|
| 项目名称 | AIASK V1 前端产品化 |
| 功能名称 | Native 文件、代码、终端、浏览器能力 |
| 功能编号前缀 | `NATIVE` |
| 文档版本 | 1.0.0 |
| 更新日期 | 2026-06-21 |
| V1 状态 | 高级能力，必须 full mode/control token |
| 代码基准 | `packages/agent/src/aiask_agent/routes/full_controls.py`、`tools/catalog.py`、`tool_registry.py`、`desktop/src/services/aiaskApi.ts` |

### 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|---|---|---|---|
| 1.0.0 | 2026-06-21 | 按 L4 模板补齐 Native 高权限能力的门禁、流程、错误和测试 | Codex |

### 术语定义

| 术语 | 定义 | 代码证据 |
|---|---|---|
| Native Tool | 文件、终端、浏览器、进程等本地高权限工具 | `general_full` toolset |
| Full Mode | 高权限模式 | `tools/policy.py` |
| Process/Terminal/Browser Controls | 本地运行状态只读和受控入口 | `routes/full_controls.py` |

## 1. 功能设计

### 1.1 需求背景与价值

| 项 | 内容 |
|---|---|
| 问题陈述 | 文件、终端、浏览器能力风险高，必须让用户知道何时只读、何时会执行或写入。 |
| 解决方案 | 统一标记 full mode、control token、ActionIntent、stdout/stderr、文件 diff 和 blocked reason。 |
| 业务价值 | 保留强大本地能力，同时避免误执行。 |

### 1.2 用户故事

| 编号 | 优先级 | 用户故事 | 成功标准 |
|---|---|---|---|
| NATIVE-US-001 | P1 | 作为用户，我希望看到终端/浏览器会话状态。 | sessions/backends 可见。 |
| NATIVE-US-002 | P1 | 作为用户，我希望文件写入前看到 diff 和确认。 | 写入动作 gated/intent。 |
| NATIVE-US-003 | P1 | 作为安全负责人，我希望 full mode 未启用时高权限动作不可执行。 | disabled/blocked reason 可见。 |

### 1.3 功能分解与优先级

| 功能编号 | 功能点 | 优先级 | 当前代码依据 | 待开发事项 | 验收标准 |
|---|---|---|---|---|---|
| NATIVE-F001 | Process/Terminal/Browser 状态 | P1 | `/v1/processes`、terminal/browser routes | UI 汇总 | 只读状态可见 |
| NATIVE-F002 | 文件/代码写入 | P1 | `agent_file_*` 工具 | diff/confirm | 无门禁不执行 |
| NATIVE-F003 | 终端/代码执行 | P1 | terminal/code tools | stdout/stderr | full mode/control token |

### 1.4 业务规则与边界

full mode 必须显式；写入前有 diff/确认；执行结果必须展示 stdout/stderr/exit code；Desktop 不直接执行本地命令。

## 2. 流程设计

状态机：`disabled -> gated -> preview -> approved -> running -> success|failed|blocked`。

## 3. 架构设计

Desktop 只展示高权限状态和受控入口；Agent full_controls routes 和 tool policy 是执行边界。

## 4. 功能说明：接口与数据

| 能力 | Endpoint/Tool | Token | 字段 |
|---|---|---|---|
| Processes | `/v1/processes` | control | pid/name/status |
| Terminal backends | `/v1/terminal/backends` | control | backend/sessions |
| Browser sessions | `/v1/browser/sessions` | control | session/status |
| Native tools | `agent_*` general_full tools | full/control | side_effect/stdout/stderr |

## 5. 前端设计

高权限 UI 必须用 ActionPanel、DiffPreview、CommandPreview、OutputPanel、RiskNotice、ApprovalLink。

## 6. 开发规范

新增 Native 能力必须补 full mode gate、control token、side_effect、redaction、negative test。

## 7. 错误说明

| 错误码 | 用户提示 | 技术原因 | 处理 |
|---|---|---|---|
| NATIVE-201 | 需要 full mode | full disabled | 显示设置入口 |
| NATIVE-401 | 需要控制令牌 | control missing | 禁用执行 |
| NATIVE-501 | 执行失败 | non-zero/error | 展示 stdout/stderr |

## 8. 功能测试

| 用例编号 | 场景 | 预期 |
|---|---|---|
| TC-NATIVE-001 | full mode disabled | 高权限按钮 blocked |
| TC-NATIVE-002 | command fail | stdout/stderr 可见 |
| TC-NATIVE-003 | file write | diff/confirm |
| TC-NATIVE-004 | no direct bypass | Desktop 不直接执行 |

## 9. 不做什么

- 不在普通模式一键执行终端/写文件/浏览器操作。
- 不隐藏命令和输出。
- 不绕过 Agent policy。

## 10. 代码实证与成熟实现补强

### 10.1 当前代码审计

| 能力 | 代码证据 | 当前行为 | 文档结论 |
|---|---|---|---|
| Full controls | `routes/full_controls.py` | `/v1/processes`、`/v1/terminal/backends`、`/v1/terminal/sessions`、`/v1/browser/sessions` | Native 能力只通过 Agent HTTP 观测/控制 |
| Diagnostics | `DiagnosticsPanel.tsx` | 读取 terminal backends/sessions，需要 control token | 无 token 显示 gated，不直接启动终端 |
| Security scan | `SecurityPanel.tsx` | 调 `agent_security_scan`，参数 `include_env: false` | 安全扫描默认不包含 env 内容 |
| Tool policy | `tools/policy.py`、`schema_general_full.py` | general_full 需显式启用 | full mode 不是默认能力 |

### 10.2 Native 功能细节

| 功能 | 用户看到 | 技术边界 | 验收 |
|---|---|---|---|
| 文件/代码 | 计划、diff、artifact、source、approval | 写入只能走 `agent_file_patch/write` 和控制门禁 | 无 token 不写文件 |
| 终端/进程 | backend、session、stdout/stderr、exit code | `routes/full_controls.py` 只在 full/control 下可用 | 命令不可静默执行 |
| 浏览器 | session 状态、页面标题、错误 | Agent browser tool facade | 不在 Desktop 直连 CDP |
| 安全扫描 | path/text、scan result、advisory | `include_env: false` | env 值不出现在结果中 |

### 10.3 成熟技术采用

Tauri Security 官方文档强调桌面应用的 trust boundaries。AIASK 采用“Desktop 只做 UI，Agent 统一执行和审计”的模式，不采用前端直接访问本地文件系统、终端、浏览器或 WebView 特权。

## 11. 前端页面设计与布局细化

### 11.1 页面布局

| 区域 | 布局与内容 | 代码依据 | 交互要求 |
|---|---|---|---|
| 能力卡片 | file、patch、search、terminal、process、browser、web、media、security scan | `ToolsIntentsApprovalsPage.tsx`、native `agent_*` tools | 每张卡显示 read-only/stateful/high-risk |
| 受控操作面板 | 参数表单、dry-run、确认提示、intent/approval 状态 | `ActionIntent` routes | 写文件、终端、浏览器动作必须 gated |
| 运行结果 | stdout/stderr、exit code、browser session、process status、scan report | Agent native routes/tools | 结果默认折叠，错误和 blocked reason 可见 |
| 安全提示 | workspace 边界、control token、full mode、secret redaction | `SecurityPanel.tsx`、`shared.tsx` | 不展示真实环境变量值 |

### 11.2 组件树建议

```text
NativeCapabilitiesView
├── NativeCapabilityCards
├── ControlledActionForm
├── RunResultPanel
├── ProcessBrowserTerminalStatus
└── NativeSecurityEvidencePanel
```

### 11.3 状态和响应式

- `gated/blocked` 是常态设计：缺 full mode/control token 时能力卡仍可解释，但不可执行高风险动作。
- `success` 必须展示 run/action id、输出摘要和审计证据，不只弹 toast。
- 窄屏能力卡单列，结果面板折叠，长输出按固定高度滚动。

## 原有内容保留

## 功能目标

AIASK 具备 Hermes 类 native 能力：读文件、写文件、patch、搜索文件、运行 Python/代码、操作终端、管理进程、浏览器导航与快照、网页提取、多模态处理。这些能力在产品上不能简单暴露成“随便执行”，必须作为高权限工具能力纳入 AI 回复和审批流程。

## 代码证据

| 能力 | 代码位置 |
|---|---|
| 能力映射 | `packages/agent/src/aiask_agent/capabilities.py` |
| full controls route | `packages/agent/src/aiask_agent/routes/full_controls.py` |
| 工具目录/注册 | `packages/agent/src/aiask_agent/tools/catalog.py`、`tool_registry.py` |
| Terminal APIs | `/v1/processes`、`/v1/terminal/backends`、`/v1/terminal/sessions` |
| Browser APIs | `/v1/browser/sessions` 与 `agent_browser_*` 工具 |
| 前端入口 | Workbench 工具调用卡、Tools/Intents/Approvals、Readiness/Diagnostics |

## 用户流程

1. 用户在对话中要求“编辑文件/创建代码/运行终端/运行代码/打开网页”。
2. AI 生成工具调用计划，前端右侧显示将执行的工具和风险。
3. 只读动作可直接显示结果；写入/执行动作必须等待确认或 full mode。
4. 执行后返回文件 diff、命令输出、浏览器快照、错误和产物。
5. 用户可从 run events 和 artifacts 追踪每次动作。

## 前端展现

| 能力 | UI |
|---|---|
| 文件读取 | 文件路径、摘要、引用位置 |
| 文件写入/patch | diff、影响文件、确认按钮、回滚入口 |
| 代码执行 | 语言、输入、stdout/stderr、退出码、超时 |
| 终端 | backend、session、命令、输出、进程状态 |
| 浏览器 | url、快照、点击/输入动作、控制台错误 |
| 网页搜索/提取 | query、来源、摘要、引用链接 |

## 安全规则

1. full mode 未开启时，高权限 native 工具只显示能力说明，不提供执行按钮。
2. 文件写入、patch、终端、浏览器控制必须显示影响范围。
3. 终端输出要截断和折叠，避免刷屏。
4. 不显示 secret、`.env` 原值、凭据。
5. 所有 native 动作必须有 run/event 记录。

## 验收规则

1. 对话触发 native 工具时，右侧栏显示工具调用卡。
2. 写入/执行类工具缺 control token 时不能执行。
3. 文件 patch 结果必须可审查。
4. 终端/代码执行失败显示退出码和错误摘要。
5. 浏览器操作必须有目标 URL 和快照/状态。

## 详细落地规范

### 问题场景与技术方案

| 问题 | 表现 | 技术方案 | 代码落点 | 验收 |
|---|---|---|---|---|
| AI 要编辑文件 | 先展示 diff 和影响文件 | `agent_file_patch` + full/control gate | `capabilities.py`、tool registry | 无确认不写入 |
| AI 要创建代码 | 生成文件计划和路径 | file write intent/checkpoint | native tools | 路径和内容摘要可见 |
| AI 要运行代码 | 显示语言、输入、超时 | `agent_execute_python` 或 terminal | full controls | stdout/stderr 可见 |
| AI 要运行终端 | 命令预览和风险 | `agent_terminal`/process | `/v1/terminal/*` | exit code 可见 |
| AI 要操作浏览器 | URL、动作、快照 | `agent_browser_*` | browser sessions | 快照/console 可见 |
| 输出过大 | 折叠和截断 | output summarizer | UI RawPayloadDetails | 不撑破页面 |

### 高权限动作 UI 规则

| 动作 | 必须显示 |
|---|---|
| 写文件 | 文件路径、diff、确认、回滚说明 |
| 运行终端 | 命令、工作目录、超时、风险 |
| 运行代码 | 语言、输入、输出、错误 |
| 浏览器控制 | URL、动作序列、快照 |
| 网页提取 | 来源 URL、抓取时间、引用 |

### 代码生成/修改步骤

1. 新 native 能力先进入 Agent tool catalog，不直接写 Desktop 控件。
2. 工具 schema 必须声明输入、输出、side_effect。
3. Desktop 工具卡只根据 tool event 渲染，不硬编码具体能力。
4. 测试覆盖 full mode 关闭、control token 缺失、执行失败和输出截断。

### 不做什么

- 不读取或展示 `.env` secret 原值。
- 不允许普通模式直接写文件/跑终端。
- 不把浏览器自动化伪装成普通链接打开。

### 状态机补充

`requested -> preflight -> awaiting_confirm -> executing -> succeeded/failed -> artifact_recorded`

写入类动作额外有 `checkpoint_created -> patch_applied -> verified -> rollback_available`。
