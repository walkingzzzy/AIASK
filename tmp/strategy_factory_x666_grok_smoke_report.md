# 策略工厂24小时运行与质量追踪

- session_id: `smoke_x666_grok_20260614`
- started_at: `2026-06-14T09:23:42.929137+08:00`
- updated_at: `2026-06-14T09:28:30.529524+08:00`
- duration_hours: `0.2`
- pause_sec_between_rounds: `0`
- execution_mode: `stock_first_observe_primary`
- target_codes: `601288`
- python: `C:\Users\walking\Desktop\aiask\packages\akshare-mcp\.venv\Scripts\python.exe`
- sqlite: `C:\Users\walking\Desktop\aiask\data\db\akshare_mcp.sqlite3`
- report_path: `C:\Users\walking\Desktop\aiask\tmp\strategy_factory_x666_grok_smoke_report.md`
- data_source: `real Strategy Factory runtime + MCP-equivalent manager handlers`

## 累计概览

| 指标 | 数值 |
| --- | ---: |
| 记录轮数 | 1 |
| spawned 总数 | 20 |
| submitted 总数 | 16 |
| Gate 3 通过率 | 6/16 |
| 全部 observe 提交轮数 | 1 |
| observe 被 intake 识别轮数 | 0 |
| paper observation recognized 合计 | 0 |

## 优先级判断

- `P0 未解决` 旧 G3 全拦 / record-only 卡死：当前记录里还缺少足够的提交和 observe intake 证据，不能证明旧式全拦已经解除。 证据：累计 submitted=16, Gate3=6/16, observe intake 识别轮数=0
- `P0 未解决` 高质量策略产出仍未打通：虽然已不再全拦，但高质量策略还没有形成 formal readiness、前向覆盖和执行审计正反馈。 证据：strict_ready_zero=1 轮, zero_forward_coverage=1 轮, audit_needs_attention=1 轮; 最新轮 raw_b_or_above=6, strict_ready=0, submitted=16
- `P1 未解决` 运行时退化仍在影响候选生成质量：当前不只是候选质量本身偏弱，LLM 超时冷却和 partial_llm 退化也在把生成链路推回本地 fallback，压低可执行规格和策略上限。 证据：factory_runtime_degraded=1 轮, llm_timeout_cooldown_active=1 轮, latest_factory_status=partial_infra
- `P0 未解决` G3 通过样本仍未进入 formal 通道：当前执行模式下，G3 通过并不等于 formal_incubation；实跑已经出现“有 G3 通过样本，但整轮仍全部落在 observe”的现象。 证据：gate_pass_but_observe_only_rounds=1, latest_gate3_passed=6, latest_submitted=16, latest_lane_counts={"observe_incubation": 16}
- `P0 未解决` stock_first_observe_primary 模式疑似在提交前预路由到 observe 轨道：当前模式级证据表明，候选在提交前就被 observe-first 路径优先送往 observe 轨道，导致 G3 通过与 formal_incubation 进一步脱钩。 证据：execution_mode=stock_first_observe_primary, gate_pass_but_observe_only_rounds=1, example_round=1, example_gate3_passed=6, example_submitted=16, example_lane_counts={"observe_incubation": 16}, example_budget_track_counts={"formal_incubation": 0, "observe_incubation": 0, "deferred_budget_queue": 16}, example_strategy_status_counts={"submitted": 10}
- `P1 未解决` 生成管线仍有空规格 / fallback 产能损耗：staged pipeline 仍会退回本地规则生成，限制可执行规格产出和候选质量上限。 证据：pipeline_stage_fallback=1 次, pipeline_no_executable_specs=1 次
- `P1 未解决` formal 准入阻塞仍集中在交易质量指标：当前主要不是流程断路，而是 post-cost sharpe、profit factor、win rate 等质量门没有被穿透。 证据：profit_factor x6, diagnostic_only_not_allowed_for_incubation x4, default_profile_not_allowed_for_single_name_runtime x3, execution_readiness_tier:missing_executable_contract x3, win_rate x3

## 当前主要问题

- `pipeline_stage_fallback`: 1 次
- `pipeline_no_executable_specs`: 1 次
- `factory_runtime_degraded`: 1 次
- `llm_timeout_cooldown_active`: 1 次
- `observe_only_submission`: 1 次
- `gate_pass_but_observe_only`: 1 次
- `budget_summary_final_lane_mismatch`: 1 次
- `strict_ready_zero_despite_raw_b`: 1 次
- `strategy_params_storage_truncated`: 1 次
- `no_forward_signal_coverage_yet`: 1 次

## Gate 3 失败原因累计

