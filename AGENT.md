# AGENT.md — 金融系统级 AGENT 开发规范

> 本文件是仓库的开发与协作约定。所有人类与 AI 编码代理（Claude / Codex / Cursor / Kiro 等）改动本仓库前必须先读它。
>
> 维护原则：**事实优先，代码先于文档**。所有结论必须能落到具体文件 + 行号；与代码不一致的描述视作过期，发现后立即修订。

---

## 1. 项目定位

这是一个面向 A 股（兼顾宏观/期货/期权）的"**金融系统级 AI Agent**"，核心定义来自 `docs/architecture/金融系统级Agent优化方案.md`：以六层架构组织能力，从基础设施一路覆盖到监管治理。

```
L6  监管合规与治理   审计追踪 / 可解释性 / 人类监督
L5  多 Agent 编排    专业化角色 / 辩论 / 共识 / 任务分解
L4  自主决策与执行   策略生成 / 回测 / 风控 / 执行 / 意图确认
L3  金融推理引擎     因子 / 基本面 / 技术面 / 情绪 / 归因
L2  数据感知与记忆   行情 / 财报 / 新闻 / 长期记忆 / 学习闭环
L1  基础设施         LLM 路由 / MCP / 安全沙箱 / 网关 / 工具注册
```

仓库由四个**互为依赖但边界明确**的代码包 + 一个桌面端组成，最终拼出三大并行的"工厂"：

| 子系统 | 物理位置 | 角色 |
|---|---|---|
| **AIASK Agent 运行时** | `packages/agent` | L1-L6 编排器、HTTP API、模型循环、`agent_*` 工具表面、网关、意图确认 |
| **AKShare MCP Server** | `packages/akshare-mcp` | L2-L4 金融领域 MCP（市场/财务/因子/回测/策略/向量/治理）+ SQLite 持久层 |
| **Strategy Factory** | `packages/strategy-factory` | L4 策略生产线（DDD 分层：domain / application / infrastructure / api） |
| **Finance MCP Servers** | `packages/finance-mcp-servers` | L1 国内行情/交易软件桥（通达信 / 同花顺 / 东方财富 / MiniQMT） |
| **Desktop 工作台** | `desktop/` | React + Vite + Tauri，仅消费 Agent HTTP API（不直连 MCP / 不直调 manager） |

三大工厂的依赖与反馈：

```
                 ┌─────────────── 衰减 / 实盘反馈 ───────────────┐
                 │                                                │
   因子挖掘工厂 ──产出活跃因子池──▶ 策略工厂 ──产出策略候选──▶ 孵化工厂 ──产出毕业策略──▶ 实盘
   FactorMiningFactory             StrategyFactory                IncubationFactory
   pkg: akshare-mcp                pkg: strategy-factory          pkg: akshare-mcp
   .services/factor_mining_factory .application/                  .services/incubation_factory
```

---

## 2. 系统级 Agent 架构与边界（必读）

整个项目最重要的一条边界：**模型只能看到 `agent_*` 工具，所有金融能力通过 adapter 落到 MCP / Strategy Factory，绝不直暴露 manager**。这是由代码强制的，不是"建议"。

### 2.1 Agent 运行时层级（实测）

```
Desktop / CLI / 第三方客户端
        │  HTTP (FastAPI on 127.0.0.1:8767)
        ▼
┌──────────────────────────────────────────────────────────┐
│  packages/agent/src/aiask_agent/server.py                │
│  - create_app(): 构造 finance_safe runtime + lazy full   │
│  - require_api / require_full / control_authorized       │
│  - 路由: /v1/responses /v1/chat/completions /intents/*   │
│         /v1/capabilities/parity /v1/hermes/* /v1/mcp/*   │
│         /v1/desktop/quant/* /v1/runs/{id}/events SSE     │
└──────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│  AgentRuntime (runtime.py)                               │
│  循环: planner → context_compaction → model.complete    │
│        → tool_call (registry) → guardrails → events     │
│  组件: ContextManager, TaskPlanner, ToolLoopGuardrails, │
│        FinancialMemoryStore, ActionIntentStore,         │
│        AgentSessionStore                                 │
└──────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│  AgentToolRegistry (tool_registry.py)                    │
│  - register(name, ...) 强制 ensure_agent_tool_name       │
│  - openai_tools() → 给 LLM 看                            │
│  - call_tool(name, args) → 统一 envelope + trace_id      │
│  - 元数据: side_effect.level, category, toolset          │
└──────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│  Adapters (aiask_agent/adapters/)                        │
│  akshare.py             → analyze_stock_workflow 等      │
│  strategy_factory.py    → call_strategy_manager(action)  │
│  quant.py               → 回测 / 因子 / 组合 / 风险      │
│  → 内部走 from akshare_mcp.tools.managers.* import       │
└──────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│  MCP / Strategy Factory / SQLite / 向量平台              │
└──────────────────────────────────────────────────────────┘
```

### 2.2 双运行模式（toolset），由代码强制

定义在 `packages/agent/src/aiask_agent/tools/policy.py`：

| toolset | 默认 | 切换条件 | 允许的 tool category |
|---|---|---|---|
| `finance_safe` | ✅ | — | `financial_read`、`financial_stateful`、`mcp_financial` |
| `general_full` | ❌ | `AIASK_AGENT_TOOLSET=general_full` + `AIASK_AGENT_ENABLE_GENERAL_TOOLS=1` + `AIASK_AGENT_ENABLE_HERMES_FULL=1` + loopback + 控制 token | 上面 + `general_*` / `browser` / `terminal_backend` / `messaging` / `platform_*` / `rl_training` / `moa` / 等 19 类 |

`server.py:283 _hermes_full_enabled()`、`server.py:362 full_authorized()` 三层并行：环境变量 + loopback IP + Bearer token；任何一层不满足就 401/403。

### 2.3 Hermes 边界（vendor 只读快照）

`docs/architecture/hermes-boundary.md` 是硬性合同，落实到代码：

- `vendor/hermes-agent-upstream/` 只是参考实现快照。**禁止** `import` / 子进程 / sidecar 调用。
- 任何 `pyproject.toml` / lock 都**禁止**出现 `hermes-agent` 依赖。
- 等价能力（browser、terminal、skill、plugin、cron、MoA、RL、平台网关 ...）必须用 AIASK 自有模块在 `packages/agent` 重写。
- 守门测试：
  - `packages/agent/tests/test_no_hermes_dependency.py` — 扫描 `import hermes`、`from hermes`
  - `packages/agent/tests/test_hermes_reference_guardrails.py` — 防止 vendor 路径被 sys.path 注入
  - `packages/agent/tests/test_native_full_parity.py` — 对等矩阵覆盖测试

### 2.4 模型可见 / 不可见对照（硬性边界）

`tools/policy.py:9 FORBIDDEN_DIRECT_MANAGER_TOKENS` — 凡是 `agent_*` 工具名包含以下子串就抛 `ValueError`：

```python
("strategy_manager", "live_trading_manager", "paper_trading_manager",
 "execution_manager", "available_tools", "get_tool_contract")
```

正确做法是在 `adapters/strategy_factory.py` 包一层：

```python
async def call_strategy_manager(action: str, params: dict) -> dict:
    from akshare_mcp.tools.managers.strategy_manager import strategy_manager
    return await asyncio.wait_for(strategy_manager(action=action, params=params), timeout=...)
```

然后注册成 `agent_strategy_review_snapshot`、`agent_factory_status` 等模型可读的别名。


---

## 3. 仓库结构（Monorepo）

每个 `packages/*` 是独立 Python 包，**uv** 管理 venv，包间通过 `tool.uv.sources = { path = "...", editable = true }` 互链。Python ≥ 3.12。

### 3.1 顶层目录

```
.
├── packages/
│   ├── agent/                  # AIASK Agent 运行时 (aiask-agent)
│   ├── akshare-mcp/            # AKShare MCP Server (akshare-mcp)
│   ├── strategy-factory/       # Strategy Factory (strategy-factory)
│   └── finance-mcp-servers/    # 通达信/同花顺/东方财富/QMT MCP (aiask-finance-mcp-servers)
├── desktop/                    # React 18 + Vite 6 + Tauri 2
├── scripts/                    # 一次性维护脚本（db_init / db_sync / 审计）
├── docs/                       # 设计与审计文档
├── data/db/                    # SQLite 主库存放点
├── monitoring/ configs/ vendor/ reports/
├── pytest.ini                  # 根 pytest（agent + strategy-factory）
├── Makefile                    # 顶层任务
├── run_strategy_factory.py     # 策略工厂常驻进程
├── run_factor_mining_factory.py# 因子挖掘工厂常驻进程
├── .env / .env.example
└── *.md                         # 顶层方案（策略工厂跑偏修复 / 因子挖掘工厂设计 等）
```

### 3.2 包间依赖（实测自 pyproject.toml）

```
                    aiask-agent
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
  akshare-mcp ──▶ strategy-factory   finance-mcp-servers
       │               │              （独立 stdio MCP，
       └──── editable ┘               通过 MCPAggregator 发现）
```

- `agent/pyproject.toml` 显式 `dependencies = ["akshare-mcp", "strategy-factory", "fastapi", "uvicorn", "openai", "mcp", ...]`，且 `[tool.uv.sources]` 把后两者指向 `../akshare-mcp` 与 `../strategy-factory` editable path。
- `akshare-mcp/pyproject.toml` 同样 editable 依赖 `strategy-factory`。
- `finance-mcp-servers` **不被** agent 显式依赖，运行时通过 `~/.aiask-agent/mcp_servers.json` 注册到 `MCPAggregator`，由 `agent_mcp_*` 工具暴露。

### 3.3 关键模块速览

**`packages/agent/src/aiask_agent/`**（Agent 运行时）：

```
server.py                    HTTP API + create_app + main()
runtime.py                   AgentRuntime 主循环
context.py                   ContextManager（上下文压缩 / 摘要）
planner.py                   TaskPlanner（多步规划）
tool_registry.py             AgentToolRegistry + aiask_envelope
tool_guardrails.py           ToolLoopGuardrails（防爆量循环）
tool_risk.py                 side_effect 分级 + CONFIRM_REQUIRED 行动表
tools/policy.py              ToolPolicy / ToolPolicyEngine / agent_* 检查
tools/catalog.py             FINANCE_SAFE_TOOL_CATALOG / GENERAL_TOOL_CATALOG
tools/schemas.py             所有工具 JSON Schema
adapters/{akshare,strategy_factory,quant}.py  → 进入 MCP / 工厂
intents.py                   ActionIntentStore (SQLite WAL) + IntentExecutor
approvals.py                 ApprovalStore（高危终端命令二次审批）
mcp_client.py                MCPAggregator + MCPTokenStore (OAuth)
acp.py                       ACPManager（客户端注入的 MCP）
gateway.py                   GatewayRuntime + 18+ 平台 ADAPTERS
webhooks.py / scheduler.py   Webhook + Cron
plugin_runtime.py            NativePluginManager（Python/HTTP/Subprocess）
skill_packs.py               SkillPackManager（Hermes-class 技能包）
native_capabilities.py       browser / vision / image_gen / TTS / skills
memory.py / memory_providers.py    长期记忆（默认 SQLite，可插拔）
session_store.py             会话 + responses 持久化
model_client.py              LLM 客户端（OpenAI 兼容）
model_providers.py           ModelProviderRegistry + ProviderUsageStore（凭证池）
learning_loop.py             反思 + 经验注入
recovery.py                  retry_async（指数回退 + 抖动）
financial_readiness.py       金融系统就绪度报告（/v1/financial-system/readiness）
capabilities.py              Hermes parity matrix（HERMES_TOOL_EQUIVALENTS 等）
moa.py / rl_atropos.py / homeassistant.py / voice.py / tui.py
```

