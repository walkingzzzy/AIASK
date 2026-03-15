"""策略工厂回测初筛。"""

from __future__ import annotations

import asyncio
import time
from statistics import median
from typing import Any, Dict, List, Optional

from .constants import (
    BACKTEST_AI_PROTOTYPE_THRESHOLDS,
    BACKTEST_CONCURRENCY,
    BACKTEST_CODE_CONCURRENCY,
    BACKTEST_DEFAULT_THRESHOLDS,
    BACKTEST_TYPE_THRESHOLDS,
    REPRESENTATIVE_STOCKS,
)
from .utils import _extract_target_codes_from_payload, get_strategy_factory_package


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
        codes = list(dict.fromkeys(codes or list(REPRESENTATIVE_STOCKS)))
        sem = asyncio.Semaphore(BACKTEST_CODE_CONCURRENCY)

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
            **BACKTEST_DEFAULT_THRESHOLDS,
            **(BACKTEST_TYPE_THRESHOLDS.get(strategy_type) or {}),
        }
        candidate = dict(candidate or {})
        tags = {str(tag).strip().lower() for tag in list(candidate.get("tags") or [])}
        generator_type = str(candidate.get("generator_type") or "").strip().lower()
        if (
            strategy_type == "dsl_rule"
            or generator_type == "external_llm"
            or "external_llm" in tags
            or "llm_proxy_fallback" in tags
        ):
            thresholds = {**thresholds, **BACKTEST_AI_PROTOTYPE_THRESHOLDS}
        return thresholds

    @classmethod
    def _collect_preload_codes(cls, candidates: List[dict]) -> List[str]:
        ordered_codes: List[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            evaluated_codes, _, _, _ = cls._resolve_backtest_codes(candidate)
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
        from ..backtest.engine import BacktestEngine

        passed: List[dict] = []
        failed: List[dict] = []
        sem = asyncio.Semaphore(BACKTEST_CONCURRENCY)
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
        for item in results:
            if isinstance(item, BaseException):
                continue
            candidate, result = item
            candidate["backtest_result"] = result
            if result.get("passed"):
                candidate["backtest_metrics"] = result.get("metrics") or {}
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
        return {
            "sharpe_ratio": float(median([metric["sharpe_ratio"] for metric in results])),
            "total_return": float(median([metric["total_return"] for metric in results])),
            "max_drawdown": float(median([metric["max_drawdown"] for metric in results])),
            "win_rate": float(median([metric.get("win_rate", 0) for metric in results])),
            "trades_count": float(median([metric["trades_count"] for metric in results])),
        }

    @staticmethod
    def _resolve_backtest_codes(candidate: dict) -> tuple[List[str], List[str], List[str], str]:
        target_codes = _extract_target_codes_from_payload(candidate, limit=12)
        representative_codes = [code for code in REPRESENTATIVE_STOCKS if code not in target_codes]
        evaluated_codes = list(dict.fromkeys([*target_codes, *REPRESENTATIVE_STOCKS]))
        return evaluated_codes, target_codes, representative_codes, ("candidate_target_symbols" if target_codes else "representative_only")

    async def _test_one(self, candidate: dict, db, engine) -> dict:
        factory_pkg = get_strategy_factory_package()
        strategy_type = str(candidate.get("strategy_type") or "unknown")
        thresholds = self._get_thresholds(strategy_type, candidate)
        results: List[dict] = []
        successful_codes: List[str] = []
        skipped_codes: List[dict] = []
        failed_codes: List[dict] = []
        evaluated_codes, target_codes, representative_codes, code_source = self._resolve_backtest_codes(candidate)
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
                    {**candidate["params"], "initial_capital": 100000, "commission": 0.00025},
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
            except Exception:
                return {
                    "code": code,
                    "layer": layer,
                    "status": "failed",
                    "reason": "exception",
                    "cache_hit": cache_hit,
                    "run_ms": round((time.perf_counter() - started_at) * 1000, 2),
                }

        code_sem = asyncio.Semaphore(BACKTEST_CODE_CONCURRENCY)

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

        primary_results = layer_results["target"] if len(layer_results["target"]) >= thresholds["min_samples"] else results
        primary_layer = "target" if len(layer_results["target"]) >= thresholds["min_samples"] else "combined"
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
            "queue_wait_ms": 0.0,
            "backtest_run_ms": round((time.perf_counter() - candidate_started_at) * 1000, 2),
            "code_run_ms_total": round(code_run_ms_total, 2),
            "code_run_count": len(code_results),
            "avg_code_ms": round(code_run_ms_total / len(code_results), 2) if code_results else 0.0,
            "kline_cache_hit_count": kline_cache_hit_count,
            "skipped_codes": skipped_codes,
            "failed_codes": failed_codes,
            "thresholds": thresholds,
            "layers": {
                "target": {
                    "requested_codes": target_codes,
                    "successful_codes": layer_successful_codes["target"],
                    "sample_count": len(layer_results["target"]),
                    "metrics": self._summarize_result_set(layer_results["target"]),
                },
                "representative": {
                    "requested_codes": representative_codes,
                    "successful_codes": layer_successful_codes["representative"],
                    "sample_count": len(layer_results["representative"]),
                    "metrics": self._summarize_result_set(layer_results["representative"]),
                },
            },
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
