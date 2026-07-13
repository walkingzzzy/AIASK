# AIASK 当前实际状态（代码对标一页纸）

> 更新：2026-07-13  
> 口径：只写**当前源码可核验**的事实。历史进度、里程碑、完成报告见 `archive/historical/`。  
> 核验入口：`scripts/factories/run_three_factories.py`、`packages/strategy-factory/src/strategy_factory/**`、`packages/agent/src/aiask_agent/**`、`desktop/src/hooks/useConnectionSettings.ts`。

---

## 1. 系统是什么

多包 monorepo：**策略生产线 + Agent 控制面 + Desktop V1**。

| 路径 | 代码角色（现状） |
| --- | --- |
| `packages/strategy-factory` | 编排契约 owner：`contracts/*`、`runtime/*` facade、bootstrap、incubation phase 表；**不**静态依赖 `akshare_mcp` |
| `packages/akshare-mcp` | 肥宿主：MCP tools、数据适配、host providers、`IncubationFactoryRunner` I/O、matching/promotion 实现面、`FactoryDiagnosticsService` |
| `packages/aiask-quant-core` | SQLite schema/storage 与 quant primitives |
| `packages/agent` | Desktop **live** 控制面（默认 HTTP `:8765`）：Intent、tool policy、readiness、in-process adapters |
| `desktop/` | React/Vite/Tauri UI；默认 `mode=mock`，live `baseUrl=http://127.0.0.1:8765` |
| `packages/desktop-api` | 可选薄 CRUD `:8001`，**不是**四工厂/live 主后端 |
| `scripts/factories` | 进程 lifecycle（supervisor/runners/diagnostics）；**不拥有**业务状态机真相 |

控制面链路（代码路径）：

```text
Desktop (mock | live→Agent :8765)
  → Agent HTTP / ActionIntent / agent_* tools
    → adapters (in-process) → strategy_factory.runtime.* + akshare_mcp services
      → SQLite (aiask_quant_core storage)
```

---

## 2. 运行拓扑（以 supervisor 源码为准）

**主入口**：`scripts/factories/run_three_factories.py`  
文件名历史遗留；`SUPERVISED_FACTORY_NAMES` / `REQUIRED_SCRIPTS` 默认 **4** 个运行体：

1. `strategy_factory` → `run_strategy_factory.py`  
2. `factor_mining_factory` → `run_factor_mining_factory.py`  
3. `incubation_factory` → `run_incubation_factory.py`  
4. `market_event_ingest` → `run_market_event_ingest.py`  

**不在** `SUPERVISED_FACTORY_NAMES` 内：

- `run_signal_tracker.py` — **证据 sidecar**（signals / forward returns 等）  
- `run_strategy_factory_quality_session.py` — **验证会话 only**，禁止当生产补偿面  

兼容入口：`run_all_factories.py` 委托 `run_three_factories.py`。

Supervisor 子环境关键强制（源码常量/逻辑）：

- `AIASK_FACTORY_RUNTIME_PROFILE=production_supervisor`  
- `AIASK_FACTORY_PAPER_OWNER=incubation_factory`  
- runtime configurator 指向 host：`akshare_mcp.adapters.strategy_factory_runtime:configure_strategy_factory_runtime_services`（可通过 env 覆盖）

共启与日报：

- `scripts/factories/COSTART_EVIDENCE_LOOP.md`  
- `uv run python scripts/ops/runtime_formal_daily.py`

---

## 3. Strategy Factory bootstrap / 契约（源码锚点）

### 3.1 Canonical bootstrap

- 文件：`packages/strategy-factory/src/strategy_factory/runtime/default_bootstrap.py`  
- `DEFAULT_REQUIRED_RUNTIME_PROVIDERS`：**19** 个名字（缺一则 bootstrap 失败）  
- 加载方式：`AIASK_STRATEGY_FACTORY_RUNTIME_CONFIGURATOR` 或 entry point group `aiask.strategy_factory.runtime`  
- `infrastructure/mcp_services.py` 仅为 `runtime_services` 的 **compat shim**，不是业务 owner 实现体  

### 3.2 Runtime facade（SF 侧）

`packages/strategy-factory/src/strategy_factory/runtime/`：

- `factor_mining.py` / `incubation.py` / `market_event_ingest.py` / `signal_tracker.py`  
- `incubation_phases.py` — phase 名/超时/required 表  
- `incubation_orchestrator_shell.py` — phase plan 壳（**明确不 import** host；I/O 仍 host）  
- `default_bootstrap.py`

### 3.3 契约 owner（SF）

`packages/strategy-factory/src/strategy_factory/contracts/`：

