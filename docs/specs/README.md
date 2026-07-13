# 规范与方案（`docs/specs`）— 代码对标

> 更新：2026-07-13  
> **Current-state 架构细节**以 `../CURRENT.md` + `../factory-architecture/00–13` 为准。  
> 本目录放 **方案 / ownership 冻结 / 生产闭环分期**；target 文档不得伪装成“已经 Live”。

## 1. 生产闭环（2026-07-11）

| 文档 | 与代码的关系 |
| --- | --- |
| `五大生产缺陷闭环开发方案-2026-07-11.md` | 主方案：晋级/宿主/Mock≠Live/退出/运维；锚点应对 `hard_gate`/`runner`/`financial_readiness` |
| `五大生产缺陷闭环-目标完成审计-2026-07-11.md` | **方案+代码闭环**审计 PASS；明确 **非 Live 宣称** |
| `五大生产缺陷-剩余闭环修改计划-2026-07-11.md` | R1 运行态样本 / R2 runner 抽离 / R3 Graphify / R4 UX |
| `P1-B-S1-akshare-factory-services-freeze.md` | host 冻结：新状态机不得长在 AK services |
| `P1-B-S4-lifecycle-load-vs-evaluate-boundary.md` | load vs evaluate 边界 |
| `P2-稳态治理脚手架-2026-07-11.md` | drift / soak / golden 最小稳态 |
| `策略说明闭环-为什么生成与孵化-2026-07-13.md` | 生成/孵化可解释性契约与 Desktop 展示 |

### 已在代码侧可对上的闭环资产（摘要）

- hard gate / promotion_ready / evidence_gaps contracts in SF  
- fail-closed signal lineage toggle + matching reject path  
- `FactoryDiagnosticsService` + Agent `agent_factory_formal_diagnostics`  
- readiness：`production_ready` / `maturity_level` / `signal_tracker_presence`  
- Intent：external runner fail-closed + dry-run defaults  
- `scripts/ops/runtime_formal_daily.py` + `COSTART_EVIDENCE_LOOP.md`  

### 仍 open（不得写进“已 Live”）

- 有样本 formal/exit 转化 SLO（R1）  
- incubation runner I/O 全量迁出 AK（R2）  

## 2. 架构迁移 target-state

| 文档 | 用途 |
| --- | --- |
| `四工厂独立化与MCP瘦身拆分开发方案-2026-06-23.md` | ownership 反转与 MCP 瘦身主方案（**target**） |

## 3. 协作 / 前端主规范

| 文档 | 用途 |
| --- | --- |
| `AGENT.md` | 仓库协作约定 |
| `AIASK项目开发技术规范-V1前端产品化-2026-06-21.md` | 前端产品化主规范 |

前端现行工作流：`../frontend-v1/FRONTEND_WORKFLOW.md`。

## 4. 运维配套（仓库脚本）

```text
scripts/factories/README.md
scripts/factories/COSTART_EVIDENCE_LOOP.md
uv run python scripts/ops/runtime_formal_daily.py
python scripts/factories/check_factory_doc_banned_phrases.py
```

## 5. 使用规则

- 谈 **现状拓扑/契约常量** → `CURRENT` + factory-architecture，不写进“完成报告”语气  
- 谈 **分期与 DoD** → 本目录 2026-07 三件套  
- 谈 **历史 June 进度** → `../archive/historical/2026-06/`  
- 任何 “PASS/完成” 必须带范围标签：`scheme_and_code_closed_loop` vs `live_production_claim=false`  
