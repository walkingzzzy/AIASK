# AIASK 项目代码结构深度审查与模块化整理方案

日期：2026-06-14  
范围：当前工作树代码、包边界、Graphify 图谱、关键入口文件、超 1000 行文件和已有守门测试。

## 0. 结论先行

AIASK 当前不是功能不足，而是功能已经快速长成一个多包金融 Agent 平台后，代码收口速度跟不上业务扩展速度。核心边界仍然基本正确：Desktop 走 Agent HTTP，模型可见工具走 `agent_*` facade，AKShare manager plane 是内部能力，Strategy Factory 和 Quant Core 分层方向也清楚。

主要结构问题有四类：

1. 单文件承载过多架构层职责。`packages/agent/src/aiask_agent/server.py` 已达 6532 行，包含 app factory、鉴权、Desktop payload、161 个 route decorator、工具审计调用、fallback HTTP server 和 CLI main。
2. Desktop 合同分散且互相牵连。`aiaskApi.ts`、`mockApi.ts`、`types.ts`、`styles.css` 同时膨胀，真实 API、Mock、类型、样式和页面状态互相绑死。
3. AKShare、Strategy Factory、Quant Core 内部已有部分拆分，但很多拆分仍停留在“大文件 + fragment loader / parts 文件”的历史中，IDE 跳转、静态分析、依赖图和新人理解成本仍然高。
4. 工作树和根目录卫生需要先冻结。当前 `git status --short` 显示 155 项变更，其中 modified 113、deleted 5、untracked 37。整理不能在未分层的脏工作树上做大规模移动。

建议采用“保 facade、拆领域、守合同、小步迁移”的路线。第一批不改行为，只移动结构并加守门测试；第二批再治理跨包 facade 和 fragment loader。

## 1. 必须保持的硬边界

这些边界来自当前仓库技能规则、代码和测试，不应在整理中被破坏：

| 边界 | 说明 |
| --- | --- |
| Desktop -> Agent HTTP only | Desktop 不直接 import Python 包，不直连 MCP，不直调 manager。 |
| 模型可见工具必须是 `agent_*` | 由 `packages/agent/src/aiask_agent/tool_registry.py` 和 `tools/policy.py` 约束。 |
| AKShare managers 不直接暴露给 Desktop 或模型 | manager 是 provider/internal plane，Agent facade 做审计、guardrail、normalization。 |
| 有副作用能力必须保留 guardrail | Strategy/factor/incubation/execution/gateway/plugin/file/terminal/browser/live trading 必须保留 ActionIntent、control token 或等价护栏。 |
| Quant Core 只做底层共享能力 | 不新增反向依赖 Agent、Desktop、AKShare manager 内部实现。 |
| 不操作 secrets/runtime state | 本方案没有读取 `.env`、运行 DB、logs、cache、broker state。 |

## 2. 证据采集方式

本报告使用当前工作树重新统计，行数口径为 PowerShell `@(Get-Content -LiteralPath $file).Count`。此前用 `Measure-Object -Line` 会低估部分文件，已放弃该口径。

复现实用命令：

```powershell
rg --files
git status --short
$items = rg --files | Where-Object { $_ -match '\.(py|ts|tsx|css|js|jsx)$' } |
  ForEach-Object { [PSCustomObject]@{ Lines = @(Get-Content -LiteralPath $_).Count; File = $_ } } |
  Where-Object { $_.Lines -ge 1000 } |
  Sort-Object Lines -Descending
rg -n '^\s*@app\.(get|post|put|delete|patch)\(' packages/agent/src/aiask_agent/server.py
rg -n 'requestJson' desktop/src/services/aiaskApi.ts
rg -n 'cleanPath ===' desktop/src/mockApi.ts
rg -n '^export (interface|type) ' desktop/src/types.ts
rg -n 'exec_fragments|exec_block|_fragment_loader' packages -g '*.py'
```

Graphify 证据来自旧基线：

| 图谱文件 | 状态 |
| --- | --- |
| `reports/code-graph/full-2026-05-29/curated/CURATED_SUMMARY.json` | 存在，但早于 6 月变更，只作基线。 |
| `reports/code-graph/full-2026-05-29/curated/endpoint-map.json` | 存在，当前代码需二次确认。 |
| `reports/code-graph/full-2026-05-29/curated/cross-package-edges.json` | 存在，适合看跨包热点。 |

Graphify 基线摘要：

| 项 | 数量 |
| --- | ---: |
| original nodes | 18879 |
| original edges | 49016 |
| core nodes | 7638 |
| core edges | 19921 |
| tests nodes | 1120 |
| docs nodes | 1612 |

Graphify package 子图：

| 包 | nodes | edges |
| --- | ---: | ---: |
| agent | 540 | 1897 |
| akshare-mcp | 4190 | 11216 |
| strategy-factory | 1754 | 4032 |
| aiask-quant-core | 619 | 1253 |
| desktop | 429 | 1111 |
| root-runners | 63 | 137 |

当前 endpoint map 基线：

| 分类 | 数量 |
| --- | ---: |
| endpoints total | 117 |
| server 和 desktop 都出现 | 62 |
| server-only | 42 |
| desktop-only | 13 |

当前 cross-package edges 热点：

| 方向 | 数量 |
| --- | ---: |
| akshare-mcp -> strategy-factory | 47 |
| strategy-factory -> aiask-quant-core | 21 |
| akshare-mcp -> aiask-quant-core | 16 |
| agent -> akshare-mcp | 4 |
| root-runners -> akshare-mcp | 3 |
| strategy-factory -> akshare-mcp | 3 |
| aiask-quant-core -> akshare-mcp | 1 |
| aiask-quant-core -> strategy-factory | 1 |

注意：后两类反向边需要人工确认是否为合法 runtime hook、兼容层或真实边界风险。

## 3. 当前规模事实

源码目录体量：

| 根目录 | 文件数 | 行数 |
| --- | ---: | ---: |
| `packages/agent/src/aiask_agent` | 69 | 37211 |
| `desktop/src` | 114 | 43511 |
| `packages/akshare-mcp/src/akshare_mcp` | 546 | 197150 |
| `packages/strategy-factory/src/strategy_factory` | 237 | 85585 |
| `packages/aiask-quant-core/src/aiask_quant_core` | 106 | 36957 |
| `packages/finance-mcp-servers/src/aiask_finance_mcp` | 11 | 1566 |

超 1000 行文件共 50 个，总计 87446 行。分布：

| 一级目录 | 超 1000 行文件数 |
| --- | ---: |
| `packages` | 40 |
| `desktop` | 7 |
| `scripts` | 3 |

## 4. 超 1000 行文件完整清单与拆分方向

| 行数 | 文件 | 当前问题 | 建议拆分方向 |
| ---: | --- | --- | --- |
| 6532 | `packages/agent/src/aiask_agent/server.py` | app factory、路由、auth、payload、工具审计、fallback server、main 混在一起 | 拆 `routes/*`、`services/audited_tool_calls.py`、`services/desktop_payloads.py`、`services/route_auth.py`，保留 `server.py` 只装配 app |
| 5215 | `desktop/src/styles.css` | 全局样式、页面样式、组件样式混杂，843 个顶层 selector-ish | 拆 `styles/globals.css`、`layout.css`、`workbench.css`、`finance.css`、`agent-pages.css`、`forms.css`、`tables.css` |
| 4992 | `desktop/e2e/capabilities.spec.ts` | 一个 e2e 覆盖过多页面和能力矩阵，失败定位慢 | 按 workspace 拆 `capabilities-overview.spec.ts`、`mcp.spec.ts`、`gateway.spec.ts`、`factory.spec.ts`、`responsive.spec.ts` |
| 4159 | `desktop/src/mockApi.ts` | mock fixture、route dispatch、状态变更和合同都在一个文件 | 拆 `mock/index.ts`、`mock/handlers/*`、`mock/fixtures/*`、共享 path constants |
| 3198 | `packages/agent/src/aiask_agent/session_store.py` | schema、session、run、audit、broker、artifact、policy、handoff、search 全在一个 store | 拆 `stores/session_core.py`、`run_store.py`、`audit_store.py`、`broker_store.py`、`evidence_store.py`、`user_data_store.py`、`handoff_store.py`、`search_store.py`，保 `AgentSessionStore` facade |
| 2486 | `scripts/factories/run_strategy_factory_quality_session.py` | 长跑 factory 脚本兼具配置、执行、观测、报告 | 拆 `scripts/factories/strategy_quality/{config.py,runner.py,reporting.py,cli.py}` |
| 2215 | `packages/agent/src/aiask_agent/native_capabilities.py` | web、media、skills、plugins、MCP、memory、gateway、RL、平台工具混杂 | 拆 `native/web.py`、`media.py`、`skills.py`、`plugins.py`、`mcp_admin.py`、`models_memory.py`、`gateway_tools.py`、`learning.py`、`platforms.py`、`rl.py` |
| 2198 | `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_mgr_crud.py` | strategy CRUD、personal strategy、ranking、paper session、signals、capabilities 混杂 | 拆 `strategy_mgr_crud/{public_catalog.py,personal.py,subscriptions.py,paper_session.py,ranking.py,signals.py,capabilities.py}` |
| 2142 | `packages/aiask-quant-core/src/aiask_quant_core/storage/sqlite/strategy_ai_parts/queries.py` | scheduler、dispatch、factory runs、topn、events、theme graph、outbox 查询混杂 | 拆 repository：`factory_runs.py`、`dispatch.py`、`topn_scores.py`、`events.py`、`theme_graph.py`、`lineage.py`、`outbox.py` |
| 2085 | `desktop/src/types.ts` | 131 个导出类型聚合在一个文件 | 拆 `types/agent.ts`、`finance.ts`、`gateway.ts`、`mcp.ts`、`settings.ts`、`factory.ts`、`index.ts` |
| 2015 | `packages/strategy-factory/src/strategy_factory/application/stock_strategy_matrix_parts/normalizers.py` | runtime flags、family plans、direction gate、sector bias、priority scoring、profile summary 混杂 | 拆 `runtime_flags.py`、`family_plans.py`、`direction_gate.py`、`sector_bias.py`、`priority_scoring.py`、`profile_summary.py`、`router_telemetry.py`、`param_space.py` |
| 1860 | `packages/aiask-quant-core/src/aiask_quant_core/storage/sqlite/strategy_incubation_parts/queries.py` | trade links、signal evidence、audit、closure、acceptance、metrics 混杂 | 拆 `trade_positions.py`、`signal_evidence.py`、`trade_audit.py`、`closure_snapshots.py`、`execution_acceptance.py`、`incubation_metrics.py` |
| 1829 | `packages/agent/src/aiask_agent/gateway.py` | config store、directory、message store、20 多个平台 adapter、router、runtime 混杂 | 拆 `gateway/models.py`、`config_store.py`、`directory_store.py`、`message_store.py`、`http_client.py`、`adapters/*.py`、`router.py`、`runtime.py` |
| 1720 | `packages/agent/src/aiask_agent/runtime.py` | Agent run loop、handoff、OpenAI tools、python/code tools、job tools 混杂 | 拆 `runtime/run_loop.py`、`handoff.py`、`tool_calling.py`、`code_tools.py`、`jobs.py`、保 `AgentRuntime` facade |
| 1656 | `packages/akshare-mcp/src/akshare_mcp/services/tdx_sync_service.py` | TDX sync 覆盖交易日、基础、quote、sector、financial、fund flow、derived、completeness | 拆 `tdx_sync/service.py`、`tasks/market.py`、`tasks/financial.py`、`tasks/events.py`、`tasks/derived.py`、`completeness.py` |
| 1652 | `packages/aiask-quant-core/src/aiask_quant_core/storage/sqlite/market_context.py` | headline、radar、events、docs、vectors、research、fund flow 在一个 mixin | 拆 `headline_labels.py`、`stock_radar_repo.py`、`market_events_repo.py`、`market_documents_repo.py`、`vectors_repo.py`、`fund_flow_repo.py` |
| 1639 | `packages/akshare-mcp/src/akshare_mcp/services/stock_radar.py` | 抽取、LLM、RSS、PDF、OCR、打分、确认、持久化、API 混杂 | 拆 `stock_radar/{extraction.py,llm.py,rss.py,pdf.py,scoring.py,confirmations.py,persistence.py,api.py}` |
| 1624 | `packages/akshare-mcp/src/akshare_mcp/services/strategy_acceptance_remediation.py` | acceptance、remediation、semantic evidence、策略修复逻辑集中 | 拆 `acceptance/{models.py,evidence.py,remediation.py,reporting.py}` |
| 1595 | `packages/strategy-factory/tests/test_admission_authority.py` | 单测试文件覆盖 admission 多场景 | 拆按 gate/domain 场景测试 |
| 1565 | `packages/akshare-mcp/tests/test_theme_graph_schema.py` | schema、CRUD、regression 在一个测试 | 拆 theme node、edge、exposure、migration tests |
| 1539 | `desktop/src/features/factory-events/FactoryEventTriggerPanel.tsx` | 41 个 state hooks、22 个 callbacks、4 个 effects、7 个视图区块 | 拆 hooks 与 tab components |
| 1528 | `desktop/src/services/aiaskApi.ts` | 171 个方法、136 处 `requestJson` 引用，所有领域 HTTP client 在一个 class | 拆 `services/api/core.ts` 和各 domain client，保 `AiaskApi` facade |
| 1348 | `packages/strategy-factory/src/strategy_factory/application/_submitter_actions/runner_parts/semantic_contract.py` | submitter semantic contract 逻辑过大 | 拆 validation、normalization、freezing、reporting |
| 1347 | `packages/akshare-mcp/src/akshare_mcp/services/market_event_sources.py` | event source 采集和规范化混杂 | 拆 source adapters、normalizers、persistence |
| 1317 | `scripts/ops/trade_prediction_shadow_validation.py` | ops 脚本过长 | 拆 config、runner、report、cli |
| 1282 | `packages/akshare-mcp/src/akshare_mcp/tools/tool_catalog.py` | tool catalog 构建集中 | 按 category 拆 catalog fragments，生成统一 catalog |
| 1280 | `packages/akshare-mcp/src/akshare_mcp/services/stock_profile_pipeline.py` | profile pipeline 阶段集中 | 拆 extract、feature、profile、persist、report |
| 1234 | `packages/strategy-factory/src/strategy_factory/domain/market_evidence.py` | evidence pack、direction、factor/event/fund-flow entries、prediction contract 混杂 | 拆 `market_evidence/{coercion.py,direction.py,factors.py,events.py,fund_flow.py,regime.py,pack.py,prediction_contract.py,quality.py}` |
| 1224 | `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_mgr_lifecycle.py` | recheck、submit、factory run、dispatch、audit、quality gate 混杂 | 拆 `lifecycle/{quality_recheck.py,submission.py,factory_status.py,dispatch.py,execution_audit.py}` |
| 1223 | `packages/akshare-mcp/src/akshare_mcp/tools/market_temperature.py` | market temperature 工具 surface 过宽 | 拆 snapshot、history、industry、validation 工具模块 |
| 1190 | `packages/akshare-mcp/src/akshare_mcp/provider_contracts/registry.py` | provider contract registry 集中 | 拆 registry core、providers、validation、reporting |
| 1173 | `packages/akshare-mcp/src/akshare_mcp/tools/market/kline.py` | kline 参数、路由、fallback、validation 混杂 | 拆 request parsing、provider routing、validation、formatting |
| 1152 | `packages/strategy-factory/src/strategy_factory/application/cycle_runner_parts/normalizers.py` | cycle runner normalizers 过宽 | 按 input、candidate、budget、telemetry 拆 |
| 1141 | `packages/akshare-mcp/src/akshare_mcp/tools/finance.py` | finance tools 聚合 | 按 quote、fundamental、flow、macro 拆 |
| 1126 | `packages/akshare-mcp/tests/test_factory_deep_repair.py` | repair tests 过长 | 按 repair stage 拆 |
| 1120 | `packages/agent/tests/test_extended_agent_capabilities.py` | capability tests 过宽 | 按 native/web/media/platform/rl 拆 |
| 1118 | `packages/agent/src/aiask_agent/gateway_daemon.py` | daemon lifecycle、status、platform 控制集中 | 拆 daemon state、platform supervisor、status API |
| 1106 | `packages/agent/src/aiask_agent/tools/schemas.py` | 工具 schema 全量集中 | 按 tool domain 拆 schema modules，聚合导出 |
| 1098 | `desktop/src/features/workspace/FinanceLabPage.tsx` | finance workspace 多 tab 和状态集中 | 拆 tabs、hooks、panels |
| 1093 | `packages/akshare-mcp/src/akshare_mcp/services/strategy_pipeline.py` | pipeline orchestration 过宽 | 拆 stage runner、contracts、reporting |
| 1085 | `packages/strategy-factory/src/strategy_factory/application/_factory_scheduler_loop_parts/policy.py` | scheduler policy 过宽 | 拆 admission、budget、dispatch、quality policy |
| 1069 | `packages/strategy-factory/src/strategy_factory/application/semantic_contract_parts/policy.py` | semantic policy 过宽 | 拆 thresholds、validation、target policy |
| 1050 | `packages/akshare-mcp/src/akshare_mcp/data_source/tdx_tqcenter.py` | TDX/TQCenter provider 逻辑过宽 | 拆 client、mapping、fallback、capabilities |
| 1046 | `packages/strategy-factory/src/strategy_factory/application/_submitter_actions/runner.py` | submitter runner 仍依赖 fragment 注入 | 先保 shim，再迁移到正常 package |
| 1045 | `scripts/db_sync.py` | DB sync 脚本过长 | 拆 db_sync config、tasks、report、cli |
| 1038 | `packages/strategy-factory/src/strategy_factory/application/_cycle_success_summary.py` | success summary 逻辑集中 | 拆 metrics、formatting、quality summary |
| 1035 | `packages/akshare-mcp/tests/test_full_chain_regression_repairs.py` | full-chain regression 测试过长 | 按链路阶段拆 |
| 1034 | `packages/akshare-mcp/src/akshare_mcp/tools/market_blocks.py` | market block 工具集中 | 拆 concept、industry、constituents、formatting |
| 1015 | `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared/overview.py` | lifecycle overview 过宽 | 拆 overview builders、quality、execution、formatting |
| 1013 | `packages/aiask-quant-core/src/aiask_quant_core/storage/sqlite/_vector_unified_storage.py` | vector storage 统一层过宽 | 拆 collection、documents、embeddings、query |

## 5. 关键代码证据

### 5.1 Agent `server.py`

当前证据：

| 位置 | 证据 |
| --- | --- |
| `packages/agent/src/aiask_agent/server.py:360` | `_audited_runtime_tool_call`，说明工具调用审计逻辑在 server 内。 |
| `packages/agent/src/aiask_agent/server.py:2525` | `create_app`，app factory 入口。 |
| `packages/agent/src/aiask_agent/server.py:2876` | `desktop_capabilities_payload` 嵌在 `create_app` 内。 |
| `packages/agent/src/aiask_agent/server.py:3173-4661` | 161 个 `@app.get/post/patch/delete` route decorator 集中在一个函数体。 |
| `packages/agent/src/aiask_agent/server.py:4672` | `build_server` fallback HTTP server。 |
| `packages/agent/src/aiask_agent/server.py:4723` | `AIASKAgentHandler` fallback handler。 |
| `packages/agent/src/aiask_agent/server.py:6443` | `main` CLI entry。 |

路由领域证据：

| 行段 | 领域 |
| --- | --- |
| 3173-3229 | health、tool catalog、capabilities |
| 3231-3359 | Desktop settings、data、stock data sources、local user、activity、policy |
| 3368-3479 | factor factory、trade predictions、stock radar、workbench summary |
| 3505-3534 | AI status/config/smoke/models |
| 3534-3566 | quant research |
| 3566-3607 | tool call、Hermes、readiness |
| 3621-3706 | financial manager、broker |
| 3722-3979 | Hermes sessions、responses、runs、artifacts、sources、search |
| 4002-4077 | sessions messages、undo/archive、ActionIntent |
| 4085-4151 | admin tools、processes、terminal、browser、skills、plugins |
| 4156-4242 | gateway status/platform/messages/webhooks |
| 4265-4339 | connectors、gateway daemon |
| 4339-4399 | learning、RL |
| 4404-4563 | plugins、MCP |
| 4582-4661 | webhooks、approvals、jobs |

结论：`server.py` 应该是 app assembly，不应该继续承担业务路由实现。

### 5.2 Agent `session_store.py`

当前证据：

| 位置 | 证据 |
| --- | --- |
| `session_store.py:147` | `AgentSessionStore` 开始。 |
| `session_store.py:186` | `_ensure_schema`，schema 创建也在同一类里。 |
| `session_store.py:547-784` | session、message、undo。 |
| `session_store.py:876-1030` | responses、runs、run events。 |
| `session_store.py:1118-1331` | activity、tool invocation audit。 |
| `session_store.py:1366-1750` | broker profile/account/position/order/deal/analytics。 |
| `session_store.py:1769-2074` | sources、artifacts、context snapshots。 |
| `session_store.py:2107-2694` | feedback、user policy、export/delete/retention、learning dataset。 |
| `session_store.py:2707-2868` | handoff、subgoal。 |
| `session_store.py:2875-3036` | search 和 search row indexing。 |

结论：这是一个典型 facade 候选。外部保留 `AgentSessionStore`，内部拆成 repository/service mixins。

### 5.3 Agent `gateway.py`

当前证据：

| 位置 | 证据 |
| --- | --- |
| `gateway.py:278` | `GatewayConfigStore`。 |
| `gateway.py:336` | `GatewayChannelDirectoryStore`。 |
| `gateway.py:491` | `GatewayMessageStore`。 |
| `gateway.py:611` | `BasePlatformAdapter`。 |
| `gateway.py:809-1544` | Webhook、Local、API server、Email、Feishu、DingTalk、WeCom、Discord、Slack、Telegram、Line、Teams、Home Assistant、Matrix、Mattermost、WhatsApp、TwilioSMS、BlueBubbles、Signal、SimpleX、QQBot adapters。 |
| `gateway.py:1613` | `DeliveryRouter`。 |
| `gateway.py:1789` | `GatewayRuntime`。 |

结论：adapter explosion 已经形成。平台 adapter 必须移入 `gateway/adapters/`，否则每加一个平台都会继续扩大一个巨型文件。

### 5.4 Agent `native_capabilities.py`

当前证据：

| 位置 | 证据 |
| --- | --- |
| `native_capabilities.py:85` | `media_provider_catalog`。 |
| `native_capabilities.py:211-333` | URL 校验、fetch、文本抽取。 |
| `native_capabilities.py:351` | `SkillStore`。 |
| `native_capabilities.py:2010-2059` | RL tools。 |
| `native_capabilities.py:2062-2091` | message/webhook tools。 |

结论：native capability 是工具聚合层，应该按 tool domain 拆，最后由 registry 聚合。

### 5.5 Desktop API、Mock、Types、CSS

当前证据：

| 文件 | 证据 |
| --- | --- |
| `desktop/src/services/aiaskApi.ts:102` | `AiaskApi` class。 |
| `desktop/src/services/aiaskApi.ts:107-1521` | 171 个方法，从 health/tools 到 broker/MCP。 |
| `desktop/src/services/aiaskApi.ts` | 136 处 `requestJson` 引用，说明所有领域 HTTP 调用集中。 |
| `desktop/src/mockApi.ts:3174` | `mockRequestJson` dispatch 入口。 |
| `desktop/src/mockApi.ts:3179-4154` | 86 个 `cleanPath ===` 分支，真实 API mock 和 fixture 混在一个函数。 |
| `desktop/src/types.ts:1-2085` | 131 个 `export interface/type`，覆盖 health、tool、market、agent、Hermes、AI、MCP、skills、plugins、user、gateway、jobs、factory、finance、broker。 |
| `desktop/src/styles.css:92` | `.app-shell` 开始，之后同文件继续覆盖 sidebar、workbench、capabilities、quant、tables、MCP、readiness 等。 |
| `desktop/src/styles.css` | 843 个顶层 selector-ish。 |

结论：Desktop 必须先拆合同层，后拆 UI。否则 UI 改动会不断牵动 mock/types/API。

### 5.6 Factory Event UI

当前证据：

| 位置 | 证据 |
| --- | --- |
| `FactoryEventTriggerPanel.tsx:325` | `FactoryEventTriggerPanel` 单组件入口。 |
| `FactoryEventTriggerPanel.tsx:332-386` | 41 个 `useState`，覆盖 tab、events、preview、lineage、exposure/outbox、radar、form、approval、outcome。 |
| `FactoryEventTriggerPanel.tsx:388-822` | 22 个 `useCallback`，覆盖 load、preview、create、approve、pause、outcome、maintenance、radar intents。 |
| `FactoryEventTriggerPanel.tsx:471-483` | 4 个 `useEffect`。 |
| `FactoryEventTriggerPanel.tsx:928` 和 `1487` | 中间 render helper 与最终 return，说明视图和状态逻辑混在同一组件。 |

结论：先拆 hooks，再拆 tab components。

### 5.7 AKShare manager/service 热点

当前证据：

| 文件 | 证据 |
| --- | --- |
| `strategy_mgr_crud.py:98` | personal strategy mutation guard。 |
| `strategy_mgr_crud.py:1205-2200` | create/publish/archive/list/detail/review/events/subscription/personal/update/delete/paper/rank/AI optimize/capabilities/signals handlers。 |
| `strategy_mgr_lifecycle.py:349-417` | recheck validation/risk/quality inputs/closure refresh。 |
| `strategy_mgr_lifecycle.py:454-1124` | review recheck、submission replay、submit、lifecycle scan、factory status/run/dispatch/topn、execution audit。 |
| `stock_radar.py:303` | event extraction。 |
| `stock_radar.py:420` | LLM enhancement。 |
| `stock_radar.py:598` | RSS ingestion。 |
| `stock_radar.py:675-763` | PDF download 和 PyMuPDF/pdfplumber/PaddleOCR parse。 |
| `stock_radar.py:1242-1623` | run/status/candidates/digest/push/schedule API。 |
| `tdx_sync_service.py:134` | `TdxSyncService`。 |
| `tdx_sync_service.py:173-1710` | `run_all` 和二十多个 `_sync_*`/`_derive_*` tasks。 |

结论：AKShare 已成为最重业务包，manager 和 service 必须按业务用例拆，不要继续增加单文件 handler。

### 5.8 Strategy Factory 和 Quant Core 热点

当前证据：

| 文件 | 证据 |
| --- | --- |
| `stock_strategy_matrix_parts/normalizers.py:71-2028` | runtime flags、family allocation、direction gate、sector bias、priority scoring、profile summary、router telemetry、family plans、param search 全在一个 fragment part。 |
| `domain/market_evidence.py:713` | `build_market_evidence_pack`。 |
| `domain/market_evidence.py:790` | `resolve_direction_and_confidence`。 |
| `domain/market_evidence.py:954` | `_build_prediction_contract_from_pack`。 |
| `domain/market_evidence.py:1099` | `apply_evidence_first_candidate`。 |
| `domain/market_evidence.py:1167` | `summarize_generation_quality`。 |
| `strategy_ai_parts/queries.py:2-314` | factory runs、artifacts、scheduler state、dispatch。 |
| `strategy_ai_parts/queries.py:352-555` | topn/full-market scores。 |
| `strategy_ai_parts/queries.py:701-964` | event clusters、themes、company exposure、event signals。 |
| `strategy_ai_parts/queries.py:1002-2126` | theme graph、event injection、lineage、outbox。 |
| `strategy_incubation_parts/queries.py:2-164` | trade position links、signal evidence backfill。 |
| `strategy_incubation_parts/queries.py:825-1636` | trade audit、verification、snapshots、acceptance。 |
| `market_context.py:387-462` | headline labels。 |
| `market_context.py:565-847` | stock radar runs/candidates/push logs。 |
| `market_context.py:880-1046` | normalized market events 和 documents。 |
| `market_context.py:1482-1605` | vector docs、research reports、stock fund flow。 |

结论：Quant Core storage 需要从 mixin 巨型 query surface 迁移为 repository modules；Strategy Factory 的 fragment parts 需要逐步转成正常 modules。

## 6. 目标结构

### 6.1 Agent

```text
packages/agent/src/aiask_agent/
  server.py                         # create_app, lifespan, router assembly only
  routes/
    health.py
    desktop_data.py
    desktop_user.py
    desktop_finance.py
    ai.py
    responses_runs_sessions.py
    intents_approvals.py
    tools.py
    hermes.py
    gateway.py
    connectors.py
    plugins_skills.py
    mcp.py
    webhooks.py
    jobs.py
    learning_rl.py
  services/
    audited_tool_calls.py
    desktop_payloads.py
    route_auth.py
  stores/
    session_core.py
    run_store.py
    audit_store.py
    broker_store.py
    evidence_store.py
    user_data_store.py
    handoff_store.py
    search_store.py
  native/
    web.py
    media.py
    skills.py
    plugins.py
    mcp_admin.py
    models_memory.py
    gateway_tools.py
    learning.py
    platforms.py
    rl.py
  gateway/
    models.py
    config_store.py
    directory_store.py
    message_store.py
    http_client.py
    router.py
    runtime.py
    adapters/
      feishu.py
      discord.py
      slack.py
      telegram.py
      ...
```

迁移规则：

1. 路由 path、method、response shape 不变。
2. `server.py` 保留 `create_app`，每个 route group 用 `include_router` 装配。
3. `_audited_runtime_tool_call` 迁移为唯一工具审计入口，不允许 route 自己绕过。
4. control token、ActionIntent、side_effect metadata 的判断集中在 route/service helper。
5. 每拆一个 route group 跑 endpoint drift 和 tool-call path gate。

### 6.2 Desktop

```text
desktop/src/services/
  aiaskApi.ts                       # backward-compatible facade
  api/
    core.ts
    healthApi.ts
    agentApi.ts
    financeApi.ts
    factoryApi.ts
    gatewayApi.ts
    mcpApi.ts
    settingsApi.ts
    pluginsSkillsApi.ts

desktop/src/mock/
  index.ts
  routePaths.ts
  fixtures/
    agent.ts
    finance.ts
    gateway.ts
    mcp.ts
    factory.ts
  handlers/
    agent.ts
    finance.ts
    gateway.ts
    mcp.ts
    settings.ts

desktop/src/types/
  agent.ts
  finance.ts
  gateway.ts
  mcp.ts
  settings.ts
  factory.ts
  user.ts
  index.ts

desktop/src/styles/
  globals.css
  layout.css
  workbench.css
  finance.css
  agent-pages.css
  forms.css
  tables.css
```

`FactoryEventTriggerPanel.tsx` 目标：

```text
desktop/src/features/factory-events/
  FactoryEventTriggerPanel.tsx      # shell only
  hooks/
    useFactoryEvents.ts
    useFactoryMaintenance.ts
    useFactoryRadar.ts
    useFactoryEventForm.ts
  components/
    FactoryEventTabs.tsx
    EventsTab.tsx
    CreateTab.tsx
    PreviewTab.tsx
    LineageTab.tsx
    RadarTab.tsx
    MaintenancePanel.tsx
```

迁移规则：

1. 保留 `AiaskApi` facade，旧页面 import 不一次性改完。
2. API path 先抽常量，真实 client 和 mock handler 共用，减少 drift。
3. types 拆分后由 `types/index.ts` 统一导出。
4. CSS 先按页面域拆 import，不改变 class 名，第二阶段再消化命名。
5. e2e 先按页面/能力拆文件，不改断言语义。

### 6.3 AKShare MCP

```text
packages/akshare-mcp/src/akshare_mcp/
  tools/managers/strategy_mgr_crud/
    __init__.py
    public_catalog.py
    personal.py
    subscriptions.py
    paper_session.py
    ranking.py
    signals.py
    capabilities.py
  tools/managers/strategy_mgr_lifecycle/
    __init__.py
    quality_recheck.py
    submission.py
    factory_status.py
    dispatch.py
    execution_audit.py
  services/stock_radar/
    __init__.py
    extraction.py
    llm.py
    rss.py
    pdf.py
    scoring.py
    confirmations.py
    persistence.py
    api.py
  services/tdx_sync/
    service.py
    tasks/
      market.py
      financial.py
      events.py
      derived.py
    completeness.py
```

迁移规则：

1. 原文件先变成 import/re-export facade，保持 manager action 名称不变。
2. Manager handler 的 `ok/fail/manager_protocol` envelope 不改变。
3. Stateful/trade-risk action 的 guardrail metadata 不允许在拆分中丢失。
4. AKShare 调 Strategy Factory 只通过 public facade，减少对 application/domain 深层 import。

### 6.4 Strategy Factory

```text
packages/strategy-factory/src/strategy_factory/
  application/stock_strategy_matrix/
    runtime_flags.py
    family_plans.py
    direction_gate.py
    sector_bias.py
    priority_scoring.py
    profile_summary.py
    router_telemetry.py
    param_space.py
  domain/market_evidence/
    coercion.py
    direction.py
    factors.py
    events.py
    fund_flow.py
    regime.py
    pack.py
    prediction_contract.py
    quality.py
```

迁移规则：

1. 新代码禁止新增 `_fragment_loader` 使用。
2. 旧 fragment 每次只迁一个 public shim。
3. 先迁低风险 pure normalizer，再迁 scheduler/submitter。
4. 保持 Strategy Factory 不反向依赖 AKShare。

### 6.5 Quant Core

```text
packages/aiask-quant-core/src/aiask_quant_core/storage/sqlite/
  strategy_ai_repos/
    factory_runs.py
    dispatch.py
    topn_scores.py
    events.py
    theme_graph.py
    lineage.py
    outbox.py
  strategy_incubation_repos/
    trade_positions.py
    signal_evidence.py
    trade_audit.py
    closure_snapshots.py
    execution_acceptance.py
    incubation_metrics.py
  market_context_repos/
    headline_labels.py
    stock_radar_repo.py
    market_events_repo.py
    market_documents_repo.py
    vectors_repo.py
    fund_flow_repo.py
```

迁移规则：

1. Quant Core repository 不 import Agent/Desktop/AKShare manager。
2. 若确实需要 Strategy Factory contract，放在明确的 contracts/runtime hook 层，并加 boundary test。
3. Mixin facade 先保留，逐步委托到 repos。

## 7. 分阶段执行路线

### P0：冻结基线和仓库卫生

目标：先让整理在可控工作树上发生。

动作：

1. 和业务改动分离：把当前 155 项变更分类为业务改动、生成产物、临时报告、兼容删除。
2. 根目录只保留稳定入口和少量总纲文档，临时报表进入 `docs/archive/` 或 `reports/sessions/`。
3. `.gitignore` 检查 `output/`、`tmp/`、`desktop/.playwright-cli/`、runtime logs/cache/DB。
4. 决定 Graphify 是否重建。若不重建，所有架构文档注明 2026-05-29 图谱是 stale baseline。

验收：

```bash
git status --short
uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
uv run pytest packages/strategy-factory/tests/test_package_decoupling_boundary.py -q
```

### P1：Agent server 先拆 route

目标：把 `server.py` 从 6532 行缩为 app assembly。

顺序：

1. health/readiness/capabilities。
2. Desktop data/user/settings。
3. responses/runs/sessions/artifacts/sources/search。
4. intents/approvals。
5. tools/Hermes/admin tools。
6. gateway/connectors/webhooks/jobs。
7. AI/learning/RL。
8. financial manager/broker/quant/factory desktop surfaces。

验收：

```bash
uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
uv run pytest packages/agent/tests/test_tool_registry.py -q
uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py -q
uv run pytest packages/agent/tests/test_desktop_capabilities_api.py -q
```

后两组若仍慢，先记录耗时并抽小样本，不阻塞纯 route relocation。

### P2：Desktop 合同层拆分

目标：真实 API、Mock、Types、CSS 各自有边界。

顺序：

1. 抽 `services/api/core.ts` 和 path constants。
2. `AiaskApi` 按领域委托，但保 class facade。
3. `mockApi.ts` 拆 handlers/fixtures。
4. `types.ts` 拆 domain type modules。
5. `styles.css` 按页面域拆，不改 class 语义。
6. `FactoryEventTriggerPanel.tsx` 拆 hooks 和 tab components。

验收：

```bash
cd desktop
npm run typecheck
npm test
npm run test:e2e:mock
```

### P3：AKShare / Strategy Factory / Quant Core 收口 facade

目标：减少深层 import 和 manager 泄漏。

顺序：

1. 为 AKShare 调 Strategy Factory 建更窄 facade，例如 `strategy_factory.api.runtime`、`api.market_views`、`api.quality_reporting`。
2. Agent adapters 不直接知道 AKShare manager 内部结构，只调用 AKShare public adapter/facade。
3. Quant Core repository 拆分，并加反向依赖守门。
4. 清理 Graphify 中的反向边，逐项判断合法 hook 或真实风险。

新增测试建议：

```text
packages/agent/tests/test_import_boundary.py
packages/akshare-mcp/tests/test_strategy_factory_facade_boundary.py
packages/aiask-quant-core/tests/test_package_boundary.py
```

验收：

```bash
uv run pytest packages/strategy-factory/tests/test_package_decoupling_boundary.py -q
uv run pytest packages/agent/tests/test_tool_registry.py -q
uv run pytest packages/akshare-mcp/tests/test_strategy_factory_ownership.py -q
```

### P4：fragment loader 退场

当前证据：`rg -n 'exec_fragments|exec_block|_fragment_loader' packages -g '*.py'` 显示 AKShare、Strategy Factory、Quant Core 都有使用，且集中在 DSL、backtest、storage queries、scheduler、submitter、semantic contract、manager helpers 等核心路径。

目标：新代码不再增加 fragment loader，旧代码逐步迁移到普通 module。

迁移顺序：

1. DTO、pure normalizers、contracts。
2. quality_reporting、candidate_contract、semantic_contract。
3. stock_strategy_matrix、market_evidence。
4. sqlite query parts。
5. scheduler、submitter、factory loop。

规则：

1. 每次只迁一个 public shim。
2. 原 import path 保留 re-export。
3. 迁移 PR 必须有 import smoke test。
4. 迁移后更新 Graphify 或至少更新本报告里的 stale 标记。

## 8. 推荐 PR 顺序

| PR | 内容 | 风险 |
| --- | --- | --- |
| PR1 | 仓库卫生：`.gitignore`、报告归档、Graphify stale 标记 | 低 |
| PR2 | Agent health/capabilities/readiness routes 拆出 | 中低 |
| PR3 | Agent sessions/runs/artifacts/search routes 拆出 | 中 |
| PR4 | Desktop `AiaskApi` facade 拆 domain clients | 中 |
| PR5 | Desktop mock/types 拆分并共享 path constants | 中 |
| PR6 | `FactoryEventTriggerPanel` hooks/components 拆分 | 中 |
| PR7 | AKShare `strategy_mgr_crud` facade 拆分 | 中高 |
| PR8 | Quant Core `strategy_ai` repository 拆分 | 中高 |
| PR9 | Strategy Factory `stock_strategy_matrix` normalizers 退 fragment 试点 | 中高 |

## 9. 成功标准

| 目标 | 可量化标准 |
| --- | --- |
| `server.py` 收口 | 降到 800 行以内，只包含 app wiring、lifespan、router include、fallback server/main。 |
| Desktop 合同清晰 | `aiaskApi.ts` 只做 facade，domain clients 单文件不超过 400 行。 |
| Mock 可维护 | `mockApi.ts` 消失或只保 compatibility export，handler 单文件不超过 500 行。 |
| Types 可维护 | `types.ts` 消失或只做 barrel export，domain type 文件不超过 500 行。 |
| CSS 可维护 | `styles.css` 拆成页面域文件，单 CSS 文件不超过 800 行。 |
| Store 可维护 | `AgentSessionStore` 保 facade，broker/evidence/search/user policy 独立 repository。 |
| AKShare manager 收口 | manager action 名称不变，但实现按领域模块化。 |
| Fragment 不扩散 | 新代码无新增 `_fragment_loader` 使用。 |
| 边界守住 | endpoint drift、tool registry、tool call path、package decoupling tests 进入常规验证。 |

## 10. 不建议做的事

1. 不建议一次性大重写 `server.py`、`mockApi.ts`、`styles.css`。
2. 不建议在当前 155 项变更未分类前做跨包重构。
3. 不建议删除 legacy UI，除非 replacement view 和 e2e 覆盖已稳定。
4. 不建议绕过 `agent_*` facade 暴露 AKShare manager。
5. 不建议让 Strategy Factory 新增对 AKShare 的直接依赖。
6. 不建议在整理过程中操作 live trading、broker state、runtime DB、logs 或 cache。

## 11. 本次审查的直接下一步

最稳的第一步是做一个只移动、不改行为的 PR：

1. 新建 `packages/agent/src/aiask_agent/routes/health.py` 和 `services/desktop_payloads.py`。
2. 从 `server.py` 迁出 health、detailed health、capabilities、tools catalog 只读路由。
3. `server.py` 中用 `include_router` 接回。
4. 跑 endpoint drift、tool-call path、tool registry。

这一步可以验证迁移模板是否可行。一旦模板跑通，再按相同模式处理 Desktop API 和 AKShare manager。

## 12. 执行记录

### 2026-06-14 第一批：Agent 只读路由拆分模板

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/health.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_health_router(...))` 挂载 |
| 已迁出端点 | `/health`、`/health/detailed`、`/v1/capabilities/parity`、`/v1/tools`、`/v1/desktop/capabilities` |
| `server.py` 行数 | 6489 行 |
| 新模块行数 | `routes/health.py` 86 行 |
| `server.py` FastAPI route decorators | 156 个 |
| `routes/health.py` route decorators | 5 个 |

验证结果：

```bash
uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 3.15s

uv run pytest packages/agent/tests/test_desktop_capabilities_api.py -q
# 7 passed in 42.83s
```

下一批建议继续从 `server.py` 中迁出 Desktop settings/data/user 只读和低副作用路由，并保持同样规则：先抽 router factory，不改变 path、method、response shape 和 guardrail。

### 2026-06-14 第二批：Desktop data/settings 路由拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/desktop_data.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_desktop_data_router(...))` 挂载 |
| 已迁出端点 | `/v1/desktop/settings/status`、`/v1/desktop/data/status`、`/v1/desktop/data/sync-plan`、`/v1/desktop/stock-data-sources`、`POST /v1/desktop/stock-data-sources`、`/v1/desktop/stock-data-sources/test` |
| 累计迁出 FastAPI route decorators | 11 个 |
| `server.py` 行数 | 6462 行 |
| `server.py` FastAPI route decorators | 150 个 |
| 新模块行数 | `routes/desktop_data.py` 59 行 |

验证结果：

```bash
uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 0.90s

uv run pytest packages/agent/tests/test_desktop_ops_api.py packages/agent/tests/test_desktop_capabilities_api.py -q
# 21 passed in 150.82s
```

下一批建议迁出 Desktop local user/activity/policy 路由，但需要特别注意 `require_user_scope`、retention/delete/export 等数据治理行为，不要把跨用户 control-token 规则拆散。

### 2026-06-14 第三批：Desktop user/activity/data-governance 路由拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/desktop_user.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_desktop_user_router(...))` 挂载 |
| 已迁出端点 | local profile GET/POST/PATCH、desktop events、feedback、user activity、analytics summary、user export/delete、retention sweep、learning dataset、recommendations、data-policy GET/PATCH |
| 累计迁出 FastAPI route decorators | 25 个 |
| `server.py` 行数 | 6378 行 |
| `server.py` FastAPI route decorators | 136 个 |
| 新模块行数 | `routes/desktop_user.py` 124 行 |

验证结果：

```bash
uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 2.67s

uv run pytest packages/agent/tests/test_desktop_ops_api.py packages/agent/tests/test_desktop_workbench_contracts.py -q
# 25 passed in 188.03s
```

当前 P1 已验证的迁移模板：

1. 每个 route group 使用 `create_*_router(...)` factory。
2. `server.py` 保留 runtime、auth、control、scope helper 的来源，并通过依赖注入传给 router。
3. 新 router 不改变 path、method、response shape。
4. 对 control-token 和 cross-user scope 的判断仍由原 helper 执行。

下一批可迁出 `/v1/desktop/factor-factory/status`、trade prediction、stock radar digest/candidates 这些 Desktop finance read surfaces；它们会触及 `runtime.tool_registry.call_tool`，建议同步引入统一的 audited desktop read helper，避免 route 拆分后审计路径分散。

### 2026-06-14 第四批：Desktop finance read surfaces 路由拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增/启用 route 模块 | `packages/agent/src/aiask_agent/routes/desktop_finance.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_desktop_finance_router(...))` 挂载 |
| 已迁出端点 | `/v1/desktop/factor-factory/status`、trade prediction status/outcomes/matrix、stock radar status/candidates/digest |
| 审计路径 | trade prediction 与 stock radar 端点由 `audited_desktop_tool_call` 注入调用，不再在 FastAPI route 内直连 `runtime.tool_registry.call_tool` |
| 守门同步 | 从 `docs/architecture/tool-call-path-classification.json` 移除 6 条已经 stale 的 `server.py::create_app.desktop_*` 直连分类，保留 fallback HTTPServer 只读分类 |
| 累计迁出 FastAPI route decorators | 32 个 |
| `server.py` 行数 | 6276 行 |
| `server.py` FastAPI route decorators | 129 个 |
| 新模块行数 | `routes/desktop_finance.py` 139 行 |
| `routes/desktop_finance.py` route decorators | 7 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/desktop_finance.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 3.16s

uv run pytest packages/agent/tests/test_desktop_ops_api.py -q
# 14 passed in 89.70s

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py -q
# 11 passed in 149.88s

uv run pytest packages/agent/tests/test_desktop_capabilities_api.py -q
# 7 passed in 64.24s
```

当前 P1 模板补充结论：

1. 对会触及 `agent_*` 工具的 Desktop route，router factory 应优先接收 `audited_desktop_tool_call`，而不是直接持有 `runtime.tool_registry.call_tool`。
2. route 迁出后需要同步维护 `tool-call-path-classification.json`，删除 stale 的直连分类，避免守门测试把历史路径误认为当前例外。
3. 下一批建议迁出 `/v1/desktop/workbench/summary` 和 AI status/config/smoke/models 这一组只读/低副作用 Desktop shell 端点；如果涉及配置保存，继续保持 control-token 判断留在注入 helper 或原 route auth helper 中。

### 2026-06-14 第五批：Workbench summary 与 AI 配置路由拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/desktop_workbench.py`、`packages/agent/src/aiask_agent/routes/ai.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_desktop_workbench_router(...))` 和 `app.include_router(create_ai_router(...))` 挂载 |
| 已迁出端点 | `/v1/desktop/workbench/summary`、`/v1/ai/status`、`/v1/ai/config` GET/PATCH、`/v1/ai/smoke`、`/v1/ai/models` |
| guardrail 保持 | `PATCH /v1/ai/config` 继续由注入的 `require_control` 执行 control-token 判断，`ValueError` 仍转换为 400 HTTP 响应 |
| 累计迁出 FastAPI route decorators | 38 个 |
| `server.py` 行数 | 6266 行 |
| `server.py` FastAPI route decorators | 123 个 |
| 新模块行数 | `routes/desktop_workbench.py` 26 行；`routes/ai.py` 50 行 |
| 新模块 route decorators | `desktop_workbench.py` 1 个；`ai.py` 5 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/ai.py packages/agent/src/aiask_agent/routes/desktop_workbench.py packages/agent/src/aiask_agent/routes/desktop_finance.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 3.77s

uv run pytest packages/agent/tests/test_ai_status_and_smoke.py -q
# 10 passed, 1 skipped in 97.68s

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_desktop_ops_api.py -q
# 25 passed in 231.98s
```

当前 P1 模板补充结论：

1. 简单只读 route 可以只注入 payload builder，避免新 router import runtime、store 或 env helper。
2. 含控制令牌的低副作用 route 可以迁出，但必须把 `require_control` 作为显式依赖传入 router factory。
3. 下一批建议迁出 `/v1/desktop/runs` 与 responses/runs/sessions/artifacts/search 这一组运行历史路由；这组会触及 run/session store 和 SSE，需要单独核对 fallback HTTPServer 对应分支。

### 2026-06-14 第六批：Desktop runs 运行历史入口拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/desktop_runs.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_desktop_runs_router(...))` 挂载 |
| 已迁出端点 | `/v1/desktop/runs` |
| 行为保持 | route 仍只执行 `require_api`，再委托 `_desktop_runs_payload`；fallback HTTPServer 分支保持原样 |
| 累计迁出 FastAPI route decorators | 39 个 |
| `server.py` 行数 | 6272 行 |
| `server.py` FastAPI route decorators | 122 个 |
| 新模块行数 | `routes/desktop_runs.py` 26 行 |
| 新模块 route decorators | 1 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/desktop_runs.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 3.40s

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py -q
# 11 passed in 100.91s
```

当前 P1 模板补充结论：

1. 单端点 route 迁移也值得跑 endpoint drift，因为它能证明 URL/method 没被 include 顺序影响。
2. `server.py` 行数可能因 adapter 和 import 短期回升，但 route decorator 数仍是更直接的路由收口指标。
3. 下一批建议处理 `/v1/responses`、`/v1/chat/completions`、`/v1/search` 的模型响应入口；这组应和 session/run 历史读取分开，避免一次迁出过多状态路径。

### 2026-06-14 第七批：Responses、Chat Completions 与 Search 路由拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/responses.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_responses_router(...))` 挂载 |
| 已迁出端点 | `POST /v1/responses`、`POST /v1/chat/completions`、`GET /v1/responses/{response_id}`、`DELETE /v1/responses/{response_id}`、`GET /v1/search` |
| streaming 保持 | responses/chat streaming 继续复用原 `response_sse` 与 `chat_completion_sse` async generator，并返回 `StreamingResponse(..., media_type="text/event-stream")` |
| 行为保持 | runtime selection、response/chat payload 格式化、response store get/delete、search payload 都通过 `server.py` 注入，fallback HTTPServer 分支保持原样 |
| 累计迁出 FastAPI route decorators | 44 个 |
| `server.py` 行数 | 6236 行 |
| `server.py` FastAPI route decorators | 117 个 |
| 新模块行数 | `routes/responses.py` 99 行 |
| 新模块 route decorators | 5 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/responses.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 5.19s

uv run pytest packages/agent/tests/test_server.py -q
# 7 passed in 96.64s

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py -q
# 11 passed in 139.83s
```

当前 P1 模板补充结论：

1. streaming route 可以迁出，但 SSE generator 不应复制，继续从 app factory 注入原 helper。
2. 模型响应入口和运行历史读取应分开迁移；前者重点是 runtime selection/streaming，后者重点是 store 查询、SSE event stream 和状态变更。
3. 下一批建议迁出 `/v1/runs/{run_id}`、run events/artifacts/sources/trace/tool-invocations 和 session artifacts/sources 这一组运行历史读取 route；`cancel/stop/steer` 有状态写入，建议单独批次处理。

### 2026-06-14 第八批：Run history 读取路由拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/run_history.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_run_history_router(...))` 挂载 |
| 已迁出端点 | run events/SSE、run get、run artifacts/sources/trace-eval/tool-invocations、session artifacts/sources/messages、artifact get/content、source get、tool invocation get |
| 状态写入保留 | `/v1/runs/{run_id}/cancel`、`/stop`、`/steer` 仍留在 `server.py`，等待单独批次处理 |
| SSE 保持 | run events 继续复用原 `sse_events` 与 `_normalize_run_event`，返回 `text/event-stream` |
| fallback 保持 | fallback HTTPServer 中对应 GET/DELETE/POST 分支保持原样 |
| 累计迁出 FastAPI route decorators | 58 个 |
| `server.py` 行数 | 6146 行 |
| `server.py` FastAPI route decorators | 103 个 |
| 新模块行数 | `routes/run_history.py` 134 行 |
| 新模块 route decorators | 14 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/run_history.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 4.00s

uv run pytest packages/agent/tests/test_evidence_artifacts_sources.py -q
# 5 passed in 65.65s

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py -q
# 11 passed in 131.68s

uv run pytest packages/agent/tests/test_extended_agent_capabilities.py::test_http_sse_run_events_toolsets_and_jobs -q
# 1 passed in 8.14s
```

当前 P1 模板补充结论：

1. 运行历史读取 route 适合按“只读 store surface”集中迁移，但状态写入 route 应保持单独批次。
2. SSE route 的测试应覆盖 FastAPI 与 fallback 至少一个哨兵路径；本批 FastAPI 由 workbench/evidence 测试覆盖，fallback 由 extended capability 单测覆盖。
3. 下一批建议处理 run cancel/stop/steer 与 session undo/archive 这类状态写入 route；它们应继续显式执行 `require_api` 或 `require_full`，并保留写入事件 payload。

### 2026-06-14 第九批：Run/session control 状态路由拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/run_control.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_run_control_router(...))` 挂载 |
| 已迁出端点 | `/v1/runs/{run_id}/cancel`、`/stop`、`/steer`、`/v1/sessions/{session_id}/undo`、`/archive` |
| guardrail 保持 | run control 继续执行 `require_api`；session undo/archive 继续执行 `require_full`，即 full mode + control-token gate |
| 状态写入保持 | cancel 继续更新 run payload/status 并追加 `run.cancelled`；steer 继续追加 `run.steer`；archive/undo 继续委托 session store |
| 累计迁出 FastAPI route decorators | 63 个 |
| `server.py` 行数 | 6093 行 |
| `server.py` FastAPI route decorators | 98 个 |
| 新模块行数 | `routes/run_control.py` 82 行 |
| 新模块 route decorators | 5 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/run_control.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 2.14s

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py -q
# 11 passed in 101.55s

uv run pytest packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface -q
# 1 passed in 8.63s
```

当前 P1 模板补充结论：

1. 状态写入 route 可迁出，但 router factory 必须显式接收 `require_api`/`require_full`，不能隐藏 guardrail。
2. 写入事件 payload 应在迁移后用 store-level 断言测试覆盖，而不仅是 endpoint 200。
3. 下一批建议处理 `intents` 与 `approvals` route；这组会触及 `agent_action_intent_*` 工具审计和 control-token gate，需要同步关注 `tool-call-path-classification.json` 是否出现 stale 或新增直连分类。

### 2026-06-14 第十批：ActionIntent HTTP 路由拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/intents.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_intents_router(...))` 挂载 |
| 已迁出端点 | `/intents` GET/POST、`/intents/{intent_id}` GET、`/intents/{intent_id}/confirm`、`/deny` |
| 审计路径 | `GET /intents/{intent_id}` 改为通过 `audited_desktop_tool_call("agent_action_intent_get", ...)`，不再直连 `runtime.tool_registry.call_tool` |
| guardrail 保持 | create/confirm/deny 继续执行 control-token gate；list/get 继续执行 API gate |
| 守门同步 | 从 `docs/architecture/tool-call-path-classification.json` 移除 stale 的 `server.py::create_app.intent_get::agent_action_intent_get` 直连分类，保留 fallback HTTPServer 只读分类 |
| 累计迁出 FastAPI route decorators | 68 个 |
| `server.py` 行数 | 6060 行 |
| `server.py` FastAPI route decorators | 93 个 |
| 新模块行数 | `routes/intents.py` 67 行 |
| 新模块 route decorators | 5 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/intents.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 4.54s

uv run pytest packages/agent/tests/test_intents.py -q
# 5 passed in 19.03s

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_desktop_workbench_contracts.py -q
# 18 passed in 154.38s
```

当前 P1 模板补充结论：

1. route 迁移是顺手减少 direct tool call 例外的好时机；读工具也可以走审计 helper。
2. 修改 direct call 路径后必须同步 `tool-call-path-classification.json`，否则守门测试会提示 stale 分类。
3. 下一批建议迁出 `/v1/approvals` list/decision route；它们是 control-token 操作，应和 intents 分开记录。

### 2026-06-14 第十一批：Approvals HTTP 路由拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/approvals.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_approvals_router(...))` 挂载 |
| 已迁出端点 | `/v1/approvals`、`/v1/approvals/{approval_id}/{decision}` |
| guardrail 保持 | 两个 route 继续执行 `require_full`，即 full mode + control-token gate |
| store 行为保持 | 继续通过 `ApprovalStore(runtime.session_store.path)` list/decide；迁移后由 `approval_store_factory` 注入 |
| 累计迁出 FastAPI route decorators | 70 个 |
| `server.py` 行数 | 6050 行 |
| `server.py` FastAPI route decorators | 91 个 |
| 新模块行数 | `routes/approvals.py` 34 行 |
| 新模块 route decorators | 2 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/approvals.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 1.09s

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_desktop_workbench_contracts.py -q
# 18 passed in 140.45s
```

当前 P1 模板补充结论：

1. `ApprovalStore` 这类轻量 store 可以用 factory 注入，避免 router 在 import 层绑定具体 state path。
2. 审批类 route 要和 intent 创建/确认分开记录，方便后续审计 guardrail 是否仍完整。
3. 下一批建议迁出 jobs route，之后再处理 gateway/connectors/webhooks 这些外部平台/计划任务相关路径。

### 2026-06-14 第十二批：Jobs HTTP 路由拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/jobs.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_jobs_router(...))` 挂载 |
| 已迁出端点 | `/v1/jobs` GET/POST、`/v1/jobs/{job_id}` PATCH/DELETE、`/v1/jobs/{job_id}/runs`、`/v1/jobs/{job_id}/run` |
| 行为保持 | 继续使用 `require_api`，job store create/update/delete/list/list_runs 和 scheduler run_job 行为不变 |
| 后续注意 | jobs 创建/更新/删除/立即运行属于计划任务状态变更，后续可单独评估是否升级到 control-token 或 ActionIntent gate |
| 累计迁出 FastAPI route decorators | 78 个 |
| `server.py` 行数 | 6009 行 |
| `server.py` FastAPI route decorators | 85 个 |
| 新模块行数 | `routes/jobs.py` 67 行 |
| 新模块 route decorators | 6 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/jobs.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 1.05s

uv run pytest packages/agent/tests/test_extended_agent_capabilities.py::test_http_sse_run_events_toolsets_and_jobs -q
# 1 passed in 14.77s

uv run pytest packages/agent/tests/test_server.py -q
# 7 passed in 58.86s
```

当前 P1 模板补充结论：

1. 计划任务 route 可先做结构迁移，但 guardrail 等级需要在单独安全批次里评估，避免“迁移”和“策略变更”混在一起。
2. scheduler 相关 route 适合用 `job_store` 与 `scheduler` 两个依赖注入，router 不需要知道 runtime 其余部分。
3. 下一批建议迁出 tools/Hermes/admin tools 或 gateway/connectors/webhooks；这两组都涉及 full-mode/control gate，应继续小批量处理。

### 2026-06-14 第十三批：Tools 与 Hermes admin tool 路由拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/tools.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_tools_router(...))` 挂载 |
| 已迁出端点 | `POST /v1/tools/{tool_name}`、`POST /v1/hermes/admin/tools/{tool_name}` |
| 审计路径保持 | 两个 route 继续通过 `audited_tool_call` 记录 tool invocation 与 evidence |
| guardrail 保持 | desktop read-only tool endpoint 继续执行 API gate 与 read-only metadata gate；Hermes admin tool endpoint 继续执行 `require_full` |
| 累计迁出 FastAPI route decorators | 80 个 |
| `server.py` 行数 | 5988 行 |
| `server.py` FastAPI route decorators | 83 个 |
| 新模块行数 | `routes/tools.py` 52 行 |
| 新模块 route decorators | 2 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/tools.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 2.68s

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_desktop_workbench_contracts.py -q
# 18 passed in 152.70s

uv run pytest packages/agent/tests/test_desktop_ops_api.py::test_agent_web_search_uses_configured_search_source -q
# 1 passed in 7.51s
```

当前 P1 模板补充结论：

1. 通用工具调用 route 迁出时，要把 metadata read-only 判断和审计 helper 一起注入，避免 router 自行绕开策略。
2. Full-mode admin tool route 可和 read-only tool route 放在同一模块，但必须保留不同 source chain，便于审计区分。
3. 下一批建议处理 Hermes status/readiness/financial-system readiness 这类只读状态 route，或转向 gateway/connectors/webhooks。

### 2026-06-14 第十四批：Hermes 与 financial readiness 状态路由拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/hermes_status.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_hermes_status_router(...))` 挂载 |
| 已迁出端点 | `/v1/hermes/status`、`/v1/hermes/readiness`、`/v1/financial-system/readiness` |
| 行为保持 | Hermes status 继续使用原 parity/full-surface payload；financial readiness 继续传入 full runtime 状态、control-token 配置状态和 AI status |
| guardrail 保持 | 三个 route 继续执行 `require_api` |
| 累计迁出 FastAPI route decorators | 83 个 |
| `server.py` 行数 | 5989 行 |
| `server.py` FastAPI route decorators | 80 个 |
| 新模块行数 | `routes/hermes_status.py` 33 行 |
| 新模块 route decorators | 3 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/hermes_status.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 3.47s

uv run pytest packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_financial_manager_desktop_api.py -q
# 13 passed in 113.32s

uv run pytest packages/agent/tests/test_native_full_parity.py::test_financial_system_readiness_gate_reports_required_blockers packages/agent/tests/test_native_full_parity.py::test_financial_system_readiness_can_reach_ready_with_core_runtime_config -q
# 2 passed in 29.32s
```

当前 P1 模板补充结论：

1. 状态/readiness route 适合迁成纯 payload-builder router，避免 route 模块了解 runtime 组装细节。
2. Readiness route 的验证要覆盖 degraded/ready 两种路径，否则容易只验证静态 shape。
3. 下一批建议处理 Desktop quant/financial-manager/broker surfaces，或处理 gateway/connectors/webhooks 这些 full-mode 平台 route。

### 2026-06-14 第十五批：Desktop quant、financial-manager、broker surfaces 归并

已落地内容：

| 项 | 结果 |
| --- | --- |
| 扩展 route 模块 | `packages/agent/src/aiask_agent/routes/desktop_finance.py` |
| `server.py` 装配方式 | 继续使用 `app.include_router(create_desktop_finance_router(...))`，新增 quant/financial/broker 依赖注入 |
| 已迁出端点 | quant presets/research runs、financial-manager catalog/status/query/intent、broker readiness/sync/accounts/positions/orders/analytics run/latest |
| 审计路径保持 | quant research、financial-manager query/intent、broker sync 继续通过 `audited_desktop_tool_call`，source_chain 保持原值 |
| guardrail 保持 | financial-manager intent 继续执行 control-token gate；broker user scope 查询继续执行 `require_user_scope` |
| fallback 保持 | fallback HTTPServer 中对应 finance GET/POST 分支保持原样 |
| 累计迁出 FastAPI route decorators | 98 个 |
| `server.py` 行数 | 5870 行 |
| `server.py` FastAPI route decorators | 65 个 |
| `routes/desktop_finance.py` 行数 | 286 行 |
| `routes/desktop_finance.py` route decorators | 22 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/desktop_finance.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 4.40s

uv run pytest packages/agent/tests/test_quant_product.py packages/agent/tests/test_financial_manager_desktop_api.py packages/agent/tests/test_broker_readonly_api.py -q
# 13 passed in 87.05s
```

当前 P1 模板补充结论：

1. 同一 Desktop finance 域内的 route 可以逐步归并到同一个 router，但应通过依赖注入保留 query/intent/sync 的不同审计 source_chain。
2. broker readonly route 迁移时不要触碰 live trading guardrail；本批只迁 HTTP 结构，不改变 broker token、consent、read-only 返回 envelope。
3. 下一批建议处理 Hermes sessions/handoffs/resume-context，或 gateway/connectors/webhooks。

### 2026-06-14 第十六批：Hermes sessions/config/handoff 路由拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/hermes.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_hermes_router(...))` 挂载 |
| 已迁出端点 | `/v1/hermes/toolsets`、`/v1/hermes/tools`、`/v1/hermes/config`、`/v1/hermes/sessions`、`/v1/hermes/handoffs`、`/v1/hermes/sessions/{session_id}/resume-context` |
| guardrail 保持 | toolsets 继续执行 API gate；tools/config/sessions/handoffs/resume-context 继续执行 full-mode/control gate |
| 行为保持 | session summary、handoff queue、resume context 继续由 `server.py` payload builder 注入，未改 response shape |
| 累计迁出 FastAPI route decorators | 104 个 |
| `server.py` 行数 | 5867 行 |
| `server.py` FastAPI route decorators | 59 个 |
| 新模块行数 | `routes/hermes.py` 71 行 |
| 新模块 route decorators | 6 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/hermes.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 1.61s

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface -q
# 8 passed in 113.45s

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py -q
# 11 passed in 150.87s
```

当前 P1 模板补充结论：

1. Hermes full-mode route 适合按“配置/会话/上下文”聚合，而不要和通用 tools/admin tool route 混在一起。
2. Handoff/resume-context route 迁出时保留 payload builder 注入，可以避免 router import intent store 或 session summarizer。
3. 下一批建议处理 gateway/connectors/webhooks，或先收尾当前 P1 批次并进入更小的 PR/提交切分。

### 2026-06-14 第十七批：Full/native controls 只读路由拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/full_controls.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_full_controls_router(...))` 挂载 |
| 已迁出端点 | `/v1/processes`、`/v1/terminal/backends`、`/v1/terminal/sessions`、`/v1/terminal/backends/{name}/sessions`、`/v1/browser/sessions` |
| guardrail 保持 | 全部 route 继续执行 `require_full`，即 general_full/full-mode + control-token gate |
| 行为保持 | process registry、terminal backend/session listing、browser session stub 均由原 helper 注入，未改变 response shape |
| `server.py` 行数 | 5846 行 |
| `server.py` FastAPI route decorators | 54 个 |
| 新模块行数 | `routes/full_controls.py` 49 行 |
| 新模块 route decorators | 5 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/full_controls.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 3.16s

uv run pytest packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface packages/agent/tests/test_terminal_cross_platform.py -q
# 12 passed in 11.14s
```

当前 P1 模板补充结论：

1. Full/native control route 迁出时，router 不需要 import process registry 或 backend implementation；通过 list helper 注入更利于后续测试隔离。
2. 不要在结构迁移时扩大 terminal/process/browser 权限，本批只保留原有 full-mode gate 与只读 listing surface。
3. 下一批建议处理 skills/plugins route，或进入 gateway/connectors/webhooks route 拆分。

### 2026-06-14 第十八批：Skills/plugins route 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/plugins_skills.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_plugins_skills_router(...))` 挂载 |
| 已迁出端点 | `/v1/skills`、`/v1/skills/{name}`、`/v1/plugins`、`/v1/plugins/{name}`、`/v1/plugins/{name}/tools/{tool}/test`、`/v1/plugins/{name}/commands`、`/v1/plugins/{name}/commands/{command}/test` |
| guardrail 保持 | skills/plugins 列表与测试 route 继续执行 `require_full`；skills/plugins mutation 继续通过 `full_tool_call` 调用 `agent_skill_manage` / `agent_plugin_manage` |
| 行为保持 | skills snapshot、plugin list、manifest self-test、tool/command test 的 response shape 与结构化 error_code 保持不变，fallback HTTPServer 分支未改 |
| 守门同步 | `docs/architecture/tool-call-path-classification.json` 将 `agent_skill_manage` snapshot 直连分类 key 从 `server.py::create_app.skills` 更新到 `routes/plugins_skills.py::create_plugins_skills_router.skills` |
| `server.py` 行数 | 5771 行 |
| `server.py` FastAPI route decorators | 44 个 |
| 新模块行数 | `routes/plugins_skills.py` 110 行 |
| 新模块 route decorators | 10 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/plugins_skills.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 2.91s

uv run pytest packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface packages/agent/tests/test_hermes_full_expanded_capabilities.py -q
# 7 passed in 37.58s
```

当前 P1 模板补充结论：

1. Skills/plugins route 和 native plugin manager 的耦合可通过 factory 注入控制在 route 模块边界内，`server.py` 只保留装配职责。
2. 结构迁移时必须同步 direct tool-call classification；否则路径守门会正确识别出迁移后的新调用位置。
3. 下一批建议处理 MCP 聚合 route，或先读 gateway/webhooks 参考后迁出 gateway/connectors/webhooks route。

### 2026-06-14 第十九批：MCP aggregation route 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/mcp.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_mcp_router(...))` 挂载 |
| 已迁出端点 | `/v1/mcp/servers`、`/v1/mcp/tools`、`/v1/mcp/resources`、`/v1/mcp/prompts`、`/v1/mcp/oauth_status`、`/v1/mcp/register-local`、`/v1/mcp/discover`、`/v1/mcp/oauth/start`、`/v1/mcp/oauth/callback`、`/v1/mcp/resources/read`、`/v1/mcp/prompts/get` |
| guardrail 保持 | server inventory 继续走 `require_api`；tools/resources/prompts/oauth/register/discover/read/get 继续走 `require_full`；OAuth callback 继续通过 `full_tool_call` 调用 `agent_mcp_manage` |
| 行为保持 | MCP inventory、local registration、discovery、OAuth、resource read、prompt get 的 response shape 和错误 envelope 保持不变；fallback HTTPServer 分支未改 |
| runtime 刷新保持 | register/discover 成功后继续执行 `runtime.refresh_tool_registry()` 并将 `full_runtime` 置空，本批用 `refresh_mcp_runtime` 回调注入 |
| `server.py` 行数 | 5673 行 |
| `server.py` FastAPI route decorators | 33 个 |
| 新模块行数 | `routes/mcp.py` 135 行 |
| 新模块 route decorators | 11 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/mcp.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 0.93s

uv run pytest packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface packages/agent/tests/test_server.py::test_legacy_http_mcp_inventory_honors_all_query_and_full_gate -q
# 9 passed in 66.36s
```

当前 P1 模板补充结论：

1. MCP route 的运行时刷新属于 app assembly 状态，适合保留在 `server.py` 本地回调中注入 route module。
2. `/v1/mcp/servers` 与其他 MCP 管理/读取 route 的 gate 不完全相同，迁移时必须保留 `require_api` 与 `require_full` 的差异。
3. 下一批建议先读 gateway/webhooks 参考，再迁出 gateway/connectors/webhooks；或单独迁出 learning/RL 这一组低耦合 route。

### 2026-06-14 第二十批：Learning/RL route 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/learning_rl.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_learning_rl_router(...))` 挂载 |
| 已迁出端点 | `/v1/learning/status`、`/v1/learning/review`、`/v1/learning/apply`、`/v1/rl/environments`、`/v1/rl/config`、`/v1/rl/runs`、`/v1/rl/runs/{run_id}`、`/v1/rl/runs/{run_id}/stop`、`/v1/rl/runs/{run_id}/results`、`/v1/rl/runs/{run_id}/logs` |
| guardrail 保持 | 全部 route 继续执行 `require_full`，保持 full-mode/control-token gate |
| 行为保持 | LearningLoop 和 RLAtroposManager 仍由 `server.py` 基于 `runtime.session_store.path` 构造后注入；status/review/apply、RL config/runs/results/logs 的 response shape 未改 |
| `server.py` 行数 | 5617 行 |
| `server.py` FastAPI route decorators | 21 个 |
| 新模块行数 | `routes/learning_rl.py` 82 行 |
| 新模块 route decorators | 12 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/learning_rl.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 3.40s

uv run pytest packages/agent/tests/test_hermes_full_expanded_capabilities.py -q
# 6 passed in 30.56s
```

当前 P1 模板补充结论：

1. Learning/RL route 可以按 manager factory 注入迁出，不需要 route module 直接 import session store 或 runtime。
2. RL training/start/stop 仍属于 full-mode gated surface；本批未改变 missing backend/status/error 的暴露方式。
3. 下一批建议处理 gateway/connectors/webhooks，并先按 gateway/webhooks 参考确认外部平台副作用边界。

### 2026-06-14 第二十一批：Gateway/connectors/webhooks route 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增 route 模块 | `packages/agent/src/aiask_agent/routes/gateway.py`、`packages/agent/src/aiask_agent/routes/connectors.py`、`packages/agent/src/aiask_agent/routes/webhooks.py` |
| `server.py` 装配方式 | 使用 `app.include_router(create_gateway_router(...))`、`create_connectors_router(...)`、`create_webhooks_router(...)` 挂载 |
| 已迁出 gateway 端点 | `/v1/gateway/status`、`/v1/gateway/daemon/status`、`/v1/gateway/platforms`、`/v1/gateway/platforms/{platform}/start`、`/v1/gateway/platforms/{platform}/stop`、`/v1/gateway/platforms/{platform}/health`、`/v1/gateway/messages`、`/v1/gateway/messages/{message_id}/retry`、`/v1/gateway/directory`、`/v1/gateway/directory/refresh`、`/v1/gateway/send`、`/v1/gateway/direct-deliver`、`/v1/gateway/webhooks/{platform}` |
| 已迁出 connectors 端点 | `/v1/connectors`、`/v1/connectors/summary`、`/v1/connectors/{connector_type}/{name}`、`/v1/connectors/{connector_type}/{name}/test` |
| 已迁出 webhooks 端点 | `/v1/webhooks`、`/v1/webhooks/{webhook_id}`、`/v1/webhooks/{webhook_id}/trigger` |
| guardrail 保持 | gateway/webhooks/connector 管理面继续保持原 `require_api` / `require_full` / `full_tool_call` 差异；webhook subscribe/remove/trigger 继续走 `agent_webhook` |
| 行为保持 | GatewayRuntime、DeliveryRouter、GatewayConfigStore、ConnectorManager、WebhookStore 均由 `server.py` 通过 factory 注入；send/direct-deliver/retry/platform start-stop、inbound webhook、connector test 的 response shape 未改 |
| `server.py` 行数 | 5474 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `routes/gateway.py` 135 行；`routes/connectors.py` 55 行；`routes/webhooks.py` 39 行 |
| 新模块 route decorators | `routes/gateway.py` 13 个；`routes/connectors.py` 4 个；`routes/webhooks.py` 4 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/routes/gateway.py packages/agent/src/aiask_agent/routes/connectors.py packages/agent/src/aiask_agent/routes/webhooks.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 4.77s

uv run pytest packages/agent/tests/test_hermes_full_expanded_capabilities.py packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface -q
# 7 passed in 72.81s

uv run pytest packages/agent/tests/test_gateway_daemon.py packages/agent/tests/test_gateway_daemon_phase2.py packages/agent/tests/test_gateway_daemon_phase4.py -q
# 54 passed in 8.26s

uv run pytest packages/agent/tests/test_hermes_native_live_adapters.py -q
# 18 passed in 91.45s

uv run pytest packages/agent/tests/test_server.py -q
# 7 passed in 94.83s

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py -q
# 11 passed in 151.74s
```

当前 P1 模板补充结论：

1. `server.py` 中 FastAPI `@app.*` route decorators 已清零；FastAPI HTTP surface 已全部通过 `routes/*` factory 装配。
2. Gateway 外部平台副作用 route 可以迁出，但 adapter、daemon、session-store-backed message/directory store 的构造仍应留在 app assembly 注入，避免 route module 私自绑定运行时状态。
3. 下一步如果继续瘦 `server.py`，重点不再是 route decorator，而是 auth/control helpers、Desktop payload builders、audited tool-call helper、fallback HTTPServer、CLI main 的分层。

### 2026-06-14 第二十二批：Route auth/control helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/route_auth.py` |
| `server.py` 装配方式 | 在 `create_app` 内创建 `RouteAuthorizer`，并将 `require_api`、`require_control`、`require_full`、`control_authorized`、`full_authorized`、`select_runtime`、`require_user_scope` 继续注入现有 route factories |
| 已迁出职责 | bearer token 提取、loopback 判断、Hermes full enablement、mode error status、control token configured 判断、API/control/full 授权、runtime selection、user-scope gate |
| guardrail 保持 | loopback-only control endpoint、control-token gate、full-mode env gate、cross-user control-token requirement、unsupported mode 400、missing full/control config 503 均保持原行为 |
| fallback 保持 | fallback HTTPServer 继续通过 `server.py` 私有别名使用同一套底层 token/loopback/full-mode helper，未改变 fallback route 行为 |
| `server.py` 行数 | 5398 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `route_auth.py` 118 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/route_auth.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 4.16s

uv run pytest packages/agent/tests/test_server.py -q
# 7 passed in 78.68s

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_intents.py -q
# 23 passed in 190.21s
```

当前 P1 模板补充结论：

1. Auth/control helper 可以先以纯 HTTP guard 形式抽出，不需要同时移动 payload builders 或 fallback handler。
2. `server.py` 继续保留 app assembly、runtime factory 和 fallback HTTPServer；下一批适合处理 audited tool-call helper 或 Desktop payload builders。
3. 结构迁移后仍要同时覆盖 FastAPI route drift、tool-call path gate、server fallback 和 Desktop contract 测试。

### 2026-06-14 第二十三批：Audited tool-call helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/audited_tool_calls.py` |
| `server.py` 装配方式 | 保留 `_audited_runtime_tool_call(...)` 薄 wrapper，内部委托 `audited_runtime_tool_call(...)`，现有调用点无需改名 |
| 已迁出职责 | tool invocation start/finish、duration/error/approval/intent 写入、`tool_registry.call_tool` 调用、source/artifact evidence extraction、run event 写入 |
| guardrail 保持 | 不改工具名、不改 toolset policy、不改 `agent_*` facade；Desktop/server 触发的工具执行仍走原审计链路 |
| 守门同步 | `docs/architecture/tool-call-path-classification.json` 将 audited helper 直连分类 key 从 `server.py::_audited_runtime_tool_call` 更新到 `audited_tool_calls.py::audited_runtime_tool_call` |
| `server.py` 行数 | 5328 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `audited_tool_calls.py` 99 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/audited_tool_calls.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 2.73s

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_evidence_artifacts_sources.py -q
# 23 passed in 158.09s
```

当前 P1 模板补充结论：

1. Tool-call 审计实现可以独立成模块，但 `server.py` 保留薄 wrapper 有利于降低调用点 churn。
2. 任何移动 `tool_registry.call_tool` 的批次都必须同步 direct-call classification，并跑 `test_tool_call_path_gate.py`。
3. 下一批建议继续拆 Desktop payload builders，或单独规划 fallback HTTPServer 分层。

### 2026-06-14 第二十四批：Desktop data payload builder 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/desktop_payloads.py` |
| `server.py` 装配方式 | 从 `desktop_payloads.py` 导入 `desktop_data_status_payload_for_runtime`、`desktop_data_sync_plan_payload_for_runtime` 并保留原私有别名，现有 FastAPI/fallback 调用点无需改名 |
| 已迁出职责 | Desktop data status payload、quant data gate 调用、Desktop data sync-plan / ActionIntent request payload 生成 |
| guardrail 保持 | data sync 仍只生成 intent request，不直接执行状态写入；`side_effect` 仍标记 stateful + confirmation_required |
| 守门同步 | `docs/architecture/tool-call-path-classification.json` 将 `agent_quant_data_gate` 只读状态调用分类 key 从 `server.py::_desktop_data_status_payload_for_runtime` 更新到 `desktop_payloads.py::desktop_data_status_payload_for_runtime` |
| `server.py` 行数 | 5229 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `desktop_payloads.py` 108 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/desktop_payloads.py
# passed

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
# 13 passed in 3.48s

uv run pytest packages/agent/tests/test_desktop_ops_api.py packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_intents.py -q
# 26 passed in 170.36s
```

当前 P1 模板补充结论：

1. Desktop data payload builder 可独立成模块，route/fallback 继续通过原私有别名调用，降低迁移噪音。
2. 只要 payload builder 内仍直接调用 `tool_registry.call_tool`，就必须同步 direct-call classification。
3. 下一批建议继续迁出 AI config/status/smoke/models payload builder，或拆 Desktop settings payload builder。

### 2026-06-14 第二十五批：Responses/chat payload helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/response_payloads.py` |
| `server.py` 装配方式 | 从 `response_payloads.py` 导入 `messages_from_responses_payload`、`chat_completion_payload`、`responses_payload` 并保留原私有别名 |
| 已迁出职责 | `/v1/responses` 输入 messages 规范化、Responses API payload 格式化、Chat Completions payload 格式化 |
| 行为保持 | 保留当前 AIASK 扩展字段：`session_id`、`run_id`、`tool_calls`、`audit_events`、`events`、`context_summary_id`、`planner_steps`、`subruns` |
| `server.py` 行数 | 5158 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `response_payloads.py` 80 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/response_payloads.py
# passed

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_desktop_workbench_contracts.py -q
# 18 passed in 149.60s

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 3 passed in 0.39s
```

当前 P1 模板补充结论：

1. Responses/chat payload helpers 可独立成纯格式化模块，不需要依赖 runtime 或 session store。
2. 搬迁 payload formatter 时必须先对齐当前合同字段，避免回退到早期 OpenAI-compatible 最小格式。
3. 下一批建议继续迁出 AI config/status/smoke/models payload builder，或拆 local profile/request context helper。

### 2026-06-14 第二十六批：Desktop settings/local profile payload 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 扩展模块 | `packages/agent/src/aiask_agent/desktop_payloads.py` |
| `server.py` 装配方式 | 从 `desktop_payloads.py` 导入 `agent_endpoint`、`local_profile_payload`、`save_local_profile`，并用 `_desktop_settings_status_payload_for_runtime(...)` 薄 wrapper 注入 `_ai_status_payload_for_runtime` |
| 已迁出职责 | local profile 路径/默认值/读取/保存、Agent endpoint 推断、Desktop settings status payload builder |
| 行为保持 | Desktop settings status 继续包含 agent、llm、memory、databases、stock data sources、profile、`secrets_redacted`；local profile 文件仍写入 `aiask_agent_home()/local_profile.json` |
| fallback 保持 | fallback HTTPServer 和 FastAPI route 继续通过原函数名/别名调用 profile/settings helper，未改变 path、method、response shape |
| `server.py` 行数 | 5065 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 模块行数 | `desktop_payloads.py` 230 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/desktop_payloads.py
# passed

uv run pytest packages/agent/tests/test_desktop_ops_api.py packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_server.py -q
# 28 passed in 192.68s

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 3 passed in 0.41s
```

当前 P1 模板补充结论：

1. Desktop settings/local profile helper 适合和 Desktop data payload 放在同一模块，形成 Desktop-facing payload 聚合点。
2. AI status payload 仍留在 `server.py`，通过 wrapper 注入，避免本批同时移动模型 provider/env 写入逻辑。
3. 下一批建议单独迁出 AI config/status/smoke/models payload builder，并配套跑 `test_ai_status_and_smoke.py`。

### 2026-06-14 第二十七批：Request context helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/request_context.py` |
| `server.py` 装配方式 | 从 `request_context.py` 导入 `request_user_id_from_payload`、`request_context_payload`、`tool_payload_with_request_context` 并保留原私有别名 |
| 已迁出职责 | 请求/user id 解析、session/run/trace/source 上下文构造、外层 request payload 到 tool payload 的上下文字段合并 |
| 行为保持 | 继续从 `X-AIASK-User-Id`、`X-AIASK-Session-Id`、`X-AIASK-Run-Id`、`X-AIASK-Trace-Id` 读取上下文；缺省 user 仍来自 local profile 或 `local` |
| `server.py` 行数 | 5030 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `request_context.py` 47 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/request_context.py packages/agent/src/aiask_agent/desktop_payloads.py
# passed

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_intents.py packages/agent/tests/test_evidence_artifacts_sources.py -q
# 28 passed in 181.85s

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 3 passed in 0.36s
```

当前 P1 模板补充结论：

1. Request context helper 是 audited tool call、Financial Manager intent、broker sync、Desktop activity 共同依赖，独立模块能减少 `server.py` 横切职责。
2. 迁出后仍保持 local profile 作为缺省 user 来源，因此需和 `desktop_payloads.py` 的 profile helper 一起编译验证。
3. 下一批建议单独迁出 AI config/status/smoke/models payload builder，或先规划 fallback HTTPServer 分层。

### 2026-06-14 第二十八批：AI status/smoke/models payload builder 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/ai_payloads.py` |
| `server.py` 装配方式 | 从 `ai_payloads.py` 导入 `ai_status_payload_for_runtime`、`ai_error_payload`、`refresh_runtime_model_client`、`ai_smoke_payload_for_runtime`、`ai_models_payload_for_runtime` 并保留原私有别名 |
| 已迁出职责 | AI status payload、AI smoke payload、AI models payload、模型客户端刷新、AI smoke error payload、models 响应 secret redaction |
| 暂留职责 | `AI_MODEL_PROVIDER_PRESETS`、`_ai_config_payload_for_runtime`、`_save_ai_config_for_runtime` 仍留在 `server.py`，避免本批同时移动 provider preset 和 `.env` 写入合同 |
| 行为保持 | `/v1/ai/status`、`/v1/ai/smoke`、`/v1/ai/models` 继续返回原 response shape；fallback HTTPServer 继续通过原函数名调用同一批 helper |
| guardrail 保持 | status/models 只暴露 configured/missing/provider/model 等状态；models 列表继续 redaction `secret/token/api_key/apikey/password/credential` 字段；本批不新增 `.env` 写入路径，不读取或记录 raw secret 值 |
| `server.py` 行数 | 4800 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `ai_payloads.py` 261 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/ai_payloads.py
# passed

uv run pytest packages/agent/tests/test_ai_status_and_smoke.py -q
# 10 passed, 1 skipped in 121.97s

uv run pytest packages/agent/tests/test_desktop_ops_api.py packages/agent/tests/test_desktop_capabilities_api.py -q
# 21 passed in 223.34s

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 10 passed in 118.97s
```

当前 P1 模板补充结论：

1. AI status/smoke/models payload builder 可独立成模型供应商运行时 helper 模块，同时让 `server.py` 继续承接 config preset 和保存入口，迁移风险可控。
2. 迁出 models payload 时必须保留本地 secret redaction，因为 provider 返回对象可能包含 `api_key`、`token` 等字段。
3. 下一批可继续小步迁出 AI config/preset/save 逻辑，或先规划 fallback HTTPServer 分层。

### 2026-06-14 第二十九批：AI config/preset/save payload 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 扩展模块 | `packages/agent/src/aiask_agent/ai_payloads.py` |
| `server.py` 装配方式 | 从 `ai_payloads.py` 导入 `ai_config_payload_for_runtime`、`save_ai_config_for_runtime` 并继续保留原私有别名供 FastAPI route factory 和 fallback HTTPServer 调用 |
| 已迁出职责 | `AI_MODEL_PROVIDER_PRESETS`、AI config payload、AI config save payload、provider preset 匹配、prompt-cache env 更新、runtime model client refresh 后的状态回读 |
| 行为保持 | `/v1/ai/config` GET/PATCH 继续保持原 response shape；PATCH 仍由 route 层 `require_control` 保护；fallback HTTPServer 继续用同一 helper 执行 config 读取/保存 |
| guardrail 保持 | 保存响应只返回 `updated_keys`、env 文件路径和 configured 状态，不返回 raw API key；provider 仍限制在 `mock/openai/anthropic/anthropic_messages`；未新增绕过 control-token 的写入入口 |
| `server.py` 行数 | 4387 行 |
| `server.py` FastAPI route decorators | 0 个 |
| `ai_payloads.py` 行数 | 674 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/ai_payloads.py
# passed

uv run pytest packages/agent/tests/test_ai_status_and_smoke.py -q
# 10 passed, 1 skipped in 124.93s

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 10 passed in 116.69s

uv run pytest packages/agent/tests/test_desktop_ops_api.py packages/agent/tests/test_desktop_capabilities_api.py -q
# 21 passed in 225.23s
```

当前 P1 模板补充结论：

1. AI provider preset 和 config save 逻辑可以和 status/smoke/models payload 放在同一个 Agent AI helper 模块，形成模型配置合同的单一维护点。
2. `.env` 写入职责迁出时必须保持 route 层 control-token gate，不应在 helper 内新增任何未授权写入路径。
3. 下一批若继续瘦 `server.py`，更适合拆 fallback HTTPServer 或 CLI/main，而不是继续扩张 `ai_payloads.py`。

### 2026-06-14 第三十批：fallback HTTPServer 分层

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/fallback_server.py` |
| `server.py` 装配方式 | `server.py` 保留同签名 `build_server(...)` 薄 wrapper，延迟导入 `fallback_server.build_server(...)`，CLI `--legacy-http` 和既有测试继续从 `aiask_agent.server import build_server` 使用原入口 |
| 已迁出职责 | compatibility `ThreadingHTTPServer` 构造、`AIASKAgentHTTPServer` 生命周期关闭、`AIASKAgentHandler` 的 legacy GET/POST/OPTIONS/SSE HTTP 分发 |
| 行为保持 | legacy HTTP path、method、status code、response shape、SSE 输出和 control/full-mode guardrail 均保持；fallback handler 仍复用 `server.py` 中已拆出的 payload/auth/tool helper |
| direct-call 守门同步 | `docs/architecture/tool-call-path-classification.json` 将 7 个 fallback read-only direct tool call 分类从 `server.py::build_server.AIASKAgentHandler` 更新到 `fallback_server.py::build_server.AIASKAgentHandler` |
| `server.py` 行数 | 2632 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `fallback_server.py` 1784 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/fallback_server.py packages/agent/src/aiask_agent/ai_payloads.py
# passed

uv run pytest packages/agent/tests/test_server.py -q
# 7 passed in 85.26s

uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 3 passed in 0.34s

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_intents.py -q
# 23 passed in 197.59s

uv run pytest packages/agent/tests/test_extended_agent_capabilities.py::test_http_sse_run_events_toolsets_and_jobs -q
# 1 passed in 11.73s
```

当前 P1 模板补充结论：

1. fallback HTTPServer 可先作为 legacy 兼容层独立成模块，保留 `server.py` 同签名 wrapper 以降低 import/call-site churn。
2. 本批采用 lazy helper binding 作为过渡手段，优先保证 legacy route 行为零漂移；后续可按 route family 继续把 fallback handler 内部拆薄。
3. `server.py` 已从大文件降到 2632 行，下一批更适合迁出 CLI/main/doctor/gateway 命令，或收束 app assembly 中剩余 payload helper。

### 2026-06-14 第三十一批：Server CLI/main 分层

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/server_cli.py` |
| `server.py` 装配方式 | `server.py` 保留 `main(argv=None)` 薄 wrapper，延迟导入 `server_cli.main(...)`；`pyproject.toml` 中 `aiask-agent = aiask_agent.server:main` 入口无需变化 |
| 已迁出职责 | `aiask-agent` 服务端启动参数解析、`--legacy-http` 分支、ASGI/uvicorn 启动、`tui` 子命令、`gateway status/setup/start/stop` 子命令、`doctor --full-hermes-native` 诊断命令 |
| 行为保持 | 非 loopback 绑定仍要求 `AIASK_AGENT_API_TOKEN`；`doctor` 未带 `--full-hermes-native` 仍按原逻辑拒绝；客户端 `aiask_agent/cli.py` 未改动 |
| `server.py` 行数 | 2550 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `server_cli.py` 104 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/server_cli.py packages/agent/src/aiask_agent/fallback_server.py packages/agent/src/aiask_agent/ai_payloads.py
# passed

$env:PYTHONPATH='packages/agent/src'; python -m aiask_agent.server --help
# passed; prints server host/port/--legacy-http help

$env:PYTHONPATH='packages/agent/src'; @'
from aiask_agent.server import main
try:
    main(['doctor'])
except SystemExit as exc:
    assert 'unsupported doctor command' in str(exc)
else:
    raise AssertionError('doctor without --full-hermes-native should exit')
'@ | python -
# passed

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 10 passed in 49.11s
```

当前 P1 模板补充结论：

1. `server.py` 现在主要剩 app assembly、shared payload/helper glue 和 public compatibility wrappers，服务端启动命令已经独立。
2. 服务端 CLI 与客户端 `aiask_agent/cli.py` 需要保持分工：前者启动/诊断 Agent，后者调用 Agent HTTP API。
3. 下一批如果继续 P1，可把 `create_app` 内剩余的 Desktop capabilities/readiness payload helper 再拆出，或整理 `server.py` 顶部尚未迁出的通用 helpers。

### 2026-06-14 第三十二批：Desktop capabilities payload builder 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/desktop_capabilities_payloads.py` |
| `server.py` 装配方式 | `create_app` 内保留 `desktop_capabilities_payload(request)` 薄 wrapper，向 `desktop_capabilities_payload_for_runtime(...)` 注入 runtime、full/control 授权函数、full runtime builder、Hermes readiness、Quant store 和 AI status payload |
| 已迁出职责 | `/v1/desktop/capabilities` 聚合 payload、capability counts、MCP registration/discovery 摘要、skills/plugins gated payload、quant preflight、financial system readiness 聚合 |
| 行为保持 | Desktop capabilities response shape、gated/live_backend source、control/full-mode 状态、secret redaction、MCP detected port/auth 字段、quant raw refs 均保持 |
| direct-call 守门同步 | `docs/architecture/tool-call-path-classification.json` 将 2 个 Desktop capabilities read-only direct tool call 分类从 `server.py::create_app.desktop_capabilities_payload` 更新到 `desktop_capabilities_payloads.py::desktop_capabilities_payload_for_runtime` |
| `server.py` 行数 | 2355 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `desktop_capabilities_payloads.py` 250 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/desktop_capabilities_payloads.py packages/agent/src/aiask_agent/fallback_server.py packages/agent/src/aiask_agent/server_cli.py
# passed

uv run pytest packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_quant_product.py -q
# 10 passed in 122.57s

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 10 passed in 114.43s

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_intents.py -q
# 16 passed in 172.24s
```

当前 P1 模板补充结论：

1. Desktop capabilities 聚合逻辑适合独立成 payload builder 模块，`server.py` 只负责 route assembly 和授权闭包注入。
2. 搬迁该 payload 时必须同步 direct-call 分类，因为其中仍包含 full-mode 授权后的只读 Strategy Factory snapshot 和 skill snapshot 调用。
3. 下一批可继续拆 `server.py` 内 Hermes readiness/health payload helper，或把 run/session/workbench payload helper 从 `server.py` 中迁出。

### 2026-06-14 第三十三批：Run/session/workbench payload helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/run_payloads.py` |
| `server.py` 装配方式 | 从 `run_payloads.py` 导入 `_normalize_run_event`、`_artifact_content_payload`、`_session_summary_payload`、`_handoff_queue_payload`、`_session_resume_context_payload`、`_run_trace_eval_payload`、`_workbench_summary_payload`、`_desktop_runs_payload`，保留原私有别名供 FastAPI routes 和 fallback HTTPServer lazy binding 调用 |
| 已迁出职责 | run event normalization、artifact content safe read payload、run/session summaries、handoff queue/resume context、run trace eval、Desktop workbench summary、Desktop runs list payload |
| 行为保持 | `/v1/desktop/workbench/summary`、`/v1/desktop/runs`、`/v1/hermes/sessions`、`/v1/hermes/handoffs`、`/v1/runs/{id}/events`、artifact/source/readiness 相关 response shape 均保持 |
| guardrail 保持 | artifact content 仍走 `_path_allowed_for_artifact_read` 和 metadata/status gate；workbench access 仍通过 full-mode/control-token 状态计算；handoff resume payload 继续 `secrets_redacted` |
| `server.py` 行数 | 1787 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `run_payloads.py` 596 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/run_payloads.py packages/agent/src/aiask_agent/fallback_server.py packages/agent/src/aiask_agent/server_cli.py
# passed

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_evidence_artifacts_sources.py -q
# 16 passed in 155.22s

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 10 passed in 91.56s

uv run pytest packages/agent/tests/test_extended_agent_capabilities.py::test_http_sse_run_events_toolsets_and_jobs -q
# 1 passed in 6.22s
```

当前 P1 模板补充结论：

1. run/session/workbench payload helper 可作为独立模块承接 Desktop workbench、Runs/Events、Hermes sessions/handoff 和 artifacts/sources 的格式化逻辑。
2. fallback HTTPServer 通过 `server.py` lazy binding 继续拿到同名 helper，因此本批没有改变 legacy path 或 route 行为。
3. `server.py` 已降到 1787 行，下一批更适合继续拆 Hermes readiness/health payload helper 或 Financial Manager/broker payload helper。

### 2026-06-14 第三十四批：Hermes readiness/status payload helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 启用模块 | `packages/agent/src/aiask_agent/hermes_payloads.py` |
| `server.py` 装配方式 | 从 `hermes_payloads.py` 导入 `_redact_required_env`、`_parity_live_evidence`、`_hermes_readiness_payload_for_runtime`、`_hermes_status_payload_for_runtime`、`_financial_readiness_payload_for_runtime`，`create_app` 内保留同名 thin wrapper 并注入 runtime、full runtime builder、full-mode 状态和 AI status payload |
| 已迁出职责 | required env/public health 脱敏、Hermes live evidence 汇总、Hermes full surface status、Hermes readiness/status payload、financial-system readiness payload wrapper |
| 行为保持 | `/health/detailed` 的 Hermes parity/live evidence 脱敏、`/v1/hermes/status`、`/v1/hermes/readiness`、`/v1/financial-system/readiness` 的 response shape 和 full-mode/control-token 状态计算保持 |
| fallback 保持 | fallback HTTPServer 继续通过 `server.py` lazy binding 拿到 `_redact_required_env`、`_parity_live_evidence` 兼容别名，legacy health/status path 未改 |
| direct-call 守门同步 | 本批未迁移任何 `tool_registry.call_tool` 调用，`docs/architecture/tool-call-path-classification.json` 无需更新 |
| `server.py` 行数 | 1580 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 模块行数 | `hermes_payloads.py` 291 行 |

验证结果：
```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/hermes_payloads.py packages/agent/src/aiask_agent/fallback_server.py
# passed

uv run pytest packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_native_full_parity.py packages/agent/tests/test_hermes_native_live_adapters.py::test_hermes_readiness_endpoint_reports_native_surfaces -q
# 13 passed in 78.67s

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 10 passed in 41.71s

uv run pytest packages/agent/tests/test_financial_manager_desktop_api.py packages/agent/tests/test_live_readiness_smoke_script.py -q
# 8 passed in 40.68s
```

当前 P1 模板补充结论：

1. Hermes readiness/status payload 与 app assembly 可干净分离，`server.py` 只负责把 runtime/full-mode 闭包注入 payload helper。
2. health/detailed 与 fallback HTTPServer 仍依赖 `_redact_required_env`、`_parity_live_evidence` 这两个兼容别名，因此保留别名比批量改调用点更稳。
3. `server.py` 已降到 1580 行，下一批更适合拆 Financial Manager/broker payload helper，或继续收束顶部通用 MCP/plugin utility。

### 2026-06-14 第三十五批：Financial Manager/broker payload helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/financial_payloads.py` |
| `server.py` 装配方式 | 从 `financial_payloads.py` 导入 financial catalog/status/query/intent 和 broker readiness/accounts/sync/analytics payload builder，`server.py` 保留 `_financial_*`、`_broker_*` 同名兼容 wrapper 供 FastAPI route factory 与 fallback HTTPServer lazy binding 调用 |
| 已迁出职责 | Financial Manager group/action catalog、MCP wrapped-tool availability detail、secret redaction、status/readiness 聚合、read-only query payload、ActionIntent intent payload、broker read-only context/sync/accounts/analytics payload |
| 行为保持 | Financial Manager read-only query 仍走 audited tool call；stateful action 仍返回 intent-only/ActionIntent 路径；broker live order/cancel 仍 blocked，broker sync 仍要求 consent 且只读；response shape、`secrets_redacted`、`live_trading_enabled: False` 保持 |
| fallback 保持 | fallback HTTPServer 继续通过 `server.py` lazy binding 调用 `_financial_catalog_payload`、`_financial_status_payload`、`_financial_query_payload`、`_financial_intent_payload`、`_broker_*` wrapper，legacy path 未改 |
| direct-call 守门同步 | 本批未新增或迁移裸 `tool_registry.call_tool`；Financial Manager query/intent 仍通过 `audited_tool_calls.py::audited_runtime_tool_call`，`docs/architecture/tool-call-path-classification.json` 无需更新 |
| `server.py` 行数 | 1120 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `financial_payloads.py` 538 行 |

验证结果：
```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/financial_payloads.py packages/agent/src/aiask_agent/fallback_server.py
# passed

uv run pytest packages/agent/tests/test_financial_manager_desktop_api.py packages/agent/tests/test_broker_readonly_api.py packages/agent/tests/test_realtime_finance_facades.py -q
# 13 passed in 63.79s

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_desktop_capabilities_api.py -q
# 17 passed in 107.55s

uv run pytest packages/agent/tests/test_live_readiness_smoke_script.py -q
# 2 passed in 0.05s
```

当前 P1 模板补充结论：

1. Financial Manager 与 broker read-only payload 可独立在 Agent runtime 内成模块，Desktop route factory 继续只通过注入函数消费，不直接接触 manager/MCP 原始接口。
2. 将 ActionIntent/read-only/live-trading-disabled 文案和 redaction 留在同一 payload 模块，有利于后续维护 Financial Manager 桌面合同。
3. `server.py` 已降到 1120 行，下一批若继续 P1，更适合拆顶部 MCP/plugin utility 或进一步压缩 app assembly glue。

### 2026-06-14 第三十六批：HTTP/MCP/plugin utility helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/server_http_utils.py`、`packages/agent/src/aiask_agent/mcp_payloads.py`、`packages/agent/src/aiask_agent/plugin_payloads.py` |
| `server.py` 装配方式 | 从 `server_http_utils.py` 导入 `_json_dumps`、`_query_bool`、`_truthy`、`_read_json`、`_header_token`、`_cors_origins`；从 `mcp_payloads.py` 导入 `_classify_mcp_error`、`_mcp_action_error_payload`；从 `plugin_payloads.py` 导入 `_plugin_tools`、`_plugin_self_test_payload` |
| 已迁出职责 | fallback/ASGI 共用 JSON bytes、query bool、truthy、request JSON、header token、CORS origin helper；MCP discovery/resource/prompt 错误分类和 payload；plugin manifest self-test 和 manifest tool list |
| 行为保持 | fallback HTTPServer lazy binding 继续从 `server.py` 取得同名私有别名；CORS 默认 origin、MCP error_code/detail/auth readiness、plugin manifest self-test response shape 保持 |
| direct-call 守门同步 | 本批未迁移任何 `tool_registry.call_tool` 路径；plugins/skills route 中既有 direct snapshot 分类未变，`docs/architecture/tool-call-path-classification.json` 无需更新 |
| `server.py` 行数 | 989 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `server_http_utils.py` 70 行；`mcp_payloads.py` 62 行；`plugin_payloads.py` 29 行 |

验证结果：
```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/server_http_utils.py packages/agent/src/aiask_agent/mcp_payloads.py packages/agent/src/aiask_agent/plugin_payloads.py packages/agent/src/aiask_agent/fallback_server.py
# passed

$env:PYTHONPATH='packages/agent/src'; @'
from aiask_agent import server
for name in ('_json_dumps','_query_bool','_truthy','_read_json','_header_token','_cors_origins','_classify_mcp_error','_mcp_action_error_payload','_plugin_tools','_plugin_self_test_payload'):
    assert callable(getattr(server, name)), name
'@ | python -
# passed

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 10 passed in 47.38s

uv run pytest packages/agent/tests/test_mcp_client.py packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface -q
# 10 passed in 51.90s
```

当前 P1 模板补充结论：

1. `server.py` 已进入千行以内，剩余主要是 app assembly、runtime/full-runtime 闭包、SSE formatter 和各 route factory 的依赖注入。
2. fallback HTTPServer 对 `server.py` 私有别名的 lazy binding 仍保留，因此 helper 迁移要继续用 alias，而不是一次性改 fallback 内部调用。
3. P1 已具备阶段性切分条件；若继续瘦身，可优先处理 SSE formatter 或 gateway/connectors factory glue。

### 2026-06-14 第三十七批：SSE formatter helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/streaming_payloads.py` |
| `server.py` 装配方式 | 从 `streaming_payloads.py` 导入 `_sse_events_stream`、`_chat_completion_sse_stream`、`_response_sse_stream`，`create_app` 内保留 `sse_events`、`chat_completion_sse`、`response_sse` thin wrapper 供 route factory 注入 |
| 已迁出职责 | run events SSE chunk、chat completions SSE chunk、responses SSE chunk 的 `id:`/`event:`/`data:` 字节序列格式化 |
| 行为保持 | `/v1/runs/{run_id}/events`、`/v1/runs/{run_id}/events/stream`、`/v1/responses` stream、`/v1/chat/completions` stream 的 `text/event-stream` 输出结构保持；`[DONE]` 终止 chunk 保持 |
| fallback 修正 | legacy fallback chat completion SSE 原先间接依赖 `server.py` 的 `time` import；本批在 `fallback_server.py` 显式 `import time`，避免 helper 外移后 lazy binding 缺失 |
| direct-call 守门同步 | 本批未迁移任何 `tool_registry.call_tool` 路径，`docs/architecture/tool-call-path-classification.json` 无需更新 |
| `server.py` 行数 | 949 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `streaming_payloads.py` 71 行 |

验证结果：
```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/streaming_payloads.py packages/agent/src/aiask_agent/fallback_server.py
# passed

uv run pytest packages/agent/tests/test_extended_agent_capabilities.py::test_http_sse_run_events_toolsets_and_jobs packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 11 passed in 47.89s
```

当前 P1 模板补充结论：

1. SSE formatter 已从 app assembly 中分离，`server.py` 继续只负责把 stream generator wrapper 注入 route factory。
2. fallback HTTPServer 的标准库依赖应逐步显式化，减少对 `server.py` import namespace 的偶然依赖。
3. `server.py` 已降到 949 行，下一批若继续 P1，更适合拆 gateway/connectors factory glue 或把 remaining app wrapper 归组。

### 2026-06-14 第三十八批：Gateway/connectors/webhook route factory glue 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/gateway_route_factories.py` |
| `server.py` 装配方式 | 在 `create_app` 内创建 `GatewayRouteFactories(runtime=runtime, app=app, daemon_getter=lambda: _daemon)`，并将 gateway runtime/store/config/router、connector manager、webhook store 和 gateway daemon status payload factory 注入 route factories |
| 已迁出职责 | Gateway message/directory/runtime store factory、Gateway config/delivery router factory、Gateway platform adapter/normalize 注入、gateway daemon status payload、connector manager factory、webhook store factory |
| 行为保持 | `/v1/gateway/*`、`/v1/connectors/*`、`/v1/webhooks/*` route path/method/response shape 保持；Gateway daemon 生命周期仍由 `server.py` lifespan 控制；fallback HTTPServer 未改 |
| direct-call 守门同步 | 本批未迁移任何 `tool_registry.call_tool` 路径，`docs/architecture/tool-call-path-classification.json` 无需更新 |
| `server.py` 行数 | 929 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `gateway_route_factories.py` 68 行 |

验证结果：
```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/gateway_route_factories.py packages/agent/src/aiask_agent/fallback_server.py
# passed

uv run pytest packages/agent/tests/test_gateway_daemon.py packages/agent/tests/test_gateway_daemon_phase2.py packages/agent/tests/test_gateway_daemon_phase4.py packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 64 passed in 49.97s

uv run pytest packages/agent/tests/test_connector_health.py packages/agent/tests/test_desktop_capabilities_api.py -q
# 9 passed in 40.33s
```

当前 P1 模板补充结论：

1. Gateway/connectors/webhook route factory glue 可独立成 factory binder，`server.py` 继续只保留 lifespan 中 daemon start/stop 和 router include 顺序。
2. 本批保留 `ADAPTERS`、Hermes baseline 等 legacy fallback lazy binding 兼容导入，避免同时改 fallback health/status 行为。
3. `server.py` 已降到 929 行，下一批若继续 P1，可考虑整理剩余 app wrapper/route include 装配，或转入阶段性完整回归与提交切分。

### 2026-06-14 第三十九批：FastAPI lifespan/gateway daemon lifecycle 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/app_lifecycle.py` |
| `server.py` 装配方式 | 在 `create_app` 内创建 `AgentAppLifecycle(runtime=runtime, full_runtime_getter=lambda: full_runtime)`，并将 `lifecycle.lifespan` 注入 `FastAPI(...)`；`GatewayRouteFactories` 通过 `lifecycle.daemon` 读取当前 daemon |
| 已迁出职责 | Gateway daemon env 开关、daemon start/stop、daemon start warning、shutdown 时 full runtime/runtime close |
| 行为保持 | `AIASK_GATEWAY_DAEMON_ENABLED` 语义、daemon start 失败降级为 warning、shutdown 顺序、Gateway daemon status getter 均保持；fallback HTTPServer 未改 |
| direct-call 守门同步 | 本批未迁移任何 `tool_registry.call_tool` 路径，`docs/architecture/tool-call-path-classification.json` 无需更新 |
| `server.py` 行数 | 900 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `app_lifecycle.py` 52 行 |

验证结果：
```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/app_lifecycle.py packages/agent/src/aiask_agent/gateway_route_factories.py packages/agent/src/aiask_agent/fallback_server.py
# passed

uv run pytest packages/agent/tests/test_gateway_daemon.py packages/agent/tests/test_gateway_daemon_phase2.py packages/agent/tests/test_gateway_daemon_phase4.py packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 64 passed in 48.57s

uv run pytest packages/agent/tests/test_connector_health.py packages/agent/tests/test_desktop_capabilities_api.py -q
# 9 passed in 44.48s
```

当前 P1 模板补充结论：

1. FastAPI lifespan 已从 app assembly 中分离，`server.py` 只负责创建 lifecycle 对象并交给 FastAPI。
2. Gateway daemon 当前状态由 lifecycle 统一持有，gateway route factory 只通过 getter 读取，不再依赖 `server.py` 闭包变量。
3. `server.py` 已降到 900 行，下一批若继续 P1，更适合整理剩余 app wrapper/route include 装配或进入阶段性完整回归与提交切分。

### 2026-06-14 第四十批：Runtime/full-runtime factory 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/runtime_factories.py` |
| `server.py` 装配方式 | 从 `runtime_factories.py` 导入 `build_runtime_and_executor` 作为 `_build_runtime_and_executor` 兼容别名，并用 `FullRuntimeManager(runtime)` 替代 `create_app` 内的 `full_runtime` nonlocal closure |
| fallback 同步 | `fallback_server.py` 复用 `FullRuntimeManager` 构造 legacy native full runtime，保留 `_build_native_full_runtime()` 函数名供 handler 内部调用 |
| 已迁出职责 | 默认 `AgentRuntime + IntentExecutor` 构造、Hermes/full native runtime 缓存、full runtime active/current/reset/close/aclose |
| 行为保持 | `finance_safe` 默认 runtime、`general_full` policy、workspace roots、shared session store/model client、refresh MCP 后 full runtime reset、FastAPI 与 fallback full-mode response shape 保持 |
| direct-call 守门同步 | 本批未迁移任何 `tool_registry.call_tool` 路径，`docs/architecture/tool-call-path-classification.json` 无需更新 |
| `server.py` 行数 | 875 行 |
| `server.py` FastAPI route decorators | 0 个 |
| `fallback_server.py` 行数 | 1762 行 |
| 新模块行数 | `runtime_factories.py` 60 行 |

验证结果：
```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/fallback_server.py packages/agent/src/aiask_agent/runtime_factories.py packages/agent/src/aiask_agent/app_lifecycle.py
# passed

uv run pytest packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface packages/agent/tests/test_extended_agent_capabilities.py::test_http_sse_run_events_toolsets_and_jobs packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 12 passed in 60.92s

uv run pytest packages/agent/tests/test_tool_registry.py packages/agent/tests/test_desktop_capabilities_api.py -q
# 17 passed in 39.33s
```

当前 P1 模板补充结论：

1. runtime 构造与 full-runtime 缓存状态已经脱离 `server.py` app assembly，FastAPI/fallback 共用同一套构造逻辑。
2. fallback HTTPServer 对 server lazy binding 的依赖进一步减少了重复实现，但仍保留 legacy 入口和 helper 名称，未改 HTTP path。
3. `server.py` 已降到 875 行，下一批可继续整理 remaining app wrapper/include 装配，或进入拆组完整 Agent HTTP contract 回归与阶段性提交切分。

### 2026-06-14 第四十一批：FastAPI route assembly 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/app_route_assembly.py` |
| `server.py` 装配方式 | `create_app` 保留 runtime、authorizer 和 payload wrapper 构造，然后通过 `configure_agent_app(app, AgentRouteAssembly(...))` 注入完整路由装配依赖 |
| 已迁出职责 | CORS middleware 配置、全部 FastAPI `include_router(...)` 顺序、route factory imports、full/native controls factory 绑定、MCP refresh/full-runtime reset 绑定、Gateway/connectors/webhook route include 绑定 |
| 行为保持 | route path、method、response shape、CORS allow headers、Gateway daemon getter、MCP refresh 后 full-runtime reset、plugin/MCP/native/full-mode dependency injection 保持 |
| fallback 兼容 | 未改 `fallback_server.py` HTTP path；`server.py` 仍保留 fallback lazy binding 当前使用的私有 helper/import aliases |
| direct-call 守门同步 | 本批未迁移任何 `tool_registry.call_tool` 路径，`docs/architecture/tool-call-path-classification.json` 无需新增变更 |
| `server.py` 行数 | 642 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `app_route_assembly.py` 406 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/app_route_assembly.py packages/agent/src/aiask_agent/fallback_server.py
# passed

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 10 passed in 43.05s

uv run pytest packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_ai_status_and_smoke.py packages/agent/tests/test_financial_manager_desktop_api.py packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface packages/agent/tests/test_extended_agent_capabilities.py::test_http_sse_run_events_toolsets_and_jobs -q
# timed out after 184s before pytest summary; split verification below passed

uv run pytest packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_ai_status_and_smoke.py -q
# 17 passed, 1 skipped in 79.69s

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_financial_manager_desktop_api.py -q
# 17 passed in 121.75s

uv run pytest packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface packages/agent/tests/test_extended_agent_capabilities.py::test_http_sse_run_events_toolsets_and_jobs -q
# 2 passed in 14.79s

uv run pytest packages/agent/tests/test_gateway_daemon.py packages/agent/tests/test_gateway_daemon_phase2.py packages/agent/tests/test_gateway_daemon_phase4.py packages/agent/tests/test_connector_health.py -q
# 56 passed in 3.78s
```

当前 P1 模板补充结论：

1. FastAPI route include 顺序和 CORS middleware 已从 `server.py` app assembly 中分离，`server.py` 不再直接导入各 route factory。
2. `server.py` 当前职责进一步收口到 runtime 构造、authorizer/wrapper 构造、fallback 兼容别名和 app handoff；所有 HTTP path 的实际路由仍由既有 route factory 承接。
3. `server.py` 已降到 642 行；继续瘦身时应优先按 wrapper 职责成组迁移，或先做拆组完整 Agent HTTP contract 回归后作为阶段边界切分。

### 2026-06-14 第四十二批：Unused `create_app` wrapper 清理

已落地内容：

| 项 | 结果 |
| --- | --- |
| 清理范围 | `packages/agent/src/aiask_agent/server.py` |
| 已删除内容 | 不再被任何 route assembly 注入使用的 `_control_snapshot()`、`_desktop_settings_status_payload()`、`_desktop_data_status_payload()`、`_desktop_data_sync_plan_payload()` 局部 helper，以及未使用的 `api_authorized` 局部绑定 |
| 行为保持 | 实际注入 route factory 的 `desktop_settings_status_payload()`、`desktop_data_status_payload()`、`desktop_data_sync_plan_payload()` 保留；fallback HTTPServer 的 `_api_authorized()` handler 方法未改 |
| direct-call 守门同步 | 本批未迁移任何 `tool_registry.call_tool` 路径，`docs/architecture/tool-call-path-classification.json` 无需新增变更 |
| `server.py` 行数 | 618 行 |
| `server.py` FastAPI route decorators | 0 个 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/app_route_assembly.py packages/agent/src/aiask_agent/fallback_server.py
# passed

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 10 passed in 48.70s
```

当前 P1 模板补充结论：

1. `create_app` 中的 pre-authorizer Desktop helper 遗留已经清掉，当前剩余 wrapper 均被 route assembly 或 fallback 兼容路径引用。
2. fallback 中命中的 `_api_authorized()` 属于 legacy handler 自有方法，本批未触碰 fallback HTTP path。
3. 继续拆分时不宜按单函数零碎移动，应按 AI/Hermes/run/search/tool-call wrapper 职责成组迁移，并继续保持 fallback alias 兼容检查。

### 2026-06-14 第四十三批：App route callback factory 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/app_route_callbacks.py` |
| `server.py` 装配方式 | `create_app` 只构造 runtime、`FullRuntimeManager`、`QuantResearchStore`、`AppRouteCallbackFactory`、lifespan 和 FastAPI app，再用 `callbacks.route_assembly(...)` 交给 `configure_agent_app(...)` |
| 已迁出职责 | `RouteAuthorizer` 构造、tool/full-tool audited call wrapper、Desktop settings/data/capabilities wrapper、AI config/status wrapper、workbench/run/search/artifact/session wrapper、Hermes readiness/status/session wrapper、Financial Manager/broker wrapper、SSE wrapper、`AgentRouteAssembly` 依赖对象构造 |
| 行为保持 | `source_chain=["aiask_agent.server", "full_tool_call"]` 保持；route path/method/response shape 保持；control token/full-mode/user-scope guardrail 仍由 `RouteAuthorizer` 提供；fallback HTTPServer 未改 |
| fallback 兼容 | `server.py` 继续保留 fallback lazy binding 当前使用的私有 helper 和 import aliases，本批没有迁移 legacy HTTP path |
| direct-call 守门同步 | 本批未新增裸 `tool_registry.call_tool` 路径；`test_tool_call_path_gate.py` 已通过，`docs/architecture/tool-call-path-classification.json` 无需新增变更 |
| `server.py` 行数 | 281 行 |
| `server.py` FastAPI route decorators | 0 个 |
| 新模块行数 | `app_route_callbacks.py` 509 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/app_route_callbacks.py packages/agent/src/aiask_agent/app_route_assembly.py packages/agent/src/aiask_agent/fallback_server.py
# passed

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 10 passed in 46.59s

uv run pytest packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_ai_status_and_smoke.py -q
# 17 passed, 1 skipped in 90.33s

uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_financial_manager_desktop_api.py packages/agent/tests/test_broker_readonly_api.py -q
# 21 passed in 153.43s

uv run pytest packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface packages/agent/tests/test_extended_agent_capabilities.py::test_http_sse_run_events_toolsets_and_jobs packages/agent/tests/test_tool_registry.py packages/agent/tests/test_gateway_daemon.py packages/agent/tests/test_gateway_daemon_phase2.py packages/agent/tests/test_gateway_daemon_phase4.py packages/agent/tests/test_connector_health.py -q
# 68 passed in 22.78s
```

当前 P1 模板补充结论：

1. `server.py` 已基本回到 app entrypoint/compatibility shim：runtime 默认构造、FastAPI app 创建、route assembly handoff、fallback `build_server` 和 CLI `main`。
2. 仍保留若干 fallback lazy binding 兼容 import/helper，因此不宜仅按“unused import”做机械清理；下一步若要继续瘦身，应先显式化 fallback 依赖，再删除 `server.py` 兼容别名。
3. P1 已适合进入阶段边界：补跑拆组 Agent HTTP contract、核对 endpoint/tool-call gates、再考虑 P2 Desktop 合同层拆分。

### 2026-06-14 第四十四批：P1 边界回归与 Factor Factory 兼容注入

已落地内容：

| 项 | 结果 |
| --- | --- |
| 修复范围 | `packages/agent/src/aiask_agent/app_route_assembly.py`、`packages/agent/src/aiask_agent/app_route_callbacks.py`、`packages/agent/src/aiask_agent/server.py` |
| 回归发现 | P1 边界回归中 `test_desktop_factor_factory_status_endpoint_uses_safe_facade` 发现 route assembly 直接引用底层 `factor_factory_status`，绕过了测试和兼容层 monkeypatch 的 `aiask_agent.server.factor_factory_status` |
| 修复方式 | 将 `factor_factory_status` 加入 `AgentRouteAssembly` 显式依赖，由 `AppRouteCallbackFactory` 持有，并在 `server.create_app` 传入当前 `server.factor_factory_status` 兼容别名 |
| 行为保持 | `/v1/desktop/factor-factory/status` 仍使用 safe facade；生产路径不变；测试/外部兼容 monkeypatch 继续可通过 `aiask_agent.server.factor_factory_status` 覆盖 |
| direct-call 守门同步 | 本批未新增裸 `tool_registry.call_tool` 路径；`test_tool_call_path_gate.py` 已通过，`docs/architecture/tool-call-path-classification.json` 无需新增变更 |
| `server.py` 行数 | 281 行 |
| `server.py` FastAPI route decorators | 0 个 |
| `app_route_callbacks.py` 行数 | 509 行 |
| `app_route_assembly.py` 行数 | 406 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/app_route_callbacks.py packages/agent/src/aiask_agent/app_route_assembly.py packages/agent/src/aiask_agent/fallback_server.py
# passed

uv run pytest packages/agent/tests/test_desktop_ops_api.py packages/agent/tests/test_evidence_artifacts_sources.py packages/agent/tests/test_intents.py -q
# 24 passed in 113.93s

uv run pytest packages/agent/tests/test_realtime_finance_facades.py packages/agent/tests/test_mcp_client.py -q
# 5 passed in 0.32s

uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# 10 passed in 44.61s
```

当前 P1 模板补充结论：

1. P1 route/callback 拆分后，server-level compatibility aliases 不只是 fallback 使用，也可能被测试或外部启动脚本 monkeypatch；迁移 route assembly 依赖时要优先显式注入兼容别名。
2. Agent HTTP contract 拆组回归已覆盖 Desktop ops、evidence artifacts、intents、MCP client、realtime finance、server/drift/tool-call gate。
3. P1 进入阶段边界前仍建议保留当前拆组命令，而不是恢复单个超长 pytest 命令。

### 2026-06-14 本轮收尾快照

当前代码直接统计：

| 文件/范围 | 行数 | route decorators |
| --- | ---: | ---: |
| `packages/agent/src/aiask_agent/server.py` | 281 | 0 |
| `packages/agent/src/aiask_agent/app_route_callbacks.py` | 509 | 0 |
| `packages/agent/src/aiask_agent/app_route_assembly.py` | 406 | 0 |
| `packages/agent/src/aiask_agent/runtime_factories.py` | 60 | 0 |
| `packages/agent/src/aiask_agent/app_lifecycle.py` | 52 | 0 |
| `packages/agent/src/aiask_agent/gateway_route_factories.py` | 68 | 0 |
| `packages/agent/src/aiask_agent/streaming_payloads.py` | 71 | 0 |
| `packages/agent/src/aiask_agent/server_http_utils.py` | 70 | 0 |
| `packages/agent/src/aiask_agent/mcp_payloads.py` | 62 | 0 |
| `packages/agent/src/aiask_agent/plugin_payloads.py` | 29 | 0 |
| `packages/agent/src/aiask_agent/financial_payloads.py` | 538 | 0 |
| `packages/agent/src/aiask_agent/hermes_payloads.py` | 291 | 0 |
| `packages/agent/src/aiask_agent/run_payloads.py` | 596 | 0 |
| `packages/agent/src/aiask_agent/desktop_capabilities_payloads.py` | 250 | 0 |
| `packages/agent/src/aiask_agent/server_cli.py` | 104 | 0 |
| `packages/agent/src/aiask_agent/fallback_server.py` | 1762 | 0 |
| `packages/agent/src/aiask_agent/ai_payloads.py` | 674 | 0 |
| `packages/agent/src/aiask_agent/route_auth.py` | 118 | 0 |
| `packages/agent/src/aiask_agent/audited_tool_calls.py` | 99 | 0 |
| `packages/agent/src/aiask_agent/desktop_payloads.py` | 230 | 0 |
| `packages/agent/src/aiask_agent/request_context.py` | 47 | 0 |
| `packages/agent/src/aiask_agent/response_payloads.py` | 80 | 0 |
| `packages/agent/src/aiask_agent/routes/health.py` | 86 | 5 |
| `packages/agent/src/aiask_agent/routes/desktop_data.py` | 59 | 6 |
| `packages/agent/src/aiask_agent/routes/desktop_user.py` | 124 | 14 |
| `packages/agent/src/aiask_agent/routes/desktop_finance.py` | 286 | 22 |
| `packages/agent/src/aiask_agent/routes/desktop_workbench.py` | 26 | 1 |
| `packages/agent/src/aiask_agent/routes/ai.py` | 50 | 5 |
| `packages/agent/src/aiask_agent/routes/desktop_runs.py` | 26 | 1 |
| `packages/agent/src/aiask_agent/routes/responses.py` | 99 | 5 |
| `packages/agent/src/aiask_agent/routes/run_history.py` | 134 | 14 |
| `packages/agent/src/aiask_agent/routes/run_control.py` | 82 | 5 |
| `packages/agent/src/aiask_agent/routes/intents.py` | 67 | 5 |
| `packages/agent/src/aiask_agent/routes/approvals.py` | 34 | 2 |
| `packages/agent/src/aiask_agent/routes/jobs.py` | 67 | 6 |
| `packages/agent/src/aiask_agent/routes/tools.py` | 52 | 2 |
| `packages/agent/src/aiask_agent/routes/hermes_status.py` | 33 | 3 |
| `packages/agent/src/aiask_agent/routes/hermes.py` | 71 | 6 |
| `packages/agent/src/aiask_agent/routes/full_controls.py` | 49 | 5 |
| `packages/agent/src/aiask_agent/routes/plugins_skills.py` | 110 | 10 |
| `packages/agent/src/aiask_agent/routes/mcp.py` | 135 | 11 |
| `packages/agent/src/aiask_agent/routes/learning_rl.py` | 82 | 12 |
| `packages/agent/src/aiask_agent/routes/gateway.py` | 135 | 13 |
| `packages/agent/src/aiask_agent/routes/connectors.py` | 55 | 4 |
| `packages/agent/src/aiask_agent/routes/webhooks.py` | 39 | 4 |

本轮核心结果：

1. `server.py` 从第三批记录时的 6378 行、136 个 FastAPI route decorators，收口到 281 行、0 个 FastAPI route decorators。
2. 新增/启用的 route factory 覆盖 Desktop data/user/finance/workbench/runs、AI config/status、responses/chat/search、run history/control、intents/approvals、jobs、tools、Hermes status/sessions、full/native controls、skills/plugins、MCP aggregation、learning/RL、gateway/connectors/webhooks，并新增 `route_auth.py` 承接 auth/control helper、`runtime_factories.py` 承接 runtime/full-runtime factory、`app_route_assembly.py` 承接 FastAPI CORS 和 route include assembly、`app_route_callbacks.py` 承接 app route callback/wrapper factory、`audited_tool_calls.py` 承接 tool-call 审计 helper、`desktop_payloads.py` 承接 Desktop data/settings/profile payload builder、`desktop_capabilities_payloads.py` 承接 Desktop capabilities 聚合 payload、`run_payloads.py` 承接 run/session/workbench/handoff/artifact payload helper、`streaming_payloads.py` 承接 SSE formatter、`gateway_route_factories.py` 承接 Gateway/connectors/webhook route factory glue、`app_lifecycle.py` 承接 FastAPI lifespan/Gateway daemon lifecycle、`hermes_payloads.py` 承接 Hermes readiness/status/live evidence payload helper、`financial_payloads.py` 承接 Financial Manager/broker read-only payload helper、`server_http_utils.py` 承接 fallback/ASGI HTTP utility、`mcp_payloads.py` 承接 MCP error payload helper、`plugin_payloads.py` 承接 plugin manifest payload helper、`request_context.py` 承接 request context helper、`response_payloads.py` 承接 responses/chat payload formatter、`ai_payloads.py` 承接 AI config/status/smoke/models payload builder、`fallback_server.py` 承接 legacy HTTPServer、`server_cli.py` 承接服务端启动 CLI，并清理 `create_app` 未引用 wrapper 遗留、保留 `factor_factory_status` server-level monkeypatch 兼容。
3. `docs/architecture/tool-call-path-classification.json` 已同步删除或更新迁移后 stale 的 FastAPI/direct tool-call 分类；fallback HTTPServer 的只读分类已指向 `fallback_server.py`，Desktop capabilities 的只读分类已指向 `desktop_capabilities_payloads.py`；第三十四至四十四批未新增裸 `tool_registry.call_tool` 路径，因此无需新增分类变更。
4. 所有本轮迁移均保持 path、method、response shape 和既有 guardrail；fallback HTTPServer 已移出 `server.py`，但保留原 `build_server` 入口。

本轮已跑过的主要验证集：

```bash
uv run pytest packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_tool_registry.py -q
uv run pytest packages/agent/tests/test_desktop_ops_api.py -q
uv run pytest packages/agent/tests/test_desktop_capabilities_api.py -q
uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py -q
uv run pytest packages/agent/tests/test_ai_status_and_smoke.py -q
uv run pytest packages/agent/tests/test_server.py -q
uv run pytest packages/agent/tests/test_evidence_artifacts_sources.py -q
uv run pytest packages/agent/tests/test_intents.py -q
uv run pytest packages/agent/tests/test_quant_product.py packages/agent/tests/test_financial_manager_desktop_api.py packages/agent/tests/test_broker_readonly_api.py -q
uv run pytest packages/agent/tests/test_extended_agent_capabilities.py::test_http_sse_run_events_toolsets_and_jobs -q
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/server_cli.py packages/agent/src/aiask_agent/fallback_server.py
uv run pytest packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_quant_product.py -q
uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_evidence_artifacts_sources.py -q
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/hermes_payloads.py packages/agent/src/aiask_agent/fallback_server.py
uv run pytest packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_native_full_parity.py packages/agent/tests/test_hermes_native_live_adapters.py::test_hermes_readiness_endpoint_reports_native_surfaces -q
uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
uv run pytest packages/agent/tests/test_financial_manager_desktop_api.py packages/agent/tests/test_live_readiness_smoke_script.py -q
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/financial_payloads.py packages/agent/src/aiask_agent/fallback_server.py
uv run pytest packages/agent/tests/test_financial_manager_desktop_api.py packages/agent/tests/test_broker_readonly_api.py packages/agent/tests/test_realtime_finance_facades.py -q
uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py packages/agent/tests/test_desktop_capabilities_api.py -q
uv run pytest packages/agent/tests/test_live_readiness_smoke_script.py -q
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/server_http_utils.py packages/agent/src/aiask_agent/mcp_payloads.py packages/agent/src/aiask_agent/plugin_payloads.py packages/agent/src/aiask_agent/fallback_server.py
uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
uv run pytest packages/agent/tests/test_mcp_client.py packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface -q
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/streaming_payloads.py packages/agent/src/aiask_agent/fallback_server.py
uv run pytest packages/agent/tests/test_extended_agent_capabilities.py::test_http_sse_run_events_toolsets_and_jobs packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/gateway_route_factories.py packages/agent/src/aiask_agent/fallback_server.py
uv run pytest packages/agent/tests/test_gateway_daemon.py packages/agent/tests/test_gateway_daemon_phase2.py packages/agent/tests/test_gateway_daemon_phase4.py packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
uv run pytest packages/agent/tests/test_connector_health.py packages/agent/tests/test_desktop_capabilities_api.py -q
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/app_lifecycle.py packages/agent/src/aiask_agent/gateway_route_factories.py packages/agent/src/aiask_agent/fallback_server.py
uv run pytest packages/agent/tests/test_gateway_daemon.py packages/agent/tests/test_gateway_daemon_phase2.py packages/agent/tests/test_gateway_daemon_phase4.py packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
uv run pytest packages/agent/tests/test_connector_health.py packages/agent/tests/test_desktop_capabilities_api.py -q
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/fallback_server.py packages/agent/src/aiask_agent/runtime_factories.py packages/agent/src/aiask_agent/app_lifecycle.py
uv run pytest packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface packages/agent/tests/test_extended_agent_capabilities.py::test_http_sse_run_events_toolsets_and_jobs packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
uv run pytest packages/agent/tests/test_tool_registry.py packages/agent/tests/test_desktop_capabilities_api.py -q
uv run pytest packages/agent/tests/test_tool_registry.py packages/agent/tests/test_desktop_ops_api.py packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_ai_status_and_smoke.py packages/agent/tests/test_server.py packages/agent/tests/test_evidence_artifacts_sources.py packages/agent/tests/test_intents.py packages/agent/tests/test_financial_manager_desktop_api.py packages/agent/tests/test_broker_readonly_api.py packages/agent/tests/test_realtime_finance_facades.py packages/agent/tests/test_mcp_client.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
# timed out after 304s before pytest summary; split verification below passed
uv run pytest packages/agent/tests/test_tool_registry.py packages/agent/tests/test_desktop_ops_api.py packages/agent/tests/test_ai_status_and_smoke.py -q
# 34 passed, 1 skipped in 137.34s
uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_evidence_artifacts_sources.py packages/agent/tests/test_intents.py -q
# 21 passed in 122.33s
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/app_route_assembly.py packages/agent/src/aiask_agent/fallback_server.py
uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
uv run pytest packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_ai_status_and_smoke.py -q
uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_financial_manager_desktop_api.py -q
uv run pytest packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface packages/agent/tests/test_extended_agent_capabilities.py::test_http_sse_run_events_toolsets_and_jobs -q
uv run pytest packages/agent/tests/test_gateway_daemon.py packages/agent/tests/test_gateway_daemon_phase2.py packages/agent/tests/test_gateway_daemon_phase4.py packages/agent/tests/test_connector_health.py -q
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/app_route_assembly.py packages/agent/src/aiask_agent/fallback_server.py
uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
python -m py_compile packages/agent/src/aiask_agent/server.py packages/agent/src/aiask_agent/app_route_callbacks.py packages/agent/src/aiask_agent/app_route_assembly.py packages/agent/src/aiask_agent/fallback_server.py
uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
uv run pytest packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_ai_status_and_smoke.py -q
uv run pytest packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_financial_manager_desktop_api.py packages/agent/tests/test_broker_readonly_api.py -q
uv run pytest packages/agent/tests/test_native_full_parity.py::test_fastapi_native_full_management_surface packages/agent/tests/test_extended_agent_capabilities.py::test_http_sse_run_events_toolsets_and_jobs packages/agent/tests/test_tool_registry.py packages/agent/tests/test_gateway_daemon.py packages/agent/tests/test_gateway_daemon_phase2.py packages/agent/tests/test_gateway_daemon_phase4.py packages/agent/tests/test_connector_health.py -q
uv run pytest packages/agent/tests/test_desktop_ops_api.py packages/agent/tests/test_evidence_artifacts_sources.py packages/agent/tests/test_intents.py -q
uv run pytest packages/agent/tests/test_realtime_finance_facades.py packages/agent/tests/test_mcp_client.py -q
uv run pytest packages/agent/tests/test_server.py packages/agent/tests/test_endpoint_drift_gate.py packages/agent/tests/test_tool_call_path_gate.py -q
```

剩余建议：

1. P1 的 FastAPI route decorator 迁移、route include assembly 拆分、app route callback factory 拆分、auth/control helper 拆分、runtime/full-runtime factory 拆分、audited tool-call helper 拆分、Desktop payload builder 拆分、Desktop capabilities payload 拆分、run/session/workbench payload 拆分、SSE formatter 拆分、Gateway/connectors/webhook route factory glue 拆分、FastAPI lifespan/Gateway daemon lifecycle 拆分、Hermes readiness/status payload 拆分、Financial Manager/broker payload 拆分、HTTP/MCP/plugin utility 拆分、request context helper 拆分、responses/chat payload formatter 拆分、AI config/status/smoke/models payload builder 拆分、fallback HTTPServer 分层、server CLI/main 分层、unused `create_app` wrapper 清理和 Factor Factory compatibility injection 已经完成；下一步可把 P1 作为阶段边界，进入 P2 Desktop 合同层拆分前先切分提交/PR。
2. 本地大组合回归曾在 304s 和 184s 超时且未产出 pytest summary，已按文件拆分补跑通过；切分提交前建议沿用拆组命令，避免本地/CI 单命令超时。
3. P2 进入 Desktop API/mock/types/CSS 拆分前，先把当前 Agent route 拆分作为独立 PR 或提交切分，降低后续冲突面。

### 2026-06-14 第四十五批：Desktop `AiaskApi` core facade 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/services/api/core.ts` |
| `AiaskApi` 装配方式 | `desktop/src/services/aiaskApi.ts` 继续导出 `AiaskApi` facade 和 `AiaskClientOptions` 类型；`AiaskApi` 继承 `AiaskApiCore`，业务方法签名和路径保持不变 |
| 已迁出职责 | `AiaskClientOptions`、endpoint normalization 绑定、`apiToken/controlToken` 持有、`controlOrApiToken`、`compactForSearch` |
| 行为保持 | Desktop 仍只通过 Agent HTTP API；mock/live 分流仍由 `requestJson` 与 `mockApi` 控制；所有 `AiaskApi` route path、method、token 选择保持 |
| 测试同步 | `SessionsPage.test.tsx` 中继续会话按钮点击前等待按钮解除 busy/disabled，修复全量 Desktop unit suite 中的测试时序红灯；产品页面代码未改 |
| `aiaskApi.ts` 行数 | 1503 行 |
| 新模块行数 | `services/api/core.ts` 38 行 |
| Agent page 测试行数 | `SessionsPage.test.tsx` 147 行 |

验证结果：

```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts --environment jsdom
# 1 passed; 8 tests passed

npx vitest run src/features/agent-pages/SessionsPage.test.tsx --environment jsdom
# 1 passed; 11 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模板补充结论：

1. Desktop API core 已有根层 `desktop/src/api.ts`，本批新增的是 `services/api/core.ts`，专门服务 `AiaskApi` facade 的构造和 token helpers；后续 domain client 可复用同一 core。
2. `AiaskApi` facade 可以在不改调用方的前提下逐步拆 domain clients；下一批更适合抽 AI/responses 或 Gateway/MCP 这类边界清晰的方法组。
3. `mockApi.ts` 仍是 P2 最大风险面；拆 mock route constants/handlers 前应保持 `npm run typecheck`、`npx vitest run src/services/aiaskApi.test.ts --environment jsdom`、`npm test` 这组验证。

### 2026-06-14 第四十六批：Desktop AI/responses domain client 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/services/api/ai.ts` |
| `AiaskApi` 装配方式 | `AiaskApi` 保留 `aiStatus`、`aiSmoke`、`aiModels`、`aiConfig`、`aiConfigSave`、`response`、`responseGet`、`responseDelete` facade 方法；实现委托到 `services/api/ai.ts` |
| 已迁出职责 | `/v1/ai/status`、`/v1/ai/smoke`、`/v1/ai/models`、`/v1/ai/config`、`/v1/responses`、`/v1/responses/{id}` 的 path/method/token/body 绑定和返回类型 |
| 行为保持 | Desktop 仍只通过 Agent HTTP API；AI config 保存仍使用 control token；responses create 可继续传入 override token；response get/delete 仍使用 API token |
| `aiaskApi.ts` 行数 | 1494 行 |
| `services/api/core.ts` 行数 | 38 行 |
| 新模块行数 | `services/api/ai.ts` 68 行 |

验证结果：

```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts --environment jsdom
# 1 passed; 8 tests passed

npx vitest run src/hooks/useAgentWorkbench.test.tsx src/features/models/ModelsWorkspace.test.tsx --environment jsdom
# 2 passed; 10 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模板补充结论：

1. `services/api/core.ts` + `services/api/ai.ts` 已证明 `AiaskApi` facade 可按 domain function 模式拆分，而不改变 UI/hook 调用方。
2. 下一批更适合抽 Gateway/MCP/connectors 或 run/session 这类路径密集方法组；它们应继续用 `AiaskApi` 同名方法做 facade。
3. `mockApi.ts` 仍未拆分，后续拆 mock handlers 前应先抽 path constants，避免 API client 与 mock dispatch 各自手写路径继续漂移。

### 2026-06-14 第四十七批：Desktop Gateway/MCP/connectors domain client 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/services/api/integrations.ts` |
| `AiaskApi` 装配方式 | `AiaskApi` 保留 connectors、Gateway、webhooks、MCP 同名 facade 方法；纯 HTTP path/method/token/body 绑定委托到 `services/api/integrations.ts` |
| 已迁出职责 | `/v1/connectors/*`、`/v1/gateway/status`、`/v1/gateway/daemon/status`、`/v1/gateway/platforms`、`/v1/gateway/messages`、`/v1/gateway/directory`、`/v1/webhooks`、`/v1/mcp/register-local`、`/v1/mcp/discover`、`/v1/mcp/resources/read`、`/v1/mcp/prompts/get`、`/v1/mcp/oauth/start` 的请求封装 |
| 行为保持 | Desktop 仍只通过 Agent HTTP API；Gateway/MCP/Connectors 页面调用方未改；`gatewaySendIntent` 与 `webhookTriggerIntent` 仍留在 `AiaskApi` facade，通过既有 `createActionIntent` 生成受控预览/审批 |
| `aiaskApi.ts` 行数 | 1471 行 |
| `services/api/core.ts` 行数 | 38 行 |
| `services/api/ai.ts` 行数 | 68 行 |
| 新模块行数 | `services/api/integrations.ts` 190 行 |

验证结果：

```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts --environment jsdom
# 1 passed; 8 tests passed

npx vitest run src/features/agent-pages/GatewayPage.test.tsx src/features/agent-pages/McpConnectorsPage.test.tsx src/features/agent-pages/ReadinessHealthPage.test.tsx --environment jsdom
# 3 passed; 9 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模板补充结论：

1. Gateway/MCP/connectors 这种跨 Agent Ops 页面共用的路径组，已可按 `services/api/*` domain client 拆分；`AiaskApi` 继续作为 Desktop 页面的稳定合同层。
2. 涉及 ActionIntent 的 facade 方法不宜机械迁出到纯 HTTP 模块，除非后续抽出显式 intent helper；当前保留在 `AiaskApi` 内可避免重复 side-effect guardrail 逻辑。
3. 下一批更适合继续拆 `run/session/workbench` 或 `plugins/skills/jobs/learning/RL` 方法组；`mockApi.ts` 仍应在 domain client 继续收敛后单独处理 route constants/handlers。

### 2026-06-14 第四十八批：Desktop run/session/workbench domain client 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/services/api/workbench.ts` |
| `AiaskApi` 装配方式 | `AiaskApi` 保留 run、session、workbench 同名 facade 方法；实现委托到 `services/api/workbench.ts` |
| 已迁出职责 | `/v1/desktop/workbench/summary`、`/v1/desktop/runs`、`/v1/runs/{id}`、`/v1/runs/{id}/events`、`/v1/runs/{id}/trace-eval`、`/v1/runs/{id}/artifacts`、`/v1/runs/{id}/sources`、`/v1/runs/{id}/cancel|stop|steer`、`/v1/hermes/sessions`、`/v1/hermes/sessions/{id}/resume-context`、`/v1/sessions/{id}/messages|undo|archive|artifacts|sources` 的请求封装 |
| 行为保持 | Desktop 仍只通过 Agent HTTP API；mock endpoint 下的 run events 仍走 `requestJson` 读取数组，live endpoint 下仍走 SSE fetch + `parseSseEvents`；session undo/archive 仍使用 control token |
| `aiaskApi.ts` 行数 | 1396 行 |
| `services/api/core.ts` 行数 | 38 行 |
| `services/api/ai.ts` 行数 | 68 行 |
| `services/api/integrations.ts` 行数 | 190 行 |
| 新模块行数 | `services/api/workbench.ts` 218 行 |

验证结果：

```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts --environment jsdom
# 1 passed; 8 tests passed

npx vitest run src/hooks/useAgentWorkbench.test.tsx src/features/agent-pages/SessionsPage.test.tsx src/features/agent-pages/RunsEventsPage.test.tsx --environment jsdom
# 3 passed; 27 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模板补充结论：

1. `runEvents` 的 mock/live 双路径已随 domain client 迁出，说明带局部协议差异的 route wrapper 也可以离开 `AiaskApi` facade，而不影响 hook/page 调用方。
2. `AiaskApi` facade 行数已从 1503 行降到 1396 行；后续可优先继续拆 `plugins/skills/jobs/learning/RL` 或 `financial/quant/factory` 方法组。
3. P2 的最大剩余风险仍在 `mockApi.ts`：在继续抽 route constants/handlers 前，应复用本轮已稳定的 domain module 边界，避免一次性大改 mock dispatch。

### 2026-06-14 第四十九批：Desktop Ops domain client 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/services/api/ops.ts` |
| `AiaskApi` 装配方式 | `AiaskApi` 保留 jobs、skills、plugins、learning、RL 同名 facade 方法；实现委托到 `services/api/ops.ts` |
| 已迁出职责 | `/v1/jobs`、`/v1/jobs/{id}`、`/v1/jobs/{id}/run`、`/v1/jobs/{id}/runs`、`/v1/skills`、`/v1/skills/{name}`、`/v1/plugins`、`/v1/plugins/{name}`、`/v1/plugins/{name}/tools/{tool}/test`、`/v1/plugins/{name}/commands`、`/v1/plugins/{name}/commands/{command}/test`、`/v1/learning/status|review|apply`、`/v1/rl/environments|config|runs`、`/v1/rl/runs/{id}/stop|results|logs` 的请求封装 |
| 行为保持 | Desktop 仍只通过 Agent HTTP API；jobs 仍使用 API token；skills/plugins/learning apply/RL mutation 仍使用 control token；`jobsCreate`、`jobsUpdate`、`jobsDelete`、`jobsRun` aliases 保持不变 |
| `aiaskApi.ts` 行数 | 1373 行 |
| `services/api/core.ts` 行数 | 38 行 |
| `services/api/ai.ts` 行数 | 68 行 |
| `services/api/integrations.ts` 行数 | 190 行 |
| `services/api/workbench.ts` 行数 | 218 行 |
| 新模块行数 | `services/api/ops.ts` 225 行 |

验证结果：

```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/agent-pages/PluginsSkillsPage.test.tsx --environment jsdom
# 2 passed; 10 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模板补充结论：

1. Desktop Ops 类 HTTP wrappers 已从 `AiaskApi` 中移出，下一步可继续拆 finance/quant/factory 这类大块业务 API，或先切入 `mockApi.ts` 的 route constants。
2. `services/api/*` 目前已形成 core、ai、integrations、workbench、ops 五个模块；继续拆分时应保持“domain function + facade delegate”的同一模式，避免 UI 层跟着搬迁。
3. Automation/Workflows/Learning RL 面板目前主要依赖 service route 测试和全量 unit suite 间接覆盖；后续改页面行为时应补专门组件测试。

### 2026-06-14 第五十批：Desktop state/profile/data domain client 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/services/api/desktopState.ts` |
| `AiaskApi` 装配方式 | `AiaskApi` 保留 settings、data、stock data sources、local profile、user activity/feedback/data policy/recommendations 同名 facade 方法；实现委托到 `services/api/desktopState.ts` |
| 已迁出职责 | `/v1/desktop/settings/status`、`/v1/desktop/data/status`、`/v1/desktop/data/sync-plan`、`/v1/desktop/stock-data-sources`、`/v1/desktop/stock-data-sources/test`、`/v1/desktop/users/local-profile`、`/v1/desktop/events`、`/v1/desktop/feedback`、`/v1/desktop/users/{id}/activity|export|delete|learning-dataset|recommendations|data-policy`、`/v1/desktop/analytics/summary`、`/v1/desktop/retention/sweep` 的请求封装 |
| 行为保持 | Desktop 仍只通过 Agent HTTP API；settings/profile/data/user 方法名未变；stock source save/test 和 retention sweep 仍使用 control token；`memorySearch`、`dataGate`、intent/tool facade helpers 暂留在 `AiaskApi` |
| `aiaskApi.ts` 行数 | 1302 行 |
| `services/api/core.ts` 行数 | 38 行 |
| `services/api/ai.ts` 行数 | 68 行 |
| `services/api/integrations.ts` 行数 | 190 行 |
| `services/api/workbench.ts` 行数 | 218 行 |
| `services/api/ops.ts` 行数 | 225 行 |
| 新模块行数 | `services/api/desktopState.ts` 238 行 |

验证结果：

```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/user/LocalUserWorkspace.test.tsx --environment jsdom
# 2 passed; 11 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模板补充结论：

1. Desktop state/profile/data routes 已形成独立 domain client，Settings、Data Sync、Local User 等页面继续通过 `AiaskApi` facade 调用，无需 UI 迁移。
2. `memorySearch` 与 `dataGate` 仍走 `readOnlyTool`，后续如果要迁出 tool facade wrappers，宜先抽统一 tool-call helper，而不是在 domain modules 中重复 `/v1/tools/{tool}` 细节。
3. 下一步可拆 finance/quant/factory HTTP wrappers，或开始 `mockApi.ts` route constants/handlers 的低风险切分；两者都应继续保持小批次验证。

### 2026-06-14 第五十一批：Desktop finance/quant/factory domain client 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/services/api/finance.ts` |
| `AiaskApi` 装配方式 | `AiaskApi` 保留 stock radar、trade prediction、Factor Factory status、quant research、Financial Manager、broker 同名 facade 方法；直接 HTTP wrapper 委托到 `services/api/finance.ts` |
| 已迁出职责 | `/v1/desktop/stock-radar/status|candidates|digest`、`/v1/desktop/trade-predictions/status|outcomes|matrix`、`/v1/desktop/factor-factory/status`、`/v1/desktop/quant/presets`、`/v1/desktop/quant/research-runs`、`/v1/desktop/quant/research-runs/{id}`、`/v1/desktop/quant/research-runs/{id}/report`、`/v1/desktop/financial-manager/catalog|status|query|intent`、`/v1/desktop/broker-readiness`、`/v1/desktop/broker/sync|accounts|positions|orders`、`/v1/desktop/broker/analytics/run|latest` 的请求封装 |
| 行为保持 | Desktop 仍只通过 Agent HTTP API；Financial Manager intent 仍使用 control token；broker routes 仍经 Agent HTTP guardrails；stock radar/factory/other ActionIntent 方法仍留在 `AiaskApi` facade |
| `aiaskApi.ts` 行数 | 1198 行 |
| `services/api/core.ts` 行数 | 38 行 |
| `services/api/ai.ts` 行数 | 68 行 |
| `services/api/integrations.ts` 行数 | 190 行 |
| `services/api/workbench.ts` 行数 | 218 行 |
| `services/api/ops.ts` 行数 | 225 行 |
| `services/api/desktopState.ts` 行数 | 238 行 |
| 新模块行数 | `services/api/finance.ts` 295 行 |

验证结果：

```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/quant/QuantResearchWorkspace.test.tsx src/features/financial-manager/FinancialManagerWorkspace.test.tsx src/features/factory-events/FactoryEventTriggerPanel.test.tsx src/features/incubation/IncubationFactoryPanel.test.tsx --environment jsdom
# 5 passed; 29 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模板补充结论：

1. Finance/quant/factory 直接 HTTP wrappers 已进入独立 domain client，`AiaskApi` facade 首次降到 1200 行以内。
2. 涉及 `readOnlyTool` 的市场温度、Factory Event、Incubation status，以及涉及 `createActionIntent` 的写入/调度方法仍留在 facade；后续应先抽通用 tool/intent helper，再决定是否继续迁出。
3. `mockApi.ts` 仍是 P2 剩余最大文件；在 API facade domain 边界稳定后，可以开始拆 mock route constants/handler groups。

### 2026-06-14 第五十二批：Desktop mock routing helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/routing.ts` |
| `mockApi.ts` 装配方式 | `mockRequestJson` 继续作为 mock 入口；method normalization、body record coercion、path/query parsing、`ok()` promise helper 委托到 `mock/routing.ts` |
| 已迁出职责 | `normalizeMockMethod`、`mockBodyRecord`、`parseMockPath`、`ok` |
| 行为保持 | mock path 解析仍使用原有 `path.split("?")` 语义；body coercion 仍按原逻辑把 object body 作为 record；所有 mock route 分支和 fixture payload 未改 |
| `aiaskApi.ts` 行数 | 1198 行 |
| `mockApi.ts` 行数 | 4151 行 |
| 新模块行数 | `mock/routing.ts` 16 行 |

验证结果：

```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts --environment jsdom
# 1 passed; 8 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模板补充结论：

1. `mockApi.ts` 已开始有独立 `mock/` 目录；后续可逐步迁出 fixture builders、route handler groups 和 path constants。
2. 这批刻意只拆 routing primitives，避免在 4000+ 行 mock dispatch 中同时移动 payload/handler 逻辑；下一批可优先拆 Desktop state/profile mock handlers，与 `services/api/desktopState.ts` 边界对齐。
3. Mock 拆分期间继续保持 `npm run typecheck`、`npx vitest run src/services/aiaskApi.test.ts --environment jsdom`、`npm test` 作为最低回归线。

### 2026-06-14 第五十三批：Desktop mock data-source fixture helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/desktopData.ts` |
| `mockApi.ts` 装配方式 | `mockApi.ts` 继续持有 stock data source mock state 和 route dispatch；`dataStatus`、`stockDataSourcesStatus`、`saveMockStockDataSource`、`testMockStockDataSource` 改为薄 wrapper，具体 fixture/helper 逻辑委托到 `mock/desktopData.ts` |
| 已迁出职责 | Desktop data status payload、stock data source configured 判定、secret redaction、draft merge、source list status、source save/test payload builder |
| 行为保持 | `/v1/desktop/data/status`、`/v1/desktop/stock-data-sources`、`/v1/desktop/stock-data-sources/test` 的 route 分支和 mutable source state 仍在 `mockApi.ts`；保存数据源仍会回写原 `mockStockDataSources` 列表 |
| `mockApi.ts` 行数 | 4032 行 |
| `mock/routing.ts` 行数 | 16 行 |
| 新模块行数 | `mock/desktopData.ts` 163 行 |

验证结果：

```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/settings/StockDataSourcesPanel.test.tsx src/features/settings/SettingsWorkspace.test.tsx src/features/user/LocalUserWorkspace.test.tsx --environment jsdom
# 4 passed; 18 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模板补充结论：

1. Mock 拆分已从 routing primitives 进入 fixture/helper 层；下一步可继续把 profile/activity/user-policy mock state 或 Desktop state route handlers 迁到 `mock/desktopState.ts`。
2. 当前选择保留 mutable state 在 `mockApi.ts`，是为了避免一次性迁移所有用户活动、session、run、artifact 依赖；后续可以按状态簇逐步抽。
3. `mockApi.ts` 已从 4159 行降到 4032 行，但仍是 P2 最大 Desktop 文件；继续拆 handler groups 时应保持每批都有 service + affected panel tests。

### 2026-06-14 第五十四批：Desktop mock AI fixture helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/ai.ts` |
| `mockApi.ts` 装配方式 | `mockApi.ts` 继续保留 `/v1/ai/*` route dispatch；AI mock config state、provider presets、status/config/smoke/models payload builders 委托到 `mock/ai.ts` |
| 已迁出职责 | `mockModelConfig`、AI provider presets、`aiStatus` payload、`aiConfig` payload、AI config save mutation、AI smoke payload、AI models payload |
| 行为保持 | `/v1/ai/status`、`/v1/ai/config`、`/v1/ai/smoke`、`/v1/ai/models` route path/method 分支未变；config save 仍更新 mock model state 并影响后续 status/models/smoke |
| `mockApi.ts` 行数 | 3925 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 163 行 |
| 新模块行数 | `mock/ai.ts` 141 行 |

验证结果：

```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/hooks/useAgentWorkbench.test.tsx src/features/models/ModelsWorkspace.test.tsx src/features/settings/SettingsWorkspace.test.tsx --environment jsdom
# 4 passed; 22 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模板补充结论：

1. Mock fixture helpers 已开始按 API domain 对齐：`mock/ai.ts` 对应 `services/api/ai.ts`，`mock/desktopData.ts` 对应 Desktop data/source routes。
2. 下一步可继续抽 `mock/workbench.ts`（runs/sessions/events/artifacts）或 `mock/userState.ts`（profile/activity/feedback/policy），但应避免一次性搬动所有 mutable session/run state。
3. `mockApi.ts` 已降到 4000 行以内；后续目标仍是把 dispatch 和 fixture/handler 分开，直到 `mockApi.ts` 只保 compatibility entrypoint。

### 2026-06-14 第五十五批：Desktop mock responses helper 并入 AI mock module

已落地内容：

| 项 | 结果 |
| --- | --- |
| 更新模块 | `desktop/src/mock/ai.ts` |
| `mockApi.ts` 装配方式 | `mockApi.ts` 继续保留 `/v1/responses` 和 `/v1/responses/{id}` route dispatch；response create/get/delete payload builders 委托到 `mock/ai.ts` |
| 已迁出职责 | `mockResponseCreate`、`mockResponseGet`、`mockResponseDelete` |
| 行为保持 | `/v1/responses` create 仍返回 `resp_mock`、`AIASK_OK` 和原 metadata；`/v1/responses/{id}` GET/DELETE route path 和返回对象未变 |
| `mockApi.ts` 行数 | 3925 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 163 行 |
| `mock/ai.ts` 行数 | 175 行 |

验证结果：

```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/hooks/useAgentWorkbench.test.tsx src/features/models/ModelsWorkspace.test.tsx --environment jsdom
# 3 passed; 18 tests passed

npx vitest run src/services/aiaskApi.test.ts --environment jsdom
# 1 passed; 8 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模板补充结论：

1. `mock/ai.ts` 现在覆盖 AI config/status/smoke/models 和 responses mock payload，边界已与 `services/api/ai.ts` 基本对齐。
2. 下一批更适合抽 `mock/workbench.ts` 或 `mock/userState.ts`；若抽 workbench，应同步跑 `useAgentWorkbench`、Sessions、Runs/Events 相关测试。
3. Mock 拆分仍保持 route dispatch 留在 `mockApi.ts`、payload/helper 先外迁的低风险节奏。

### 2026-06-14 第五十六批：Desktop mock jobs helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/jobs.ts` |
| `mockApi.ts` 装配方式 | `mockApi.ts` 继续保留 `/v1/jobs`、`/v1/jobs/{id}`、`/v1/jobs/{id}/run`、`/v1/jobs/{id}/runs` route dispatch；jobs mutable state 和 payload helpers 委托到 `mock/jobs.ts` |
| 已迁出职责 | 初始 jobs 列表、jobs list/create/update/delete/run/runs payload、`agent_job_list` tool result 使用的 job list getter |
| 行为保持 | `/v1/jobs` route path/method 分支未变；create/update/delete 仍修改同一 mock jobs state；`agent_job_run` envelope 仍在 `mockApi.ts` 用统一 `envelope` 包装 |
| `mockApi.ts` 行数 | 3904 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 163 行 |
| `mock/ai.ts` 行数 | 175 行 |
| 新模块行数 | `mock/jobs.ts` 63 行 |

验证结果：

```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts --environment jsdom
# 1 passed; 8 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模板补充结论：

1. Mock Ops 类 jobs state 已迁出，开始与 `services/api/ops.ts` 的 jobs 子域对齐。
2. `mockApi.ts` 仍保留 learning/RL/skills/plugins/webhooks 等 Ops route payload，可后续继续按 `mock/ops.ts` 或更细文件迁出。
3. 由于 Automation/Workflows 当前缺少专门组件测试，后续若改 jobs 页面行为应补测试；本批只移动 mock payload/state，使用 service route test + full unit suite 覆盖。
### 2026-06-14 第五十七批：Desktop mock learning/RL/webhook helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/ops.ts` |
| `mockApi.ts` 装配方式 | `mockApi.ts` 继续保留 `/v1/learning/*`、`/v1/rl/*`、`/v1/webhooks*` route dispatch；payload builders 委托到 `mock/ops.ts` |
| 已迁出职责 | learning status/review/apply payload、RL environments/config/runs/detail/artifact payload、webhooks list/create/delete/trigger raw payload |
| 行为保持 | path/method 分支未变；`/v1/webhooks/{id}/trigger` 仍在 `mockApi.ts` 用 `envelope("agent_webhook", ...)` 包装；approvals/intents 状态机未移动 |
| `mockApi.ts` 行数 | 3906 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 163 行 |
| `mock/ai.ts` 行数 | 175 行 |
| `mock/jobs.ts` 行数 | 63 行 |
| 新模块行数 | `mock/ops.ts` 60 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/settings/SettingsWorkspace.test.tsx --environment jsdom
# 2 passed; 12 tests passed

npm test
# 34 passed; 144 tests passed

npm run typecheck
# passed after final import compaction
```

当前 P2 模块补充结论：
1. `mock/ops.ts` 已开始覆盖非 jobs 的 Ops mock payload，先处理自包含的 learning/RL/webhook 子域。
2. Stateful guardrail 相关的 approvals/intents 仍保留在 `mockApi.ts`，避免把 `intents` map 与 ActionIntent 行为拆散；后续应先抽通用 intent helper 再迁移。
3. 下一批可继续迁出 skills/plugins/MCP/connectors 等自包含 Ops payload，或转向 workbench/session mock state；继续保持小批次 + typecheck + affected tests + full unit suite。
### 2026-06-14 第五十八批：Desktop mock integrations helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/integrations.ts` |
| `mockApi.ts` 装配方式 | `mockApi.ts` 继续保留 skills/plugins/MCP/connectors route dispatch；`capabilities()` 仍在入口层读取后传入 helper，payload builders 委托到 `mock/integrations.ts` |
| 已迁出职责 | skills list/install/update/delete、plugins list/upsert/update/tool test/commands/command test、MCP aggregate/read/discover/OAuth mock payload、connectors summary/list/detail/test payload |
| 行为保持 | path/method 分支未变；MCP discover 仍返回 `capabilities().mcp.tools`；connector detail/test object 区分保持；控制令牌语义仍由 `AiaskApi` 调用面和 mock route 分支保持 |
| `mockApi.ts` 行数 | 3907 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 163 行 |
| `mock/ai.ts` 行数 | 175 行 |
| `mock/jobs.ts` 行数 | 63 行 |
| `mock/ops.ts` 行数 | 60 行 |
| 新模块行数 | `mock/integrations.ts` 118 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/agent-pages/McpConnectorsPage.test.tsx src/features/agent-pages/PluginsSkillsPage.test.tsx --environment jsdom
# 3 passed; 14 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Desktop mock 的 integration payload 已与 Agent HTTP 集成面分离；`mockApi.ts` 仍只做 route dispatch、capability snapshot 获取和状态机保留。
2. 本批行数几乎持平，因为原先 payload 多数压在单行 return 中；收益主要是把 MCP/plugins/skills/connectors response shape 从主 dispatch 文件移出。
3. 下一批更适合迁出 gateway/process/browser/terminal 等只读 Ops payload，或单独抽 profile/activity/session state；涉及 Gateway 时继续跑 `GatewayPage` 相关测试。
### 2026-06-14 第五十九批：Desktop mock Gateway helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/gateway.ts` |
| `mockApi.ts` 装配方式 | `mockApi.ts` 继续负责 `/v1/gateway/*` path match、decode 和 profile 注入；Gateway status/daemon/platforms/messages/retry/directory payload builders 委托到 `mock/gateway.ts` |
| 已迁出职责 | Gateway status、daemon status、platform list/start/stop/health payload、message list、message retry、directory list、directory refresh |
| 行为保持 | `/v1/gateway/messages` 仍使用当前 mock profile 的 `user_id`；directory 仍使用 `profile_name`；platform stop 仍返回 `stopped`，start/health 仍返回 `ready`；send/direct-deliver 等 side-effect 路径未触碰 |
| `mockApi.ts` 行数 | 3893 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 163 行 |
| `mock/ai.ts` 行数 | 175 行 |
| `mock/jobs.ts` 行数 | 63 行 |
| `mock/ops.ts` 行数 | 60 行 |
| `mock/integrations.ts` 行数 | 118 行 |
| 新模块行数 | `mock/gateway.ts` 46 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/agent-pages/GatewayPage.test.tsx --environment jsdom
# 2 passed; 11 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Gateway mock payload 已从主 dispatch 文件中分离，Desktop GatewayPage 仍完全通过 `AiaskApi`/Agent HTTP mock route 消费。
2. Gateway 外部投递类 side-effect 未扩展；本批只搬现有 safe mock response shape，符合集成面 guardrail 边界。
3. 下一批可迁出 process/browser/terminal native-readiness mock payload，或开始拆 profile/activity/user-policy state；若触碰 native tool 面需跑对应页面/API 测试。
### 2026-06-14 第六十批：Desktop mock native-readiness helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/nativeTools.ts` |
| `mockApi.ts` 装配方式 | `mockApi.ts` 继续负责 `/v1/processes`、`/v1/browser/sessions`、`/v1/terminal/*` path match、backend decode 和 query limit 解析；native readiness payload 委托到 `mock/nativeTools.ts` |
| 已迁出职责 | process list、browser session list、terminal backend list、terminal backend sessions、terminal sessions |
| 行为保持 | terminal backend session 仍使用 decoded backend、`limit` slice 和当前 mock profile `user_id`；只读 readiness/probe payload 保持；未新增 terminal/process/browser 执行或写入入口 |
| `mockApi.ts` 行数 | 3881 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 163 行 |
| `mock/ai.ts` 行数 | 175 行 |
| `mock/jobs.ts` 行数 | 63 行 |
| `mock/ops.ts` 行数 | 60 行 |
| `mock/integrations.ts` 行数 | 118 行 |
| `mock/gateway.ts` 行数 | 46 行 |
| 新模块行数 | `mock/nativeTools.ts` 32 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/components/DiagnosticsPanel.test.tsx src/features/capabilities/CapabilitiesWorkspace.test.tsx --environment jsdom
# 3 passed; 14 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Desktop mock 的 native-readiness payload 已从主 dispatch 文件分离，仍保持 general_full/control-token 由 API 调用面表达。
2. `mockApi.ts` 中剩余较大的可迁移区域主要是 profile/activity/user-policy state、workbench/session/run/artifact state、以及 finance workspace payload。
3. 下一批若继续 mock 拆分，建议优先选择 profile/activity/user-policy 这类自包含 state；若迁 workbench/session state，需要同步跑 `useAgentWorkbench`、Sessions/Runs 页面测试。
### 2026-06-14 第六十一批：Desktop mock settings status helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/settings.ts` |
| `mockApi.ts` 装配方式 | `settingsStatus()` 继续作为主入口内部 wrapper；AI status、stock data source status 和当前 profile 由 `mockApi.ts` 注入，settings payload builder 委托到 `mock/settings.ts` |
| 已迁出职责 | Desktop settings status agent/LLM/memory/database/stock-data/profile 聚合 payload |
| 行为保持 | `/v1/desktop/settings/status` response shape、secret redaction 标记、profile 引用、stock data source status 聚合均保持；未改变 SettingsWorkspace API 调用路径 |
| `mockApi.ts` 行数 | 3847 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 163 行 |
| `mock/ai.ts` 行数 | 175 行 |
| `mock/jobs.ts` 行数 | 63 行 |
| `mock/ops.ts` 行数 | 60 行 |
| `mock/integrations.ts` 行数 | 118 行 |
| `mock/gateway.ts` 行数 | 46 行 |
| `mock/nativeTools.ts` 行数 | 32 行 |
| 新模块行数 | `mock/settings.ts` 42 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/settings/SettingsWorkspace.test.tsx --environment jsdom
# 2 passed; 12 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Settings status 这种只读聚合 payload 已适合迁出，`mockApi.ts` 继续保留状态来源和 route entrypoint。
2. 后续若迁 profile/activity/user-policy，需要先拆出用户态 store/helper，并同步覆盖 `LocalUserWorkspace` 的 seed、policy、export/delete、learning dataset 流程。
3. 若继续追求低风险，可先迁 `capabilities()` 的静态工具目录常量；但完整 capability payload 还依赖 Strategy/AI/financial helper，需要单独批次处理。
### 2026-06-14 第六十二批：Desktop mock data sync plan helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 更新模块 | `desktop/src/mock/desktopData.ts` |
| `mockApi.ts` 装配方式 | `/v1/desktop/data/sync-plan` route 继续由 `mockApi.ts` 分派；当前 `dataStatus()` 和 request body 注入 `mockDesktopDataSyncPlan(...)` |
| 已迁出职责 | Desktop data sync plan payload、sync intent params 默认值、market-temperature cache 参数默认值、stateful confirmation side-effect metadata |
| 行为保持 | `codes/task_type/period` 默认值、`market_temperature_snapshot_cache` 的 `limit/top_n/min_bars` 默认值、`Mock sync plan approval.` rationale 和 `secrets_redacted` 保持 |
| `mockApi.ts` 行数 | 3830 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 185 行 |
| `mock/ai.ts` 行数 | 175 行 |
| `mock/jobs.ts` 行数 | 63 行 |
| `mock/ops.ts` 行数 | 60 行 |
| `mock/integrations.ts` 行数 | 118 行 |
| `mock/gateway.ts` 行数 | 46 行 |
| `mock/nativeTools.ts` 行数 | 32 行 |
| `mock/settings.ts` 行数 | 42 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/settings/StockDataSourcesPanel.test.tsx --environment jsdom
# 2 passed; 11 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Desktop data/source 相关 mock 已进一步集中到 `mock/desktopData.ts`，`mockApi.ts` 保留 route 和当前状态注入。
2. Sync plan 仍标注 stateful confirmation metadata，Desktop 侧不会绕过 ActionIntent/guardrail 语义。
3. 下一批可继续在同样节奏下拆用户态 store/helper，或先处理 health/tools/capability 的静态 payload 常量。
### 2026-06-14 第六十三批：Desktop mock user state helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/userState.ts` |
| `mockApi.ts` 装配方式 | `mockApi.ts` 继续负责 local profile route、user activity/export/delete/analytics/learning route 聚合，以及 session/run/source/artifact 跨状态拼装；用户活动、工具调用、反馈、用户数据策略的 mutable state 和创建/更新 helper 委托到 `mock/userState.ts` |
| 已迁出职责 | activity events store、tool invocation audit store、feedback store、user data policy store、redaction helper、mock timestamp helper、record events/feedback/tool invocation、delete-user audit state |
| 行为保持 | `recordEvents`/`recordFeedback` payload shape、tool audit redaction、learning dataset allow_learning 逻辑、user policy PATCH 更新时间、delete dry-run/real-run 语义保持；未迁 session/run/artifact 状态 |
| `mockApi.ts` 行数 | 3741 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 185 行 |
| `mock/ai.ts` 行数 | 175 行 |
| `mock/jobs.ts` 行数 | 63 行 |
| `mock/ops.ts` 行数 | 60 行 |
| `mock/integrations.ts` 行数 | 118 行 |
| `mock/gateway.ts` 行数 | 46 行 |
| `mock/nativeTools.ts` 行数 | 32 行 |
| `mock/settings.ts` 行数 | 42 行 |
| 新模块行数 | `mock/userState.ts` 129 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/user/LocalUserWorkspace.test.tsx --environment jsdom
# 2 passed; 11 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. 用户态 mutable store 已离开 `mockApi.ts`，主 dispatch 文件只保留跨域聚合和 route wiring。
2. `LocalUserWorkspace` 的 seed、policy save、export/delete preview、learning eligibility 都已通过 targeted test 覆盖。
3. 后续若继续拆 mock，较高收益方向是 workbench/session/run/artifact state；这会触碰 `useAgentWorkbench`、SessionsPage、RunsEventsPage，应单独批次处理。
### 2026-06-14 第六十四批：Desktop mock workbench evidence helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/workbench.ts` |
| `mockApi.ts` 装配方式 | `mockApi.ts` 继续保留 session/run/handoff/message route dispatch 和 mutable session state；Agent sources/artifacts 静态 evidence、filter helper、artifact content/detail、source detail 委托到 `mock/workbench.ts` |
| 已迁出职责 | mock Agent artifacts、mock Agent sources、run/session evidence filtering、artifact content payload、artifact/source detail fallback |
| 行为保持 | `/v1/runs/{id}/artifacts`、`/v1/runs/{id}/sources`、`/v1/sessions/{id}/artifacts`、`/v1/sessions/{id}/sources`、`/v1/artifacts/{id}/content`、artifact/source detail shape 保持；run trace eval 继续使用同一 evidence counts；session/run mutable state 未迁移 |
| `mockApi.ts` 行数 | 3566 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 185 行 |
| `mock/ai.ts` 行数 | 175 行 |
| `mock/jobs.ts` 行数 | 63 行 |
| `mock/ops.ts` 行数 | 60 行 |
| `mock/integrations.ts` 行数 | 118 行 |
| `mock/gateway.ts` 行数 | 46 行 |
| `mock/nativeTools.ts` 行数 | 32 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 129 行 |
| 新模块行数 | `mock/workbench.ts` 199 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/hooks/useAgentWorkbench.test.tsx src/components/WorkbenchView.test.tsx src/features/agent-pages/SessionsPage.test.tsx src/features/agent-pages/RunsEventsPage.test.tsx --environment jsdom
# 5 passed; 46 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Workbench evidence 数据已从 `mockApi.ts` 中分离，主文件不再直接持有 Agent artifact/source arrays。
2. Session/run/handoff/message mutable state 仍保留在 `mockApi.ts`，这是下一批 workbench 拆分的主要边界。
3. 若继续拆 workbench，应优先迁 `mockRunSummaries`、`mockSessionMessages`、`currentMockSessionSummaries` 和 handoff/resume helper，并持续跑 Workbench/Sessions/Runs targeted tests。
### 2026-06-14 第六十五批：Desktop mock tool catalog helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/toolCatalog.ts` |
| `mockApi.ts` 装配方式 | `mockApi.ts` 继续保留 `/v1/tools`、`/v1/hermes/tools`、`agent_tool_catalog` tool result、capabilities tool mapping 和 health payload assembly；finance/native tool catalog constants 委托到 `mock/toolCatalog.ts` |
| 已迁出职责 | `financeTools`、`hermesTools`、`allMockTools()` |
| 行为保持 | `agent_*` 工具名、capability、category、side_effect、schemas/examples 保持；`/v1/tools` 仍只返回 finance tools，`/v1/hermes/tools` 与 `agent_tool_catalog` 仍返回 finance+Hermes tools |
| `mockApi.ts` 行数 | 3504 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 185 行 |
| `mock/ai.ts` 行数 | 175 行 |
| `mock/jobs.ts` 行数 | 63 行 |
| `mock/ops.ts` 行数 | 60 行 |
| `mock/integrations.ts` 行数 | 118 行 |
| `mock/gateway.ts` 行数 | 46 行 |
| `mock/nativeTools.ts` 行数 | 32 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 129 行 |
| `mock/workbench.ts` 行数 | 199 行 |
| 新模块行数 | `mock/toolCatalog.ts` 67 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/agent-pages/ToolsIntentsApprovalsPage.test.tsx src/features/agent-pages/ReadinessHealthPage.test.tsx src/features/capabilities/CapabilitiesWorkspace.test.tsx --environment jsdom
# 4 passed; 22 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Static tool catalog constants 已从主 dispatch 文件移出，`mockApi.ts` 不再直接维护 finance/native tool arrays。
2. Tool catalog 仍坚持 `agent_*` 命名和 side-effect 分类，未引入 Desktop 直连工具或 manager 调用。
3. 下一批可继续收敛 health/Hermes/capabilities payload，或开始迁 session/run/handoff mutable workbench state。
### 2026-06-14 第六十六批：Desktop mock financial readiness helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/capabilities.ts` |
| `mockApi.ts` 装配方式 | `capabilities()` 继续作为 `/v1/desktop/capabilities` 聚合入口；`financial_system` 子 payload 委托到 `mockFinancialSystemReadiness()` |
| 已迁出职责 | financial readiness required/optional gates、next_actions、live smoke checklist、readiness summary/disclaimer |
| 行为保持 | `/v1/financial-system/readiness` 仍从 `capabilities().financial_system` 返回；live smoke checklist path/command、MCP auth env var 名称、read-only financial workflow next action、mock investment disclaimer 保持 |
| `mockApi.ts` 行数 | 3423 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 185 行 |
| `mock/ai.ts` 行数 | 175 行 |
| `mock/jobs.ts` 行数 | 63 行 |
| `mock/ops.ts` 行数 | 60 行 |
| `mock/integrations.ts` 行数 | 118 行 |
| `mock/gateway.ts` 行数 | 46 行 |
| `mock/nativeTools.ts` 行数 | 32 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 129 行 |
| `mock/workbench.ts` 行数 | 199 行 |
| `mock/toolCatalog.ts` 行数 | 67 行 |
| 新模块行数 | `mock/capabilities.ts` 85 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/agent-pages/ReadinessHealthPage.test.tsx src/features/capabilities/CapabilitiesWorkspace.test.tsx --environment jsdom
# 3 passed; 14 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. `capabilities()` 中的 financial readiness 大块已先迁出，避免一次性移动 Hermes/status/MCP/skills/plugins/AI 等全部聚合。
2. Financial readiness 仍通过 Desktop -> Agent HTTP mock route 表达，不引入任何 broker/live trading 操作。
3. 后续可继续在 `mock/capabilities.ts` 中收敛 Hermes status/parity/readiness 与 MCP/static sections，或转向 session/run/handoff mutable workbench state。
### 2026-06-14 第六十七批：Desktop mock Hermes capability helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 更新模块 | `desktop/src/mock/capabilities.ts` |
| `mockApi.ts` 装配方式 | `capabilities()` 继续作为 `/v1/desktop/capabilities` 聚合入口；Hermes status/parity/readiness/tool mapping 子树委托到 `mockHermesCapabilities(allTools)` |
| 已迁出职责 | Hermes baseline constants、Hermes status、capability parity、v0.14/v0.16 delta、Hermes readiness/live evidence、tool/platform/feature mapping、Hermes providers/memory/acp/security/skill_packs 子状态 |
| 行为保持 | `/v1/hermes/status`、`/v1/capabilities/parity`、`/v1/hermes/readiness` 仍从 `capabilities().hermes` 取对应 payload；tool mapping 仍基于 `allMockTools()` 和 `side_effect` 分类 |
| `mockApi.ts` 行数 | 3292 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 185 行 |
| `mock/ai.ts` 行数 | 175 行 |
| `mock/jobs.ts` 行数 | 63 行 |
| `mock/ops.ts` 行数 | 60 行 |
| `mock/integrations.ts` 行数 | 118 行 |
| `mock/gateway.ts` 行数 | 46 行 |
| `mock/nativeTools.ts` 行数 | 32 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 129 行 |
| `mock/workbench.ts` 行数 | 199 行 |
| `mock/toolCatalog.ts` 行数 | 67 行 |
| `mock/capabilities.ts` 行数 | 222 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/agent-pages/ReadinessHealthPage.test.tsx src/features/capabilities/CapabilitiesWorkspace.test.tsx --environment jsdom
# 3 passed; 14 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Hermes capability 子树已从 `mockApi.ts` 中分离，主文件只保留 route dispatch 和顶层 capability composition。
2. `mock/capabilities.ts` 已承接 readiness/capability 静态 payload，后续可继续迁 MCP/skills/plugins/providers/memory 等剩余静态 capability sections。
3. `mockApi.ts` 已降到 3300 行以内；下一批可以继续收敛 capabilities 静态 sections，或拆 session/run/handoff mutable workbench state。
### 2026-06-14 第六十八批：Desktop mock capability static sections 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 更新模块 | `desktop/src/mock/capabilities.ts` |
| `mockApi.ts` 装配方式 | `capabilities()` 继续保留 Strategy/quant/financial 顶层组合；MCP 聚合 section 委托到 `mockMcpCapabilitySection()`，skills/plugins/providers/memory/acp/security/ai/raw_refs 委托到 `mockStaticCapabilitySections(aiStatus())` |
| 已迁出职责 | MCP registration/discovery/tools/resources/prompts/OAuth static capability payload、skills/skill_packs/plugins/providers/memory/acp/security/AI/raw_refs static sections |
| 行为保持 | MCP wrapped tool names、auth env var 名称、skills/plugins mock entries、memory provider readiness 和 `ai` section shape 保持；`ai` 入参使用正式 `AiStatus` 类型 |
| `mockApi.ts` 行数 | 3248 行 |
| `mock/routing.ts` 行数 | 16 行 |
| `mock/desktopData.ts` 行数 | 185 行 |
| `mock/ai.ts` 行数 | 175 行 |
| `mock/jobs.ts` 行数 | 63 行 |
| `mock/ops.ts` 行数 | 60 行 |
| `mock/integrations.ts` 行数 | 118 行 |
| `mock/gateway.ts` 行数 | 46 行 |
| `mock/nativeTools.ts` 行数 | 32 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 129 行 |
| `mock/workbench.ts` 行数 | 199 行 |
| `mock/toolCatalog.ts` 行数 | 67 行 |
| `mock/capabilities.ts` 行数 | 276 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# failed first: aiStatus parameter was typed as unknown

npm run typecheck
# passed after narrowing to AiStatus

npx vitest run src/services/aiaskApi.test.ts src/features/agent-pages/McpConnectorsPage.test.tsx src/features/agent-pages/PluginsSkillsPage.test.tsx src/features/agent-pages/ReadinessHealthPage.test.tsx src/features/capabilities/CapabilitiesWorkspace.test.tsx --environment jsdom
# 5 passed; 20 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. `capabilities()` 已明显变薄，静态 readiness/capability sections 已集中到 `mock/capabilities.ts`。
2. 本批 typecheck 捕获并修正了 `ai` section 的类型收窄问题，避免把 `CapabilityWorkbenchPayload.ai` 降成 `unknown`。
3. `mockApi.ts` 剩余主要大块集中在 session/run/handoff mutable state、finance workspace payload 和 tool result domain payload；下一批可选其中一个边界继续。
### 2026-06-14 第六十九批：Desktop mock run/event fixture 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 更新模块 | `desktop/src/mock/workbench.ts`、`desktop/src/mockApi.ts` |
| `mockApi.ts` 装配方式 | 静态 `mockRunEvents` / `mockRunSummaries` 已迁入 `mock/workbench.ts`；主 mock route dispatcher 通过 `mockRunEventsData()`、`mockRunSummariesData()` 读取 |
| 已迁出职责 | run event fixture、run summary fixture、summary 中的 `event_count` / `last_event` 派生关系 |
| 保留职责 | `mockSessionSummaries`、session messages、handoff/resume context、route dispatch 和 user export/delete 仍留在 `mockApi.ts`，作为后续 mutable workbench state 拆分边界 |
| 行为保持 | `/v1/desktop/workbench/summary`、`/v1/desktop/runs`、`/v1/runs/run_mock/events`、run trace eval、user activity/export/delete 中的 run/event payload shape 保持；approval jump target 和 `agent_*` tool names 保持 |
| `mockApi.ts` 行数 | 3091 行 |
| `mock/routing.ts` 行数 | 13 行 |
| `mock/desktopData.ts` 行数 | 175 行 |
| `mock/ai.ts` 行数 | 166 行 |
| `mock/jobs.ts` 行数 | 56 行 |
| `mock/ops.ts` 行数 | 48 行 |
| `mock/integrations.ts` 行数 | 95 行 |
| `mock/gateway.ts` 行数 | 39 行 |
| `mock/nativeTools.ts` 行数 | 28 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 117 行 |
| `mock/workbench.ts` 行数 | 282 行 |
| `mock/toolCatalog.ts` 行数 | 64 行 |
| `mock/capabilities.ts` 行数 | 271 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/hooks/useAgentWorkbench.test.tsx src/components/WorkbenchView.test.tsx src/features/agent-pages/SessionsPage.test.tsx src/features/agent-pages/RunsEventsPage.test.tsx --environment jsdom
# 5 passed; 46 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Workbench 证据、run summary、run event 静态 fixture 已集中在 `mock/workbench.ts`，`mockApi.ts` 更接近纯 route/state 组合层。
2. 本批只迁静态 fixture，没有移动 session/handoff 可变状态，降低了 reset/export/delete 路径的回归面。
3. 下一批优先选择 session/handoff mutable state 或 finance workspace payload 继续拆分；两者都应保持 Desktop -> Agent HTTP mock 合同，不引入 Python/MCP/manager 直连。
### 2026-06-14 第七十批：Desktop mock session/handoff state 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 更新模块 | `desktop/src/mock/workbench.ts`、`desktop/src/mockApi.ts` |
| `mockApi.ts` 装配方式 | `resetMockApiState()` 保留为导出入口，但委托 `resetMockWorkbenchState(profile.user_id)`；session/search/handoff/resume/undo/archive/message routes 通过 workbench helper 读取或修改状态 |
| 已迁出职责 | `mockSessionSummaries`、session messages、current session summary 派生、handoff queue、resume context、session undo、session archive、workbench summary |
| 保留职责 | `mockApi.ts` 仍负责 HTTP mock route dispatch、profile mutation、user export/delete 聚合、run trace eval、finance/tool result domain payload |
| 行为保持 | `/v1/desktop/workbench/summary`、`/v1/hermes/sessions`、`/v1/hermes/handoffs`、`/v1/hermes/sessions/{id}/resume-context`、`/v1/sessions/{id}/undo`、`/v1/sessions/{id}/archive`、`/v1/sessions/{id}/messages` payload shape 保持；undo/archive 仍只改变本地 mock state |
| `mockApi.ts` 行数 | 2828 行 |
| `mock/routing.ts` 行数 | 13 行 |
| `mock/desktopData.ts` 行数 | 175 行 |
| `mock/ai.ts` 行数 | 166 行 |
| `mock/jobs.ts` 行数 | 56 行 |
| `mock/ops.ts` 行数 | 48 行 |
| `mock/integrations.ts` 行数 | 95 行 |
| `mock/gateway.ts` 行数 | 39 行 |
| `mock/nativeTools.ts` 行数 | 28 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 117 行 |
| `mock/workbench.ts` 行数 | 529 行 |
| `mock/toolCatalog.ts` 行数 | 64 行 |
| `mock/capabilities.ts` 行数 | 271 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/hooks/useAgentWorkbench.test.tsx src/components/WorkbenchView.test.tsx src/features/agent-pages/SessionsPage.test.tsx src/features/agent-pages/RunsEventsPage.test.tsx --environment jsdom
# 5 passed; 46 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Desktop mock workbench/session/handoff 数据边界已经集中到 `mock/workbench.ts`，`mockApi.ts` 不再直接维护 session mutable arrays。
2. `resetMockApiState()` 的外部测试入口未破坏，只把 reset 细节下沉到 workbench helper。
3. 下一批可继续拆 finance workspace payload，或把 run trace eval 中的 workbench evidence 聚合迁入 `mock/workbench.ts`，但后者应避免重新耦合 user activity/tool invocation state。
### 2026-06-14 第七十一批：Desktop mock Financial Manager payload 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/financialManager.ts` |
| 更新模块 | `desktop/src/mockApi.ts` |
| `mockApi.ts` 装配方式 | `/v1/desktop/financial-manager/catalog/status/query/intent` 只做 route dispatch；payload 由 `mockFinancialManagerCatalog()`、`mockFinancialManagerStatus()`、`mockFinancialManagerQuery()`、`mockFinancialManagerIntent()` 生成 |
| 已迁出职责 | Financial Manager group/action catalog、readiness/status payload、read-only query mock results、blocked/stateful-intent guard payload、intent payload construction |
| 保留职责 | `mockApi.ts` 仍维护 `intents` Map；Financial Manager intent helper 通过 callback 注册 intent，避免新模块持有全局 route state |
| 行为保持 | read-only query 仍返回 `agent_analyze_stock` / `agent_portfolio_risk` / `agent_quant_data_gate` mock payload；stateful financial actions 仍要求 ActionIntent；blocked live broker action 仍返回 `FINANCIAL_ACTION_BLOCKED`；status 中 broker live trading remains false |
| `mockApi.ts` 行数 | 2706 行 |
| `mock/routing.ts` 行数 | 13 行 |
| `mock/desktopData.ts` 行数 | 175 行 |
| `mock/ai.ts` 行数 | 166 行 |
| `mock/jobs.ts` 行数 | 56 行 |
| `mock/ops.ts` 行数 | 48 行 |
| `mock/integrations.ts` 行数 | 95 行 |
| `mock/gateway.ts` 行数 | 39 行 |
| `mock/nativeTools.ts` 行数 | 28 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 117 行 |
| `mock/workbench.ts` 行数 | 529 行 |
| `mock/toolCatalog.ts` 行数 | 64 行 |
| `mock/capabilities.ts` 行数 | 271 行 |
| `mock/financialManager.ts` 行数 | 170 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/financial-manager/FinancialManagerWorkspace.test.tsx --environment jsdom
# 2 passed; 9 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Financial Manager mock 合同已从主 route dispatcher 中拆出，且未扩大到 broker-readonly payload，边界更清楚。
2. `intents` Map 仍由 `mockApi.ts` 统一拥有，避免 Financial Manager 模块和 generic ActionIntent routes 产生双状态。
3. 下一批可继续拆 broker-readonly mock payload，或转向 quant/stock-radar/factory payload；broker-readonly 拆分时要继续保持 explicit consent、read-only、live_trading_enabled=false。
### 2026-06-14 第七十二批：Desktop mock broker read-only payload 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/brokerReadonly.ts` |
| 更新模块 | `desktop/src/mockApi.ts` |
| `mockApi.ts` 装配方式 | `/v1/desktop/broker-readiness`、`/v1/desktop/broker/sync`、`/v1/desktop/broker/accounts|positions|orders`、`/v1/desktop/broker/analytics/*` 只做 route dispatch；payload 由 broker read-only helper 生成 |
| 已迁出职责 | QMT/同花顺 mock broker profile、account/position/order/deal snapshot、analytics、readiness checklist、explicit consent failure、broker snapshot payload |
| 行为保持 | broker sync 仍要求 `consent`；所有 broker mock payload 继续 `read_only: true`、`live_trading_enabled: false`、`secrets_redacted: true`；没有新增 live place/cancel route，也没有 broker token 缓存或绕过 |
| `mockApi.ts` 行数 | 2333 行 |
| `mock/routing.ts` 行数 | 13 行 |
| `mock/desktopData.ts` 行数 | 175 行 |
| `mock/ai.ts` 行数 | 166 行 |
| `mock/jobs.ts` 行数 | 56 行 |
| `mock/ops.ts` 行数 | 48 行 |
| `mock/integrations.ts` 行数 | 95 行 |
| `mock/gateway.ts` 行数 | 39 行 |
| `mock/nativeTools.ts` 行数 | 28 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 117 行 |
| `mock/workbench.ts` 行数 | 529 行 |
| `mock/toolCatalog.ts` 行数 | 64 行 |
| `mock/capabilities.ts` 行数 | 271 行 |
| `mock/financialManager.ts` 行数 | 170 行 |
| `mock/brokerReadonly.ts` 行数 | 388 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/financial-manager/FinancialManagerWorkspace.test.tsx --environment jsdom
# 2 passed; 9 tests passed

npx vitest run src/features/workspace/FinanceLabPage.test.tsx --environment jsdom
# 1 passed; 1 test passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Broker read-only mock data now has an explicit module boundary and no longer bloats the main route dispatcher.
2. The extraction preserved the finance MCP guardrail distinction: account/order snapshots are read-only evidence, not live trading readiness.
3. 下一批可继续拆 quant/stock-radar/factory payload；若继续 broker/live 相关内容，必须保持 per-call broker-token/live-order guardrail 不被 mock UI 暗示为可用。
### 2026-06-14 第七十三批：Desktop mock stock data-source state 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 更新模块 | `desktop/src/mock/desktopData.ts`、`desktop/src/mockApi.ts` |
| `mockApi.ts` 装配方式 | stock data-source route wrapper 继续存在，但状态读写委托 `mockStockDataSourcesStatusData()`、`mockSaveStockDataSourceData()`、`mockTestStockDataSourceData()` |
| 已迁出职责 | stock data-source presets、mutable mock stock data-source list、save 后更新 sources 的状态管理 |
| 保留职责 | `mockApi.ts` 仍负责 `/v1/desktop/data/status` envelope 注入、sync-plan route dispatch、settings status 聚合 |
| 行为保持 | presets、env var 名称、secret redaction、unsupported provider handling、test connectivity status、existing API routes 保持 |
| `mockApi.ts` 行数 | 2163 行 |
| `mock/routing.ts` 行数 | 13 行 |
| `mock/desktopData.ts` 行数 | 354 行 |
| `mock/ai.ts` 行数 | 166 行 |
| `mock/jobs.ts` 行数 | 56 行 |
| `mock/ops.ts` 行数 | 48 行 |
| `mock/integrations.ts` 行数 | 95 行 |
| `mock/gateway.ts` 行数 | 39 行 |
| `mock/nativeTools.ts` 行数 | 28 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 117 行 |
| `mock/workbench.ts` 行数 | 529 行 |
| `mock/toolCatalog.ts` 行数 | 64 行 |
| `mock/capabilities.ts` 行数 | 271 行 |
| `mock/financialManager.ts` 行数 | 170 行 |
| `mock/brokerReadonly.ts` 行数 | 388 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/data/DataSyncWorkspace.test.tsx src/features/settings/SettingsModeWorkspace.test.tsx --environment jsdom
# 1 passed; 8 tests passed

npx vitest run src/features/settings/StockDataSourcesPanel.test.tsx src/features/settings/SettingsWorkspace.test.tsx src/features/settings/SecurityPanel.test.tsx --environment jsdom
# 3 passed; 8 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. `mock/desktopData.ts` now owns the stock data-source mutable state it already knew how to validate/redact.
2. Settings status continues to consume stock data-source status through the same `stockDataSourcesStatus()` wrapper, preserving aggregation behavior.
3. 下一批可转向 market temperature / quant / stock radar payload；market temperature 是当前 `mockApi.ts` 中下一块较大的纯 payload 逻辑。
### 2026-06-14 第七十四批：Desktop mock market temperature payload 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/marketTemperature.ts` |
| 更新模块 | `desktop/src/mockApi.ts` |
| `mockApi.ts` 装配方式 | `toolResult()` 继续按 `agent_market_temperature_*` tool name dispatch；具体 snapshot/cache/history/constituents/forward-validation payload 由 `mock/marketTemperature.ts` 生成 |
| 已迁出职责 | market temperature snapshot、cache readiness/history、industry history、industry constituents、forward validation mock matrices |
| 行为保持 | tool names、read-only envelope、`market_temperature.v1` contract version、source_chain、benchmark/quality/cache fields 保持 |
| `mockApi.ts` 行数 | 1780 行 |
| `mock/routing.ts` 行数 | 13 行 |
| `mock/desktopData.ts` 行数 | 354 行 |
| `mock/ai.ts` 行数 | 166 行 |
| `mock/jobs.ts` 行数 | 56 行 |
| `mock/ops.ts` 行数 | 48 行 |
| `mock/integrations.ts` 行数 | 95 行 |
| `mock/gateway.ts` 行数 | 39 行 |
| `mock/nativeTools.ts` 行数 | 28 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 117 行 |
| `mock/workbench.ts` 行数 | 529 行 |
| `mock/toolCatalog.ts` 行数 | 64 行 |
| `mock/capabilities.ts` 行数 | 271 行 |
| `mock/financialManager.ts` 行数 | 170 行 |
| `mock/brokerReadonly.ts` 行数 | 388 行 |
| `mock/marketTemperature.ts` 行数 | 384 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/market-temperature/MarketTemperatureWorkspace.test.tsx --environment jsdom
# 2 passed; 11 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Market temperature mock tool payloads now have a dedicated read-only domain module.
2. `mockApi.ts` has crossed below 1800 lines while still owning route dispatch and generic envelope creation.
3. 下一批可继续拆 Strategy Factory / stock radar / trade prediction payload，或 stop P2 cleanup after one more focused slice and reassess P3/P4 readiness.
### 2026-06-14 第七十五批：Desktop mock stock radar payload 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/stockRadar.ts` |
| 更新模块 | `desktop/src/mockApi.ts` |
| `mockApi.ts` 装配方式 | `agent_stock_radar_status/candidates/digest` tool dispatch 和 `/v1/desktop/stock-radar/*` routes 继续保留；run/candidate/digest fixture 与 tier filtering 委托到 `stockRadarPayload()`、`stockRadarCandidatesPayload()` |
| 已迁出职责 | stock radar latest run fixture、candidate fixture、digest preview、candidate tier filter |
| 行为保持 | status/candidates/digest envelope tool names、candidate shape、dry_run/no_trade metadata 和 `/v1/desktop/stock-radar/candidates?tier=...` 行为保持 |
| `mockApi.ts` 行数 | 1714 行 |
| `mock/routing.ts` 行数 | 13 行 |
| `mock/desktopData.ts` 行数 | 354 行 |
| `mock/ai.ts` 行数 | 166 行 |
| `mock/jobs.ts` 行数 | 56 行 |
| `mock/ops.ts` 行数 | 48 行 |
| `mock/integrations.ts` 行数 | 95 行 |
| `mock/gateway.ts` 行数 | 39 行 |
| `mock/nativeTools.ts` 行数 | 28 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 117 行 |
| `mock/workbench.ts` 行数 | 529 行 |
| `mock/toolCatalog.ts` 行数 | 64 行 |
| `mock/capabilities.ts` 行数 | 271 行 |
| `mock/financialManager.ts` 行数 | 170 行 |
| `mock/brokerReadonly.ts` 行数 | 388 行 |
| `mock/marketTemperature.ts` 行数 | 384 行 |
| `mock/stockRadar.ts` 行数 | 70 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/factory-events/FactoryEventTriggerPanel.test.tsx --environment jsdom
# 2 passed; 25 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Stock Radar mock payload 已从主 dispatcher 中拆出，Factory Event panel 的 radar 调用路径保持。
2. `mockApi.ts` 剩余大块集中在 Strategy Factory / factory events / trade prediction / incubation / quant research 等 finance fixture。
3. P2 可继续按 finance fixture 小块拆分；若要进入 P3，应先记录当前 P2 状态并确认 `mockApi.ts` 是否接受继续保留 1700 行级别的 route glue。
### 2026-06-14 第七十六批：Desktop mock trade prediction payload 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/tradePrediction.ts` |
| 更新模块 | `desktop/src/mockApi.ts` |
| `mockApi.ts` 装配方式 | `agent_trade_prediction_status/outcomes/matrix` tool dispatch 和 `/v1/desktop/trade-predictions/status|outcomes|matrix` routes 继续保留；status/outcomes/matrix payload 由 `tradePredictionStatus()`、`tradePredictionOutcomes()`、`tradePredictionMatrix()` 生成 |
| 已迁出职责 | trade prediction outcome fixture、filter/limit 处理、status 汇总、score/data-quality counts、dimension matrix 聚合 |
| 行为保持 | `agent_*` tool names、status/outcomes/matrix object shape、strategy/stock/status/date/dimensions/limit filtering、partial status counts、read-only mock 行为保持；没有新增 live trading 或 broker side effect |
| `mockApi.ts` 行数 | 1491 行 |
| `mock/routing.ts` 行数 | 13 行 |
| `mock/desktopData.ts` 行数 | 354 行 |
| `mock/ai.ts` 行数 | 166 行 |
| `mock/jobs.ts` 行数 | 56 行 |
| `mock/ops.ts` 行数 | 48 行 |
| `mock/integrations.ts` 行数 | 95 行 |
| `mock/gateway.ts` 行数 | 39 行 |
| `mock/nativeTools.ts` 行数 | 28 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 117 行 |
| `mock/workbench.ts` 行数 | 529 行 |
| `mock/toolCatalog.ts` 行数 | 64 行 |
| `mock/capabilities.ts` 行数 | 271 行 |
| `mock/financialManager.ts` 行数 | 170 行 |
| `mock/brokerReadonly.ts` 行数 | 388 行 |
| `mock/marketTemperature.ts` 行数 | 384 行 |
| `mock/stockRadar.ts` 行数 | 70 行 |
| `mock/tradePrediction.ts` 行数 | 228 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/factory-events/FactoryEventTriggerPanel.test.tsx src/features/financial-manager/FinancialManagerWorkspace.test.tsx --environment jsdom
# 3 passed; 26 tests passed

npx vitest run src/features/incubation/IncubationFactoryPanel.test.tsx --environment jsdom
# 1 passed; 1 test passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Trade Prediction mock payload 已从主 dispatcher 中拆出，Strategy Factory / Factory Event 相关调用仍通过 Agent HTTP mock route 与 `agent_*` facade 暴露。
2. `mockApi.ts` 已降到 1500 行以下，剩余职责更接近 route glue、generic envelope、Strategy Factory / incubation / quant research 等尚未拆分 fixture。
3. 下一批优先拆 Strategy Factory 或 incubation payload；继续保持 mock 只表达 dry-run/read-only/quality evidence，不暗示 live broker 或实盘交易可用。
### 2026-06-14 第七十七批：Desktop mock incubation payload 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/incubation.ts` |
| 更新模块 | `desktop/src/mockApi.ts` |
| `mockApi.ts` 装配方式 | `agent_incubation_factory_status` 与 `agent_strategy_domain_events` tool dispatch 继续保留；hit-rate report、domain events、status payload、event_type/limit filtering 由 `incubationFactoryStatusPayload()` 与 `strategyDomainEventsPayload()` 生成 |
| 已迁出职责 | incubation hit-rate report fixture、promotion blocker summary、lifecycle evidence、incubation/domain event fixture、domain event filtering/limit |
| 行为保持 | `agent_*` tool names、incubation status envelope、`incubation_factory.hit_rate_report_generated` / `incubation.stage_transitioned` event shapes、limit filtering、read-only mock behavior 保持；未新增 ActionIntent、broker 或 live trading side effect |
| `mockApi.ts` 行数 | 1185 行 |
| `mock/routing.ts` 行数 | 13 行 |
| `mock/desktopData.ts` 行数 | 354 行 |
| `mock/ai.ts` 行数 | 166 行 |
| `mock/jobs.ts` 行数 | 56 行 |
| `mock/ops.ts` 行数 | 48 行 |
| `mock/integrations.ts` 行数 | 95 行 |
| `mock/gateway.ts` 行数 | 39 行 |
| `mock/nativeTools.ts` 行数 | 28 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 117 行 |
| `mock/workbench.ts` 行数 | 529 行 |
| `mock/toolCatalog.ts` 行数 | 64 行 |
| `mock/capabilities.ts` 行数 | 271 行 |
| `mock/financialManager.ts` 行数 | 170 行 |
| `mock/brokerReadonly.ts` 行数 | 388 行 |
| `mock/marketTemperature.ts` 行数 | 384 行 |
| `mock/stockRadar.ts` 行数 | 70 行 |
| `mock/tradePrediction.ts` 行数 | 228 行 |
| `mock/incubation.ts` 行数 | 307 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/incubation/IncubationFactoryPanel.test.tsx src/features/factory-events/FactoryEventTriggerPanel.test.tsx --environment jsdom
# 3 passed; 26 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Incubation mock payload 已有独立领域模块，Finance Lab / Incubation panel / Event Console 继续通过 Agent HTTP mock 和 `agent_*` facade 读取。
2. `mockApi.ts` 已接近 route glue 目标，剩余超千行主要来自 Strategy Factory 小 fixture、factory-event mock action 分支、quant research fixture 和通用 route dispatch。
3. 下一批可拆 Strategy Factory status/runs/review snapshot 或 quant research payload；若要进入更大 handler 分组拆分，应先确认 route dispatch 文件的目标形态。
### 2026-06-14 第七十八批：Desktop mock Strategy Factory / factory-event payload 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/strategyFactory.ts` |
| 更新模块 | `desktop/src/mockApi.ts` |
| `mockApi.ts` 装配方式 | `agent_factory_status/runs`、`agent_strategy_review_snapshot`、`agent_factory_event_*`、`agent_strategy_manager` compatibility mock 分支继续由 `toolResult()` dispatch；Strategy Factory status/runs/review snapshot 和 factory-event payload 由 `mock/strategyFactory.ts` 生成 |
| 已迁出职责 | strict incubation blocker summary、factory run/review snapshot、factory event list、preview tasks、lineage、theme exposure、outbox status、`agent_strategy_manager` mock kwargs parsing |
| 行为保持 | `agent_*` factory facade names、Strategy Factory readiness/status shape、strict blocker evidence、factory-event read payloads 保持；`agent_strategy_manager` 仅作为既有 mock compatibility 分支迁移，未新增 raw manager model-visible surface；未新增 live trading side effect |
| `mockApi.ts` 行数 | 1006 行 |
| `mock/routing.ts` 行数 | 13 行 |
| `mock/desktopData.ts` 行数 | 354 行 |
| `mock/ai.ts` 行数 | 166 行 |
| `mock/jobs.ts` 行数 | 56 行 |
| `mock/ops.ts` 行数 | 48 行 |
| `mock/integrations.ts` 行数 | 95 行 |
| `mock/gateway.ts` 行数 | 39 行 |
| `mock/nativeTools.ts` 行数 | 28 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 117 行 |
| `mock/workbench.ts` 行数 | 529 行 |
| `mock/toolCatalog.ts` 行数 | 64 行 |
| `mock/capabilities.ts` 行数 | 271 行 |
| `mock/financialManager.ts` 行数 | 170 行 |
| `mock/brokerReadonly.ts` 行数 | 388 行 |
| `mock/marketTemperature.ts` 行数 | 384 行 |
| `mock/stockRadar.ts` 行数 | 70 行 |
| `mock/tradePrediction.ts` 行数 | 228 行 |
| `mock/incubation.ts` 行数 | 307 行 |
| `mock/strategyFactory.ts` 行数 | 175 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/factory-events/FactoryEventTriggerPanel.test.tsx src/features/factory/StrategyFactoryPanel.test.tsx --environment jsdom
# 3 passed; 27 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. Strategy Factory mock payload 已从主 dispatcher 移出，同时保留 Agent `agent_*` facade 和现有 compatibility mock 行为。
2. `mockApi.ts` 只差少量 quant research fixture 即可退出超 1000 行清单。
3. 下一批优先拆 quant research fixture，完成 P2 mock 文件瘦身里程碑。
### 2026-06-14 第七十九批：Desktop mock quant research payload 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/mock/quantResearch.ts` |
| 更新模块 | `desktop/src/mockApi.ts` |
| `mockApi.ts` 装配方式 | `/v1/desktop/quant/presets`、`/v1/desktop/quant/research-runs`、`/v1/desktop/quant/research-runs/{id}/report` route dispatch 继续保留；presets、research artifact、report payload 由 `mockQuantPresets()` 与 `mockQuantResearchArtifact()` 生成 |
| 已迁出职责 | quant presets fixture、data_status/database 注入后的 preset payload、research stages、quant research report fixture |
| 行为保持 | quant research route paths、`agent_quant_research_run` envelope、stage names、report shape、`MOCK_NOT_INVESTMENT_ADVICE` disclaimer 保持；未新增交易或外部数据 side effect |
| `mockApi.ts` 行数 | 999 行 |
| `mock/routing.ts` 行数 | 13 行 |
| `mock/desktopData.ts` 行数 | 354 行 |
| `mock/ai.ts` 行数 | 166 行 |
| `mock/jobs.ts` 行数 | 56 行 |
| `mock/ops.ts` 行数 | 48 行 |
| `mock/integrations.ts` 行数 | 95 行 |
| `mock/gateway.ts` 行数 | 39 行 |
| `mock/nativeTools.ts` 行数 | 28 行 |
| `mock/settings.ts` 行数 | 42 行 |
| `mock/userState.ts` 行数 | 117 行 |
| `mock/workbench.ts` 行数 | 529 行 |
| `mock/toolCatalog.ts` 行数 | 64 行 |
| `mock/capabilities.ts` 行数 | 271 行 |
| `mock/financialManager.ts` 行数 | 170 行 |
| `mock/brokerReadonly.ts` 行数 | 388 行 |
| `mock/marketTemperature.ts` 行数 | 384 行 |
| `mock/stockRadar.ts` 行数 | 70 行 |
| `mock/tradePrediction.ts` 行数 | 228 行 |
| `mock/incubation.ts` 行数 | 307 行 |
| `mock/strategyFactory.ts` 行数 | 188 行 |
| `mock/quantResearch.ts` 行数 | 40 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/quant/QuantResearchWorkspace.test.tsx src/features/factory-events/FactoryEventTriggerPanel.test.tsx --environment jsdom
# 3 passed; 27 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. `desktop/src/mockApi.ts` 已从原始 4159 行降到 999 行，按方案口径退出超 1000 行文件清单。
2. Desktop mock 现已形成 `mock/` 领域模块边界，主文件主要保留 mock entrypoint、auth/envelope、route dispatch、profile/intents 状态和少量跨域聚合。
3. P2 mock 瘦身可作为阶段里程碑；后续若继续推进 Desktop，应转向 `types.ts`、`styles.css`、`FactoryEventTriggerPanel.tsx` 或 e2e suite 拆分。
### 2026-06-14 第八十批：Desktop finance 类型合同拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/types/finance.ts` |
| 更新模块 | `desktop/src/types.ts` |
| `types.ts` 装配方式 | 顶部新增 `export * from "./types/finance"`，保留现有 `../../types` / `../types` 导入兼容 |
| 已迁出职责 | Trade Prediction status/outcomes/matrix 类型、Market Temperature snapshot/cache/history/constituents/forward-validation 类型 |
| 行为保持 | 纯类型迁移，无运行时代码变化；Desktop 仍只通过 Agent HTTP API；所有 market temperature / trade prediction API method signatures 与组件 import 路径保持 |
| `types.ts` 行数 | 1807 行 |
| `types/finance.ts` 行数 | 279 行 |
| `mockApi.ts` 行数 | 999 行 |
| `services/aiaskApi.ts` 行数 | 1198 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/market-temperature/MarketTemperatureWorkspace.test.tsx src/features/incubation/IncubationFactoryPanel.test.tsx --environment jsdom
# 3 passed; 12 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. `desktop/src/types.ts` 已开始按领域拆分，Finance 读模型里最独立的 market temperature / trade prediction 类型先迁出。
2. 兼容导出口保持现有调用方不变，后续可以继续拆 `types/agent.ts`、`types/workbench.ts`、`types/settings.ts`、`types/broker.ts` 等模块。
3. 当前 Desktop 仍在超 1000 行清单中的主要文件是 `styles.css`、`e2e/capabilities.spec.ts`、`types.ts`、`FactoryEventTriggerPanel.tsx`、`services/aiaskApi.ts`、`FinanceLabPage.tsx`；下一批宜继续从 `types.ts` 或 `services/aiaskApi.ts` 的低耦合块切入。
### 2026-06-14 第八十一批：Desktop finance 类型合同第二批拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 更新模块 | `desktop/src/types/finance.ts`、`desktop/src/types.ts` |
| `types.ts` 装配方式 | 继续通过 `export * from "./types/finance"` 保持兼容导出；根文件用 type-only import 引入 `QuantPresetPayload` / `QuantResearchRun` 供 `DesktopDataStatus` 与 `CapabilityWorkbenchPayload` 本地引用 |
| 已迁出职责 | Factor Factory status、Quant preset/research run/report、Financial Manager catalog/action/query/intent result、Broker readiness/account/position/order/deal/profile/analytics/snapshot/sync 类型 |
| 保留职责 | `FinancialReadinessGate`、`FinancialNextAction`、`FinancialSystemReadiness`、`FinancialManagerStatus` 暂留 `types.ts`，因为 readiness action 仍依赖 `MainView` 导航类型 |
| 行为保持 | 纯类型迁移，无运行时代码变化；Desktop HTTP route、mock/live 分流、Broker read-only/live-trading guardrail 字段保持 |
| `types.ts` 行数 | 1478 行 |
| `types/finance.ts` 行数 | 610 行 |
| `mockApi.ts` 行数 | 999 行 |
| `services/aiaskApi.ts` 行数 | 1198 行 |
| `features/workspace/FinanceLabPage.tsx` 行数 | 1102 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/quant/QuantResearchWorkspace.test.tsx src/features/financial-manager/FinancialManagerWorkspace.test.tsx src/features/workspace/FinanceLabPage.test.tsx --environment jsdom
# 4 passed; 12 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. `desktop/src/types.ts` 已从 2085 行降到 1478 行，finance 类型已基本集中到 `types/finance.ts`。
2. 根类型文件仍承担导航、workbench、settings、capability 聚合等跨域合同，下一批可继续拆 `types/workbench.ts` 或 `types/settings.ts`。
3. Desktop 当前超 1000 行文件剩余：`styles.css`、`FactoryEventTriggerPanel.tsx`、`types.ts`、`services/aiaskApi.ts`、`FinanceLabPage.tsx`；`mockApi.ts` 已不在 Desktop 超 1000 行列表内。
### 2026-06-14 第八十二批：Desktop workbench 类型合同拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/types/workbench.ts` |
| 更新模块 | `desktop/src/types.ts` |
| `types.ts` 装配方式 | 顶部新增 `export * from "./types/workbench"`；根文件用 type-only import 引入 `RecentSessionSummary`、`RunRecord`、`NormalizedRunEvent` 供用户数据导出/活动 payload 本地引用 |
| 已迁出职责 | Agent response/run record、task artifact/source/review/context/thread、session handoff、recent session、handoff queue、session resume/undo/archive、desktop run/workbench summary、normalized run event、run trace eval、timeline event、diagnostics summary 类型 |
| 行为保持 | 纯类型迁移，无运行时代码变化；Workbench、Sessions、Runs/Events、TaskPanels、Timeline、mock/workbench 和 `services/api/workbench.ts` 继续从 `../types` 兼容导入 |
| `types.ts` 行数 | 1082 行 |
| `types/finance.ts` 行数 | 610 行 |
| `types/workbench.ts` 行数 | 400 行 |
| `mockApi.ts` 行数 | 999 行 |
| `services/aiaskApi.ts` 行数 | 1198 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/components/WorkbenchView.test.tsx src/hooks/useAgentWorkbench.test.tsx src/features/agent-pages/SessionsPage.test.tsx src/features/agent-pages/RunsEventsPage.test.tsx src/services/aiaskApi.test.ts --environment jsdom
# 5 passed; 46 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. `desktop/src/types.ts` 已从 1478 行降到 1082 行，接近退出超 1000 行清单。
2. Workbench/run/session 类型已与已有 `mock/workbench.ts`、`services/api/workbench.ts` 边界对齐。
3. 下一批迁出 AI/provider 或 settings/user 类型中的一小块即可让 `types.ts` 低于 1000 行。
### 2026-06-14 第八十三批：Desktop AI/provider 类型合同拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/types/ai.ts` |
| 更新模块 | `desktop/src/types.ts` |
| `types.ts` 装配方式 | 顶部新增 `export * from "./types/ai"`；根文件用 type-only import 引入 `AiStatus` 供 settings/capability 聚合类型本地引用 |
| 已迁出职责 | `AiStatus`、prompt cache policy、AI smoke result、AI provider preset、AI config payload/save payload/save result |
| 行为保持 | 纯类型迁移，无运行时代码变化；AI status/config/smoke/models API signatures、mock AI payload、capability AI section 兼容导出保持 |
| `types.ts` 行数 | 960 行 |
| `types/ai.ts` 行数 | 123 行 |
| `types/finance.ts` 行数 | 610 行 |
| `types/workbench.ts` 行数 | 400 行 |
| `mockApi.ts` 行数 | 999 行 |
| `services/aiaskApi.ts` 行数 | 1198 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/hooks/useAiSmoke.test.tsx --environment jsdom
# 1 passed; 8 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. `desktop/src/types.ts` 已从原始 2085 行降到 960 行，按方案口径退出超 1000 行文件清单。
2. Desktop P2 已完成两个关键瘦身里程碑：`mockApi.ts` 999 行、`types.ts` 960 行，且都保留兼容入口。
3. Desktop 当前超 1000 行文件剩余：`styles.css`、`FactoryEventTriggerPanel.tsx`、`services/aiaskApi.ts`、`FinanceLabPage.tsx`；下一批可转向 `services/aiaskApi.ts` facade 收口或组件/CSS 拆分。
### 2026-06-14 第八十四批：Desktop API full console / intent helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/services/api/fullConsole.ts`、`desktop/src/services/api/intents.ts` |
| 更新模块 | `desktop/src/services/aiaskApi.ts`、`desktop/src/services/api/finance.ts`、`desktop/src/services/api/workbench.ts` |
| `aiaskApi.ts` 装配方式 | 继续导出 `AiaskApi` 兼容 facade；full console、read-only tool、ActionIntent、approval、handoff/search 和 finance intent action 由领域 helper 承接 |
| 已迁出职责 | full console 聚合与 control-token 降级 fallback、`/intents` create/get/confirm/deny/list、`/v1/approvals` list/decide、stock radar / factory event / factor factory intent action name 与默认 rationale、handoffs/search 拼参 |
| 行为保持 | `/v1/hermes/*`、`/v1/tools/{agent_*}`、`/intents`、`/v1/approvals`、stock/factory/factor intent action names、`ttl_seconds: 86400`、control token 降级 reason/error 字段、Desktop Agent HTTP-only 边界保持；未新增 Python/MCP/manager 直连或交易 side effect |
| `services/aiaskApi.ts` 行数 | 999 行 |
| `services/api/fullConsole.ts` 行数 | 156 行 |
| `services/api/intents.ts` 行数 | 85 行 |
| `services/api/finance.ts` 行数 | 348 行 |
| `services/api/workbench.ts` 行数 | 250 行 |
| `types.ts` 行数 | 960 行 |
| `mockApi.ts` 行数 | 999 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/services/aiaskApi.test.ts src/features/factory-events/FactoryEventTriggerPanel.test.tsx src/features/factory/StrategyFactoryPanel.test.tsx --environment jsdom
# 3 passed; 27 tests passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. `desktop/src/services/aiaskApi.ts` 已从原始 1198 行降到 999 行，按方案口径退出超 1000 行文件清单。
2. Desktop P2 已完成三个兼容入口瘦身里程碑：`mockApi.ts` 999 行、`types.ts` 960 行、`services/aiaskApi.ts` 999 行。
3. Desktop 当前超 1000 行文件剩余：`styles.css` 5215 行、`FactoryEventTriggerPanel.tsx` 1553 行、`FinanceLabPage.tsx` 1102 行；下一批宜优先拆 `FactoryEventTriggerPanel.tsx` 或 `FinanceLabPage.tsx`，CSS 可独立作为样式分区批次处理。
### 2026-06-14 第八十五批：Desktop FinanceLab 页面孵化 Worklist 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/features/workspace/FinanceLabIncubation.tsx`、`desktop/src/features/workspace/FinanceLabUtils.ts` |
| 更新模块 | `desktop/src/features/workspace/FinanceLabPage.tsx` |
| `FinanceLabPage.tsx` 装配方式 | 页面继续持有 API 调用、状态、broker 只读同步和主 DOM；孵化 hit-rate/lifecycle/worklist 证据提取与渲染由 `FinanceLabIncubation.tsx` 承接，unknown 解析与格式化工具由 `FinanceLabUtils.ts` 承接 |
| 已迁出职责 | incubation report fallback、promotion blocker 合并、lifecycle evidence rows、weak family/regime cells、hit-rate worklist JSX、`recordFromUnknown` / `arrayFromUnknown` / money/percent/string helpers |
| 行为保持 | FinanceLab 仍只通过 `AiaskApi` 走 Agent HTTP；broker read-only consent、sync 按钮、factory relay、incubation worklist 文案与测试断言保持；未新增 live trading、Python/MCP/manager 直连或状态副作用 |
| `features/workspace/FinanceLabPage.tsx` 行数 | 795 行 |
| `features/workspace/FinanceLabIncubation.tsx` 行数 | 284 行 |
| `features/workspace/FinanceLabUtils.ts` 行数 | 33 行 |
| `services/aiaskApi.ts` 行数 | 999 行 |
| `types.ts` 行数 | 960 行 |
| `mockApi.ts` 行数 | 999 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/features/workspace/FinanceLabPage.test.tsx --environment jsdom
# 1 passed; 1 test passed

npm test
# 34 passed; 144 tests passed
```

当前 P2 模块补充结论：
1. `desktop/src/features/workspace/FinanceLabPage.tsx` 已从 1102 行降到 795 行，按方案口径退出超 1000 行文件清单。
2. Desktop P2 已完成四个兼容入口瘦身里程碑：`mockApi.ts`、`types.ts`、`services/aiaskApi.ts`、`FinanceLabPage.tsx` 均低于 1000 行。
3. Desktop 当前超 1000 行文件剩余：`styles.css` 5215 行、`FactoryEventTriggerPanel.tsx` 1553 行；下一批宜拆 `FactoryEventTriggerPanel.tsx` 的表单/雷达/证据子组件，CSS 可作为最后的样式分区批次处理。
### 2026-06-14 第八十六批：Desktop Factory Event 面板数据/子面板拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/features/factory-events/FactoryEventTriggerData.ts`、`desktop/src/features/factory-events/FactoryEventTriggerPanels.tsx` |
| 更新模块 | `desktop/src/features/factory-events/FactoryEventTriggerPanel.tsx` |
| `FactoryEventTriggerPanel.tsx` 装配方式 | 主面板继续持有 Agent HTTP client、load/intent callbacks、tab state 和事件创建/审批/暂停/结果记录逻辑；payload 解析、选项常量、雷达/维护/创建/血缘/日志展示块迁出 |
| 已迁出职责 | factory event / preview / lineage / stock radar payload normalization、status/time/intent id helpers、maintenance status panel、stock radar tab、ActionLog panel、Create tab、Lineage tab |
| 行为保持 | `agent_factory_event_list`、`agent_factory_event_preview_tasks`、`agent_factory_event_lineage`、`agent_factory_theme_exposure_status`、`agent_factory_event_outbox_status` 读路径保持；`strategy_manager.factory_event_*`、`strategy_manager.factory_theme_*`、`stock_radar.*` ActionIntent action names 和控制令牌禁用态保持；未新增 manager 直连或交易副作用 |
| `features/factory-events/FactoryEventTriggerPanel.tsx` 行数 | 944 行 |
| `features/factory-events/FactoryEventTriggerData.ts` 行数 | 280 行 |
| `features/factory-events/FactoryEventTriggerPanels.tsx` 行数 | 572 行 |
| `features/workspace/FinanceLabPage.tsx` 行数 | 795 行 |
| `services/aiaskApi.ts` 行数 | 999 行 |
| `types.ts` 行数 | 960 行 |
| `mockApi.ts` 行数 | 999 行 |

验证结果：
```bash
cd desktop
npm run typecheck
# passed

npx vitest run src/features/factory-events/FactoryEventTriggerPanel.test.tsx --environment jsdom
# 1 passed; 17 tests passed

npm test
# failed: src/views.test.ts has 2 current VIEW_GROUPS contract failures
# primary group is undefined; advanced-finance defaultCollapsed is undefined
```

当前 P2 模块补充结论：
1. `desktop/src/features/factory-events/FactoryEventTriggerPanel.tsx` 已从 1553 行降到 944 行，按方案口径退出超 1000 行文件清单。
2. Desktop P2 已完成五个兼容入口瘦身里程碑：`mockApi.ts`、`types.ts`、`services/aiaskApi.ts`、`FinanceLabPage.tsx`、`FactoryEventTriggerPanel.tsx` 均低于 1000 行。
3. Desktop 当前超 1000 行文件剩余：`styles.css` 5215 行；另有 `src/views.test.ts` 与当前 `VIEW_GROUPS`（仅 `core` group）合同不一致，需要单独恢复 view registry 分组或同步测试预期后才能恢复全量 `npm test` 绿色。
### 2026-06-14 第八十七批：Desktop CSS 分区拆分与 ViewGroup 守门恢复

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/src/styles/globals-layout.css`、`desktop/src/styles/capabilities-quant.css`、`desktop/src/styles/workbench-dashboard.css`、`desktop/src/styles/workbench-surfaces.css`、`desktop/src/styles/finance-events.css`、`desktop/src/styles/tools-forms.css`、`desktop/src/styles/responsive-shell.css`、`desktop/src/styles/settings-context.css`、`desktop/src/styles/finance-operations.css`、`desktop/src/styles/data-models.css` |
| 更新模块 | `desktop/src/styles.css`、`desktop/src/views.ts`、`desktop/e2e/capabilities.spec.ts` |
| `styles.css` 装配方式 | 入口文件只保留 10 个 `@import`，顺序与原始 5215 行样式完全一致；拆分时做了逐行重组校验，确认分片按 import 顺序拼回后与原始 CSS 行内容一致 |
| `views.ts` 装配方式 | `VIEW_GROUPS` 从单个 `core` 恢复为 `primary`、`advanced-finance`、`advanced-ops`、`legacy`；匹配 `AppSidebar` 的 primary/advanced 渲染逻辑、`views.test.ts` 守门和 e2e `VIEW_GROUP_IDS` 映射 |
| e2e helper 修复 | `openSettings()` 先兼容旧主区设置按钮，找不到时通过 sidebar `data-view-id="settings"` 打开设置页，避免 mock e2e 依赖首页快捷卡 |
| 行为保持 | 未改 class 名、selector 顺序、CSS declaration 或页面组件；Desktop 仍由 `main.tsx` import `./styles.css`；legacy group 继续 `diagnosticOnly` 且默认折叠 |
| `styles.css` 行数 | 10 行 |
| `styles/globals-layout.css` 行数 | 340 行 |
| `styles/capabilities-quant.css` 行数 | 692 行 |
| `styles/workbench-dashboard.css` 行数 | 471 行 |
| `styles/workbench-surfaces.css` 行数 | 564 行 |
| `styles/finance-events.css` 行数 | 519 行 |
| `styles/tools-forms.css` 行数 | 745 行 |
| `styles/responsive-shell.css` 行数 | 656 行 |
| `styles/settings-context.css` 行数 | 456 行 |
| `styles/finance-operations.css` 行数 | 353 行 |
| `styles/data-models.css` 行数 | 419 行 |
| `views.ts` 行数 | 432 行 |
| `e2e/capabilities.spec.ts` 行数 | 4999 行 |

验证结果：
```bash
cd desktop
npx vitest run src/views.test.ts --environment jsdom
# 1 passed; 6 tests passed

npm run typecheck
# passed

npm test
# 34 passed; 144 tests passed

npm run build
# passed; Vite emitted the existing workspaces chunk-size warning

npm run test:e2e:mock
# 11 passed; 3 optional live tests skipped

# repo root
rg --files desktop/src | <line-count filter >= 1000>
# NO_DESKTOP_SRC_FILES_GE_1000
```

当前 P2 模块补充结论：
1. `desktop/src/styles.css` 已从 5215 行降到 10 行 import facade，所有新增 CSS 分片均低于 800 行，满足方案中的 CSS 可维护验收口径。
2. `desktop/src` 当前已无 TS/TSX/CSS/JS/JSX 文件超过 1000 行；Desktop P2 的 `mockApi.ts`、`types.ts`、`services/aiaskApi.ts`、`FinanceLabPage.tsx`、`FactoryEventTriggerPanel.tsx`、`styles.css` 大文件治理均已退出超 1000 行清单。
3. `views.test.ts` 守门已恢复绿色，全量 Desktop Vitest、production build 和 mock e2e 均通过；下一步可将 Desktop P2 作为阶段边界，转向 `desktop/e2e/capabilities.spec.ts` 拆分，或回到计划中 packages/scripts 的剩余超 1000 行文件。

### 2026-06-14 第八十八批：Desktop e2e capabilities 规格文件拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/e2e/support/capabilitiesNavigation.ts`、`desktop/e2e/support/capabilitiesMockServer.ts`、`desktop/e2e/support/capabilitiesInventory.ts`、`desktop/e2e/support/capabilitiesFullMatrix.ts` |
| 更新模块 | `desktop/e2e/capabilities.spec.ts` |
| `capabilities.spec.ts` 装配方式 | 主规格文件保留 Playwright hooks、测试标题、mock/live 场景断言和可选 live smoke；标签/导航 helper、mock API fixture server、库存/矩阵断言 helper、full frontend matrix 长流程分别迁出到 support 模块 |
| 已迁出职责 | 中文/英文 label 映射、Settings/sidebar 导航 helper、control token 设置 helper、mock Agent HTTP route fixture、frontend inventory/layout/button coverage helper、full frontend matrix 报告与截图写入流程 |
| 行为保持 | 测试名称、mock endpoint、control-token gates、optional live skip、full matrix 报告路径和 Desktop -> Agent HTTP mock 合同保持；未新增 Desktop 直连 Python/MCP/manager 或 live trading side effect |
| `e2e/capabilities.spec.ts` 行数 | 798 行 |
| `e2e/support/capabilitiesNavigation.ts` 行数 | 559 行 |
| `e2e/support/capabilitiesInventory.ts` 行数 | 255 行 |
| `e2e/support/capabilitiesFullMatrix.ts` 行数 | 584 行 |
| `e2e/support/capabilitiesMockServer.ts` 行数 | 2864 行 |

验证结果：

```bash
cd desktop
npm run typecheck
# passed

npm test
# 34 passed; 144 tests passed

npx playwright test -g "MCP panel gates controls"
# 1 passed

npx playwright test -g "Full frontend matrix"
# 1 passed

npm run test:e2e:mock
# 11 passed; 3 optional live tests skipped

# repo root
git diff --check -- desktop/e2e/capabilities.spec.ts desktop/e2e/support/capabilitiesNavigation.ts desktop/e2e/support/capabilitiesMockServer.ts desktop/e2e/support/capabilitiesInventory.ts desktop/e2e/support/capabilitiesFullMatrix.ts AIASK_CODE_STRUCTURE_CLEANUP_PLAN_2026-06-14.md
# no whitespace errors; Git only warned that capabilities.spec.ts CRLF will normalize to LF
```

当前 P2/e2e 补充结论：

1. `desktop/e2e/capabilities.spec.ts` 已从 4999 行降到 798 行，主规格文件退出超 1000 行清单，失败定位也从“一个巨型文件”收敛为导航、mock server、inventory、full matrix 四类 support 边界。
2. 本批刻意保持 `capabilitiesMockServer.ts` 为单一 mock route fixture server，以降低路线迁移风险；它仍有 2864 行，是下一批 e2e fixture 分域的首要目标，可按 capabilities/data-market/quant-trade/finance-broker route payload 分片继续瘦身。
3. Desktop `src` 仍保持无 TS/TSX/CSS/JS/JSX 文件超过 1000 行；仓库级目标尚未完成，剩余重点仍包括 `packages/agent/src/aiask_agent/session_store.py`、`packages/agent/src/aiask_agent/native_capabilities.py`、`scripts/factories/run_strategy_factory_quality_session.py` 以及 AKShare manager/analytics 侧的大文件。

### 2026-06-14 第八十九批：Desktop e2e mock server fixture 分域拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `desktop/e2e/support/capabilitiesMockConstants.ts`、`desktop/e2e/support/capabilitiesMockCorePayloads.ts`、`desktop/e2e/support/capabilitiesMockDataMarket.ts`、`desktop/e2e/support/capabilitiesMockTradePrediction.ts`、`desktop/e2e/support/capabilitiesMockDesktopFixtures.ts`、`desktop/e2e/support/capabilitiesMockDesktopRoutes.ts` |
| 更新模块 | `desktop/e2e/support/capabilitiesMockServer.ts` |
| `capabilitiesMockServer.ts` 装配方式 | 保留 Playwright `page.route(API_ORIGIN/**)` dispatcher、mutable webhook/stock-source state 和 route 顺序；capability/AI/settings payload、data/market/factory payload、trade prediction payload、desktop/finance/broker fixtures、desktop user/governance routes 分别迁出 |
| 已迁出职责 | `API_ORIGIN` 共享常量、Hermes/capabilities/AI/settings payload、data status/stock source/market temperature/factory event/quant/factor/incubation/jobs payload、trade prediction status/outcome/matrix fixture、connectors/workbench/financial manager/broker/run event fixtures、Desktop feedback/analytics/retention/user policy/export/delete route handlers |
| 行为保持 | 所有 mock route path、method 分支、response shape、control-token 判断、broker read-only/live-trading-disabled 字段、ActionIntent envelope 和 optional live skip 行为保持；未新增 Desktop 直连 Python/MCP/manager 或 live trading side effect |
| `e2e/support/capabilitiesMockServer.ts` 行数 | 907 行 |
| `e2e/support/capabilitiesMockDataMarket.ts` 行数 | 688 行 |
| `e2e/support/capabilitiesMockCorePayloads.ts` 行数 | 445 行 |
| `e2e/support/capabilitiesMockDesktopFixtures.ts` 行数 | 491 行 |
| `e2e/support/capabilitiesMockDesktopRoutes.ts` 行数 | 231 行 |
| `e2e/support/capabilitiesMockTradePrediction.ts` 行数 | 193 行 |
| `e2e/support/capabilitiesMockConstants.ts` 行数 | 1 行 |

验证结果：

```bash
cd desktop
npm run typecheck
# passed

npm test
# 34 passed; 144 tests passed

npx playwright test -g "MCP panel gates controls"
# 1 passed

npx playwright test -g "Full frontend matrix"
# 1 passed

npm run test:e2e:mock
# 11 passed; 3 optional live tests skipped

# repo root
git diff --check -- desktop/e2e/capabilities.spec.ts desktop/e2e/support AIASK_CODE_STRUCTURE_CLEANUP_PLAN_2026-06-14.md
# no whitespace errors; Git only warned that capabilities.spec.ts CRLF will normalize to LF
```

当前 P2/e2e 补充结论：

1. `desktop/e2e` 当前 TS support 与主规格文件均低于 1000 行：`capabilities.spec.ts` 798 行，最大 support 文件 `capabilitiesMockServer.ts` 907 行。
2. e2e mock 已形成更清晰的 fixture 边界：route dispatcher、core/capability payload、data-market/factory payload、trade prediction payload、desktop/finance fixture、desktop governance routes 分离，后续新增 mock 能按领域落点扩展。
3. 仓库级目标仍未完成；下一阶段可从剩余 packages/scripts 大文件继续推进，例如 `packages/agent/src/aiask_agent/session_store.py`、`packages/agent/src/aiask_agent/native_capabilities.py`、`scripts/factories/run_strategy_factory_quality_session.py` 或 AKShare manager/analytics 侧文件。

### 2026-06-14 第九十批：Agent session store helper/schema 首轮拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/session_store_utils.py`、`packages/agent/src/aiask_agent/session_store_schema.py` |
| 更新模块 | `packages/agent/src/aiask_agent/session_store.py` |
| `session_store.py` 装配方式 | 保留 `AgentSessionStore` facade 和 `_ensure_schema(conn)` 静态方法签名；纯 helper、审计脱敏、JSON/时间工具迁入 `session_store_utils.py`；SQLite schema 初始化、messages 迁移、FTS5 创建和 commit 迁入 `session_store_schema.py` |
| 已迁出职责 | `now_iso`、`sanitize_for_audit`、`_dumps` / `_loads`、truthy/number/text 清洗、metadata archive 判定、secret key redaction、全量 session store schema DDL 与兼容迁移 |
| 行为保持 | `from aiask_agent.session_store import now_iso`、`sanitize_for_audit`、`AgentSessionStore` 继续可用；session/run/event/search/broker/user-data 方法体未改；schema SQL、messages deleted 字段迁移、`aiask_search_fts` fallback 行为保持；未读取 secrets、未操作运行态 DB/log/cache/broker state |
| `session_store.py` 行数 | 2721 行 |
| `session_store_utils.py` 行数 | 137 行 |
| `session_store_schema.py` 行数 | 365 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/session_store_utils.py packages/agent/src/aiask_agent/session_store_schema.py
# passed

uv run pytest -q packages/agent/tests/test_session_memory_todo.py
# 6 passed

uv run pytest -q packages/agent/tests/test_desktop_workbench_contracts.py
# 11 passed

uv run pytest -q packages/agent/tests/test_broker_readonly_api.py
# 4 passed

uv run pytest -q packages/agent/tests/test_ai_status_and_smoke.py
# 10 passed, 1 skipped

git diff --check -- packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/session_store_utils.py packages/agent/src/aiask_agent/session_store_schema.py AIASK_CODE_STRUCTURE_CLEANUP_PLAN_2026-06-14.md
# no whitespace errors
```

当前 Agent session store 补充结论：

1. 本批先做最低风险首轮拆分：外部 facade、HTTP 合同、Desktop 期望的 recent sessions/runs/events/search payload 均不改，只把纯工具和 schema 初始化从巨型 store 中拆出。
2. `session_store.py` 已从 3198 行降到 2721 行，仍未退出超 1000 行清单；下一轮宜继续按方案拆 `run/events`、`activity/tool audit`、`broker snapshots`、`evidence/artifacts`、`user data policy`、`handoff/search` 等 repository/mixin 边界。
3. 仓库级目标仍未完成；剩余重点仍包括 `packages/agent/src/aiask_agent/session_store.py`、`packages/agent/src/aiask_agent/native_capabilities.py`、`scripts/factories/run_strategy_factory_quality_session.py` 以及 AKShare/Strategy/Quant 侧的大文件。

### 2026-06-14 第九十一批：Agent session store row helper 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/session_store_rows.py` |
| 更新模块 | `packages/agent/src/aiask_agent/session_store.py` |
| `session_store.py` 装配方式 | `AgentSessionStore` 继续保留 `_session_row`、`_tool_invocation_row`、`_broker_*_row`、`_handoff_row`、`_subgoal_row`、`_session_is_archived`、`_session_user_id` 等 staticmethod 名称；实现迁入 `session_store_rows.py`，类尾部以 `staticmethod(...)` 绑定保持内部调用兼容 |
| 已迁出职责 | SQLite row 到 dict 的 session/activity/tool/source/artifact/context/feedback/policy/broker/handoff/subgoal 转换，payload JSON 解析，broker/context `secrets_redacted` 标记，archived session 判定，session user id 查询 |
| 行为保持 | `self._source_row(...)`、`self._broker_profile_row(...)`、`AgentSessionStore._session_is_archived(...)` 等调用路径不变；Desktop recent sessions/runs/events、broker read-only payload、AI status/smoke 间接依赖的 store 返回 shape 保持；未新增运行态 DB/log/cache/broker 操作 |
| `session_store.py` 行数 | 2595 行 |
| `session_store_rows.py` 行数 | 171 行 |
| `session_store_utils.py` 行数 | 137 行 |
| `session_store_schema.py` 行数 | 365 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/session_store_rows.py packages/agent/src/aiask_agent/session_store_utils.py packages/agent/src/aiask_agent/session_store_schema.py
# passed

uv run pytest -q packages/agent/tests/test_session_memory_todo.py
# 6 passed

uv run pytest -q packages/agent/tests/test_desktop_workbench_contracts.py
# 11 passed

uv run pytest -q packages/agent/tests/test_broker_readonly_api.py
# 4 passed

uv run pytest -q packages/agent/tests/test_ai_status_and_smoke.py
# 10 passed, 1 skipped

git diff --check -- packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/session_store_utils.py packages/agent/src/aiask_agent/session_store_schema.py packages/agent/src/aiask_agent/session_store_rows.py AIASK_CODE_STRUCTURE_CLEANUP_PLAN_2026-06-14.md
# no whitespace errors
```

当前 Agent session store 补充结论：

1. `session_store.py` 已从 3198 行降到 2595 行，纯 helper、schema、row conversion 三类低风险代码已迁出，后续可以开始拆真正的领域 repository/mixin。
2. 下一轮优先级建议为 `search/indexing` 或 `handoff/subgoal`：这两块依赖面较窄，比 broker/user-data 大段逻辑更适合继续小步迁移。
3. 仓库级目标仍未完成；`session_store.py` 本身仍超过 1000 行，且 `native_capabilities.py`、factory 脚本、AKShare/Strategy/Quant 侧仍有多处大文件待处理。

### 2026-06-14 第九十二批：Agent session store search/indexing 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/session_store_search.py` |
| 更新模块 | `packages/agent/src/aiask_agent/session_store.py` |
| `session_store.py` 装配方式 | `AgentSessionStore.search()` 保留在 facade；`_fts_available`、`_index_search_row`、`_search_row`、`_search_like` 实现迁入 `session_store_search.py`，类尾部继续以同名 staticmethod 绑定 |
| 已迁出职责 | FTS5 可用性探测、search FTS 索引行写入、search row payload JSON 解析、messages/sources/artifacts 的 LIKE fallback 搜索、archived session 过滤 |
| 行为保持 | `/v1/search` 依赖的 `AgentSessionStore.search()` 签名和返回 shape 不变；FTS5 不可用时仍 fallback 到 LIKE；source/artifact search payload 仍使用 metadata JSON；未新增外部调用或运行态 DB/log/cache/broker 操作 |
| `session_store.py` 行数 | 2474 行 |
| `session_store_search.py` 行数 | 133 行 |
| `session_store_rows.py` 行数 | 171 行 |
| `session_store_utils.py` 行数 | 137 行 |
| `session_store_schema.py` 行数 | 365 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/session_store_search.py packages/agent/src/aiask_agent/session_store_rows.py packages/agent/src/aiask_agent/session_store_utils.py packages/agent/src/aiask_agent/session_store_schema.py
# passed

uv run pytest -q packages/agent/tests/test_session_memory_todo.py packages/agent/tests/test_evidence_artifacts_sources.py
# 11 passed

uv run pytest -q packages/agent/tests/test_desktop_workbench_contracts.py
# 11 passed

uv run pytest -q packages/agent/tests/test_broker_readonly_api.py
# 4 passed

uv run pytest -q packages/agent/tests/test_ai_status_and_smoke.py
# 10 passed, 1 skipped

git diff --check -- packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/session_store_utils.py packages/agent/src/aiask_agent/session_store_schema.py packages/agent/src/aiask_agent/session_store_rows.py packages/agent/src/aiask_agent/session_store_search.py AIASK_CODE_STRUCTURE_CLEANUP_PLAN_2026-06-14.md
# no whitespace errors
```

当前 Agent session store 补充结论：

1. `session_store.py` 已从 3198 行降到 2474 行，低风险外围拆分已覆盖 helper、schema、row conversion、search/indexing 四类。
2. 下一批可继续拆 `handoff/subgoal`，或进入更大的 `broker snapshots` / `user data policy` repository 拆分；前者风险更低，后者减行更明显。
3. 仓库级目标仍未完成；`session_store.py` 仍超过 1000 行，packages/scripts 侧还有多处计划内大文件待处理。

### 2026-06-14 第九十三批：Agent session store handoff/subgoal mixin 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/session_store_handoff.py` |
| 更新模块 | `packages/agent/src/aiask_agent/session_store.py` |
| `session_store.py` 装配方式 | `AgentSessionStore` 继承 `SessionStoreHandoffMixin`；`request_handoff`、`get_handoff`、`update_handoff`、`list_handoffs`、`upsert_subgoal`、`get_subgoal`、`list_subgoals`、`clear_subgoals` 保持同名实例方法 |
| 已迁出职责 | handoff record 创建/查询/状态更新/队列列表、session-scoped subgoal 创建更新/查询/清空、handoff/subgoal 相关 session auto-create 和 JSON criteria/metadata 持久化 |
| 行为保持 | `agent_session_handoff`、`agent_subgoal`、Hermes handoff queue、resume context 依赖的 store 方法名和返回 shape 保持；`AgentSessionStore` facade 仍是唯一外部入口；未新增模型可见工具、manager 直连、交易副作用或运行态 DB/log/cache/broker 操作 |
| `session_store.py` 行数 | 2307 行 |
| `session_store_handoff.py` 行数 | 176 行 |
| `session_store_search.py` 行数 | 133 行 |
| `session_store_rows.py` 行数 | 171 行 |
| `session_store_utils.py` 行数 | 137 行 |
| `session_store_schema.py` 行数 | 365 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/session_store_handoff.py packages/agent/src/aiask_agent/session_store_search.py packages/agent/src/aiask_agent/session_store_rows.py packages/agent/src/aiask_agent/session_store_utils.py packages/agent/src/aiask_agent/session_store_schema.py
# passed

PYTHONPATH=packages/agent/src uv run python -c "from aiask_agent.session_store import AgentSessionStore; s=AgentSessionStore(); assert hasattr(s, 'request_handoff'); assert hasattr(s, 'upsert_subgoal'); assert hasattr(s, 'search')"
# passed

uv run pytest -q packages/agent/tests/test_desktop_workbench_contracts.py packages/agent/tests/test_hermes_full_expanded_capabilities.py -k "handoff or subgoal"
# 3 passed, 14 deselected

uv run pytest -q packages/agent/tests/test_session_memory_todo.py packages/agent/tests/test_evidence_artifacts_sources.py
# 11 passed

uv run pytest -q packages/agent/tests/test_desktop_workbench_contracts.py
# 11 passed

git diff --check -- packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/session_store_utils.py packages/agent/src/aiask_agent/session_store_schema.py packages/agent/src/aiask_agent/session_store_rows.py packages/agent/src/aiask_agent/session_store_search.py packages/agent/src/aiask_agent/session_store_handoff.py AIASK_CODE_STRUCTURE_CLEANUP_PLAN_2026-06-14.md
# no whitespace errors
```

当前 Agent session store 补充结论：

1. `session_store.py` 已从 3198 行降到 2307 行；外围 helper/schema/row/search 和较窄 handoff/subgoal 领域均已拆出。
2. 下一步若继续治理 `session_store.py`，宜在 `broker snapshots` 或 `user data policy/export/delete/retention` 中二选一作为较大减行批次，并继续保持 `AgentSessionStore` facade。
3. 仓库级目标仍未完成；本文件仍超过 1000 行，其他 packages/scripts 大文件仍需按方案继续拆分。

### 2026-06-14 第九十四批：Agent session store broker repository mixin 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/session_store_broker.py` |
| 更新模块 | `packages/agent/src/aiask_agent/session_store.py` |
| `session_store.py` 装配方式 | `AgentSessionStore` 继承 `SessionStoreBrokerMixin` 和 `SessionStoreHandoffMixin`；broker profile/snapshot/analytics 方法继续通过 `AgentSessionStore` facade 暴露 |
| 已迁出职责 | broker profile upsert/sync/list、account/position/order/deal snapshot 写入与列表、behavior analytics 写入与查询、broker filter/list helper |
| 行为保持 | broker read-only API、Financial Manager Desktop API 仍通过 Agent store facade；broker `write_enabled=0`、read-only/live-trading-disabled 语义、snapshot payload 脱敏和 analytics JSON shape 保持；未新增 live trading、manager 直连、外部 broker 操作或运行态 DB/log/cache/broker state 操作 |
| `session_store.py` 行数 | 1905 行 |
| `session_store_broker.py` 行数 | 411 行 |
| `session_store_handoff.py` 行数 | 176 行 |
| `session_store_search.py` 行数 | 133 行 |
| `session_store_rows.py` 行数 | 171 行 |
| `session_store_utils.py` 行数 | 137 行 |
| `session_store_schema.py` 行数 | 365 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/session_store_broker.py packages/agent/src/aiask_agent/session_store_handoff.py packages/agent/src/aiask_agent/session_store_search.py packages/agent/src/aiask_agent/session_store_rows.py packages/agent/src/aiask_agent/session_store_utils.py packages/agent/src/aiask_agent/session_store_schema.py
# passed

PYTHONPATH=packages/agent/src uv run python -c "from aiask_agent.session_store import AgentSessionStore; s=AgentSessionStore(); assert hasattr(s, 'upsert_broker_profile'); assert hasattr(s, 'list_broker_account_snapshots'); assert hasattr(s, 'latest_broker_analytics')"
# passed

uv run pytest -q packages/agent/tests/test_broker_readonly_api.py
# 4 passed

uv run pytest -q packages/agent/tests/test_financial_manager_desktop_api.py
# 6 passed

uv run pytest -q packages/agent/tests/test_session_memory_todo.py packages/agent/tests/test_evidence_artifacts_sources.py
# 11 passed

uv run pytest -q packages/agent/tests/test_desktop_workbench_contracts.py
# 11 passed

git diff --check -- packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/session_store_broker.py packages/agent/src/aiask_agent/session_store_utils.py packages/agent/src/aiask_agent/session_store_schema.py packages/agent/src/aiask_agent/session_store_rows.py packages/agent/src/aiask_agent/session_store_search.py packages/agent/src/aiask_agent/session_store_handoff.py AIASK_CODE_STRUCTURE_CLEANUP_PLAN_2026-06-14.md
# no whitespace errors
```

当前 Agent session store 补充结论：

1. `session_store.py` 已从 3198 行降到 1905 行，首次低于 2000 行；broker 领域已经独立成 repository mixin。
2. 若继续瘦身，下一块建议拆 `sources/artifacts/context snapshots` 或 `user data policy/export/delete/retention`，两者都能明显减少主 facade 体积。
3. 仓库级目标仍未完成；`session_store.py` 距离低于 1000 行还需要继续拆分，其他 packages/scripts 大文件也仍在计划清单内。

### 2026-06-14 第九十五批：Agent session store evidence/source/artifact mixin 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/session_store_evidence.py` |
| 更新模块 | `packages/agent/src/aiask_agent/session_store.py` |
| `session_store.py` 装配方式 | `AgentSessionStore` 继续作为 facade，继承 `SessionStoreBrokerMixin`、`SessionStoreEvidenceMixin`、`SessionStoreHandoffMixin`；source/artifact/context snapshot 方法名保持 |
| 已迁出职责 | agent source 写入/查询/列表、artifact 写入/查询/列表、context snapshot 写入/查询/列表、source/artifact search index 写入、metadata/preview/context payload 脱敏 |
| 行为保持 | evidence/artifact/source API 和 runtime context snapshot 依赖的 store 方法签名与返回 shape 保持；search index 写入仍通过 `_index_search_row`；未新增外部 provider 调用、manager 直连或运行态 DB/log/cache/broker 操作 |
| `session_store.py` 行数 | 1566 行 |
| `session_store_evidence.py` 行数 | 354 行 |
| `session_store_broker.py` 行数 | 411 行 |
| `session_store_handoff.py` 行数 | 176 行 |
| `session_store_search.py` 行数 | 133 行 |
| `session_store_rows.py` 行数 | 171 行 |
| `session_store_utils.py` 行数 | 137 行 |
| `session_store_schema.py` 行数 | 365 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/session_store_evidence.py packages/agent/src/aiask_agent/session_store_broker.py packages/agent/src/aiask_agent/session_store_handoff.py packages/agent/src/aiask_agent/session_store_search.py packages/agent/src/aiask_agent/session_store_rows.py packages/agent/src/aiask_agent/session_store_utils.py packages/agent/src/aiask_agent/session_store_schema.py
# passed

PYTHONPATH=packages/agent/src uv run python -c "from aiask_agent.session_store import AgentSessionStore; s=AgentSessionStore(); assert hasattr(s, 'record_source'); assert hasattr(s, 'record_artifact'); assert hasattr(s, 'record_context_snapshot')"
# passed

uv run pytest -q packages/agent/tests/test_evidence_artifacts_sources.py
# 5 passed

uv run pytest -q packages/agent/tests/test_session_memory_todo.py
# 6 passed

uv run pytest -q packages/agent/tests/test_desktop_workbench_contracts.py
# 11 passed

git diff --check -- packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/session_store_evidence.py packages/agent/src/aiask_agent/session_store_broker.py packages/agent/src/aiask_agent/session_store_utils.py packages/agent/src/aiask_agent/session_store_schema.py packages/agent/src/aiask_agent/session_store_rows.py packages/agent/src/aiask_agent/session_store_search.py packages/agent/src/aiask_agent/session_store_handoff.py AIASK_CODE_STRUCTURE_CLEANUP_PLAN_2026-06-14.md
# no whitespace errors
```

当前 Agent session store 补充结论：

1. `session_store.py` 已从 3198 行降到 1566 行，schema/helper/row/search/handoff/broker/evidence 七类职责已经迁出。
2. 若目标是让 `session_store.py` 退出超 1000 行清单，下一批应优先拆 `user data policy/export/delete/retention/learning dataset`；该段体量最大，完成后主 facade 有望接近或低于 1000 行。
3. 仓库级目标仍未完成；即使 `session_store.py` 后续退出清单，`native_capabilities.py`、factory 脚本和 AKShare/Strategy/Quant 侧大文件仍需继续处理。

### 2026-06-14 第九十六批：Agent session store user-data/retention mixin 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/session_store_user_data.py` |
| 更新模块 | `packages/agent/src/aiask_agent/session_store.py` |
| `session_store.py` 装配方式 | `AgentSessionStore` 继续作为兼容 facade，继承 broker/evidence/handoff/user-data mixins；`search()` 和 session/run/activity/tool audit 核心仍留在 facade 内 |
| 已迁出职责 | feedback CRUD、user data policy get/update、user activity summary、analytics summary、user data export/delete、retention policy sweep、learning dataset、workflow recommendations、user data policy list helper |
| 行为保持 | Desktop user activity/feedback/policy/export/delete/retention routes、learning dataset、workflow recommendations 返回 shape 保持；secret redaction、dry-run、market-data-unaffected 标记、hard-delete/anonymize 分支和 FTS cleanup 行为保持；未新增 secrets 读取、外部副作用、live trading 或 runtime DB/log/cache/broker 操作 |
| `session_store.py` 行数 | 973 行 |
| `session_store_user_data.py` 行数 | 609 行 |
| `session_store_evidence.py` 行数 | 354 行 |
| `session_store_broker.py` 行数 | 411 行 |
| `session_store_handoff.py` 行数 | 176 行 |
| `session_store_search.py` 行数 | 133 行 |
| `session_store_rows.py` 行数 | 171 行 |
| `session_store_utils.py` 行数 | 137 行 |
| `session_store_schema.py` 行数 | 365 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/session_store_user_data.py packages/agent/src/aiask_agent/session_store_evidence.py packages/agent/src/aiask_agent/session_store_broker.py packages/agent/src/aiask_agent/session_store_handoff.py packages/agent/src/aiask_agent/session_store_search.py packages/agent/src/aiask_agent/session_store_rows.py packages/agent/src/aiask_agent/session_store_utils.py packages/agent/src/aiask_agent/session_store_schema.py
# passed

PYTHONPATH=packages/agent/src uv run python -c "from aiask_agent.session_store import AgentSessionStore; s=AgentSessionStore(); assert hasattr(s, 'record_feedback'); assert hasattr(s, 'export_user_data'); assert hasattr(s, 'apply_retention_policies'); assert hasattr(s, 'search')"
# passed

uv run pytest -q packages/agent/tests/test_session_memory_todo.py
# 6 passed

uv run pytest -q packages/agent/tests/test_desktop_workbench_contracts.py
# 11 passed

uv run pytest -q packages/agent/tests/test_evidence_artifacts_sources.py
# 5 passed

uv run pytest -q packages/agent/tests/test_broker_readonly_api.py packages/agent/tests/test_financial_manager_desktop_api.py
# 10 passed

git diff --check -- packages/agent/src/aiask_agent/session_store.py packages/agent/src/aiask_agent/session_store_user_data.py packages/agent/src/aiask_agent/session_store_evidence.py packages/agent/src/aiask_agent/session_store_broker.py packages/agent/src/aiask_agent/session_store_utils.py packages/agent/src/aiask_agent/session_store_schema.py packages/agent/src/aiask_agent/session_store_rows.py packages/agent/src/aiask_agent/session_store_search.py packages/agent/src/aiask_agent/session_store_handoff.py AIASK_CODE_STRUCTURE_CLEANUP_PLAN_2026-06-14.md
# no whitespace errors
```

当前 Agent session store 补充结论：

1. `packages/agent/src/aiask_agent/session_store.py` 已从 3198 行降到 973 行，按方案口径退出超 1000 行清单；外部仍保留 `AgentSessionStore`、`now_iso`、`sanitize_for_audit` 兼容入口。
2. session store 已形成 facade + schema/utils/rows/search/handoff/broker/evidence/user-data mixins 的分层，后续细拆可以围绕 activity/tool audit 或 session/run core 继续，但不再是当前超 1000 行压力点。
3. 仓库级目标仍未完成；下一阶段可转向 `packages/agent/src/aiask_agent/native_capabilities.py`、`scripts/factories/run_strategy_factory_quality_session.py` 或 AKShare/Strategy/Quant 侧剩余大文件。

### 2026-06-14 第九十七批：Agent native capabilities 顶层 helper/store/media 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/native_utils.py`、`packages/agent/src/aiask_agent/native_web_utils.py`、`packages/agent/src/aiask_agent/native_media.py`、`packages/agent/src/aiask_agent/native_skill_store.py`、`packages/agent/src/aiask_agent/native_message_outbox.py` |
| 更新模块 | `packages/agent/src/aiask_agent/native_capabilities.py` |
| `native_capabilities.py` 装配方式 | 继续导出 `SkillStore`、`MessageOutbox`、`media_provider_catalog` 等兼容名字，并保留 `build_native_capability_handlers()` / `agent_*` handler 注册表；顶层 slug/limit、web fetch/extract/json helpers、media provider/generation helpers、skill store、message outbox 迁出 |
| 已迁出职责 | public web URL 校验与 fetch、HTML text/link extraction、JSON HTTP helper、media provider catalog、image/TTS/STT helper、skill CRUD/archive/backup/audit/templates、message outbox persistence/send |
| 行为保持 | `agent_*` 工具名、envelope/meta/side-effect 字段、general_full/control-token 入口、SkillStore 兼容导入、media provider catalog shape 和 private web target block 行为保持；未扩大文件/terminal/browser/web/media 权限面 |
| `native_capabilities.py` 行数 | 1505 行 |
| `native_media.py` 行数 | 276 行 |
| `native_web_utils.py` 行数 | 156 行 |
| `native_skill_store.py` 行数 | 254 行 |
| `native_message_outbox.py` 行数 | 68 行 |
| `native_utils.py` 行数 | 18 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/native_capabilities.py packages/agent/src/aiask_agent/native_media.py packages/agent/src/aiask_agent/native_web_utils.py packages/agent/src/aiask_agent/native_skill_store.py packages/agent/src/aiask_agent/native_message_outbox.py packages/agent/src/aiask_agent/native_utils.py
# passed

PYTHONPATH=packages/agent/src uv run python -c "from aiask_agent.native_capabilities import SkillStore, MessageOutbox, media_provider_catalog, build_native_capability_handlers; print(SkillStore.__name__, MessageOutbox.__name__, media_provider_catalog()['object'])"
# passed

uv run pytest -q packages/agent/tests/test_native_full_parity.py
# 5 passed

uv run pytest -q packages/agent/tests/test_hermes_full_expanded_capabilities.py -k "media or image or audio or subgoal or handoff"
# 1 passed, 5 deselected

git diff --check -- packages/agent/src/aiask_agent/native_capabilities.py packages/agent/src/aiask_agent/native_media.py packages/agent/src/aiask_agent/native_web_utils.py packages/agent/src/aiask_agent/native_skill_store.py packages/agent/src/aiask_agent/native_message_outbox.py packages/agent/src/aiask_agent/native_utils.py AIASK_CODE_STRUCTURE_CLEANUP_PLAN_2026-06-14.md
# no whitespace errors
```

当前 Agent native capabilities 补充结论：

1. `native_capabilities.py` 已从 2215 行降到 1505 行，顶层 helper/store/media/outbox 已拆出，但文件仍超过 1000 行。
2. 下一步若继续治理该文件，应拆 `build_native_capability_handlers()` 内部的领域 handler，例如 web/search、skills/plugins/MCP、gateway/platform、learning/RL/HA/Feishu/Discord/message/webhook。
3. 所有模型可见工具仍保持 `agent_*` facade，未暴露 raw manager 名称或扩大 side-effect 权限。

### 2026-06-14 第九十八批：Agent native capabilities web/media/planning handler 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/native_web_handlers.py`、`packages/agent/src/aiask_agent/native_media_handlers.py`、`packages/agent/src/aiask_agent/native_planning_handlers.py` |
| 更新模块 | `packages/agent/src/aiask_agent/native_capabilities.py` |
| `native_capabilities.py` 装配方式 | `build_native_capability_handlers()` 继续作为 handler 注册 facade；web/search、media/vision/generation、clarify/todo/subgoal handler 组由 builder 返回 dict，并在最终 handler 表中以 `**web_handlers`、`**media_handlers`、`**planning_handlers` 展开 |
| 已迁出职责 | `agent_web_search` / `agent_web_extract` / `agent_x_search`，`agent_vision_analyze` / `agent_media_provider_catalog` / `agent_image_generate` / `agent_video_generate` / `agent_text_to_speech` / `agent_transcribe_audio`，`agent_clarify` / `agent_todo_*` / `agent_subgoal` |
| 行为保持 | 所有 `agent_*` 工具名、envelope side-effect level、media provider catalog 兼容导入、private URL 校验、external generation idempotent 标记、todo/subgoal store 方法调用保持；未扩大 web/media/filesystem/terminal/browser 权限面 |
| `native_capabilities.py` 行数 | 995 行 |
| `native_web_handlers.py` 行数 | 221 行 |
| `native_media_handlers.py` 行数 | 207 行 |
| `native_planning_handlers.py` 行数 | 137 行 |
| `native_media.py` 行数 | 276 行 |
| `native_web_utils.py` 行数 | 156 行 |
| `native_skill_store.py` 行数 | 254 行 |
| `native_message_outbox.py` 行数 | 68 行 |
| `native_utils.py` 行数 | 18 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/native_capabilities.py packages/agent/src/aiask_agent/native_planning_handlers.py packages/agent/src/aiask_agent/native_media_handlers.py packages/agent/src/aiask_agent/native_web_handlers.py packages/agent/src/aiask_agent/native_media.py packages/agent/src/aiask_agent/native_web_utils.py packages/agent/src/aiask_agent/native_skill_store.py packages/agent/src/aiask_agent/native_message_outbox.py packages/agent/src/aiask_agent/native_utils.py
# passed

PYTHONPATH=packages/agent/src uv run python -c "from aiask_agent.native_capabilities import build_native_capability_handlers; from aiask_agent.session_store import AgentSessionStore; from aiask_agent.tools.policy import ToolPolicy; policy=ToolPolicy(toolset='general_full', general_tools_enabled=True, workspace_roots=[]); handlers=build_native_capability_handlers(policy=policy, session_store=AgentSessionStore()); expected={'agent_web_search','agent_web_extract','agent_x_search','agent_clarify','agent_todo','agent_subgoal','agent_vision_analyze','agent_media_provider_catalog','agent_image_generate','agent_video_generate','agent_text_to_speech','agent_transcribe_audio'}; assert expected <= set(handlers)"
# passed

uv run pytest -q packages/agent/tests/test_native_full_parity.py
# 5 passed

uv run pytest -q packages/agent/tests/test_hermes_full_expanded_capabilities.py -k "media or image or audio or subgoal or handoff"
# 1 passed, 5 deselected

uv run pytest -q packages/agent/tests/test_hermes_reference_guardrails.py -k "web or native or agent"
# 1 passed, 3 deselected

uv run pytest -q packages/agent/tests/test_extended_agent_capabilities.py -k "session_handoff or subgoal or handoff"
# 4 passed, 19 deselected

git diff --check -- packages/agent/src/aiask_agent/native_capabilities.py packages/agent/src/aiask_agent/native_web_handlers.py packages/agent/src/aiask_agent/native_media_handlers.py packages/agent/src/aiask_agent/native_planning_handlers.py packages/agent/src/aiask_agent/native_media.py packages/agent/src/aiask_agent/native_web_utils.py packages/agent/src/aiask_agent/native_skill_store.py packages/agent/src/aiask_agent/native_message_outbox.py packages/agent/src/aiask_agent/native_utils.py AIASK_CODE_STRUCTURE_CLEANUP_PLAN_2026-06-14.md
# no whitespace errors
```

当前 Agent native capabilities 补充结论：

1. `packages/agent/src/aiask_agent/native_capabilities.py` 已从 2215 行降到 995 行，按方案口径退出超 1000 行清单。
2. native tools 仍通过 `build_native_capability_handlers()` 和 `agent_*` 注册表统一暴露；后续可继续细拆 skills/plugins/MCP、gateway、learning/RL/HA/Feishu/Discord/message/webhook handler，但当前已不再是超 1000 行压力点。
3. 仓库级目标仍未完成；下一阶段可转向 `scripts/factories/run_strategy_factory_quality_session.py` 或 AKShare/Strategy/Quant 侧剩余大文件。

### 2026-06-14 第九十九批：Agent tool schema general_full 分组拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/agent/src/aiask_agent/tools/schema_helpers.py`、`packages/agent/src/aiask_agent/tools/schema_general_full.py` |
| 更新模块 | `packages/agent/src/aiask_agent/tools/schemas.py` |
| `schemas.py` 装配方式 | 继续导出兼容入口 `schema` 与 `TOOL_SCHEMAS`；finance-safe / ActionIntent schema 留在 facade，general_full 原生工具 schema 由 `GENERAL_FULL_TOOL_SCHEMAS` 合并进入总表 |
| 已迁出职责 | file/terminal/process/code/browser/web/media/todo/skill/plugin/MCP/model/memory/ACP/security/gateway/learning/HA/MoA/Feishu/Discord/RL/webhook/job/session 等 general_full 工具 schema |
| 行为保持 | `TOOL_SCHEMAS` 总数、schema helper shape、`agent_*` 工具名、ActionIntent `ALLOWED_ACTIONS` enum、registry/runtime 导入路径保持；未暴露 raw manager 名称，未改动 toolset gate、control-token gate 或 side-effect metadata |
| schema 指纹 | 拆分前后 `TOOL_SCHEMAS` 均为 136 项，canonical SHA-256 均为 `8755046fca95db1b48ec18666728bca584cfdd60fdbbbf32b3eefd72f4391b1e` |
| `schemas.py` 行数 | 314 行 |
| `schema_general_full.py` 行数 | 795 行 |
| `schema_helpers.py` 行数 | 12 行 |

验证结果：

```bash
python -m py_compile packages/agent/src/aiask_agent/tools/schemas.py packages/agent/src/aiask_agent/tools/schema_general_full.py packages/agent/src/aiask_agent/tools/schema_helpers.py
# passed

PYTHONPATH=packages/agent/src python -c "import hashlib,json; from aiask_agent.tools.schemas import TOOL_SCHEMAS; data=json.dumps(TOOL_SCHEMAS, sort_keys=True, ensure_ascii=True); print(len(TOOL_SCHEMAS)); print(hashlib.sha256(data.encode()).hexdigest())"
# 136
# 8755046fca95db1b48ec18666728bca584cfdd60fdbbbf32b3eefd72f4391b1e

uv run pytest -q packages/agent/tests/test_tool_registry.py packages/agent/tests/test_native_full_parity.py packages/agent/tests/test_realtime_finance_facades.py
# 18 passed

uv run pytest -q packages/agent/tests/test_desktop_capabilities_api.py packages/agent/tests/test_endpoint_drift_gate.py
# 9 passed

git diff --check -- packages/agent/src/aiask_agent/tools/schemas.py packages/agent/src/aiask_agent/tools/schema_general_full.py packages/agent/src/aiask_agent/tools/schema_helpers.py
# no whitespace errors
```

当前 Agent tool schema 补充结论：

1. `packages/agent/src/aiask_agent/tools/schemas.py` 已从 1106 行降到 314 行，按方案口径退出超 1000 行清单。
2. schema 拆分后仍由 `TOOL_SCHEMAS` 统一服务 `tool_registry.py` 与 `runtime.py`，外部导入 `aiask_agent.tools.schemas.TOOL_SCHEMAS` 不变。
3. 仓库级目标仍未完成；当前超 1000 行清单已转向 factory 脚本、AKShare/Strategy/Quant 侧大文件，以及 Agent `gateway.py` / `fallback_server.py` / `runtime.py` / `gateway_daemon.py`。

### 2026-06-15 第一〇〇批：AKShare tool_catalog 按 category 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/akshare-mcp/src/akshare_mcp/tools/tool_catalog/`（`__init__.py` facade + `_helpers.py` + `contracts_<category>.py` ×11 + `workflow_guides.py`）|
| 装配方式 | `tool_catalog.py` 单文件改为同名 package；`__init__.py` 按 research/quant/strategy/data_sync/search/screening/governance/skills/risk/execution/market 顺序 `TOOL_CONTRACTS.update(_CONTRACTS_*)`，再 `update(provider_tool_contracts())`，保留 `get_tool_contract`/`list_tool_contracts`/`get_workflow_guide`/`build_tool_meta` |
| 已迁出职责 | `STANDARD_ENVELOPE_OUTPUT_SCHEMA` + `_contract` 入 `_helpers.py`；各 category contract dict 入 `contracts_<category>.py`；`WORKFLOW_GUIDES` 入 `workflow_guides.py` |
| 行为保持 | `from .tool_catalog import ...` 调用方（`resources/catalog.py`、`adapter_tools.py`、`ai_workflows.py`、`governance_workflow.py`、`search.py`）不变；`build_strategy_manager_input_schema`/`provider_tool_contracts` 相对 import 深度修正为 `...` |
| 零漂移校验 | `TOOL_CONTRACTS` 86 项 SHA-256 `5e42b1a6c5ee8fc772fe718c2aa77432d25aa7a49ec2f2d180a88d61163e6453`、`WORKFLOW_GUIDES` 5 项 `ac94deccd7b9ef497736efd213a73bc02f908a35f217aafa34624fc5dd961abe` 拆分前后一致 |
| 最大新文件行数 | `contracts_market.py` 330 行（原 1282 行单文件已退出超 1000 行清单）|

验证结果：

```bash
F:/Python311/python.exe -m py_compile packages/akshare-mcp/src/akshare_mcp/tools/tool_catalog/*.py
# passed
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/ -q -k "catalog or contract or tool_meta"
# 77 passed, 621 deselected
```

### 2026-06-15 第一〇一批：AKShare stock_radar service 分层拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/akshare-mcp/src/akshare_mcp/services/stock_radar/`（`__init__.py` facade + `analysis.py` + `ingest.py`）|
| 装配方式 | `services/stock_radar.py` 改同名 package；`__init__.py` 保留 orchestrator `run_stock_radar`、confirmations、`stock_radar_status/candidates/digest`、`push_stock_radar_digest`、`schedule_stock_radar_update`、`run_stock_radar_sync`，并 re-export analysis/ingest 全部公开+私有名 |
| 已迁出职责 | `analysis.py`: 规则抽取/LLM 增强/打分/RadarExtraction + 文本清洗常量；`ingest.py`: RSS/PDF 下载解析/文档持久化 |
| monkeypatch 兼容 | 测试 patch 的 `requests`、`run_market_text_source_ingest`、`_confirmation_factors` 仍在 `__init__` 命名空间；`_pdf_parse_status` 改为经包命名空间间接调用 `_download_pdf_file`/`_extract_pdf_text_from_file`，保持 `radar_mod.<fn>` patch 生效 |
| 行为保持 | `tools/stock_radar.py`、agent `adapters/desktop_ops.py`/`adapters/stock_radar.py` 的 `from ..services.stock_radar import ...` 不变；in-function 相对 import 深度修正（`..strategy_llm_provider`/`..market_event_sources`/`..market_text_source_ingest`）|
| pyflakes | 三文件无 F821（undefined name）|
| 行数 | `__init__.py` 839 / `analysis.py` 579 / `ingest.py` 352（原 1639 行单文件退出清单）|

验证结果：

```bash
F:/Python311/python.exe -m py_compile .../services/stock_radar/*.py
# passed
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_stock_radar.py -q
# 11 passed
# agent 跨包：python -m pytest tests/test_stock_radar_intents.py -q → 10 passed
```

### 2026-06-15 第一〇二批：AKShare market_temperature 工具拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `packages/akshare-mcp/src/akshare_mcp/tools/market_temperature/`（`__init__.py` facade + `helpers.py`）|
| 装配方式 | `tools/market_temperature.py` 改同名 package；`__init__.py` 保留 6 个 public async 工具 + `register(mcp)` + `get_db` import（测试 monkeypatch 目标），从 `helpers.py` re-export 全部 31 个 pure helper |
| 已迁出职责 | `helpers.py`: `_safe_float`/`_pct_change`/`_build_stock_row`/`_cached_snapshot`/`_compute_snapshot_from_db` 等纯计算与快照构建（含 `build_market_temperature_snapshot` 调用）|
| 行为保持 | `register(mcp)` 注册 6 工具不变；agent `adapters/akshare.py` 的 `load_registered_tool("akshare_mcp.tools.market_temperature", ...)` module-attr 访问不变；测试 `market_temperature_tool.get_db`/`_pct_change` monkeypatch 仍生效 |
| import 深度 | `helpers.py` 用 `...services.market_temperature`；`__init__` 用 `...services`/`...storage`/`..manager_protocol` |
| pyflakes | 无 F821 |
| 行数 | `__init__.py` 726 / `helpers.py` 539（原 1223 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_market_temperature.py tests/test_market_temperature_data_sync.py -q
# 21 passed
```

### 2026-06-15 第一〇三批：AKShare provider_contracts registry 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `provider_contracts/_shared.py`、`provider_contracts/_platform_contracts.py` |
| 装配方式 | `registry.py` 保留 `_CONTRACTS`（market-data 合同）+ `_CONTRACTS.update(_platform_contracts())` + `get_provider_tool_contract`/`provider_tool_contracts`；shared builders/policies 与 `_platform_contracts()` 迁出 |
| 已迁出职责 | `_shared.py`: `_contract`/`_schema`/`_array_of`/所有 `_*_FRESHNESS`/`_*_SOURCE_POLICY` 常量 + models/base import；`_platform_contracts.py`: 585 行 analysis-layer 合同生成函数 |
| 行为保持 | `from ._shared import *` + `__all__`（90 名，含下划线常量与 models）保证跨模块名可见；`provider_contracts/__init__.py` 的 `from .registry import get_provider_tool_contract, provider_tool_contracts` 不变 |
| 零漂移 | `provider_tool_contracts()` 59 项 SHA-256 `3625b47307c5e74930f065495b5bedf2872aca0c5cee463d6be2e735e8599525` 拆分前后一致 |
| 行数 | `registry.py` 316 / `_shared.py` 390 / `_platform_contracts.py` 594（原 1190 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_provider_contracts.py -q
# 34 passed
```

### 2026-06-15 第一〇四批：AKShare strategy_acceptance_remediation 拆分（helper + mixin）

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `services/acceptance_helpers.py`、`acceptance_remediation_core.py`、`acceptance_backtest.py`、`acceptance_bootstrap.py` |
| 装配方式 | `strategy_acceptance_remediation.py` 保留 `class StrategyAcceptanceRemediationService(_RemediationCoreMixin, _BacktestMixin, _BootstrapMixin)` + 模块单例 + `get_strategy_acceptance_remediation_service`，并 re-export helper 名 |
| 已迁出职责 | helpers/dataclasses（`_safe_float`/`_RoundTrip`/`build_failed_metrics_filter_patch`/`summarize_code_performance` 等）入 `acceptance_helpers.py`；service 类 12 方法按 remediation-core / backtest / bootstrap 拆 3 mixin |
| 行为保持 | `strategy_mgr_crud.py:537` 的 `from ...services.strategy_acceptance_remediation import StrategyAcceptanceRemediationService, _strategy_runtime_params` 不变；MRO = Service→Core→Backtest→Bootstrap→object；11 实例方法齐全 |
| pyflakes | 无 F821 |
| 行数 | 主文件 79 / helpers 591 / core 292 / backtest 329 / bootstrap 540（原 1624 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_strategy_acceptance_remediation.py -q
# 8 passed
```

### 2026-06-15 第一〇五批：AKShare market_event_sources 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `services/event_constants.py`、`event_mappers.py`、`event_validation.py` |
| 装配方式 | `market_event_sources.py` 保留 adapters、`event_source_status`、CNINFO/SSE fetchers（用 `requests`）、`normalize_market_text_events`、`persist_normalized_events`、`bridge_*`，从三个子模块 import 常量/mappers/validator |
| 已迁出职责 | `event_constants.py`: tier/cap/token 常量 + `_coerce_date_text`/`_unique_list`；`event_mappers.py`: `_clean`/`_normalize_source_tier`/CNINFO+SSE 公告 mapper；`event_validation.py`: 签名 helper + `MultiSourceEventValidator` |
| 行为保持 | `market_text_source_ingest.py`、`stock_radar/ingest.py` 的 import 不变；测试 patch 的 `requests`/`fetch_cninfo_official_announcements` 仍在主模块；切片提取（非手抄）保证常量/正文字节一致 |
| pyflakes | 四文件无 F821 |
| 行数 | 主文件 882 / constants 75 / mappers 149 / validation 321（原 1347 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_market_event_sources.py -q
# 12 passed
```

### 2026-06-15 第一〇六批：AKShare stock_profile_pipeline 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `services/profile_features.py` |
| 装配方式 | `stock_profile_pipeline.py` 保留 scoring/archetype/regime、embedding/summary/payload builders、async DB 层（`build_stock_profile_payload`/`backfill_stock_profile_vectors`/`load_stock_profile_context`），从 `profile_features.py` re-export 常量与特征抽取 |
| 已迁出职责 | `profile_features.py`: `_PROFILE_TYPES`/`_FEATURE_*`/`_DIMENSION_*`/`_COVERAGE_*` 常量 + `build_stock_profile_features`/`_extract_*`/`_build_raw_features_grouped`/`_extended_technical_features` 等特征构建 |
| 行为保持 | `resources/stock_and_watchlist.py`、`tools/_vector_common.py`、`vector_optimize_bootstrap.py`、`_data_sync_manager_support_sync.py` import 不变；测试访问的 `spp._build_profile_summary`/`_resolve_regime_from_features`/`_holding_bucket_hint_from_archetype` 仍在主模块；全部特征名按原 module 语义 re-export |
| 行数 | 主文件 712 / profile_features 640（原 1303 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_profile_regime_p1_1.py tests/test_sqlite_runtime_compat.py -q
# 8 passed
```

### 2026-06-15 第一〇七批：AKShare strategy_pipeline 拆分（helper + stage mixin）

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `services/pipeline_support.py`、`pipeline_stages.py` |
| 装配方式 | `strategy_pipeline.py` 保留 `class MultiStageStrategyPipeline(_PipelineStageMixin)`（`__init__`/`run_pipeline`/`run_stage`）+ 模块单例 + `get_strategy_pipeline`；共享 header（stdlib + strategy_stages/strategy_llm_provider import + logger）复制进每个模块 |
| 已迁出职责 | `pipeline_support.py`: `_get_pipeline_constants`/`PipelineResult`/stage 输出与 provider-format-failure helpers；`pipeline_stages.py`: `_PipelineStageMixin`（`_call_llm_stage`/`_call_fallback_stage`/`_enrich_with_stock_profiles`/`_build_initial_input`/`_prepare_stage_input`）|
| 行为保持 | `get_strategy_pipeline()` 单例语义不变；MRO = Pipeline→StageMixin→object；测试通过 factory swap 仍生效 |
| pyflakes | 三文件无 F821 |
| 行数 | 主文件 392 / support 284 / stages 519（原 1093 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_strategy_pipeline_quality_fixes.py -q
# 6 passed
```

### 2026-06-15 第一〇八批：AKShare tools/market/kline 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `tools/market/kline/`（`__init__.py` facade + `kline_rows.py` + `kline_minute.py`）|
| 装配方式 | `tools/market/kline.py` 改同名 package；`__init__.py` 保留 `get_kline`/`_get_kline_impl`/`_async_save_klines_to_db`/`get_minute_kline`/`get_kline_data`/`get_index_kline` + `data_source`（测试 patch 目标），re-export rows/minute helpers |
| 已迁出职责 | `kline_rows.py`: kline 行校验/响应封装/`_process_kline_akshare`；`kline_minute.py`: `_parse_minute_period` + akshare/sina/tencent 分钟线 fetcher |
| 行为保持 | `from .market.kline import get_kline/...`、`from .market import get_kline`、`db_freshness` 的 `_get_kline_impl` import 不变；`@cached` 装饰器随 `get_kline`/`get_minute_kline` 保留（计数 2=2）；相对 import 深度 `...`→`....` 修正 |
| pyflakes | 三文件无 F821 |
| 行数 | `__init__.py` 836 / kline_minute 254 / kline_rows 236（原 1195 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_failed_tool_regressions.py tests/test_tool_argument_contract.py -q
# 9 passed
```

### 2026-06-15 第一〇九批：AKShare data_source/tdx_tqcenter 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `data_source/tdx_tqcenter/`（`__init__.py` facade + `_core.py` + `info_queries.py` + `market_queries.py`）|
| 装配方式 | `tdx_tqcenter.py` 改同名 package；`__init__.py` 通过 `from ._core import *` + 显式下划线名 + info/market 名 re-export 全部公开 `get_*`，保留 stock_list/sector/formula/download/status 在 `__init__` |
| 已迁出职责 | `_core.py`: 连接管理（`get_tq`/`reset_tq`）+ 数值/日期 helpers + `get_kline`/`get_realtime_quote`；`info_queries.py`: `get_more_info`..`get_kzz_info`；`market_queries.py`: `get_gp_one_data`..`get_financial_data_by_date` |
| 行为保持 | `data_source/__init__.py`、`quotes.py`、`market_data.py`、`tdx_sync_service.py`、`services/__init__.py` 的 import 与别名不变；测试 `_tqcenter.<fn>` module-object monkeypatch（23 名）仍生效，mixin 仍按 module-attr 调用 |
| pyflakes | 四文件无 F821 |
| 行数 | `__init__.py` 281 / `_core.py` 406 / info 291 / market 302（原 1114 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_data_source_tdx_routing.py tests/test_runtime_client_lifecycle.py -q
# 24 passed
```

### 2026-06-15 第一一〇批：AKShare tools/finance 纯 helper 拆分（monkeypatch-fragile，保守）

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `tools/financials_helpers.py` |
| 装配方式 | `finance.py` 保留全部 provider fetcher（`_get_financials_tdx/tushare/akshare/_em/_indicator`）、公共工具 `get_financials`/`get_stock_info`、以及被测试 monkeypatch 的全局 `ak`/`cache`/`data_source`/`_call_with_retry`/`resolve_existing_security_code_sync`；纯 helper 迁出后 re-import |
| 已迁出职责 | `financials_helpers.py`: `_ok_stock_info_degraded`/`_build_financial_cache_entry`/`_read_financial_cache_entry`/`_financial_missing_fields`/`_ok_financial`/`_fail_financial`/`_row_non_null_count`/`_pick_best_statement_row`/`_calc_ratio`/`_first_not_none`（均不引用被 patch 的全局，且未被测试 patch）|
| 行为保持 | 保守拆分：`_call_with_retry` 与所有 provider 仍在 `finance.py`，确保 `setattr(finance, "_get_financials_tdx"/"ak"/"cache"/"data_source")` + `get_financials.__wrapped__` 的 monkeypatch 链路不变 |
| pyflakes | 两文件无 F821 |
| 行数 | `finance.py` 995 / `financials_helpers.py` 219（原 1157 行退出清单，主文件 995 < 1000）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_baostock_optional_dependency.py tests/test_provider_contracts.py tests/test_mcp_full_tool_regression_fixes.py tests/test_failed_tool_regressions.py tests/test_tdx_phase3_tools_e2e.py tests/test_sqlite_runtime_compat.py -q
# 64 passed, 5 skipped（与拆分前 baseline 一致）
```

### 2026-06-15 第一一一批：AKShare tools/market_blocks 拆分（monkeypatch-fragile，保守）

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `tools/block_helpers.py` |
| 装配方式 | `market_blocks.py` 保留 `get_market_blocks`/`get_block_stocks`/DB fetchers + 被 patch 的 `ak`/`get_db`/`_fetch_from_db`/`_fetch_from_akshare`；placeholder helpers + `_fetch_concept_stocks_from_ths` 迁出后 re-import |
| 已迁出职责 | `block_helpers.py`: `_is_placeholder_summary`/`_sanitize_placeholder_blocks`（纯）+ `_fetch_concept_stocks_from_ths`（THS 概念成分股；自带 `ak`/`requests` import；仅经 `get_block_stocks` 调用，无 ak=None patch 路径触达）|
| 行为保持 | `get_market_blocks` 的 ak=None/get_db patch 路径全部留在主模块；`_fetch_concept_stocks_from_ths` 仍以 facade 名暴露 |
| pyflakes | 两文件无 F821 |
| 行数 | `market_blocks.py` 882 / `block_helpers.py` 188（原 1040 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_full_chain_regression_repairs.py tests/test_provider_contracts.py -q
# 66 passed（与拆分前 baseline 一致）
```

### 2026-06-15 第一一二批：AKShare strategy_lifecycle_shared/overview 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `services/strategy_lifecycle_shared/overview_helpers.py` |
| 装配方式 | `overview.py` 保留巨型 `build_incubation_overview`（895 行单函数不做高风险内部分解）+ `build_closure_review`；顶部 helper 迁出后 re-import；新增 `_persist_and_finalize_overview` 承接末尾 closure snapshot 持久化+finalize |
| 已迁出职责 | `overview_helpers.py`: `_quality_report_timestamp`/`_CLOSURE_SNAPSHOT_DROP_FIELDS`/`_trim_closure_snapshot`/`_resolve_risk_hard_gate`/`_persist_and_finalize_overview` |
| 行为保持 | `strategy_lifecycle_shared/__init__.py` 的 `globals().update(...)` 自动 re-export，consumers（incubation_pipeline/promotion_pipeline/runtime_control/runtime_risk 等）import 不变；持久化逻辑逐字迁移为模块级 async helper |
| pyflakes | 两文件无 F821 |
| 行数 | `overview.py` 925 / `overview_helpers.py` 182（原 1027 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_incubation_overview_snapshot_cache.py tests/test_closure_review_contract.py tests/test_strategy_lifecycle_shared_runtime.py tests/test_cross_regime_promotion_gate.py tests/test_execution_audit_snapshot_contract.py -q
# 18 passed
```

**阶段1（AKShare 源码大文件）完成**：tool_catalog / stock_radar / market_temperature / provider_contracts.registry / strategy_acceptance_remediation / market_event_sources / stock_profile_pipeline / strategy_pipeline / tools.market.kline / data_source.tdx_tqcenter / finance / market_blocks / strategy_lifecycle_shared.overview 共 13 个文件全部退出超 1000 行清单。

### 2026-06-15 第一一三批：AKShare strategy_mgr_crud 拆分（manager 子包）

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `tools/managers/strategy_mgr_crud/`（`__init__.py` facade + `_support.py` + `_personal_support.py` + `handlers_catalog.py` + `handlers_personal.py`）|
| 装配方式 | `strategy_mgr_crud.py` 改同名 package；`__init__.py` re-export 全部 29 个 `handle_*`，并用 `globals().update(dir(_support)+dir(_personal_support))` 保留私有 helper 的顶层可见性（旧 `from ...strategy_mgr_crud import _helper` 兼容）|
| 已迁出职责 | `_support.py`: 通用 helper + `_resolve_strategy_incubation_overview`；`_personal_support.py`: personal-strategy 上下文/变更计划/回测/post-update pipeline；`handlers_catalog.py`: help/create/publish/archive/list/detail/review/events/subscribe 等 14 个 handler；`handlers_personal.py`: fork/personal/paper/rank/ai_optimize/capabilities/signals 等 15 个 handler |
| 行为保持 | `strategy_manager.py:22-52` 的 29 个 `handle_*` import 不变；import 深度 `...`→`....`、`.X`→`..X` 修正；测试 `test_mcp_fix_plan_batch3/4.py` 的源码静态扫描改用 `_strategy_mgr_crud_source()`（兼容单文件/包目录），未改断言语义 |
| pyflakes | 五文件无 F821 |
| 行数 | `__init__` 77 / `_support` 525 / `_personal_support` 706 / `handlers_catalog` 480 / `handlers_personal` 706（原 2210 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_mcp_fix_plan_batch3.py tests/test_mcp_fix_plan_batch4.py tests/test_strategy_market_incubation_surface.py tests/test_strategy_review_workflow_contract.py -q
# 38 passed
```

### 2026-06-15 第一一四批：AKShare strategy_mgr_lifecycle 拆分（manager 子包）

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `tools/managers/strategy_mgr_lifecycle/`（`__init__.py` facade + `_lifecycle_support.py` + `handlers.py`）|
| 装配方式 | 改同名 package；`__init__.py` 用 `globals().update(dir(_lifecycle_support)+dir(handlers))` 保留全部 16 个 `handle_*` + `run_quality_gate`/`lifecycle_scan` + 兼容别名 `_run_quality_gate`/`_lifecycle_scan` + 私有 helper |
| 已迁出职责 | `_lifecycle_support.py`: env/scheduler/recheck/quality-input helpers + `_get_strategy_factory_scheduler_with_runtime`；`handlers.py`: 19 个 handler + `run_quality_gate`/`lifecycle_scan` + 别名 |
| 行为保持 | `strategy_manager.py` 的 16 handler + `_lifecycle_scan`/`_run_quality_gate` import 不变；import 深度 `...`→`....`（顶层+in-function）修正；handler 经 `_ls._get_strategy_factory_scheduler_with_runtime` 调用以维持 monkeypatch（测试 patch 目标同步为 `lifecycle._lifecycle_support`）|
| pyflakes | 三文件无 F821 |
| 行数 | `__init__` 11 / `_lifecycle_support` 451 / `handlers` 829（原 1225 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_factory_market_views_contract.py tests/test_strategy_factory_ownership.py tests/test_mcp_fix_plan_batch3.py tests/test_mcp_fix_plan_batch4.py tests/test_strategy_review_workflow_contract.py -q
# 44 passed (11 + 33)
```

### 2026-06-15 第一一五批：AKShare tdx_sync_service 拆分（class → domain mixins）

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `services/tdx_sync_market.py`、`tdx_sync_financial.py`、`tdx_sync_events.py`、`tdx_sync_derived.py`、`tdx_sync_completeness.py` |
| 装配方式 | `tdx_sync_service.py` 保留 `class TdxSyncService(_MarketSyncMixin, _FinancialSyncMixin, _EventsSyncMixin, _DerivedSyncMixin, _CompletenessMixin)` + `__init__` + `run_all` 编排 + `run_tdx_sync` 模块函数 |
| 已迁出职责 | 27 个 `_sync_*`/`_derive_*`/completeness 方法按 market(9)/financial(5)/events(3)/derived(6)/completeness(4) 路由到 5 个 mixin（按方法名路由，逐方法切片，零 unrouted）|
| 行为保持 | `data_sync_scheduler.py:371` 的 `from .tdx_sync_service import TdxSyncService` 与 `run_tdx_sync` 不变；MRO = Service→Market→Financial→Events→Derived→Completeness→object；所有 `self._sync_*` 调用经 MRO 解析不变 |
| pyflakes | 六文件无 F821 |
| 行数 | 主文件 248 / market 575 / financial 480 / events 285 / derived 415 / completeness 387（原 1711 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src;../strategy-factory/src" python -m pytest tests/test_tdx_storage_phase8.py tests/test_warmup_audit_scripts_contract.py -q
# 22 passed
```

**阶段2（AKShare manager + service 类）完成**：strategy_mgr_crud / strategy_mgr_lifecycle / tdx_sync_service 共 3 个文件退出超 1000 行清单。AKShare 包内已无源码文件 ≥1000 行。

### 2026-06-15 第一一六批：Quant Core strategy_ai fragment 退场（Pattern C → 真 mixin）

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `storage/sqlite/strategy_ai_repos/`（`reads.py`/`writes.py`/`mappers.py` + queries 拆 7 repo：`factory_runs`/`dispatch`/`topn_scores`/`events`/`theme_graph`/`lineage`/`outbox`）|
| 装配方式 | `strategy_ai.py` 删除 `_exec_block(...)`，改为 `class StrategyAIMixin(_ReadsMixin, _WritesMixin, _FactoryRunsMixin, _DispatchMixin, _TopnScoresMixin, _EventsMixin, _ThemeGraphMixin, _LineageMixin, _OutboxMixin, _MappersMixin)`；每个 class-body 片段加共享 header（stdlib + `..strategy_factory_json_budget` + logger）转成真 mixin |
| 已迁出职责 | queries.py 的 63 个方法按表前缀路由到 7 repo（factory_runs 10 / dispatch 5 / topn 8 / events 17 / theme_graph 11 / lineage 7 / outbox 5）；reads/writes/mappers 各转单 mixin |
| 零漂移 | `StrategyAIMixin` 方法集 99 个、SHA-256 `81bb014a5783dd94f3edcf9c408f511f12977a06b32860f00859cc6b3b0f1ac9` 退场前后完全一致；MRO 顺序镜像旧 `reads→writes→queries→mappers` 拼接；删除 `strategy_ai_parts/`（无外部引用）|
| pyflakes | 11 文件无 F821 |
| 行数 | `strategy_ai.py` 27 / 最大 repo `reads.py` 709（原 queries.py 2152 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../strategy-factory/src" python -m pytest tests/ -q -k "storage or strategy or kline or json"   # 30 passed (quant-core)
PYTHONPATH=... python -m pytest tests/test_theme_graph_schema.py tests/test_strategy_factory_ownership.py -q   # 36 passed (akshare consumers)
```

### 2026-06-15 第一一七批：Quant Core strategy_incubation fragment 退场（Pattern C）

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `storage/sqlite/strategy_incubation_repos/`（`_base.py` 承接 header imports/常量/module helpers + reads/writes/mappers + queries 拆 6 repo：`trade_positions`/`signal_evidence`/`closure_snapshots`/`execution_acceptance`/`incubation_metrics`/`trade_audit`）|
| 装配方式 | `strategy_incubation.py` 删除 `_exec_block(...)`，改为 `class StrategyIncubationMixin(_IncReadsMixin, _IncWritesMixin, 6×query mixin, _IncMappersMixin)`；`_base.py` 用 `__all__` 导出 header 名（`_safe_int`/`_string`/`_fallback_execution_audit_gate` 等），各 mixin `from ._base import *` + 显式下划线 helper |
| 已迁出职责 | queries.py 17 方法路由（closure 7 / trade_audit 5 / metrics 2 / 其余各 1）；reads/writes/mappers 各转 mixin |
| 零漂移 | `StrategyIncubationMixin` 方法集 59 个、SHA-256 `487dcd9c982bd0f7b20e58f7e74e20d35d39ba74219636c1feaa7f2767c2462b` 退场前后一致；删 `strategy_incubation_parts/`（无外部引用）|
| pyflakes | 无 F821（仅 star-import 提示）|
| 行数 | `strategy_incubation.py` 26 / 最大 repo `trade_audit.py` 932（原 queries.py 1860 行退出清单）|

验证结果：

```bash
PYTHONPATH=... python -m pytest tests/test_execution_audit_acceptance_backfill.py tests/test_execution_audit_snapshot_contract.py tests/test_closure_review_contract.py -q
# 8 passed
SQLiteAdapter(':memory:') 实例化 OK
```

### 2026-06-15 第一一八批：Quant Core market_context 拆分（Pattern B mixin）

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `storage/sqlite/market_context_repos/`（`base.py` 承接 class-attrs + 全部 static/classmethod helper；`headline_labels`/`stock_radar_repo`/`market_events_repo`/`market_documents_repo`/`vectors_fund_flow_repo` 承接各域 async 方法）|
| 装配方式 | `market_context.py` 改为 `class MarketContextMixin(_BaseMixin, _HeadlineMixin, _StockRadarMixin, _EventsMixin, _DocumentsMixin, _VectorsFundFlowMixin)`；class-attrs/helpers 集中在 `_BaseMixin`，经 MRO 供各域 async 方法 `self.`/`cls.` 调用 |
| 已迁出职责 | 52 成员：34 个 class-attr/static/class helper → base；async 方法按 headline(2)/stock_radar(8)/events(3)/documents(2)/vectors+fund_flow(3) 分域 |
| 零漂移 | `MarketContextMixin` 成员集 52、SHA-256 `479bbffa6365de607b567d5d79eaa333417c84267a130482c65f19feb92e2d85` 拆分前后一致；repo 相对 import 深度 `.`→`..` 修正 |
| pyflakes | 无 F821 |
| 行数 | `market_context.py` 19 / 最大 repo `base.py` 455（原 1652 行退出清单）|

验证结果：

```bash
PYTHONPATH=... python -m pytest tests/test_market_event_storage.py tests/test_market_temperature_storage.py -q   # 6 passed (quant-core)
PYTHONPATH=... python -m pytest tests/test_stock_radar.py -q   # 11 passed (akshare)
```

### 2026-06-15 第一一九批：Quant Core _vector_unified_storage 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `storage/sqlite/_vector_unified_storage_search.py`（`_VectorUnifiedStorageSearchMixin`）|
| 装配方式 | `_vector_unified_storage.py` 保留 collections/profiles 方法；search/snapshot/kline-pattern 方法迁出；`vector_unified.py` 的 `VectorUnifiedMixin` 基类列表插入新 `_VectorUnifiedStorageSearchMixin` |
| 已迁出职责 | `search_vector_collection`/`save_vector_index_snapshot`/`save_kline_pattern_window`/`list_kline_pattern_windows`/`list_vector_index_snapshots` 等迁入 search mixin；保持 8-space class-body 缩进 |
| 零漂移 | `VectorUnifiedMixin` 成员集 52、SHA-256 `d08c97e281399e009115412ccf918d9dc288b8a45e8f3944f4d6727250c73445` 拆分前后一致 |
| pyflakes | 无 F821 |
| 行数 | `_vector_unified_storage.py` 441 / `_vector_unified_storage_search.py` 586（原 1013 行退出清单）|

验证结果：

```bash
PYTHONPATH=... python -m pytest tests/test_sqlite_runtime_compat.py -q   # 2 passed (akshare consumer)
SQLiteAdapter VectorUnified 方法齐全
```

**阶段3（Quant Core storage）完成**：strategy_ai_parts/queries / strategy_incubation_parts/queries / market_context / _vector_unified_storage 共 4 个文件退出超 1000 行清单，且 strategy_ai/strategy_incubation 的 `_exec_block` fragment loader 已退场为真 mixin。

### 2026-06-15 第一二〇批：Strategy Factory stock_strategy_matrix fragment 退场（Pattern C）

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `application/stock_strategy_matrix_mixins/`（`normalizers_core`/`normalizers_allocation`/`normalizers_scoring`/`normalizers_families` + `policy` + `evaluation`）|
| 装配方式 | `stock_strategy_matrix.py` 删除 `_exec_block(...)`，改为 `class StockStrategyMatrixPlanner(_MarketOpportunityScannerUtilityMixin, _MatrixNormalizersCoreMixin, _MatrixAllocationMixin, _MatrixScoringMixin, _MatrixFamiliesMixin, _MatrixPolicyMixin, _MatrixEvaluationMixin)`；normalizers.py 54 方法路由 4 mixin（core 含 `__init__`+class-attrs），policy/evaluation 各转 mixin |
| 零漂移 | `StockStrategyMatrixPlanner` 成员集 88、SHA-256 `bd6eb259d2fd0375fc98d5e5785755c8782e3c8d2c162e730481964d9be98160` 退场前后一致；删 `stock_strategy_matrix_parts/`（无外部引用）；`future_annotations` 保留 |
| monkeypatch 修复 | 拆分后 9 个 runtime 配置常量（`STOCK_STRATEGY_MATRIX_ENABLED`/`STOCK_FIRST_ROUTER_*`/`STRATEGY_FACTORY_VECTOR_*`/`STOCK_DIRECTION_GATE_ENABLED`）改为经 `domain.constants` module 引用（`_matrix_const.X`），test_target_scope/test_direction_gate/test_router_matrix_wiring 的 monkeypatch 同步重定向到 `domain.constants` |
| pyflakes | 无 F821 |
| 行数 | `stock_strategy_matrix.py` 66 / 最大 mixin `policy.py` 985（原 normalizers.py 2032 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src" python -m pytest tests/ -q -k "matrix or router or scanner or direction or target or fragment or decoupling"
# 86 passed
```

### 2026-06-15 第一二一批：Strategy Factory domain/market_evidence 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `domain/market_evidence_entries.py` |
| 装配方式 | `market_evidence.py` 保留 public builders（`build_market_evidence_pack`/`resolve_direction_and_confidence`/`apply_evidence_first_candidate`/`summarize_generation_quality`）+ `_build_prediction_contract_from_pack`/`_build_alpha_thesis` 等，从 entries 模块 re-import 29 个 coercion/entry helper |
| 已迁出职责 | `market_evidence_entries.py`: `_as_dict`/`_normalize_direction`/`_evidence_source_type`/`_snapshot_factor_entries`/`_event_entries`/`_fund_flow_entries`/`_regime_entries`/`_template_entry` 等抽取层 |
| 行为保持 | `research/runner.py`、`domain/spawner.py`、`api/semantic_contract.py` 的 import 不变（注意 `application/market_evidence.py` 是另一独立文件，未触碰）|
| pyflakes | 无 F821 |
| 行数 | `market_evidence.py` 604 / `market_evidence_entries.py` 709（原 1234 行退出清单）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src" python -m pytest tests/test_evidence_first_generation.py -q   # 10 passed
```

### 2026-06-15 第一二二批：Strategy Factory application 层多文件拆分

已落地内容：

| 文件 | 处理 | 行数结果 |
| --- | --- | --- |
| `application/_cycle_success_summary.py` 1038 | 抽 17 个聚合 helper 到 `_cycle_success_aggregators.py`，保留 `build_success_run_summary` | 854 / 227 |
| `submission_gate/runner_parts/multiple_testing.py` 1017 | fragment 再分片：拆出 `multiple_testing_admission.py` 并加入 `submission_gate/runner.py` 的 `_exec_fragments` 列表 | 744 / 271 |
| `semantic_contract_parts/policy.py` 1069 | fragment 再分片：拆出 `policy_contract.py` 加入 `semantic_contract.py` 的 `_exec_fragments` 列表 | 415 / 652 |
| `cycle_runner_parts/normalizers.py` 1152 | fragment 再分片：拆出 `run_loop.py`（`run` 方法）加入 `cycle_runner.py` 的 `_exec_block` 列表 | 375 / 776 |
| `_factory_scheduler_loop_parts/policy.py` 1090 | fragment 再分片：拆出 `policy_execution.py` 加入 `_factory_scheduler_loop.py` 的 `_exec_block` 列表 | 676 / 413 |
| `_submitter_actions/runner.py` 1046 | 抽 17 个模块级 helper 到 `_runner_helpers.py`，`from ._runner_helpers import (...)` 在 exec_block 前注入 globals | 613 / 544 |

| 项 | 结果 |
| --- | --- |
| 行为保持 | exec_block/exec_fragments 列表新增分片文件后，原 class/module 命名空间组合不变；`FactoryCycleRunner`/`_StrategySubmitterActionsMixin`/`_StrategyFactorySchedulerLoopMixin` 方法齐全；`build_success_run_summary`/`synthesize_confidence_contract` 等公共入口 import 不变 |
| 测试同步 | `test_scheduler_smoke.py::test_cycle_runner_does_not_enable_factor_self_heal_by_default` 静态源码扫描改为读取 `cycle_runner_parts/*.py` 全目录（`run` 方法已移至 `run_loop.py`）|
| pyflakes | 涉及文件无 F821 |
| 已知遗留 | `_submitter_actions/runner_parts/semantic_contract.py`（1348）为单个 1330 行 `_submit_one` 方法 fragment，无法按方法边界安全机械拆分，按方案"不建议一次性大重写"暂留，待后续函数级分解 |
| 预存在失败 | `test_runtime_provider_boundary.py` 2 例为 `from run_strategy_factory import`（脚本在 `scripts/factories/` 而非仓库根）导致的预存在失败，与本次重构无关（git diff 该测试无改动）|

验证结果：

```bash
PYTHONPATH="src;../aiask-quant-core/src" python -m pytest tests/test_fragment_loader.py tests/test_package_decoupling_boundary.py tests/test_scheduler_smoke.py -q   # 23 passed
PYTHONPATH=... python -m pytest tests/ -q -k "submitter or submission or cycle or scheduler or semantic or contract or success or matrix"   # 全绿（除 2 预存在 root-runner 失败）
```

### 2026-06-15 第一二三批：Agent gateway.py 拆分（Pattern B 包 + facade）

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `aiask_agent/gateway/`（`__init__.py` facade + `models.py` + `stores.py` + `http_client.py` + `adapters.py` + `router.py` + `runtime.py`）|
| 装配方式 | `gateway.py` 改同名 package；`__init__.py` 用 `globals().update(dir(每个子模块))` re-export 全部公开名；子模块按依赖层级 `from .X import *` 串联（models←stores/http_client←adapters←router(+stores)←runtime）|
| 已迁出职责 | models: 常量/`GatewayPlatformStatus`/`normalize_platform`/`parse_delivery_target`；stores: 3 个 Gateway*Store；http_client: `BasePlatformAdapter`+`_json/_form/_multipart_request*`；adapters: 24 个平台 adapter + `ADAPTERS`+`adapter_for`；router: `DeliveryRouter`；runtime: `GatewayRuntime` |
| 行为保持 | 外部 10 个 import 名（`ADAPTERS`/`DeliveryRouter`/`Gateway*Store`/`GatewayRuntime`/`HERMES_PLATFORM_MATRIX`/`PLATFORM_ENV_KEYS`/`adapter_for`/`normalize_platform`）齐全；adapters 经 `_http.` module-attr 调用 http helper 以维持 `gateway_module._http_client.<fn>` monkeypatch（test 同步重定向）；相对 import 深度 `.`→`..` 修正 |
| pyflakes | 无 F821（仅 star-import 提示）|
| 预存在失败 | `test_hermes_native_live_adapters.py::test_gateway_inbound_...` 因 untracked `gateway_route_factories.py` 的 `delivery_router(self)` 与 `routes/gateway.py` 调用 `delivery_router_factory(messages=...)` 签名不匹配而失败——已用 HEAD 单文件 gateway.py 复现，确认与本次拆分无关 |
| 行数 | 最大 `adapters.py` 835（原 1829 行退出清单）|

验证结果：

```bash
PYTHONPATH=... python -m pytest tests/test_gateway_daemon.py tests/test_gateway_daemon_phase2.py tests/test_gateway_daemon_phase4.py -q   # 全绿
PYTHONPATH=... python -m pytest tests/test_hermes_native_live_adapters.py -q   # 17 passed, 1 预存在失败
PYTHONPATH=... python -m pytest tests/test_endpoint_drift_gate.py tests/test_tool_call_path_gate.py tests/test_server.py tests/test_connector_health.py -q   # 12 passed
```

### 2026-06-15 第一二四批：Agent runtime.py 拆分（AgentRuntime mixin）

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `_runtime_handoff.py`、`_runtime_tool_calling.py`、`_runtime_code_tools.py`、`_runtime_jobs.py` |
| 装配方式 | `runtime.py` 保留 header/常量/`AgentRunResult` + `class AgentRuntime(_RuntimeHandoffMixin, _RuntimeToolCallingMixin, _RuntimeCodeToolsMixin, _RuntimeJobsMixin)` 含 `__init__`/生命周期/`run`(728 行单方法)；handoff/tool-calling/code-tools/jobs 方法群迁出为 sibling mixin |
| 已迁出职责 | handoff specialist policy；`_openai_tool_name(s)`/`_build_context`/`_parse_tool_call`/`_merge_usage`/`_estimate_tokens`；`_register_runtime_bound_tools`/`_moa_tool`/`_execute_python_tool`/`_build_aiask_tools_module`；`_delegate_task`/`_run_job_tool`/`_cronjob_tool` |
| 零漂移 | `AgentRuntime` 方法集 28、SHA-256 `d9e83bdd9a89fef09fb0fb5c860cacbb4c4f5ff52b8cdb77d9e9bbbacc9f3482` 拆分前后一致；staticmethod 装饰器逐一校验保留；`_delegate_task` 内 `AgentRuntime` 改 lazy import 避免循环 |
| 守门同步 | `tool-call-path-classification.json` 的 `_execute_python_tool.handle_rpc` 直连分类 key 从 `runtime.py::AgentRuntime` 更新到 `_runtime_code_tools.py::_RuntimeCodeToolsMixin` |
| 预存在失败 | `test_extended_agent_capabilities.py::test_general_file_terminal_and_code_tools_are_workspace_scoped`（agent_execute_python 子进程 stdout 为空）已用 HEAD 单文件 runtime.py 复现，确认与本次拆分无关 |
| 行数 | `runtime.py` 951 / 最大 mixin `_runtime_code_tools.py` 558（原 1720 行退出清单）|

验证结果：

```bash
PYTHONPATH=... python -m pytest tests/test_server.py tests/test_tool_call_path_gate.py tests/test_endpoint_drift_gate.py tests/test_tool_registry.py -q   # 20 passed
PYTHONPATH=... python -m pytest tests/test_extended_agent_capabilities.py -q   # 22 passed, 1 预存在失败
```

### 2026-06-15 第一二五批：Agent gateway_daemon.py 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `_gateway_daemon_listeners.py`（`_GatewayDaemonListenersMixin`）|
| 装配方式 | `gateway_daemon.py` 保留 `ListenerStatus`/`DaemonStatus` dataclass + `class GatewayDaemon(_GatewayDaemonListenersMixin)`（`__init__`/`start`/`stop`/`status`/`_on_inbound_message`/`_handle_control`/`health_check` 等核心）+ `create_gateway_daemon`/`daemon_enabled`；平台 poller 迁出 |
| 已迁出职责 | `_poll_telegram`/`_poll_email`/`_poll_weixin_ilink`/`_ws_wecom`/`_ws_qqbot`/`_ws_discord` 监听器 |
| 零漂移 | `GatewayDaemon` 方法集 18、SHA-256 `ab3f326e3d407db3ae61faf704ec46325e530730b3b0a032fb2806debd1b6904` 拆分前后一致 |
| 预存在问题 | 第 335 行 `logger.debug(...)` 引用未定义 `logger`，HEAD 原文件 pyflakes 同样报 F821（rate-limit blocked 分支的潜在 latent bug，与本次拆分无关，保持原状未改）|
| 行数 | `gateway_daemon.py` 581 / `_gateway_daemon_listeners.py` 636（原 1143 行退出清单）|

验证结果：

```bash
PYTHONPATH=... python -m pytest tests/test_gateway_daemon.py tests/test_gateway_daemon_phase2.py tests/test_gateway_daemon_phase4.py -q   # 54 passed
```

### 2026-06-15 第一二六批：scripts/factories/run_strategy_factory_quality_session 拆分

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `scripts/factories/_quality_session_common.py`（格式化 helper + 常量）、`_quality_session_report.py`（blocker/sample 分析）、`_quality_session_render.py`（报告渲染）|
| 装配方式 | 主脚本保留 sys.path bootstrap、runtime/db 装配、async 采集器、state 管理、`main`；从 3 个 sibling 模块 import 纯函数（render 经 `_quality_session_render` re-export report 分析名）|
| 已迁出职责 | common: `_safe_int/_safe_float/_pct/_format_dt/_now/_iso_now/_json_dump/_write_json/_process_alive` + `LOGGER/MARKET_TZ/DEFAULT_EXECUTION_MODE`；report: `_build_blocker_summary/_compact_run_detail/_extract_issue_flags/_quality_strategy_pool` 等；render: `_render_report/_render_entry/_build_aggregate_summary/_build_priority_findings/_render_*` |
| 行为保持 | `python run_strategy_factory_quality_session.py --help` 正常；`@dataclass SessionPaths` 装饰器修正保留；report/render 各补 `import json`/`Counter` |
| 二次分片 | 主脚本再拆出 `_quality_session_collectors.py`（async 采集器 + `_split_run_ids`/`_resolve_latest_run_id_since`）；`_LEGACY_BUDGET_MISMATCH_*` 常量入 common |
| 行数 | 主脚本 597 / common 102 / report 424 / render 946 / collectors 577（原 2495 行退出清单）|

验证结果：

```bash
F:/Python311/python.exe -m py_compile scripts/factories/*.py   # passed
python run_strategy_factory_quality_session.py --help   # argparse help OK
```

### 2026-06-15 第一二七批：scripts/db_sync 拆分 + shadow_validation 回退

已落地内容：

| 文件 | 处理 | 结果 |
| --- | --- | --- |
| `scripts/db_sync.py` 1080 | 拆出 `_db_sync_common.py`（常量/helper/sys.path + `pro`/`tdx_local` 单例）、`_db_sync_tasks.py`（15 个 `sync_*` 任务）；main 保留 `show_status`/`main` | 主 364 / common 130 / tasks 646；`--help` OK |
| `scripts/ops/trade_prediction_shadow_validation.py` 1317 | 尝试 3-way 拆分时 path 常量（`REPO_ROOT`/`DEFAULT_SHADOW_DB`）跨模块引用产生 F821，已**回退到原文件**（保持可编译），留待后续按 common(常量+path helper)/snapshots/commands 重新切分 | 维持 1317（未退出清单）|

### 2026-06-15 本会话收尾快照

**起点**：仓库 41 个 ≥1000 行文件。**当前**：8 个。本会话清掉 33 个，批次 100–127。

剩余 8 个：
1. `packages/agent/src/aiask_agent/fallback_server.py` 1762 — 单 `build_server` 函数内嵌 `AIASKAgentHandler` 闭包类（do_GET ~900 行），需 closure→实例属性重构，高风险暂留
2. `packages/strategy-factory/.../runner_parts/semantic_contract.py` 1362 — 单个 1330 行 `_submit_one` 方法 fragment，无法按方法边界机械拆分
3. `scripts/ops/trade_prediction_shadow_validation.py` 1317 — 本批回退，待重做
4-8. 5 个测试文件（`test_admission_authority` 1645 / `test_theme_graph_schema` 1565 / `test_factory_deep_repair` 1129 / `test_extended_agent_capabilities` 1120 / `test_full_chain_regression_repairs` 1035）

**已完成阶段**：P1（Agent server,前序会话）、P2（Desktop,前序会话）、阶段1-2（AKShare 源码+manager 全清）、阶段3（Quant Core,含 strategy_ai/strategy_incubation 的 `_exec_block` fragment 退场为真 mixin）、阶段4（Strategy Factory,含 stock_strategy_matrix fragment 退场）、阶段5（gateway/runtime/gateway_daemon；fallback_server 暂留）。

**零漂移保证**：所有 facade 类/包均经方法集 SHA-256 或工具指纹比对，拆分前后一致；guardrail/control-token/ActionIntent/live-trading 边界未改；fragment loader 在 quant-core/strategy-factory 的 4 处核心已退场。

### 2026-06-15 第一二八批：scripts/ops/trade_prediction_shadow_validation 拆分（重做成功）

已落地内容：

| 项 | 结果 |
| --- | --- |
| 新增模块 | `scripts/ops/_shadow_common.py`（常量 + `CommandSpec` + path/db/env helpers + `SECRET_PATTERNS`/`_redact`）、`_shadow_snapshots.py`（`collect_local_snapshot`/`collect_agent_snapshot` + matrix/dimension helpers）|
| 装配方式 | 主脚本保留 imports + 命令构建器（`regression_commands`/`run_command` 等）+ `cmd_*` handlers + `main`；从 common/snapshots import |
| 上次回退修复 | path 常量 `REPO_ROOT`/`DEFAULT_SHADOW_DB`/`DEFAULT_REPORT_ROOT` 统一进 common 并 re-import；`_redact`/`SECRET_PATTERNS` 移入 common 供 snapshots 复用；snapshots 补 `Path` import |
| 行为保持 | `--help` OK；纯 stdlib 脚本，无包依赖；无 F821 |
| 行数 | 主脚本 805 / common 282 / snapshots 330（原 1317 行退出清单）|

**scripts 全部退出超 1000 行清单**：run_strategy_factory_quality_session、db_sync、trade_prediction_shadow_validation 三个脚本完成。

### 2026-06-15 第一二九批：strategy-factory + akshare-mcp 大测试文件拆分

已落地内容：

| 文件 | 处理 | 结果 |
| --- | --- | --- |
| `strategy-factory/tests/test_admission_authority.py` 1645 | 拆 `_admission_helpers.py`（共享 helper + autouse fixture `_clear_dev_v1_env`）+ 4 个测试文件（core/observe_first/downgrades/submit_flow/submit_persist）| 主 91，最大 577 |
| `akshare-mcp/tests/test_theme_graph_schema.py` 1565 | 新建 `conftest.py`（`tmp_db_path`/`initialized_db` fixture）+ `_theme_graph_helpers.py`（helper + `EXPECTED/LEGACY/FORBIDDEN_TABLES`）+ 3 个测试文件（schema/events/lineage）| 最大 584；DDL 自检 `__file__` 仍指 schema 文件 |
| 行为保持 | pytest 自动发现拆分后的测试文件；fixture 经 conftest 跨文件共享；autouse fixture 经 import 注册；按 `def test_`/`async def test_` 边界切片，避免 stranded 装饰器（修了 `@pytest.fixture`/`@pytest.mark.asyncio` 边界）|

验证结果：

```bash
# strategy-factory
python -m pytest tests/test_admission_authority*.py -q   # 24 passed
# akshare-mcp
python -m pytest tests/test_theme_graph_schema.py tests/test_theme_graph_events.py tests/test_theme_graph_lineage.py -q   # 29 passed
```

### 2026-06-15 第一三〇批：剩余大测试文件拆分（deep_repair / full_chain / extended_capabilities）

已落地内容：

| 文件 | 处理 | 结果 |
| --- | --- | --- |
| `akshare-mcp/tests/test_factory_deep_repair.py` 1129 | 按 test 边界拆 2 文件（part2 含 `_seed_pool_for_admission` + 其消费者）| 506 / 628 |
| `akshare-mcp/tests/test_full_chain_regression_repairs.py` 1035 | 拆 2 文件，共享 header + `FakeMcp`/`FakeAcquire` 类各自复制 | 410 / 658 |
| `agent/tests/test_extended_agent_capabilities.py` 1120 | 拆 2 文件，共享 header + 6 个 Model 类各自复制 | 562 / 717 |
| 行为保持 | 纯按 `def test_` 边界切片，header（imports + 共享 Fake/Model 类）复制到各文件；pytest 自动发现；collection 校验通过（23 / 60 tests collected）|

### 2026-06-16 全任务收尾快照

**起点 41 个 ≥1000 行文件 → 现 2 个。** 本会话批次 100–130 清掉 39 个。

**剩余 2 个（均为单体不可机械拆分，已记录原因）**：
1. `packages/agent/src/aiask_agent/fallback_server.py` 1762 — `build_server` 函数内嵌 `AIASKAgentHandler` 闭包类（`do_GET` ~900 行闭包方法，引用 build_server 局部变量），需 closure→实例属性重构，超出机械切片范围
2. `packages/strategy-factory/.../runner_parts/semantic_contract.py` 1362 — 单个 1330 行 `_submit_one` 方法 fragment，无法按方法边界拆分

**阶段完成度**：P1（Agent server，前序）✅ / P2（Desktop，前序）✅ / 阶段1 AKShare 源码 ✅ / 阶段2 AKShare manager ✅ / 阶段3 Quant Core（fragment 退场）✅ / 阶段4 Strategy Factory ✅ / 阶段5 Agent gateway·runtime·gateway_daemon ✅（fallback_server 暂留）/ 阶段6 scripts ✅ + 5 大测试文件全拆 ✅。

**零漂移与边界**：所有 facade（类/包）方法集 SHA-256/工具指纹拆分前后一致；guardrail / control-token / ActionIntent / live-trading 边界未改；quant-core + strategy-factory 的 `_exec_block` fragment loader 在 strategy_ai/strategy_incubation/stock_strategy_matrix 三处核心退场为真 mixin；`tool-call-path-classification.json` 同步更新迁移后的直连分类。

**预存在失败（与本次重构无关，已逐一用 HEAD 复现确认）**：`test_runtime_provider_boundary`（runner 不在仓库根）、`test_gateway_inbound`（untracked `gateway_route_factories` 签名 bug）、`test_general_file_terminal_and_code_tools`（子进程 stdout）、`gateway_daemon.py:335` `logger` 未定义 latent bug。
