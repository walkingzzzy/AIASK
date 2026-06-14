# AIASK 系统级 Agent 协调审计报告

日期：2026-06-13  
范围：AIASK Agent Runtime、Desktop HTTP 合同、工具调用审计、证据/产物链路、上下文理解、Agent 交接/委派、金融/量化/经纪只读流程。

## 1. 结论摘要

AIASK 目前不是普通应用，也不是“聊天壳 + 工具列表”的阶段。当前仓库已经具备系统级 Agent 的关键底座：

- Desktop 基本通过 Agent HTTP API 访问后端，没有发现 Desktop 直接导入 Python 包、直接调用 MCP 或 manager 的主路径。
- Agent 工具以 `agent_*` facade 暴露，内部 manager/MCP 名称没有作为模型可见工具主面泄漏。
- SQLite 中已有 `run_events`、`tool_invocations`、`agent_sources`、`agent_artifacts`、`session_handoffs` 等一等状态表。
- Runtime 主循环已经记录模型事件、工具调用、审批、guardrail、source/artifact 事件。
- `context_references` 已能解析项目文件、`@file`、`@url`，并把引用沉淀为 sources/artifacts。

核心问题不是“完全缺能力”，而是“协调漂移”：有些用户触发执行路径经过统一审计/证据链路，有些路径直接 `tool_registry.call_tool()`；有些只是状态探针可以直连，有些却会导致 Agent 的因果账本缺页。系统级 Agent 真正要达标，必须保证所有用户可见执行、外部系统读取、状态变更、研究运行、交接和上下文压缩都可追踪、可复盘、可恢复。

本轮已修复 P0/P1 中最实际的缺口：金融管理器查询/意图、broker-readonly 同步、量化研究运行、通用 `/intents` 创建已经进入统一 `tool_invocations` + evidence helper；`agent_execute_python` 内部 RPC 子工具也会逐项落审计账本；artifact 内容读取已经防止越权读取被标记 blocked 的路径；runtime 上下文准备也已经生成 durable `context_snapshots`，把压缩、引用和风险标记沉淀到可复盘对象中；handoff ownership 和 context snapshot 也已经从 session metadata 提升为 Desktop Sessions 可见合同。

## 2. 外部研究基准

本次联网核验的一手资料和提炼标准如下：

- OpenAI Agents SDK：Agent 是 LLM + tools + handoffs + guardrails + tracing + sessions 的组合，不只是工具注册。参考：https://openai.github.io/openai-agents-python/
- OpenAI Tracing：trace 应覆盖 model calls、tool calls、handoffs、guardrails、custom spans。参考：https://openai.github.io/openai-agents-python/tracing/
- OpenAI Handoffs：handoff 是“对话/任务所有权转移”，不是单纯记录一条交接单。参考：https://openai.github.io/openai-agents-python/handoffs/
- OpenAI Guardrails：输入、输出、工具和人工审核都要作为可追踪控制点。参考：https://openai.github.io/openai-agents-python/guardrails/
- MCP Tools 规范：工具是模型控制的 schema-defined 执行点；需要输入校验、输出约束、敏感操作确认、审计日志。参考：https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- LangGraph Agent 概念：复杂 Agent 应显式建模 State、Nodes、Edges 和 state-driven routing/handoff。参考：https://langchain-ai.github.io/langgraph/concepts/agentic_concepts/
- Anthropic Building Effective Agents：从简单模式开始，但多 agent/多工具系统必须使用清晰组合模式，避免 opaque abstraction。参考：https://www.anthropic.com/engineering/building-effective-agents
- A2A Protocol：跨 Agent 协作需要 capability discovery、stateful Task、Messages、Artifacts，并避免暴露内部工具/状态。参考：https://a2a-protocol.org/latest/specification/

这些资料共同指向一个工程判断：系统级 Agent 的核心不是“更多功能”，而是统一的状态账本、工具合同、证据链、权限边界、上下文恢复和交接语义。

## 3. 当前实现证据

### 3.1 架构规模和边界

Graphify 基线显示仓库核心图约 7,638 节点、19,921 边，其中 `packages/agent/src/aiask_agent/server.py` 是最高连接度节点；`desktop/src/services/aiaskApi.ts`、`desktop/src/mockApi.ts`、`desktop/src/types.ts` 也是高连接度节点。说明 AIASK 的协调中枢已经集中在 Agent HTTP 与 Desktop 合同上，不能随意重排。

关键边界：

