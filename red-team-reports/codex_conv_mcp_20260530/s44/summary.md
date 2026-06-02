# N44 · 策略超市生命周期 (strategy_manager 全 action)

- **运行**: 2026-05-30 17:54 · 30 次真实调用 · user_id=redteam_conv_20260530
- **判定**: Pass 14 / Degraded 3 / Fail-graceful 2 / Fail-schema 11
- **verdict**: `fail_schema_payload_bloat_and_nonexistent_target_handling_inconsistency_but_submit_gate_robust`

## 场景说明
覆盖 N42 未触及的 strategy_manager action（72 个 action 中），聚焦：未测只读 action（get_signals/execution_audit_verification/runtime_control/runtime_cycle_status/rank by win_rate）、隔离写生命周期（create→fork→submit→review→delete/archive）、以及一批 nonexistent strategy_id 边界。全程隔离 user，两个测试策略测后清理。

## 关键发现

### ★★ F-N44-1（HIGH）submit/risk_events/promotion_reviews payload 爆炸 + 错误血缘
对手工 create 的 zero-evidence draft 调 `submit`，单次响应内嵌**最近 5 个完整 factory run**（每个 ~110KB 全 stages），数十万 token，几乎撑爆上下文。且 `closure_review.factory_run_id` 误置为全局 `factory_run_1780133277`（该 draft 与任何 run 零关联），`closure_review.owner_state.kind=anonymous`（创建者归属丢失）。与 F-N42-2 同源同族。

### ★★ F-N44-2（MED）subscribe 裸抛 FOREIGN KEY 错误
`subscribe(nonexistent)` → `FOREIGN KEY constraint failed`（DB 层异常直接冒泡），而同 ID 的 detail/incubation_overview 都返回干净 `STRATEGY_MANAGER_NOT_FOUND`。subscribe 缺前置存在性校验。

### ★ F-N44-3（MED）runtime_control 对不存在目标静默伪成功
`runtime_control(pause, nonexistent)` → `success=true`（control_mode=active/status=released），无 NOT_FOUND。write 类控制操作对不存在目标应拒绝。

### ★ F-N44-4（MED）execution_audit_verification 与目标存在性解耦
`execution_audit_verification(nonexistent)` 返回完整 `needs_attention` 报告（all_required_tables_present=true / migrations applied）。该工具实际验证全局 DB schema 而非具体策略，任意不存在 ID 都"schema 通过"。

### ★ F-N44-5（MED）review 评分聚合断链 + 无 self-review 防护
`review(rating=4)` 成功，但随后 my_strategies 该策略 `avg_rating=0/review_count=0`，聚合未刷新；且允许 owner 自评（同 N42）。

### F-N44-6（LOW）submit 后个人 draft 变 read-only 不可删
submit→rejected 后 owner_state 从 owned_personal_strategy 变 owned_strategy/editable=false，delete 报 "market strategies are read-only"，仅 archive 可行。submit 是不可逆单向效应（即便 rejected），同 F-N42-3。

### F-N44-7（LOW）vector_health 标志矛盾
`sqlite_python_enabled=false` 但 `backend_used=sqlite_python`/`fallback_used=false`，自相矛盾。

### F-N44-8（LOW）archived 策略仍 editable
personal_strategy_suggestions 对 archived 策略仍 `editable=true`/暴露 optimize+persist_update(stateful)。

## 正向亮点

- **★★★ submit 质量门极严且与 publish 形成鲜明对照**：对 zero-evidence draft，submit 严格 `status=rejected`——gate_a(pass)/gate_b(block, 3 硬失败)/gate_c(observe)，research/incubation/live 三档 admission_evaluations 各带完整阈值矩阵+逐条 reasons，multiple_testing(deflated_sharpe/PBO/white_reality_check/hansen_spa)+semantic_contract 检测全就位。**这正是 F-N42-1（publish 零质量门绕过）所缺失的闸门**——系统具备严格闸门能力，只是 publish 路径未接入。
- **★★ submit 完整血缘事件链**：domain.events + ai.task_runs(19391) + execution_audit snapshot 持久化，trace_id/correlation_id 贯穿。
- ★ fork_strategy 血缘清晰；my_strategies 状态区分准确；边界查询多数返回标准 NOT_FOUND 或空骨架。

## 护栏遵守
全程隔离 user_id，2 个测试策略测后清理（fork delete 成功；rejected probe 因 F-N44-6 只能 archive）。未触发 run_factory_once/run_runtime_cycle。risk_events/promotion_reviews/factory_status 巨型 payload 黑名单工具刻意规避（仅前序已采集）。
