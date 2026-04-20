

def _select_best_candidate(candidate_runs: Mapping[str, StrategyArtifact]) -> tuple[str | None, StrategyArtifact | None]:
    ranked = [
        (candidate_id, run)
        for candidate_id, run in candidate_runs.items()
        if run.equity_curve is not None and not run.equity_curve.empty
    ]
    ranked.sort(key=lambda item: _metrics_rank_key(item[1].metrics))
    if not ranked:
        return None, None
    return ranked[0]


def _candidate_payload(candidate_id: str | None, artifact: StrategyArtifact | None) -> dict[str, Any] | None:
    if not candidate_id or artifact is None:
        return None
    return {
        "candidate_id": candidate_id,
        "name": artifact.name,
        "metrics": dict(artifact.metrics),
        "params": dict(artifact.extra),
    }


def _main_summary_source(protocol: ResearchProtocol) -> str:
    return f"{protocol.baseline_slippage_bps:.1f}bps_main"


def _build_cost_scenarios(
    *,
    price_df: pd.DataFrame,
    dividend_df: pd.DataFrame,
    protocol: ResearchProtocol,
) -> tuple[list[CostScenarioResult], dict[str, StrategyArtifact], list[dict[str, Any]]]:
    scenarios: list[tuple[str, float]] = [
        ("historical_control", CONTROL_SCENARIO_SLIPPAGE_BPS),
        ("main", float(protocol.baseline_slippage_bps)),
        ("stress", float(protocol.stress_slippage_bps)),
    ]
    results: list[CostScenarioResult] = []
    main_suite: dict[str, StrategyArtifact] = {}
    optimization_payloads: list[dict[str, Any]] = []
    for scenario_name, slippage_bps in scenarios:
        suite, optimized_candidates = run_legacy_core_suite(
            price_df,
            dividend_df,
            slippage_bps=slippage_bps,
        )
        if scenario_name == "main":
            main_suite = suite
            optimization_payloads = optimized_candidates
        results.append(
            CostScenarioResult(
                scenario=scenario_name,
                slippage_bps=float(slippage_bps),
                commission_rate=0.00025,
                sell_tax_rate=0.0,
                strategy_metrics={key: dict(value.metrics) for key, value in suite.items()},
                summary_source="legacy_core_suite",
            )
        )
    return results, main_suite, optimization_payloads


def _aggregate_family_oos(curves: Mapping[str, list[pd.DataFrame]]) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for family, family_curves in curves.items():
        combined_curve = _chain_oos_curves(family_curves)
        payload[family] = _summarize_nav_curve(combined_curve)
    return payload


def _baseline_reference_payload() -> dict[str, Any]:
    return {
        "summary_json": str(BASELINE_REFERENCE_DIR / "510300_backtest_summary_20260410.json"),
        "report_markdown": str(BASELINE_REFERENCE_DIR / "510300_backtest_report_20260410.md"),
        "frozen_script": str(LEGACY_SCRIPT_PATH),
    }


