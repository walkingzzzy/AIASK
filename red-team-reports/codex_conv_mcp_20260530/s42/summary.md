# N42 · AI 工作流-策略复核 (strategy_review_workflow / strategy_manager 全生命周期)

- **运行**: 2026-05-30 17:38 · 32 次真实工具调用 · verdict=**fail_schema_publish_gate_bypass_and_payload_bloat**
- **工具**: `strategy_review_workflow`、`strategy_manager`(70 个 action 的生命周期/治理/向量/AI/孵化全覆盖)
- **隔离**: user_id=`redteam_conv_20260530`；建 2 个测试策略 `strat_1780133799_ef91794a`(ma_cross probe) + `strat_1780133851_bf0a2c5a`(badtype)，测后均 archive+unsubscribe；`run_factory_once`/`run_runtime_cycle` 全程未触发。

## 判定分布
Pass 16 · Degraded 4 · Fail-graceful 2 · **Fail-schema 6**

## 关键发现

### ★★★ F-N42-1（HIGH）publish 质量门完全绕过
对一个 `pipeline_stage=warmup` / `raw_signal_count=0` / `execution_audit_gate=missing` / `quality_passed=false` / `promotion_ready=false` / `blocker_count=3`(5D样本0<20、skill LCB≤0、前向覆盖0%) 的零证据 draft，`publish` 直接返回 `status=listed` 成功上架公开策略超市。完全绕过 `execution_reality.promotion_gate`(min_sharpe0.5/min_win_rate0.45/min_trade_count20/min_incubation_days30)。垃圾策略可一键发布被他人 subscribe/rank。

### ★★ F-N42-2（HIGH）单策略复核内嵌全量 factory run 历史 + 错误血缘
`strategy_review_workflow`/`closure_review`/`detail`/`factory_status` 对单个用户 draft，把最近 5 个完整 strategy-factory run（每个 110-119KB、含全 stages）内联进响应（数十万 token）。更严重：手工 create 的 draft 与任何 factory run 无关联，却被赋 `correlation_id/factory_run_id=factory_run_1780132151_31625ea1`（全局调度 run），血缘错误归属。

### ★ F-N42-3（MEDIUM）publish 不可逆 + delete/archive 语义割裂
策略一旦 publish→listed，owner 即无法 `delete_personal_strategy`（"market strategies are read-only" / BACKEND_ERROR），只能 archive；而同 user 的 draft 态策略可正常 delete。publish 单向不可逆但契约无提示。

### F-N42-4（LOW）incubation_overview 文档契约不符
help 文档称 `strategy_id` 可选（无参返回 incubating 列表），运行时却必填报错。

### F-N42-5（MEDIUM）create 不校验 strategy_type
`strategy_type=totally_fake_strategy_type_zzz` 无白名单校验直接入库，下游无执行器可能崩。

## 正向亮点
- ★★ `strategy_review_workflow` 4 步编排优雅降级（partial_failed + recoverable + resume_hint + failed_steps 显式）。
- ★★ `execution_audit_acceptance` 多层验证工程质量高（schema/migrations/coverage/lineage/semantic_contract + 可执行 recommendations）。
- ★★ capability_health 15 能力健康追踪 + signal_quality_registry 校准漂移监测完整。
- ★ 错误路径规范（name/strategy_id required、NOT_FOUND 均 error_code 标准化）；personal_strategy_context/suggestions 的 mutation_guard + advisory_only 诚实标注。

## standing_caveat
DB 仅约 250 根日线/8 只标的；策略注册表初始为空（list=0）；strategy_factory 后台 run(447 等)为前序残留只读，非本场景触发。
