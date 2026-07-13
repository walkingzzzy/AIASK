# 工厂运行脚本（代码对标）

> 更新：2026-07-13  
> 与 `scripts/factories/run_three_factories.py` 源码一致。旧 “Signal Factory 第四工厂 / Phase 完成” 叙述已废弃。

## Supervisor

**主入口**：`run_three_factories.py`  
（文件名历史遗留；`SUPERVISED_FACTORY_NAMES` / `REQUIRED_SCRIPTS` 默认 **最多 4** 运行体，可 CLI/环境裁剪）

| 名称 | 脚本 |
| --- | --- |
| Strategy Factory | `run_strategy_factory.py` |
| Factor Mining Factory | `run_factor_mining_factory.py` |
| Incubation Factory | `run_incubation_factory.py` |
| Market Event Ingest | `run_market_event_ingest.py` |

兼容：`run_all_factories.py` → 委托 supervisor。

生产子环境关键强制（见 supervisor 源码）：

- `AIASK_FACTORY_RUNTIME_PROFILE=production_supervisor`  
- `AIASK_FACTORY_PAPER_OWNER=incubation_factory`  
- runtime configurator → host `configure_strategy_factory_runtime_services`  

## SignalTracker（sidecar）

- **不在** `SUPERVISED_FACTORY_NAMES`  
- 入口：`run_signal_tracker.py`（`--once` / daemon）  
- 缺席时：diagnostics `signal_tracker.status=absent`，readiness `signal_tracker_presence` 降级/阻塞  

共启：`COSTART_EVIDENCE_LOOP.md`

## Quality session（非生产）

- `run_strategy_factory_quality_session.py`  
- 只验证/暴露；**禁止**补偿生产 formal  

## 诊断

```bash
uv run python scripts/ops/runtime_formal_daily.py
uv run python scripts/factories/diagnose_formal_blockers.py
python scripts/factories/check_factory_doc_banned_phrases.py
```

## 文档

- 现状一页：`docs/CURRENT.md`  
- 架构：`docs/factory-architecture/01-当前实际架构.md`  
- 运维手册：`docs/factory-architecture/06-运行与诊断手册.md`  

## 禁止宣称

- Live / formal 已通（除非 readiness L4 + 非空证据）  
- bootstrap_ready = hard gate 通过  
- supervisor 已含 SignalTracker  