def build_oos_fold_results(
    *,
    protocol: ResearchProtocol,
    price_map: Mapping[str, pd.DataFrame],
    dividend_map: Mapping[str, pd.DataFrame],
    futures_fee_info: Mapping[str, Any],
) -> tuple[list[FoldResult], dict[str, list[pd.DataFrame]], dict[str, list[pd.DataFrame]]]:
    core_prices = price_map.get("risk_core", pd.DataFrame())
    core_dividends = dividend_map.get("risk_core", pd.DataFrame())
    windows = build_monthly_windows(
        core_prices["date"],
        train_months=protocol.train_months,
        test_months=protocol.test_months,
        step_months=protocol.step_months,
    )
    assumptions = _legacy_assumptions(protocol.baseline_slippage_bps)
    fold_results: list[FoldResult] = []
    family_curves: dict[str, list[pd.DataFrame]] = {
        "scheme1": [],
        "scheme2": [],
        "optimized_regime": [],
        "family_a": [],
        "family_b": [],
        "family_c": [],
        "family_d": [],
    }
    full_candidate_curves: dict[str, list[pd.DataFrame]] = {
        "family_a": [],
        "family_b": [],
        "family_c": [],
        "family_d": [],
    }
    for fold_index, window in enumerate(windows, start=1):
        train_start = window["train_start"]
        train_end = window["train_end"]
        test_start = window["test_start"]
        test_end = window["test_end"]
        train_prices = _slice_frame(core_prices, train_start, train_end)
        train_dividends = _slice_dividends(core_dividends, train_start, train_end)
        test_prices = _slice_frame(core_prices, test_start, test_end)
        test_dividends = _slice_dividends(core_dividends, test_start, test_end)
        train_suite, _ = run_legacy_core_suite(train_prices, train_dividends, slippage_bps=protocol.baseline_slippage_bps)
        legacy = _load_legacy_module()
        _trade_dates, monthly_schedule, next_trade_after_ex = legacy.build_trading_calendar(test_prices, test_dividends)
        indicators = legacy.build_indicator_frame(test_prices)
        scheme1_test = legacy.simulate_monthly_dca(
            test_prices,
            test_dividends,
            monthly_schedule,
            next_trade_after_ex,
            assumptions,
            name="scheme1",
            description="oos scheme1",
            fixed_external_injection=True,
            take_profit_pct=None,
        )
        scheme2_tp = _safe_float(train_suite["scheme2"].extra.get("take_profit_pct"), 0.20)
        scheme2_test = legacy.simulate_monthly_dca(
            test_prices,
            test_dividends,
            monthly_schedule,
            next_trade_after_ex,
            assumptions,
            name="scheme2",
            description="oos scheme2",
            fixed_external_injection=False,
            take_profit_pct=scheme2_tp,
        )
        optimized_test = legacy.simulate_regime_strategy(
            test_prices,
            test_dividends,
            monthly_schedule,
            next_trade_after_ex,
            assumptions,
            indicators,
            ma_window=_safe_int(train_suite["optimized_regime"].extra.get("ma_window"), 150),
            rsi_floor=_safe_int(train_suite["optimized_regime"].extra.get("rsi_floor"), 45),
            rsi_cap=_safe_int(train_suite["optimized_regime"].extra.get("rsi_cap"), 90),
            sell_rsi=_safe_int(train_suite["optimized_regime"].extra.get("sell_rsi"), 40),
            use_slope=bool(train_suite["optimized_regime"].extra.get("use_slope", True)),
        )
        serialized_scheme1 = _serialize_strategy(scheme1_test)
        serialized_scheme2 = _serialize_strategy(scheme2_test)
        serialized_optimized = _serialize_strategy(optimized_test)
        family_curves["scheme1"].append(serialized_scheme1.equity_curve)
        family_curves["scheme2"].append(serialized_scheme2.equity_curve)
        family_curves["optimized_regime"].append(serialized_optimized.equity_curve)

        sliced_prices = _slice_price_map(price_map, train_start, train_end)
        family_selections: dict[str, dict[str, Any]] = {
            "scheme2": _candidate_payload("take_profit", train_suite["scheme2"]),
            "optimized_regime": _candidate_payload("optimized_regime", train_suite["optimized_regime"]),
        }
        family_metrics: dict[str, dict[str, Any]] = {
            "scheme1": dict(serialized_scheme1.metrics),
            "scheme2": dict(serialized_scheme2.metrics),
            "optimized_regime": dict(serialized_optimized.metrics),
        }
        for family in ("family_a", "family_b", "family_c", "family_d"):
            candidate_runs = _build_family_candidate_runs(
                family,
                price_map=sliced_prices,
                assumptions=assumptions,
                futures_fee_info=futures_fee_info,
            )
            selected_candidate_id, selected_candidate_run = _select_best_candidate(candidate_runs)
            family_selections[family] = _candidate_payload(selected_candidate_id, selected_candidate_run)
            if selected_candidate_run is None:
                family_metrics[family] = _empty_artifact(family).metrics
                continue
            test_price_map = _slice_price_map(price_map, test_start, test_end)
            oos_candidates = _build_family_candidate_runs(
                family,
                price_map=test_price_map,
                assumptions=assumptions,
                futures_fee_info=futures_fee_info,
            )
            oos_run = oos_candidates.get(selected_candidate_id) or _empty_artifact(family)
            family_metrics[family] = dict(oos_run.metrics)
            family_curves[family].append(oos_run.equity_curve)
            full_candidate_curves[family].extend(run.equity_curve for run in candidate_runs.values() if not run.equity_curve.empty)
        fold_results.append(
            FoldResult(
                fold_index=fold_index,
                train_start=train_start.strftime("%Y-%m-%d"),
                train_end=train_end.strftime("%Y-%m-%d"),
                test_start=test_start.strftime("%Y-%m-%d"),
                test_end=test_end.strftime("%Y-%m-%d"),
                selected_candidates=family_selections,
                oos_metrics=family_metrics,
            )
        )
    return fold_results, family_curves, full_candidate_curves


