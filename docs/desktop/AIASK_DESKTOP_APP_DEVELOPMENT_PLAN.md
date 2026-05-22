# AIASK 桌面应用端开发方案：当前基线

修订日期：2026-04-24

## 当前结论

桌面端上游 Agent runtime 是 AIASK 自有 `aiask-agent`，不是 Hermes API
Server。AIASK 原生实现 Hermes 级能力；Hermes 仅作为
`vendor/hermes-agent-upstream/` 中的 reference 源码保留。

正式边界以 `docs/architecture/hermes-boundary.md` 为准。

## 当前运行边界

```text
Desktop App
  负责：Agent 工作台、会话查看、策略工厂观察、intent 确认/拒绝 UI、健康检查

AIASK Agent Server (`packages/agent`, script: `aiask-agent`)
  负责：Agent loop、session、run/response store、金融记忆、任务状态、
       金融工具编排、AIASK native Hermes-full 能力、OpenAI-compatible HTTP API、
       action intent control surface

AIASK MCP + Strategy Factory
  负责：金融工具、策略工厂、审计、side_effect、确认后实际执行
```

桌面端首选对接：

- `GET /health`
- `GET /health/detailed`
- `GET /v1/tools`
- `POST /v1/tools/{name}`（只读工具）
- `POST /v1/chat/completions`
- `POST /v1/responses`
- `GET /v1/responses/{id}`
- `DELETE /v1/responses/{id}`
- `GET /v1/hermes/status`
- `GET /v1/hermes/toolsets`
- `GET /v1/hermes/tools`（control token）
- `GET /v1/hermes/config`（control token）
- `GET /v1/hermes/sessions`（control token）
- `GET /intents/{id}`
- `POST /intents/{id}/confirm`
- `POST /intents/{id}/deny`

## 安全边界

- `aiask-agent` 默认绑定 `127.0.0.1`。
- 普通 API 在 loopback 绑定下用于本地开发；非 loopback 必须配置 `AIASK_AGENT_API_TOKEN`。
- confirm/deny 只允许 loopback，且必须携带 `AIASK_AGENT_CONTROL_TOKEN` 或兼容的 `AIASK_LOCAL_CONTROL_TOKEN`。
- 桌面端不直接调用 MCP，不直接 import `strategy_factory`，不直接调用 vendor Hermes。
- 桌面端可通过 AIASK `hermes_full` 模式访问 AIASK 原生高权限能力；该模式需要本地 control token。
- 桌面端不再连接 Hermes API Server，不依赖 Hermes run events 或 Hermes CORS 配置。

## 当前实现位置

- `desktop/`
- `packages/agent/pyproject.toml`
- `packages/agent/src/aiask_agent/runtime.py`
- `packages/agent/src/aiask_agent/tool_registry.py`
- `packages/agent/src/aiask_agent/session_store.py`
- `packages/agent/src/aiask_agent/memory.py`
- `packages/agent/src/aiask_agent/todo.py`
- `packages/agent/src/aiask_agent/intents.py`
- `packages/agent/src/aiask_agent/server.py`

## MVP 范围

本轮 MVP 已按“可用闭环”收敛：

- 桌面端可配置 `aiask-agent` endpoint，默认 `http://127.0.0.1:8767`。
- 桌面端通过 `/health/detailed` 和 `/v1/tools` 获取健康状态和安全工具目录。
- Agent Console 只调用 `/v1/responses`，展示回答、工具调用和审计事件。
- Strategy Factory 观察台只通过 `/v1/tools/agent_factory_status`、`agent_factory_runs`、`agent_strategy_review_snapshot` 读取结构化数据。
- Intent Inspector 通过 `GET /intents/{id}` 读取状态，通过 confirm/deny 控制面执行确认或拒绝。
- MVP 不包含 sidecar、远程多用户 BFF、真实交易或模拟交易执行。
- `hermes_full` UI 仅切换 AIASK 原生 full-capability mode，不启动或嵌入 Hermes。

## 废弃方案

以下历史方向已经废弃，仅作为短历史附录，不再作为桌面端开发依据：

- 桌面端连接 Hermes API Server。
- 桌面端依赖 Hermes `/v1/runs`、`/v1/runs/{run_id}/events` 或 Hermes SSE timeline。
- 打包 Hermes 作为默认 sidecar。
- 通过自由文本 Hermes run 完成 action intent confirm/deny。
- 桌面端直接访问 MCP、数据库、`strategy_factory` 或底层 manager。

后续如果需要流式 timeline，应在 `aiask-agent` 内设计自有 run/event API，
而不是恢复 Hermes runtime 路线。