**`packages/akshare-mcp/src/akshare_mcp/`**：

```
server.py                    FastMCP("AKShare Stock Data Server v2")
                             - register_runtime_surface(profile)
                             - core / heavy 双层注册
                             - transport: stdio | sse | streamable-http
start_server.py              入口（建议 python -X utf8 启动）
tools/                       MCP 工具层（@mcp.tool 注册）
  managers/                  XX_manager 聚合面（不能直暴露给 LLM）
    strategy_manager.py      ← 单一入口，dispatch 到 ~80 个 action handler
    quant_manager.py         ← 因子 / 回测 / 模型注册表 / AutoML
    risk_manager.py          ← VaR / 暴露 / 压力测试
    incubation_factory_*     ← 孵化相关 manager
    data_sync_manager.py / paper_trading_manager.py / ...
  market/ news/ semantic/    业务工具组
  ai_workflows.py            analyze_stock / governance / 多步研报
  pit_middleware.py          PIT 切片 helper
  tool_catalog.py            导出 MCP tool registry
services/                    领域服务（80+ 个）
  strategy_factory/          ← 策略工厂的"实现端"，与 packages/strategy-factory 协作
  factor_mining_factory/     ← 因子挖掘工厂（多引擎 + 进化 + 池）
  incubation_factory/        ← 孵化工厂（intake/forward_verify/feedback/accelerator）
  vector_platform.py         StrategyVectorPlatform（向量画像 + ANN 索引）
  vector_search.py           VectorSearchEngine（numpy/sqlite 双后端）
  text_embedding.py          OpenAI / Ollama / hash_fallback 三档嵌入
  data_sync.py / data_sync_scheduler.py  ← 数据同步队列 + 死信
  pit_utils.py               Point-In-Time helper
  factor_validation_pipeline.py / factor_scheduler.py
  strategy_lifecycle_shared/ closure_review / incubation / state_machine
  governance_monitor.py / runtime_alerts.py / runtime_risk.py
  promotion_pipeline.py      毕业流水线（incubation → live）
  decision_*.py              决策融合 / 离线评估 / 规则门
  + ~70 个其他领域服务
storage/                     SQLite 存储层
  sqlite/__init__.py         SQLiteAdapter (Mixin 组合, asyncpg-shape API)
  sqlite/schema_*.py         市场 / 策略 / 向量 / 应用 4 大 schema 入口
  sqlite/_schema_market_phase_{1..7}.py  分阶段 DDL
  sqlite/strategy_*           策略 CRUD / AI / 孵化 / 运行态
  sqlite/vector_unified.py    向量统一存储
data_source/                 Tushare / AKShare / eFinance / Baostock 切换
core/                        cache / rate_limiter / retry / vectorized_indicators
contracts/                   strategy_manager_contract.py（80+ action 白名单）
auth.py / env_loader.py / cache.py / utils_kline.py
prompts/ resources/ schemas/  MCP 资源、提示词、Pydantic schema
```

**`packages/strategy-factory/src/strategy_factory/`**（DDD 分层）：

```
api/
  facade.py                  ★ 唯一稳定外部门面，_LAZY_EXPORTS 列表
  contracts.py               Gateway Protocol：VectorSearchGateway / Validation /
                             Risk / Incubation / Autonomy / FactorResearch
  dto.py / dto_parts/        DTO（也用 _fragment_loader 拼装）
application/                 编排层
  factory_scheduler.py       StrategyFactoryScheduler（continuous / daily 模式）
    └── _factory_scheduler_{analysis,runtime,loop}.py   Mixin 切片
  cycle_runner.py            FactoryCycleRunner（单次周期）
  research/runner.py         ResearchPlaneRunner
  research/spawner.py        StrategySpawner
  research/factor_research.py FactorResearchBuilder
  research/opportunity.py    MarketOpportunityScanner
  research/matrix.py         StockStrategyMatrixPlanner
  collect.py                 DataCollector
  backtest_filter.py         BacktestFilter（候选级 shared result）
  quality_gates.py           Gate-A/B/C + Pre-Gate
  submission_gate.py         run_submission_quality_gate
  deduplicator.py / submitter.py / elimination.py
  factory_task_board.py      FactoryTaskBoard（独立 SQLite 任务追踪）
  panels.py / quality_reporting.py / governance_plane_contract.py
  research_plane_contract.py / semantic_contract.py / precompile_contract.py
  event_engine.py            LocalEventDrivenResearchEngine
  incubation_budgeter.py     InNcubation budget allocator
  + 30+ application 模块
domain/                      纯领域
  constants.py               REPRESENTATIVE_STOCKS, BACKTEST_*_THRESHOLDS,
                             RESEARCH_/INCUBATION_/LIVE_ADMISSION_THRESHOLDS,
                             FACTOR_STRATEGY_MAPPING, 50+ env-driven flags
  spawner.py / spawner_parts/         策略族注册
  targets.py / targets_parts/          目标股票解析
  trading_calendar.py / naming.py
  parameter_distribution_registry.py
  spawn_policy_registry.py
  research_tasks.py / strategy_profile.py
infrastructure/
  mcp_adapters.py            MCPRuntimeAdapters
  mcp_services.py            get_backtest_engine_class / runtime warmup
compat/                      过渡兼容层
_fragment_loader.py          exec_fragments / exec_block 拼接器
```

**`packages/finance-mcp-servers/src/aiask_finance_mcp/`**：

```
tongdaxin/server.py          aiask-finance-tdx (pytdx, 行情+下单)
tonghuashun/server.py        aiask-finance-ths (easytrader, Windows only)
eastmoney/server.py          aiask-finance-em (efinance, 行情)
qmt/server.py                aiask-finance-qmt (XtQuant, 需 QMT 客户端)
```

每个都是独立 stdio MCP Server，通过 `mcp_servers_example.json` 配进 `MCPAggregator`。


---

## 4. MCP 子系统（深度）

MCP 在本仓库以**两个角色**出现：一是 **akshare-mcp** 自身作为一个金融 MCP Server（被 Cursor / Claude Desktop 等外部客户端使用），二是 **AIASK Agent 内部的 MCPAggregator** 把若干 MCP Server 聚合成 `agent_mcp_*` 工具。这两条路径不要混淆。

### 4.1 akshare-mcp · 注册架构

入口：`packages/akshare-mcp/start_server.py` → `akshare_mcp.server.main()`。核心逻辑：

```python
# packages/akshare-mcp/src/akshare_mcp/server.py
mcp = FastMCP("AKShare Stock Data Server v2", host=..., port=...)

def _current_startup_profile() -> str:
    # 由环境变量 AKSHARE_MCP_STARTUP_PROFILE 决定: "full" | "tool-only" | "worker"
    ...

def _register_runtime_surface(app: FastMCP, *, startup_profile: str):
    _register_core_tools(app, ...)         # market/finance/fund_flow/macro/news/options/...
                                            # technical/backtest/portfolio/valuation/decision/...
                                            # ai_workflows/governance/managers/research/...
    if startup_profile in {"full", "worker"}:
        _register_full_only_tools(app)     # vector / skills / quant / sentiment /
                                            # data_sync / factor_profile (lazy import)

def _resolve_transport() -> tuple[str, str | None]:
    # MCP_TRANSPORT: stdio (默认) | sse | streamable-http
```

每个 `tools/<name>.py` 都暴露 `def register(mcp: FastMCP)`，里面用 `@mcp.tool()` 装饰协程函数。**约定**：

- 所有协程必须返回 `manager_protocol.ok / fail` envelope（含 `success / data / error / meta`）。
- `meta` 至少带 `tool / source_chain / side_effect / pit`（PIT 切片状态）。
- 长任务在 `services/` 实现，`tools/` 只做参数归一化 + 调用 + envelope 封装。

### 4.2 manager_protocol（MCP 工具的统一契约）

`packages/akshare-mcp/src/akshare_mcp/tools/manager_protocol.py` 定义：

```python
normalize_manager_kwargs(kwargs, *, field_aliases=None)   # PG/JSON 字符串 / dict 都支持
normalize_manager_payload(*, params, kwargs, code, extra) # 合并 BFF 旧调用 + 新结构化调用
normalize_manager_code(code, kwargs, *, normalize=False)  # 代码归一化（去前缀 / 大小写）
extract_common_meta(kwargs, *, defaults)                  # 抽取 as_of / adjust / strict / lineage_*
build_manager_meta(...)                                   # 统一 meta（PIT / lineage / side_effect）
_infer_side_effect_level(tool, action, default)           # 根据动作名推断 read_only / stateful / trade_risk
```

**做新 manager / 新 action 时必须走这套**，否则会被契约测试 `test_tool_argument_contract.py` 拒绝。

### 4.3 strategy_manager 是单一 dispatch 点

`packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py` 是策略相关功能的**唯一对外入口**，对应契约 `contracts/strategy_manager_contract.py`：

```python
STRATEGY_MANAGER_ACTIONS = (
    # CRUD
    "help","create","publish","archive","list","detail","review_report","events",
    "update_metrics","review","subscribe","unsubscribe","my_subscriptions","my_strategies",
    "fork_strategy","update_strategy","delete_personal_strategy",
    "personal_strategy_context","personal_strategy_suggestions",
    "paper_session_get","paper_session_get_or_create","rank","capabilities",
    "daily_snapshot","daily_snapshots","get_signals","get_forward_returns","get_signal_stats",
    # Lifecycle / Factory
    "review_report_recheck","submission_replay","submit",
    "lifecycle_scan","incubation_overview","closure_review",
    "factory_status","factory_run_once","factory_dispatch_run","factory_dispatch_status",
    "factory_runs","factory_run_detail","factory_topn_latest","factory_run_topn",
    "execution_audit_verification","execution_audit_acceptance",
    # Incubation
    "incubation_accounts","incubation_metrics","paper_account","paper_orders","paper_nav",
    "incubation_sync_run","incubation_pipeline","incubation_pipeline_run",
    # Risk / Runtime / Promotion
    "risk_events","risk_snapshots","risk_scan_run","risk_recovery","resolve_risk_event",
    "runtime_alerts","runtime_alert_dispatch_run","runtime_alert_ack",
    "runtime_control","runtime_control_set","runtime_cycle_status","runtime_cycle_run",
    "promotion_reviews","promotion_review_run",
    # Domain projection / Vector / AI / Factory event / Tasks
    "domain_events","domain_projection","domain_projection_snapshot","domain_projection_rebuild",
    "vector_profiles","vector_indexes","vector_index_snapshots","vector_ann_search",
    "vector_reconcile","vector_rebuild","vector_health","vector_cleanup",
    "ai_generate","ai_optimize_personal_strategy","ai_experiments","task_runs",
    "factory_event_create","factory_event_list","factory_event_update",
    "factory_event_approve","factory_event_record_outcome","factory_event_preview_tasks",
)
```