def build_selection_gate(
    *,
    aggregate_oos: Mapping[str, dict[str, Any]],
    fold_results: Sequence[FoldResult],
) -> list[SelectionGateResult]:
    benchmark = aggregate_oos.get("scheme1", {})
    benchmark_cagr = _safe_float(benchmark.get("cagr"))
    benchmark_mdd = _safe_float(benchmark.get("max_drawdown"))
    latest_selection: dict[str, dict[str, Any] | None] = {}
    for fold in fold_results:
        for family, candidate in fold.selected_candidates.items():
            latest_selection[family] = candidate
    results: list[SelectionGateResult] = []
    for family in ("scheme2", "optimized_regime", "family_a", "family_b", "family_c", "family_d"):
        metrics = aggregate_oos.get(family, {})
        oos_cagr = _safe_float(metrics.get("cagr"))
        oos_mdd = _safe_float(metrics.get("max_drawdown"))
        passed = oos_cagr >= benchmark_cagr * 2.0 and oos_mdd <= benchmark_mdd
        reason = "passed" if passed else "failed_gate"
        results.append(
            SelectionGateResult(
                family=family,
                passed=passed,
                oos_cagr=oos_cagr,
                benchmark_oos_cagr=benchmark_cagr,
                oos_max_drawdown=oos_mdd,
                benchmark_oos_max_drawdown=benchmark_mdd,
                selected_candidate=latest_selection.get(family),
                reason=reason,
            )
        )
    return results


def build_final_recommendation(selection_gate: Sequence[SelectionGateResult]) -> FinalRecommendation:
    passed = [item for item in selection_gate if item.passed and item.selected_candidate]
    passed.sort(key=lambda item: (-item.oos_cagr, item.oos_max_drawdown, item.family))
    if not passed:
        return FinalRecommendation(
            decision="no_candidate_passed",
            selected_family=None,
            selected_candidate=None,
            summary="全部放开后仍无候选通过门槛。",
            passed_gate=False,
        )
    winner = passed[0]
    return FinalRecommendation(
        decision="single_candidate",
        selected_family=winner.family,
        selected_candidate=winner.selected_candidate,
        summary=f"推荐 {winner.family} 作为唯一通过门槛的候选。",
        passed_gate=True,
    )


