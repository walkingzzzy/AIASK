# 策略工厂四工厂架构与技术规范

## 规范地位

**本目录 `00`–`13` 是策略工厂 current-state 强制规范。**  
所有相关开发/修复必须先核对本规范与 `../CURRENT.md`（代码对标一页纸）。

### 禁止（与代码守门一致）

- Quality Session 启用生产补偿 / 伪造 formal  
- 新增 Phase 3x 补丁代替根因  
- 用 `success` 掩盖 `partial_infra` / `failed`  
- 绕过 `ExecutionUniverseContract`  
- 把 `bootstrap_pending` / `bootstrap_ready` 当 production hard gate 通过  
- 从多局部真相拼健康报告  
- 在 `strategy-factory` **src** 引入 `akshare_mcp` 静态依赖  

### 规范 vs 代码

1. 规范是目标、代码未实现 → 标注“当前未实现”或改代码  
2. 规范与代码不符 → 优先修文档或回退违规代码  
3. 历史进度报告 → 只在 `../archive/historical/`，不得回填本目录  

---

## 当前结论（源码可核验）

| 结论 | 代码锚点 |
| --- | --- |
| 四运行体 = Strategy / Factor Mining / Incubation / Market Event Ingest | `run_three_factories.SUPERVISED_FACTORY_NAMES` |
| SignalTracker = sidecar，不在 supervisor | 不在 `REQUIRED_SCRIPTS`；`run_signal_tracker.py` 独立 |
| Supervisor 文件名历史遗留 | `run_three_factories.py` 实际默认最多 4 子进程 |
| Bootstrap 必需 providers = 19 | `default_bootstrap.DEFAULT_REQUIRED_RUNTIME_PROVIDERS` |
| Hard gate floor=20，conversion≥0.20，只认 `passed` | `contracts/hard_gate.py` |
| Incubation required phases = 4 | `incubation_phases.required_phase_names()` |
| Runner I/O 仍大量 host | `akshare_mcp.services.incubation_factory.runner` |
| Desktop live → Agent :8765，默认 mock | `desktop/.../useConnectionSettings.ts` |
| Mock 永不 production_ready | `financial_readiness.production_ready` |
| 诊断含 signal_tracker 推断 | `FactoryDiagnosticsService._signal_tracker_presence` |

---

## Source of truth（活跃树）

### A. 一页现状

- [`../CURRENT.md`](../CURRENT.md)

### B. Current-state（本目录）

1. [00-术语与四工厂口径裁决](00-术语与四工厂口径裁决.md)  
2. [01-当前实际架构](01-当前实际架构.md) ⭐ 架构总入口  
3. [02-策略工厂全链路生命周期规范](02-策略工厂全链路生命周期规范.md)  
4. [03-四工厂运行规范](03-四工厂运行规范.md)  
5. [04-SignalTracker与证据闭环规范](04-SignalTracker与证据闭环规范.md)  
6. [05-技术治理与修复路线图](05-技术治理与修复路线图.md)  
7. [06-运行与诊断手册](06-运行与诊断手册.md)  
8. [07-四工厂目标与业务价值](07-四工厂目标与业务价值.md)  
9. [08-外部原则与参考映射](08-外部原则与参考映射.md)  
10. [09-深度架构审查报告](09-深度架构审查报告.md)  
11. [10-规范符合性清单](10-规范符合性清单.md)  
12. [11-禁止的修复方式与正确路径](11-禁止的修复方式与正确路径.md)  
13. [12-四工厂真实流程与MCP依赖审计](12-四工厂真实流程与MCP依赖审计.md)  
14. [13-四工厂-MCP能力占用台账](13-四工厂-MCP能力占用台账.md)  
15. [CODE_REVIEW_CHECKLIST.md](CODE_REVIEW_CHECKLIST.md)

> 若 `12`/`13` 中的统计数字与当前源码不一致，以源码与 `01`/`CURRENT` 为准，并应回写修正。

### C. 2026-07 生产闭环（`../specs/`）

- 五大生产缺陷闭环开发方案 / 目标完成审计 / 剩余闭环修改计划（2026-07-11）  
- P1-B-S1 冻结、P1-B-S4 边界、P2 稳态脚手架  

审计 PASS 范围 = **方案+代码闭环**，**不是** Live。

### D. Target-state（非现状证明）

- `strategy-factory-spec/`  
- `../specs/四工厂独立化与MCP瘦身拆分开发方案-2026-06-23.md`

### E. 运维

- `../../scripts/factories/README.md`  
- `../../scripts/factories/COSTART_EVIDENCE_LOOP.md`  
- `uv run python scripts/ops/runtime_formal_daily.py`

### F. 历史（非 SoT）

- `../archive/historical/2026-06/` — June 进度/里程碑/一次性运行报告  

---

## 阅读顺序

**新人**：`../CURRENT.md` → `11` → `00` → `01` → `02` → `10`  
**修生产问题**：`runtime_formal_daily.py` → `06` → `04` → `11`  
**改边界**：`01` + `contracts/*` 源码 + `P1-B-S1`  
**运维共启**：`COSTART_EVIDENCE_LOOP.md` + `03`

---

## 问题归层（强制）

改代码前必须落到：

1. 控制面（谁触发）  
2. 生命周期物理状态 vs 派生诊断状态  
3. 证据链是否完整  
4. 责任组件（SF / Factor / Incubation / MEI / SignalTracker / Quant Core / quality）  

禁止：只改 timeout、只在 quality session 补偿、只把 bootstrap 当晋级证据。
