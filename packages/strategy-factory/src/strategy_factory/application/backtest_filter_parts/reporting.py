
    @staticmethod
    def _finite_float(value: Any, default: float = 0.0) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return float(default)
        if not np.isfinite(result):
            return float(default)
        return float(result)

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        arr = np.asarray(values, dtype=float)
        arr = arr[np.isfinite(arr)]
        if arr.size <= 0:
            return 0.0
        return float(np.percentile(arr, percentile))

    @classmethod
    def _trade_profile_from_round_trips(
        cls,
        round_trips: Any,
        *,
        initial_capital: float = 100000.0,
    ) -> dict[str, Any]:
        rows = [dict(item or {}) for item in list(round_trips or []) if isinstance(item, dict)]
        closed_rows = [
            item
            for item in rows
            if str(item.get("status") or "").strip().lower() in {"", "closed"}
        ]
        if not closed_rows:
            return {
                "trade_profile_available": False,
                "trade_profile_source": "round_trip_positions",
                "trade_distribution": {
                    "available": False,
                    "source": "round_trip_positions",
                    "sample_count": 0,
                },
            }

        pnl_values = [cls._finite_float(item.get("realized_pnl")) for item in closed_rows]
        return_values = [
            cls._finite_float(item.get("realized_return"))
            for item in closed_rows
            if item.get("realized_return") is not None
        ]
        if not return_values and initial_capital > 0:
            return_values = [pnl / float(initial_capital) for pnl in pnl_values]
        holding_days = [
            cls._finite_float(item.get("hold_days"))
            for item in closed_rows
            if item.get("hold_days") is not None
        ]
        wins = [value for value in pnl_values if value > 0]
        losses = [value for value in pnl_values if value < 0]
        flats = [value for value in pnl_values if value == 0]
        gross_profit = float(sum(wins))
        gross_loss = float(abs(sum(losses)))
        profit_factor = 999.0 if gross_loss <= 0 and gross_profit > 0 else (gross_profit / gross_loss if gross_loss > 0 else 0.0)
        expectancy = float(sum(pnl_values) / len(pnl_values)) if pnl_values else 0.0
        expectancy_return = float(sum(return_values) / len(return_values)) if return_values else 0.0
        avg_win = float(sum(wins) / len(wins)) if wins else 0.0
        avg_loss = float(abs(sum(losses) / len(losses))) if losses else 0.0
        payoff_ratio = float(avg_win / avg_loss) if avg_win > 0 and avg_loss > 0 else 0.0
        win_rate = float(len(wins) / len(pnl_values)) if pnl_values else 0.0
        breakeven_win_rate = float(avg_loss / (avg_win + avg_loss)) if (avg_win + avg_loss) > 0 else 0.0
        return {
            "trade_profile_available": True,
            "trade_profile_source": "round_trip_positions",
            "trade_count": int(len(pnl_values)),
            "trades_count": int(len(pnl_values)),
            "closed_round_trip_count": int(len(pnl_values)),
            "win_rate": round(win_rate, 6),
            "profit_factor": round(profit_factor, 6),
            "expectancy": round(expectancy, 6),
            "expectancy_return": round(expectancy_return, 6),
            "avg_win": round(avg_win, 6),
            "avg_loss": round(avg_loss, 6),
            "payoff_ratio": round(payoff_ratio, 6),
            "breakeven_win_rate": round(breakeven_win_rate, 6),
            "gross_profit": round(gross_profit, 6),
            "gross_loss": round(gross_loss, 6),
            "trade_distribution": {
                "available": True,
                "source": "round_trip_positions",
                "sample_count": int(len(pnl_values)),
                "win_count": int(len(wins)),
                "loss_count": int(len(losses)),
                "flat_count": int(len(flats)),
                "pnl_mean": round(float(np.mean(pnl_values)), 6),
                "pnl_median": round(float(np.median(pnl_values)), 6),
                "pnl_std": round(float(np.std(pnl_values)), 6),
                "pnl_min": round(float(min(pnl_values)), 6),
                "pnl_max": round(float(max(pnl_values)), 6),
                "pnl_p10": round(cls._percentile(pnl_values, 10), 6),
                "pnl_p25": round(cls._percentile(pnl_values, 25), 6),
                "pnl_p75": round(cls._percentile(pnl_values, 75), 6),
                "pnl_p90": round(cls._percentile(pnl_values, 90), 6),
                "return_mean": round(float(np.mean(return_values)), 6) if return_values else 0.0,
                "return_median": round(float(np.median(return_values)), 6) if return_values else 0.0,
                "return_p10": round(cls._percentile(return_values, 10), 6) if return_values else 0.0,
                "return_p90": round(cls._percentile(return_values, 90), 6) if return_values else 0.0,
                "avg_holding_days": round(float(np.mean(holding_days)), 6) if holding_days else 0.0,
                "holding_days_p50": round(cls._percentile(holding_days, 50), 6) if holding_days else 0.0,
                "holding_days_p90": round(cls._percentile(holding_days, 90), 6) if holding_days else 0.0,
            },
        }

    @classmethod
    def _trade_profile_from_trades(
        cls,
        trades: Any,
        *,
        initial_capital: float = 100000.0,
    ) -> dict[str, Any]:
        rows = [dict(item or {}) for item in list(trades or []) if isinstance(item, dict)]
        exit_rows = [
            item
            for item in rows
            if int(cls._finite_float(item.get("signal"), 0.0)) < 0
            or str(item.get("action") or "").strip().lower() in {"exit", "reduce", "sell"}
            or cls._finite_float(item.get("profit"), 0.0) != 0.0
        ]
        if not exit_rows:
            return {
                "trade_profile_available": False,
                "trade_profile_source": "trades",
                "trade_distribution": {
                    "available": False,
                    "source": "trades",
                    "sample_count": 0,
                },
            }
        round_trips = []
        for index, item in enumerate(exit_rows, 1):
            pnl = cls._finite_float(item.get("profit"))
            notional = abs(cls._finite_float(item.get("shares")) * cls._finite_float(item.get("price")))
            round_trips.append(
                {
                    "round_trip_id": f"trade_exit_{index}",
                    "status": "closed",
                    "realized_pnl": pnl,
                    "realized_return": pnl / notional if notional > 0 else (pnl / initial_capital if initial_capital > 0 else 0.0),
                    "hold_days": item.get("holding_days"),
                }
            )
        profile = cls._trade_profile_from_round_trips(round_trips, initial_capital=initial_capital)
        profile["trade_profile_source"] = "trades"
        distribution = dict(profile.get("trade_distribution") or {})
        distribution["source"] = "trades"
        profile["trade_distribution"] = distribution
        return profile

    @classmethod
    def _trade_profile_from_metric(cls, metric: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(metric or {})
        initial_capital = cls._finite_float(payload.get("initial_capital"), 100000.0)
        profile = cls._trade_profile_from_round_trips(
            payload.get("round_trip_positions"),
            initial_capital=initial_capital,
        )
        if not profile.get("trade_profile_available"):
            profile = cls._trade_profile_from_trades(
                payload.get("trades"),
                initial_capital=initial_capital,
            )
        if profile.get("trade_profile_available"):
            return profile
        return {
            "trade_profile_available": False,
            "trade_profile_source": "unavailable",
            "trade_profile_unavailable_reason": (
                "missing_round_trip_positions_and_trades"
                if not payload.get("round_trip_positions") and not payload.get("trades")
                else "no_closed_trade_pnl"
            ),
            "trade_distribution": dict(profile.get("trade_distribution") or {}),
        }

    @classmethod
    def _merge_trade_profile_metrics(cls, metric: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(metric or {})
        profile = cls._trade_profile_from_metric(payload)
        for key, value in profile.items():
            if value in (None, "", [], {}):
                continue
            payload[key] = value
        return payload

    @classmethod
    def _aggregate_trade_profile_metrics(
        cls,
        results: List[dict],
        *,
        initial_capital: float = 100000.0,
    ) -> dict[str, Any]:
        round_trips: list[dict[str, Any]] = []
        trades: list[dict[str, Any]] = []
        for metric in list(results or []):
            payload = dict(metric or {})
            for item in list(payload.get("round_trip_positions") or []):
                if isinstance(item, dict):
                    round_trips.append(dict(item))
            if not round_trips:
                for item in list(payload.get("trades") or []):
                    if isinstance(item, dict):
                        trades.append(dict(item))
        profile = cls._trade_profile_from_round_trips(round_trips, initial_capital=initial_capital)
        if not profile.get("trade_profile_available"):
            profile = cls._trade_profile_from_trades(trades, initial_capital=initial_capital)
        if profile.get("trade_profile_available"):
            profile["trade_profile_aggregation"] = "component_closed_trades"
            return profile
        return {
            "trade_profile_available": False,
            "trade_profile_source": "unavailable",
            "trade_profile_unavailable_reason": "no_component_closed_trade_pnl",
            "trade_distribution": dict(profile.get("trade_distribution") or {}),
        }

    @staticmethod
    def _derive_trade_validation_metrics(candidate: dict, result: dict) -> dict[str, Any]:
        metrics = dict(result.get("metrics") or {})
        layers = dict(result.get("layers") or {})
        target_metrics = dict((layers.get("target") or {}).get("metrics") or {})
        representative_metrics = dict((layers.get("representative") or {}).get("metrics") or {})
        combined_metrics = dict((layers.get("combined") or {}).get("metrics") or {})
        event_window_metrics = dict(result.get("event_window_metrics") or {})
        research_task = _normalize_research_task_contract(candidate.get("research_task") or {})
        event_window = dict(research_task.get("event_window") or {})
        holding_window = dict(research_task.get("holding_window") or {})
        holding_horizon = dict(candidate.get("holding_horizon") or {})
        risk_rules = dict(candidate.get("risk_rules") or {})
        execution_assumptions = dict(candidate.get("execution_assumptions") or {})
        portfolio_spec = dict(candidate.get("portfolio_spec") or {})

        trade_count = float(metrics.get("trades_count") or metrics.get("trade_count") or 0.0)
        avg_holding_days = float(
            metrics.get("avg_holding_days")
            or holding_window.get("max_days")
            or holding_horizon.get("max_days")
            or risk_rules.get("max_holding_days")
            or 0.0
        )
        turnover_proxy = float(metrics.get("turnover_proxy") or 0.0)
        if turnover_proxy <= 0 and trade_count > 0:
            turnover_proxy = round(trade_count / max(avg_holding_days, 5.0), 4) if avg_holding_days > 0 else float(trade_count)

        target_layer_oos_return = float(target_metrics.get("total_return") or metrics.get("total_return") or 0.0)
        representative_return = float(representative_metrics.get("total_return") or 0.0)
        combined_return = float(combined_metrics.get("total_return") or metrics.get("total_return") or 0.0)
        event_window_return = float(
            event_window_metrics.get("bhar")
            or event_window_metrics.get("abnormal_return")
            or event_window_metrics.get("total_return")
            or target_layer_oos_return
            or combined_return
            or 0.0
        )
        target_layer_abnormal_return = round(
            float(event_window_metrics.get("abnormal_return"))
            if event_window_metrics.get("abnormal_return") is not None
            else target_layer_oos_return - representative_return,
            4,
        )

        post_event_decay = round(
            float(event_window_metrics.get("post_event_decay"))
            if event_window_metrics.get("post_event_decay") is not None
            else ((target_layer_oos_return - event_window_return) / max(abs(event_window_return), 0.01)),
            4,
        )

        event_window_hit_ratio = round(
            float(event_window_metrics.get("hit_ratio"))
            if event_window_metrics.get("hit_ratio") is not None
            else (
                (
                    (1.0 if event_window_return > 0 else 0.0)
                    + (1.0 if target_layer_abnormal_return > 0 else 0.0)
                    + (1.0 if target_layer_oos_return > 0 else 0.0)
                ) / 3.0
            ),
            4,
        )

        lookback_days = float((research_task.get("estimation_window") or {}).get("lookback_days") or 60.0)
        post_days = float(event_window.get("post_days") or holding_window.get("max_days") or avg_holding_days or 20.0)
        observation_days = BacktestFilter._trade_density_observation_days(
            metrics=metrics,
            target_metrics=target_metrics,
            combined_metrics=combined_metrics,
            event_window_metrics=event_window_metrics,
            lookback_days=lookback_days,
            post_days=post_days,
            trade_count=trade_count,
            avg_holding_days=avg_holding_days,
        )
        trade_density = round(trade_count / observation_days * 20.0, 4)

        target_sharpe = float(target_metrics.get("sharpe_ratio") or metrics.get("sharpe_ratio") or 0.0)
        combined_sharpe = float(combined_metrics.get("sharpe_ratio") or metrics.get("sharpe_ratio") or 0.0)
        representative_sharpe = float(representative_metrics.get("sharpe_ratio") or 0.0)
        stability_scale = max(abs(target_sharpe), abs(combined_sharpe), abs(representative_sharpe), 0.25)
        stability_dispersion = abs(target_sharpe - combined_sharpe) + abs(target_sharpe - representative_sharpe)
        parameter_stability = round(max(0.0, min(1.0, 1.0 - stability_dispersion / (stability_scale * 4.0))), 4)
        expected_turnover_band = str(
            candidate.get("expected_turnover_band")
            or holding_horizon.get("expected_turnover_band")
            or dict(candidate.get("rebalance_rule") or {}).get("expected_turnover_band")
            or execution_assumptions.get("expected_turnover_band")
            or ""
        ).strip().lower() or None
        capacity_bucket = str(
            candidate.get("capacity_bucket")
            or execution_assumptions.get("capacity_bucket")
            or portfolio_spec.get("capacity_bucket")
            or ""
        ).strip().lower() or None
        turnover_cost_class = str(
            candidate.get("turnover_cost_class")
            or execution_assumptions.get("turnover_cost_class")
            or ""
        ).strip().lower() or None
        position_sizing_rationale = str(
            candidate.get("position_sizing_rationale")
            or dict(candidate.get("position_sizing") or {}).get("position_sizing_rationale")
            or portfolio_spec.get("position_sizing_rationale")
            or ""
        ).strip() or None

        trade_profile_metrics = BacktestFilter._trade_profile_from_metric(metrics)
        if not trade_profile_metrics.get("trade_profile_available"):
            primary_layer = str(result.get("primary_validation_layer") or result.get("primary_layer") or "").strip().lower()
            layer_profile = (
                dict((layers.get("target") or {}).get("trade_profile") or {})
                if primary_layer == "target"
                else dict((layers.get("combined") or {}).get("trade_profile") or {})
            )
            if layer_profile.get("trade_profile_available"):
                trade_profile_metrics = layer_profile

        return {
            "avg_holding_days": round(avg_holding_days, 4),
            "turnover_proxy": round(turnover_proxy, 4),
            "target_layer_oos_return": round(target_layer_oos_return, 4),
            "target_layer_abnormal_return": round(target_layer_abnormal_return, 4),
            "event_window_hit_ratio": round(event_window_hit_ratio, 4),
            "post_event_decay": round(post_event_decay, 4),
            "trade_density": round(trade_density, 4),
            "parameter_perturbation_trade_stability": round(parameter_stability, 4),
            "event_study_mode": str(event_window_metrics.get("event_study_mode") or "").strip().lower() or None,
            "event_sample_count": int(event_window_metrics.get("event_sample_count") or 0),
            "event_anchor_count": int(event_window_metrics.get("event_anchor_count") or 0),
            "control_group_count": int(event_window_metrics.get("control_group_count") or 0),
            "event_sample_source": event_window_metrics.get("event_sample_source"),
            "event_time_anchors": list(event_window_metrics.get("event_time_anchors") or [])[:8],
            "traceable_to_event_samples": bool(event_window_metrics.get("traceable_to_event_samples")),
            "event_audit_incomplete": bool(event_window_metrics.get("event_audit_incomplete")),
            "expected_turnover_band": expected_turnover_band,
            "capacity_bucket": capacity_bucket,
            "turnover_cost_class": turnover_cost_class,
            "position_sizing_rationale": position_sizing_rationale,
            "market_regime_assumption": candidate.get("market_regime_assumption"),
            **trade_profile_metrics,
        }

    @staticmethod
    def _build_backtest_metrics_contract(candidate: dict, result: dict) -> dict[str, Any]:
        payload = dict(result or {})
        metrics = dict(payload.get("metrics") or {})
        layers = dict(payload.get("layers") or {})
        primary_layer = str(
            payload.get("primary_validation_layer")
            or payload.get("primary_layer")
            or "combined"
        ).strip().lower() or "combined"
        target_metrics = dict((layers.get("target") or {}).get("metrics") or {})
        combined_metrics = dict((layers.get("combined") or {}).get("metrics") or metrics)
        primary_metrics = (
            target_metrics
            if primary_layer == "target" and target_metrics
            else combined_metrics
        )
        sharpe_ratio = _safe_float(primary_metrics.get("sharpe_ratio"), _safe_float(metrics.get("sharpe_ratio")))
        post_cost_sharpe = _safe_float(
            primary_metrics.get("post_cost_sharpe"),
            _safe_float(metrics.get("post_cost_sharpe"), sharpe_ratio),
        )
        trades_count = int(
            primary_metrics.get("trades_count")
            or primary_metrics.get("trade_count")
            or metrics.get("trades_count")
            or metrics.get("trade_count")
            or 0
        )
        max_drawdown = _safe_float(primary_metrics.get("max_drawdown"), _safe_float(metrics.get("max_drawdown")))
        win_rate = _safe_float(primary_metrics.get("win_rate"), _safe_float(metrics.get("win_rate")))
        target_codes = list(payload.get("target_codes") or _extract_target_codes_from_payload(candidate))
        required_fields = {
            "sharpe_ratio": sharpe_ratio,
            "post_cost_sharpe": post_cost_sharpe,
            "trades_count": trades_count,
            "max_drawdown": max_drawdown,
            "validation_focus": payload.get("validation_focus"),
            "code_source": payload.get("code_source"),
        }
        missing_fields = [key for key, value in required_fields.items() if value in (None, "", [])]
        status = "present" if not missing_fields else ("partial" if len(missing_fields) < len(required_fields) else "missing")
        return {
            "contract_version": "strategy_factory.backtest_metrics_contract.v1",
            "status": status,
            "available": status != "missing",
            "missing_fields": missing_fields,
            "sharpe_ratio": round(sharpe_ratio, 6),
            "post_cost_sharpe": round(post_cost_sharpe, 6),
            "trade_count": trades_count,
            "trades_count": trades_count,
            "max_drawdown": round(max_drawdown, 6),
            "win_rate": round(win_rate, 6),
            "profit_factor": _safe_float(primary_metrics.get("profit_factor"), _safe_float(metrics.get("profit_factor"))),
            "expectancy": _safe_float(primary_metrics.get("expectancy"), _safe_float(metrics.get("expectancy"))),
            "expectancy_return": _safe_float(primary_metrics.get("expectancy_return"), _safe_float(metrics.get("expectancy_return"))),
            "payoff_ratio": _safe_float(primary_metrics.get("payoff_ratio"), _safe_float(metrics.get("payoff_ratio"))),
            "breakeven_win_rate": _safe_float(
                primary_metrics.get("breakeven_win_rate"),
                _safe_float(metrics.get("breakeven_win_rate")),
            ),
            "trade_distribution": dict(primary_metrics.get("trade_distribution") or metrics.get("trade_distribution") or {}),
            "validation_focus": payload.get("validation_focus"),
            "primary_validation_layer": primary_layer,
            "code_source": payload.get("code_source"),
            "target_codes": list(target_codes),
        }

    @staticmethod
    def _resolve_backtest_plan(candidate: dict) -> tuple[List[str], List[str], List[str], str, str]:
        candidate = apply_resolved_candidate_envelope(candidate)
        target_codes = _extract_target_codes_from_payload(candidate, limit=12)
        target_codes = _apply_preferred_code_order(target_codes, _preferred_target_order(candidate))
        raw_research_task = candidate.get("research_task") or {}
        research_task = _normalize_research_task_contract(raw_research_task)
        validation_profile = dict(candidate.get("validation_profile") or {})
        validation_focus = str(
            validation_profile.get("validation_focus")
            or research_task.get("validation_focus")
            or "target_plus_representative"
        ).strip().lower()
        representative_stocks = list(_compat_setting("REPRESENTATIVE_STOCKS", REPRESENTATIVE_STOCKS))
        representative_codes = [code for code in representative_stocks if code not in target_codes]
        has_explicit_research_task = _has_explicit_research_task(candidate)

        if not has_explicit_research_task:
            if validation_focus == "broad_generalization":
                evaluated_codes = list(dict.fromkeys([*target_codes, *representative_stocks]))
                return (
                    evaluated_codes,
                    target_codes,
                    representative_codes,
                    "target_plus_representative",
                    validation_focus,
                )
            if target_codes:
                return list(target_codes), target_codes, representative_codes, "candidate_target_symbols", "candidate_target_only"
            return list(representative_stocks), target_codes, representative_codes, "representative_only", "target_plus_representative"

        if validation_focus in {"candidate_target_only", "event_target_only", "target_only"} and target_codes:
            evaluated_codes = list(target_codes)
            code_source = validation_focus
        elif validation_focus == "broad_generalization":
            evaluated_codes = list(dict.fromkeys([*target_codes, *representative_stocks]))
            code_source = "target_plus_representative"
        else:
            selected_representatives = representative_codes[:2] if target_codes else representative_stocks[:2]
            evaluated_codes = list(dict.fromkeys([*target_codes, *selected_representatives]))
            code_source = "candidate_target_plus_representative" if target_codes else "representative_only"
        return evaluated_codes, target_codes, representative_codes, code_source, validation_focus

    @classmethod
    def _resolve_backtest_codes(cls, candidate: dict) -> tuple[List[str], List[str], List[str], str]:
        evaluated_codes, target_codes, representative_codes, code_source, _ = cls._resolve_backtest_plan(candidate)
        return evaluated_codes, target_codes, representative_codes, code_source
