

def run_510300_research_v3(protocol: ResearchProtocol, *, timestamp: str | None = None) -> BundleArtifacts:
    resolved, price_map, dividend_map, futures_fee_info = resolve_default_instruments(protocol.end_date)
    core_prices = price_map["risk_core"]
    core_dividends = dividend_map["risk_core"]
    cost_scenarios, main_suite, optimization_payloads = _build_cost_scenarios(
        price_df=core_prices,
        dividend_df=core_dividends,
        protocol=protocol,
    )
    fold_results, family_curves, _full_candidate_curves = build_oos_fold_results(
        protocol=protocol,
        price_map=price_map,
        dividend_map=dividend_map,
        futures_fee_info=futures_fee_info,
    )
    aggregate_oos = _aggregate_family_oos(family_curves)
    cash_sleeve_results: list[CashSleeveResult] = []
    if protocol.enable_cash_sleeves:
        for key in ("cash_money", "cash_short_bond", "cash_treasury"):
            frame = price_map.get(key, pd.DataFrame())
            funding_dates = {date: MONTHLY_CONTRIBUTION for date in _build_monthly_execution_dates(core_prices["date"])}
            scheduler_audit = simulate_cash_sleeve_scheduler(cash_price_df=frame, funding_needs=funding_dates)
            cash_sleeve_results.append(
                CashSleeveResult(
                    family=key,
                    selected_instrument=asdict(resolved[key]),
                    metrics={"history_rows": int(len(frame)), "median_amount_60d": _median_amount_60(frame)},
                    scheduler_audit=scheduler_audit,
                )
            )
    enhancement_results: list[EnhancementFamilyResult] = []
    if protocol.enable_enhancements:
        assumptions = _legacy_assumptions(protocol.baseline_slippage_bps)
        for family in ("family_a", "family_b", "family_c", "family_d"):
            candidate_runs = _build_family_candidate_runs(
                family,
                price_map=price_map,
                assumptions=assumptions,
                futures_fee_info=futures_fee_info,
            )
            candidate_id, candidate_run = _select_best_candidate(candidate_runs)
            enhancement_results.append(
                EnhancementFamilyResult(
                    family=family,
                    selected_candidate=_candidate_payload(candidate_id, candidate_run),
                    aggregate_oos=aggregate_oos.get(family, {}),
                    validation=_build_candidate_validation(candidate_runs),
                    candidate_count=len(candidate_runs),
                    notes=[],
                )
            )
    selection_gate = build_selection_gate(aggregate_oos=aggregate_oos, fold_results=fold_results)
    final_recommendation = build_final_recommendation(selection_gate)
    summary = {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "research_protocol": {
            **asdict(protocol),
            "baseline_reference": protocol.baseline_reference or _baseline_reference_payload()["summary_json"],
        },
        "baseline_reference": _baseline_reference_payload(),
        "instrument_resolution": {
            "resolved": {key: asdict(value) for key, value in resolved.items()},
        },
        "cost_scenarios": [asdict(item) for item in cost_scenarios],
        "optimization_candidates": optimization_payloads,
        "oos_folds": [asdict(item) for item in fold_results],
        "cash_sleeve_results": [asdict(item) for item in cash_sleeve_results],
        "enhancement_results": [asdict(item) for item in enhancement_results],
        "selection_gate": [asdict(item) for item in selection_gate],
        "final_recommendation": asdict(final_recommendation),
        "backtest_sanity_check": {},
    }
    try:
        market_data = {
            code: frame.loc[:, ["date", "open", "high", "low", "close", "volume"]].to_dict(orient="records")
            for code, frame in price_map.items()
            if code in {"risk_core", "style_500", "style_chinext", "style_div_lowvol"} and not frame.empty
        }
        sanity = BacktestEngine.run_portfolio_backtest(
            market_data,
            strategy="buy_and_hold",
            params={"initial_capital": 100000.0, "target_weight_scheme": "equal_weight", "commission": 0.00025},
            return_trades=False,
        )
        summary["backtest_sanity_check"] = sanity
    except Exception as exc:
        summary["backtest_sanity_check"] = {"success": False, "error": str(exc)}
    markdown_text = render_formal_markdown(summary)
    bundle = create_bundle_artifacts(timestamp=timestamp)
    write_bundle(
        bundle=bundle,
        summary=summary,
        markdown_text=markdown_text,
        csv_frames=_build_csv_frames(
            main_suite=main_suite,
            fold_results=fold_results,
            selection_gate=selection_gate,
            aggregate_oos=aggregate_oos,
        ),
    )
    return bundle