- `walk_forward_ic_ir_0_971_0_300`: 2
- `weak_wf_ic_ir`: 2
- `purged_kfold_ic_0_001_0_020`: 2
- `weak_pkf_ic`: 2
- `bootstrap_ci_lower_0_051_0_000`: 2

## Formal 准入阻塞累计

- `profit_factor`: 6
- `diagnostic_only_not_allowed_for_incubation`: 4
- `default_profile_not_allowed_for_single_name_runtime`: 3
- `execution_readiness_tier:missing_executable_contract`: 3
- `win_rate`: 3
- `post_cost_sharpe`: 2
- `runtime_family_semantic_mismatch`: 1
- `proxy_runtime_not_allowed_for_formal_incubation`: 1
- `execution_readiness_tier:observe_diagnostic_only`: 1

## 最新轮观察

### 第 1 轮
- 工厂开始: 2026-06-14 09:23:42 +0800
- 工厂结束: 2026-06-14 09:28:27 +0800
- 工厂状态: `partial_infra`
- run_id: `factory_run_1781400225_e323fa8b`
- execution_mode: `stock_first_observe_primary`
- 工厂核心漏斗: spawned=20, dedup_kept=16/18, submitted=16, G3=6/16
- 质量概览: readiness=0.24, raw A/B/C/D=30.0%/30.0%/40.0%/0.0%
- 提交通道: {"observe_incubation": 16}; pipeline_fallback={"returned_empty:no_executable_specs": 3, "failed": 3, "cooldown_skip": 6, "local_fallback_preferred_or_skip": 2, "fallback output failed validation for strategy_generation": 2}
- Dedup: existing=642, kept=16, dropped=2, duplicate_levels={}
- 候选来源: families={"momentum": 7, "margin_divergence": 1, "quality_factor": 1, "gap_fill": 1, "north_capital_track": 1, "ma_cross": 3, "multi_factor": 2, "mean_reversion_short": 2, "rsi": 2}, origins={"local_rule": 20}
- 预算轨道摘要: track_counts={"formal_incubation": 0, "observe_incubation": 0, "deferred_budget_queue": 16}, formal_slots=12, observe_slots=24, dominant_families=["north_capital_track", "momentum", "multi_factor"]
- 问题标记: `pipeline_stage_fallback`, `pipeline_no_executable_specs`, `factory_runtime_degraded`, `llm_timeout_cooldown_active`, `observe_only_submission`, `gate_pass_but_observe_only`, `budget_summary_final_lane_mismatch`, `strict_ready_zero_despite_raw_b`, `strategy_params_storage_truncated`, `no_forward_signal_coverage_yet`, `execution_audit_needs_attention`
- 观察到的问题: pipeline staged fallback observed: {'returned_empty:no_executable_specs': 3, 'failed': 3, 'cooldown_skip': 6, 'local_fallback_preferred_or_skip': 2, 'fallback output failed validation for strategy_generation': 2}
- 观察到的问题: staged pipeline empty-spec fallback: {'returned_empty:no_executable_specs': 3, 'failed': 3, 'cooldown_skip': 6, 'local_fallback_preferred_or_skip': 2, 'fallback output failed validation for strategy_generation': 2}
- 观察到的问题: factory runtime completed with degraded status `partial_infra`
- 观察到的问题: staged pipeline entered timeout cooldown and skipped some LLM phases (cooldown_skip=6)
- 观察到的问题: all submitted strategies were routed to observe_incubation (16/16)
- 观察到的问题: gate_3 reported passed candidates, but the completed round still routed all submissions to observe_incubation (gate_3_passed=6, submitted=16)
- 观察到的问题: incubation budget summary stayed in deferred_budget_queue, but final admission still produced concrete submission lanes; this points to a plan-vs-final routing contract mismatch rather than a pure no-track condition (budget_track_counts={'formal_incubation': 0, 'observe_incubation': 0, 'deferred_budget_queue': 16}, final_lane_counts={'observe_incubation': 16})
- 观察到的问题: there are B-or-above strategies, but none reached strict incubation readiness (raw_b_or_above=6)
- 观察到的问题: sampled strategy rows were stored in compact_json mode, so row-level params were truncated in SQLite and cannot be treated as complete persistence evidence
- 观察到的问题: sampled submitted strategies still have zero forward-observation coverage
- 观察到的问题: execution audit verification still reports needs_attention on sampled strategies
- 观察到的问题: formal admission blockers among analyzed strategies: profit_factor x6; diagnostic_only_not_allowed_for_incubation x4; default_profile_not_allowed_for_single_name_runtime x3; execution_readiness_tier:missing_executable_contract x3; win_rate x3
- formal 准入阻塞: analyzed=10, strict_not_ready=10, top=profit_factor x6; diagnostic_only_not_allowed_for_incubation x4; default_profile_not_allowed_for_single_name_runtime x3; execution_readiness_tier:missing_executable_contract x3; win_rate x3
- Gate 3 失败Top: walk_forward_ic_ir_0_971_0_300 x2; weak_wf_ic_ir x2; purged_kfold_ic_0_001_0_020 x2; weak_pkf_ic x2; bootstrap_ci_lower_0_051_0_000 x2