def render_formal_markdown(summary: Mapping[str, Any]) -> str:
    protocol = summary["research_protocol"]
    recommendation = summary["final_recommendation"]
    selection_gate = summary["selection_gate"]
    cost_scenarios = summary["cost_scenarios"]
    artifacts = dict(summary.get("artifacts") or {})
    lines = [
        "# 510300 研究升级 v3 正式报告",
        "",
        "## 一、研究协议",
        "",
        f"- 截止日期：{protocol['end_date']}",
        f"- Walk-forward：{protocol['train_months']}/{protocol['test_months']}/{protocol['step_months']} 月",
        f"- 成本主场景：{protocol['baseline_slippage_bps']:.1f} bps；压力场景：{protocol['stress_slippage_bps']:.1f} bps",
        f"- 现金池开关：{'开启' if protocol['enable_cash_sleeves'] else '关闭'}；增强家族开关：{'开启' if protocol['enable_enhancements'] else '关闭'}",
        "",
        "## 二、标的解析",
        "",
    ]
    for key, payload in summary["instrument_resolution"]["resolved"].items():
        lines.append(
            f"- `{key}`：{payload['name']}（{payload['code']}），历史样本 {payload['history_rows']} 行，"
            f"近 60 日中位成交额 {_ccy(_safe_float(payload['median_amount_60d']))}。"
        )
    lines.extend(
        [
            "",
            "## 三、成本场景",
            "",
            "| 场景 | 滑点(bps) | scheme1 CAGR | scheme2 CAGR | optimized CAGR |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for scenario in cost_scenarios:
        metrics = scenario["strategy_metrics"]
        lines.append(
            "| "
            + " | ".join(
                [
                    scenario["scenario"],
                    f"{scenario['slippage_bps']:.1f}",
                    _pct(_safe_float(metrics.get("scheme1", {}).get("cagr"))),
                    _pct(_safe_float(metrics.get("scheme2", {}).get("cagr"))),
                    _pct(_safe_float(metrics.get("optimized_regime", {}).get("cagr"))),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 四、样本外门槛",
            "",
            "| 家族 | OOS CAGR | 基准 OOS CAGR | OOS MDD | 基准 OOS MDD | 通过 |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for gate in selection_gate:
        lines.append(
            "| "
            + " | ".join(
                [
                    gate["family"],
                    _pct(_safe_float(gate["oos_cagr"])),
                    _pct(_safe_float(gate["benchmark_oos_cagr"])),
                    _pct(_safe_float(gate["oos_max_drawdown"])),
                    _pct(_safe_float(gate["benchmark_oos_max_drawdown"])),
                    "是" if gate["passed"] else "否",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 五、最终推荐",
            "",
            f"- 结论：{recommendation['summary']}",
            f"- 决策枚举：`{recommendation['decision']}`",
            "",
            "## 六、产物与 promotion",
            "",
            f"- bundle：`{artifacts.get('bundle_dir', 'pending_write')}`",
            f"- CSV 数量：{len(list(artifacts.get('csv_inventory') or []))}",
            f"- baseline 冻结引用：`{summary['research_protocol']['baseline_reference']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def create_bundle_artifacts(timestamp: str | None = None) -> BundleArtifacts:
    run_id = timestamp or pd.Timestamp.utcnow().strftime("%Y%m%dT%H%M%SZ")
    bundle_dir = V3_RUNS_ROOT / run_id
    csv_dir = bundle_dir / "csv"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)
    return BundleArtifacts(
        bundle_dir=bundle_dir,
        summary_path=bundle_dir / "summary.json",
        markdown_path=bundle_dir / "formal_report.md",
        csv_dir=csv_dir,
        latest_json_path=V3_REPORT_ROOT / "latest.json",
        latest_markdown_path=V3_REPORT_ROOT / "latest.md",
        latest_pdf_path=V3_REPORT_ROOT / "latest.pdf",
    )


def write_bundle(
    *,
    bundle: BundleArtifacts,
    summary: Mapping[str, Any],
    markdown_text: str,
    csv_frames: Mapping[str, pd.DataFrame],
) -> None:
    csv_inventory: list[str] = []
    for name, frame in csv_frames.items():
        path = bundle.csv_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        csv_inventory.append(path.name)
    payload = dict(summary)
    payload["artifacts"] = {
        "bundle_dir": str(bundle.bundle_dir),
        "summary_path": str(bundle.summary_path),
        "markdown_path": str(bundle.markdown_path),
        "csv_inventory": csv_inventory,
    }
    _write_json(bundle.summary_path, payload)
    bundle.markdown_path.write_text(markdown_text, encoding="utf-8")
    V3_REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(bundle.summary_path, bundle.latest_json_path)
    shutil.copy2(bundle.markdown_path, bundle.latest_markdown_path)


def load_bundle_summary(bundle_dir: Path) -> dict[str, Any]:
    return json.loads((bundle_dir / "summary.json").read_text(encoding="utf-8"))


def validate_bundle_for_promotion(bundle_dir: Path, pdf_path: Path | None = None) -> dict[str, Any]:
    summary = load_bundle_summary(bundle_dir)
    markdown_path = bundle_dir / "formal_report.md"
    csv_dir = bundle_dir / "csv"
    markdown_text = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
    csv_files = sorted(csv_dir.glob("*.csv"))
    schema_ok = required_summary_fields().issubset(summary.keys())
    csv_ok = bool(csv_files) and all(path.stat().st_size > 0 for path in csv_files)
    pdf_ok = bool(pdf_path and pdf_path.exists() and pdf_path.stat().st_size > 0)
    markdown_ok = summary.get("final_recommendation", {}).get("summary") in markdown_text
    recommendation_gate = bool(summary.get("final_recommendation", {}).get("passed_gate"))
    return {
        "schema_ok": bool(schema_ok),
        "csv_ok": bool(csv_ok),
        "markdown_pdf_consistent": bool(markdown_ok and pdf_ok),
        "recommendation_gate": recommendation_gate,
        "promotion_ready": bool(schema_ok and csv_ok and markdown_ok and pdf_ok and recommendation_gate),
    }


def finalize_bundle_outputs(bundle_dir: Path, pdf_path: Path) -> dict[str, Any]:
    checks = validate_bundle_for_promotion(bundle_dir, pdf_path=pdf_path)
    summary = load_bundle_summary(bundle_dir)
    shutil.copy2(bundle_dir / "summary.json", V3_REPORT_ROOT / "latest.json")
    shutil.copy2(bundle_dir / "formal_report.md", V3_REPORT_ROOT / "latest.md")
    shutil.copy2(pdf_path, V3_REPORT_ROOT / "latest.pdf")
    applied = False
    if checks["promotion_ready"]:
        shutil.copy2(bundle_dir / "formal_report.md", REPO_ROOT / ROOT_REPORT_MD)
        shutil.copy2(pdf_path, REPO_ROOT / ROOT_REPORT_PDF)
        applied = True
    summary["promotion"] = {**checks, "applied": applied, "pdf_path": str(pdf_path)}
    _write_json(bundle_dir / "summary.json", summary)
    shutil.copy2(bundle_dir / "summary.json", V3_REPORT_ROOT / "latest.json")
    return summary["promotion"]


def _build_csv_frames(
    *,
    main_suite: Mapping[str, StrategyArtifact],
    fold_results: Sequence[FoldResult],
    selection_gate: Sequence[SelectionGateResult],
    aggregate_oos: Mapping[str, dict[str, Any]],
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {
        "folds": pd.DataFrame([asdict(item) for item in fold_results]),
        "selection_gate": pd.DataFrame([asdict(item) for item in selection_gate]),
        "aggregate_oos": pd.DataFrame(
            [{"family": family, **metrics} for family, metrics in aggregate_oos.items()]
        ),
    }
    for key, artifact in main_suite.items():
        frames[f"main_{key}_equity_curve"] = artifact.equity_curve
        if artifact.trades is not None and not artifact.trades.empty:
            frames[f"main_{key}_trades"] = artifact.trades
    return frames
