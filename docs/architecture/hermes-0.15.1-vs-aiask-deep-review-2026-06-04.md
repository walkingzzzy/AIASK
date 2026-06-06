# Hermes 0.15.1 vs AIASK 深度对比审查

Date: 2026-06-04

## 审查基线

- Hermes 对比基线采用本地 `vendor/hermes-agent-upstream` 当前快照，HEAD 为 `7402706c5`，版本声明为 `0.15.1`。证据见 `vendor/hermes-agent-upstream/pyproject.toml:10`、`vendor/hermes-agent-upstream/hermes_cli/__init__.py:17`。
- AIASK 当前 Hermes 参考基线已统一为 `0.15.1` / `7402706c5`；`v0.14_delta` 仅保留为历史能力分层。证据见 `packages/agent/src/aiask_agent/capabilities.py:5-11,631-662`。
- Hermes 在 AIASK 仓库内仍是参考实现，不允许被嵌入、import、shell out 或 sidecar 运行。证据见 `docs/architecture/hermes-boundary.md:7-14,46-55`。
- parity 文档已声明当前追踪 vendored Hermes `0.15.1`，并保留 `v0.14_delta` 作为历史分层。证据见 `docs/architecture/hermes-financial-product-parity.md:1-12`。

本次审查只使用非变更式证据：关键入口代码、前后端接口面、桌面 API 调用面、现有测试护栏，以及 `reports/code-graph/full-2026-05-29/curated/*` 中的 endpoint / graph 摘要。

## 1. 关键审查结论

### 1.1 AIASK 的 Hermes 兼容基线已经实质性落后，而且漂移不只在文档层

这不是简单的版本字符串没更新，而是后端能力账本、前端 mock/test 契约、以及 parity 文档三处一起漂移。

- AIASK 后端 Hermes 基线已是 `0.15.1` / `7402706c5`：`packages/agent/src/aiask_agent/capabilities.py:5-7,631-634`
- parity 文档已对齐 vendored Hermes `0.15.1`，并说明 `v0.14_delta` 为历史层：`docs/architecture/hermes-financial-product-parity.md:5-8`
- 前端测试和 mock e2e 已更新当前 baseline；`v014_delta` 内部仍保留 `v2026.5.16` 历史标签。
- 前端 mock 的 “Hermes full parity” 叙述不再作为当前 baseline 来源。

判断：这是当前最明确的审查问题。它会直接降低 `/v1/hermes/status`、桌面诊断面板、以及后续 Hermes 借鉴评估的可信度。

### 1.2 AIASK 当前的 `/v1/hermes/*` 不是“假壳”，但它更像原生管理/诊断面，而不是 Hermes 式完整 Agent 平台

AIASK 的 `/v1/hermes/*` 已经接到真实 runtime、tool registry、gateway、plugin、MCP、terminal/process 等原生能力上，不是纯 mock。

- `/v1/hermes/status` 直接声明 `implementation: "aiask_native"` 和 `embedded_vendor_runtime: False`：`packages/agent/src/aiask_agent/server.py:1729-1743`
- `/v1/hermes/toolsets`、`/v1/hermes/tools`、`/v1/hermes/config`、`/v1/hermes/sessions` 都是活接口：`packages/agent/src/aiask_agent/server.py:1786-1816`
- Full mode 还进一步暴露了 tools admin、processes、terminal backends、browser sessions、skills、plugins、gateway、connectors、learning、RL、MCP 管理接口：`packages/agent/src/aiask_agent/server.py:1967-2445`
- 桌面端 `fullConsoleSnapshot()` 会聚合 `/v1/hermes/status`、`/v1/hermes/tools`、`/v1/plugins`、`/v1/mcp/servers?all=true`、`/v1/gateway/status` 等控制面接口：`desktop/src/services/aiaskApi.ts:85-86,130-193`

但从产品形态看，AIASK 仍主要把这些能力组织成 “full console / diagnostics / capabilities workspace”，而不是像 Hermes 那样围绕 session、chat、logs、config、plugin page、ops workflow 形成一个一致的平台操作闭环。

判断：AIASK 的 `/v1/hermes/*` 是“真实能力 + 兼容管理面”，不是“纯兼容壳”；真正偏弱的是产品化承载和信息架构。

### 1.3 Hermes 0.15.1 相比 AIASK 的主要优势，不在金融深度，而在 Agent 操作闭环与平台化完成度

Hermes dashboard 的强项很明确：