- Desktop -> Agent HTTP only。
- 模型可见工具必须是 `agent_*`。
- AKShare/finance manager/MCP manager 名称应保持内部/provider-facing。
- 外部平台、文件写入、终端、浏览器、策略生命周期、交易风险路径必须有 control token、ActionIntent 或等价 guardrail。

### 3.2 证据/审计底座

当前 `AgentSessionStore` 已有：

- `run_events`：`packages/agent/src/aiask_agent/session_store.py:225`
- `session_handoffs`：`packages/agent/src/aiask_agent/session_store.py:232`
- `tool_invocations`：`packages/agent/src/aiask_agent/session_store.py:271`
- `agent_sources`：`packages/agent/src/aiask_agent/session_store.py:295`
- `agent_artifacts`：`packages/agent/src/aiask_agent/session_store.py:317`
- `start_tool_invocation()`：`packages/agent/src/aiask_agent/session_store.py:1114`
- `record_source()`：`packages/agent/src/aiask_agent/session_store.py:1675`
- `record_artifact()`：`packages/agent/src/aiask_agent/session_store.py:1737`

Runtime 主循环记录工具调用并抽取 evidence：

- 主工具调用在 `packages/agent/src/aiask_agent/runtime.py:439`
- `context.references_resolved` 在 `packages/agent/src/aiask_agent/runtime.py:199`
- `context.compacted` 在 `packages/agent/src/aiask_agent/runtime.py:235`

本轮统一 HTTP 执行审计 helper：

- `_audited_runtime_tool_call()`：`packages/agent/src/aiask_agent/server.py:360`
- FastAPI `audited_tool_call()` 委托统一 helper：`packages/agent/src/aiask_agent/server.py:2362`
- 备用 HTTPServer `_audited_tool_call()` 委托统一 helper：`packages/agent/src/aiask_agent/server.py:4605`

### 3.3 已接入统一审计的用户触发路径

本轮已把以下用户触发路径接入统一审计：

- Financial Manager read-only query：`packages/agent/src/aiask_agent/server.py:3322`
- Financial Manager ActionIntent 创建：`packages/agent/src/aiask_agent/server.py:3344`
- Broker read-only sync 内部金融查询：`packages/agent/src/aiask_agent/server.py:3359`
- Quant research run：`packages/agent/src/aiask_agent/server.py:3230`
- 通用 `/intents` 创建：`packages/agent/src/aiask_agent/server.py:3710`

对应测试：

- `packages/agent/tests/test_financial_manager_desktop_api.py`
- `packages/agent/tests/test_broker_readonly_api.py`
- `packages/agent/tests/test_desktop_workbench_contracts.py`

## 4. 问题与风险

### P0/P1 已修：用户触发执行路径曾绕过工具调用账本

问题：部分 Desktop POST 路径直接调用 `runtime.tool_registry.call_tool()`，导致工具执行结果能返回给 UI，但 Agent 的长期审计/复盘账本缺少 `tool_invocations`、source/artifact 关联或 `action_intent_id`。

影响：

- 用户行为、工具执行、审批/意图、证据之间无法形成完整因果链。
- 后续学习、追踪、失败恢复、审计面板会漏掉关键动作。
- 同一个工具经 `/v1/tools/{tool}` 与业务专用 endpoint 调用时，落库行为不一致。

已修：

- 新增统一 `_audited_runtime_tool_call()`。
- Financial Manager、broker-readonly、quant research、intent create 均接入。
- FastAPI 和备用 HTTPServer 的审计 helper 均委托同一实现。

仍需继续：

- 把所有 POST/side-effect/external-read endpoint 做一次“必须审计/可内部探针/纯状态读取”分类表。
- 对未来新增 endpoint 加 drift gate：新增直接 `tool_registry.call_tool()` 必须声明理由。

### P1 已修：`agent_execute_python` 内嵌工具 RPC 曾不是逐工具审计

原问题：Python RPC server 内部直接调用 `self.tool_registry.call_tool(name, args)`，只在 `agent_execute_python` 外层形成一次工具调用记录，内部多次 tool RPC 只在返回摘要中出现。

影响曾包括：

- Python 代码中调用的子工具没有独立 `tool_invocations`。
- 如果子工具读取外部数据、产生 artifact/source 或失败，复盘粒度不足。

已修：

