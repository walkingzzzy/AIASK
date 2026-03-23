"""策略工厂回测初筛。"""

from __future__ import annotations

import asyncio
import logging
import time
from statistics import median
from typing import Any, Dict, List, Optional

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

    def _build_last_report(self, candidates: List[dict], passed: List[dict], failed: List[dict]) -> dict:
        failed_reason_counts: Dict[str, int] = {}
        thresholds_by_type: Dict[str, dict] = {}
        candidate_run_ms_total = 0.0
        code_run_ms_total = 0.0
        code_run_count = 0
        cache_hit_total = 0
        evaluated_code_total = 0
        for item in candidates:
            strategy_type = str(item.get("strategy_type") or "unknown")
            result = item.get("backtest_result") or {}
            thresholds_by_type[strategy_type] = result.get("thresholds") or self._get_thresholds(strategy_type, item)
            candidate_run_ms_total += float(result.get("backtest_run_ms") or 0.0)
            code_run_ms_total += float(result.get("code_run_ms_total") or 0.0)
            code_run_count += int(result.get("code_run_count") or 0)
            cache_hit_total += int(result.get("kline_cache_hit_count") or 0)
            evaluated_code_total += int(result.get("evaluated_code_count") or 0)
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

        async def _test_guarded(candidate: dict) -> tuple:
            queued_at = time.perf_counter()
            async with sem:
                started_at = time.perf_counter()
                result = await self._test_one(candidate, db, BacktestEngine)
                result["queue_wait_ms"] = round((started_at - queued_at) * 1000, 2)
                return candidate, result

        results = await asyncio.gather(
            *[_test_guarded(c) for c in candidates],
            return_exceptions=True,
        )
        for candidate, item in zip(candidates, results):
            if isinstance(item, BaseException):
                logger.warning(
                    "BacktestFilter candidate failed unexpectedly strategy_type=%s error=%s",
                    candidate.get("strategy_type"),
                    item,
                    exc_info=item,
                )
                candidate["backtest_result"] = {
                    "passed": False,
                    "reason_code": "candidate_exception",
                    "reason": f"候选策略回测异常: {type(item).__name__}",
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
                    "error": f"{type(item).__name__}: {item}",
                }
                candidate.pop("backtest_metrics", None)
                failed.append(candidate)
                continue
            _, result = item
            candidate["backtest_result"] = result
            if result.get("passed"):
                derived_trade_metrics = self._derive_trade_validation_metrics(candidate, result)
                candidate["backtest_metrics"] = {
                    **dict(result.get("metrics") or {}),
                    "constraint_check": dict(result.get("constraint_check") or {}),
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
        self.last_report = self._build_last_report(candidates, passed, failed)
        return passed

    @staticmethod
    def _summarize_result_set(results: List[dict]) -> dict:
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
        event_window_return = float((result.get("event_window_metrics") or {}).get("total_return") or target_layer_oos_return or combined_return or 0.0)
        target_layer_abnormal_return = round(target_layer_oos_return - representative_return, 4)

        decay_denominator = max(abs(event_window_return), 0.01)
        post_event_decay = round((target_layer_oos_return - event_window_return) / decay_denominator, 4)

        event_window_positive = 1.0 if event_window_return > 0 else 0.0
        target_outperform = 1.0 if target_layer_abnormal_return > 0 else 0.0
        target_positive = 1.0 if target_layer_oos_return > 0 else 0.0
        event_window_hit_ratio = round((event_window_positive + target_outperform + target_positive) / 3.0, 4)

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

        target_metrics = self._summarize_result_set(layer_results["target"])
        representative_metrics = self._summarize_result_set(layer_results["representative"])
        combined_metrics = self._summarize_result_set(results)
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
            "event_window_metrics": dict(target_metrics or combined_metrics),
            "metrics": {},
            "failed_metric": None,
        }

        if len(primary_results) < thresholds["min_samples"]:
            return {
                **base_result,
                "reason_code": "insufficient_samples",
                "reason": f"有效样本 {len(primary_results)} 小于要求 {thresholds['min_samples']}",
                "failed_metric": self._build_failed_metric("sample_count", "<", thresholds["min_samples"], len(primary_results), "有效样本数"),
            }

        avg = self._summarize_result_set(primary_results)
        if avg["sharpe_ratio"] < thresholds["sharpe_min"]:
            return {
                **base_result,
                "reason_code": "sharpe_below_threshold",
                "reason": f"Sharpe {avg['sharpe_ratio']:.4f} 低于阈值 {thresholds['sharpe_min']:.2f}",
                "metrics": avg,
                "failed_metric": self._build_failed_metric("sharpe_ratio", "<", thresholds["sharpe_min"], round(avg["sharpe_ratio"], 4), "Sharpe"),
            }
        if abs(avg["max_drawdown"]) > thresholds["mdd_max"]:
            return {
                **base_result,
                "reason_code": "max_drawdown_above_threshold",
                "reason": f"回撤 {abs(avg['max_drawdown']):.4f} 高于阈值 {thresholds['mdd_max']:.2f}",
                "metrics": avg,
                "failed_metric": self._build_failed_metric("max_drawdown", ">", thresholds["mdd_max"], round(abs(avg["max_drawdown"]), 4), "最大回撤"),
            }
        if avg["trades_count"] < thresholds["trades_min"]:
            return {
                **base_result,
                "reason_code": "trades_below_threshold",
                "reason": f"交易次数 {avg['trades_count']:.1f} 低于阈值 {thresholds['trades_min']}",
                "metrics": avg,
                "failed_metric": self._build_failed_metric("trades_count", "<", thresholds["trades_min"], round(avg["trades_count"], 4), "交易次数"),
            }
        return {
            **base_result,
            "passed": True,
            "reason_code": "passed",
            "reason": "通过初筛回测",
            "metrics": avg,
        }