关联策略抽样
| strategy_id | family | grade | score | review | signal_coverage | audit | status |
| --- | --- | --- | ---: | --- | ---: | --- | --- |
| factory_1781400449_dff31346 | ma_cross | A | 75.82 | fail | 0.00 | needs_attention | submitted |
| factory_1781400423_eb411680 | momentum | A | 74.40 | pass | 0.00 | needs_attention | submitted |
| factory_1781400423_cdb21483 | momentum | A | 74.40 | pass | 0.00 | needs_attention | submitted |

代表样本诊断
- `factory_1781400449_dff31346` grade=A score=75.82 lane=observe_incubation strict_ready=false forward_coverage=0.00 audit=needs_attention exec_gate=missing post_cost_sharpe=0.324 oos_cagr=13.4% evidence_gate=missing
- 核心阻塞: profit_factor 1.548 < 1.800
- 持久化痕迹: params_storage=compact_json dropped_budget=false persisted_lane=observe_incubation quality_lane=observe_incubation planned_lane=observe_incubation budget_track=observe_incubation formal_requested=false strict_ready=false
- `factory_1781400423_eb411680` grade=A score=74.40 lane=observe_incubation strict_ready=false forward_coverage=0.00 audit=needs_attention exec_gate=missing post_cost_sharpe=0.858 oos_cagr=39.6% evidence_gate=missing
- 核心阻塞: default_profile_not_allowed_for_single_name_runtime | diagnostic_only_not_allowed_for_incubation | execution_readiness_tier:missing_executable_contract
- 持久化痕迹: params_storage=compact_json dropped_budget=false persisted_lane=observe_incubation quality_lane=observe_incubation planned_lane=observe_incubation budget_track=observe_incubation formal_requested=false strict_ready=false



## 全部运行记录

### 第 1 轮
- 工厂开始: 2026-06-14 09:23:42 +0800
- 工厂结束: 2026-06-14 09:28:27 +0800
- 工厂状态: `partial_infra`
- run_id: `factory_run_1781400225_e323fa8b`
- execution_mode: `stock_first_observe_primary`
- 工厂核心漏斗: spawned=20, dedup_kept=16/18, submitted=16, G3=6/16
- 质量概览: readiness=0.24, raw A/B/C/D=30.0%/30.0%/40.0%/0.0%
- 提交通道: {"observe_incubation": 16}; pipeline_fallback={"returned_empty:no_executable_specs": 3, "failed": 3, "cooldown_skip": 6, "local_fallback_preferred_or_skip": 2, "fallback output failed validation for strategy_generation": 2}
- Dedup: existing=642, kept=16, dropped=2, duplicate_levels={}
- 候选来源: families={"momentum": 7, "margin_divergence": 1, "quality_factor": 1, "gap_fill": 1, "north_capital_track": 1, "ma_cross": 3, "multi_factor": 2, "mean_reversion_short": 2, "rsi": 2}, origins={"local_rule": 20}
- 预算轨道摘要: track_counts={"formal_incubation": 0, "observe_incubation": 0, "deferred_budget_queue": 16}, formal_slots=12, observe_slots=24, dominant_families=["north_capital_track", "momentum", "multi_factor"]
- 问题标记: `pipeline_stage_fallback`, `pipeline_no_executable_specs`, `factory_runtime_degraded`, `llm_timeout_cooldown_active`, `observe_only_submission`, `gate_pass_but_observe_only`, `budget_summary_final_lane_mismatch`, `strict_ready_zero_despite_raw_b`, `strategy_params_storage_truncated`, `no_forward_signal_coverage_yet`, `execution_audit_needs_attention`
- 观察到的问题: pipeline staged fallback observed: {'returned_empty:no_executable_specs': 3, 'failed': 3, 'cooldown_skip': 6, 'local_fallback_preferred_or_skip': 2, 'fallback output failed validation for strategy_generation': 2}
- 观察到的问题: staged pipeline empty-spec fallback: {'returned_empty:no_executable_specs': 3, 'failed': 3, 'cooldown_skip': 6, 'local_fallback_preferred_or_skip': 2, 'fallback output failed validation for strategy_generation': 2}
- 观察到的问题: factory runtime completed with degraded status `partial_infra`
- 观察到的问题: staged pipeline entered timeout cooldown and skipped some LLM phases (cooldown_skip=6)
- 观察到的问题: all submitted strategies were routed to observe_incubation (16/16)
- 观察到的问题: gate_3 reported passed candidates, but the completed round still routed all submissions to observe_incubation (gate_3_passed=6, submitted=16)
- 观察到的问题: incubation budget summary stayed in deferred_budget_queue, but final admission still produced concrete submission lanes; this points to a plan-vs-final routing contract mismatch rather than a pure no-track condition (budget_track_counts={'formal_incubation': 0, 'observe_incubation': 0, 'deferred_budget_queue': 16}, final_lane_counts={'observe_incubation': 16})
- 观察到的问题: there are B-or-above strategies, but none reached strict incubation readiness (raw_b_or_above=6)
- 观察到的问题: sampled strategy rows were stored in compact_json mode, so row-level params were truncated in SQLite and cannot be treated as complete persistence evidence
- 观察到的问题: sampled submitted strategies still have zero forward-observation coverage
- 观察到的问题: execution audit verification still reports needs_attention on sampled strategies
- 观察到的问题: formal admission blockers among analyzed strategies: profit_factor x6; diagnostic_only_not_allowed_for_incubation x4; default_profile_not_allowed_for_single_name_runtime x3; execution_readiness_tier:missing_executable_contract x3; win_rate x3
- formal 准入阻塞: analyzed=10, strict_not_ready=10, top=profit_factor x6; diagnostic_only_not_allowed_for_incubation x4; default_profile_not_allowed_for_single_name_runtime x3; execution_readiness_tier:missing_executable_contract x3; win_rate x3
- Gate 3 失败Top: walk_forward_ic_ir_0_971_0_300 x2; weak_wf_ic_ir x2; purged_kfold_ic_0_001_0_020 x2; weak_pkf_ic x2; bootstrap_ci_lower_0_051_0_000 x2