- 外层 `agent_execute_python` 执行前注入内部 `_aiask_runtime_context`：`packages/agent/src/aiask_agent/runtime.py:441`
- 内部每个 RPC 子工具创建独立 invocation，id 形如 `parent.rpc.N`：`packages/agent/src/aiask_agent/runtime.py:962`
- 子工具 `source_chain` 使用 `["aiask_agent.runtime", "agent_execute_python.rpc", "aiask_agent.tool_registry"]`：`packages/agent/src/aiask_agent/runtime.py:975`
- 子工具写入 `tool.rpc.started` / `tool.rpc.completed` run events，并抽取 source/artifact：`packages/agent/src/aiask_agent/runtime.py:980`
- 回归测试覆盖 Agent run 内的 Python RPC 子工具审计：`packages/agent/tests/test_extended_agent_capabilities.py:276`

### P1 部分已修：handoff/subrun 已有基础 active state 与 context snapshot 链路

证据：

- `session_handoffs` 表存在：`packages/agent/src/aiask_agent/session_store.py:232`
- `agent_session_handoff` 工具存在，支持 request/status/list/complete/fail：`packages/agent/src/aiask_agent/tools/schemas.py:1093`
- `agent_delegate_task` 创建 subrun：`packages/agent/src/aiask_agent/runtime.py:1296`
- runtime 对 `agent_session_handoff` / `agent_delegate_task` 注入内部 `_aiask_runtime_context`：`packages/agent/src/aiask_agent/runtime.py:508`
- handoff request metadata 会记录 `handoff_kind=ownership_transfer`、source run/session/tool_call 和 `context_snapshot_id`：`packages/agent/src/aiask_agent/native_capabilities.py:1747`
- delegation subrun record 会记录 `mode=delegation_subrun`、parent/child context snapshot：`packages/agent/src/aiask_agent/runtime.py:1356`
- 回归测试覆盖 delegation 与 handoff 的 snapshot 链路：`packages/agent/tests/test_extended_agent_capabilities.py:523`
- session metadata 中已有 `handoff_state`、`active_agent`、`active_context_snapshot_id`：`packages/agent/src/aiask_agent/session_store.py:624`
- runtime 下一轮会消费 pending handoff state，发出 `handoff.activated` 并注入 `handoff_state` system message：`packages/agent/src/aiask_agent/runtime.py:190`
- runtime 会把 handoff target 映射到 specialist policy，写入 `handoff.policy_applied` run event，并把对应专家 prompt 与过滤后的 tool schema 传给模型：`packages/agent/src/aiask_agent/runtime.py:283`
- runtime 后续同 session 继续时会识别 active handoff，发出 `handoff.resumed` 并重新注入 handoff state/specialist policy：`packages/agent/src/aiask_agent/runtime.py:259`
- `/v1/hermes/sessions` 已暴露 `handoff_state`、`handoff_status`、`handoff_target`、`active_agent`、`active_context_snapshot_id`：`packages/agent/src/aiask_agent/server.py:1965`
- `/v1/hermes/handoffs` 已暴露 handoff queue，按 runtime_status 汇总 active/pending 等队列状态：`packages/agent/src/aiask_agent/server.py:2037`
- `/v1/hermes/sessions/{session_id}/resume-context` 已暴露 snapshot-aware resume payload：`packages/agent/src/aiask_agent/server.py:2083`
- Desktop Sessions 页面已展示任务接管、交接状态和上下文快照，并支持按 handoff target / snapshot 搜索：`desktop/src/features/agent-pages/SessionsPage.tsx:51`

已修：

- `agent_session_handoff request` 会写入 session-level pending `handoff_state`。
- 下一轮同 session runtime run 会把 pending 状态切为 active，记录 active run/trace，并向模型提供 handoff target、handoff_id、context_snapshot_id、reason、summary。
- `complete` / `fail` 会把 session handoff state 更新为 completed/failed。
- `agent_delegate_task` 仍保持 agents-as-tools/subrun 语义，并与 ownership handoff 在 metadata/record 中分开。
- Desktop Sessions 列表会显示 `接管: target` 标记；详情面板会显示 ownership、handoff status、context snapshot、handoff id、reason 和 summary。
- `risk_specialist`、`research_specialist`、`ops_specialist` 已有基础 handoff policy；policy 会注入 `handoff_specialist_policy` system message，记录 requested/effective toolset，并按已注册 preferred tools 过滤本轮 model-visible tool schemas。
- Desktop Sessions 刷新时会读取 handoff queue；点击继续会话会先读取 resume context，并把 `resume_prompt` 传给 Workbench 作为带 context_snapshot_id 的继续提示。

仍需继续：

- specialist policy 仍是内置基础矩阵，后续应扩展为配置化 target -> prompt/toolset/tool allowlist，并纳入 trace/eval。
- handoff queue 目前在 Sessions 页面显示摘要，后续应升级为独立队列视图、批量筛选和失败恢复面板。