并且在同文件中**显式列出**：

- `STRATEGY_MANAGER_READ_ONLY_ACTIONS` — 默认走 read-only 路径
- `STRATEGY_MANAGER_CONFIRM_REQUIRED_ACTIONS` — 这些 action **必须**先创建 ActionIntent 才能执行
- `STRATEGY_MANAGER_ACTION_SIDE_EFFECTS` — 每个 action 的 side_effect 元数据

> 改 / 加 strategy_manager action 的强制流程：① 在 `strategy_manager_contract.py` 加进列表；② 加 handler；③ 在 ACTION_HANDLERS 表里映射；④ 视情况加进 read-only 或 confirm-required 集合；⑤ 配套 contract test。

### 4.4 MCP Aggregator（Agent 内部）

`packages/agent/src/aiask_agent/mcp_client.py`：

- 配置文件默认 `~/.aiask-agent/mcp_servers.json`，可由 `AIASK_AGENT_MCP_CONFIG` 覆盖。
- 工具命名规则：`agent_mcp_{server}_{tool}`（自动包装），并在 `MCPAggregator.financial_tools()` 里**主动过滤**含 forbidden token 的工具名。
- 仅 `domain == "financial"` 的服务器会被并入金融工具表面；其他作为 `general_full` 才能调用的扩展工具。
- OAuth：`MCPTokenStore` 把 token 存到 `~/.aiask-agent/mcp-tokens/<server>.json`（chmod 600）。
- HTTP / SSE / streamable-http 三种传输都依赖 `httpx`，stdio 走 mcp Python SDK。

`mcp_servers.json` 示例（来自 `packages/finance-mcp-servers/mcp_servers_example.json`）：

```json
{
  "mcpServers": {
    "tongdaxin": {
      "command": "python",
      "args": ["-m", "aiask_finance_mcp.tongdaxin.server"],
      "env": {"TDX_SERVER_IP": "119.147.212.81"},
      "domain": "financial",
      "disabled": false
    }
  }
}
```

### 4.5 ACP（Agent Communication Protocol）

`packages/agent/src/aiask_agent/acp.py` 提供 `ACPManager`：客户端可以在运行时**通过 HTTP 注册自己的 MCP Server** 给 Agent。Agent 不会主动 import 客户端代码，只走 MCP 协议。这是 Desktop 之外集成第三方 MCP 的唯一受控路径。

### 4.6 MCP 启动与排错速查

| 现象 | 直接原因 | 修复 |
|---|---|---|
| Cursor/Claude 把 MCP 日志当 `[error]` | mcp / fastmcp / uvicorn 默认 INFO 写 stderr | server.py 已统一降到 WARNING；不要回退 |
| AKShare 进度条刷屏 | tqdm 默认开 | server.py 已 `os.environ.setdefault("TQDM_DISABLE", "1")` |
| 启动 UnicodeDecodeError | 非 UTF-8 文件 | 必须 `python -X utf8 start_server.py` |
| HTTP 模式 401 | `MCP_TRANSPORT=streamable-http` 未配 token | `_enforce_http_security_baseline()` 拦在 main 之前 |
| 启动后无 vector/skills/quant 工具 | `AKSHARE_MCP_STARTUP_PROFILE=tool-only` | 切回 `full` |


---

## 5. 数据库与向量库（深度）

### 5.1 SQLite 是唯一主库

存在路径优先级（实测自 `storage/sqlite/schema_base.py:default_sqlite_path`）：

```
AKSHARE_MCP_SQLITE_PATH > AIASK_SQLITE_PATH > ~/.aiask/akshare_mcp.sqlite3
```

仓库默认指向 `./data/db/akshare_mcp.sqlite3`（见 `data/README.md`）。连接参数：

| 参数 | 默认 | 环境变量 |
|---|---|---|
| journal_mode | `WAL` | `SQLITE_JOURNAL_MODE` |
| busy_timeout | 30000 ms | `SQLITE_BUSY_TIMEOUT_MS` |
| 异步形态 | asyncpg-shape (`fetch / fetchrow / fetchval / execute / executemany / transaction`) | — |

**绝不要自己 `sqlite3.connect(...)` 或在测试里写真实数据库**。统一入口：

```python
from akshare_mcp.storage import get_db, close_db, await_with_db_cleanup, run_with_db_cleanup
db = get_db()                       # SQLiteAdapter，按 event-loop / 线程隔离
await db.fetch(sql, *args)
await db.execute(sql, *args)
async with db.transaction(): ...
```

`SQLiteAdapter` 是多 Mixin 组合（`storage/sqlite/__init__.py`）：

```
SQLiteAdapter = KlineMixin + StockInfoMixin + FinancialsMixin + QuotesMixin
              + MarketContextMixin + VectorUnifiedMixin + ArtifactMixin
              + StrategyMixin + FactorStorageMixin + SignalTrackingMixin
              + SchemaBase
```

每个 Mixin 的 SQL 都被 `_prepare_sql / _split_sql / _strip_unsupported_blocks` 在执行前转换：

- PostgreSQL 类型 / 强制转换（`::jsonb`、`::vector(...)`、`TIMESTAMP WITH TIME ZONE`）→ SQLite 等价
- `$N` 参数占位符 → SQLite `?`
- `IN ($1)` 列表参数 → 展开为多 `?`
- `jsonb_array_length / jsonb_typeof / GREATEST / ILIKE / NULLS FIRST` 等 PG 方言被改写
- `DO $$ ... END $$;` / `CREATE EXTENSION` / pgvector GIN/HNSW 索引语句被剥离

### 5.2 已知反模式（炸过线上）

`docs/strategy-factory/策略工厂跑偏修复方案.md` 记录的真实 bug：`storage/sqlite/stock_info.py:220` 调 `payload.get('list_date').strftime(...)`，但 SQLite 反序列化是字符串，`'2010-08-19'.strftime(...)` 直接 `AttributeError`，外层两层 `except Exception:` 又把它静默吞掉，导致 `list_stock_universe()` 返回空，`list_stock_universe.loaded_stock_count = 0`，BULK 矩阵任务退化到 7 个 scan 任务跑通用回测。

写新 SQL 的强制流程：

1. 在 SQLite 实地跑通才能合并；不要假设字段类型与 PG 相同。
2. 异常一律带 `exc_info=True` 上报，**禁止**裸 `except Exception: pass`。
3. 涉及日期 / JSON 列时，先用 `_prepare_sql` 跑一遍核对生成的 SQLite 语句。

### 5.3 主要表分组（来自 `storage/sqlite/_schema_market_phase_*.py` + `schema_strategy_parts/`）

| 主题 | 代表表 | 入口 |
|---|---|---|
| 行情 | `kline_1d`, `quotes_minute_*`, `trading_dates`, `stocks` | `_schema_market_phase_1.py` |
| 财务 | `financials`, `financials_indicators`, `financials_forecast` | `_schema_market_phase_1.py` |
| 资金流 | `fund_flow_north`, `fund_flow_sector`, `fund_flow_market` | `_schema_market_phase_2.py` |
| 回测 | `backtest_results`, `backtest_trades`, `backtest_equity` | `_schema_market_phase_3.py` |
| 告警 / 事件 | `alerts`, `price_alerts`, `combo_alerts`, `indicator_alerts`, `alert_events`, `order_events`, `events` | `_schema_market_phase_3.py` |
| 自选股 | `watchlist`, `watchlist_groups` | `_schema_market_phase_3.py` |
| 龙虎榜 / 大宗 | `dragon_tiger`, `block_trades`, `research_reports` | `_schema_market_phase_4.py` |
| 模拟交易 | `paper_orders`, `paper_nav`, `strategy_artifacts` | `_schema_market_phase_4.py` |
| 因子持久化 | `factor_values`, `factor_ic_history` | `_schema_market_phase_4.py` |
| 用户画像 / 审计 | `user_profile_snapshots`, `recommendation_audit_log` | `_schema_market_phase_4.py` |
| 候选 / 信号证据 | `strategy_candidate_evidence`, `strategy_signal_evidence` | `_schema_market_phase_5.py` |
| 持仓 | `strategy_trade_positions`, `strategy_trade_position_fills` | `_schema_market_phase_5.py` |
| 信号 | `strategy_signals`, `strategy_signal_event_snapshots` | `_schema_market_phase_7.py` |
| 策略主体 | `strategies`, `strategy_runs`, `strategy_artifacts`, `strategy_recompile_*` | `schema_strategy_parts/` |
| 孵化生命周期 | `strategy_incubation_*`, `strategy_lifecycle_state` | `schema_strategy_parts/` |
| 数据质量 / 同步 | `data_quality_issues`, `sync_tasks`, `sync_schedules` | `_schema_market_phase_3.py` |

策略工厂还另外维护 `data/db/strategy_factory_task_board.sqlite3`（独立任务板，由 `strategy_factory.application.factory_task_board.FactoryTaskBoard` 拥有），路径走 `STRATEGY_FACTORY_TASK_BOARD_PATH`。

### 5.4 向量平台（多后端、统一画像）

向量层是**独立子系统**，由 `services/vector_platform.py` 与 `services/vector_search.py` 提供：

```
StrategyVectorPlatform (vector_platform.py)
  ├── VectorSearchEngine            (vector_search.py)
  │     backend: index / numpy fallback
  ├── StrategyTextEmbeddingService  (text_embedding.py)
  │     provider: openai_compat / ollama / hash_fallback (本地兜底)
  ├── _StrategyVectorPlatformBackendMixin   后端选择
  ├── _StrategyVectorPlatformProfilesMixin  画像写入
  ├── _StrategyVectorPlatformIndexesMixin   索引快照
  └── _StrategyVectorPlatformSearchMixin    ANN-like 检索
```

后端选择由 `STRATEGY_VECTOR_BACKEND` 决定，生产线标识 `PRODUCTION_BACKEND_STANDARD = "sqlite_python_with_observable_fallback"`。允许通过 `STRATEGY_VECTOR_ALLOW_FALLBACK=0` 关闭兜底。

**统一向量层 Schema**（`storage/sqlite/schema_vector.py` + `storage/sqlite/vector_unified.py`）：

| 表 | 角色 |
|---|---|
| `vector_collections` | 集合声明（entity_family, model_id, vector_dim, metric, status, active_version） |
| `vector_dimension_contracts` | 维度契约（profile_type × model_id × version_prefix → vector_dim, metric） |
| `vector_profiles` | 画像（embedding_json, signature, metadata），按 (collection, entity, model, version) 唯一 |
| `vector_index_snapshots` | 索引快照（status: building / active / archived，bucket_count，metrics） |
| `vector_index_items` | 索引条目（profile_id, bucket_id, coarse_score, embedding_json） |
| `market_documents` | 市场文档语料（doc_type / source / 文本 / 时点） |
| `stock_embeddings` / `pattern_vectors` / `vector_documents` | 旧版兼容表（仍在使用） |

> 维度违规（dim 不一致 / model_id 不匹配）会在 `vector_dimension_contracts` 校验阶段拒绝，跑 `make remediate-market-doc-embedding-dimensions` 能批量修复（脚本在 `packages/akshare-mcp/scripts/`）。

### 5.5 嵌入提供商三档

定义在 `services/text_embedding.py`：