- 页面组织已经围绕 `sessions`、`logs`、`analytics`、`skills`、`plugins`、`mcp`、`channels`、`webhooks`、`profiles`、`config`、`env`、`system`、`docs` 展开：`vendor/hermes-agent-upstream/web/src/App.tsx:68-142,152-189`
- dashboard 是插件 slot aware 的，支持 `PluginPage`、`PluginSlot`、`usePlugins()` 和动态路由拼装：`vendor/hermes-agent-upstream/web/src/App.tsx:89,271-331,339,476,523,559,671,702,713,763,769`
- 插件 SDK 已经公开到 `window.__HERMES_PLUGIN_SDK__`，包含 `sdkVersion`、`registerSlot`、`authedFetch`、`buildWsUrl` 等宿主能力：`vendor/hermes-agent-upstream/web/src/plugins/registry.ts:95-113,159`
- Chat 页面采用持久挂载的 PTY + xterm + session resume 模式，dashboard 与 TUI 被真正连成一个会话面：`vendor/hermes-agent-upstream/web/src/App.tsx:115-123,386-403,735-760`，`vendor/hermes-agent-upstream/web/src/pages/ChatPage.tsx:19-24,41,124-145,174-195,570-607`
- web server 已经是完整 ops surface，覆盖 sessions、logs、MCP、PTY、dashboard plugins：`vendor/hermes-agent-upstream/hermes_cli/web_server.py:1515-1535,4790-4810,5093-5115,7331-7352,8147-8415`

而 AIASK 桌面端更像高密度金融工作台：

- `App.tsx` 直接承载 `agent`、`automation`、`capabilities`、`coverage`、`data`、`financial-manager`、`quant`、`workflows`、`factor-factory`、`incubation`、`event-console` 等大量 domain workspace：`desktop/src/App.tsx:9-25,245-379`
- 当前 `desktop/src/features` 有 21 个 feature 目录，而 Hermes `web/src/pages` 是 17 个页面文件。前者更偏“领域工作台”，后者更偏“Agent 平台控制台”。

判断：AIASK 当前更强的是“金融工作台密度”；Hermes 更强的是“Agent 操作闭环、插件化、运维与配置产品化”。

### 1.4 AIASK 当前最值得保护的长板，不是 Hermes 有而 AIASK 没有的部分，而是金融安全边界和工厂链路深度

AIASK 的强项已经形成自己的架构护城河：

- Model-visible 工具统一被 `ensure_agent_tool_name()` 压到 `agent_*` 名字空间：`packages/agent/src/aiask_agent/tool_registry.py:24,51-67`
- 默认 toolset 是 `finance_safe`，`general_full` 需要显式环境开关：`packages/agent/src/aiask_agent/tool_registry.py:193-214,520-566`
- Stateful 金融 MCP 动作默认不会被直接执行，而是要求 `agent_action_intent_create` 或直接阻断：`packages/agent/src/aiask_agent/tool_registry.py:567-607`
- 这一点有专门测试护栏：`packages/agent/tests/test_hermes_reference_guardrails.py:50,70,79`
- endpoint drift 也有显式解释 gate：`packages/agent/tests/test_endpoint_drift_gate.py:36,43`

判断：凡是会稀释 `finance_safe -> action_intent -> confirmation` 这条链的 Hermes 设计，都不应直接照搬。AIASK 不能为了“更像 Hermes”而退化为通用 Agent 平台。

### 1.5 AIASK 的插件运行时已经能用，但与 Hermes 0.15.1 相比仍停留在“runner 封装层”，不是“平台扩展层”

AIASK 的 `NativePluginManager` 已经具备：

- `plugin.json` 扫描与启停：`packages/agent/src/aiask_agent/plugin_runtime.py:25-80`
- tool / command 包装为 `agent_plugin_*`：`packages/agent/src/aiask_agent/plugin_runtime.py:92-132`
- hooks、pre/post tool、pre/post llm、session hooks、terminal output transform：`packages/agent/src/aiask_agent/plugin_runtime.py:190-350`
- `python_module`、`http`、`subprocess` runner：`packages/agent/src/aiask_agent/plugin_runtime.py:366-430`

但它和 Hermes 0.15.1 的差距也很清楚：

