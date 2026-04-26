---
name: akshare-strategy-factory
description: 策略工厂、策略超市、工厂运行、孵化、评审、运行时风控、向量治理与生命周期扫描等场景使用；适用于 strategy-market 分域能力的编排与核验。
capability_tier: live_orchestrated
runtime_status: executable
product_surfaces: ["mcp", "bff", "web", "artifact"]
artifacts: ["strategy_review", "factory_run", "incubation_pipeline", "runtime_governance"]
backing_tools: ["run_skill", "strategy_manager", "strategy_review_workflow"]
backing_managers: ["strategy_manager"]
regulatory_scope: ["strategy_governance", "model_governance"]
role_tags: ["quant", "research", "risk"]
last_runtime_verified_at: "2026-04-19"
---

> 校准说明：本 skill 只定义“策略工厂”相关能力的推荐入口、证据门禁与显式触发规则，不代表仓库里存在单一、一键式且全自动的工厂总控链路。
>
> 当前真实实现是分布式承载：
> 1. 只读审查优先 `strategy_review_workflow` 与 `resource://strategy/{id}/review`
> 2. 状态、治理、触发类操作优先 `strategy_manager`
> 3. BFF/Web 入口主要落在 `apps/bff/src/strategy/` 与 `apps/web/app/strategy-market/`，它们用于产品承载与只读核验，不等于闭环已跑通
>
> 若缺少 run 记录、评审报告、孵化快照、运行时风险、向量索引或领域投影证据，应明确标注“未完成/待补证据”。


# 目标
把“策略工厂”请求收敛到可核验的运行、评审、孵化、监控与治理路径上，而不是只给出泛化策略建议。

# 适用触发
- 用户提到“策略工厂”“策略超市”“strategy-market”“工厂运行”“候选生成”“孵化”“评审”“策略运行态”“推广评审”“向量治理”“领域投影”。
- 需要核查某个策略的工厂运行记录、提交门禁、孵化管线、运行时风险、向量索引、领域事件或 AI 生成实验。

# 入口优先级
- 治理检查：
  - 跨工厂治理检查使用 `governance_check_workflow`
  - 不在 Web/BFF 侧自行复刻治理规则
- 策略只读审查：
  - 优先 `strategy_review_workflow(strategy_id=...)`
  - 同时可读 `resource://strategy/{id}/review`
  - 需要补充事件证据时再调用 `strategy_manager(action=events)`
- 工厂运行态：
  - `strategy_manager(action=capabilities|factory_status|factory_runs|factory_run_detail|task_runs)`
- 提交门禁：
  - `strategy_manager(action=execution_audit_verification)`
  - 需要显式重算/重放/提交时，再使用 `review_report_recheck|submission_replay|submit`
- 孵化与推广：
  - `strategy_manager(action=incubation_overview|incubation_accounts|incubation_metrics|paper_account|paper_orders|paper_nav|incubation_pipeline|promotion_reviews)`
- 运行时治理：
  - `strategy_manager(action=runtime_cycle_status|risk_events|risk_snapshots|runtime_alerts|runtime_control)`
- 向量治理：
  - `strategy_manager(action=vector_health|vector_indexes|vector_index_snapshots|vector_profiles|vector_ann_search)`
- 领域投影：
  - `strategy_manager(action=domain_events|domain_projection|domain_projection_snapshot)`
- AI 生成与实验：
  - `strategy_manager(action=ai_experiments|task_runs)`

# 推荐任务
- `factory_cycle`
  - 读 `capabilities`、`factory_status`、`factory_runs`
  - 有运行批次 ID 时补 `factory_run_detail`
  - 有 `strategy_id` 时补 `task_runs`
  - 只有显式设置 `trigger_factory_run=true` 才触发 `factory_run_once`
- `strategy_review`
  - 有 `strategy_id` 时优先复用 `strategy_review_workflow`
  - 额外补 `strategy_manager(action=events)`
  - 无 `strategy_id` 时退到 `strategy_manager(action=rank|list)`
  - 只有显式设置 `trigger_factory_run=true` / `trigger_runtime_cycle=true` 才会触发运行侧动作
- `submission_gate`
  - 默认只读看 `execution_audit_verification`
  - `trigger_review_report_recheck=true` 才跑 `review_report_recheck`
  - `trigger_submission_replay=true` 才跑 `submission_replay`
  - `trigger_submit=true` 才跑 `submit`
- `incubation_pipeline`
  - 默认只读看 `incubation_overview`、`incubation_accounts`、`incubation_metrics`、`paper_account`、`paper_orders`、`paper_nav`、`incubation_pipeline`、`promotion_reviews`
  - `trigger_incubation_sync=true` 才跑 `incubation_sync_run`
  - `trigger_incubation_pipeline_run=true` 才跑 `incubation_pipeline_run`
  - `trigger_promotion_review=true` 才跑 `promotion_review_run`
- `runtime_governance`
  - 默认只读看 `runtime_cycle_status`、`risk_events`、`risk_snapshots`、`runtime_alerts`、`runtime_control`
  - 只有显式 trigger 才运行 `risk_scan_run`、`risk_recovery`、`resolve_risk_event`、`runtime_alert_dispatch_run`、`runtime_alert_ack`、`runtime_control_set`、`runtime_cycle_run`
- `vector_governance`
  - 默认只读看 `vector_health`、`vector_indexes`、`vector_index_snapshots`、`vector_profiles`、`vector_ann_search`
  - 只有显式 trigger 才运行 `vector_reconcile`、`vector_rebuild`、`vector_cleanup`
- `domain_projection`
  - 默认只读看 `domain_events`、`domain_projection`、`domain_projection_snapshot`
  - `trigger_domain_projection_rebuild=true` 才跑 `domain_projection_rebuild`
- `ai_generation`
  - 默认只读看 `ai_experiments`、`task_runs`
  - `trigger_ai_generate=true` 才跑 `ai_generate`
- `smoke_test`
  - 只做只读的 `factory_cycle` 最小快照，不触发任何状态改变动作

# 失败与兜底
- `strategy_review_workflow` 不可用：
  - 退到 `resource://strategy/{id}/review` + `strategy_manager(action=review_report|runtime_alerts|factory_status|events)`
- `strategy_manager` 不可用：
  - 退到 BFF `/strategy-market/*` 接口或 Web `/strategy-market` 页面做只读核验
- 缺少 run / projection / vector / runtime 证据：
  - 只报告“当前未见证据”，不要根据榜单、页面或单次详情反推出工厂闭环已完成
- 请求退化成普通组合、风控或执行：
  - 分流到 `akshare-portfolio-manager-core` 或 `akshare-fund-manager-pro`

# 参考
- 主工具：`strategy_review_workflow`、`strategy_manager`
- 只读资源：`resource://strategy/{id}/review`
- 产品入口：`apps/bff/src/strategy/`、`apps/web/app/strategy-market/`