### P1 已修：上下文理解已有 durable context snapshot

证据：

- `ContextManager` 生成 `context_summary`：`packages/agent/src/aiask_agent/context.py:65`
- runtime 在压缩时追加 system message：`packages/agent/src/aiask_agent/runtime.py:246`
- `context_references` 可读项目文件和 `@file`/`@url` 并沉淀 source/artifact。
- `context_snapshots` 表已落地：`packages/agent/src/aiask_agent/session_store.py:341`
- `record_context_snapshot()` 持久化 API 已落地：`packages/agent/src/aiask_agent/session_store.py:1926`
- runtime 在 context prepare 后写入 `context.snapshot_created` 事件：`packages/agent/src/aiask_agent/runtime.py:306`
- `AgentRunResult` 返回 `context_snapshot_id`：`packages/agent/src/aiask_agent/runtime.py:59`

已修：

- `record_context_snapshot()` 记录 snapshot_id、session_id、run_id、trace_id、context_summary_id、source_message_ids、source_ids、artifact_ids、压缩策略、token 估算、summary_model、risk_flags 和 metadata。
- runtime 对 `lossy_compression`、`unresolved_reference`、`token_estimate_not_reduced` 生成风险标记。后者暴露了当前压缩策略在“单条超长用户消息”场景下可能不减 token 的真实质量问题。
- 快照已经纳入用户数据导出、删除/匿名化、retention payload 清理路径，避免形成新的隐性敏感数据桶。

仍需继续：

- 后续应优化 `ContextManager` 的超长单消息压缩策略，并用 snapshot risk flags 做 eval 输入。
- 长任务 replay/eval 还需要把 resume context、handoff queue 和 trace grading 串成可视化验收面板。

### P1 部分已修：工具合同已有 formal annotations 和 domain outputSchema

证据：

- 工具 catalog 使用 `side_effect`、`category`、`capability`。
- 风险归一化在 `packages/agent/src/aiask_agent/tool_risk.py:173`。
- `tools/contracts.py` 已生成 `annotations`、AIASK envelope `outputSchema` 和 domain-specific data schemas：`packages/agent/src/aiask_agent/tools/contracts.py:39`
- `domain_output_schema()` 会为 high-value 工具选择行情、新闻、市场温度、组合风险、量化研究、策略复核、交易预测、股票雷达、ActionIntent 等 data schema：`packages/agent/src/aiask_agent/tools/contracts.py:289`
- `catalog_for_toolset()` 会返回已 enrich 的工具合同：`packages/agent/src/aiask_agent/tools/catalog.py:973`
- `AgentToolRegistry.register()` 会对静态、native、MCP、plugin 工具统一 enrich metadata：`packages/agent/src/aiask_agent/tool_registry.py:69`
- HTTP tools catalog 明确透传 `annotations` / `outputSchema`：`packages/agent/src/aiask_agent/routes/tools_catalog.py:12`
- 回归测试覆盖内置工具和 MCP wrapped 工具合同：`packages/agent/tests/test_tool_registry.py:56`

已修：

- 所有 catalog/registry 工具都会有 `annotations.readOnlyHint`、`destructiveHint`、`idempotentHint`、`openWorldHint`。
- AIASK 扩展字段 `requiresApproval`、`tradeRisk` 会从 `side_effect`、category/name 风险词和 confirmation metadata 推导。
- 未提供专用 `output_schema` 的工具会得到通用 `success/data/error/meta` envelope `outputSchema`；MCP 工具自带的 `output_schema` 会被保留并镜像为 `outputSchema`。
- `agent_stock_live_quote`、`agent_stock_news_digest`、`agent_market_temperature_*`、`agent_portfolio_risk`、`agent_quant_research_run`、`agent_strategy_review_snapshot`、`agent_trade_prediction_*`、`agent_stock_radar_*`、`agent_action_intent_*` 已有更具体的 `data.properties`。
- `agent_tool_catalog`、registry metadata、HTTP catalog 已经看到同一份基础合同。

仍需继续：

- 把 broker-readonly HTTP 响应、artifact/source API 响应也提升到同等 formal response schema，而不只是模型可见 tool catalog。
- 继续补齐更窄的 per-tool required fields 和版本化 schema 测试。
- Desktop 工具目录还需要把 annotations 作为用户可见的风险/交互提示展示出来。

### P2 已修：状态探针和执行路径已有显式分类 gate

