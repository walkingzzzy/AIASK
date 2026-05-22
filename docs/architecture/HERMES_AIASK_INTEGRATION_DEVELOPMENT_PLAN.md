# Hermes Agent 与 AIASK 融合方案：AIASK 原生实现基线

修订日期：2026-04-27

## 当前结论

AIASK 的目标不是嫁接 Hermes，而是在 AIASK 自有 runtime 内原生实现
Hermes 级能力。`vendor/hermes-agent-upstream/` 只作为 v0.14.0 能力规格、
行为参考和差距对照，不进入运行时依赖、import path、sidecar 或发布物。

正式边界以 `docs/architecture/hermes-boundary.md` 为准。

## 当前执行架构

```text
客户端 / 桌面端 / 本地脚本
        |
AIASK Agent HTTP Server (`packages/agent`, script: `aiask-agent`)
        |
AIASK Agent Runtime + Session Store + Tool Registry + Intent Store
        |
AIASK native capability tools (`agent_*`)
        |
akshare-mcp + strategy-factory + DB/审计/风控
```

职责边界：

- `packages/agent`：AIASK 自有 Agent runtime，负责模型调用、工具编排、会话、response store、run events、memory、planner、scheduler、action intent、权限和 Hermes 级能力实现。
- `aiask_agent.native_capabilities`：AIASK 原生 Web、Skills、Plugins、Clarify、Todo、Vision/Image、TTS 和 Messaging Outbox 能力。
- `packages/akshare-mcp`：继续负责金融工具、manager、数据源和风控基础设施，不承载通用 Agent loop。
- `packages/strategy-factory`：继续负责策略工厂业务运行态、策略生产、验证、调度和生命周期。
- `vendor/hermes-agent-upstream`：只作 reference，不进入 active packages。

## 当前已落地能力

- `aiask_agent.runtime.AgentRuntime` 已实现多轮模型调用、OpenAI function/tool schema、工具结果回填、最大迭代、超时、retry、审计事件和 response 保存。
- `aiask_agent.tool_registry.AgentToolRegistry` 只暴露 `agent_*` 工具名。
- 默认 `finance_safe` 模式只暴露金融安全工具和金融上下文检索。
- `hermes_full` 是 AIASK 原生 full-capability 模式，需设置 `AIASK_AGENT_ENABLE_HERMES_FULL=1` 并使用 control token。
- `aiask_agent.native_capabilities` 已提供 AIASK 原生 Hermes 级基础能力面：web search/extract、skills、plugins、clarify、todo、vision metadata、image generation provider hook、TTS provider hook、message outbox。
- `aiask_agent.capabilities` 已提供金融产品 parity 矩阵；`/v1/capabilities/parity` 和 `/v1/hermes/status` 返回真实 `implemented/partial/planned/excluded` 状态。
- `aiask_agent.server` 默认迁移到 FastAPI/ASGI，保留 legacy HTTP 兼容入口；已提供 `/v1/hermes/status`、`/v1/hermes/toolsets`、`/v1/hermes/tools`、`/v1/hermes/config`、`/v1/hermes/sessions` 和 control-token 保护的 `/v1/hermes/admin/tools/{name}`。
- Full Mode 管理 API 已扩展到 `/v1/processes`、`/v1/browser/sessions`、`/v1/skills`、`/v1/plugins`、`/v1/mcp/*`、`/v1/jobs`、`/v1/webhooks`、`/v1/approvals`、`/v1/runs/{id}/events`、`/v1/runs/{id}/steer` 和 `/v1/runs/{id}/cancel`。
- `agent_terminal` 已支持 session cwd、后台进程启动、`agent_process` list/read/kill，以及与运行态状态库一致的 process/approval 记录。
- `agent_execute_python` 已升级为 runtime-bound 代码执行工具，脚本可通过自动生成的 `aiask_tools` RPC 模块调用当前启用的 AIASK 安全工具。
- `packages/agent/tests/test_no_hermes_dependency.py` 继续阻止 active packages 依赖 Hermes runtime。
- `packages/agent/tests/test_native_full_parity.py` 覆盖 AIASK 原生 full mode 管理面、MCP/skills/plugins/webhook/run control，以及 approval/plugin hook 事件。
- 桌面端 Hermes 页已改为 AIASK Full Mode 控制台，直接展示 parity、工具目录、runs/events、skills/plugins、MCP、cron/webhook、browser/process、approvals/audit。

## 当前仍非完成项

当前不能宣称“全部 Hermes 能力已完全实现”。`/v1/capabilities/parity` 会将以下能力保持为 `partial`，直到对应 provider、长会话或更深 runtime 行为有测试证明：

- 交互式 terminal/PTY、更复杂的长期进程恢复。
- browser-grade web extract、视觉语义分析、图片/TTS/STT 的真实 provider 调用。
- 多语言/远程代码沙箱、复杂 subagent 协作。
- 外部消息递送渠道、非 stdio MCP 运行时调用和 OAuth token 流程。

## 安全边界

- 生产默认是 `finance_safe`。
- `hermes_full` 不是 vendor Hermes 嫁接，而是 AIASK 原生 `general_full` 工具策略。
- 高权限工具只在 `AIASK_AGENT_ENABLE_HERMES_FULL=1` 且 control token 通过时可用。
- 真实交易、模拟交易和底层 manager 仍需 durable intent + confirm/deny 控制面。

## 废弃方向

- 嵌入 Hermes runtime。
- 启动 Hermes sidecar。
- 让桌面端连接 Hermes API、Hermes MCP 或 Hermes gateway。
- 把 `run_agent.py`、`model_tools.py`、`toolsets.py`、`hermes_cli`、`tools.mcp_tool` 等 vendor 模块加入 active package。
