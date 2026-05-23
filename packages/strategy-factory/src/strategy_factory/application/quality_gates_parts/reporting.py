

# ---------------------------------------------------------------------------
# Gate-1: 快速筛选
# ---------------------------------------------------------------------------

from .compact_contracts import (
    COMPACT_PREVIEW_LIMIT,
    compact_backtest_report as _compact_backtest_report_for_gate,
    compact_candidate_brief as _compact_gate_candidate_brief,
    compact_quality_gate_report as _compact_quality_gate_report,
)


async def gate_1_fast_screen(
    candidate: dict,
    db,
    *,
    kline_cache: Optional[Dict[str, list]] = None,
) -> GateResult:
    """用少量代表性股票做快速回测，Sharpe ≥ GATE1_SHARPE_MIN 即通过。"""
    candidate = apply_resolved_candidate_envelope(candidate)
    factory_pkg = get_strategy_factory_package()
    contract_snapshot = build_portfolio_candidate_contract(candidate)
    contract_hash = build_candidate_contract_hash(contract=contract_snapshot)
    tested_object_hash = str(candidate.get("tested_object_hash") or "").strip() or build_tested_object_hash(candidate)
    strategy_type = str(contract_snapshot.get("strategy_type") or candidate.get("strategy_type") or "momentum")
    assumptions = build_factory_backtest_assumptions(candidate)
    params = {
        **dict(candidate.get("params") or {}),
        **assumptions.to_backtest_kwargs(),
    }

    # ── 参数补充：LLM 生成的候选可能缺少回测所需的策略参数 ──────────
    # 检查 params 中是否有实际的策略参数（排除任务元数据字段）
    _TASK_META_KEYS = {
        "task_attempt_count", "task_stage_attempt_count", "candidate_local_attempt_count",
        "task_local_attempt_count", "candidate_local_selected_count", "task_local_selected_count",
        "task_network_request_count", "task_real_request_count", "task_compatibility_skip_count",
        "task_cooldown_skip_count", "task_compatibility_failure_count",
        "task_effective_response_count", "task_empty_200_response_count",
        "task_compatibility_failure_ratio", "task_effective_response_ratio",
        "task_selected_count",
    }
    strategy_params = {k: v for k, v in params.items() if k not in _TASK_META_KEYS}
    if not strategy_params:
        # 缺少策略参数 → 用 Spawner 的默认参数补充
        try:
            from strategy_factory.domain.spawner import StrategySpawner
            from strategy_factory.domain.parameter_distribution_registry import (
                ParameterDistributionRegistry,
            )
            spawner = StrategySpawner.__new__(StrategySpawner)
            default_params = spawner._legacy_varied_defaults(strategy_type, 0, snapshot=None)
            # PR-S21：优先用 task 上的 stock_profile 参数 band
            research_task = dict(candidate.get("research_task") or {})
            band = (
                research_task.get("param_search_space")
                or research_task.get("profile_param_band")
            )
            band_sample = ParameterDistributionRegistry.sample_from_param_band(band, idx=0)
            merged_defaults = dict(default_params or {})
            if band_sample:
                merged_defaults.update(dict(band_sample.get("params") or {}))
            if merged_defaults:
                params = {**merged_defaults, **params}
                # 写回 candidate 以便下游 Gate 使用
                candidate["params"] = params
        except Exception:
            pass
    # ── End 参数补充 ──────────────────────────────────────────────────

    sharpe_min = float(_compat_setting("GATE1_SHARPE_MIN", GATE1_SHARPE_MIN) or GATE1_SHARPE_MIN)
    codes, prioritized_target_codes, code_source, validation_focus, research_task = _resolve_gate_1_codes(candidate)
    precompile_validation = validate_precompile_candidate_contract(
        candidate,
        research_task=research_task,
        source="gate_1_fast_screen",
    )
    precompile_summary = precompile_validation.to_dict()
    tested_codes = (
        list(prioritized_target_codes)
        if validation_focus != "broad_generalization" and prioritized_target_codes
        else list(codes)
    )
    sharpe_values: list[float] = []
    total_return_values: list[float] = []
    turnover_values: list[float] = []
    trade_count_values: list[float] = []
    max_drawdown_values: list[float] = []
    errors: list[str] = []
    market_data: dict[str, list] = {}

    if not precompile_validation.contract_completeness_ok:
        contract_reasons = list(precompile_validation.contract_reject_reasons or ["contract_incomplete"])
        return GateResult(
            passed=False,
            gate="gate_1",
            reasons=contract_reasons,
            metrics={
                "tested_codes": tested_codes,
                "target_codes": prioritized_target_codes,
                "code_source": code_source,
                "validation_focus": validation_focus,
                "primary_validation_layer": (
                    "combined"
                    if validation_focus == "broad_generalization"
                    else "target"
                ),
                "validation_contract_mode": "contract_fast_screen",
                "validation_scope": "fast_screen",
                "stage_role": "fast_screen",
                "contract_gate_status": "failed",
                "contract_gate": precompile_summary,
                "candidate_contract_hash": contract_hash,
                "tested_object_hash": tested_object_hash,
                "candidate_contract_snapshot": contract_snapshot,
                "backtest_assumptions": assumptions.to_audit_dict(),
                "tested_code_count": len(tested_codes),
                "eligible_code_count": 0,
                "sharpe_values": [],
            },
        )

    for code in tested_codes:
        try:
            if kline_cache and code in kline_cache:
                klines = kline_cache[code]
            else:
                klines = await db.get_klines(code, limit=250)
            if not klines or len(klines) < 30:
                errors.append(f"{code}:insufficient_klines")
                continue
            market_data[code] = list(klines)
        except Exception as exc:
            errors.append(f"{code}:{type(exc).__name__}")

    if len(market_data) > 1:
        portfolio_runner = getattr(factory_pkg.BacktestEngine, "run_portfolio_backtest", None)
        if not callable(portfolio_runner):
            errors.append("portfolio_contract_runner_unavailable")
        else:
            try:
                result = await asyncio.to_thread(
                    portfolio_runner,
                    market_data,
                    strategy_type,
                    params,
                )
                payload = dict(result.get("data") or {}) if isinstance(result, dict) else {}
                if not isinstance(result, dict) or not result.get("success"):
                    raise ValueError((result or {}).get("error") or "portfolio_backtest_failed")
                sharpe = float(payload.get("sharpe_ratio") or payload.get("sharpe") or 0.0)
                sharpe_values.append(sharpe)
                if payload.get("total_return") is not None:
                    total_return_values.append(_safe_float(payload.get("total_return"), 0.0))
                if payload.get("turnover_proxy") is not None:
                    turnover_values.append(_safe_float(payload.get("turnover_proxy"), 0.0))
                if payload.get("trades_count") is not None:
                    trade_count_values.append(_safe_float(payload.get("trades_count"), 0.0))
                if payload.get("max_drawdown") is not None:
                    max_drawdown_values.append(abs(_safe_float(payload.get("max_drawdown"), 0.0)))
            except Exception as exc:
                errors.append(f"portfolio_contract:{type(exc).__name__}")
    else:
        for code, klines in market_data.items():
            try:
                BacktestEngine = factory_pkg.BacktestEngine
                result = await asyncio.to_thread(
                    BacktestEngine.run_backtest,
                    code,
                    klines,
                    strategy_type,
                    params,
                )
                payload = dict(result.get("data") or {}) if isinstance(result, dict) else {}
                if not isinstance(result, dict) or not result.get("success"):
                    raise ValueError((result or {}).get("error") or "backtest_failed")
                sharpe = float(payload.get("sharpe_ratio") or payload.get("sharpe") or 0.0)
                sharpe_values.append(sharpe)
                if payload.get("total_return") is not None:
                    total_return_values.append(_safe_float(payload.get("total_return"), 0.0))
                if payload.get("turnover_proxy") is not None:
                    turnover_values.append(_safe_float(payload.get("turnover_proxy"), 0.0))
                if payload.get("trades_count") is not None:
                    trade_count_values.append(_safe_float(payload.get("trades_count"), 0.0))
                if payload.get("max_drawdown") is not None:
                    max_drawdown_values.append(abs(_safe_float(payload.get("max_drawdown"), 0.0)))
            except Exception as exc:
                errors.append(f"{code}:{type(exc).__name__}")

    if not sharpe_values:
        return GateResult(
            passed=False,
            gate="gate_1",
            reasons=["no_backtest_results", *errors],
            metrics={
                "tested_codes": tested_codes,
                "target_codes": prioritized_target_codes,
                "code_source": code_source,
                "validation_focus": validation_focus,
                "primary_validation_layer": (
                    "combined"
                    if validation_focus == "broad_generalization"
                    else "target"
                ),
                "validation_contract_mode": (
                    "portfolio_contract_fast_screen"
                    if len(tested_codes) > 1
                    else "single_code_fast_screen"
                ),
                "validation_scope": "fast_screen",
                "stage_role": "fast_screen",
                "contract_gate_status": "passed" if precompile_validation.contract_completeness_ok else "failed",
                "contract_gate": precompile_summary,
                "event_window_config": {
                    "event_window": dict(research_task.get("event_window") or {}),
                    "estimation_window": dict(research_task.get("estimation_window") or {}),
                    "holding_window": dict(research_task.get("holding_window") or {}),
                },
                "contamination_summary": {
                    "validation_focus": validation_focus,
                    "representative_included": bool([code for code in tested_codes if code not in prioritized_target_codes]),
                    "representative_code_count": len([code for code in tested_codes if code not in prioritized_target_codes]),
                },
                "candidate_contract_hash": contract_hash,
                "tested_object_hash": tested_object_hash,
                "candidate_contract_snapshot": contract_snapshot,
                "backtest_assumptions": assumptions.to_audit_dict(),
                "tested_code_count": len(tested_codes),
                "eligible_code_count": len(market_data),
                "sharpe_values": [],
            },
        )

    avg_sharpe = sum(sharpe_values) / len(sharpe_values)
    target_sample_count = len(prioritized_target_codes)
    research_target_count = len(_extract_target_codes_from_payload(candidate, limit=12))
    target_sample_ratio = round(target_sample_count / max(1, research_target_count), 4) if research_target_count > 0 else None

    # ══════════════════════════════════════════════════════════════════════════
    # 自适应门控评估（阶段 2-4 实现）
    # ══════════════════════════════════════════════════════════════════════════

    # ── 阶段 2: Benchmark-Relative Sharpe ──────────────────────────────────
    # 计算同期 Buy-and-Hold 基准收益
    benchmark_returns = []
    for code, klines in market_data.items():
        if klines and len(klines) >= 2:
            first_close = float(klines[0].get("close") or klines[0].get("Close") or 0)
            last_close = float(klines[-1].get("close") or klines[-1].get("Close") or 0)
            if first_close > 0:
                benchmark_returns.append(last_close / first_close - 1.0)
    avg_benchmark_return = sum(benchmark_returns) / len(benchmark_returns) if benchmark_returns else 0.0
    # 简化基准 Sharpe 估算：年化收益 / 假设波动率 15%
    trading_days = len(list(market_data.values())[0]) if market_data else 250
    annualization = 252.0 / max(trading_days, 1)
    benchmark_sharpe = (avg_benchmark_return * annualization) / 0.15 if avg_benchmark_return != 0 else 0.0
    excess_sharpe = avg_sharpe - benchmark_sharpe
    excess_sharpe_min = 0.10  # 策略需超越基准 0.10

    # ── 阶段 3: Regime-Aware 动态阈值 ─────────────────────────────────────
    if avg_benchmark_return > 0.10:
        regime = "bull"
        regime_sharpe_min = 0.30
    elif avg_benchmark_return < -0.05:
        regime = "bear"
        regime_sharpe_min = -0.50  # 熊市中亏得少就行
    else:
        regime = "neutral"
        regime_sharpe_min = 0.10

    # ── 阶段 4: 多维度综合评分 ─────────────────────────────────────────────
    multi_score = 0.0

    # 维度 1: 超额收益（30 分）
    avg_total_return = sum(total_return_values) / len(total_return_values) if total_return_values else 0.0
    excess_return = avg_total_return - avg_benchmark_return
    if excess_return > 0.05:
        multi_score += 30
    elif excess_return > 0.0:
        multi_score += 20
    elif excess_return > -0.03:
        multi_score += 10

    # 维度 2: 交易质量（25 分）— 有交易且 Sharpe 不是极端负值
    avg_trades = sum(trade_count_values) / len(trade_count_values) if trade_count_values else 0.0
    if avg_trades >= 3 and avg_sharpe > -1.0:
        multi_score += 25
    elif avg_trades >= 1:
        multi_score += 10

    # 维度 3: 风险控制（20 分）
    avg_mdd = sum(max_drawdown_values) / len(max_drawdown_values) if max_drawdown_values else 0.0
    if avg_mdd < 0.10:
        multi_score += 20
    elif avg_mdd < 0.20:
        multi_score += 12
    elif avg_mdd < 0.30:
        multi_score += 5

    # 维度 4: 相对表现（15 分）
    if excess_sharpe >= 0.20:
        multi_score += 15
    elif excess_sharpe >= 0.05:
        multi_score += 10
    elif excess_sharpe >= 0.0:
        multi_score += 5

    # 维度 5: 信号稳定性（10 分）
    if 3 <= avg_trades <= 50:
        multi_score += 10
    elif avg_trades > 0:
        multi_score += 5

    # ── 综合判定：三种方式任一通过即可 ─────────────────────────────────────
    passed_absolute = avg_sharpe >= sharpe_min                    # 原始绝对阈值
    passed_relative = excess_sharpe >= excess_sharpe_min          # 相对基准
    passed_regime = avg_sharpe >= regime_sharpe_min               # 市场状态自适应
    passed_multi = multi_score >= 45                              # 多维度综合

    passed = passed_absolute or passed_relative or passed_regime or passed_multi

    # 构建失败原因
    gate_1_reasons = []
    if not passed:
        gate_1_reasons.append(f"avg_sharpe_{avg_sharpe:.4f}_below_{sharpe_min}")
        gate_1_reasons.append(f"excess_sharpe_{excess_sharpe:.4f}_below_{excess_sharpe_min}")
        gate_1_reasons.append(f"regime_{regime}_sharpe_below_{regime_sharpe_min}")
        gate_1_reasons.append(f"multi_score_{multi_score:.0f}_below_45")

    return GateResult(
        passed=passed,
        gate="gate_1",
        reasons=gate_1_reasons,
        metrics={
            "tested_codes": tested_codes,
            "target_codes": prioritized_target_codes,
            "target_sample_count": target_sample_count,
            "research_target_count": research_target_count,
            "target_sample_ratio": target_sample_ratio,
            "code_source": code_source,
            "validation_focus": validation_focus,
            "primary_validation_layer": (
                "combined"
                if validation_focus == "broad_generalization"
                else "target"
            ),
            "validation_contract_mode": (
                "portfolio_contract_fast_screen"
                if len(tested_codes) > 1
                else "single_code_fast_screen"
            ),
            "validation_scope": "fast_screen",
            "stage_role": "fast_screen",
            "contract_gate_status": "passed" if precompile_validation.contract_completeness_ok else "failed",
            "contract_gate": precompile_summary,
            "tested_code_count": len(tested_codes),
            "eligible_code_count": len(market_data),
            "sharpe_values": [round(v, 4) for v in sharpe_values],
            "avg_sharpe": round(avg_sharpe, 4),
            "avg_total_return": round(avg_total_return, 6),
            "avg_turnover_proxy": round(sum(turnover_values) / len(turnover_values), 4) if turnover_values else 0.0,
            "avg_trades_count": round(avg_trades, 4),
            "avg_max_drawdown": round(avg_mdd, 6),
            "threshold": sharpe_min,
            # 自适应门控指标
            "adaptive_gate": {
                "benchmark_sharpe": round(benchmark_sharpe, 4),
                "excess_sharpe": round(excess_sharpe, 4),
                "excess_sharpe_min": excess_sharpe_min,
                "regime": regime,
                "regime_sharpe_min": regime_sharpe_min,
                "multi_score": round(multi_score, 1),
                "multi_score_threshold": 45,
                "passed_absolute": passed_absolute,
                "passed_relative": passed_relative,
                "passed_regime": passed_regime,
                "passed_multi": passed_multi,
                "avg_benchmark_return": round(avg_benchmark_return, 6),
            },
            "error_count": len(errors),
            "errors": errors,
            "candidate_contract_hash": contract_hash,
            "tested_object_hash": tested_object_hash,
            "candidate_contract_snapshot": contract_snapshot,
            "backtest_assumptions": assumptions.to_audit_dict(),
            "event_window_config": {
                "event_window": dict(research_task.get("event_window") or {}),
                "estimation_window": dict(research_task.get("estimation_window") or {}),
                "holding_window": dict(research_task.get("holding_window") or {}),
            },
            "contamination_summary": {
                "validation_focus": validation_focus,
                "representative_included": bool([code for code in tested_codes if code not in prioritized_target_codes]),
                "representative_code_count": len([code for code in tested_codes if code not in prioritized_target_codes]),
            },
        },
    )


