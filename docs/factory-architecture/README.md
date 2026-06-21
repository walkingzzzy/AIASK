# 策略工厂四工厂架构与技术规范

本文档集是策略工厂相关运行体系的长期规范入口。它的目标不是再写一份“运行说明”，而是把策略工厂从补丁式修复拉回统一架构：四工厂各自负责什么、为什么存在、要达成什么目标、产生什么证据、失败时如何定位，都必须在这里有可执行的判断标准。

本文档以当前代码、启动脚本、Graphify 代码图谱、AKShare MCP 资源目录、测试和最近运行事实为准；历史报告和根目录 Markdown 只作为问题背景。若本文档与当前代码冲突，以当前代码为准，并优先修正文档。

## 当前结论

- 正式“四工厂”运行主管口径为：`Strategy Factory`、`Factor Mining Factory`、`Incubation Factory`、`Market Event Ingest`。
- `SignalTracker` 是策略孵化闭环必需的 sidecar，不再混称为 supervisor 管理的第四工厂。
- `scripts/factories/run_three_factories.py` 是当前四运行体 supervisor；`scripts/factories/run_all_factories.py` 是兼容入口。
- `scripts/factories/run_strategy_factory_quality_session.py` 是验证会话，不是生产 supervisor，也不应该承担生产补偿逻辑。
- 生命周期必须分成物理状态和业务覆盖层：`strategies.status`、`strategy_incubation_accounts.stage/status` 是实际存储；`generated -> ... -> promotion_ready` 是证据派生诊断状态。
- production hard gate 只认 `execution_audit_gate_status='passed'`；`bootstrap_pending/bootstrap_ready` 只能作为诊断或样本债状态。
- `healthy/pending_evidence/degraded/blocked/unsafe` 是规范级健康模型，当前代码尚未统一实现为同一个 enum/class。
- 当前会话未暴露可调用的 `thinking` MCP；本轮深度审查使用了可见的 `akshare-mcp` resources、Graphify、当前源码和公开联网资料。若后续环境暴露 `thinking` MCP，应把其审查结论追加到 [09-深度架构审查报告](09-深度架构审查报告.md)。

## 目标读者

- 产品和业务负责人：看 [07-四工厂目标与业务价值](07-四工厂目标与业务价值.md)，理解四工厂最终要形成什么策略生产线。
- 架构和后端工程：看 `00` 到 `05`，按契约改代码，而不是追单个指标修补。
- 运维和验证人员：看 [06-运行与诊断手册](06-运行与诊断手册.md) 和 [10-规范符合性清单](10-规范符合性清单.md)，判断系统是健康、待证据成熟、退化还是阻塞。
- 后续审查者：看 [appendix/source-index](appendix/source-index.md)，从源码、Graphify、MCP 和公开资料复核本文档。

## 阅读顺序

1. [00-术语与四工厂口径裁决](00-术语与四工厂口径裁决.md)
2. [01-当前实际架构](01-当前实际架构.md)
3. [02-策略工厂全链路生命周期规范](02-策略工厂全链路生命周期规范.md)
4. [03-四工厂运行规范](03-四工厂运行规范.md)
5. [04-SignalTracker与证据闭环规范](04-SignalTracker与证据闭环规范.md)
6. [05-技术治理与修复路线图](05-技术治理与修复路线图.md)
7. [06-运行与诊断手册](06-运行与诊断手册.md)
8. [07-四工厂目标与业务价值](07-四工厂目标与业务价值.md)
9. [08-外部原则与参考映射](08-外部原则与参考映射.md)
10. [09-深度架构审查报告](09-深度架构审查报告.md)
11. [10-规范符合性清单](10-规范符合性清单.md)
12. [appendix/source-index](appendix/source-index.md)

## 如何使用

遇到策略工厂问题时，不再从某个表层指标开始修。先把问题落到以下四层：

1. 控制面：哪个 supervisor、sidecar、quality session 或 Agent 入口触发了运行。
2. 生命周期：先看 `strategies.status`、`strategy_incubation_accounts.stage/status`、`pipeline_stage` 的物理状态，再派生策略停在 `generated`、`admitted_observe`、`paper_signalled`、`paper_ordered`、`paper_filled_open`、`round_trip_closed`、`audit_ready` 的哪一段。
3. 证据链：`strategy_signals`、`paper_orders`、`paper_trades`、`strategy_trade_positions`、`signal_forward_returns`、`strategy_signal_evidence`、execution audit 是否可串联。
4. 责任组件：应由 Strategy、Factor Mining、Incubation、Market Event Ingest、SignalTracker、Quant Core storage 还是 quality session 暴露失败。

只有当这四层都解释清楚后，才进入代码修改或数据修复。任何只让 `healthy=true`、只加 timeout、只在质量会话里补偿、只把 bootstrap 当晋级证据的修法，都不符合本规范。

## 文档边界

本文档说明架构、契约、运行规范和诊断方法，不直接修改策略工厂代码。策略生成、因子挖掘、孵化、paper 交易、execution audit 等行为仍由各自源码实现。

本文档不保存 `.env`、凭证值、数据库 dump、broker 状态或 live 交易凭证。任何运行命令都必须遵守 live trading guardrail：默认只允许诊断、paper、read-only 或明确受控的工厂流程。

## 当前未完成事项

- 统一生命周期账本仍需产品化为只读诊断入口，避免人工拼 Strategy run、SignalTracker、Incubation 和 SQLite 表。
- SignalTracker sidecar 虽然已有 phase-level timeout 和 partial result 结构，但仍需在生产控制面中成为显式依赖，而不是靠运维记忆单独启动。
- execution audit 与 hard gate 已坚持真实 paper closed round-trip，但样本债需要通过持续 paper execution 和 stale close policy 自然消化。
- `quality session` 仍应继续瘦身：它可以验证、采样和报告，不应成为生产证据补偿路径。
- `thinking` MCP 当前不可见；后续若可用，需要把独立审查结论纳入 `09`，并标注与代码事实是否一致。

## 维护规则

- 修改四工厂启动方式时，必须同步更新 `00`、`03` 和 `06`。
- 修改策略生命周期或证据表语义时，必须同步更新 `02`、`04` 和 `10`。
- 修改 Strategy Factory 与 AKShare MCP 的 provider 边界时，必须同步更新 `01` 和 `appendix/source-index`。
- 修改 quality session 行为时，必须说明它是验证工具还是生产控制面；默认只能是验证工具。
- 修改 hard gate、execution audit 或 bootstrap/backtest 行为时，必须明确 production hard gate 只认真实 paper closed round-trip。