关联策略抽样
| strategy_id | family | grade | score | review | signal_coverage | audit | status |
| --- | --- | --- | ---: | --- | ---: | --- | --- |
| factory_1781400449_dff31346 | ma_cross | A | 75.82 | fail | 0.00 | needs_attention | submitted |
| factory_1781400423_eb411680 | momentum | A | 74.40 | pass | 0.00 | needs_attention | submitted |
| factory_1781400423_cdb21483 | momentum | A | 74.40 | pass | 0.00 | needs_attention | submitted |

代表样本诊断
- `factory_1781400449_dff31346` grade=A score=75.82 lane=observe_incubation strict_ready=false forward_coverage=0.00 audit=needs_attention exec_gate=missing post_cost_sharpe=0.324 oos_cagr=13.4% evidence_gate=missing
- 核心阻塞: profit_factor 1.548 < 1.800
- 持久化痕迹: params_storage=compact_json dropped_budget=false persisted_lane=observe_incubation quality_lane=observe_incubation planned_lane=observe_incubation budget_track=observe_incubation formal_requested=false strict_ready=false
- `factory_1781400423_eb411680` grade=A score=74.40 lane=observe_incubation strict_ready=false forward_coverage=0.00 audit=needs_attention exec_gate=missing post_cost_sharpe=0.858 oos_cagr=39.6% evidence_gate=missing
- 核心阻塞: default_profile_not_allowed_for_single_name_runtime | diagnostic_only_not_allowed_for_incubation | execution_readiness_tier:missing_executable_contract
- 持久化痕迹: params_storage=compact_json dropped_budget=false persisted_lane=observe_incubation quality_lane=observe_incubation planned_lane=observe_incubation budget_track=observe_incubation formal_requested=false strict_ready=false



## 当前判断

- staged pipeline 仍然存在 `no_executable_specs` 型空规格回退，这是真实产能问题。
- 当前多数提交仍落在 observe lane，说明正式孵化就绪率偏低。
- 出现了原始质量不差但 strict incubation readiness 仍为 0 的轮次，需要继续查 formal 准入约束。
- 当前 formal 准入阻塞集中在: `profit_factor`, `diagnostic_only_not_allowed_for_incubation`, `default_profile_not_allowed_for_single_name_runtime`, `execution_readiness_tier:missing_executable_contract`, `win_rate`。
- 新提交策略的前向观测覆盖还很低，短期内不应夸大其真实交易质量。