- Hermes 是 `plugin.yaml + register(ctx)` 的宿主式插件模型：`vendor/hermes-agent-upstream/hermes_cli/plugins.py:19-32,289-357`
- Hermes 有更完整的 hook 集、source discovery、entry point discovery、kind 分类、enable/disable 策略、provider 语义和 dashboard plugin hub：`vendor/hermes-agent-upstream/hermes_cli/plugins.py:128-172,1007-1190,1202-1372,1537-1585`
- Hermes dashboard 还能把插件页面、导航、slots、宿主 API 串成完整 UI 扩展协议：`vendor/hermes-agent-upstream/web/src/App.tsx:271-331,615-645`，`vendor/hermes-agent-upstream/web/src/plugins/registry.ts:95-113`

判断：AIASK 近期最该借鉴的是 Hermes 的“slot/page 生命周期与可观测性设计”，不是直接引入外部 dashboard JS 插件执行模型。

### 1.6 AIASK 的前后端覆盖面已经不小，但 UI/API 覆盖错位和 mock 漂移风险正在积累

仓库内现成 endpoint map 工件显示：

- endpoint 总数 117
- desktop/server 已匹配 62
- server only 42
- desktop only 13

证据见 `reports/code-graph/full-2026-05-29/curated/endpoint-map.json`。

这不等于 42 个“缺失功能”，但它说明两件事：

1. 后端已经长出了大量管理面和运维面接口，桌面承载并不均匀。
2. 前端里有一部分兼容/coverage/mocks 叙述没有随真实 runtime 同步演化。

这点也可以从桌面核心 API 客户端体量看出来：`desktop/src/services/aiaskApi.ts` 已经 844 行，而桌面入口 `desktop/src/App.tsx` 463 行；说明 API 聚合和 UI 编排都开始承压。Hermes 也大，但它是围绕统一 dashboard IA 展开的：`vendor/hermes-agent-upstream/web/src/App.tsx` 1099 行，`vendor/hermes-agent-upstream/hermes_cli/web_server.py` 7546 行。

## 2. 值得借鉴的清单

### 高优先级（1-4 周内可落地）

| 借鉴点 | 落点 | 适合 AIASK 的原因 | 近期是否可落地 |
| --- | --- | --- | --- |
| 先把 Hermes 基线、parity 文档、桌面 mock/test 从 `0.14.0` 刷到 `0.15.1` | 前端 + 后端 + 测试 + 文档 | 成本最低，但能立刻消除“我们到底在对齐谁”的认知噪音，也能让后续借鉴项有可信基线 | 是，1 周内 |
| 把当前 workbench 演进成“session-first 的 Agent 控制台” | 前端 + 产品 | Hermes 最强的是 persistent chat、session resume、run state 连贯性。AIASK 已有 thread/workbench/run events 基础，缺的是围绕 session 的主路径组织 | 是，2-4 周 |
| 参照 Hermes 的页面分层，把 logs / gateway / MCP / plugins / skills / readiness 做成更清晰的一组管理页 | 前端 + 后端 + 产品 | AIASK 后端接口已经大多存在，主要差在 IA 和可操作性，不需要先做大规模 runtime 重构 | 是，1-3 周 |
| 在桌面端引入 AIASK-native 的 slot/page 扩展点，而不是继续把 plugin 面板做成只读注册表 | 前端 + 插件体系 | Hermes 的 `PluginPage` / `PluginSlot` 很成熟。AIASK 可先做“内部受控扩展点”，提升能力承载，而不直接执行外部 JS | 是，2-4 周 |

高优先级说明：

- 这里最值得马上做的不是“做个更像 Hermes 的皮肤”，而是把 AIASK 已有真实后端能力重新组织成更强的 Agent 操作闭环。
- 第一项虽然看起来像 housekeeping，但实际上是后续所有设计判断的前提。

### 中优先级（平台化增强，但不宜压过金融主链）

| 借鉴点 | 落点 | 适合 AIASK 的原因 | 近期是否可落地 |
| --- | --- | --- | --- |
| 升级插件契约：从 `plugin.json + runner` 向“manifest + typed hooks + readiness + install/update state”靠拢 | 后端 + 插件体系 | AIASK 当前插件能执行，但对生命周期、provider 语义、配置健康度和 UI 承载支持较薄 | 部分可落地，3-6 周 |
| 借鉴 Hermes dashboard plugin hub / provider selection 的管理思路 | 后端 + 前端 + 产品 | 对 skills / plugins / MCP / connector 的统一配置与健康展示很有帮助，尤其适合 full mode 运维 | 部分可落地，3-6 周 |
| 如果 AIASK 后续提供远程 web dashboard，可借鉴 Hermes 的 base-path、session token、WS ticket、401 reload 策略 | 后端 + 前端基础设施 | Hermes 这套 auth / ws / reverse proxy 处理非常成熟，但对当前本地 Tauri 工作台不是最急需 | 取决于 web dashboard 计划 |
| 借鉴 Hermes 的 TUI + dashboard 联动思路，但先只吸收“会话持久化与状态同步”部分 | 前端 + 后端 + 产品 | AIASK 近期真正需要的是更流畅的会话闭环，不一定要马上做完整 TUI 双界面 | 中期可落地 |

