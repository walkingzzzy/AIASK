"""策略工厂回测初筛。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from copy import deepcopy
from statistics import median
from typing import Any, Dict, List, Optional

import numpy as np

from .legacy_bridge import get_compat_symbol, get_compat_value
from ..api.contracts import FactoryBacktestAssumptions
from ..domain.constants import (
    BACKTEST_AI_PROTOTYPE_THRESHOLDS,
    BACKTEST_CONCURRENCY,
    BACKTEST_CODE_CONCURRENCY,
    BACKTEST_DEFAULT_THRESHOLDS,
    BACKTEST_TYPE_THRESHOLDS,
    REPRESENTATIVE_STOCKS,
)
from ..domain.targets import _build_target_alignment_contract
from ..domain.targets import _extract_target_codes_from_payload
from ..domain.targets import _normalize_research_task_contract
from ..infrastructure.mcp_services import get_backtest_engine_class
from .runtime import get_strategy_factory_package as _runtime_get_strategy_factory_package


_LEGACY_BACKTEST_FILTER_MODULE = "akshare_mcp.services.strategy_factory.backtest_filter"
_LEGACY_RUNTIME_MODULE = "akshare_mcp.services.strategy_factory.runtime"
logger = logging.getLogger(__name__)

def _compat_setting(name: str, default: Any) -> Any:
    return get_compat_value(_LEGACY_BACKTEST_FILTER_MODULE, name, default)


def _get_strategy_factory_package():
    target = get_compat_symbol(
        _LEGACY_RUNTIME_MODULE,
        "get_strategy_factory_package",
        _runtime_get_strategy_factory_package,
    )
    return target()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _unique_reasons(reasons: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for reason in reasons:
        token = str(reason or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def build_target_quality_gate_summary(
    candidate: Optional[dict],
    *,
    gate_1_metrics: Optional[dict[str, Any]] = None,
    backtest_result: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload = dict(candidate or {})
    research_task = _normalize_research_task_contract(payload.get("research_task") or {})
    target_alignment_contract = _build_target_alignment_contract(research_task, candidate=payload)
    target_codes = _extract_target_codes_from_payload(payload, limit=12)
    research_target_symbols = list(research_task.get("target_symbols") or target_codes)
    research_target_count = len(research_target_symbols)
    quality_gate_enabled = bool(target_alignment_contract.get("quality_gate_enabled"))

    constraint_check = dict(payload.get("constraint_check") or {})
    result_payload = dict(backtest_result or {})
    if isinstance(result_payload.get("constraint_check"), dict):
        constraint_check = dict(result_payload.get("constraint_check") or {})

    coverage_ratio_raw = constraint_check.get("coverage_ratio")
    intersection_ratio_raw = constraint_check.get("intersection_ratio")
    overlap_count_raw = constraint_check.get("target_overlap_count")
    coverage_ratio = None if coverage_ratio_raw is None else round(_safe_float(coverage_ratio_raw, 0.0), 4)
    intersection_ratio = None if intersection_ratio_raw is None else round(_safe_float(intersection_ratio_raw, 0.0), 4)
    overlap_count = (
        max(0, int(overlap_count_raw))
        if overlap_count_raw is not None
        else len(set(target_codes).intersection(research_target_symbols))
    )

    min_coverage_ratio = round(_safe_float(target_alignment_contract.get("min_coverage_ratio"), 0.0), 4)
    min_intersection_ratio = round(_safe_float(target_alignment_contract.get("min_intersection_ratio"), 0.0), 4)
    min_required_overlap_count = max(0, int(target_alignment_contract.get("min_required_overlap_count") or 0))
    min_target_sample_count = max(0, int(target_alignment_contract.get("min_target_sample_count") or 0))
    min_target_layer_stability = round(_safe_float(target_alignment_contract.get("min_target_layer_stability"), 0.0), 4)

    sampled_target_count = None
    target_sample_ratio = None
    target_layer_stability = None
    target_layer_dispersion = None
    target_sharpe = None
    representative_sharpe = None
    combined_sharpe = None

    gate_1_payload = dict(gate_1_metrics or {})
    if gate_1_payload:
        target_codes_payload = gate_1_payload.get("target_codes")
        if target_codes_payload is not None:
            sampled_target_count = len(list(target_codes_payload or []))
        if sampled_target_count is not None and research_target_count > 0:
            target_sample_ratio = round(sampled_target_count / research_target_count, 4)
        sharpe_values = [_safe_float(item, 0.0) for item in list(gate_1_payload.get("sharpe_values") or [])]
        if len(sharpe_values) >= 2:
            target_sharpe = round(_safe_float(gate_1_payload.get("avg_sharpe"), 0.0), 4)
            target_layer_dispersion = round(max(sharpe_values) - min(sharpe_values), 4)
            stability_denominator = max(abs(target_sharpe), 0.5) + 1.0
            target_layer_stability = round(
                max(0.0, min(1.0, 1.0 - target_layer_dispersion / stability_denominator)),
                4,
            )

    layers = dict(result_payload.get("layers") or {})
    if layers:
        target_layer = dict((layers.get("target") or {}))
        representative_layer = dict((layers.get("representative") or {}))
        combined_layer = dict((layers.get("combined") or {}))
        if sampled_target_count is None:
            sampled_target_count = len(list(target_layer.get("successful_codes") or []))
            if research_target_count > 0:
                target_sample_ratio = round(sampled_target_count / research_target_count, 4)
        target_metrics = dict(target_layer.get("metrics") or {})
        representative_metrics = dict(representative_layer.get("metrics") or {})
        combined_metrics = dict(combined_layer.get("metrics") or result_payload.get("metrics") or {})
        target_sharpe = round(_safe_float(target_metrics.get("sharpe_ratio"), 0.0), 4)
        representative_sharpe = round(_safe_float(representative_metrics.get("sharpe_ratio"), 0.0), 4)
        combined_sharpe = round(_safe_float(combined_metrics.get("sharpe_ratio"), 0.0), 4)
        stability_scale = max(abs(target_sharpe), abs(combined_sharpe), abs(representative_sharpe), 0.25)
        target_layer_dispersion = round(
            abs(target_sharpe - combined_sharpe) + abs(target_sharpe - representative_sharpe),
            4,
        )
        target_layer_stability = round(
            max(0.0, min(1.0, 1.0 - target_layer_dispersion / (stability_scale * 4.0))),
            4,
        )

    reasons: list[str] = []
    alignment_ok = True
    sample_sufficient = True
    target_layer_stable = True

    if quality_gate_enabled:
        if not target_codes:
            alignment_ok = False
            reasons.append("target_universe_alignment_too_low")
        elif coverage_ratio is not None and coverage_ratio < min_coverage_ratio:
            alignment_ok = False
            reasons.append("target_universe_alignment_too_low")
        elif intersection_ratio is not None and intersection_ratio < min_intersection_ratio:
            alignment_ok = False
            reasons.append("target_universe_alignment_too_low")
        elif min_required_overlap_count > 0 and overlap_count < min_required_overlap_count:
            alignment_ok = False
            reasons.append("target_universe_alignment_too_low")

        if sampled_target_count is not None and min_target_sample_count > 0 and sampled_target_count < min_target_sample_count:
            sample_sufficient = False
            reasons.append("target_sample_sufficiency_too_low")

        if (
            target_layer_stability is not None
            and min_target_layer_stability > 0.0
            and target_layer_stability < min_target_layer_stability
        ):
            target_layer_stable = False
            reasons.append("target_layer_stability_too_low")

    return {
        "profile": target_alignment_contract.get("profile"),
        "quality_gate_enabled": quality_gate_enabled,
        "targeted_snapshot": bool(target_alignment_contract.get("targeted_snapshot")),
        "research_target_count": research_target_count,
        "target_symbol_count": len(target_codes),
        "coverage_ratio": coverage_ratio,
        "min_coverage_ratio": min_coverage_ratio,
        "intersection_ratio": intersection_ratio,
        "min_intersection_ratio": min_intersection_ratio,
        "target_overlap_count": int(overlap_count),
        "min_required_overlap_count": min_required_overlap_count,
        "sampled_target_count": sampled_target_count,
        "min_target_sample_count": min_target_sample_count,
        "target_sample_ratio": target_sample_ratio,
        "target_layer_stability": target_layer_stability,
        "min_target_layer_stability": min_target_layer_stability,
        "target_layer_dispersion": target_layer_dispersion,
        "target_sharpe": target_sharpe,
        "representative_sharpe": representative_sharpe,
        "combined_sharpe": combined_sharpe,
        "alignment_ok": alignment_ok,
        "sample_sufficient": sample_sufficient,
        "target_layer_stable": target_layer_stable,
        "target_alignment_contract": dict(target_alignment_contract),
        "reasons": _unique_reasons(reasons),
    }


class BacktestFilter:
    """回测筛选候选策略。"""

    SHARPE_MIN = BACKTEST_DEFAULT_THRESHOLDS["sharpe_min"]
    MDD_MAX = BACKTEST_DEFAULT_THRESHOLDS["mdd_max"]
    TRADES_MIN = BACKTEST_DEFAULT_THRESHOLDS["trades_min"]
    MIN_SAMPLES = BACKTEST_DEFAULT_THRESHOLDS["min_samples"]

    def __init__(self):
        self.last_report: dict = {
            "summary": {
                "input_count": 0,
                "passed_count": 0,
                "failed_count": 0,
                "strategy_type_counts": {},
                "passed_strategy_type_counts": {},
                "failed_strategy_type_counts": {},
                "failed_reason_counts": {},
                "thresholds_by_type": {},
            },
            "passed": [],
            "failed": [],
        }
        self.type_thresholds = dict(BACKTEST_TYPE_THRESHOLDS)
        self._kline_cache: dict[str, list] = {}

    async def preload_klines(self, db, codes: list[str] | None = None) -> None:
        """批量预取 K 线至缓存，后续 _test_one 复用。"""
        representative_stocks = list(_compat_setting("REPRESENTATIVE_STOCKS", REPRESENTATIVE_STOCKS))
        code_concurrency = int(_compat_setting("BACKTEST_CODE_CONCURRENCY", BACKTEST_CODE_CONCURRENCY) or BACKTEST_CODE_CONCURRENCY)
        codes = list(dict.fromkeys(codes or representative_stocks))
        sem = asyncio.Semaphore(code_concurrency)

        async def _fetch(code: str) -> None:
            async with sem:
                try:
                    self._kline_cache[code] = await db.get_klines(code, limit=500)
                except Exception:
                    pass

        await asyncio.gather(*[_fetch(c) for c in codes if c not in self._kline_cache])

    def get_last_report(self) -> dict:
        return self.last_report

    @staticmethod
    def _count_by_strategy_type(items: List[dict]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in items:
            strategy_type = str(item.get("strategy_type") or "unknown")
            counts[strategy_type] = counts.get(strategy_type, 0) + 1
        return counts

    @staticmethod
    def _build_report_entry(candidate: dict) -> dict:
        return {
            "strategy_type": candidate.get("strategy_type"),
            "generator_type": candidate.get("generator_type"),
            "params": candidate.get("params"),
            "spawn_reason": candidate.get("spawn_reason"),
            "generation_reason": candidate.get("generation_reason") or {},
            "target_symbols": candidate.get("target_symbols") or _extract_target_codes_from_payload(candidate),
            "stock_pool": candidate.get("stock_pool") or {},
            "selection_logic": candidate.get("selection_logic") or [],
            "research_task": candidate.get("research_task") or {},
            "event_context": candidate.get("event_context") or {},
            "tags": candidate.get("tags") or [],
            "constraint_check": candidate.get("constraint_check") or {},
            "validation_profile": candidate.get("validation_profile") or {},
            "backtest_result": candidate.get("backtest_result") or {},
            "backtest_metrics": candidate.get("backtest_metrics") or {},
        }

    @staticmethod
    def _build_failed_metric(field: str, operator: str, threshold: Any, actual: Any, label: str) -> dict:
        return {
            "field": field,
            "operator": operator,
            "threshold": threshold,
            "actual": actual,
            "label": label,
        }

    def _get_thresholds(self, strategy_type: str, candidate: Optional[dict] = None) -> dict:
        thresholds = {
            **dict(_compat_setting("BACKTEST_DEFAULT_THRESHOLDS", BACKTEST_DEFAULT_THRESHOLDS)),
            **(dict(_compat_setting("BACKTEST_TYPE_THRESHOLDS", BACKTEST_TYPE_THRESHOLDS)).get(strategy_type) or {}),
        }
        candidate = dict(candidate or {})
        tags = {str(tag).strip().lower() for tag in list(candidate.get("tags") or [])}
        generator_type = str(candidate.get("generator_type") or "").strip().lower()
        has_parent_strategy = bool(str(candidate.get("parent_strategy_id") or "").strip())
        if (
            strategy_type == "dsl_rule"
            or generator_type in {"external_llm", "llm_proxy", "pipeline_staged", "rl_bandit"}
            or "external_llm" in tags
            or "ai_generated" in tags
            or "llm_proxy_fallback" in tags
            or has_parent_strategy
        ):
            thresholds = {**thresholds, **dict(_compat_setting("BACKTEST_AI_PROTOTYPE_THRESHOLDS", BACKTEST_AI_PROTOTYPE_THRESHOLDS))}
        return thresholds

    @classmethod
    def _collect_preload_codes(cls, candidates: List[dict]) -> List[str]:
        ordered_codes: List[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            evaluated_codes, _, _, _, _ = cls._resolve_backtest_plan(candidate)
            for code in evaluated_codes:
                if code in seen:
                    continue
                seen.add(code)
                ordered_codes.append(code)
        return ordered_codes

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): BacktestFilter._json_safe(item)
                for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
            }
        if isinstance(value, (list, tuple, set)):
            return [BacktestFilter._json_safe(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def _build_shared_result_key(self, candidate: dict) -> str:
        strategy_type = str(candidate.get("strategy_type") or "unknown").strip().lower() or "unknown"
        research_task = _normalize_research_task_contract(candidate.get("research_task") or {})
        evaluated_codes, target_codes, representative_codes, code_source, validation_focus = self._resolve_backtest_plan(candidate)
        signature_payload = {
            "strategy_type": strategy_type,
            "params": dict(candidate.get("params") or {}),
            "research_task": research_task,
            "target_codes": target_codes,
            "representative_codes": representative_codes,
            "evaluated_codes": evaluated_codes,
            "code_source": code_source,
            "validation_focus": validation_focus,
            "execution_assumptions": dict(candidate.get("execution_assumptions") or {}),
            "portfolio_spec": dict(candidate.get("portfolio_spec") or {}),
            "generator_type": str(candidate.get("generator_type") or "").strip().lower(),
            "tags": sorted(
                str(tag).strip().lower()
                for tag in list(candidate.get("tags") or [])
                if str(tag).strip()
            ),
            "parent_strategy_id": str(candidate.get("parent_strategy_id") or "").strip(),
            "thresholds": self._get_thresholds(strategy_type, candidate),
        }
        serialized = json.dumps(
            self._json_safe(signature_payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"shared:{hashlib.sha1(serialized.encode('utf-8')).hexdigest()}"

    @staticmethod
    def _build_candidate_exception_result(candidate: dict, error: BaseException) -> dict:
        return {
            "passed": False,
            "reason_code": "candidate_exception",
            "reason": f"候选策略回测异常: {type(error).__name__}",
            "strategy_type": candidate.get("strategy_type") or "unknown",
            "sample_count": 0,
            "required_sample_count": 0,
            "evaluated_code_count": 0,
            "successful_code_count": 0,
            "evaluated_codes": [],
            "successful_codes": [],
            "target_codes": _extract_target_codes_from_payload(candidate),
            "representative_codes": [],
            "code_source": "candidate_exception",
            "primary_layer": "none",
            "queue_wait_ms": 0.0,
            "backtest_run_ms": 0.0,
            "code_run_ms_total": 0.0,
            "code_run_count": 0,
            "failed_metrics": [],
            "failed_codes": [],
            "skipped_codes": [],
            "metrics": {},
            "error": f"{type(error).__name__}: {error}",
        }

    @staticmethod
    def _annotate_shared_result(candidate: dict, result: dict, *, key: str, reused: bool, reuse_count: int) -> dict:
        payload = deepcopy(dict(result or {}))
        payload["constraint_check"] = dict(candidate.get("constraint_check") or payload.get("constraint_check") or {})
        payload["shared_result_key"] = key
        payload["shared_result_reused"] = bool(reused)
        payload["shared_result_reuse_count"] = max(0, int(reuse_count or 0))
        return payload

    def _apply_result_to_candidate(
        self,
        candidate: dict,
        result: dict,
        passed: List[dict],
        failed: List[dict],
    ) -> None:
        candidate["backtest_result"] = result
        if result.get("passed"):
            derived_trade_metrics = self._derive_trade_validation_metrics(candidate, result)
            candidate["backtest_metrics"] = {
                **dict(result.get("metrics") or {}),
                "constraint_check": dict(result.get("constraint_check") or {}),
                "target_quality_summary": dict(result.get("target_quality_summary") or {}),
                "validation_focus": result.get("validation_focus"),
                "primary_validation_layer": result.get("primary_validation_layer"),
                "event_window_config": dict(result.get("event_window_config") or {}),
                "contamination_summary": dict(result.get("contamination_summary") or {}),
                "cost_assumptions": dict(result.get("cost_assumptions") or {}),
                "explicit_cost_breakdown": dict(result.get("explicit_cost_breakdown") or {}),
                "implicit_cost_breakdown": dict(result.get("implicit_cost_breakdown") or {}),
                "tradability_summary": dict(result.get("tradability_summary") or {}),
                "capacity_summary": dict(result.get("capacity_summary") or {}),
                "implementation_shortfall_model_source": result.get("implementation_shortfall_model_source"),
                "implementation_shortfall_components": dict(result.get("implementation_shortfall_components") or {}),
                "position_assumption": result.get("position_assumption"),
                "target_layer_metrics": dict(((result.get("layers") or {}).get("target") or {}).get("metrics") or {}),
                "representative_layer_metrics": dict(((result.get("layers") or {}).get("representative") or {}).get("metrics") or {}),
                "combined_layer_metrics": dict(((result.get("layers") or {}).get("combined") or {}).get("metrics") or {}),
                "event_window_metrics": dict(result.get("event_window_metrics") or {}),
                "target_layer_oos_return": float((((result.get("layers") or {}).get("target") or {}).get("metrics") or {}).get("total_return") or 0.0),
                "post_cost_sharpe": float((result.get("metrics") or {}).get("sharpe_ratio") or 0.0),
                "backtest_assumptions": dict(result.get("backtest_assumptions") or {}),
                **derived_trade_metrics,
            }
            passed.append(candidate)
        else:
            candidate.pop("backtest_metrics", None)
            failed.append(candidate)

    def _build_last_report(self, candidates: List[dict], passed: List[dict], failed: List[dict]) -> dict:
        failed_reason_counts: Dict[str, int] = {}
        thresholds_by_type: Dict[str, dict] = {}
        candidate_run_ms_total = 0.0
        code_run_ms_total = 0.0
        code_run_count = 0
        cache_hit_total = 0
        evaluated_code_total = 0
        shared_result_reused_count = 0
        shared_result_keys: set[str] = set()
        for item in candidates:
            strategy_type = str(item.get("strategy_type") or "unknown")
            result = item.get("backtest_result") or {}
            thresholds_by_type[strategy_type] = result.get("thresholds") or self._get_thresholds(strategy_type, item)
            candidate_run_ms_total += float(result.get("backtest_run_ms") or 0.0)
            code_run_ms_total += float(result.get("code_run_ms_total") or 0.0)
            code_run_count += int(result.get("code_run_count") or 0)
            cache_hit_total += int(result.get("kline_cache_hit_count") or 0)
            evaluated_code_total += int(result.get("evaluated_code_count") or 0)
            shared_result_reused_count += int(bool(result.get("shared_result_reused")))
            if int(result.get("shared_result_reuse_count") or 0) > 0 and str(result.get("shared_result_key") or "").strip():
                shared_result_keys.add(str(result.get("shared_result_key")))
        for item in failed:
            reason_code = str((item.get("backtest_result") or {}).get("reason_code") or "unknown")
            failed_reason_counts[reason_code] = failed_reason_counts.get(reason_code, 0) + 1
        candidate_count = len(candidates)
        return {
            "summary": {
                "input_count": candidate_count,
                "passed_count": len(passed),
                "failed_count": len(failed),
                "strategy_type_counts": self._count_by_strategy_type(candidates),
                "passed_strategy_type_counts": self._count_by_strategy_type(passed),
                "failed_strategy_type_counts": self._count_by_strategy_type(failed),
                "failed_reason_counts": failed_reason_counts,
                "thresholds_by_type": thresholds_by_type,
                "avg_candidate_ms": round(candidate_run_ms_total / candidate_count, 2) if candidate_count else 0.0,
                "avg_code_ms": round(code_run_ms_total / code_run_count, 2) if code_run_count else 0.0,
                "cache_hit_ratio": round(cache_hit_total / evaluated_code_total, 4) if evaluated_code_total else 0.0,
                "shared_result_reused_count": shared_result_reused_count,
                "shared_result_group_count": len(shared_result_keys),
            },
            "passed": [self._build_report_entry(item) for item in passed],
            "failed": [self._build_report_entry(item) for item in failed],
        }

    async def filter(self, candidates: List[dict], db) -> List[dict]:
        BacktestEngine = get_backtest_engine_class()
        passed: List[dict] = []
        failed: List[dict] = []
        candidate_concurrency = int(_compat_setting("BACKTEST_CONCURRENCY", BACKTEST_CONCURRENCY) or BACKTEST_CONCURRENCY)
        sem = asyncio.Semaphore(candidate_concurrency)
        preload_codes = self._collect_preload_codes(candidates)
        if preload_codes:
            await self.preload_klines(db, preload_codes)
        shared_key_by_candidate: dict[int, str] = {}
        shared_groups: dict[str, list[dict]] = {}
        shared_group_order: list[str] = []
        for candidate in candidates:
            shared_key = self._build_shared_result_key(candidate)
            shared_key_by_candidate[id(candidate)] = shared_key
            if shared_key not in shared_groups:
                shared_groups[shared_key] = []
                shared_group_order.append(shared_key)
            shared_groups[shared_key].append(candidate)
        unique_candidates = [shared_groups[key][0] for key in shared_group_order]

        async def _test_guarded(candidate: dict) -> tuple:
            queued_at = time.perf_counter()
            async with sem:
                started_at = time.perf_counter()
                result = await self._test_one(candidate, db, BacktestEngine)
                result["queue_wait_ms"] = round((started_at - queued_at) * 1000, 2)
                return candidate, result

        results = await asyncio.gather(
            *[_test_guarded(c) for c in unique_candidates],
            return_exceptions=True,
        )
        shared_results: dict[str, dict] = {}
        for candidate, item in zip(unique_candidates, results):
            shared_key = shared_key_by_candidate[id(candidate)]
            reuse_count = max(len(shared_groups.get(shared_key) or []) - 1, 0)
            if isinstance(item, BaseException):
                logger.warning(
                    "BacktestFilter candidate failed unexpectedly strategy_type=%s error=%s",
                    candidate.get("strategy_type"),
                    item,
                    exc_info=item,
                )
                result = self._build_candidate_exception_result(candidate, item)
            else:
                _, result = item
            shared_results[shared_key] = self._annotate_shared_result(
                candidate,
                result,
                key=shared_key,
                reused=False,
                reuse_count=reuse_count,
            )
        for candidate in candidates:
            shared_key = shared_key_by_candidate[id(candidate)]
            leader = (shared_groups.get(shared_key) or [candidate])[0]
            result = shared_results.get(shared_key)
            if result is None:
                result = self._annotate_shared_result(
                    candidate,
                    self._build_candidate_exception_result(candidate, RuntimeError("missing_shared_result")),
                    key=shared_key,
                    reused=False,
                    reuse_count=0,
                )
            elif candidate is not leader:
                result = self._annotate_shared_result(
                    candidate,
                    result,
                    key=shared_key,
                    reused=True,
                    reuse_count=max(len(shared_groups.get(shared_key) or []) - 1, 0),
                )
            self._apply_result_to_candidate(candidate, result, passed, failed)
        self.last_report = self._build_last_report(candidates, passed, failed)
        return passed

    @staticmethod
    def _build_median_summary(results: List[dict]) -> dict:
        if not results:
            return {}
        avg_holding_days = [
            float(metric["avg_holding_days"])
            for metric in results
            if metric.get("avg_holding_days") is not None
        ]
        turnover_values = [
            float(metric["turnover_proxy"])
            for metric in results
            if metric.get("turnover_proxy") is not None
        ]
        return {
            "sharpe_ratio": float(median([metric["sharpe_ratio"] for metric in results])),
            "total_return": float(median([metric["total_return"] for metric in results])),
            "max_drawdown": float(median([metric["max_drawdown"] for metric in results])),
            "win_rate": float(median([metric.get("win_rate", 0) for metric in results])),
            "trades_count": float(median([metric["trades_count"] for metric in results])),
            "avg_holding_days": float(median(avg_holding_days)) if avg_holding_days else 0.0,
            "turnover_proxy": float(median(turnover_values)) if turnover_values else 0.0,
        }

    @staticmethod
    def _coerce_equity_curve(metric: dict) -> Optional[np.ndarray]:
        raw_curve = metric.get("equity_curve")
        if not isinstance(raw_curve, (list, tuple)):
            return None
        try:
            curve = np.asarray(raw_curve, dtype=float)
        except (TypeError, ValueError):
            return None
        if curve.ndim != 1 or curve.size < 2:
            return None
        if not np.all(np.isfinite(curve)) or float(curve[0]) <= 0 or np.any(curve <= 0):
            return None
        return curve

    @staticmethod
    def _resample_curve(curve: np.ndarray, target_len: int) -> np.ndarray:
        if curve.size == target_len:
            return curve.astype(float, copy=True)
        if target_len <= 1:
            return np.asarray([float(curve[-1])], dtype=float)
        source_x = np.linspace(0.0, 1.0, curve.size)
        target_x = np.linspace(0.0, 1.0, target_len)
        return np.interp(target_x, source_x, curve).astype(float, copy=False)

    @staticmethod
    def _weighted_average(values: List[float], weights: Optional[List[float]] = None) -> float:
        if not values:
            return 0.0
        if not weights or len(weights) != len(values) or sum(weights) <= 0:
            return float(sum(values) / len(values))
        total_weight = float(sum(weights))
        return float(sum(value * weight for value, weight in zip(values, weights)) / total_weight)

    @staticmethod
    def _normalize_weight_scheme(target_weight_scheme: str) -> str:
        normalized = str(target_weight_scheme or "single_name").strip().lower()
        if normalized in {"equal", "equal_weight_proxy"}:
            return "equal_weight"
        if not normalized:
            return "single_name"
        return normalized

    @staticmethod
    def _normalize_target_weight_map(
        codes: List[str],
        target_weight_map: Optional[dict[str, Any]],
    ) -> dict[str, float]:
        normalized_codes = [str(code or "").strip() for code in list(codes or []) if str(code or "").strip()]
        if not normalized_codes:
            return {}
        raw_map = dict(target_weight_map or {})
        weights: dict[str, float] = {}
        for code in normalized_codes:
            try:
                value = float(raw_map.get(code, 0.0) or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                weights[code] = value
        total = float(sum(weights.values()))
        if total <= 0:
            equal_weight = 1.0 / float(len(normalized_codes))
            return {code: equal_weight for code in normalized_codes}
        return {
            code: float(value) / total
            for code, value in weights.items()
        }

    @classmethod
    def _resolve_portfolio_allocation(
        cls,
        results: List[dict],
        *,
        target_weight_scheme: str,
        target_weight_map: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, float], str]:
        normalized_scheme = cls._normalize_weight_scheme(target_weight_scheme)
        codes = [
            str(metric.get("code") or "").strip()
            for metric in results
            if str(metric.get("code") or "").strip()
        ]
        if not codes:
            return {}, normalized_scheme
        if normalized_scheme == "single_name":
            return {codes[0]: 1.0}, normalized_scheme
        normalized_map = cls._normalize_target_weight_map(codes, target_weight_map)
        if not normalized_map:
            return {}, normalized_scheme
        return normalized_map, normalized_scheme

    @classmethod
    def _build_portfolio_curve_payload(
        cls,
        results: List[dict],
        *,
        target_weight_scheme: str,
        initial_capital: float,
        target_weight_map: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        if len(results) <= 1:
            return None

        allocation_weights, normalized_scheme = cls._resolve_portfolio_allocation(
            results,
            target_weight_scheme=target_weight_scheme,
            target_weight_map=target_weight_map,
        )
        if len(allocation_weights) <= 1:
            return None

        entries: List[tuple[str, np.ndarray, dict]] = []
        for metric in results:
            code = str(metric.get("code") or "").strip()
            if not code or code not in allocation_weights:
                continue
            curve = cls._coerce_equity_curve(metric)
            if curve is None:
                continue
            entries.append((code, curve / float(curve[0]), metric))
        if len(entries) <= 1:
            return None

        target_len = max(curve.size for _, curve, _ in entries)
        aggregated_curve = np.zeros(target_len, dtype=float)
        used_metrics: List[dict] = []
        used_weights: List[float] = []
        allocation_snapshot: dict[str, float] = {}
        for code, curve, metric in entries:
            weight = float(allocation_weights.get(code, 0.0) or 0.0)
            if weight <= 0:
                continue
            aggregated_curve += cls._resample_curve(curve, target_len) * weight
            allocation_snapshot[code] = round(weight, 6)
            used_metrics.append(metric)
            used_weights.append(weight)
        if len(used_metrics) <= 1:
            return None

        capital_base = max(float(initial_capital or 0.0), 1.0)
        aggregated_curve = aggregated_curve * capital_base
        allocation_mode = (
            "target_weight_map"
            if target_weight_map and normalized_scheme != "equal_weight"
            else "equal_weight"
        )
        aggregation_mode = (
            "portfolio_equal_weight"
            if allocation_mode == "equal_weight"
            else "portfolio_weighted"
        )
        return {
            "curve": aggregated_curve.astype(float, copy=False),
            "aggregation_mode": aggregation_mode,
            "allocation_mode": allocation_mode,
            "allocation_weights": allocation_snapshot,
            "component_count": len(used_metrics),
            "curve_points": int(target_len),
            "metrics": used_metrics,
            "weights": used_weights,
            "requested_weight_scheme": normalized_scheme,
        }

    @staticmethod
    def _metrics_from_equity_curve(curve: np.ndarray) -> dict:
        if curve.size < 2 or float(curve[0]) <= 0:
            return {
                "total_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
            }
        total_return = float(curve[-1] / curve[0] - 1.0)
        peaks = np.maximum.accumulate(curve)
        drawdowns = np.where(peaks > 0, (peaks - curve) / peaks, 0.0)
        max_drawdown = float(np.max(drawdowns)) if drawdowns.size else 0.0
        sharpe_ratio = 0.0
        prev = curve[:-1]
        curr = curve[1:]
        valid = prev > 0
        if np.any(valid):
            returns = (curr[valid] - prev[valid]) / prev[valid]
            returns = returns[np.isfinite(returns)]
            if returns.size > 1:
                std = float(np.std(returns))
                if std > 0:
                    annual_return = float(np.mean(returns)) * 252.0
                    annual_std = std * np.sqrt(252.0)
                    sharpe_ratio = float((annual_return - 0.02) / annual_std)
        return {
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
        }

    @classmethod
    def _summarize_portfolio_result_set(
        cls,
        results: List[dict],
        *,
        target_weight_scheme: str,
        initial_capital: float,
        target_weight_map: Optional[dict[str, Any]] = None,
    ) -> Optional[dict]:
        payload = cls._build_portfolio_curve_payload(
            results,
            target_weight_scheme=target_weight_scheme,
            initial_capital=initial_capital,
            target_weight_map=target_weight_map,
        )
        if payload is None:
            return None

        curve_metrics = list(payload.get("metrics") or [])
        portfolio_curve = np.asarray(payload["curve"], dtype=float)
        portfolio_metrics = cls._metrics_from_equity_curve(portfolio_curve)
        component_trade_counts = [max(float(metric.get("trades_count") or 0.0), 0.0) for metric in curve_metrics]
        trade_weights = component_trade_counts if sum(component_trade_counts) > 0 else None
        avg_holding_days = [
            float(metric.get("avg_holding_days") or 0.0)
            for metric in curve_metrics
        ]
        win_rates = [
            float(metric.get("win_rate") or 0.0)
            for metric in curve_metrics
        ]
        turnover_values = [
            float(metric.get("turnover_proxy") or 0.0)
            for metric in curve_metrics
        ]

        return {
            "sharpe_ratio": float(portfolio_metrics["sharpe_ratio"]),
            "total_return": float(portfolio_metrics["total_return"]),
            "max_drawdown": float(portfolio_metrics["max_drawdown"]),
            "win_rate": cls._weighted_average(win_rates, trade_weights),
            "trades_count": float(sum(component_trade_counts)),
            "avg_holding_days": cls._weighted_average(avg_holding_days, trade_weights or list(payload.get("weights") or [])),
            "turnover_proxy": cls._weighted_average(turnover_values, list(payload.get("weights") or [])),
            "aggregation_mode": str(payload.get("aggregation_mode") or "portfolio_equal_weight"),
            "allocation_mode": str(payload.get("allocation_mode") or "equal_weight"),
            "allocation_weights": dict(payload.get("allocation_weights") or {}),
            "requested_weight_scheme": str(payload.get("requested_weight_scheme") or target_weight_scheme or "equal_weight"),
            "component_count": int(payload.get("component_count") or len(curve_metrics)),
            "portfolio_curve_points": int(payload.get("curve_points") or portfolio_curve.size),
        }

    @classmethod
    def _summarize_result_set(
        cls,
        results: List[dict],
        *,
        target_weight_scheme: str = "single_name",
        initial_capital: float = 100000.0,
        target_weight_map: Optional[dict[str, Any]] = None,
    ) -> dict:
        if not results:
            return {}
        normalized_scheme = cls._normalize_weight_scheme(target_weight_scheme)
        if normalized_scheme != "single_name":
            portfolio_summary = cls._summarize_portfolio_result_set(
                results,
                target_weight_scheme=normalized_scheme,
                initial_capital=initial_capital,
                target_weight_map=target_weight_map,
            )
            if portfolio_summary:
                return portfolio_summary
            return {
                **cls._build_median_summary(results),
                "aggregation_mode": "median_proxy",
                "requested_weight_scheme": normalized_scheme,
                "component_count": len(results),
            }
        return cls._build_median_summary(results)

    @classmethod
    def _aggregate_result_curve(
        cls,
        results: List[dict],
        *,
        target_weight_scheme: str = "single_name",
        initial_capital: float = 100000.0,
        target_weight_map: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        if not results:
            return None
        normalized_scheme = cls._normalize_weight_scheme(target_weight_scheme)
        if normalized_scheme != "single_name":
            payload = cls._build_portfolio_curve_payload(
                results,
                target_weight_scheme=normalized_scheme,
                initial_capital=initial_capital,
                target_weight_map=target_weight_map,
            )
            if payload is not None:
                return {
                    "curve": np.asarray(payload["curve"], dtype=float),
                    "aggregation_mode": str(payload.get("aggregation_mode") or "portfolio_equal_weight"),
                    "allocation_mode": str(payload.get("allocation_mode") or "equal_weight"),
                    "allocation_weights": dict(payload.get("allocation_weights") or {}),
                    "component_count": int(payload.get("component_count") or 0),
                    "curve_points": int(payload.get("curve_points") or 0),
                }

        curves: List[np.ndarray] = []
        for metric in results:
            curve = cls._coerce_equity_curve(metric)
            if curve is None:
                continue
            curves.append(curve / float(curve[0]))
        if not curves:
            return None

        if len(curves) == 1:
            curve = curves[0] * max(float(initial_capital or 0.0), 1.0)
            return {
                "curve": curve,
                "aggregation_mode": "single_name_curve",
                "component_count": 1,
                "curve_points": int(curve.size),
            }

        target_len = max(curve.size for curve in curves)
        aligned_curves = np.vstack([cls._resample_curve(curve, target_len) for curve in curves])
        if normalized_scheme != "single_name":
            aggregated = np.mean(aligned_curves, axis=0) * max(float(initial_capital or 0.0), 1.0)
            mode = "portfolio_equal_weight"
        else:
            aggregated = np.median(aligned_curves, axis=0) * max(float(initial_capital or 0.0), 1.0)
            mode = "curve_median_proxy"
        return {
            "curve": aggregated.astype(float, copy=False),
            "aggregation_mode": mode,
            "component_count": len(curves),
            "curve_points": int(target_len),
        }

    @staticmethod
    def _daily_returns_from_curve(curve: np.ndarray) -> np.ndarray:
        if curve.size < 2:
            return np.array([], dtype=float)
        prev = curve[:-1]
        curr = curve[1:]
        valid = prev > 0
        if not np.any(valid):
            return np.array([], dtype=float)
        returns = (curr[valid] - prev[valid]) / prev[valid]
        returns = returns[np.isfinite(returns)]
        return returns.astype(float, copy=False)

    @classmethod
    def _build_event_window_metrics(
        cls,
        *,
        target_results: List[dict],
        representative_results: List[dict],
        fallback_results: List[dict],
        research_task: dict[str, Any],
        target_weight_scheme: str,
        initial_capital: float,
        target_weight_map: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        event_window = dict(research_task.get("event_window") or {})
        estimation_window = dict(research_task.get("estimation_window") or {})
        pre_days = max(0, int(event_window.get("pre_days") or 0))
        post_days = max(1, int(event_window.get("post_days") or 1))
        lookback_days = max(5, int(estimation_window.get("lookback_days") or 60))

        target_curve_payload = cls._aggregate_result_curve(
            target_results or fallback_results,
            target_weight_scheme=target_weight_scheme,
            initial_capital=initial_capital,
            target_weight_map=target_weight_map,
        )
        if target_curve_payload is None:
            return {}

        representative_curve_payload = cls._aggregate_result_curve(
            representative_results,
            target_weight_scheme=target_weight_scheme,
            initial_capital=initial_capital,
            target_weight_map=target_weight_map,
        )
        target_curve = np.asarray(target_curve_payload["curve"], dtype=float)
        representative_curve = None
        if representative_curve_payload is not None:
            common_points = max(int(target_curve.size), int(representative_curve_payload["curve"].size))
            target_curve = cls._resample_curve(target_curve, common_points)
            representative_curve = cls._resample_curve(
                np.asarray(representative_curve_payload["curve"], dtype=float),
                common_points,
            )

        target_returns = cls._daily_returns_from_curve(target_curve)
        if target_returns.size < 2:
            return {}

        if representative_curve is not None:
            representative_returns = cls._daily_returns_from_curve(representative_curve)
            aligned = min(target_returns.size, representative_returns.size)
            target_returns = target_returns[-aligned:]
            representative_returns = representative_returns[-aligned:]
            benchmark_source = "representative_curve"
        else:
            representative_returns = None
            benchmark_source = "estimation_mean"

        total_returns = int(target_returns.size)
        event_start = max(0, total_returns - post_days)
        pre_start = max(0, event_start - pre_days)
        estimation_end = pre_start if pre_start > 0 else event_start
        estimation_start = max(0, estimation_end - lookback_days)

        post_target = target_returns[event_start:]
        if representative_returns is not None:
            benchmark_estimation = representative_returns[estimation_start:estimation_end]
            post_benchmark = representative_returns[event_start:]
            pre_benchmark = representative_returns[pre_start:event_start]
        else:
            benchmark_estimation = target_returns[estimation_start:estimation_end]
            baseline = float(np.mean(benchmark_estimation)) if benchmark_estimation.size else 0.0
            post_benchmark = np.full(post_target.shape, baseline, dtype=float)
            pre_benchmark = np.full((max(0, event_start - pre_start),), baseline, dtype=float)

        pre_target = target_returns[pre_start:event_start]
        abnormal_post = post_target - post_benchmark
        abnormal_pre = pre_target - pre_benchmark if pre_target.size and pre_benchmark.size else np.array([], dtype=float)

        target_total_return = float(np.prod(1.0 + post_target) - 1.0) if post_target.size else 0.0
        benchmark_total_return = float(np.prod(1.0 + post_benchmark) - 1.0) if post_benchmark.size else 0.0
        abnormal_return = float(target_total_return - benchmark_total_return)
        car = float(np.sum(abnormal_post)) if abnormal_post.size else 0.0
        denom = max(float(np.prod(1.0 + post_benchmark)), 1e-9)
        bhar = float(np.prod(1.0 + post_target) / denom - 1.0) if post_target.size else 0.0
        hit_ratio = float(np.mean(abnormal_post > 0)) if abnormal_post.size else 0.0

        split = max(1, int(len(abnormal_post) // 2))
        early_car = float(np.sum(abnormal_post[:split])) if abnormal_post.size else 0.0
        late_car = float(np.sum(abnormal_post[split:])) if abnormal_post.size > split else 0.0
        decay_denominator = max(abs(early_car), 0.01)
        post_event_decay = float(late_car / decay_denominator - 1.0)

        return {
            "total_return": round(target_total_return, 4),
            "benchmark_return": round(benchmark_total_return, 4),
            "abnormal_return": round(abnormal_return, 4),
            "car": round(car, 4),
            "bhar": round(bhar, 4),
            "hit_ratio": round(hit_ratio, 4),
            "pre_event_abnormal_return": round(float(np.sum(abnormal_pre)) if abnormal_pre.size else 0.0, 4),
            "post_event_decay": round(post_event_decay, 4),
            "pre_days_used": int(event_start - pre_start),
            "post_days_used": int(post_target.size),
            "estimation_days_used": int(estimation_end - estimation_start),
            "benchmark_source": benchmark_source,
            "aggregation_mode": target_curve_payload.get("aggregation_mode"),
            "component_count": int(target_curve_payload.get("component_count") or 0),
            "curve_points": int(target_curve_payload.get("curve_points") or target_curve.size),
        }

    @staticmethod
    def _build_backtest_assumptions(candidate: dict) -> FactoryBacktestAssumptions:
        execution_assumptions = dict(candidate.get("execution_assumptions") or {})
        portfolio_spec = dict(candidate.get("portfolio_spec") or {})
        research_task = _normalize_research_task_contract(candidate.get("research_task"))
        target_symbols = _extract_target_codes_from_payload(candidate, limit=12)
        target_weight_scheme = str(
            portfolio_spec.get("target_weight_scheme")
            or ("equal_weight" if len(target_symbols) > 1 else "single_name")
        ).strip() or ("equal_weight" if len(target_symbols) > 1 else "single_name")
        return FactoryBacktestAssumptions(
            initial_capital=float(execution_assumptions.get("initial_capital", 100000) or 100000),
            commission_rate=float(execution_assumptions.get("commission_rate", 0.00025) or 0.00025),
            slippage_bps=float(
                execution_assumptions.get("slippage_bps", 0.0)
                or float(execution_assumptions.get("slippage", 0.0) or 0.0) * 10000.0
            ),
            market_impact_bps=float(execution_assumptions.get("market_impact_bps", 0.0) or 0.0),
            arrival_price_policy=str(execution_assumptions.get("arrival_price_policy") or "next_open_proxy"),
            implementation_shortfall_proxy=float(execution_assumptions.get("implementation_shortfall_proxy", 0.0) or 0.0),
            tradability_filter=bool(execution_assumptions.get("tradability_filter", True)),
            slippage_model=execution_assumptions.get("slippage_model") or "fixed",
            max_position_pct=float(portfolio_spec.get("max_position_pct")) if portfolio_spec.get("max_position_pct") is not None else None,
            capacity_participation_rate=float(execution_assumptions.get("capacity_participation_rate", 0.0) or 0.0),
            adv_ratio_limit=float(execution_assumptions.get("adv_ratio_limit", 0.0) or 0.0),
            capacity_bucket=execution_assumptions.get("capacity_bucket"),
            position_assumption=portfolio_spec.get("position_assumption") or ("equal_weight_proxy" if len(target_symbols) > 1 else "single_name_full_notional"),
            target_weight_scheme=target_weight_scheme,
            target_weight_map=dict(portfolio_spec.get("target_weight_map") or {}),
            market_ruleset=str(execution_assumptions.get("market_ruleset") or "cn_equity"),
            sell_tax_rate=float(execution_assumptions.get("sell_tax_rate", 0.001) or 0.001),
            min_trade_lot=max(1, int(execution_assumptions.get("min_trade_lot", 100) or 100)),
            t_plus_one=bool(execution_assumptions.get("t_plus_one", True)),
            validation_focus=research_task.get("validation_focus") or "target_plus_representative",
        )

    @staticmethod
    def _derive_trade_validation_metrics(candidate: dict, result: dict) -> dict[str, Any]:
        metrics = dict(result.get("metrics") or {})
        layers = dict(result.get("layers") or {})
        target_metrics = dict((layers.get("target") or {}).get("metrics") or {})
        representative_metrics = dict((layers.get("representative") or {}).get("metrics") or {})
        combined_metrics = dict((layers.get("combined") or {}).get("metrics") or {})
        research_task = _normalize_research_task_contract(candidate.get("research_task") or {})
        event_window = dict(research_task.get("event_window") or {})
        holding_window = dict(research_task.get("holding_window") or {})
        holding_horizon = dict(candidate.get("holding_horizon") or {})
        risk_rules = dict(candidate.get("risk_rules") or {})

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
        event_window_metrics = dict(result.get("event_window_metrics") or {})
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
        observation_days = max(1.0, lookback_days + post_days)
        trade_density = round(trade_count / observation_days * 20.0, 4)

        target_sharpe = float(target_metrics.get("sharpe_ratio") or metrics.get("sharpe_ratio") or 0.0)
        combined_sharpe = float(combined_metrics.get("sharpe_ratio") or metrics.get("sharpe_ratio") or 0.0)
        representative_sharpe = float(representative_metrics.get("sharpe_ratio") or 0.0)
        stability_scale = max(abs(target_sharpe), abs(combined_sharpe), abs(representative_sharpe), 0.25)
        stability_dispersion = abs(target_sharpe - combined_sharpe) + abs(target_sharpe - representative_sharpe)
        parameter_stability = round(max(0.0, min(1.0, 1.0 - stability_dispersion / (stability_scale * 4.0))), 4)

        return {
            "avg_holding_days": round(avg_holding_days, 4),
            "turnover_proxy": round(turnover_proxy, 4),
            "target_layer_oos_return": round(target_layer_oos_return, 4),
            "target_layer_abnormal_return": round(target_layer_abnormal_return, 4),
            "event_window_hit_ratio": round(event_window_hit_ratio, 4),
            "post_event_decay": round(post_event_decay, 4),
            "trade_density": round(trade_density, 4),
            "parameter_perturbation_trade_stability": round(parameter_stability, 4),
        }

    @staticmethod
    def _resolve_backtest_plan(candidate: dict) -> tuple[List[str], List[str], List[str], str, str]:
        target_codes = _extract_target_codes_from_payload(candidate, limit=12)
        raw_research_task = candidate.get("research_task") or {}
        research_task = _normalize_research_task_contract(raw_research_task)
        validation_focus = str(research_task.get("validation_focus") or "target_plus_representative").strip().lower()
        representative_stocks = list(_compat_setting("REPRESENTATIVE_STOCKS", REPRESENTATIVE_STOCKS))
        representative_codes = [code for code in representative_stocks if code not in target_codes]
        has_explicit_research_task = bool(raw_research_task)

        if not has_explicit_research_task:
            if target_codes:
                return list(target_codes), target_codes, representative_codes, "candidate_target_symbols", "candidate_target_only"
            return list(representative_stocks), target_codes, representative_codes, "representative_only", "target_plus_representative"

        if validation_focus == "event_target_only" and target_codes:
            evaluated_codes = list(target_codes)
            code_source = "event_target_only"
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

    async def _test_one(self, candidate: dict, db, engine) -> dict:
        factory_pkg = _get_strategy_factory_package()
        strategy_type = str(candidate.get("strategy_type") or "unknown")
        thresholds = self._get_thresholds(strategy_type, candidate)
        results: List[dict] = []
        successful_codes: List[str] = []
        skipped_codes: List[dict] = []
        failed_codes: List[dict] = []
        evaluated_codes, target_codes, representative_codes, code_source, validation_focus = self._resolve_backtest_plan(candidate)
        assumptions = self._build_backtest_assumptions(candidate)
        assumptions_kwargs = assumptions.to_backtest_kwargs()
        research_task = _normalize_research_task_contract(candidate.get("research_task"))
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
                result = await factory_pkg.asyncio.to_thread(
                    engine.run_backtest,
                    code,
                    klines,
                    candidate["strategy_type"],
                    {
                        **candidate["params"],
                        **assumptions_kwargs,
                    },
                )
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

        target_metrics = self._summarize_result_set(
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
        combined_metrics = self._summarize_result_set(
            results,
            target_weight_scheme=assumptions.target_weight_scheme,
            initial_capital=assumptions.initial_capital,
            target_weight_map=assumptions.target_weight_map,
        )
        event_window_metrics = self._build_event_window_metrics(
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
        sample_audit = dict(primary_results[0] or {}) if primary_results else (dict(results[0] or {}) if results else {})
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
            return payload

        base_result = {
            "passed": False,
            "reason_code": "unknown",
            "reason": "初筛回测未完成",
            "strategy_type": strategy_type,
            "sample_count": len(primary_results),
            "required_sample_count": thresholds["min_samples"],
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
            "implementation_shortfall_model_source": sample_audit.get("implementation_shortfall_model_source"),
            "implementation_shortfall_components": dict(sample_audit.get("implementation_shortfall_components") or {}),
            "position_assumption": sample_audit.get("position_assumption"),
            "backtest_assumptions": assumptions.to_audit_dict(),
            "portfolio_backtest_mode": (
                "weighted_multi_name"
                if assumptions.target_weight_scheme != "single_name" and len(target_codes) > 1
                else "single_name"
            ),
            "portfolio_backtest_coverage": (
                1.0
                if assumptions.target_weight_scheme != "single_name" and len(target_codes) > 1 and bool(target_metrics)
                else 0.0
            ),
            "layers": {
                "target": {
                    "requested_codes": target_codes,
                    "successful_codes": layer_successful_codes["target"],
                    "sample_count": len(layer_results["target"]),
                    "metrics": target_metrics,
                },
                "representative": {
                    "requested_codes": representative_codes,
                    "successful_codes": layer_successful_codes["representative"],
                    "sample_count": len(layer_results["representative"]),
                    "metrics": representative_metrics,
                },
                "combined": {
                    "requested_codes": evaluated_codes,
                    "successful_codes": successful_codes,
                    "sample_count": len(results),
                    "metrics": combined_metrics,
                },
            },
            "event_window_metrics": dict(event_window_metrics or target_metrics or combined_metrics),
            "metrics": {},
            "failed_metric": None,
        }

        if len(primary_results) < thresholds["min_samples"]:
            return _finalize_result({
                **base_result,
                "reason_code": "insufficient_samples",
                "reason": f"有效样本 {len(primary_results)} 小于要求 {thresholds['min_samples']}",
                "failed_metric": self._build_failed_metric("sample_count", "<", thresholds["min_samples"], len(primary_results), "有效样本数"),
            })

        avg = self._summarize_result_set(
            primary_results,
            target_weight_scheme=assumptions.target_weight_scheme,
            initial_capital=assumptions.initial_capital,
            target_weight_map=assumptions.target_weight_map,
        )
        if avg["sharpe_ratio"] < thresholds["sharpe_min"]:
            return _finalize_result({
                **base_result,
                "reason_code": "sharpe_below_threshold",
                "reason": f"Sharpe {avg['sharpe_ratio']:.4f} 低于阈值 {thresholds['sharpe_min']:.2f}",
                "metrics": avg,
                "failed_metric": self._build_failed_metric("sharpe_ratio", "<", thresholds["sharpe_min"], round(avg["sharpe_ratio"], 4), "Sharpe"),
            })
        if abs(avg["max_drawdown"]) > thresholds["mdd_max"]:
            return _finalize_result({
                **base_result,
                "reason_code": "max_drawdown_above_threshold",
                "reason": f"回撤 {abs(avg['max_drawdown']):.4f} 高于阈值 {thresholds['mdd_max']:.2f}",
                "metrics": avg,
                "failed_metric": self._build_failed_metric("max_drawdown", ">", thresholds["mdd_max"], round(abs(avg["max_drawdown"]), 4), "最大回撤"),
            })
        if avg["trades_count"] < thresholds["trades_min"]:
            return _finalize_result({
                **base_result,
                "reason_code": "trades_below_threshold",
                "reason": f"交易次数 {avg['trades_count']:.1f} 低于阈值 {thresholds['trades_min']}",
                "metrics": avg,
                "failed_metric": self._build_failed_metric("trades_count", "<", thresholds["trades_min"], round(avg["trades_count"], 4), "交易次数"),
            })
        return _finalize_result({
            **base_result,
            "passed": True,
            "reason_code": "passed",
            "reason": "通过初筛回测",
            "metrics": avg,
        })
