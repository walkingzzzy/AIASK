#!/usr/bin/env python3
"""Read-only strategy factory lifecycle verification summary."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "akshare-mcp" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "strategy-factory" / "src"))


class _SmokeDB:
    async def list_strategies(self, status: str, limit: int = 500) -> list[dict[str, Any]]:
        return []

    async def get_klines(self, code: str, limit: int = 500) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        price = 10.0 + (sum(ord(ch) for ch in str(code)) % 17) / 10.0
        for idx in range(max(120, min(int(limit or 500), 220))):
            drift = ((idx % 11) - 5) * 0.001
            open_price = price
            price = max(1.0, price * (1.0 + drift + 0.0015))
            rows.append({"date": f"2025-01-{idx % 28 + 1:02d}", "open": open_price, "high": max(open_price, price) * 1.01, "low": min(open_price, price) * 0.99, "close": price, "volume": 1000000 + idx})
        return rows


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


_GENERATION_HARD_BLOCKER_CODES = {
    "runtime_disabled",
    "snapshot_completion_too_low",
    "governed_candidate_pool_required",
    "governed_candidate_pool_missing_after_scheduler_success",
    "governed_candidate_pool_unavailable_after_refresh",
    "factor_research_stale",
}


def _readiness_split(summary: dict[str, Any], readiness: dict[str, Any]) -> dict[str, Any]:
    raw_blockers = list(
        summary.get("factory_readiness_raw_blocking_reason_codes")
        or readiness.get("blocking_reason_codes")
        or []
    )
    critical_blockers = list(
        summary.get("factory_readiness_critical_blocking_reason_codes")
        or readiness.get("critical_blocking_reason_codes")
        or []
    )
    effective_blockers = list(
        summary.get("factory_readiness_blocking_reason_codes")
        or readiness.get("effective_blocking_reason_codes")
        or []
    )
    generation_blockers = list(
        summary.get("factory_generation_blockers")
        or readiness.get("generation_blockers")
        or []
    )
    if "factory_generation_can_proceed" in summary:
        generation_can_proceed = bool(summary.get("factory_generation_can_proceed"))
    elif "generation_can_proceed" in readiness:
        generation_can_proceed = bool(readiness.get("generation_can_proceed"))
    else:
        generation_blockers = [
            str(code)
            for code in [*critical_blockers, *raw_blockers]
            if str(code) in _GENERATION_HARD_BLOCKER_CODES
        ]
        generation_can_proceed = not generation_blockers
    if "factory_production_can_proceed" in summary:
        production_can_proceed = bool(summary.get("factory_production_can_proceed"))
    elif "production_can_proceed" in readiness:
        production_can_proceed = bool(readiness.get("production_can_proceed"))
    else:
        production_can_proceed = bool(summary.get("factory_readiness_can_proceed", readiness.get("can_proceed")))
    production_blockers = list(
        summary.get("factory_production_blockers")
        or readiness.get("production_blockers")
        or effective_blockers
    )
    readiness_mode = summary.get("factory_readiness_mode") or readiness.get("readiness_mode")
    if not readiness_mode:
        readiness_mode = (
            "generation_blocked"
            if not generation_can_proceed
            else "generation_allowed_production_blocked"
            if not production_can_proceed
            else "production_allowed"
        )
    return {
        "generation_can_proceed": generation_can_proceed,
        "generation_blockers": generation_blockers,
        "production_can_proceed": production_can_proceed,
        "production_blockers": production_blockers,
        "readiness_mode": readiness_mode,
    }


def _collect_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary = dict(result.get("summary") or {})
    stages = dict(result.get("stages") or {})
    readiness = dict(stages.get("readiness") or {})
    readiness_split = _readiness_split(summary, readiness)
    spawn = dict((stages.get("spawn") or {}).get("summary") or (stages.get("spawn") or {}).get("data") or stages.get("spawn") or {})
    spawn_summary = dict(spawn.get("summary") or spawn)
    gate0 = dict(((result.get("quality_gate") or {}).get("gate_0") or {}))
    backtest_summary = dict((result.get("backtest_report") or {}).get("summary") or {})
    dedup_stage = dict(stages.get("deduplicate") or {})
    dedup_payload = dict(dedup_stage.get("data") or dedup_stage)
    dedup_summary = dict(dedup_payload.get("summary") or {})
    if "fallback_dedup_mode" in dedup_payload and "fallback_dedup_mode" not in dedup_summary:
        dedup_summary = dict(dedup_payload)
    submit = dict(result.get("submit_result") or {})
    strategies = [dict(item or {}) for item in list(submit.get("strategies") or [])]
    quality_fallback_count = 0
    risk_validation_missing_count = 0
    for item in strategies:
        if item.get("validation_evidence_mode") == "backtest_derived_fallback" or item.get("risk_evidence_mode") == "backtest_derived_fallback":
            quality_fallback_count += 1
        if item.get("formal_risk_validation_evidence_missing"):
            risk_validation_missing_count += 1
    final_candidate_count = _safe_int(summary.get("candidates_spawned") or spawn_summary.get("candidate_count"))
    spawn_candidate_count = _safe_int(spawn_summary.get("candidate_count"))
    spawn_materialized_count = _safe_int(spawn_summary.get("materialized_param_candidate_count"))
    empty_param_count = _safe_int(spawn_summary.get("empty_param_candidate_count"))
    gate0_failed = list(gate0.get("failed") or [])
    gate0_missing_params = [
        item
        for item in gate0_failed
        if any(str(reason or "").startswith("missing_executable_params") for reason in list(item.get("reasons") or []))
    ]
    if final_candidate_count > spawn_candidate_count and not gate0_missing_params and empty_param_count == 0:
        materialized_param_count = final_candidate_count
        materialized_param_scope = "final_candidates_gate0_verified"
    else:
        materialized_param_count = spawn_materialized_count
        materialized_param_scope = "spawn_stage"

    return {
        "run_status": result.get("status"),
        "factory_readiness_score": summary.get("factory_readiness_score") or readiness.get("readiness_score"),
        "factory_readiness_can_proceed": summary.get("factory_readiness_can_proceed", readiness.get("can_proceed")),
        "factory_generation_can_proceed": readiness_split["generation_can_proceed"],
        "factory_generation_blockers": readiness_split["generation_blockers"],
        "factory_production_can_proceed": readiness_split["production_can_proceed"],
        "factory_production_blockers": readiness_split["production_blockers"],
        "factory_readiness_mode": readiness_split["readiness_mode"],
        "submission_mode": summary.get("submission_mode") or submit.get("submission_mode"),
        "submit_read_only": bool(submit.get("read_only")),
        "submit_diagnostic_only": bool(submit.get("diagnostic_only")),
        "candidate_count": final_candidate_count,
        "strategy_type_coverage_count": _safe_int(spawn_summary.get("strategy_type_coverage_count")),
        "strategy_type_counts": dict(spawn_summary.get("strategy_type_counts") or {}),
        "empty_param_candidate_count": empty_param_count,
        "materialized_param_candidate_count": materialized_param_count,
        "materialized_param_candidate_scope": materialized_param_scope,
        "coverage_target_met": bool(spawn_summary.get("coverage_target_met")),
        "gate_0_failed_count": _safe_int(gate0.get("failed_count")),
        "gate_0_failed": gate0_failed,
        "gate_1_passed": _safe_int(((result.get("quality_gate") or {}).get("gate_1") or {}).get("passed_count")),
        "gate_2_passed": _safe_int(backtest_summary.get("passed_count")),
        "shared_result_reused_count": _safe_int(backtest_summary.get("shared_result_reused_count")),
        "dedup_report_available": bool(dedup_summary),
        "fallback_dedup_mode": dedup_summary.get("fallback_dedup_mode"),
        "structural_hash_duplicates": _safe_int(dedup_summary.get("structural_hash_duplicates")),
        "vector_checks": _safe_int(dedup_summary.get("vector_checks")),
        "submitted": _safe_int(submit.get("submitted")),
        "formal_incubation_count": _safe_int(submit.get("formal_incubation_count")),
        "quality_report_fallback_count": quality_fallback_count,
        "formal_risk_validation_evidence_missing_count": risk_validation_missing_count,
    }


async def _run_smoke(rounds: int) -> dict[str, Any]:
    from strategy_factory.domain.spawner import StrategySpawner
    from strategy_factory.application.quality_gates import gate_0_structural
    from strategy_factory.application.backtest_filter import BacktestFilter
    from strategy_factory.application.deduplicator import Deduplicator

    db = _SmokeDB()
    round_summaries: list[dict[str, Any]] = []
    all_types: set[str] = set()
    for idx in range(max(1, int(rounds or 1))):
        snapshot = {"date": f"2026-05-{idx + 1:02d}", "fear_greed_index": 50, "fg_components": {"volatility": 50}}
        spawner = StrategySpawner()
        candidates = spawner.spawn(snapshot)
        gate_failures = [dict(candidate, gate_0_result={"reasons": gate_0_structural(candidate).reasons}) for candidate in candidates if not gate_0_structural(candidate).passed]
        executable_param_failures = [
            item
            for item in gate_failures
            if any(str(reason or "").startswith("missing_executable_params") for reason in item.get("gate_0_result", {}).get("reasons") or [])
        ]
        trade_contract_failures = [
            item
            for item in gate_failures
            if any(str(reason or "").startswith("missing_trade_fields") for reason in item.get("gate_0_result", {}).get("reasons") or [])
        ]
        # Do not run heavy strategy backtests here; this smoke verifies identity, Gate-0 and dedup audit plumbing.
        deduplicator = Deduplicator(vector_gateway=None)
        unique = await deduplicator.deduplicate(candidates, db)
        spawn_summary = dict((spawner.get_last_report() or {}).get("summary") or {})
        all_types.update(str(item.get("strategy_type") or "") for item in candidates if item.get("strategy_type"))
        round_summaries.append(
            {
                "round": idx + 1,
                "candidate_count": len(candidates),
                "strategy_type_coverage_count": len({item.get("strategy_type") for item in candidates}),
                "strategy_type_counts": dict(spawn_summary.get("strategy_type_counts") or {}),
                "empty_param_candidate_count": _safe_int(spawn_summary.get("empty_param_candidate_count")),
                "materialized_param_candidate_count": _safe_int(spawn_summary.get("materialized_param_candidate_count")),
                "gate_0_failed_count": len(gate_failures),
                "gate_0_missing_executable_param_count": len(executable_param_failures),
                "gate_0_trade_contract_enrichment_gap_count": len(trade_contract_failures),
                "gate_0_failed": [{"strategy_type": item.get("strategy_type"), "reasons": item.get("gate_0_result", {}).get("reasons")} for item in gate_failures[:8]],
                "dedup_report": deduplicator.get_last_report(),
                "unique_count": len(unique),
            }
        )
    return {
        "mode": "smoke",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rounds": round_summaries,
        "acceptance": {
            "empty_param_candidate_count": sum(item["empty_param_candidate_count"] for item in round_summaries),
            "gate_0_missing_executable_param_count": sum(item["gate_0_missing_executable_param_count"] for item in round_summaries),
            "invalid_topn_count": sum(1 for item in round_summaries for failed in item["gate_0_failed"] if "invalid_strategy_type:topn_equity_portfolio" in failed.get("reasons", [])),
            "strategy_type_coverage_10_rounds": len(all_types),
            "coverage_target_met": len(all_types) >= 12,
        },
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Verify strategy factory lifecycle audit metrics without mutating production state.")
    parser.add_argument("--input-json", help="Existing factory run result JSON to summarize.")
    parser.add_argument("--output", help="Write summary JSON to this path.")
    parser.add_argument("--smoke-rounds", type=int, default=0, help="Run local read-only generation/dedup smoke rounds.")
    args = parser.parse_args()

    if args.input_json:
        payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
        report = {"mode": "input_json", "generated_at": datetime.now(timezone.utc).isoformat(), "summary": _collect_summary(dict(payload or {}))}
    else:
        report = await _run_smoke(args.smoke_rounds or 2)

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