### 低优先级（谨慎处理，避免平台化过度）

| 借鉴点 | 落点 | 适合 AIASK 的原因 | 近期是否可落地 |
| --- | --- | --- | --- |
| 直接做 Hermes 式外部 dashboard JS 插件执行 | 前端 + 安全 | Hermes 有成熟 SDK，但 AIASK 金融场景里执行外部 JS 扩展的安全面太大，当前只读策略是合理的 | 不建议近期做 |
| 追求完整 Hermes CLI/TUI 双产品面复刻 | 前端 + runtime | 工程量大，而且会把注意力从金融主链路移到通用 Agent 平台上 | 不建议近期做 |
| 把大量通用 config/env/docs/product pages 原样搬入桌面 | 前端 + 产品 | 这些能力有价值，但如果先于 session 闭环和金融研究闭环落地，容易稀释主线 | 低优先级 |

明确不建议直接移植的部分：

- 直接 import / embed / sidecar-run vendored Hermes runtime
- 在桌面端执行外部 Hermes dashboard 插件 JavaScript
- 让模型直接看到 raw manager 名字或 raw stateful MCP 动作

## 3. 前端 / 后端 / 应用功能对比矩阵

### 前端对比矩阵

| 维度 | AIASK 当前实现 | Hermes 0.15.1 | 审查判断 |
| --- | --- | --- | --- |
| 页面组织 | 以金融工作台为中心，`App.tsx` 直接分发到 20+ workspace，覆盖 quant、financial-manager、factor/incubation factory、data、automation、capabilities 等：`desktop/src/App.tsx:9-25,245-379` | 以 Agent 平台运维为中心，围绕 sessions、logs、plugins、mcp、config、env、profiles、system 等页面组织：`vendor/hermes-agent-upstream/web/src/App.tsx:68-142,152-189` | AIASK 更强在领域密度；Hermes 更强在平台信息架构 |
| 会话交互 | 有 workbench、thread、inspector、run events，但 Hermes 管理面更多是 snapshot / diagnostics 拉取：`desktop/src/App.tsx:95-116,165-189,201-217`，`desktop/src/services/aiaskApi.ts:130-193` | ChatPage 持久挂载，PTY + xterm + websocket + resume 参数打通，切页不卸载会话：`vendor/hermes-agent-upstream/web/src/App.tsx:115-123,735-760`，`vendor/hermes-agent-upstream/web/src/pages/ChatPage.tsx:174-195,570-607` | 这是 AIASK 最值得借鉴的前端主线 |
| 插件承载 | 当前插件面板明确只做只读注册表，不执行外部 Hermes dashboard JS：`desktop/src/features/capabilities/PluginsPanel.tsx:134`，测试也锁住这一点：`desktop/src/features/capabilities/CapabilitiesWorkspace.test.tsx:214` | 插件可注册 route、sidebar nav、slots、宿主 API，是真正的一等 UI 扩展 | AIASK 应借鉴 slot/page 结构，但保留“受控扩展、不执行外部 JS”的安全边界 |
| 诊断与配置体验 | 有 full console、diagnostics、settings、skills、tools 等承载，但内容是“接口聚合”多于“操作路径设计” | 有 dedicated logs/config/env/system/profiles/plugins hub，操作闭环更成熟 | AIASK 可以在不改 runtime 的前提下先提升 IA 与任务路径 |
| 主界面定位 | 偏“金融工作台” | 偏“Agent 平台控制台” | 两者目标不同，不能用单一标准判优劣 |

### 后端对比矩阵