当前仍存在一些直接 `tool_registry.call_tool()`，但已被显式分类为 audited runtime loop、audited server helper、audited Python RPC child tool、internal readiness probe、Desktop read-only status/snapshot、simple HTTP read-only fallback。

已修：

- 新增 `docs/architecture/tool-call-path-classification.json`，逐项记录当前直连调用的分类和原因。
- 新增 `packages/agent/tests/test_tool_call_path_gate.py`，从 AST 抽取当前源码里的直接 `tool_registry.call_tool()` 路径，并要求分类文件完全覆盖；新增未分类直连调用会失败，删除路径后分类不清理也会失败。
- `_financial_query_payload()`、`_financial_intent_payload()` 的无注入 fallback 已改为 `_audited_runtime_tool_call()`：`packages/agent/src/aiask_agent/server.py:2084`
- full-mode mutation helper `full_tool_call()` 已改为 `_audited_runtime_tool_call()`：`packages/agent/src/aiask_agent/server.py:2423`

仍需继续：

- 当前分类保留了部分 Desktop 只读状态读和 fallback HTTPServer 只读读；如果这些路径升级为用户执行或外部副作用，必须迁入 audited helper 或 ActionIntent。
- 后续 Desktop 时间线仍需把 user_activity_event -> tool_invocation -> run_event -> source/artifact/intent 做更完整的可视化聚合。

## 5. 本轮已落地修复

### 5.1 Artifact 内容读取越权防护

问题：artifact 记录若指向 workspace 外路径，即使 evidence 阶段标记为 blocked，内容 API 仍可能基于 DB record 读取磁盘。

修复：内容 API 在读取前检查 blocked/denied、`metadata.read_allowed`、以及 `_path_allowed_for_artifact_read`。blocked artifact 返回 `encoding: "blocked"`。

测试：`packages/agent/tests/test_evidence_artifacts_sources.py`

### 5.2 Desktop evidence 面板从推断产物改为 durable artifacts/sources

问题：TaskPanels 里旧逻辑混合 thread/response/run 推断产物与 durable artifacts，容易让 UI 展示“看起来像证据但不是 Agent 证据账本”的内容。

修复：`buildTaskArtifacts()` 只从 Agent artifact API 的 durable records 构建；sources 单独通过 `SourcesPanel` 展示。

测试：`desktop/src/components/WorkbenchView.test.tsx`

### 5.3 用户触发工具路径统一审计

新增：

- `_tool_payload_with_request_context()`：`packages/agent/src/aiask_agent/server.py:350`
- `_audited_runtime_tool_call()`：`packages/agent/src/aiask_agent/server.py:360`

接入：

- `/v1/desktop/financial-manager/query`
- `/v1/desktop/financial-manager/intent`
- `/v1/desktop/broker/sync`
- `/v1/desktop/quant/research-runs`
- `/intents`
- `/v1/tools/{tool_name}` 和 `/v1/hermes/admin/tools/{tool_name}` 继续统一审计

新增/扩展测试：

- broker-readonly 同步会记录 3 个只读 broker 查询 invocation。
- financial-manager query/intent 会记录 invocation，并关联 `action_intent_id`。
- `/intents` 会记录 `agent_action_intent_create` invocation。
- quant research route 会记录 `agent_quant_research_run` invocation。

### 5.4 Durable context snapshot 与协作链路

新增：

- `context_snapshots` 表和 `record_context_snapshot()` / `list_context_snapshots()`。
- `AgentRunResult.context_snapshot_id`。
- `context.snapshot_created` run event。
- handoff request metadata 记录 `handoff_kind=ownership_transfer` 和 `context_snapshot_id`。
- delegation subrun record 记录 parent/child context snapshot。

新增/扩展测试：

- `test_session_memory_todo.py` 覆盖 snapshot 持久化、导出、匿名化和 retention payload 清理。
- `test_extended_agent_capabilities.py` 覆盖 runtime context snapshot、context references snapshot、delegation snapshot 链路、handoff snapshot 链路。

### 5.5 Desktop handoff ownership 可见性

新增：

- `/v1/hermes/sessions` 会在 session metadata 存在 handoff 状态时返回正式摘要字段：`handoff_state`、`handoff_status`、`handoff_target`、`handoff_id`、`handoff_context_snapshot_id`、`active_agent`、`active_context_snapshot_id`。
- `RecentSessionSummary` 增加 `SessionHandoffState` 类型，Desktop 不再需要从任意 metadata 字段猜测交接状态。
- Mock API 增加 active handoff 样本，覆盖接管 Agent、handoff id、source run/tool call 和 context snapshot。
- Sessions 页面列表显示 `接管: risk_specialist`，详情面板显示任务接管、交接状态、上下文快照、交接原因和摘要。
- 搜索可匹配 handoff target、active agent、handoff id、context snapshot id。