| Provider | 触发 | 备注 |
|---|---|---|
| `openai_compat` | `STRATEGY_EMBEDDING_PROVIDER=openai_compat` + `STRATEGY_EMBEDDING_BASE_URL` + `STRATEGY_EMBEDDING_API_KEY` | 默认 `text-embedding-3-small` |
| `ollama` | `STRATEGY_EMBEDDING_PROVIDER=ollama` | 走本地 ollama embeddings API |
| `hash_fallback` | `STRATEGY_EMBEDDING_PROVIDER=hash_fallback`（默认） | 纯本地散列向量，**只用于离线开发** |

`STRATEGY_EMBEDDING_ALLOW_HASH_FALLBACK=0` 可禁用兜底；`STARTUP_EMBEDDING_CHECK_ENABLED=1` 启用启动期实测嵌入。

### 5.6 数据同步链路

> **数据源原则（2026 重构后）**：所有数据获取**首选本地通达信 vipdoc**，按以下顺序降级：
>   1. SQLite 本地（DB-first）
>   2. 本地 TDX vipdoc（mootdx Reader / struct 解析） ← `data_source/tdx_local.py`
>   3. 在线 TDX 行情服务器（pytdx 多 IP 故障切换）
>   4. Tushare Pro / AKShare / Baostock / eFinance（仅在 `TDX_LOCAL_ONLY!=1` 时启用）
>
> 切换开关在 `.env`：`TDX_LOCAL_ONLY=1` 关掉所有网络降级；`TDX_INSTALL_DIR` 指向通达信安装根（含 `vipdoc/`）。

```
本地 TDX vipdoc     (data/db/akshare_mcp.sqlite3 之外的二进制源)
       │
       ▼
TdxLocalSource (data_source/tdx_local.py)
       │   mootdx.Reader / pytdx.TdxHq_API
       ▼
DataSourceManager (data_source/__init__.py)  ← 单例 data_source
       │
       ├─→ get_kline()               本地 SQLite → TDX 本地 → TDX 在线 → ……
       ├─→ get_realtime_quote()      TDX 快照/在线行情 → ……
       ├─→ get_trading_dates()       TDX 上证日线反推 → ……
       ▼
所有 tools / services / strategy_factory（零改动消费方）
```

> **冷启动同步**：`python scripts/db_sync_tdx.py --all` 一键把通达信本地 vipdoc 灌入 SQLite，
> 全程不依赖外部网络。原 `scripts/db_sync.py`（Tushare Pro 驱动）保留作为可选回灌路径。

```
Tushare / AKShare / eFinance / Baostock     (data_source/，仅在 TDX_LOCAL_ONLY!=1 时启用)
        │
        ▼
DataSyncService (services/data_sync.py)        异步队列 + 死信
        │   写入 data/db/akshare_mcp.sqlite3
        ▼
DataSyncScheduler (services/data_sync_scheduler.py)  启动时 + 每日 15:30
        │
        ▼
data_sync_manager (tools/managers/data_sync_manager.py)
        │
        ▼
scripts/db_sync.py --full|--incremental|--type kline|north_fund|margin|financial
```

死信落 `packages/akshare-mcp/cache/dead_letters/`（在 .gitignore），**不要**提交。

`data_source/` 自己实现源切换（Tushare → eFinance → Baostock），`tushare_whitelist.py` 控制 Tushare Pro 接口白名单。


---

## 6. 策略工厂（Strategy Factory · 深度）

策略工厂是这个仓库中**最复杂的子系统**，物理上跨两个 package：

| 包 | 角色 |
|---|---|
| `packages/strategy-factory` | 编排骨架（domain / application / api / infrastructure）— "怎么跑" |
| `packages/akshare-mcp/services/strategy_factory/` | 与领域服务深度耦合的实现端 — "跑出来什么" |

### 6.1 调度入口与运行模式

`StrategyFactoryScheduler`（`strategy_factory/application/factory_scheduler.py`）支持两种调度模式：

| 模式 | env | 行为 |
|---|---|---|
| `continuous` | `STRATEGY_FACTORY_SCHEDULE_MODE=continuous`（默认） | 24/7 循环，市场时段间隔 `FACTORY_MARKET_HOURS_INTERVAL_SEC`，盘后 `FACTORY_OFF_HOURS_INTERVAL_SEC` |
| `daily` | `STRATEGY_FACTORY_SCHEDULE_MODE=daily` | 每日 `FACTORY_DAILY_RUN_TIME` 触发，最多 `FACTORY_MAX_DAILY_RUNS` 次 |

调度器实现：

- 由三个 Mixin 拼装：`_StrategyFactorySchedulerAnalysisMixin / _RuntimeMixin / _LoopMixin`
- 内置**断路器**：连续失败 ≥ `STRATEGY_FACTORY_MAX_CONSECUTIVE_FAILURES`（默认 5）切到 `open`，回退 `STRATEGY_FACTORY_CIRCUIT_OPEN_BACKOFF_SEC`（1800s），然后 half-open 探测
- 内置**交易日历**（`domain/trading_calendar.py`）；非交易日 / 收盘后会切到 `off_hours_interval`
- 内置 **dispatch run**：`factory_dispatch_run` 接 token 异步触发，可被同步 `factory_dispatch_status` 查询
- 维护 `_family_gate_feedback`（指数平滑 α=0.3，`P2-D 孵化反馈`）按 family 跟踪 Gate 通过率

调用入口：

| 路径 | 怎么用 |
|---|---|
| **Python API** | `from strategy_factory import get_strategy_factory_scheduler; sched = get_strategy_factory_scheduler(); await sched.start()` |
| **MCP / Agent** | `strategy_manager(action="factory_run_once" \| "factory_dispatch_run" \| "factory_status" \| "factory_runs" \| "factory_run_detail")` |
| **常驻脚本** | `python run_strategy_factory.py [--once] [--interval N] [--codes ...]` |

### 6.2 单次周期（FactoryCycleRunner）

`application/cycle_runner.py` 是**单次产线**，主类 `FactoryCycleRunner` 用 `_fragment_loader.exec_block` 把 `cycle_runner_parts/normalizers.py` 拼进去。每个 run 经过的阶段（按顺序）：

```
readiness        ReadinessService (services/readiness_service.py)
                 - 完成度 / 最低分阈值，FACTORY_READINESS_HARD_BLOCK 控制软硬阻塞
collect          DataCollector              （行情 / 资金流 / 财务）
warmup           runtime_warmup_runner      （特征预热）
factor_research  FactorResearchBuilder       (research/factor_research.py)
research_plane   ResearchPlaneRunner         (research/runner.py)
spawn            StrategySpawner             (research/spawner.py)
                 + StockStrategyMatrixPlanner (research/matrix.py)  ← BULK 模式
candidate_pipe   CandidatePipeline           (services/candidate_pipeline.py)
quality_gates    Pre-Gate → Gate-A → Gate-B → Gate-C
backtest_filter  BacktestFilter              (backtest_filter.py)
deduplicator     Deduplicator                (deduplicator.py)
submission_gate  run_submission_quality_gate (submission_gate.py)
submitter        StrategySubmitter           (submitter.py)
                 → 写孵化 + 触发 incubation_budgeter
governance       build_governance_plane_artifact
```

每个 `Stage` 产出 `StageStatus` + 计时 + 错误聚合，最终 `FactoryRunResult` 里有：

```
run_id, trace_id, status (succeeded|partial|failed),
stages: { stage_name: { status, elapsed_seconds, ... } },
artifacts: { ... },
parity_role: primary,
engine_version: FACTORY_ENGINE_VERSION,
read_only: bool
```

### 6.3 三档准入阈值（重点）

`packages/strategy-factory/src/strategy_factory/domain/constants.py` 定义三档：

| 档位 | 用途 | post_cost_sharpe_min | trade_count_min | mdd_max | walk_forward_ic_ir_min | DSR_min | PBO_max | committee_score_min |
|---|---|---|---|---|---|---|---|---|
| `RESEARCH_ADMISSION_THRESHOLDS` | 研究通过 | 0.05 | 3 | 0.50 | 0.20 | -0.10 | 0.75 | 0.0 |
| `INCUBATION_ADMISSION_THRESHOLDS` | 进孵化 | 0.10 | 4 | 0.45 | 0.30 | 0.0 | 0.60 | 0.58 |
| `LIVE_ADMISSION_THRESHOLDS` | 实盘可用 | 0.35 | 8 | 0.25 | 0.45 | 0.10 | 0.35 | 0.70 |

事件类策略 `event_trade_validation` 还有更严格的 `event_window_hit_ratio_min` / `post_event_decay_min` / `trade_density_max`。

`QUALITY_GATE_THRESHOLDS = dict(INCUBATION_ADMISSION_THRESHOLDS["statistical_validation"])`（保持向后兼容），但**新代码应该按"档位"显式选择**，不要再读 `QUALITY_GATE_THRESHOLDS`。

### 6.4 BULK 矩阵（每股专属策略）

事件驱动 / 因子覆盖式生产模式。控制开关：

```
STRATEGY_FACTORY_BULK_STOCK_MATRIX_ENABLED=true           # 默认 false
STRATEGY_FACTORY_BULK_STOCK_MATRIX_UNIVERSE_LIMIT=5000
STRATEGY_FACTORY_BULK_STOCK_MATRIX_FAMILIES_PER_STOCK=3
STRATEGY_FACTORY_BULK_STOCK_MATRIX_MAX_TASKS_PER_RUN=15000
STRATEGY_FACTORY_BULK_STOCK_MATRIX_MAX_CANDIDATES_PER_RUN=15000
STRATEGY_FACTORY_BULK_STOCK_MATRIX_GENERATION_LIMIT_PER_TASK=1
STRATEGY_FACTORY_BULK_BATCH_SIZE=100
STRATEGY_FACTORY_BULK_CONCURRENCY=20
STRATEGY_FACTORY_BULK_STOCK_MATRIX_TASKS_PER_SHARD=24
```

落地在 `application/research/matrix.py` 的 `StockStrategyMatrixPlanner.plan()`。调度器决定走 BULK 还是 scan，由调度元数据 + readiness 综合决定（不是单纯 flag）。

### 6.5 facade 边界（极重要）

**其他包想用策略工厂，只能从 `strategy_factory` 包顶层引用**，不能直接 import `application/...`：

```python
# ✅ 正确
from strategy_factory import (
    get_strategy_factory_scheduler,
    StrategySpawner,
    BacktestFilter,
    StrategySubmitter,
    run_submission_quality_gate,
    build_strategy_panels,
    get_factory_constants,
    QUALITY_GATE_THRESHOLDS,
)

# ❌ 错误
from strategy_factory.application.submitter import StrategySubmitter
```

`api/facade.py` 的 `_LAZY_EXPORTS` / `_FACADE_EXPORTS` 是稳定符号清单。新增能力时要么扩这两份清单，要么走 `api/contracts.py` 里的 Gateway Protocol：

```
VectorSearchGateway, ValidationGateway, RiskGateway,
IncubationGateway, AutonomyGateway, FactorResearchGateway
```

`infrastructure/mcp_adapters.py` 的 `MCPRuntimeAdapters` 把 Gateway 落到具体 MCP / akshare-mcp 实现。

### 6.6 任务板（独立 SQLite）