| 模块 | 锁定语义（代码常量） |
| --- | --- |
| `hard_gate.py` | `PRODUCTION_TRADE_FLOOR_DEFAULT=20`；expectancy>0；pnl_conversion>0；`EXECUTION_CONVERSION_EFFICIENCY_MIN=0.20`；状态含 `bootstrap_ready` 但 **production 通过只认 `passed`** |
| `promotion_ready.py` | pure promotion floors |
| `evidence_gaps.py` | 证据缺口 schema |
| `execution_universe.py` | 可执行 universe 契约 |

Host 侧（如 `akshare_mcp.../confidence.py`）应对 hard gate **re-export/委托**，不得分叉阈值。

### 3.4 Incubation once 必选 phase（代码表）

`incubation_phases.INCUBATION_ONCE_PHASES` 中 `required=True`：

1. `intake`  
2. `exit_signal_paper_execution`  
3. `execution_audit_acceptance`  
4. `pipeline`  

其余 phase 可选。I/O 实现仍主要在  
`packages/akshare-mcp/src/akshare_mcp/services/incubation_factory/runner.py`。

---

## 4. Agent / Desktop 控制面（源码锚点）

### 4.1 Desktop

`desktop/src/hooks/useConnectionSettings.ts`：

- 默认 `mode = mock`（`VITE_AIASK_API_MODE` 可覆盖）  
- 默认 `baseUrl = http://127.0.0.1:8765`  
- live 只应打 Agent，不直连 MCP/DB  

### 4.2 Intent 可执行性

`packages/agent/src/aiask_agent/tool_risk.py` + `intents.py`：

- 大量 `strategy_manager.*` 在 confirm 策略名单里，但 **Agent 真正可执行** 的写动作是有限集合（`AGENT_EXECUTABLE_STRATEGY_ACTIONS`：factory_run_once/dispatch 与部分 factory_event_* 等）  
- 其余 confirm 名单动作创建 intent 时 **fail-closed**（`STRATEGY_FACTORY_EXTERNAL_RUNNER_REQUIRED`）  
- `incubation_factory.run_once` 等默认倾向 `dry_run=true`（显式 `dry_run=false` 才真跑）

### 4.3 Readiness / 成熟度

`packages/agent/src/aiask_agent/financial_readiness.py`：

- `production_ready = (status==ready) and not mock AI`  
- `maturity_level`：`L0`…`L4`（L4 需要非 mock + ready + 证据形态）  
- `code_closed_loop_ready`：代码闭环资产存在性（**不等于 Live**）  
- 必选工厂探针含：evidence / lineage / exit / hard_gate / formal / **`signal_tracker_presence`**

### 4.4 诊断同源

`packages/akshare-mcp/.../factory_diagnostics.py`：

- 只读 formal/observe/orders/trades/exit_funnel/hard_gate_histogram  
- `signal_tracker` 字段：由 DB 推断 present/stale/absent  
- 空库 next_action：`bootstrap_factory_runtime`  
- 有池无信号：`start_signal_tracker_sidecar`

---

## 5. 成熟度诚实口径（禁止混读）

| 层级 | 含义 | 代码如何体现 |
| --- | --- | --- |
| L0 | 包可装/进程可起 | 脚本存在 |
| L1 | 契约+控制面代码闭环 | contracts / intents / readiness 字段存在 |
| L2 | 运行态有策略池 | diagnostics `observe/incubating/formal` 非全空 |
| L3 | paper 证据/退出可测 | signals/orders/trades/closed 非空且可解释 |
| L4 | Live production ready | `production_ready=true` 且非 mock；**禁止默认宣称** |

本地库经常出现：`formal_count=0`、`signals/orders/trades=0` 但行情表很大 → **行情底座在、策略证据链未跑**，不是“没写门禁”。

---

## 6. 现行文档 SoT（只信这些活跃树）

1. 本文件 `docs/CURRENT.md`  
2. `docs/factory-architecture/00`–`13` + `README.md`  
3. `docs/specs/*2026-07-11*` 与 ownership 冻结文档  
4. `scripts/factories/README.md` + `COSTART_EVIDENCE_LOOP.md`  
5. `docs/frontend-v1/FRONTEND_WORKFLOW.md`  

历史：`docs/archive/historical/**` — **非 SoT**。

---

## 7. 明确禁止写进“现状”的句子

- “SignalTracker 是 supervisor 第四工厂”  
- “run_all_factories 已启动完整证据闭环”  
- “bootstrap_ready 算 hard gate 通过”  
- “方案+代码 PASS = Live 生产就绪”  
- “Desktop mock 绿 = 生产门禁绿”  
- “strategy-factory 已物理迁出全部 runner I/O”  

---

## 8. 快速核验命令

```bash
# supervisor 成员（读源码常量即可）
# SUPERVISED_FACTORY_NAMES / REQUIRED_SCRIPTS

# 只读诊断
uv run python scripts/ops/runtime_formal_daily.py

# hard gate 阈值守门测试（包内）
# packages/strategy-factory/tests/test_hard_gate_thresholds_snapshot.py
```