新增/扩展测试：

- `packages/agent/tests/test_desktop_workbench_contracts.py` 覆盖 `/v1/hermes/sessions` handoff ownership 字段。
- `desktop/src/features/agent-pages/SessionsPage.test.tsx` 覆盖 Desktop handoff ownership 和 context snapshot 展示。

### 5.6 Specialist handoff policy routing

新增：

- `HANDOFF_SPECIALIST_POLICIES` 定义 `risk_specialist`、`research_specialist`、`ops_specialist` 的基础角色、requested toolset、preferred tools 和专家指令。
- runtime 消费 pending handoff 后，会创建 `handoff_specialist_policy` system message，明确 target、policy_id、role、effective_toolset、context_snapshot_id、preferred_tools、advertised_tools 和 instructions。
- 本轮模型调用使用 handoff policy 过滤后的 `active_model_tools`，让 target 不只是 metadata，而是实际影响模型可见工具面。
- `handoff.policy_applied` run event 记录 policy_id、requested/effective toolset、preferred_tools、advertised_tools 和 filtered 状态。
- context snapshot metadata 记录 `handoff_policy`，让后续 replay/eval 能知道当时采用了哪个专家策略。

新增/扩展测试：

- `test_runtime_consumes_pending_session_handoff_state_on_next_turn` 覆盖 policy event 和 system message 注入。
- `test_handoff_specialist_policy_filters_advertised_tools` 覆盖 risk specialist 在 general_full registry 下只广告风险相关工具，不广告 `agent_file_read` 等 general tools，并把 policy 写入 context snapshot metadata。
- `test_runtime_resumes_active_handoff_state_on_later_turn` 覆盖后续同 session 继续时的 `handoff.resumed`、handoff state/system policy 再注入和 snapshot metadata。

### 5.7 Handoff queue 与 snapshot-aware resume

新增：

- runtime 后续同 session run 会读取 active `handoff_state`，发出 `handoff.resumed`，并再次注入 handoff state 与 specialist policy。
- `/v1/hermes/handoffs` 返回 handoff queue，补齐 `runtime_status`、`active_agent`、`resume_context_snapshot_id`、`resume_ready` 和 summary。
- `/v1/hermes/sessions/{session_id}/resume-context` 返回 session summary、handoff runtime record、context snapshot、risk_flags、source/artifact ids 和 `resume_prompt`。
- Desktop `AiaskApi` 增加 `handoffsList()` 与 `sessionResumeContext()`。
- Desktop Sessions 页面刷新时读取 handoff queue，点击继续会话时先读取 resume context，再把 snapshot-aware prompt 传给 Workbench。

新增/扩展测试：

- `test_hermes_handoff_queue_and_resume_context_contract` 覆盖队列授权、active runtime_status、resume_context_snapshot_id、risk_flags、source_ids 和 resume_prompt。
- `SessionsPage.test.tsx` 覆盖交接队列展示、继续会话携带 resume context、恢复上下文面板。

### 5.8 Formal tool contract annotations 与 domain outputSchema

新增：

- `tools/contracts.py` 统一生成 `annotations`、`outputSchema`、`contract_version`、`contract_source`。
- 静态 catalog、registry metadata、MCP wrapped tools、HTTP tools catalog 共用同一基础合同。
- 高价值模型可见工具会获得 domain-specific `data` schema，包括 quote/news/market-temperature/portfolio-risk/quant-research/strategy-review/trade-prediction/stock-radar/ActionIntent。
- 未来 artifact/source 命名工具预留 evidence records schema 分支；MCP/provider 自带 `output_schema` 仍优先保留。

新增/扩展测试：

- `test_tool_registry.py` 覆盖 finance-safe catalog 每个工具的 annotations/outputSchema。
- `test_tool_registry.py` 断言 quote/news/market/risk/intent 的 `outputSchema.properties.data.properties` 含有 domain 字段。
- MCP wrapped tool 保留 provider `output_schema`，同时补齐 `outputSchema` 和 read-only/open-world annotations。

### 5.9 Direct tool call classification gate

新增：

- `docs/architecture/tool-call-path-classification.json` 作为直接 `tool_registry.call_tool()` 路径分类账本。
- `packages/agent/tests/test_tool_call_path_gate.py` 作为漂移 gate。
- server fallback 的 Financial Manager query/intent 和 full-mode mutation helper 改为统一 audited helper。

