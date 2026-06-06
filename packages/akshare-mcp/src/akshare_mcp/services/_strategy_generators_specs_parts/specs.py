

def _enrich_rule_template_contract(
    strategy_type: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    enriched = deepcopy(contract or {})
    if not enriched:
        return {}
    holding_horizon = dict(enriched.get("holding_horizon") or {})
    execution_assumptions = dict(enriched.get("execution_assumptions") or {})
    portfolio_spec = dict(enriched.get("portfolio_spec") or {})
    position_sizing = dict(enriched.get("position_sizing") or {})
    max_days = int(holding_horizon.get("max_days") or 10)
    alpha_half_life = float(enriched.get("alpha_half_life") or max(2, round(max_days * 0.75)))
    expected_turnover_band = str(
        holding_horizon.get("expected_turnover_band")
        or ("low" if max_days >= 24 else "medium" if max_days >= 12 else "high")
    ).strip().lower()
    capacity_bucket = str(
        execution_assumptions.get("capacity_bucket")
        or ("mid" if max_days >= 10 else "small")
    ).strip().lower()
    enriched.setdefault(
        "holding_rationale",
        (
            "围绕目标信号的半衰期持有，避免在信号尚未衰减前过早换手。"
            if strategy_type in {"momentum", "ma_cross", "volatility_breakout", "event_structure_breakout"}
            else "围绕慢变量扩散或修复窗口持有，在预期兑现后再做再平衡。"
        ),
    )
    enriched.setdefault("alpha_half_life", alpha_half_life)
    enriched.setdefault(
        "cost_sensitivity_grid",
        {
            "base_case": {
                "commission_rate": execution_assumptions.get("commission_rate", 0.00025),
                "slippage_bps": execution_assumptions.get("slippage_bps", 5),
                "tradability_filter": execution_assumptions.get("tradability_filter", True),
                "slippage_model": execution_assumptions.get("slippage_model", "fixed"),
                "market_impact_bps": execution_assumptions.get("market_impact_bps", 0.0),
            },
            "source": "rule_template_contract",
        },
    )
    enriched.setdefault(
        "position_model",
        position_sizing.get("mode")
        or portfolio_spec.get("position_assumption")
        or "equal_weight",
    )
    enriched.setdefault(
        "capacity_assumption",
        {
            "max_position_pct": portfolio_spec.get("max_position_pct"),
            "capacity_bucket": capacity_bucket,
            "symbol_count": 4,
        },
    )
    enriched.setdefault(
        "market_regime_assumption",
        {
            "summary": (
                "趋势扩张阶段更容易兑现。"
                if strategy_type in {"momentum", "ma_cross", "volatility_breakout", "event_structure_breakout"}
                else "中低噪声、流动性正常阶段更容易兑现。"
            ),
            "preferred_regime": (
                "trend_expansion"
                if strategy_type in {"momentum", "ma_cross", "volatility_breakout", "event_structure_breakout"}
                else "stable_liquid_cn_equity"
            ),
            "avoid_regime": "illiquid_stressed_market",
        },
    )
    holding_horizon.setdefault("alpha_half_life", alpha_half_life)
    holding_horizon.setdefault("expected_turnover_band", expected_turnover_band)
    holding_horizon.setdefault("cooldown_window_days", max(1, int(round(alpha_half_life / 3.0))))
    enriched["holding_horizon"] = holding_horizon
    position_sizing.setdefault("capacity_bucket", capacity_bucket)
    position_sizing.setdefault(
        "position_sizing_rationale",
        "equal_weight_diversified_basket"
        if position_sizing.get("mode") != "single_name"
        else "single_name_conviction_capped_by_capacity",
    )
    position_sizing.setdefault("expected_turnover_band", expected_turnover_band)
    enriched["position_sizing"] = position_sizing
    execution_assumptions.setdefault("capacity_bucket", capacity_bucket)
    execution_assumptions.setdefault(
        "turnover_cost_class",
        "medium_touch" if expected_turnover_band in {"high", "very_high"} else "low_touch",
    )
    execution_assumptions.setdefault("expected_turnover_band", expected_turnover_band)
    enriched["execution_assumptions"] = execution_assumptions
    portfolio_spec.setdefault(
        "position_sizing_rationale",
        position_sizing.get("position_sizing_rationale"),
    )
    portfolio_spec.setdefault("capacity_bucket", capacity_bucket)
    portfolio_spec.setdefault("expected_turnover_band", expected_turnover_band)
    enriched["portfolio_spec"] = portfolio_spec
    return enriched


def _rule_semantic_expected_move(strategy_type: str) -> str:
    return "neutral"


def _rule_failure_summary(
    trade_plan: dict[str, Any],
    risk_rules: dict[str, Any],
) -> str:
    exit_bias = str(trade_plan.get("exit_bias") or "signal_reversal_or_time_stop").strip()
    max_holding_days = int(risk_rules.get("max_holding_days") or 0)
    stop_loss_pct = float(risk_rules.get("stop_loss_pct") or risk_rules.get("stop_loss") or 0.0)
    parts = [exit_bias]
    if stop_loss_pct > 0:
        parts.append(f"stop_loss_{round(stop_loss_pct * 100.0, 2)}pct")
    if max_holding_days > 0:
        parts.append(f"time_stop_{max_holding_days}d")
    return " / ".join(parts)


def _attach_rule_trade_plan_claims(
    strategy_type: str,
    trade_plan: Optional[dict[str, Any]],
    *,
    entry_claim_id: str,
    exit_claim_id: str,
    entry_evidence_ids: list[str],
    exit_evidence_ids: list[str],
) -> dict[str, Any]:
    payload = dict(trade_plan or {})
    entry = dict(payload.get("entry") or {})
    exit_payload = dict(payload.get("exit") or {})
    entry.setdefault("node_id", "entry_step_1")
    entry.setdefault("phase", "entry")
    entry.setdefault("entry_bias", str(payload.get("entry_bias") or "").strip() or None)
    entry["claim_ids"] = [entry_claim_id]
    entry["evidence_ids"] = list(entry_evidence_ids)
    exit_payload.setdefault("node_id", "exit_step_1")
    exit_payload.setdefault("phase", "exit")
    exit_payload.setdefault("exit_bias", str(payload.get("exit_bias") or "").strip() or None)
    exit_payload["claim_ids"] = [exit_claim_id]
    exit_payload["evidence_ids"] = list(exit_evidence_ids)
    payload["entry"] = entry
    payload["exit"] = exit_payload
    if payload.get("entry_bias") in (None, "", [], {}):
        payload["entry_bias"] = entry.get("entry_bias")
    if payload.get("exit_bias") in (None, "", [], {}):
        payload["exit_bias"] = exit_payload.get("exit_bias")
    payload.setdefault("semantic_generation_mode", "rule_semantic_contract")
    payload.setdefault("strategy_type", str(strategy_type or "").strip().lower() or None)
    return payload


def _build_rule_semantic_contract_bundle(
    strategy_type: str,
    *,
    strategy_name: str,
    description: str,
    source: str,
    regime: str,
    fg: int,
    factor_summary: Optional[dict[str, Any]] = None,
    trade_plan: Optional[dict[str, Any]] = None,
    holding_horizon: Optional[dict[str, Any]] = None,
    risk_rules: Optional[dict[str, Any]] = None,
    target_symbols: Optional[list[str]] = None,
    rationale: Optional[str] = None,
    template_contract: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    strategy_key = str(strategy_type or "").strip().lower() or "rule_strategy"
    holding = dict(holding_horizon or {})
    risk = dict(risk_rules or {})
    entry_expected_move = _rule_semantic_expected_move(strategy_key)
    target_symbol_list = [
        str(symbol).strip()
        for symbol in list(target_symbols or [])
        if str(symbol).strip()
    ][:12]
    primary_horizon_days = max(
        1,
        int(
            holding.get("max_days")
            or holding.get("alpha_half_life")
            or risk.get("max_holding_days")
            or 10
        ),
    )
    entry_claim_id = f"{strategy_key}_claim_entry"
    exit_claim_id = f"{strategy_key}_claim_exit"
    entry_evidence_ids = [f"{strategy_key}_ev_context", f"{strategy_key}_ev_template"]
    exit_evidence_ids = [f"{strategy_key}_ev_invalidation"]
    normalized_trade_plan = _attach_rule_trade_plan_claims(
        strategy_key,
        trade_plan,
        entry_claim_id=entry_claim_id,
        exit_claim_id=exit_claim_id,
        entry_evidence_ids=entry_evidence_ids,
        exit_evidence_ids=exit_evidence_ids,
    )
    factor_payload = dict(factor_summary or {})
    template_payload = dict(template_contract or {})
    factor_names = [
        str(item).strip()
        for item in list(factor_payload.get("top_factor_names") or [])
        if str(item).strip()
    ][:3]
    rationale_text = str(rationale or description or strategy_name or strategy_key).strip()
    failure_summary = _rule_failure_summary(normalized_trade_plan, risk)
    evidence_chain = {
        "thesis": rationale_text,
        "generation_mode": "rule_semantic_contract",
        "evidences": [
            {
                "evidence_id": entry_evidence_ids[0],
                "source_type": "template_fallback",
                "direction": "neutral",
                "summary": (
                    f"{source} 认为 {strategy_key} 与 {regime} 环境匹配"
                    + (f"，top_factors={factor_names}" if factor_names else "")
                    + f"，fear_greed_index={int(fg)}。"
                ),
                "proxy_only": True,
                "target_symbols": list(target_symbol_list),
                "horizon_days": primary_horizon_days,
                "claim_ids": [entry_claim_id],
                "support_metric": {
                    "source": source,
                    "regime": regime,
                    "fear_greed_index": int(fg),
                    "top_factor_names": list(factor_names),
                },
            },
            {
                "evidence_id": entry_evidence_ids[1],
                "source_type": "rule_template_contract",
                "direction": "neutral",
                "summary": (
                    f"{strategy_name} 使用模板化 trade plan / risk rules / horizon。"
                    f" entry_bias={normalized_trade_plan.get('entry_bias')},"
                    f" exit_bias={normalized_trade_plan.get('exit_bias')}。"
                ),
                "proxy_only": True,
                "target_symbols": list(target_symbol_list),
                "horizon_days": primary_horizon_days,
                "claim_ids": [entry_claim_id],
                "support_metric": {
                    "template_generation_profile": template_payload.get("template_generation_profile"),
                    "holding_horizon": dict(holding),
                    "risk_rules": dict(risk),
                },
            },
            {
                "evidence_id": exit_evidence_ids[0],
                "source_type": "risk_template",
                "direction": "neutral",
                "summary": f"退出/失效条件由模板风控定义：{failure_summary}。",
                "proxy_only": True,
                "target_symbols": list(target_symbol_list),
                "horizon_days": min(primary_horizon_days, max(1, primary_horizon_days // 2)),
                "claim_ids": [exit_claim_id],
                "support_metric": {
                    "failure_summary": failure_summary,
                    "stop_loss_pct": risk.get("stop_loss_pct") or risk.get("stop_loss"),
                    "max_holding_days": risk.get("max_holding_days"),
                },
            },
        ],
    }
    prediction_contract = {
        "generation_mode": "rule_semantic_contract",
        "primary_horizon_days": primary_horizon_days,
        "target": "forward_return_neutral",
        "direction": "neutral",
        "template_fallback_used": True,
        "direction_source": "rule_template_diagnostic_fallback",
        "conflict_resolution_rule": {
            "policy": "prefer_invalidation_when_exit_evidence_present",
            "tie_breaker": "risk_first",
        },
        "claims": [
            {
                "claim_id": entry_claim_id,
                "claim_type": "entry",
                "summary": rationale_text,
                "expected_move": entry_expected_move,
                "expected_horizon": primary_horizon_days,
                "evidence_ids": list(entry_evidence_ids),
                "failure_condition": failure_summary,
                "conflict_resolution_rule": {
                    "policy": "prefer_invalidation_when_exit_evidence_present",
                },
                "target_symbols": list(target_symbol_list),
            },
            {
                "claim_id": exit_claim_id,
                "claim_type": "exit",
                "summary": f"当 {normalized_trade_plan.get('exit_bias') or 'risk_rule'} 出现时退出。",
                "expected_move": "neutral",
                "expected_horizon": min(primary_horizon_days, max(1, primary_horizon_days // 2)),
                "evidence_ids": list(exit_evidence_ids),
                "failure_condition": "entry thesis restored",
                "conflict_resolution_rule": {
                    "policy": "risk_first",
                },
                "target_symbols": list(target_symbol_list),
            },
        ],
    }
    confidence_contract = synthesize_confidence_contract(
        {
            "strategy_type": strategy_key,
            "evidence_chain": dict(evidence_chain),
            "prediction_contract": dict(prediction_contract),
        }
    )
    claim_to_trade_plan_map = {
        "claim_to_trade_step_ids": {
            entry_claim_id: [str(dict(normalized_trade_plan.get("entry") or {}).get("node_id") or "entry_step_1")],
            exit_claim_id: [str(dict(normalized_trade_plan.get("exit") or {}).get("node_id") or "exit_step_1")],
        },
        "trade_step_to_claim_ids": {
            str(dict(normalized_trade_plan.get("entry") or {}).get("node_id") or "entry_step_1"): [entry_claim_id],
            str(dict(normalized_trade_plan.get("exit") or {}).get("node_id") or "exit_step_1"): [exit_claim_id],
        },
    }
    return {
        "trade_plan": normalized_trade_plan,
        "evidence_chain": evidence_chain,
        "prediction_contract": prediction_contract,
        "confidence_contract": confidence_contract,
        "claim_to_trade_plan_map": claim_to_trade_plan_map,
    }
