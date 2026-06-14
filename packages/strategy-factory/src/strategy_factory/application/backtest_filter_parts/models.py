
    async def _test_one(self, candidate: dict, db, engine) -> dict:
        candidate = apply_resolved_candidate_envelope(candidate)
        factory_pkg = _get_strategy_factory_package()
        strategy_type = str(candidate.get("strategy_type") or "unknown")
        thresholds = self._get_thresholds(strategy_type, candidate)
        results: List[dict] = []
        successful_codes: List[str] = []
        skipped_codes: List[dict] = []
        failed_codes: List[dict] = []
        evaluated_codes, target_codes, representative_codes, code_source, validation_focus = self._resolve_backtest_plan(candidate)
        contract_snapshot = build_portfolio_candidate_contract(candidate)
        contract_hash = build_candidate_contract_hash(contract=contract_snapshot)
        execution_contract_hash = str(candidate.get("execution_contract_hash") or "").strip() or contract_hash
        tested_object_hash = str(candidate.get("tested_object_hash") or "").strip() or build_tested_object_hash(candidate)
        candidate_identity_signature = str(candidate.get("candidate_identity_signature") or "").strip()
        assumptions = self._build_backtest_assumptions(candidate)
        assumptions_kwargs = assumptions.to_backtest_kwargs()
        research_task = _normalize_research_task_contract(candidate.get("research_task"))
        has_explicit_research_task = _has_explicit_research_task(candidate)
        required_sample_count = _resolve_required_sample_count(
            candidate,
            thresholds=thresholds,
            research_task=research_task,
            validation_focus=validation_focus,
            target_codes=target_codes,
        )
        target_set = set(target_codes)
        layer_results: Dict[str, List[dict]] = {"target": [], "representative": []}
        layer_successful_codes: Dict[str, List[str]] = {"target": [], "representative": []}
        candidate_started_at = time.perf_counter()

        async def _run_one_code(code: str) -> dict:
            layer = "target" if code in target_set else "representative"
            started_at = time.perf_counter()
            cache_hit = False
            try:
                klines = self._kline_cache.get(code)
                if klines is not None:
                    cache_hit = True
                else:
                    klines = await db.get_klines(code, limit=500)
                    self._kline_cache[code] = klines or []
                if not klines or len(klines) < 100:
                    return {
                        "code": code,
                        "layer": layer,
                        "status": "skipped",
                        "reason": "insufficient_klines",
                        "available": len(klines or []),
                        "cache_hit": cache_hit,
                        "run_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    }
                try:
                    # PR-S1: 单只股票回测超时保护，命中后该 code 计入 failed，释放并发槽
                    _backtest_timeout = float(
                        _compat_setting(
                            "BACKTEST_CODE_TIMEOUT_SEC",
                            BACKTEST_CODE_TIMEOUT_SEC,
                        )
                        or BACKTEST_CODE_TIMEOUT_SEC
                    )
                    result = await asyncio.wait_for(
                        factory_pkg.asyncio.to_thread(
                            engine.run_backtest,
                            code,
                            klines,
                            candidate["strategy_type"],
                            {
                                **_ensure_strategy_params(
                                    candidate["strategy_type"],
                                    candidate["params"],
                                    research_task=candidate.get("research_task"),
                                ),
                                **assumptions_kwargs,
                            },
                            True,
                        ),
                        timeout=_backtest_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "BacktestFilter code backtest timed out strategy_type=%s code=%s timeout=%.1fs",
                        candidate.get("strategy_type"),
                        code,
                        _backtest_timeout,
                    )
                    return {
                        "code": code,
                        "layer": layer,
                        "status": "failed",
                        "reason": "timeout",
                        "timeout_sec": _backtest_timeout,
                        "cache_hit": cache_hit,
                        "run_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    }
                if result.get("success"):
                    return {
                        "code": code,
                        "layer": layer,
                        "status": "success",
                        "data": result["data"],
                        "cache_hit": cache_hit,
                        "run_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    }
                return {
                    "code": code,
                    "layer": layer,
                    "status": "failed",
                    "reason": "backtest_failed",
                    "cache_hit": cache_hit,
                    "run_ms": round((time.perf_counter() - started_at) * 1000, 2),
                }
            except Exception as exc:
                logger.warning(
                    "BacktestFilter code backtest failed strategy_type=%s code=%s error=%s",
                    candidate.get("strategy_type"),
                    code,
                    exc,
                    exc_info=exc,
                )
                return {
                    "code": code,
                    "layer": layer,
                    "status": "failed",
                    "reason": f"exception:{type(exc).__name__}",
                    "cache_hit": cache_hit,
                    "run_ms": round((time.perf_counter() - started_at) * 1000, 2),
                }

        code_concurrency = int(_compat_setting("BACKTEST_CODE_CONCURRENCY", BACKTEST_CODE_CONCURRENCY) or BACKTEST_CODE_CONCURRENCY)
        code_sem = asyncio.Semaphore(code_concurrency)

        async def _run_guarded(code: str) -> dict:
            async with code_sem:
                return await _run_one_code(code)

        code_results = await asyncio.gather(*[_run_guarded(code) for code in evaluated_codes])
        code_run_ms_total = 0.0
        kline_cache_hit_count = 0
        for item in code_results:
            code_run_ms_total += float(item.get("run_ms") or 0.0)
            if item.get("cache_hit"):
                kline_cache_hit_count += 1
            layer = str(item.get("layer") or "representative")
            code = str(item.get("code") or "")
            if item.get("status") == "success":
                result_data = dict(item.get("data") or {})
                result_data = self._merge_trade_profile_metrics(result_data)
                results.append(result_data)
                layer_results[layer].append(result_data)
                successful_codes.append(code)
                layer_successful_codes[layer].append(code)
            elif item.get("status") == "skipped":
                skipped_codes.append({
                    "code": code,
                    "reason": item.get("reason"),
                    "available": item.get("available", 0),
                    "layer": layer,
                })
            else:
                failed_codes.append({"code": code, "reason": item.get("reason"), "layer": layer})

        target_portfolio_metrics = await self._run_portfolio_engine_summary(
            candidate=candidate,
            engine=engine,
            codes=layer_successful_codes["target"],
            assumptions=assumptions,
        )
        combined_portfolio_metrics = await self._run_portfolio_engine_summary(
            candidate=candidate,
            engine=engine,
            codes=successful_codes,
            assumptions=assumptions,
        )

        target_metrics = target_portfolio_metrics or self._summarize_result_set(
            layer_results["target"],
            target_weight_scheme=assumptions.target_weight_scheme,
            initial_capital=assumptions.initial_capital,
            target_weight_map=assumptions.target_weight_map,
        )
        representative_metrics = self._summarize_result_set(
            layer_results["representative"],
            target_weight_scheme=assumptions.target_weight_scheme,
            initial_capital=assumptions.initial_capital,
        )
        combined_metrics = combined_portfolio_metrics or self._summarize_result_set(
            results,
            target_weight_scheme=assumptions.target_weight_scheme,
            initial_capital=assumptions.initial_capital,
            target_weight_map=assumptions.target_weight_map,
        )
        target_trade_profile = self._aggregate_trade_profile_metrics(
            layer_results["target"],
            initial_capital=assumptions.initial_capital,
        )
        representative_trade_profile = self._aggregate_trade_profile_metrics(
            layer_results["representative"],
            initial_capital=assumptions.initial_capital,
        )
        combined_trade_profile = self._aggregate_trade_profile_metrics(
            results,
            initial_capital=assumptions.initial_capital,
        )
        if target_metrics and not target_metrics.get("trade_profile_available"):
            target_metrics = {**target_metrics, **target_trade_profile}
        if representative_metrics and not representative_metrics.get("trade_profile_available"):
            representative_metrics = {**representative_metrics, **representative_trade_profile}
        if combined_metrics and not combined_metrics.get("trade_profile_available"):
            combined_metrics = {**combined_metrics, **combined_trade_profile}
        event_window_metrics = self._build_event_window_metrics(
            candidate=candidate,
            target_results=layer_results["target"],
            representative_results=layer_results["representative"],
            fallback_results=results,
            research_task=research_task,
            target_weight_scheme=assumptions.target_weight_scheme,
            initial_capital=assumptions.initial_capital,
            target_weight_map=assumptions.target_weight_map,
        )
        if validation_focus == "event_target_only":
            primary_results = layer_results["target"]
            primary_layer = "target"
        elif validation_focus == "broad_generalization":
            primary_results = results
            primary_layer = "combined"
        else:
            primary_results = layer_results["target"] if layer_results["target"] else results
            primary_layer = "target" if layer_results["target"] else "combined"
        primary_metrics_payload = (
            target_metrics
            if primary_layer == "target"
            else combined_metrics
        )
        if primary_layer == "target" and not target_metrics:
            primary_metrics_payload = combined_metrics
        sample_audit = (
            dict(primary_metrics_payload or {})
            if bool((primary_metrics_payload or {}).get("portfolio_engine_used"))
            else (dict(primary_results[0] or {}) if primary_results else (dict(results[0] or {}) if results else {}))
        )
        event_window_config = {
            "event_window": dict(research_task.get("event_window") or {}),
            "estimation_window": dict(research_task.get("estimation_window") or {}),
            "holding_window": dict(research_task.get("holding_window") or {}),
        }
        contamination_summary = {
            "validation_focus": validation_focus,
            "target_code_count": len(target_codes),
            "representative_code_count": len([code for code in evaluated_codes if code not in target_set]),
            "representative_included": bool([code for code in evaluated_codes if code not in target_set]),
            "mixed_layer_used": primary_layer == "combined",
        }

        def _finalize_result(result_payload: dict[str, Any]) -> dict[str, Any]:
            payload = dict(result_payload or {})
            payload["target_quality_summary"] = build_target_quality_gate_summary(
                candidate,
                backtest_result=payload,
            )
            payload["backtest_metrics_contract"] = self._build_backtest_metrics_contract(candidate, payload)
            payload["backtest_metrics_contract_status"] = str(
                dict(payload.get("backtest_metrics_contract") or {}).get("status") or "missing"
            ).strip().lower() or "missing"
            return payload

        base_result = {
            "passed": False,
            "reason_code": "unknown",
            "reason": "初筛回测未完成",
            "strategy_type": strategy_type,
            "sample_count": len(primary_results),
            "required_sample_count": required_sample_count,
            "evaluated_code_count": len(evaluated_codes),
            "successful_code_count": len(successful_codes),
            "evaluated_codes": evaluated_codes,
            "successful_codes": successful_codes,
            "target_codes": target_codes,
            "representative_codes": representative_codes,
            "code_source": code_source,
            "primary_layer": primary_layer,
            "primary_validation_layer": primary_layer,
            "validation_focus": validation_focus,
            "candidate_contract_hash": contract_hash,
            "execution_contract_hash": execution_contract_hash,
            "tested_object_hash": tested_object_hash,
            "candidate_identity_signature": candidate_identity_signature or None,
            "candidate_contract_snapshot": contract_snapshot,
            "logic_signature": str(candidate.get("logic_signature") or "").strip() or None,
            "dsl_signature": str(candidate.get("dsl_signature") or "").strip() or None,
            "factor_signature": str(candidate.get("factor_signature") or "").strip() or None,
            "entry_exit_signature": str(candidate.get("entry_exit_signature") or "").strip() or None,
            "queue_wait_ms": 0.0,
            "backtest_run_ms": round((time.perf_counter() - candidate_started_at) * 1000, 2),
            "code_run_ms_total": round(code_run_ms_total, 2),
            "code_run_count": len(code_results),
            "avg_code_ms": round(code_run_ms_total / len(code_results), 2) if code_results else 0.0,
            "kline_cache_hit_count": kline_cache_hit_count,
            "skipped_codes": skipped_codes,
            "failed_codes": failed_codes,
            "thresholds": thresholds,
            "constraint_check": dict(candidate.get("constraint_check") or {}),
            "event_window_config": event_window_config,
            "contamination_summary": contamination_summary,
            "cost_assumptions": dict(sample_audit.get("cost_assumptions") or {}),
            "explicit_cost_breakdown": dict(sample_audit.get("explicit_cost_breakdown") or {}),
            "implicit_cost_breakdown": dict(sample_audit.get("implicit_cost_breakdown") or {}),
            "tradability_summary": dict(sample_audit.get("tradability_summary") or {}),
            "capacity_summary": dict(sample_audit.get("capacity_summary") or {}),
            "economic_semantics": {
                "holding_rationale": candidate.get("holding_rationale"),
                "alpha_half_life": candidate.get("alpha_half_life"),
                "market_regime_assumption": candidate.get("market_regime_assumption"),
                "position_sizing_rationale": candidate.get("position_sizing_rationale"),
                "capacity_bucket": candidate.get("capacity_bucket")
                or dict(candidate.get("execution_assumptions") or {}).get("capacity_bucket"),
                "turnover_cost_class": candidate.get("turnover_cost_class")
                or dict(candidate.get("execution_assumptions") or {}).get("turnover_cost_class"),
                "expected_turnover_band": candidate.get("expected_turnover_band")
                or dict(candidate.get("holding_horizon") or {}).get("expected_turnover_band"),
                "economic_semantics_score": candidate.get("economic_semantics_score"),
                "economic_semantics_missing_fields": list(
                    candidate.get("economic_semantics_missing_fields") or []
                ),
            },
            "implementation_shortfall_model_source": sample_audit.get("implementation_shortfall_model_source"),
            "implementation_shortfall_components": dict(sample_audit.get("implementation_shortfall_components") or {}),
            "position_assumption": sample_audit.get("position_assumption"),
            "backtest_assumptions": assumptions.to_audit_dict(),
            "portfolio_backtest_mode": (
                "portfolio_engine_shared_cash"
                if bool((primary_metrics_payload or {}).get("portfolio_engine_used"))
                else (
                    "weighted_multi_name"
                    if assumptions.target_weight_scheme != "single_name" and len(target_codes) > 1
                    else "single_name"
                )
            ),
            "portfolio_backtest_coverage": (
                1.0
                if bool((primary_metrics_payload or {}).get("portfolio_engine_used"))
                else (
                    1.0
                    if assumptions.target_weight_scheme != "single_name" and len(target_codes) > 1 and bool(target_metrics)
                    else 0.0
                )
            ),
                "layers": {
                    "target": {
                        "requested_codes": target_codes,
                        "successful_codes": layer_successful_codes["target"],
                        "sample_count": len(layer_results["target"]),
                        "metrics": target_metrics,
                        "trade_profile": target_trade_profile,
                        "metrics_source": "portfolio_engine" if target_portfolio_metrics else "proxy_aggregation",
                    },
                    "representative": {
                        "requested_codes": representative_codes,
                        "successful_codes": layer_successful_codes["representative"],
                        "sample_count": len(layer_results["representative"]),
                        "metrics": representative_metrics,
                        "trade_profile": representative_trade_profile,
                        "metrics_source": "proxy_aggregation",
                    },
                    "combined": {
                        "requested_codes": evaluated_codes,
                        "successful_codes": successful_codes,
                        "sample_count": len(results),
                        "metrics": combined_metrics,
                        "trade_profile": combined_trade_profile,
                        "metrics_source": "portfolio_engine" if combined_portfolio_metrics else "proxy_aggregation",
                    },
                },
            "event_window_metrics": dict(event_window_metrics or target_metrics or combined_metrics),
            "metrics": {},
            "failed_metric": None,
        }

        primary_successful_codes = (
            list(layer_successful_codes["target"])
            if primary_layer == "target"
            else list(successful_codes)
        )
        if (
            has_explicit_research_task
            and
            assumptions.target_weight_scheme != "single_name"
            and len(primary_successful_codes) > 1
            and not bool((primary_metrics_payload or {}).get("portfolio_engine_used"))
        ):
            return _finalize_result({
                **base_result,
                "reason_code": "portfolio_engine_required",
                "reason": "多标的验证未获得真实组合回测结果",
                "failed_metric": self._build_failed_metric(
                    "portfolio_backtest_coverage",
                    "<",
                    1.0,
                    round(float(base_result.get("portfolio_backtest_coverage") or 0.0), 4),
                    "组合回测覆盖度",
                ),
            })

        if (
            str(research_task.get("task_source") or "").strip().lower() == "event_driven"
            and bool((event_window_metrics or {}).get("event_audit_incomplete"))
        ):
            return _finalize_result({
                **base_result,
                "reason_code": "event_audit_incomplete",
                "reason": "事件验证仅有最小样本代理，缺少正式事件审计证据",
                "failed_metric": self._build_failed_metric(
                    "event_audit_incomplete",
                    "==",
                    False,
                    bool((event_window_metrics or {}).get("event_audit_incomplete")),
                    "事件审计完整性",
                ),
            })

        if (
            str(research_task.get("task_source") or "").strip().lower() == "event_driven"
            and not bool((event_window_metrics or {}).get("traceable_to_event_samples"))
        ):
            return _finalize_result({
                **base_result,
                "reason_code": "event_samples_required",
                "reason": "事件验证缺少可追溯事件样本",
                "failed_metric": self._build_failed_metric(
                    "event_sample_count",
                    ">",
                    0,
                    int((event_window_metrics or {}).get("event_sample_count") or 0),
                    "事件样本数",
                ),
            })

        if len(primary_results) < required_sample_count:
            return _finalize_result({
                **base_result,
                "reason_code": "insufficient_samples",
                "reason": f"有效样本 {len(primary_results)} 小于要求 {required_sample_count}",
                "failed_metric": self._build_failed_metric("sample_count", "<", required_sample_count, len(primary_results), "有效样本数"),
            })

        avg = (
            dict(primary_metrics_payload or {})
            if bool((primary_metrics_payload or {}).get("portfolio_engine_used"))
            else self._summarize_result_set(
                primary_results,
                target_weight_scheme=assumptions.target_weight_scheme,
                initial_capital=assumptions.initial_capital,
                target_weight_map=assumptions.target_weight_map,
            )
        )

        # ══════════════════════════════════════════════════════════════════
        # Gate-2 自适应评估
        # ══════════════════════════════════════════════════════════════════
        if avg and not bool(avg.get("trade_profile_available")):
            avg = {
                **avg,
                **self._aggregate_trade_profile_metrics(
                    primary_results,
                    initial_capital=assumptions.initial_capital,
                ),
            }

        strategy_sharpe = float(avg.get("sharpe_ratio", 0))
        strategy_return = float(avg.get("total_return", 0))
        strategy_trades = float(avg.get("trades_count", 0))
        strategy_mdd = abs(float(avg.get("max_drawdown", 0)))

        # 基准收益估算（从回测结果中提取）
        benchmark_returns_g2 = []
        for pr in primary_results:
            pr_data = pr.get("data") or {}
            bh = pr_data.get("buy_hold_return") or pr_data.get("benchmark_return")
            if bh is not None:
                benchmark_returns_g2.append(float(bh))
        avg_benchmark_return_g2 = (
            sum(benchmark_returns_g2) / len(benchmark_returns_g2)
            if benchmark_returns_g2
            else 0.0
        )

        # 市场状态
        if avg_benchmark_return_g2 > 0.10:
            regime_g2 = "bull"
            regime_sharpe_min_g2 = thresholds["sharpe_min"]
        elif avg_benchmark_return_g2 < -0.05:
            regime_g2 = "bear"
            regime_sharpe_min_g2 = -0.30
        else:
            regime_g2 = "neutral"
            regime_sharpe_min_g2 = 0.05

        # 超额 Sharpe
        benchmark_sharpe_g2 = avg_benchmark_return_g2 * 4.0  # 简化年化
        excess_sharpe_g2 = strategy_sharpe - benchmark_sharpe_g2

        # 多维度评分
        multi_score_g2 = 0.0
        excess_return_g2 = strategy_return - avg_benchmark_return_g2
        if excess_return_g2 > 0.05:
            multi_score_g2 += 30
        elif excess_return_g2 > 0.0:
            multi_score_g2 += 20
        elif excess_return_g2 > -0.03:
            multi_score_g2 += 10
        if strategy_trades >= thresholds["trades_min"] and strategy_sharpe > -1.0:
            multi_score_g2 += 25
        elif strategy_trades >= 1:
            multi_score_g2 += 10
        if strategy_mdd < thresholds["mdd_max"] * 0.5:
            multi_score_g2 += 20
        elif strategy_mdd < thresholds["mdd_max"]:
            multi_score_g2 += 12
        if excess_sharpe_g2 >= 0.20:
            multi_score_g2 += 15
        elif excess_sharpe_g2 >= 0.0:
            multi_score_g2 += 8
        if thresholds["trades_min"] <= strategy_trades <= 80:
            multi_score_g2 += 10

        # 软预筛:把 win_rate / profit_factor 纳入多维评分(observe-first 宽进下不硬淘汰,
        # 让交易质量双低的候选评分自然被压低、更难达 50 分线)。
        # 仅在指标真实可得(present_real)时计分;缺数据(0/无交易)不加不减,避免误伤缺数据候选。
        strategy_win_rate = float(avg.get("win_rate", 0) or 0)
        strategy_profit_factor = float(avg.get("profit_factor", 0) or 0)
        quality_score_g2 = 0.0
        if strategy_win_rate > 0:
            if strategy_win_rate >= 0.45:
                quality_score_g2 += 10
            elif strategy_win_rate >= 0.38:
                quality_score_g2 += 6
            elif strategy_win_rate >= 0.30:
                quality_score_g2 += 2
        if strategy_profit_factor > 0:
            if strategy_profit_factor >= 1.8:
                quality_score_g2 += 8
            elif strategy_profit_factor >= 1.3:
                quality_score_g2 += 5
            elif strategy_profit_factor >= 1.0:
                quality_score_g2 += 2
        multi_score_g2 += quality_score_g2

        # 综合判定（任一通过即可）
        passed_absolute_g2 = strategy_sharpe >= thresholds["sharpe_min"]
        passed_relative_g2 = excess_sharpe_g2 >= 0.15
        passed_regime_g2 = strategy_sharpe >= regime_sharpe_min_g2
        passed_multi_g2 = multi_score_g2 >= 50
        gate_2_passed = passed_absolute_g2 or passed_relative_g2 or passed_regime_g2 or passed_multi_g2

        # 硬约束
        if strategy_mdd > thresholds["mdd_max"]:
            gate_2_passed = False
        if strategy_trades < thresholds["trades_min"]:
            gate_2_passed = False

        avg["adaptive_gate_2"] = {
            "regime": regime_g2,
            "multi_score": round(multi_score_g2, 1),
            "quality_score": round(quality_score_g2, 1),
            "win_rate": round(strategy_win_rate, 4),
            "profit_factor": round(strategy_profit_factor, 4),
            "passed_absolute": passed_absolute_g2,
            "passed_relative": passed_relative_g2,
            "passed_regime": passed_regime_g2,
            "passed_multi": passed_multi_g2,
        }

        if not gate_2_passed:
            reason_parts = []
            if strategy_mdd > thresholds["mdd_max"]:
                reason_parts.append(f"mdd={strategy_mdd:.4f}>{thresholds['mdd_max']}")
            elif strategy_trades < thresholds["trades_min"]:
                reason_parts.append(f"trades={strategy_trades:.0f}<{thresholds['trades_min']}")
            else:
                reason_parts.append(f"sharpe={strategy_sharpe:.4f},regime={regime_g2},score={multi_score_g2:.0f}")
            return _finalize_result({
                **base_result,
                "reason_code": "adaptive_gate_2_failed",
                "reason": f"自适应评估未通过: {';'.join(reason_parts)}",
                "metrics": avg,
                "failed_metric": self._build_failed_metric("adaptive_score", "<", 50, round(multi_score_g2, 1), "自适应综合评分"),
            })

        return _finalize_result({
            **base_result,
            "passed": True,
            "reason_code": "passed",
            "reason": "通过初筛回测",
            "metrics": avg,
        })
