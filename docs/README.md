# Docs 导航（代码对标现行树）

> 更新：2026-07-13  
> 原则：**活跃树只放与当前代码一致的 SoT；历史快照进 archive；target-state 必须标明不是现状。**

## 分层

| 层 | 路径 | 用途 |
| --- | --- | --- |
| 代码对标一页纸 | [`CURRENT.md`](CURRENT.md) | 包角色、拓扑、契约常量、控制面、成熟度 |
| Current-state 规范 | [`factory-architecture/`](factory-architecture/) | `00`–`13` 强制规范 |
| 方案 / ownership | [`specs/`](specs/) | 2026-07 闭环、冻结边界、瘦身 target |
| 前端工作流 | [`frontend-v1/`](frontend-v1/) | 现行流程 only |
| 运维 | `../scripts/factories/`、`../scripts/ops/` | 共启、日报、诊断 |
| 历史 | [`archive/historical/`](archive/historical/) | 过期进度/里程碑/一次性报告 |

## 必读顺序

1. [CURRENT.md](CURRENT.md) — **先读**  
2. [factory-architecture/01-当前实际架构.md](factory-architecture/01-当前实际架构.md)  
3. [factory-architecture/00-术语与四工厂口径裁决.md](factory-architecture/00-术语与四工厂口径裁决.md)  
4. [factory-architecture/11-禁止的修复方式与正确路径.md](factory-architecture/11-禁止的修复方式与正确路径.md)  
5. [specs/五大生产缺陷闭环开发方案-2026-07-11.md](specs/五大生产缺陷闭环开发方案-2026-07-11.md)  
6. [specs/五大生产缺陷-剩余闭环修改计划-2026-07-11.md](specs/五大生产缺陷-剩余闭环修改计划-2026-07-11.md)  
7. [../scripts/factories/COSTART_EVIDENCE_LOOP.md](../scripts/factories/COSTART_EVIDENCE_LOOP.md)

## 源码核验捷径

| 问题 | 先打开 |
| --- | --- |
| supervisor 管谁 | `scripts/factories/run_three_factories.py` |
| bootstrap 必需几项 | `strategy_factory/runtime/default_bootstrap.py` |
| hard gate 阈值 | `strategy_factory/contracts/hard_gate.py` |
| incubation 必选 phase | `strategy_factory/runtime/incubation_phases.py` |
| Desktop 默认连哪 | `desktop/src/hooks/useConnectionSettings.ts` |
| production_ready | `aiask_agent/financial_readiness.py` |
| Intent 谁能执行 | `aiask_agent/tool_risk.py` `AGENT_EXECUTABLE_*` |
| 诊断 next_actions | `akshare_mcp/services/factory_diagnostics.py` |

## 协作 / 前端主规范

- `specs/AGENT.md`  
- `specs/AIASK项目开发技术规范-V1前端产品化-2026-06-21.md`  
- 前端工作流：`frontend-v1/FRONTEND_WORKFLOW.md`

## 明确不是 SoT

- `archive/historical/**`  
- 任何 STARTUP_CONFIRMED / MILESTONE / P2_PROGRESS / 日期完成报告  
- `strategy-factory-spec/` 内 planned 路径（target only）  
- Graphify 2026-05 数字（参考 blast radius，非最终拓扑证明）

## 整理规则

1. **现状行为** → `CURRENT` + `factory-architecture/00-13`  
2. **分期方案/冻结** → `specs/`  
3. **某日运行/进度** → `archive/historical/`  
4. 文档与代码冲突 → 当天修文档或修代码，禁止活跃树双真相  