`application/factory_task_board.py:FactoryTaskBoard` 写入 `data/db/strategy_factory_task_board.sqlite3`，跟踪每个 spawn 任务的 lineage / family / 候选数量 / 各 Gate 命中。前端通过 `factory_runs / factory_run_detail` 读这张板子。


---

## 7. 因子挖掘工厂（Factor Mining Factory · 深度）

第三大并行引擎，源码在 `packages/akshare-mcp/src/akshare_mcp/services/factor_mining_factory/`。设计来自 `docs/factor-mining/因子挖掘工厂设计方案.md`（综合 Chain-of-Alpha 双链、Hubble AST 沙箱、AlphaAgent 抗衰减、CogAlpha 多 Agent 进化）。

### 7.1 单例与对外接口

```python
from akshare_mcp.services.factor_mining_factory import get_factor_mining_factory
factory = get_factor_mining_factory()      # FactorMiningFactory 单例

await factory.run_mining_cycle(
    trigger="scheduled" | "manual" | "decay_response" | "weekly_deep_search",
    engines=None | ["llm_primary", "gp_classic", "mcts_guided", "rl_alphagen", "rule_seed"],
    candidate_count=30,
    evolution_generations=5,
    codes=None | ["600519", ...],
)

await factory.run_maintenance()   # 衰减检测 + 自动退役
factory.status()                   # {initialized, run_count, last_run_at, pool_size, engines: {...}}
```

延迟初始化的子模块（`factory.py:_ensure_initialized`）：

```
EngineScheduler          engines/engine_scheduler.py   多引擎并行搜索调度
EvolutionaryOptimizer    evolution/optimizer.py        变异 / 交叉 / 选择
ActiveFactorPool         pool/active_pool.py           入池 / 退役 / 大小
DecayMonitor             feedback/decay_monitor.py     衰减检测 + alerts
FactorMetaLearner        feedback/meta_learner.py      经验注入
```

### 7.2 多引擎并行搜索

`engines/`：

| 引擎 | 文件 | 角色 |
|---|---|---|
| `llm_primary` | `llm_engine.py` | 由 LLM 生成因子表达式（受控 prompt + 结构化输出） |
| `gp_classic` | `gp_engine.py` | 遗传编程 |
| `mcts_guided` | `mcts_engine.py` | 蒙特卡洛树搜索 |
| `rl_alphagen` | `rl_engine.py` | RL 风格搜索引擎（本地受控实现，可选） |
| `rule_seed` | `rule_engine.py` | 经典规则种子（动量 / 估值 / 质量 ...） |

每个引擎实现 `engines/base.py` 的 `BaseFactorEngine`：

```python
class BaseFactorEngine:
    name: str
    async def search(self, *, context: MiningContext, candidate_count: int) -> list[FactorCandidate]: ...
    def health(self) -> dict: ...
```

`EngineScheduler.search` 并行调度，单引擎失败不影响整体。

### 7.3 沙箱与执行

`sandbox/` 是因子表达式的 AST 编译器：

```
dsl.py            因子 DSL 定义（运算符 / 字段 / 时间窗口）
compiler.py       AST → Python 闭包，受限算子白名单
feature_frame.py  统一的特征矩阵接口（pandas-backed）
evaluator.py      在 feature_frame 上评估 + 标准化
```

LLM 生成的表达式 **必须** 经过 `compiler.py` 编译，未通过白名单的算子会被拒。

### 7.4 进化优化

`evolution/optimizer.py:EvolutionaryOptimizer` 跑指定代数：

- 群体规模由 `candidate_count` 控制
- 每代：评估 → 排名 → 交叉 → 变异 → 精英保留
- 默认代数 5；`weekly_deep_search` 跑 10

### 7.5 验证流水线

复用 `services/factor_validation_pipeline.py` + `services/factor_validation_bootstrap.py`：

- IC / IR / Rank IC（多窗口）
- Walk-Forward 检验
- DSR (Deflated Sharpe Ratio) / PBO
- 经济解释性 (`validation/economic_sense.py`)

### 7.6 因子池管理

`pool/`：

| 文件 | 角色 |
|---|---|
| `active_pool.py` | 活跃池（入池 / 退役 / 大小限制） |
| `decay_tracker.py` | 单因子衰减时序追踪 |
| `orthogonalizer.py` | 正交化（避免高度相关因子并存） |
| `portfolio_optimizer.py` | 组合层面的因子配权 |
| `storage.py` | SQLite 持久化（写入 `factor_values` / `factor_ic_history`） |

### 7.7 反馈闭环

`feedback/`：

| 文件 | 角色 |
|---|---|
| `decay_monitor.py` | 衰减告警（severity ∈ low/medium/high/critical） |
| `knowledge_graph.py` | 因子知识图谱（同族 / 父子 / 互斥关系） |
| `meta_learner.py` | 经验提取，喂给下一轮 LLM prompt |
| `performance_writer.py` | 接收策略侧因子表现反馈，写入因子反馈事件并触发衰减/补挖信号 |

### 7.8 调度（常驻进程）

`run_factor_mining_factory.py` 是顶层运行器，四种模式：

| 模式 | 触发 | 行为 |
|---|---|---|
| `schedule`（默认） | — | 每日 18:30 挖掘 + 每日 06:00 维护 + 周日 02:00 深度搜索 |
| `interval` | `--interval N` | 固定 N 秒一次 |
| `once` | `--once` | 单次挖掘 |
| `maintenance` | `--maintenance` | 单次维护，衰减 ≥ 3 时自动触发补充搜索 |

环境变量：`FACTOR_MINING_FACTORY_ENABLED=1`、`FACTOR_LLM_*`（同 `STRATEGY_LLM_*` 命名规范）。

---

## 8. 孵化工厂（Incubation Factory · 深度）

物理位置 `packages/akshare-mcp/src/akshare_mcp/services/incubation_factory/`。它**不是策略工厂的子流程**，是独立运行体，负责"模拟盘验证 → 推进阶段 → 反馈给策略工厂"的闭环。设计文件 `docs/incubation-factory/孵化工厂-独立运行方案.md`。

### 8.1 主类与子模块

`IncubationFactoryRunner`（`runner.py`）：

```python
runner = IncubationFactoryRunner(run_time=time(18,30), dry_run=False, auto_apply_review=True)
await runner.run_once()      # 单次完整孵化周期
await runner.run_daemon()    # 守护：每日 18:30
```

子模块（实测自 `__init__` 与 `run_once` 阶段）：

| 子模块 | 文件 | 职责 |
|---|---|---|
| `IncubationIntake` | `intake.py` | 自动接纳策略工厂提交的新策略（`scan_and_accept`） |
| `SignalGenerator` | `signal_generator.py` | 给孵化中策略生成最新信号 |
| `ForwardVerifier` | `forward_verifier.py` | **前向收益验证**（孵化期内的真实持仓推进） |
| `MetricsRecorder` | `metrics_recorder.py` | 把每次验证写到 SQLite（`strategy_incubation_*`） |
| `HitRateReporter` | `hit_rate_reporter.py` | 命中率报告（按 stage / family / horizon） |
| `FeedbackWriter` | `feedback_writer.py` | 把命中率反馈到策略工厂可消费的表 |
| `IncubationAccelerator` | `accelerator.py` | 表现极好的策略加速推进 |
| `AlertMonitor` | `alert_monitor.py` | 异常告警（验证失败率超阈值 / 信号生成失败） |

每次 `run_once` 跑 9 个 phase（信号生成 / 验证 / 指标 / 流水线评估 / 命中率 / 反馈 / 加速 / 告警 / 心跳），每条策略 30s 超时，整批 600s 超时。

### 8.2 与生命周期表的耦合

孵化的策略状态由 `services/strategy_lifecycle_shared/state_machine.py` 管理：

```
research → incubation_warmup → incubation_observe → incubation_graduate → live | deprecated
```

`forward_verifier` 写 `strategy_incubation_metrics`、`strategy_incubation_phase`，`promotion_pipeline.py` 在毕业时把策略状态推到 `live`。

### 8.3 触发方式

| 触发 | 命令 |
|---|---|
| 守护进程 | `cd packages/akshare-mcp && make incubation-factory-daemon` |
| 单次 | `make incubation-factory` |
| 状态 | `make incubation-factory-status` |
| Dry-run | `make incubation-factory-dry-run` |
| MCP / Agent | `strategy_manager(action="incubation_pipeline_run")` 等 |


---

## 9. Agent HTTP API（实测路由表）

`packages/agent/src/aiask_agent/server.py:create_app()` 注册的全部路由。所有路由都至少要 `require_api(request)`（API token），标 🔒 的还要 `require_full(request)`（hermes_full 三件套）。

### 9.1 健康 / 能力 / 状态

| 路由 | 用途 |
|---|---|
| `GET /health` | 简单存活 |
| `GET /health/detailed` | 含 parity / hermes / readiness 摘要 |
| `GET /v1/capabilities/parity` | Hermes 对等矩阵（不依赖 vendor） |
| `GET /v1/hermes/status` | full_mode_enabled / full_mode_active / parity / 工具数 |
| `GET /v1/hermes/readiness` | 各能力 readiness |
| `GET /v1/financial-system/readiness` | 金融系统就绪度（数据库 / 索引 / readiness 子项） |
| `GET /v1/hermes/toolsets` | 当前 toolset 与可切换列表 |
| `GET /v1/hermes/tools` 🔒 | full 工具列表 |
| `GET /v1/hermes/config` 🔒 | full 配置摘要 |
| `GET /v1/hermes/sessions` 🔒 | 会话列表 |

### 9.2 模型对话

| 路由 | 用途 |
|---|---|
| `POST /v1/responses` | OpenAI Responses API 兼容（推荐） |
| `POST /v1/chat/completions` | OpenAI Chat 兼容 |
| `GET /v1/responses/{response_id}` | 拉取已存响应 |
| `DELETE /v1/responses/{response_id}` | 删除会话响应 |
| `GET /v1/runs/{run_id}` | 拉取 run 元数据 |
| `GET /v1/runs/{run_id}/events` | SSE 流式事件 |
| `GET /v1/runs/{run_id}/events/stream` | 同上别名 |
| `POST /v1/runs/{run_id}/cancel` | 取消 |
| `POST /v1/runs/{run_id}/stop` | 同 cancel |
| `POST /v1/runs/{run_id}/steer` | 中途注入指令 |
| `GET /v1/sessions/{session_id}/messages` | 历史消息 |
| `GET /v1/search?query=...` | 跨会话语义搜索 |

### 9.3 工具调用 / 桌面专用

| 路由 | 用途 |
|---|---|
| `GET /v1/tools` | 当前 toolset 工具表 |
| `POST /v1/tools/{tool_name}` | **只允许 read-only 工具**直接调用（按 `metadata_is_read_only` 校验） |
| `POST /v1/hermes/admin/tools/{tool_name}` 🔒 | full 工具直接调用 |
| `GET /v1/desktop/capabilities` | 桌面端聚合面板（含 parity / readiness / connectors / skills / quant） |
| `GET /v1/desktop/quant/presets` | 量化预设 |
| `POST /v1/desktop/quant/research-runs` | 提交研究 |
| `GET /v1/desktop/quant/research-runs/{id}` / `/report` | 拉研究 / 报告 |
| `GET /v1/ai/status` / `POST /v1/ai/smoke` / `GET /v1/ai/models` | LLM 配置自检 |

