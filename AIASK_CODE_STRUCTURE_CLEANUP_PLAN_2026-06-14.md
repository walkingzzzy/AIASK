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

### 2026-06-14 本轮收尾快照

当前代码直接统计：

| 文件/范围 | 行数 | route decorators |
| --- | ---: | ---: |
| `packages/agent/src/aiask_agent/server.py` | 1787 | 0 |
| `packages/agent/src/aiask_agent/run_payloads.py` | 596 | 0 |
| `packages/agent/src/aiask_agent/desktop_capabilities_payloads.py` | 250 | 0 |
| `packages/agent/src/aiask_agent/server_cli.py` | 104 | 0 |
| `packages/agent/src/aiask_agent/fallback_server.py` | 1784 | 0 |
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

1. `server.py` 从第三批记录时的 6378 行、136 个 FastAPI route decorators，收口到 1787 行、0 个 FastAPI route decorators。
2. 新增/启用的 route factory 覆盖 Desktop data/user/finance/workbench/runs、AI config/status、responses/chat/search、run history/control、intents/approvals、jobs、tools、Hermes status/sessions、full/native controls、skills/plugins、MCP aggregation、learning/RL、gateway/connectors/webhooks，并新增 `route_auth.py` 承接 auth/control helper、`audited_tool_calls.py` 承接 tool-call 审计 helper、`desktop_payloads.py` 承接 Desktop data/settings/profile payload builder、`desktop_capabilities_payloads.py` 承接 Desktop capabilities 聚合 payload、`run_payloads.py` 承接 run/session/workbench/handoff/artifact payload helper、`request_context.py` 承接 request context helper、`response_payloads.py` 承接 responses/chat payload formatter、`ai_payloads.py` 承接 AI config/status/smoke/models payload builder、`fallback_server.py` 承接 legacy HTTPServer、`server_cli.py` 承接服务端启动 CLI。
3. `docs/architecture/tool-call-path-classification.json` 已同步删除或更新迁移后 stale 的 FastAPI/direct tool-call 分类；fallback HTTPServer 的只读分类已指向 `fallback_server.py`，Desktop capabilities 的只读分类已指向 `desktop_capabilities_payloads.py`。
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
```

剩余建议：

1. P1 的 FastAPI route decorator 迁移、auth/control helper 拆分、audited tool-call helper 拆分、Desktop payload builder 拆分、Desktop capabilities payload 拆分、run/session/workbench payload 拆分、request context helper 拆分、responses/chat payload formatter 拆分、AI config/status/smoke/models payload builder 拆分、fallback HTTPServer 分层和 server CLI/main 分层已经完成；下一步继续按小批次迁出 `server.py` 内剩余 Hermes readiness/health 或 Financial Manager/broker helper。
2. P1 结束前可再跑一次完整 Agent HTTP contract 组合，并重新统计 `server.py` helper/fallback 体量。
3. P2 进入 Desktop API/mock/types/CSS 拆分前，先把当前 Agent route 拆分作为独立 PR 或提交切分，降低后续冲突面。