分类范围：

- runtime 主工具循环和 Python RPC 子工具：audited execution。
- `_audited_runtime_tool_call()`：server audited helper。
- financial readiness / Desktop capabilities / trade prediction / stock radar：只读 readiness/status。
- fallback HTTPServer GET：只读 fallback。

## 6. 建议路线图

### P0：完成所有用户触发执行路径的统一账本

1. 建立工具调用路径分类表。
2. 所有 POST 或外部读取 endpoint 必须接入 `_audited_runtime_tool_call()` 或声明为内部 probe。
3. `run_events`、`tool_invocations`、`sources`、`artifacts` 在 Desktop 同一时间线聚合。

验收标准：

- 任何 Desktop 用户动作都能追踪到 user_activity_event -> tool_invocation -> run_event -> source/artifact/intent。
- 直接新增 `tool_registry.call_tool()` 的 PR 如果没有分类说明，测试失败。

### P1：把 handoff 从记录升级为运行时状态机

1. 增加 active/last agent state：已完成基础 session metadata。
2. delegation 与 handoff 分开建模：已在 metadata/record 中区分 `delegation_subrun` 与 `ownership_transfer`。
3. handoff 目标 agent 接管下一轮上下文：已完成 pending -> active 消费、system message 注入和基础 specialist prompt/tool schema routing。
4. subrun/handoff 与 artifacts/sources/run_events 统一链路：已初步记录 parent/child context snapshot，Desktop ownership/context snapshot 展示已落地，snapshot-aware resume 与 handoff queue 基础契约已完成。
5. specialist policy 矩阵配置化：仍需继续，把内置策略升级为可配置 target -> prompt/toolset/tool allowlist/eval rubric。
6. handoff queue 产品化：仍需继续，加入独立队列页、失败/超时筛选和恢复操作。

验收标准：

- 能回答“当前任务由谁拥有，为什么转交，接收方拿到了哪个 context snapshot，下一轮谁继续”。

### P1：上下文快照和恢复

1. 增加 durable context snapshot：已完成。
2. context summary 记录输入范围、引用、模型、token、风险：已完成基础账本。
3. handoff/subrun 引用 snapshot id：已完成基础链路；session resume context 已显式返回 snapshot_id、risk_flags、source_ids、artifact_ids 和 resume_prompt。
4. 建立长任务 replay/eval 测试。

验收标准：

- 任一长任务中断后，可从 session/run/snapshot/source/artifact 复建足够上下文。

### P1：工具合同正式化

1. 为 `agent_*` catalog 生成 formal annotations。
2. 高风险/高价值模型可见工具补 outputSchema：基础 domain schema 已完成；per-tool required fields 和 HTTP response schema 仍需继续。
3. MCP wrapped tool metadata 映射到 AIASK 工具合同。
4. Desktop 工具目录显示 readOnly/destructive/idempotent/openWorld/approval/tradeRisk。

验收标准：

- 模型、Desktop、审计和外部协议看到同一份工具合同。

### P2：系统级 trace/eval

1. trace spans 覆盖 model/tool/handoff/guardrail/context/artifact。
2. 增加 trace grading：工具是否选对、证据是否足够、guardrail 是否触发、上下文是否丢失。
3. Desktop readiness 页面显示 trace health。

验收标准：

- 系统不只会执行，还能评价自己是否协调地执行。

## 7. 验证记录

已运行并通过：

