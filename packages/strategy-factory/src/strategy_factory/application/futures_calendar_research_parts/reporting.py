
    def _build_candidate(
        self,
        frame: pd.DataFrame,
        *,
        family: str,
        config: TrendConfig | SpreadConfig,
        execution_profile: ExecutionProfile,
        backtest: dict[str, Any],
        capacity_panel: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        summary = backtest["summary"]
        regime_panel = backtest["regime_panel"]
        if family == "trend":
            leg_month = int(config.leg_month)
            strategy_name = f"SC Trend Carry M{leg_month}"
            signal_series = backtest["signal_series"]
            price_column = f"price_{leg_month:02d}"
            curve_legs = [{"side": "long", "leg_type": "month_offset", "month": leg_month}]
            instrument_profile = self._instrument_profile_from_series(
                series=signal_series,
                underlying="SC",
                curve_legs=curve_legs,
                roll_rule={
                    "rule_type": "constant_maturity_roll",
                    "exit_before_front_delivery_days": 3,
                    "front_contract_column": "contract_01",
                },
            )
            raw_dsl = {
                "version": "1.0",
                "timeframe": "daily",
                "entry": {
                    "all": [
                        {
                            "op": "gt",
                            "left": {"field": "close"},
                            "right": {"indicator": "sma", "field": "close", "window": 20},
                            "trade_plan_node_id": "entry_trend_1",
                        },
                        {
                            "op": "gt",
                            "left": {"indicator": "sma", "field": "close", "window": 20},
                            "right": {"indicator": "sma", "field": "close", "window": 60},
                        },
                    ]
                },
                "exit": {
                    "any": [
                        {
                            "op": "lt",
                            "left": {"field": "close"},
                            "right": {"indicator": "sma", "field": "close", "window": 20},
                            "trade_plan_node_id": "exit_trend_1",
                        },
                        {
                            "op": "lt",
                            "left": {"indicator": "sma", "field": "close", "window": 20},
                            "right": {"indicator": "sma", "field": "close", "window": 60},
                        },
                    ]
                },
                "metadata": {
                    "signal_reference_series": price_column,
                    "trade_leg_definition": deepcopy(curve_legs),
                },
            }
            trade_plan = {
                "entry": {
                    "node_id": "entry_trend_1",
                    "claim_ids": ["claim_trend_1"],
                    "entry_bias": "carry_trend_follow",
                },
                "exit": {
                    "node_id": "exit_trend_1",
                    "claim_ids": ["claim_trend_1"],
                    "exit_bias": "trend_decay_or_delivery_protection",
                },
                "steps": [
                    {
                        "node_id": "step_trend_hold",
                        "claim_ids": ["claim_trend_1"],
                        "summary": "保持第 3/4 月常数期限多头，roll node 前主动收缩。",
                    }
                ],
            }
            prediction_contract = {
                "claims": [
                    {
                        "claim_id": "claim_trend_1",
                        "expected_move": "up",
                        "expected_horizon": 15,
                        "evidence_ids": ["trend_memo", "trend_backtest", "trend_regime"],
                        "failure_condition": "near_month_extreme_premium_or_trend_break",
                    }
                ]
            }
            portfolio_spec = {
                "position_assumption": "single_futures_directional",
                "target_weight_scheme": "single_contract_margin_budget",
                "max_position_pct": round(execution_profile.margin_budget_fraction, 4),
                "position_sizing_rationale": "用 gross margin 约束远月方向仓位，不假设跨腿保证金优惠。",
            }
            position_sizing = {
                "mode": "margin_budget",
                "position_assumption": "single_futures_directional",
                "margin_budget_fraction": round(execution_profile.margin_budget_fraction, 4),
            }
            holding_horizon = {
                "min_days": 5,
                "max_days": 25,
                "rebalance_interval_days": 1,
                "cooldown_window_days": 2,
                "expected_turnover_band": "medium",
            }
            risk_rules = {
                "stop_loss_pct": round(config.stop_loss_pct, 4),
                "time_stop_days": 25,
                "delivery_protection_days": 3,
                "near_month_premium_floor": round(config.exit_premium_floor, 4),
            }
            rebalance_rule = {
                "mode": "roll_or_signal",
                "frequency_days": 1,
                "roll_guard_days": 3,
            }
            hypothesis_text = "Backwardation carry 与远月趋势延续在近端未出现异常升水时可共振放大。"
        else:
            spread_column, near_price_column, far_price_column = self._spread_definition(config)
            strategy_name = f"SC Spread {config.leg_name.replace('_', '-')}"
            signal_series = backtest["signal_series"]
            near_month = _safe_int(near_price_column.split("_")[1], 1)
            far_month = _safe_int(far_price_column.split("_")[1], near_month + 1)
            curve_legs = [
                {"side": "long", "leg_type": "month_offset", "month": near_month},
                {"side": "short", "leg_type": "month_offset", "month": far_month},
            ]
            instrument_profile = self._instrument_profile_from_series(
                series=signal_series,
                underlying="SC",
                curve_legs=curve_legs,
                roll_rule={
                    "rule_type": "calendar_spread_roll",
                    "exit_before_front_delivery_days": 3,
                    "front_contract_column": "contract_01",
                },
            )
            raw_dsl = {
                "version": "1.0",
                "timeframe": "daily",
                "entry": {
                    "all": [
                        {
                            "op": "gte",
                            "left": {"indicator": "zscore", "field": "close", "window": 40},
                            "right": {"value": round(config.entry_z_low, 4)},
                            "trade_plan_node_id": "entry_spread_1",
                        },
                        {
                            "op": "lte",
                            "left": {"indicator": "zscore", "field": "close", "window": 40},
                            "right": {"value": round(config.entry_z_high, 4)},
                        }
                    ]
                },
                "exit": {
                    "any": [
                        {
                            "op": "gt",
                            "left": {"indicator": "zscore", "field": "close", "window": 40},
                            "right": {"value": round(config.exit_z, 4)},
                            "trade_plan_node_id": "exit_spread_1",
                        }
                    ]
                },
                "metadata": {
                    "signal_reference_series": spread_column,
                    "trade_leg_definition": deepcopy(curve_legs),
                    "mark_to_market_mode": "actual_contract_legs",
                    "entry_z_band": {
                        "low": round(config.entry_z_low, 4),
                        "high": round(config.entry_z_high, 4),
                    },
                },
            }
            trade_plan = {
                "entry": {
                    "node_id": "entry_spread_1",
                    "claim_ids": ["claim_spread_1"],
                    "entry_bias": "buy_near_sell_far_on_pullback",
                },
                "exit": {
                    "node_id": "exit_spread_1",
                    "claim_ids": ["claim_spread_1"],
                    "exit_bias": "mean_reversion_or_delivery_protection",
                },
                "steps": [
                    {
                        "node_id": "step_spread_hold",
                        "claim_ids": ["claim_spread_1"],
                        "summary": "维持买近抛远对冲，温和 pullback 后等待价差修复，时间止盈或交割保护离场。",
                    }
                ],
            }
            prediction_contract = {
                "claims": [
                    {
                        "claim_id": "claim_spread_1",
                        "expected_move": "spread_widen",
                        "expected_horizon": int(config.max_holding_days),
                        "evidence_ids": ["spread_memo", "spread_backtest", "spread_regime"],
                        "failure_condition": "term_structure_reversal_or_delivery_pressure",
                    }
                ]
            }
            portfolio_spec = {
                "position_assumption": "paired_futures_spread",
                "target_weight_scheme": "paired_margin_budget",
                "max_position_pct": round(execution_profile.margin_budget_fraction, 4),
                "position_sizing_rationale": "spread gross margin 保守计提，容量受 far-month haircut 限制。",
            }
            position_sizing = {
                "mode": "paired_margin_budget",
                "position_assumption": "paired_futures_spread",
                "margin_budget_fraction": round(execution_profile.margin_budget_fraction, 4),
            }
            holding_horizon = {
                "min_days": 3,
                "max_days": int(config.max_holding_days),
                "rebalance_interval_days": 1,
                "cooldown_window_days": 1,
                "expected_turnover_band": "medium",
            }
            risk_rules = {
                "stop_loss_abs_move": round(abs(config.stop_move), 4),
                "time_stop_days": int(config.max_holding_days),
                "delivery_protection_days": 3,
                "near_month_premium_floor": round(config.exit_premium_floor, 4),
            }
            rebalance_rule = {
                "mode": "signal_or_roll",
                "frequency_days": 1,
                "roll_guard_days": 3,
            }
            hypothesis_text = (
                "SC 期限结构在 backwardation 主导阶段具备稳定 carry，"
                "温和 pullback 后的 2-4/3-4 远端跨月更适合买近抛远并持有到结构修复。"
            )

        evidence_chain = self._build_evidence_chain(
            family=family,
            summary=summary,
            regime_panel=regime_panel,
        )
        constraint_check = self._build_constraint_check()
        research_task = {
            "task_id": "sc_calendar_full_sample_20180726_20250219",
            "task_source": "snapshot",
            "opportunity_type": f"sc_{family}_calendar",
            "target_symbols": ["SC"],
            "preferred_strategy_types": ["dsl_rule", "open_dsl"],
            "allowed_strategy_types": ["dsl_rule", "open_dsl"],
            "validation_focus": "candidate_target_only",
            "objective_profile": "high_precision",
            "trade_density_preference": "low",
            "regime_required": True,
            "cost_robust_required": True,
        }
        execution_assumptions = {
            "initial_capital": 1_000_000,
            "commission_rate": round(execution_profile.commission_rate, 6),
            "slippage_bps": round(execution_profile.slippage_bps, 4),
            "slippage_model": "fixed_plus_capacity_scaled",
            "market_impact_bps": round(execution_profile.market_impact_bps, 4),
            "tradability_filter": True,
            "capacity_participation_rate": round(execution_profile.capacity_participation_rate, 4),
            "margin_rate": round(execution_profile.margin_rate, 4),
            "contract_multiplier": int(execution_profile.contract_multiplier),
            "liquidity_bucket": execution_profile.liquidity_bucket,
            "max_contracts_per_rebalance": int(execution_profile.max_contracts_per_rebalance),
            "market_ruleset": execution_profile.market_ruleset,
            "sell_tax_rate": 0.0,
            "min_trade_lot": 1,
            "t_plus_one": False,
        }
        hypothesis_artifact = {
            "alpha_hypothesis": hypothesis_text,
            "failure_mode": {
                "primary_failure_mode": "delivery_or_structure_reversal",
                "stop_rule": deepcopy(risk_rules),
            },
            "target_universe_hypothesis": {
                "target_symbols": ["SC"],
                "target_symbol_policy": "prefer_intersection",
                "selection_mode": "explicit",
            },
            "family_hint": family,
            "holding_rationale": (
                "SC 远月方向单边依赖 backwardation carry + 趋势延续。"
                if family == "trend"
                else "买近抛远跨月对冲依赖 spread pullback 后的期限结构修复。"
            ),
            "alpha_half_life": 12 if family == "trend" else 8,
            "cost_sensitivity_grid": {
                "base_case": {
                    "commission_rate": execution_assumptions["commission_rate"],
                    "slippage_bps": execution_assumptions["slippage_bps"],
                    "market_impact_bps": execution_assumptions["market_impact_bps"],
                    "capacity_participation_rate": execution_assumptions["capacity_participation_rate"],
                },
                "stress_case": {
                    "commission_rate": round(execution_assumptions["commission_rate"] * 1.5, 6),
                    "slippage_bps": round(execution_assumptions["slippage_bps"] * 1.5, 4),
                    "market_impact_bps": round(execution_assumptions["market_impact_bps"] * 1.75, 4),
                    "capacity_participation_rate": round(execution_assumptions["capacity_participation_rate"] * 0.75, 4),
                },
            },
            "position_model": portfolio_spec["position_assumption"],
            "capacity_assumption": {
                "capital_buckets": deepcopy(capacity_panel),
                "liquidity_reference_contracts": execution_profile.liquidity_reference_contracts,
                "far_month_liquidity_haircut": execution_profile.far_month_liquidity_haircut,
            },
            "objective_profile": "high_precision",
            "trade_density_preference": "low",
            "entry_selectivity": "strict" if family == "trend" else "narrow",
            "regime_required": True,
            "cost_robust_required": True,
            "market_regime_assumption": {
                "preferred_regime": "backwardation",
                "avoid_regime": "extreme_near_month_premium",
                "regime_panel": deepcopy(regime_panel),
            },
            "validation_focus": "candidate_target_only",
        }
        candidate = {
            "status": "submitted",
            "name": strategy_name,
            "strategy_type": "dsl_rule",
            "generator_mode": "futures_calendar_research_adapter",
            "candidate_family": f"sc_{family}",
            "target_symbols": ["SC"],
            "stock_pool": {
                "selection_mode": "explicit",
                "symbols": ["SC"],
                "rationale": "SC 主任务只使用本地 ai_ready 曲线，目标标的固定为原油 SC。",
            },
            "research_task": research_task,
            "hypothesis": hypothesis_text,
            "hypothesis_artifact": hypothesis_artifact,
            "evidence_chain": evidence_chain,
            "prediction_contract": prediction_contract,
            "confidence_contract": self._build_confidence_contract(summary),
            "holding_horizon": holding_horizon,
            "trade_plan": trade_plan,
            "risk_rules": risk_rules,
            "position_sizing": position_sizing,
            "execution_notes": (
                "保守按 gross margin 与 far-month 流动性折扣约束仓位，交割保护窗口前主动减仓。"
            ),
            "rebalance_rule": rebalance_rule,
            "portfolio_spec": portfolio_spec,
            "execution_assumptions": execution_assumptions,
            "validation_profile": {
                "profile": "trade_rule_validation",
                "validation_focus": "candidate_target_only",
                "primary_validation_layer": "target",
                "objective_profile": "high_precision",
                "trade_density_preference": "low",
                "entry_selectivity": "strict" if family == "trend" else "narrow",
                "regime_required": True,
                "cost_robust_required": True,
            },
            "instrument_profile": instrument_profile,
            "constraint_check": constraint_check,
            "candidate_provenance": {
                "generator_mode": "futures_calendar_research_adapter",
                "source_data_path": str(self.data_path),
                "factory_target_status": "submitted",
            },
            "tags": [
                "futures",
                "calendar_spread" if family == "spread" else "calendar_trend",
                "gate3_candidate",
                "submitted",
            ],
            "dsl": {
                **deepcopy(raw_dsl),
                "metadata": {
                    **deepcopy(raw_dsl.get("metadata") or {}),
                    "target_symbols": ["SC"],
                    "stock_pool": {
                        "selection_mode": "explicit",
                        "symbols": ["SC"],
                    },
                    "portfolio_spec": deepcopy(portfolio_spec),
                    "execution_assumptions": deepcopy(execution_assumptions),
                    "validation_profile": {
                        "profile": "trade_rule_validation",
                        "validation_focus": "candidate_target_only",
                        "primary_validation_layer": "target",
                    },
                    "targeting_policy": {
                        "target_symbol_policy": "prefer_intersection",
                        "universe_expansion_policy": "allow_market_fallback",
                        "validation_focus": "candidate_target_only",
                    },
                    "constraint_check": deepcopy(constraint_check),
                    "instrument_profile": deepcopy(instrument_profile),
                },
            },
        }
        compiled_dsl = self._compile_strategy_blueprint_safe(
            candidate,
            market_frame=_to_ohlcv_projection(signal_series),
        )
        return candidate, raw_dsl, compiled_dsl

    def _materialize_result(
        self,
        frame: pd.DataFrame,
        *,
        family: str,
        ranked_item: dict[str, Any],
    ) -> StrategyResult:
        config = ranked_item["config"]
        execution_profile = ranked_item["execution_profile"]
        backtest = ranked_item["backtest"]
        capacity_panel = self._stress_test(
            frame,
            family=family,
            config=config,
            execution_profile=execution_profile,
        )
        candidate, raw_dsl, compiled_dsl = self._build_candidate(
            frame,
            family=family,
            config=config,
            execution_profile=execution_profile,
            backtest=backtest,
            capacity_panel=capacity_panel,
        )
        return StrategyResult(
            family=family,
            strategy_code=config.strategy_code,
            name=candidate["name"],
            config=asdict(config),
            execution_profile=asdict(execution_profile),
            summary=_round_dict_values(backtest["summary"]),
            regime_panel=_round_dict_values(backtest["regime_panel"]),
            capacity_panel=_round_dict_values({"rows": capacity_panel}).get("rows", []),
            trades=[_round_dict_values(trade) for trade in backtest["trades"]],
            candidate=_round_dict_values(candidate),
            raw_dsl=_round_dict_values(raw_dsl),
            compiled_dsl=_round_dict_values(compiled_dsl),
        )
