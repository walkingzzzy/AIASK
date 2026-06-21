

async def run_gated_submission_pipeline(
    candidates: List[dict],
    snapshot: dict,
    db,
    *,
    backtest_filter=None,
    deduplicator=None,
    submitter=None,
    gated_runner=None,
    kline_cache: Optional[Dict[str, list]] = None,
) -> Dict[str, Any]:
    """执行 Gate-0/1/2 → 去重 → Gate-3 的统一工厂门禁编排。"""
    factory_pkg = get_strategy_factory_package()
    backtest_filter = backtest_filter or factory_pkg.BacktestFilter()
    deduplicator = deduplicator or factory_pkg.Deduplicator()
    submitter = submitter or factory_pkg.StrategySubmitter()
    candidates = [
        attach_trade_prediction_context(candidate, snapshot=snapshot)
        for candidate in list(candidates or [])
    ]

    gate_runner = gated_runner or getattr(factory_pkg, "run_gated_filter", run_gated_filter)

    gate_run = await gate_runner(
        candidates,
        db,
        backtest_filter,
        kline_cache=kline_cache,
    )
    gate_report = _compact_quality_gate_report(
        gate_run.get("gate_report") or gate_run.get("quality_gate") or {}
    )
    passed = list(gate_run.get("passed") or [])
    unique = await deduplicator.deduplicate(passed, db)
    submit_result = await submitter.submit(unique, snapshot, db)
    final_gate_report = _compact_quality_gate_report(
        finalize_gate_report(gate_report, submit_result)
    )
    raw_backtest_report = (gate_report.get("gate_2") or {}).get("report")
    if not raw_backtest_report and hasattr(backtest_filter, "get_last_report"):
        raw_backtest_report = backtest_filter.get_last_report()
    return {
        "passed": passed,
        "unique": unique,
        "submitted": list(submit_result.get("strategies") or []),
        "gate_run": {
            "summary": dict(gate_run.get("summary") or {}),
            "gate_report": gate_report,
            "quality_gate": gate_report,
        },
        "submit_result": submit_result,
        "gate_report": final_gate_report,
        "quality_gate": final_gate_report,
        "dedup_report": (
            deduplicator.get_last_report()
            if hasattr(deduplicator, "get_last_report")
            else {}
        ),
        "backtest_report": _compact_backtest_report_for_gate(raw_backtest_report or {}),
    }


def build_legacy_gate_report(
    candidates: List[dict],
    passed: List[dict],
    backtest_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """为尚未切到统一 GateRunner 的调用方构造兼容 gate_report。"""
    backtest_report = _compact_backtest_report_for_gate(backtest_report or {})
    backtest_summary = dict(backtest_report.get("summary") or {})
    gate_2_passed = int(backtest_summary.get("passed_count", len(passed)))
    gate_2_input = int(backtest_summary.get("input_count", len(candidates)))
    gate_2_failed = int(backtest_summary.get("failed_count", max(gate_2_input - gate_2_passed, 0)))
    return {
        "gate_0": {
            "status": "legacy_backtest_only",
            "passed_count": None,
            "failed_count": None,
            "reason": "gate_0_not_recorded_in_legacy_path",
        },
        "pre_gate": {
            "status": "legacy_backtest_only",
            "passed_count": None,
            "failed_count": None,
            "reason": "pre_gate_not_recorded_in_legacy_path",
        },
        "gate_1": {
            "status": "legacy_backtest_only",
            "passed_count": None,
            "failed_count": None,
            "reason": "gate_1_not_recorded_in_legacy_path",
        },
        "gate_2": {
            "status": "legacy_backtest_only",
            "input_count": gate_2_input,
            "passed_count": gate_2_passed,
            "failed_count": gate_2_failed,
            "report": backtest_report,
        },
        "gate_3": build_pending_gate_3_report(gate_2_passed),
        "final_decision": {
            "stage": "gate_2",
            "passed_count": gate_2_passed,
            "pending_submission_gate_count": gate_2_passed,
        },
    }


def finalize_gate_report(
    base_gate_report: Optional[Dict[str, Any]],
    submission_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """将 Gate-3 提交结果合并进 Gate-0/1/2 报告，形成最终门禁闭环。"""
    merged = deepcopy(base_gate_report or {})
    submission_result = dict(submission_result or {})
    submit_gate_report = dict(submission_result.get("gate_report") or {})
    completed_gate_report = build_completed_gate_3_report(submission_result)
    merged["gate_3"] = dict(submit_gate_report.get("gate_3") or completed_gate_report["gate_3"])
    merged["final_decision"] = dict(
        submit_gate_report.get("final_decision") or completed_gate_report["final_decision"]
    )
    return merged