### 9.4 控制面（写入 / 高危）

控制面路由要 **loopback IP + Bearer == `AIASK_AGENT_CONTROL_TOKEN`**：

| 路由 | 用途 |
|---|---|
| `GET /intents/{intent_id}` | 拉取意图 |
| `POST /intents/{intent_id}/confirm` | 确认（控制 token） |
| `POST /intents/{intent_id}/deny` | 拒绝 |
| `POST /v1/mcp/register-local` | 注册本地 MCP Server |
| `POST /v1/mcp/discover` / `oauth/start` / ... | MCP 管理 |
| `GET /v1/processes` 🔒 / `/v1/terminal/*` 🔒 | 进程 / 终端管理 |
| `GET /v1/skills` 🔒 / `/v1/plugins` 🔒 / `/v1/jobs` 🔒 / `/v1/webhooks` 🔒 | full 模式管理 |
| `GET /v1/gateway/{status,platforms,messages,directory}` 🔒 | 平台网关 |
| `GET /v1/learning/*` 🔒 / `/v1/rl/*` 🔒 | 学习 / RL |

### 9.5 必备环境变量（按角色分组）

```
# Agent HTTP
AIASK_AGENT_HOST=127.0.0.1
AIASK_AGENT_PORT=8767
AIASK_AGENT_CORS_ORIGINS=http://localhost:1420,http://127.0.0.1:1420
AIASK_AGENT_API_TOKEN=                  # 非 loopback 必填
AIASK_AGENT_CONTROL_TOKEN=change_me     # confirm/deny + 控制面必填
AIASK_AGENT_MODEL=gpt-4.1-mini
AIASK_AGENT_MAX_ITERATIONS=8
AIASK_AGENT_MODEL_TIMEOUT=120
AIASK_AGENT_TOOL_TIMEOUT=120

# Toolset 切换
AIASK_AGENT_TOOLSET=finance_safe        # 默认；full 改为 general_full
AIASK_AGENT_ENABLE_GENERAL_TOOLS=0
AIASK_AGENT_ENABLE_HERMES_FULL=0        # full 模式三件套之一

# MCP / ACP
AIASK_AGENT_MCP_CONFIG=~/.aiask-agent/mcp_servers.json
AIASK_AGENT_MCP_TOKEN_DIR=~/.aiask-agent/mcp-tokens
MCP_HOST=127.0.0.1
MCP_TRANSPORT=stdio                     # 或 sse / streamable-http
MCP_ALLOW_TOKEN_PASSTHROUGH=false

# 数据库
AKSHARE_MCP_SQLITE_PATH=./data/db/akshare_mcp.sqlite3
AIASK_SQLITE_PATH=./data/db/akshare_mcp.sqlite3
SQLITE_BUSY_TIMEOUT_MS=30000
SQLITE_JOURNAL_MODE=WAL

# 向量层
STRATEGY_VECTOR_BACKEND=                # 留空 → 自动选；可填 sqlite_python
STRATEGY_VECTOR_ALLOW_FALLBACK=1
STRATEGY_EMBEDDING_PROVIDER=hash_fallback
STRATEGY_EMBEDDING_BASE_URL=
STRATEGY_EMBEDDING_API_KEY=
STRATEGY_EMBEDDING_MODEL=text-embedding-3-small
STRATEGY_EMBEDDING_ALLOW_HASH_FALLBACK=1
STARTUP_EMBEDDING_CHECK_ENABLED=0

# 策略工厂
STRATEGY_FACTORY_SCHEDULE_MODE=continuous
STRATEGY_FACTORY_READINESS_HARD_BLOCK=0
STRATEGY_FACTORY_FACTOR_AUTO_REFRESH=1
STRATEGY_FACTORY_BULK_STOCK_MATRIX_ENABLED=false
STRATEGY_FACTORY_MAX_CONSECUTIVE_FAILURES=5
STRATEGY_FACTORY_CIRCUIT_OPEN_BACKOFF_SEC=1800
STRATEGY_LLM_ENABLED=1
STRATEGY_LLM_BASE_URL=...
STRATEGY_LLM_API_KEY=...
STRATEGY_LLM_MODEL=...

# 因子挖掘
FACTOR_MINING_FACTORY_ENABLED=1
FACTOR_LLM_BASE_URL=...
FACTOR_LLM_API_KEY=...
FACTOR_LLM_MODEL=...

# 启动 profile / 观测
AKSHARE_MCP_STARTUP_PROFILE=full        # 或 tool-only / worker
LOG_LEVEL=info
OTEL_ENABLED=true
OTEL_SERVICE_NAME=aiask-agent
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces
PROMETHEUS_PORT=9090
```

完整模板见 `.env.example`。

---

## 10. 意图确认（ActionIntentStore）

唯一允许执行写入级 `strategy_manager.*` 的路径。

### 10.1 数据 Schema（自带）

`packages/agent/src/aiask_agent/intents.py` 在 `~/.aiask-agent/intents.sqlite3`（路径来自 `paths.default_intent_db_path`）建表：

```sql
CREATE TABLE action_intents (
    intent_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,                -- 形如 "strategy_manager.factory_run_once"
    target_tool TEXT NOT NULL,           -- "strategy_manager"
    target_action TEXT NOT NULL,         -- "factory_run_once"
    params_json TEXT NOT NULL,
    status TEXT NOT NULL,                -- awaiting_confirmation / confirmed / denied / executing / succeeded / failed / expired
    user_id TEXT, rationale TEXT,
    result_json TEXT, error TEXT,
    created_at TEXT, updated_at TEXT, expires_at TEXT,
    confirmed_at TEXT, denied_at TEXT, executed_at TEXT
);
```

journal_mode WAL，busy_timeout 30s。

### 10.2 允许的 action 集合

`ALLOWED_ACTIONS` 由 `tool_risk.CONFIRM_REQUIRED_STRATEGY_ACTIONS` 派生，与策略契约一致：

```
strategy_manager.{create, publish, archive, update_metrics, subscribe, unsubscribe,
  fork_strategy, update_strategy, delete_personal_strategy, paper_session_get_or_create,
  review_report_recheck, submission_replay, submit, factory_run_once, factory_dispatch_run,
  execution_audit_acceptance, incubation_sync_run, incubation_pipeline_run,
  risk_scan_run, risk_recovery, resolve_risk_event, runtime_alert_dispatch_run,
  runtime_alert_ack, runtime_control_set, promotion_review_run, runtime_cycle_run,
  domain_projection_rebuild, vector_reconcile, vector_rebuild, vector_cleanup,
  ai_generate, ai_optimize_personal_strategy, factory_event_create, factory_event_update,
  factory_event_approve, factory_event_record_outcome}
```

试图对**不在表里的 action** 创建 intent 会抛 `ValueError`。

### 10.3 状态机

```
awaiting_confirmation ──confirm──▶ confirmed ──IntentExecutor──▶ executing
                       │                                          │
                       deny                                       ├── succeeded
                       ▼                                          └── failed
                     denied
TTL 默认 86400s，过期 → expired
```

`IntentTransition.transition` 强制 `expected_status` 校验，**禁止跳跃**。

### 10.4 怎么用（前后端模式）

```
1. 模型/前端调 agent_strategy_action 工具：
   { action: "submit", params: {...}, rationale: "..." }
2. Agent 创建 intent，返回 intent_id（status=awaiting_confirmation）
3. 用户在 Desktop 看到，点确认 → POST /intents/{id}/confirm（控制 token）
4. IntentExecutor 拿走 intent，调 strategy_factory_adapter.execute_confirmed_action
5. 状态推进到 executing → succeeded / failed，结果回写 result_json
```

**禁止**绕过 intent 直接在自由对话里执行写入级 strategy_manager action。控制面不接受非 loopback 调用。

---

## 11. Desktop 工作台

### 11.1 技术栈

```
React 18.3 + Vite 6 + TypeScript 5.7 + Tauri 2 (Rust 1.77.2+)
test: Vitest 4 + @testing-library/react + jsdom
e2e:  Playwright 1.59
```

### 11.2 与 Agent 的契约

Desktop **不直连 MCP / 不直调 strategy_manager**，全部走 Agent HTTP（见 §9）。`desktop/src/services/aiaskApi.ts` 是唯一封装：

```ts
class AiaskApi {
  health()            → GET /health/detailed
  tools()             → GET /v1/tools
  capabilities()      → GET /v1/desktop/capabilities    (control 或 api token)
  hermesStatus()      → GET /v1/hermes/status
  capabilityParity()  → GET /v1/capabilities/parity
  aiStatus / aiSmoke / aiModels
  response(body, token) → POST /v1/responses
  runEvents(runId)    → GET /v1/runs/:id/events  (SSE)
  readOnlyTool(name, body) → POST /v1/tools/:name
  quantPresets / quantResearchRun / quantResearchReport
  controlData<...>()  → /v1/hermes/tools, /v1/processes, /v1/browser/sessions,
                        /v1/skills, /v1/plugins, /v1/mcp/{servers,tools,resources,prompts,oauth_status},
                        /v1/webhooks, /v1/approvals, /v1/jobs,
                        /v1/gateway/{status,platforms,messages,directory},
                        /v1/terminal/{backends,sessions},
                        /v1/learning/{status,review}, /v1/rl/{environments,runs}
  mcpRegisterLocal / mcpDiscover / mcpResourceRead / mcpPromptGet / mcpOauthStart
}
```

### 11.3 模块划分（按业务而非技术）

```
desktop/src/features/
  ai-testing/        AI 模型自检（/v1/ai/*）
  capabilities/      Hermes 能力面板
  connectors/        数据源 / MCP / 平台连接器状态
  event-console/     事件驱动控制台
  factory/           策略工厂运行 / Top-N / 任务板
  incubation/        孵化工厂面板
  mcp/               MCP Server / Tool / Resource / Prompt 浏览
  quant/             量化研究 / 回测 / 报告
  settings/          配置（endpoint / token / toolset）
  skills/            技能包
desktop/src/components/
  AppSidebar / WorkbenchView / Timeline / DiagnosticsPanel / InspectorPanel*
desktop/src/hooks/
  useAgentWorkbench / useAiSmoke / useCapabilityWorkbench /
  useConnection / useHermesConsole
desktop/src-tauri/                    Rust 壳：tauri 2 + tauri-plugin-shell
```

### 11.4 启动

```bash
cd desktop && npm install
npm run dev          # vite 仅监听 127.0.0.1:1420
npm run tauri:dev    # 套壳完整桌面应用
npm run typecheck    # tsc --noEmit
npm run test         # vitest run src --environment jsdom
npm run test:e2e     # Playwright（默认 mock 后端）
```


---

## 12. 代码组织约定

### 12.1 DDD 分层（strategy-factory 是模板）

```
domain/          纯业务对象、常量、注册表。不 import application / infrastructure。
application/     编排、调度、流水线。可以 import domain，不可 import api。
infrastructure/  适配 MCP / SQLite / 外部 LLM。只被 application 反向依赖。
api/             facade.py 是唯一对外稳定符号；contracts.py 定义 Gateway Protocol。
```

**`akshare-mcp` 因体量更大，按角色分**：

