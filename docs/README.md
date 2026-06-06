# AIASK 文档索引

本索引只整理 `docs/` 目录。仓库根目录下的文档不在本次整理范围内。

## 阅读规则

- 当前实现以代码、manifest、测试和运行脚本为准，文档只作为入口、背景和操作说明。
- 主目录只放当前仍建议阅读的文档；过期方案、诊断复盘、截图快照和阶段性审计放入 `archive/`。
- `archive/` 中的内容保留为证据和历史背景，不能直接当作当前架构事实。
- 文档里不要写真实密钥值，只写环境变量名和配置语义。

## 当前入口

| 主题 | 入口 | 用途 |
|---|---|---|
| 仓库长期规则 | [`../AGENT.md`](../AGENT.md) | 项目级开发规范；若与代码冲突，以代码为准并同步修正文档 |
| 运维统一入口 | [`runbook/AIASK_OPERATIONS_RUNBOOK.md`](runbook/AIASK_OPERATIONS_RUNBOOK.md) | 启停、健康检查、回滚、SLO 相关操作 |
| SLO 与门禁 | [`runbook/SLO.md`](runbook/SLO.md) | 上线门禁、告警口径、残余风险 |
| 系统就绪评审 | [`architecture/AIASK_OVERALL_READINESS_REVIEW_2026-05-29.md`](architecture/AIASK_OVERALL_READINESS_REVIEW_2026-05-29.md) | 架构、能力、上线就绪度的阶段性评审 |
| Hermes 边界 | [`architecture/hermes-boundary.md`](architecture/hermes-boundary.md) | AIASK 原生能力与 Hermes reference 的边界 |
| Code Graph | [`architecture/code-graph.md`](architecture/code-graph.md) | Graphify/code graph 生成、查询和 Agent 只读工具边界 |
| TDX 数据源规范 | [`data/TDX数据源规范.md`](data/TDX数据源规范.md) | 当前 TDX-first/TDX-only 数据源边界 |
| 数据维护手册 | [`data/数据维护手册-2026-06-03.md`](data/数据维护手册-2026-06-03.md) | K 线、因子 IC、同步失败落盘和 freshness SOP |
| Desktop 当前基线 | [`desktop/AIASK_DESKTOP_APP_DEVELOPMENT_PLAN.md`](desktop/AIASK_DESKTOP_APP_DEVELOPMENT_PLAN.md) | Desktop 只通过 Agent HTTP API 消费能力 |
| Desktop 手工测试 | [`desktop/frontend-mcp-manual-test.md`](desktop/frontend-mcp-manual-test.md) | 前端 MCP/Agent 手工验证步骤 |
| 归档索引 | [`archive/README.md`](archive/README.md) | 历史方案、诊断、审计、快照的存放位置 |

## 当前目录

```text
docs/
├── architecture/           当前架构边界、就绪评审、code graph
├── data/                   当前数据源规范、数据维护、旧向量表退役计划
├── desktop/                Desktop 当前基线和手工测试
├── event-driven/           当前事件驱动专题方案
├── factor-mining/          因子挖掘工厂当前设计
├── incubation-factory/     孵化工厂当前说明入口
├── ops/                    本地开发和终端编码运维说明
├── runbook/                统一运维 runbook 与 SLO
├── strategy-factory/       当前策略工厂专题与状态迁移说明
└── archive/                历史方案、诊断、审计、截图和旧计划
```

## 策略工厂当前专题

`strategy-factory/2026-06-倒置架构与因子路由/` 是当前策略工厂修复与验证专题，建议按下面顺序阅读：

1. [`策略工厂实际架构现状梳理-2026-06-02.md`](strategy-factory/2026-06-倒置架构与因子路由/策略工厂实际架构现状梳理-2026-06-02.md)
2. [`策略工厂倒置架构设计方案-2026-06-02.md`](strategy-factory/2026-06-倒置架构与因子路由/策略工厂倒置架构设计方案-2026-06-02.md)
3. [`策略工厂Alpha源接线修复方案-2026-06-03.md`](strategy-factory/2026-06-倒置架构与因子路由/策略工厂Alpha源接线修复方案-2026-06-03.md)
4. [`策略工厂Stock-First多策略路由方案-2026-06-03.md`](strategy-factory/2026-06-倒置架构与因子路由/策略工厂Stock-First多策略路由方案-2026-06-03.md)
5. [`因子超市与数据架构差距评估-2026-06-03.md`](strategy-factory/2026-06-倒置架构与因子路由/因子超市与数据架构差距评估-2026-06-03.md)
6. [`两方案代码可行性核验报告-2026-06-03.md`](strategy-factory/2026-06-倒置架构与因子路由/两方案代码可行性核验报告-2026-06-03.md)
7. [`灰度上线手册-P0数据与toggle-2026-06-03.md`](strategy-factory/2026-06-倒置架构与因子路由/灰度上线手册-P0数据与toggle-2026-06-03.md)
8. [`策略工厂修复进度总览-2026-06-03.md`](strategy-factory/2026-06-倒置架构与因子路由/策略工厂修复进度总览-2026-06-03.md)

状态枚举迁移单独见 [`strategy-factory/status-migration.md`](strategy-factory/status-migration.md)。

## 运行入口速查

| 能力 | 入口 |
|---|---|
| Agent 服务 | `packages/agent/src/aiask_agent/server.py`，脚本 `aiask-agent` |
| AKShare MCP | `packages/akshare-mcp/src/akshare_mcp/server.py`，脚本 `akshare-mcp` |
| Strategy Factory | `scripts/factories/run_strategy_factory.py`，兼容入口 `run_strategy_factory.py` |
| Factor Mining Factory | `scripts/factories/run_factor_mining_factory.py` |
| Incubation Factory | `scripts/factories/run_incubation_factory.py` |
| Desktop | `desktop/`，开发命令 `cd desktop && npm run dev` |

## 基本验证命令

```powershell
make test-agent
make test-finance
cd desktop && npm run typecheck
```

文档-only 修改至少检查 Markdown 链接和路径是否仍存在。
