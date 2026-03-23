---
name: akshare-strategy-factory
description: 策略工厂、策略超市、工厂运行、孵化、评审、运行时风控、向量治理与生命周期扫描等场景使用；适用于 strategy-market 分域能力的编排与核验。
---

> 校准说明：本 skill 只定义“策略工厂”相关能力的推荐调用顺序与证据门禁，不代表仓库里存在单一、封闭且全自动的一键工厂总控链路。
>
> 当前真实实现是分布式承载：核心 MCP 入口为 `strategy_manager`，BFF/Web 入口主要落在 `apps/bff/src/strategy/` 与 `apps/web/app/strategy-market/`。
>
> 若某一步缺少运行记录、评审报告、孵化快照、运行时风险或向量索引证据，应明确标注“未完成/待补证据”，不要把工厂页面存在误判为闭环已经跑通。


# 目标
把“策略工厂”相关请求收敛到可核验的运行、评审、孵化、监控与治理路径上，而不是只给出泛化的策略建议。

# 适用触发
- 用户提到“策略工厂”“策略超市”“strategy-market”“工厂运行”“候选生成”“孵化”“评审”“策略运行态”。
- 需要核查某个策略的工厂运行记录、运行时风险、向量索引或推广评审状态。

# 推荐流程
- 阶段 0（入口确认）：
  - 优先确认是“工厂运行/治理”问题，而不是普通选股或回测问题。
  - 工厂主入口优先用 `strategy_manager`；若用户需要产品面展示，再落到 `/strategy-market` 分域页面。
- 阶段 1（工厂运行态）：
  - 用 `strategy_manager(action=factory_status)` 看调度、最近摘要与能力开关。
  - 用 `strategy_manager(action=factory_runs)`、`strategy_manager(action=factory_run_detail)` 看运行批次与阶段结果。
  - 需要人工触发时，用 `strategy_manager(action=factory_run_once)`。
- 阶段 2（策略清单与评审）：
  - 用 `strategy_manager(action=rank|list|detail)` 看策略列表与详情。
  - 用 `strategy_manager(action=review_report|review_report_recheck)` 看评审报告与复检。
  - 用 `strategy_manager(action=get_signals|get_forward_returns|get_signal_stats|events)` 看信号、前瞻收益和事件轨迹。
- 阶段 3（孵化与运行时）：
  - 用 `strategy_manager(action=incubation_overview|incubation_accounts|incubation_metrics)` 看孵化状态。
  - 用 `strategy_manager(action=paper_account|paper_orders|paper_nav)` 核查模拟盘承载。
  - 用 `strategy_manager(action=risk_events|risk_snapshots|runtime_alerts|runtime_control)` 看运行时风险、告警与控制平面。
- 阶段 4（向量与治理）：
  - 用 `strategy_manager(action=vector_health|vector_indexes|vector_index_snapshots|vector_profiles|vector_ann_search)` 看向量平台与索引健康。
  - 用 `strategy_manager(action=domain_events|domain_projection|promotion_reviews|lifecycle_scan)` 看领域事件、投影、晋级评审与生命周期治理。
- 阶段 5（分流）：
  - 若问题退化成普通组合、风控或仿真执行，转到 `akshare-portfolio-manager-core` 或 `akshare-fund-manager-pro` 的流程。

# 失败与兜底
- `strategy_manager` 不可用：退到 BFF `/strategy-market/*` 接口或 Web `/strategy-market` 页面做只读核验。
- 工厂运行记录缺失：只报告“未见 run 证据”，不要根据策略榜单反推工厂已运行。
- 孵化/风控接口缺失：仅返回现有策略详情与评审结果，不补造运行时结论。
- 向量治理不可用：不要把相似策略检索或 ANN 结果当作质量证明，单独标注为“索引侧证据缺失”。

# 参考
- 主工具：`strategy_manager`
- 配套承载：`paper_trading_manager`、`risk_manager`
- 产品入口：`apps/bff/src/strategy/`、`apps/web/app/strategy-market/`