```
tools/                MCP 工具层（@mcp.tool 装饰）
tools/managers/       聚合面（XX_manager.py），不能直暴露给 LLM
services/             领域服务实现（70+ 个）
storage/sqlite/       SQLite 持久化
data_source/          外部数据源切换
core/                 cache / rate_limiter / retry / vectorized_indicators
contracts/            跨模块契约（如 strategy_manager_contract.py）
```

### 12.2 文件切片：`*_parts/` + `_fragment_loader`

为了控制单文件大小，仓库引入了**碎片加载器**：

- `packages/strategy-factory/src/strategy_factory/_fragment_loader.py`
- `packages/akshare-mcp/src/akshare_mcp/_fragment_loader.py`

约定：

- 主文件 `foo.py` 用 `exec_block(globals(), 'foo_parts', header, ['x.py', 'y.py', ...])` 把碎片拼成一个命名空间。
- 碎片放在 `foo_parts/` 目录，**不能**作为独立模块被 `import`。
- 设置 `STRATEGY_FACTORY_FRAGMENT_CHECK=1` 可在加载时对碎片间符号重定义发出 warning。
- **绝不能**为了"清理"删掉 `*_parts/` 目录，那会直接破坏运行时。

例：`storage/sqlite/strategy_crud.py` 的实现分散在 `_strategy_crud_core.py` / `_strategy_crud_market.py` / `_strategy_crud_quality.py` / `_strategy_crud_utils.py`，由主文件加载。

### 12.3 命名规则

| 对象 | 规则 |
|---|---|
| 模块 / 函数 | `snake_case` |
| 类 | `PascalCase` |
| 常量 | `UPPER_SNAKE_CASE`（集中在 `domain/constants.py` / `services/.../constants.py`） |
| 内部辅助 | 文件 / 函数加 `_` 前缀（`_strategy_crud_core.py`、`_decision_buy.py`、`_factory_scheduler_loop.py`） |
| Mixin | 后缀 `Mixin`（`KlineMixin`、`_StrategyVectorPlatformBackendMixin`） |
| 测试文件 | `tests/test_<被测>.py` |

### 12.4 异步约定

- 顶层入口几乎全部 `async`（FastAPI / FastMCP / strategy_factory）。
- 同步阻塞调用（pandas、TA-Lib、akshare、`pytdx`）**必须** `asyncio.to_thread` 包裹，禁止直接放在 event loop 里。
- 长任务循环用 `_interruptible_sleep` / `recovery.retry_async` 响应 SIGINT / SIGTERM。
- 工具调用统一 `asyncio.wait_for(..., timeout=...)`，timeout 在 adapter 层注入：
  - Agent → strategy_manager: `AIASK_STRATEGY_FACTORY_TOOL_TIMEOUT` (默认 15s)
  - Agent → quant tool: `AIASK_QUANT_TOOL_TIMEOUT` (默认 30s)

### 12.5 类型与日志

- 全部源文件 `from __future__ import annotations`，函数签名带 type hints。
- 公开函数加 docstring；中文为主、术语保留英文。
- 错误处理**禁止**裸 `except Exception: pass`；至少 `logger.warning(..., exc_info=True)`。
- 日志 `logging.getLogger(__name__)`，不要用 `print`。

---

## 13. 数据契约与 PIT 一致性

### 13.1 工具返回 envelope（强约束）

所有 `agent_*` 与 MCP 工具返回必须满足：

```json
{
  "success": true|false,
  "data": <payload>,
  "error": null|string,
  "error_code": "OPTIONAL_MACHINE_CODE",
  "meta": {
    "trace_id": "aiask-agent:<tool>:<ts>:<8hex>",
    "source_chain": ["aiask_agent", ...],
    "side_effect": {
      "level": "read_only" | "stateful" | "trade_risk" | "confirm_required",
      "target": "tool_name_or_action",
      "confirmation_required": bool,
      "idempotent": bool
    },
    "toolset": "finance_safe" | "general_full",
    "tool": "...",
    "pit": {"as_of": "...", "pit_passed": bool},
    "pit_guard": {"active": bool, "filtered_rows": int}
  }
}
```

`tool_registry.aiask_envelope` / `ensure_aiask_envelope` 会自动补齐缺失字段。

### 13.2 Side-effect 分级

`packages/agent/src/aiask_agent/tool_risk.py`：

| level | 含义 | 默认行为 |
|---|---|---|
| `read_only` | 不写入、可重放 | 直接执行；可经 `POST /v1/tools/{name}` |
| `stateful` | 改写持久状态 | 走 ActionIntent 确认 |
| `trade_risk` | 涉及下单 / 撤单 / live trade | 必须 ActionIntent + 二次审批（finance_safe 默认拒） |
| `confirm_required` | 显式高风险（终端命令、文件 patch） | ApprovalStore 二次审批 |

`mcp_call_side_effect / classify_strategy_manager_action` 在 MCP 调用层会自动按工具名 + action 名推断分级。

### 13.3 PIT（Point-In-Time）

由 `services/pit_utils.py` + `tools/pit_middleware.py` 强制：

```python
from akshare_mcp.tools.pit_middleware import create_pit_context, build_pit_meta_simple

ctx = create_pit_context(as_of)
klines, pit_guard = ctx.filter_klines_by_as_of(klines)
result["meta"]["pit_guard"] = pit_guard
result["meta"]["time_precision"] = "historical_eod_close_as_of" if pit_guard["active"] else "historical_eod_close"
```

**所有研究 / 决策 / 回测 / 情绪工具必须带 `as_of`**。新工具加 `as_of` 参数到 `tools/schemas.py`。

### 13.4 contract test（不可绕过）

| 测试 | 守的契约 |
|---|---|
| `packages/akshare-mcp/tests/test_tool_argument_contract.py` | 所有 manager 接受 BFF 旧 kwargs 字符串 + 新 params dict |
| `packages/akshare-mcp/tests/test_strategy_market_incubation_surface.py` | 策略 / 孵化 surface 完整性 |
| `packages/akshare-mcp/tests/test_strategy_mgr_capabilities_health.py` | strategy_manager.capabilities / health |
| `packages/akshare-mcp/tests/test_strategy_dsl_semantic_contract.py` | DSL 语义 |
| `packages/akshare-mcp/tests/test_factor_validation_bootstrap.py` | 因子校验 |
| `packages/akshare-mcp/tests/test_tool_catalog_vector_contracts.py` | 向量层契约 |
| `packages/strategy-factory/tests/test_public_contracts.py` | facade 公共符号 |
| `packages/agent/tests/test_no_hermes_dependency.py` | vendor Hermes 不被 import |
| `packages/agent/tests/test_tool_registry.py` | `agent_*` 命名规则 |
| `packages/agent/tests/test_intents.py` | ActionIntent 状态机 |

---

## 14. 测试规范

### 14.1 框架与发现

```
pytest (>= 8) + pytest-asyncio (auto mode for finance-mcp-servers)
根 pytest.ini:        覆盖 packages/agent + packages/strategy-factory
akshare-mcp/pytest.ini 单独配置（pythonpath 含 strategy-factory/src）
agent/pytest.ini      含 akshare-mcp/src + strategy-factory/src 路径
```

不要在仓库根 `pytest packages/akshare-mcp/tests` —— 必须 `cd packages/akshare-mcp && pytest -q`。

### 14.2 用什么跑

```bash
# 顶层一键
make test            # = test-agent + test-finance + desktop vitest

# 分包
make test-agent
make test-finance
cd packages/akshare-mcp && pytest -q tests/test_<模块>.py
cd packages/strategy-factory && pytest -q
cd desktop && npm test
cd desktop && npm run test:e2e            # mock 模式
AIASK_DESKTOP_RUN_LIVE=1 npm run test:e2e:live   # 联通真实 Agent（需 Agent 在跑）
```

### 14.3 写测试的硬要求

- **不要联网**：`OPENAI_API_KEY` / `TUSHARE_TOKEN` 在测试里走 mock。
- **不要写真实 SQLite**：用 `tmp_path` + `AKSHARE_MCP_SQLITE_PATH=tmp_path/test.sqlite3`。
- 修 bug 至少加一个能复现旧 bug 的单测；改阈值要附"旧通过 / 新拒绝"对比。
- 新增公共契约（DTO / facade 符号 / 工具 schema）必须配套契约测试。
- 新增 strategy_manager action 必须同步 `STRATEGY_MANAGER_ACTIONS` 与契约测试。

### 14.4 Hermes / Native 边界测试

- `test_no_hermes_dependency.py` — 扫 `import hermes` / `from hermes`
- `test_hermes_reference_guardrails.py` — 防止 vendor 路径被 sys.path 注入
- `test_hermes_full_expanded_capabilities.py` — full 模式工具完整性
- `test_native_full_parity.py` — 对等矩阵完整性
- `test_hermes_native_live_adapters.py` — adapter 不依赖 vendor


---

## 15. 常用命令

### 15.1 顶层 Makefile

```bash
make bootstrap        # uv sync agent + npm install desktop
make test             # 全套测试（agent + finance 关键契约 + desktop vitest）
make test-agent       # pytest packages/agent/tests
make test-finance     # 策略 / 工具参数 / 孵化 surface 三组关键契约
make typecheck        # desktop tsc --noEmit
make build-desktop    # vite build + cargo check
make package-desktop  # tauri build
make smoke            # curl http://127.0.0.1:8767/health
```

### 15.2 三大工厂常驻进程

```bash
# 策略工厂
python run_strategy_factory.py                        # 默认 10s 间隔
python run_strategy_factory.py --once
python run_strategy_factory.py --interval 300 --codes 600519 000001

# 因子挖掘工厂（4 模式）
python run_factor_mining_factory.py                   # schedule（18:30 挖掘 / 06:00 维护 / 周日 02:00 深度）
python run_factor_mining_factory.py --once
python run_factor_mining_factory.py --maintenance
python run_factor_mining_factory.py --interval 7200
python run_factor_mining_factory.py --status
python run_factor_mining_factory.py --engines llm_primary gp_classic --candidates 50 --generations 8

# 孵化工厂（akshare-mcp 内置）
cd packages/akshare-mcp
make incubation-factory                # 单次
make incubation-factory-daemon         # 守护
make incubation-factory-status
make incubation-factory-dry-run
```

### 15.3 数据库 / 维护

```bash
python scripts/db_init.py                                  # 建 / 迁移所有表
python scripts/db_sync.py --full                           # 全量历史
python scripts/db_sync.py --incremental                    # 增量
python scripts/db_sync.py --type kline --codes 600519,000001
python scripts/db_sync.py --type north_fund
python scripts/db_sync.py --type margin
python scripts/db_sync.py --type financial
python scripts/backup_db.py                                # （在 packages/akshare-mcp/scripts/）
python scripts/check_db_status.py
python scripts/audit_data_quality.py
```

### 15.4 工具 / 治理脚本

```bash
# akshare-mcp 子目录
make tool-registry                     # 导出 MCP tool registry
make tool-description-audit            # 工具描述审计
python scripts/scan_tushare_permissions.py
python scripts/export_scenario_coverage.py
python scripts/remediate_market_doc_embedding_dimensions.py

# 仓库根
python scripts/skill_coverage_audit.py
python scripts/seed_strategy_factory_theme_graph.py
python scripts/run_theme_regression_backtest.py
python scripts/strategy-execution-audit-acceptance.py <report.json>
python scripts/strategy-incubation-history-replay.py <report.json> --sample-gap-only
python scripts/backfill_classic_factor_ic.py
```