# ---------------------------------------------------------------------------
# Pipeline: Gate-0 → Gate-1 → select top-K → Gate-2 (full backtest)
# ---------------------------------------------------------------------------

async def run_gated_filter(
    candidates: List[dict],
    db,
    backtest_filter,
    *,
    kline_cache: Optional[Dict[str, list]] = None,
) -> Dict[str, Any]:
    """执行 Gate-0 → Gate-1 → Gate-2 全流程。

    Returns dict with:
        passed: Gate-2 通过的候选列表
        gate_0_results: Gate-0 结果
        gate_1_results: Gate-1 结果
        gate_2_results: Gate-2 结果（BacktestFilter 报告）
    """
    # --- Gate-0 ---
    gate_0_passed: list[dict] = []
    gate_0_failed: list[dict] = []
    gate_0_batch_count = 0
    for start in range(0, len(candidates), _GATE_0_BATCH_SIZE):
        gate_0_batch_count += 1
        for candidate in candidates[start : start + _GATE_0_BATCH_SIZE]:
            prepared_candidate = apply_resolved_candidate_envelope(
                _enrich_legacy_gate_0_candidate(candidate)
            )
            candidate.clear()
            candidate.update(prepared_candidate)
            result = gate_0_structural(candidate)
            candidate["gate_0_result"] = {"passed": result.passed, "reasons": result.reasons}
            if result.passed:
                gate_0_passed.append(candidate)
            else:
                gate_0_failed.append(candidate)

    logger.info("Gate-0: %d/%d passed structural check", len(gate_0_passed), len(candidates))

    # --- Pre-Gate ---
    pre_gate_passed: list[dict] = []
    pre_gate_failed: list[dict] = []
    family_quota_limit = max(2, min(_PRE_GATE_FAMILY_QUOTA_DEFAULT, math.ceil(len(gate_0_passed) * 0.4))) if gate_0_passed else _PRE_GATE_FAMILY_QUOTA_DEFAULT
    per_stock_quota_limit = _PRE_GATE_PER_STOCK_QUOTA_DEFAULT
    if FACTORY_PRE_GATE_ENABLED:
        seen_signatures: set[str] = set()
        family_counts: dict[str, int] = {}
        stock_counts: dict[str, int] = {}
        for candidate in gate_0_passed:
            result = pre_gate_screen(
                candidate,
                seen_signatures=seen_signatures,
                family_counts=family_counts,
                stock_counts=stock_counts,
                family_quota_limit=family_quota_limit,
                per_stock_quota_limit=per_stock_quota_limit,
            )
            candidate["pre_gate_result"] = {
                "passed": result.passed,
                "reasons": result.reasons,
                "metrics": result.metrics,
            }
            if result.passed:
                pre_gate_passed.append(candidate)
            else:
                pre_gate_failed.append(candidate)
    else:
        pre_gate_passed = list(gate_0_passed)

    logger.info(
        "Pre-Gate: %d/%d passed cheap filter",
        len(pre_gate_passed),
        len(gate_0_passed),
    )

    # --- Gate-1 ---
    backtest_concurrency = int(_compat_setting("BACKTEST_CONCURRENCY", BACKTEST_CONCURRENCY) or BACKTEST_CONCURRENCY)
    sem = asyncio.Semaphore(backtest_concurrency)
    gate_1_preload_codes: list[str] = []
    gate_1_preload_status = "skipped"
    gate_1_kline_cache_ready = bool(kline_cache)
    if pre_gate_passed and hasattr(backtest_filter, "preload_klines"):
        gate_1_preload_codes = _collect_gate_1_preload_codes(pre_gate_passed)
        if gate_1_preload_codes:
            try:
                await backtest_filter.preload_klines(db, gate_1_preload_codes)
                refreshed_cache = getattr(backtest_filter, "_kline_cache", None)
                if refreshed_cache is not None:
                    kline_cache = refreshed_cache
                gate_1_kline_cache_ready = bool(kline_cache)
                gate_1_preload_status = "ready"
            except Exception as exc:
                # Retry with reduced scope (representative stocks only)
                try:
                    from ...domain.constants import REPRESENTATIVE_STOCKS as _REPR_STOCKS
                    await backtest_filter.preload_klines(db, list(_REPR_STOCKS))
                    refreshed_cache = getattr(backtest_filter, "_kline_cache", None)
                    if refreshed_cache is not None:
                        kline_cache = refreshed_cache
                    gate_1_kline_cache_ready = bool(kline_cache)
                    gate_1_preload_status = "partial_retry"
                except Exception:
                    gate_1_preload_status = f"failed:{type(exc).__name__}"
                logger.warning("Gate-1 preload failed for %d codes: %s", len(gate_1_preload_codes), exc)
        else:
            gate_1_preload_status = "no_codes"
    elif pre_gate_passed:
        gate_1_preload_status = "unsupported"
    elif FACTORY_PRE_GATE_ENABLED:
        gate_1_preload_status = "no_candidates"

    async def _screen_one(c: dict) -> tuple[dict, GateResult]:
        async with sem:
            try:
                return c, await _compat_gate_1_fast_screen(c, db, kline_cache=kline_cache)
            except Exception as exc:
                logger.warning("Gate-1 exception for %s: %s", c.get("strategy_type"), exc)
                return c, GateResult(
                    passed=False,
                    gate="gate_1",
                    reasons=[f"gate_1_exception:{type(exc).__name__}"],
                    metrics={"exception": str(exc)},
                )

    gate_1_tasks = [_screen_one(c) for c in pre_gate_passed]
    gate_1_raw = await asyncio.gather(*gate_1_tasks, return_exceptions=False)

    gate_1_scored: list[tuple[dict, float]] = []
    gate_1_failed: list[dict] = []
    for item in gate_1_raw:
        candidate, result = item
        candidate["gate_1_result"] = {
            "passed": result.passed,
            "reasons": result.reasons,
            "metrics": result.metrics,
        }
        if result.passed:
            avg_sharpe = float(result.metrics.get("avg_sharpe") or 0.0)
            candidate["gate_1_result"]["metrics"]["target_quality_summary"] = build_target_quality_gate_summary(
                candidate,
                gate_1_metrics=result.metrics,
            )
            block_reason = _post_gate_1_target_quality_block_reason(candidate, avg_sharpe)
            if block_reason:
                candidate["gate_1_result"]["passed"] = False
                candidate["gate_1_result"]["reasons"] = list(
                    dict.fromkeys([*(result.reasons or []), block_reason])
                )
                candidate["gate_1_result"]["metrics"]["post_gate_1_target_quality_block_reason"] = block_reason
                gate_1_failed.append(candidate)
                continue
            priority_score, priority_meta = _gate_2_priority_score(candidate, avg_sharpe, return_meta=True)
            candidate["gate_1_result"]["metrics"]["gate_2_priority_score"] = priority_score
            candidate["gate_1_result"]["metrics"]["gate_2_priority_meta"] = priority_meta
            gate_1_scored.append((candidate, priority_score))
        else:
            gate_1_failed.append(candidate)

    # 按综合优先级排序，进入 Gate-2 优先队列。
    gate_1_scored.sort(key=lambda x: x[1], reverse=True)
    gate1_pass_ratio = float(_compat_setting("GATE1_PASS_RATIO", GATE1_PASS_RATIO) or GATE1_PASS_RATIO)
    top_k = _resolve_gate_2_top_k(len(gate_1_scored), gate1_pass_ratio)
    gate_2_candidates = _select_gate_2_candidates(gate_1_scored, top_k)

    logger.info(
        "Gate-1: %d/%d passed fast screen, top-%d enter Gate-2 priority queue",
        len(gate_1_scored), len(pre_gate_passed), len(gate_2_candidates),
    )

    # --- Gate-2 (full backtest via BacktestFilter) ---
    if gate_2_candidates:
        gate_2_passed = await backtest_filter.filter(gate_2_candidates, db)
    else:
        gate_2_passed = []

    logger.info("Gate-2: %d/%d passed full backtest", len(gate_2_passed), len(gate_2_candidates))

    summary = {
        "input_count": len(candidates),
        "gate_0_passed": len(gate_0_passed),
        "gate_0_failed": len(gate_0_failed),
        "gate_0_batch_size": _GATE_0_BATCH_SIZE,
        "gate_0_batch_count": gate_0_batch_count,
        "pre_gate_passed": len(pre_gate_passed),
        "pre_gate_failed": len(pre_gate_failed),
        "gate_1_passed": len(gate_1_scored),
        "gate_1_failed": len(gate_1_failed),
        "gate_1_preload_code_count": len(gate_1_preload_codes),
        "gate_1_kline_cache_ready": gate_1_kline_cache_ready,
        "gate_2_input": len(gate_2_candidates),
        "gate_2_passed": len(gate_2_passed),
        "gate_3_pending": len(gate_2_passed),
    }
    gate_0_failed_details = [
        {"strategy_type": c.get("strategy_type"), "reasons": (c.get("gate_0_result") or {}).get("reasons")}
        for c in gate_0_failed[:COMPACT_PREVIEW_LIMIT]
    ]
    gate_1_failed_details = [
        {
            "strategy_type": c.get("strategy_type"),
            "reasons": (c.get("gate_1_result") or {}).get("reasons"),
            "metrics": (c.get("gate_1_result") or {}).get("metrics") or {},
        }
        for c in gate_1_failed[:COMPACT_PREVIEW_LIMIT]
    ]
    pre_gate_failed_details = [
        {
            "strategy_type": c.get("strategy_type"),
            "reasons": (c.get("pre_gate_result") or {}).get("reasons"),
            "metrics": (c.get("pre_gate_result") or {}).get("metrics") or {},
        }
        for c in pre_gate_failed[:COMPACT_PREVIEW_LIMIT]
    ]
    gate_2_report = _compact_backtest_report_for_gate(
        backtest_filter.get_last_report() if hasattr(backtest_filter, "get_last_report") else {}
    )
    gate_report = {
        "gate_0": {
            "passed_count": len(gate_0_passed),
            "failed_count": len(gate_0_failed),
            "batch_size": _GATE_0_BATCH_SIZE,
            "batch_count": gate_0_batch_count,
            "failed": gate_0_failed_details,
            "failed_preview_count": len(gate_0_failed_details),
        },
        "pre_gate": {
            "status": "completed" if FACTORY_PRE_GATE_ENABLED else "disabled",
            "passed_count": len(pre_gate_passed),
            "failed_count": len(pre_gate_failed),
            "failed": pre_gate_failed_details,
            "failed_preview_count": len(pre_gate_failed_details),
            "limits": {
                "family_quota_limit": family_quota_limit if FACTORY_PRE_GATE_ENABLED else None,
                "per_stock_quota_limit": per_stock_quota_limit if FACTORY_PRE_GATE_ENABLED else None,
                "signal_density_min": _PRE_GATE_SIGNAL_DENSITY_MIN if FACTORY_PRE_GATE_ENABLED else None,
                "signal_density_max": _PRE_GATE_SIGNAL_DENSITY_MAX if FACTORY_PRE_GATE_ENABLED else None,
            },
        },
        "gate_1": {
            "passed_count": len(gate_1_scored),
            "failed_count": len(gate_1_failed),
            "selection_mode": "priority_queue",
            "preload_status": gate_1_preload_status,
            "preload_code_count": len(gate_1_preload_codes),
            "kline_cache_ready": gate_1_kline_cache_ready,
            "failed": gate_1_failed_details,
            "failed_preview_count": len(gate_1_failed_details),
            "passed_candidates": [
                _compact_gate_candidate_brief(candidate, score=round(score, 4))
                for candidate, score in gate_1_scored[:COMPACT_PREVIEW_LIMIT]
            ],
            "passed_candidates_count": len(gate_1_scored),
            "passed_candidates_is_brief": True,
        },
        "gate_2": {
            "input_count": len(gate_2_candidates),
            "passed_count": len(gate_2_passed),
            "selection_mode": "priority_queue",
            "passed_candidates": [
                _compact_gate_candidate_brief(candidate)
                for candidate in gate_2_passed[:COMPACT_PREVIEW_LIMIT]
            ],
            "passed_candidates_count": len(gate_2_passed),
            "passed_candidates_is_brief": True,
            "report": gate_2_report,
        },
        "gate_3": build_pending_gate_3_report(len(gate_2_passed)),
        "final_decision": {
            "stage": "gate_2",
            "passed_count": len(gate_2_passed),
            "pending_submission_gate_count": len(gate_2_passed),
        },
    }

    gate_report = _compact_quality_gate_report(gate_report)

    return {
        "passed": gate_2_passed,
        "summary": summary,
        "gate_0_failed": gate_0_failed_details,
        "pre_gate_failed": pre_gate_failed_details,
        "quality_gate": gate_report,
        "gate_report": gate_report,
    }