| 维度 | AIASK 当前实现 | Hermes 0.15.1 | 审查判断 |
| --- | --- | --- | --- |
| runtime / tool registry | `AgentToolRegistry`、`agent_*` 命名策略、`finance_safe` 默认、`general_full` 受控开启：`packages/agent/src/aiask_agent/tool_registry.py:24,51-67,193-214,520-566` | Hermes 是通用 Agent runtime，tool / plugin / dashboard 更深度耦合 | AIASK 在金融安全边界上更强，不能被 Hermes 的通用性冲淡 |
| `/v1/hermes/*` 能力面 | `status`、`toolsets`、`tools`、`config`、`sessions`，以及 full mode 下的大量 admin surfaces：`packages/agent/src/aiask_agent/server.py:1729-1816,1967-2445` | `/api/*` 覆盖 session、logs、analytics、config、mcp、pty、dashboard plugins 等完整平台管理面：`vendor/hermes-agent-upstream/hermes_cli/web_server.py:1515-1535,4790-4810,5093-5115,7331-7352,8147-8415` | AIASK 已有广覆盖管理 API，但缺统一产品化承载 |
| 插件体系 | `plugin.json` + runners + hook wrapper，足够做工具桥接：`packages/agent/src/aiask_agent/plugin_runtime.py:25-80,92-165,190-350,366-430` | `plugin.yaml + register(ctx)` + 多 source discovery + kinds + dashboard plugin SDK + plugin hub：`vendor/hermes-agent-upstream/hermes_cli/plugins.py:19-32,128-172,1007-1190,1202-1372,1537-1585` | Hermes 在可扩展平台层面明显更成熟 |
| Gateway / MCP | AIASK 已有 gateway status/platforms/messages/directory/retry/webhook、MCP summary/discover/oauth/resource/prompt 等原生接口：`packages/agent/src/aiask_agent/server.py:2028-2131,2338-2445` | Hermes 也有成熟的 MCP admin 与 channels / webhooks 体验 | AIASK 后端并不弱，主要差在前端闭环和运营视图 |
| Memory / session / jobs | AIASK 有 memory、session search、jobs / cron、learning、RL：`packages/agent/src/aiask_agent/tool_registry.py:281-368,373-477`，`packages/agent/src/aiask_agent/server.py:2211-2274` | Hermes 在 session lifecycle、logs、analytics、cron 页面上更强 | AIASK 的数据与 domain depth 更强，Hermes 的 ops productization 更强 |

### 应用功能对比矩阵

| 维度 | AIASK 当前实现 | Hermes 0.15.1 | 审查判断 |
| --- | --- | --- | --- |
| 金融研究闭环 | 已深度接入 AKShare MCP、quant research、strategy/factor/incubation factory、financial manager | 基本没有 AIASK 这类垂直金融闭环深度 | 这是 AIASK 的核心长板，不应被“通用平台化”稀释 |
| Agent 闭环 | 有真实 tool、memory、session、gateway、plugin、MCP、job、learning、RL 能力，但桌面主链路仍偏工作台拼装 | chat/session/logs/plugin/config 一体化更强，尤其 dashboard + TUI 联动成熟 | AIASK 近期最应补的是这里的产品闭环 |
| 扩展闭环 | 已有 skills / plugins / MCP / connectors，但 UI 与 lifecycle 相对分散 | 插件和 dashboard extension 的契约更完整 | 借鉴空间很大，但要保留金融安全控制 |
| 运维闭环 | 后端已有 readiness、gateway health、connector summary、daemon status 等接口 | 前后端都更成熟，尤其日志、认证、插件运维和 session 管理 | AIASK 值得优先补“运维可见性”，因为 backend 已经具备地基 |

## 4. 代码审查发现

### 4.1 真实问题：Hermes 基线陈旧，已经影响到后端状态面、前端测试和文档叙事

该问题已在 Hermes 0.15.1 收尾中修正，当前仅保留为历史审查记录。

- 后端基线常量已是 `0.15.1` / `7402706c5`：`packages/agent/src/aiask_agent/capabilities.py:5-7`
- parity 文档已以 Hermes `0.15.1` 为准，并保留 `v0.14_delta` 历史层：`docs/architecture/hermes-financial-product-parity.md:5-8`
- 前端测试与 mock e2e 已断言当前 baseline，旧 `v2026.5.16` 只出现在 `v014_delta`。

影响：

- 误导桌面端和审查者对当前 Hermes 参考面的理解
- 容易把真实能力差距与旧基线差距混在一起
- 让后续借鉴优先级判断失真

### 4.2 真实问题：AIASK 已有大量 Hermes-class API，但桌面信息架构仍把它们压在“诊断快照”后面