```text
python -m py_compile packages\agent\src\aiask_agent\server.py packages\agent\src\aiask_agent\broker_readonly.py packages\agent\src\aiask_agent\evidence.py
uv run pytest packages/agent/tests/test_broker_readonly_api.py packages/agent/tests/test_financial_manager_desktop_api.py packages/agent/tests/test_tool_registry.py -q
19 passed

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py -q
8 passed

uv run pytest packages/agent/tests/test_evidence_artifacts_sources.py -q
5 passed

uv run pytest packages/agent/tests/test_extended_agent_capabilities.py -q
18 passed

python -m py_compile packages\agent\src\aiask_agent\session_store.py packages\agent\src\aiask_agent\runtime.py

uv run pytest packages/agent/tests/test_session_memory_todo.py -q
6 passed

uv run pytest packages/agent/tests/test_extended_agent_capabilities.py -q
20 passed

uv run pytest packages/agent/tests/test_hermes_full_expanded_capabilities.py -q
6 passed

python -m py_compile packages\agent\src\aiask_agent\tools\contracts.py packages\agent\src\aiask_agent\tools\catalog.py packages\agent\src\aiask_agent\tool_registry.py packages\agent\src\aiask_agent\routes\tools_catalog.py

uv run pytest packages/agent/tests/test_tool_registry.py -q
10 passed

uv run pytest packages/agent/tests/test_desktop_capabilities_api.py -q
7 passed

uv run pytest packages/agent/tests/test_server.py -q
7 passed

python -m py_compile packages\agent\src\aiask_agent\server.py packages\agent\tests\test_tool_call_path_gate.py

uv run pytest packages/agent/tests/test_tool_call_path_gate.py -q
1 passed

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_tool_registry.py -q
17 passed

uv run pytest packages/agent/tests/test_financial_manager_desktop_api.py packages/agent/tests/test_desktop_workbench_contracts.py -q
14 passed

python -m py_compile packages\agent\src\aiask_agent\session_store.py packages\agent\src\aiask_agent\native_capabilities.py packages\agent\src\aiask_agent\runtime.py

uv run pytest packages/agent/tests/test_extended_agent_capabilities.py -q
21 passed

uv run pytest packages/agent/tests/test_hermes_full_expanded_capabilities.py -q
6 passed

uv run pytest packages/agent/tests/test_session_memory_todo.py packages/agent/tests/test_extended_agent_capabilities.py -q
27 passed

python -m py_compile packages\agent\src\aiask_agent\runtime.py packages\agent\tests\test_extended_agent_capabilities.py

uv run pytest packages/agent/tests/test_extended_agent_capabilities.py -q
22 passed

uv run pytest packages/agent/tests/test_hermes_full_expanded_capabilities.py packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_tool_call_path_gate.py -q
16 passed

python -m py_compile packages\agent\src\aiask_agent\tools\contracts.py packages\agent\tests\test_tool_registry.py

uv run pytest packages/agent/tests/test_tool_registry.py -q
10 passed

uv run pytest packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_server.py -q
14 passed

python -m py_compile packages\agent\src\aiask_agent\server.py

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py -q
9 passed

cd desktop; npx vitest run src/features/agent-pages/SessionsPage.test.tsx --environment jsdom
10 passed

python -m py_compile packages\agent\src\aiask_agent\runtime.py packages\agent\tests\test_extended_agent_capabilities.py

uv run pytest packages/agent/tests/test_extended_agent_capabilities.py -q
23 passed

python -m py_compile packages\agent\src\aiask_agent\server.py packages\agent\tests\test_desktop_workbench_contracts.py

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py -q
10 passed

cd desktop; npx vitest run src/features/agent-pages/SessionsPage.test.tsx --environment jsdom
11 passed

cd desktop; npm run typecheck

uv run pytest packages/agent/tests/test_extended_agent_capabilities.py packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_tool_call_path_gate.py -q
34 passed

git diff --check
# only warning: CRLF replacement in unrelated packages/strategy-factory/tests/test_inject_run_correction_metrics.py
```

前序已通过：

```text
python -m py_compile packages\agent\src\aiask_agent\server.py packages\agent\src\aiask_agent\evidence.py
uv run pytest packages/agent/tests/test_evidence_artifacts_sources.py -q
cd desktop; npm run typecheck
cd desktop; npx vitest run src/components/WorkbenchView.test.tsx --environment jsdom
```

## 8. 当前完成度判断

本轮已经把最容易导致“Agent 发生了动作但系统账本不知道”的用户触发路径补上，把 Python 内部 RPC 子工具补进审计链路，把证据展示从推断 UI 转向 durable evidence，把上下文准备过程沉淀为 durable context snapshot，让 Desktop 能看见 handoff ownership 与 active context snapshot，让 handoff target 实际影响下一轮专家 prompt 与 model-visible tool schemas，并补上 snapshot-aware resume / handoff queue 的基础 HTTP 与 Desktop 契约。AIASK 的协调水平向系统级 Agent 迈进了一步。

但目标还未完全完成。要真正达到系统级协调，还需要继续完成：

- handoff queue 独立视图、失败恢复操作和长任务 replay/eval。
- specialist policy 配置化、评估化和更多目标覆盖。
- broker-readonly HTTP、artifact/source API 的 formal response schema，以及更窄 per-tool required fields。
- trace/eval 面板。

这些工作完成后，AIASK 才能从“功能很全的 Agent 系统”升级为“状态、证据、权限、上下文和多 Agent 协作都一致的系统级 Agent”。