### 15.5 MCP / Agent / Desktop

```bash
# AKShare MCP（stdio）
python -X utf8 packages/akshare-mcp/start_server.py
AKSHARE_MCP_STARTUP_PROFILE=tool-only python -X utf8 packages/akshare-mcp/start_server.py
MCP_TRANSPORT=streamable-http python -X utf8 packages/akshare-mcp/start_server.py

# AIASK Agent
cd packages/agent && uv run aiask-agent       # 安装后 entry point
# 或： python -m aiask_agent.server

# Finance MCP（按需）
python -m aiask_finance_mcp.eastmoney.server       # 行情，公开
python -m aiask_finance_mcp.tongdaxin.server       # 行情 + 下单
python -m aiask_finance_mcp.qmt.server             # 需 QMT 客户端
python -m aiask_finance_mcp.tonghuashun.server     # 需 Windows + easytrader

# Desktop
cd desktop && npm run dev
cd desktop && npm run tauri:dev
```

---

## 16. Git 与 PR

- **不要直推 `main` / `master`**，新分支前缀 `feature/*`、`fix/*`、`docs/*`、`refactor/*`、`audit/*`。
- 提交信息：标题 ≤ 70 字，正文写"做了什么 / 为什么 / 怎么验证"，链接到对应方案文档。
- 任何会改变行为的 PR 必须：
  1. 跑过相关 `make test-agent` / `make test-finance` / pytest 子集（贴日志）。
  2. 更新对应方案 / 审计文档（`docs/<主题>/` 或顶层 `*.md`）。
  3. 不引入未注册的工具名 / 未声明的环境变量 / 未在契约中登记的 manager action。
  4. 涉及 SQL 时附"在 SQLite 实地跑通"的截图或日志。
- 严禁提交：
  - `.env`、`*.sqlite3`、`*.log`、`__pycache__/`、`*.pyc`、`*.cpython-*.pyc`
  - `packages/akshare-mcp/cache/dead_letters/`、`reports/*.html` 之外的临时产物
  - `vendor/hermes-agent-upstream/` 之外的 vendor 内容
  - 任何看起来像 `sk-...` / `pat_...` / 真实 token 的字符串

`.gitignore` 已经覆盖以上全部，不要 `git add -f` 强加。

---

## 17. AI 编码代理（Claude / Codex / Cursor / Kiro）使用守则

针对自动编程代理在本仓库工作时的硬规则：

1. **先读代码再写**。任何改动前先 `read_file` / `grep_search`，不要根据文件名或上一次对话的记忆臆测——本仓库存在大量"文件名相同但实现已迁移"的历史。
2. **遵守 `agent_*` 命名 + forbidden token**。新工具必须 `agent_` 前缀；不得包含 §2.4 的 6 个 forbidden token。新工具同时改三处：`tools/catalog.py`、`tools/schemas.py`、`tool_registry.py`。
3. **写入级 strategy_manager action 走 ActionIntent**。新增高风险 action 时，同步 `STRATEGY_MANAGER_CONFIRM_REQUIRED_ACTIONS`、`STRATEGY_MANAGER_ACTION_SIDE_EFFECTS`、`tool_risk.CONFIRM_REQUIRED_STRATEGY_ACTIONS`。
4. **改 SQL 前在 SQLite 上验证**。本仓库主库是 SQLite，PG 风格的 SQL（`RETURNING`、`::jsonb`、自动 `datetime` 反序列化）会静默炸掉。涉及日期 / JSON 字段尤其小心。
5. **优先动 facade，不动 internal**。引用 `strategy_factory` 只用 `from strategy_factory import ...`；扩能力请加在 `api/facade.py` 的 `_LAZY_EXPORTS` / `_FACADE_EXPORTS`。
6. **不要碰 `*_parts/` 下的文件名 / 顺序**。它们由 `_fragment_loader.exec_block` 显式拼装，删除或重排即破坏运行时。
7. **不要 import `vendor/hermes-agent-upstream/`**。`test_no_hermes_dependency.py` 会立刻拒掉。
8. **路径用相对仓库根的绝对路径**。所有脚本默认 cwd 是仓库根，靠 `sys.path.insert(0, "packages/.../src")` 接入；不要把 `cwd` 当成包内目录。
9. **失败两次就停下来**。同种修改连续两次失败（典型例子：反复同 SQL / 同 import path），立即换思路或回报根因，禁止继续打补丁——尤其禁止用 `except Exception: pass` 把错误吞掉。
10. **改完跑测试**。Python 改动至少跑相关 `pytest` 子集；TS 改动至少 `npm run typecheck`。
11. **写中文为主、术语英文**。文档与注释默认中文；变量名、API 路径、错误字符串、日志关键字保留英文，方便 grep。
12. **添加环境变量必须三件套**：① 在 `.env.example` 留模板和中文注释；② 在 `os.environ.setdefault(...)` 给安全默认值；③ 在 AGENT.md §9.5 表格里加一行（或更新对应章节）。

---

## 18. 已知反模式（请勿复刻）

| 反模式 | 真实后果 |
|---|---|
| `try: ... except Exception: pass` | `docs/strategy-factory/策略工厂跑偏修复方案.md` 案例：`list_stock_universe` 抛 `AttributeError`，被两层吞掉，BULK 矩阵每轮拉到 0 行，工厂退化到 7 个 scan 任务跑通用回测 |
| 在模型可见层暴露 `xxx_manager` | `ensure_agent_tool_name` 直接抛 `ValueError` |
| 把 `xxx_manager` 直接放进 MCP 配置的 `tools` 白名单 | `MCPAggregator.financial_tools` 自动过滤掉，但写入时已经污染配置 |
| 同步阻塞 IO 直接放进 async 函数 | event loop 卡死、孵化 / 调度心跳超时 |
| 自己 `sqlite3.connect()` 自建连接 | 绕过 WAL / busy_timeout / 多实例隔离，引发 `database is locked` |
| 在 `domain/` import `application/` | 立即破坏分层，循环 import |
| 在仓库根 `pytest packages/akshare-mcp/tests` | 找不到 `strategy-factory/src` 路径，30+ 测试假阳性 |
| 把 `*_parts/` 当成 deprecated 目录删除 | 直接破坏 `_fragment_loader` 拼装 |
| `.env.example` 里写真实 token | 会被 git scanner 检出，必须替换为占位符 |
| PG 风格 SQL（`::jsonb`、`RETURNING`、`DATE` 自动反序列化） | SQLite 适配器虽然能转大部分，但日期字段类型不一致，按 PG 假设写就炸 |
| 给 finance_safe 加 `terminal` / `file_write` / `gateway` 工具 | toolset policy 自动拒，新工具要么进 general_full，要么走 ActionIntent |
| 在自由对话里让模型直接 `submit` / `factory_run_once` | 必须先 ActionIntent，控制面在 loopback + 控制 token 之外不响应 |

---

## 19. 文档与索引

### 19.1 文档目录约定（见 `docs/README.md`）

```
docs/
├── architecture/                Hermes 边界 / 对等矩阵 / 集成开发计划
├── strategy-factory/            策略工厂 6 份方案（实盘 / 性能 / 选股 / 因子挖掘 / 数据质量）
├── 策略工厂审计/                12 模块 + 总览（当前实现的真值参照）
├── incubation-factory/          孵化工厂独立运行方案
├── event-driven/                事件驱动主题图谱 / 数据源修订
└── desktop/                     Desktop 应用开发计划
```

### 19.2 当前正在执行的方案

这些 `*.md` 是**当前正在执行的整改文档**，改对应代码必须同步更新（已统一收纳到 `docs/`，按主题分目录；总索引见 `docs/README.md`）：

```
docs/strategy-factory/策略工厂跑偏修复方案.md   BULK 矩阵 / list_stock_universe / 向量画像三层根因
docs/strategy-factory/策略验证体系重构方案.md   Gate 一刀切 → 类型专属验证协议
docs/architecture/金融系统级Agent优化方案.md    L1-L6 六层架构 + Hermes parity
docs/data/数据源管理与同步方案.md               数据源注册 / 连接测试 / 一键同步
docs/factor-mining/因子挖掘工厂设计方案.md      三大并行工厂 + 多引擎 + 进化 + 反馈
docs/factor-mining/因子挖掘系统诊断报告.md      当前实现的差距与现状
docs/architecture/应用绑定与集成开发方案.md     平台 / 金融软件 / 入站守护 / 风控
```

### 19.3 从需求到代码的快速跳转

| 想做什么 | 入口 |
|---|---|
| 改策略生成 / 门禁 / 提交 | `packages/strategy-factory/src/strategy_factory/application/*.py` |
| 改单次周期阶段 | `application/cycle_runner.py` + `cycle_runner_parts/normalizers.py` |
| 改调度（continuous / daily） | `application/factory_scheduler.py` + `_factory_scheduler_*.py` |
| 改 Gate 阈值 | `domain/constants.py`（RESEARCH/INCUBATION/LIVE_ADMISSION_THRESHOLDS） |
| 改 spawner 策略族 | `domain/spawner.py` + `spawner_parts/`、`domain/spawn_policy_registry.py` |
| 改因子挖掘搜索引擎 | `services/factor_mining_factory/engines/*.py` |
| 改因子 DSL / 沙箱 | `services/factor_mining_factory/sandbox/*.py` |
| 改孵化 phase | `services/incubation_factory/{intake,signal_generator,forward_verifier,...}.py` |
| 加 / 改 MCP 工具 | `packages/akshare-mcp/src/akshare_mcp/tools/<group>/<file>.py` |
| 加 / 改 strategy_manager action | `tools/managers/strategy_manager.py` + `strategy_mgr_*.py` + `contracts/strategy_manager_contract.py` |
| 加 / 改 Agent 工具（模型可见） | `aiask_agent/tools/{catalog,schemas}.py` + `tool_registry.py` + `adapters/*.py` |
| 改 Agent HTTP API | `aiask_agent/server.py:create_app()` |
| 改 toolset 边界 | `aiask_agent/tools/policy.py` |
| 改意图状态机 | `aiask_agent/intents.py` + `tool_risk.CONFIRM_REQUIRED_STRATEGY_ACTIONS` |
| 改向量层 schema | `storage/sqlite/schema_vector.py` + `vector_unified.py` |
| 改向量画像 / 索引 | `services/vector_platform.py` + `_vector_platform_*.py` |
| 改嵌入 provider | `services/text_embedding.py` |
| 改 SQL schema | `storage/sqlite/_schema_market_phase_*.py` 或 `schema_strategy_parts/` |
| 接入新数据源 | `data_source/` + `services/data_sync.py` + `tools/managers/data_sync_manager.py` |
| 接入第三方券商 / 行情软件 | `packages/finance-mcp-servers/src/aiask_finance_mcp/<vendor>/` |
| 改 Desktop UI | `desktop/src/features/<area>/` |
| 改 Desktop 与 Agent 的契约 | `desktop/src/services/aiaskApi.ts` + `aiask_agent/server.py` |
| 写新方案 | 顶层 `*.md`（短期）或 `docs/<主题>/`（长期纲领） |

---

> **修订流程**：任何人或 AI 在改动中发现本文件描述与代码不符，必须**在同一次 PR 内**修正，而不是另起 issue。
> 文档准确性 ≥ 文档完整性。