`fullConsoleSnapshot()` 已经能拉很多真实控制面数据：`desktop/src/services/aiaskApi.ts:130-193`。但当前桌面主结构仍是 workspaces + diagnostics 的混合型布局：`desktop/src/App.tsx:245-379`。

这带来的问题不是“没有能力”，而是：

- 用户不容易理解哪些是日常 Agent 主路径，哪些是运维/诊断路径
- logs / gateway / MCP / plugins / skills 等能力被作为“控制台内容”而不是一等操作对象
- AIASK 明明已经有很强的后端 surface，却还没有把它们转成成熟的平台交互

### 4.3 真实问题：插件层明显存在“运行时能桥接，产品层不能承载”的断层

AIASK 插件运行时对 tool / hook / runner 已经够用，但它并没有形成像 Hermes 那样的统一 plugin lifecycle 和 dashboard 承载。

- AIASK 侧仍更像“manifest + runner + wrapper”系统：`packages/agent/src/aiask_agent/plugin_runtime.py:92-165,190-350`
- 桌面端当前还明确禁止外部 Hermes dashboard JS 执行：`desktop/src/features/capabilities/PluginsPanel.tsx:134`

这不是坏事，但它意味着如果 AIASK 接下来还想继续扩能力，当前 plugin surface 会越来越像“后台设施”，不太像“产品扩展系统”。

### 4.4 真实问题：UI/API 覆盖已经出现错位，继续靠 mock/coverage 叙述会越来越重

`reports/code-graph/full-2026-05-29/curated/endpoint-map.json` 显示当前 endpoint 对齐情况为 117 / 62 / 42 / 13。结合 `desktop/src/mockApi.ts`、`desktop/src/App.test.tsx`、`desktop/src/types.ts` 中的旧 Hermes 基线叙述，可以判断桌面兼容层和真实后端 surface 之间正在积累维护成本。

这不表示所有 server-only endpoint 都应该做成页面，但它明确提示：

- UI 覆盖策略需要更有层次
- mock 不该再承担“替代真实平台叙述”的角色
- capabilities / diagnostics / coverage 这些面板需要重新梳理边界

### 4.5 不是问题，但必须明确：AIASK 没有加载外部 Hermes dashboard JS，不应被误判为“落后”

这一点是 deliberate choice，不是缺功能。

- 插件面板明确说明“不加载或执行外部 Hermes dashboard 插件 JavaScript”：`desktop/src/features/capabilities/PluginsPanel.tsx:134`
- 对应测试也显式锁住了这条边界：`desktop/src/features/capabilities/CapabilitiesWorkspace.test.tsx:214`
- 仓库总边界文档也禁止引入 Hermes runtime：`docs/architecture/hermes-boundary.md:7-14,46-55`

对于金融产品来说，这是一条合理边界。AIASK 应该借鉴 Hermes 的扩展点设计，而不是直接复用其外部 JS 扩展执行模型。

### 4.6 不是问题，但必须明确：AIASK 没有把 raw stateful financial MCP 动作直接暴露给模型，这是正确的

Hermes 的通用平台思路和 AIASK 的金融安全边界不同，这一点不能被“功能看起来更全”覆盖。

- `strategy_manager` 类 stateful MCP action 会返回 `ACTION_INTENT_REQUIRED` 或 `MCP_STATEFUL_ACTION_BLOCKED`：`packages/agent/src/aiask_agent/tool_registry.py:577-607`
- 测试明确校验这条行为：`packages/agent/tests/test_hermes_reference_guardrails.py:50,70,79`

所以，任何 Hermes 借鉴都应建立在这一点之上：

1. 借鉴交互承载、管理面、插件扩展、可观测性。
2. 不借鉴会削弱 AIASK 金融安全门槛的 runtime 直通设计。

## 结论收束

如果只用一句话概括本次审查：

AIASK 目前并不是“能力不如 Hermes”，而是“金融能力更深、平台承载更散”；Hermes 0.15.1 最值得借鉴的不是通用工具数量，而是 session-first 的 Agent 操作闭环、slot/page 式前端扩展结构、以及 logs / plugins / MCP / config / gateway 这套成熟的运维产品化方法。

对 AIASK 最有近期价值的动作不是复刻 Hermes，而是：

1. 先把 `0.14.0 -> 0.15.1` 的基线漂移清掉。
2. 再把现有原生后端能力重新组织成更像“Agent 控制台”的前端主路径。
3. 最后再在 AIASK 自己的安全边界内，引入更成熟的插件承载与运维信息架构。
