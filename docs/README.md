# 金融系统级 AGENT · 文档索引

## 目录结构

```
docs/
├── architecture/           # 系统架构 / Hermes 集成 / 系统级 Agent 演进
├── strategy-factory/       # 策略工厂
├── factor-mining/          # 因子挖掘工厂
├── incubation-factory/     # 孵化工厂
├── event-driven/           # 事件驱动
├── data/                   # 数据源 / 存储治理
├── desktop/                # Desktop 应用
└── 策略工厂审计/           # 策略工厂历史审计
```

> 项目级开发规范见仓库根目录 [`AGENT.md`](../AGENT.md)。

---

## architecture/ — 系统架构

| 文档 | 说明 |
|---|---|
| [hermes-boundary.md](architecture/hermes-boundary.md) | Hermes 边界定义 |
| [hermes-financial-product-parity.md](architecture/hermes-financial-product-parity.md) | Hermes 金融产品对等性 |
| [HERMES_AIASK_INTEGRATION_DEVELOPMENT_PLAN.md](architecture/HERMES_AIASK_INTEGRATION_DEVELOPMENT_PLAN.md) | Hermes-AIASK 集成开发计划 |
| [金融系统级Agent优化方案.md](architecture/金融系统级Agent优化方案.md) | 从专业 Agent 升级为系统级 Agent 的总体方案 |
| [应用绑定与集成开发方案.md](architecture/应用绑定与集成开发方案.md) | 微信/同花顺/东方财富等外部应用绑定方案 |

---

## strategy-factory/ — 策略工厂

策略工厂负责 AI 生成交易策略候选，通过 Gate-0 → Gate-3 分级门禁筛选。

| 文档 | 说明 |
|---|---|
| [策略工厂-实盘就绪改造方案.md](strategy-factory/策略工厂-实盘就绪改造方案.md) | 从回测到实盘的改造方案 |
| [策略工厂-数据质量原则与流程.md](strategy-factory/策略工厂-数据质量原则与流程.md) | 数据质量管控原则 |
| [策略工厂-数据质量违规修复方案.md](strategy-factory/策略工厂-数据质量违规修复方案.md) | 数据质量违规修复 |
| [策略工厂-性能优化方案.md](strategy-factory/策略工厂-性能优化方案.md) | 性能优化 |
| [策略工厂-选股逻辑修复方案.md](strategy-factory/策略工厂-选股逻辑修复方案.md) | 选股逻辑修复 |
| [策略工厂-因子挖掘修复方案.md](strategy-factory/策略工厂-因子挖掘修复方案.md) | 因子挖掘修复 |
| [策略工厂-全景问题清单-2026-05-17.md](strategy-factory/策略工厂-全景问题清单-2026-05-17.md) | 全景问题清单 |
| [策略工厂-fragment-loader-重构计划.md](strategy-factory/策略工厂-fragment-loader-重构计划.md) | fragment loader 重构计划 |
| [策略工厂跑偏修复方案.md](strategy-factory/策略工厂跑偏修复方案.md) | 任务源头与画像消费链路修复 |
| [策略工厂二次修复方案.md](strategy-factory/策略工厂二次修复方案.md) | 16 轮实测后的下一阶段修复 |
| [策略工厂优化方案.md](strategy-factory/策略工厂优化方案.md) | 实测瓶颈驱动的优化方案 |
| [策略验证体系重构方案.md](strategy-factory/策略验证体系重构方案.md) | LLM-as-Judge 自适应验证体系重构 |

---

## factor-mining/ — 因子挖掘工厂

与策略工厂、孵化工厂并行的第三大引擎，负责自动化因子搜索与进化。

| 文档 | 说明 |
|---|---|
| [因子挖掘工厂设计方案.md](factor-mining/因子挖掘工厂设计方案.md) | 多引擎自动化搜索 + 进化优化的工业级因子生产线设计 |
| [因子挖掘系统诊断报告.md](factor-mining/因子挖掘系统诊断报告.md) | 因子挖掘全链路静态分析与架构诊断 |

**入口脚本**：`run_factor_mining_factory.py`

---

## incubation-factory/ — 孵化工厂

孵化工厂负责验证 AI 生成策略的真实命中率，是策略从"回测幻象"到"实盘真实"的唯一桥梁。

| 文档 | 说明 |
|---|---|
| [孵化工厂-独立运行方案.md](incubation-factory/孵化工厂-独立运行方案.md) | 孵化工厂独立运行方案（v3，含完整实现计划） |

**核心代码位置**：`packages/akshare-mcp/src/akshare_mcp/services/incubation_factory/`

**运行方式**：
```bash
# 单次运行
make incubation-factory

# 守护进程（每日 18:30）
make incubation-factory-daemon

# 查看状态
make incubation-factory-status
```

---

## event-driven/ — 事件驱动

事件驱动模块负责从市场事件（政策、财报、行业动态）触发策略生成。

| 文档 | 说明 |
|---|---|
| [事件驱动升级方案-数据源修订-2026-05-14.md](event-driven/事件驱动升级方案-数据源修订-2026-05-14.md) | 数据源修订方案 |
| [事件驱动主题联动-策略工厂升级方案-2026-05-08.md](event-driven/事件驱动主题联动-策略工厂升级方案-2026-05-08.md) | 主题联动升级方案 |

---

## data/ — 数据源与存储治理

| 文档 | 说明 |
|---|---|
| [数据源管理与同步方案.md](data/数据源管理与同步方案.md) | 数据源配置、同步状态监控、向量库管理与可视化 |
| [SQLite存储膨胀修复方案.md](data/SQLite存储膨胀修复方案.md) | SQLite 异常膨胀根因与四步治理方案 |

---

## desktop/ — Desktop 应用

Desktop 是系统的可视化前端，基于 React + Vite + Tauri。

| 文档 | 说明 |
|---|---|
| [AIASK_DESKTOP_APP_DEVELOPMENT_PLAN.md](desktop/AIASK_DESKTOP_APP_DEVELOPMENT_PLAN.md) | Desktop 应用开发计划 |

**代码位置**：`desktop/`

---

## 系统数据流

```
市场数据 → 事件驱动 → 策略工厂 → 孵化工厂 → 实盘交易
                ↑          │              │
                │          │              └── 反馈 → 策略工厂进化
          因子挖掘工厂 ────┤
                           │
                           └── Desktop 可视化
```
