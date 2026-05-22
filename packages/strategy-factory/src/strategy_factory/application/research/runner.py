"""Research plane runner for the strategy factory.

P3 goal: make factor research, task planning, local rule generation, and
external autonomy generation observable as one independent research plane that
only outputs candidates and evidence.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any

from .candidate_origin import count_candidate_origins
from ..candidate_contract import apply_resolved_candidate_envelope
from .contracts import build_research_plane_artifact
from ..services.task_orchestrator import TaskOrchestrator
from ...domain.constants import (
    FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
    is_factory_factor_auto_refresh_enabled,
)
from ...domain.strategy_profile import apply_candidate_strategy_profile
from ..services.readiness_service import resolve_factor_refresh_trigger

logger = logging.getLogger(__name__)

_GATE_1_MIN_KLINES = 250


@dataclass(slots=True)
class ResearchGenerationResult:
    local_candidates: list[dict[str, Any]] = field(default_factory=list)
    autonomy_candidates: list[dict[str, Any]] = field(default_factory=list)
    generated_candidates: list[dict[str, Any]] = field(default_factory=list)
    local_spawn_report: dict[str, Any] = field(default_factory=dict)
    autonomy_stage: dict[str, Any] = field(default_factory=dict)
    experiments: list[dict[str, Any]] = field(default_factory=list)
    full_market_topn: dict[str, Any] = field(default_factory=dict)
    full_market_score_rows: list[dict[str, Any]] = field(default_factory=list)
    autonomy_error: str | None = None
    candidate_origin_counts: dict[str, int] = field(default_factory=dict)

    @property
    def local_rule_candidate_count(self) -> int:
        return int(self.candidate_origin_counts.get("local_rule") or 0)

    @property
    def external_autonomy_candidate_count(self) -> int:
        return int(self.candidate_origin_counts.get("external_autonomy") or 0)

    @property
    def governed_candidate_activation_count(self) -> int:
        return int(self.candidate_origin_counts.get("governed_candidate_activation") or 0)


class ResearchPlaneRunner:
    """Owns research-plane generation before governance begins."""

    def __init__(self, scheduler: Any, factory_pkg: Any) -> None:
        self._scheduler = scheduler
        self._factory_pkg = factory_pkg

    async def build_factor_research_artifact(
        self,
        factor_gateway: Any,
        db: Any,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        gateway_db = self._scheduler._adapt_gateway_repository(db)
        auto_refresh_enabled = is_factory_factor_auto_refresh_enabled()
        self_heal_refresh_enabled = bool(snapshot.get("_factor_refresh_self_heal"))
        refresh_meta: dict[str, Any] = {
            "auto_refresh_enabled": auto_refresh_enabled,
            "refresh_attempted": False,
            "refresh_status": "not_needed",
            "refresh_trigger": None,
            "refresh_error": None,
            "refreshed_before_build": False,
            "refresh_result": {},
            "refresh_timeout_sec": FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
            "refresh_mode": (
                "auto"
                if auto_refresh_enabled
                else ("self_heal_enabled" if self_heal_refresh_enabled else "manual_disabled")
            ),
        }
        artifact = dict(await factor_gateway.build_artifact(gateway_db, snapshot) or {})
        summary = dict(artifact.get("summary") or {})
        refresh_trigger = resolve_factor_refresh_trigger(artifact, factor_summary=summary)
        refresh = getattr(factor_gateway, "refresh", None)
        self_heal_refresh_allowed = bool(
            refresh_trigger
            and callable(refresh)
            and self_heal_refresh_enabled
            and refresh_trigger in {
                "stale_artifact",
                "seed_fallback_without_governed_pool",
                "scheduler_warmup_missing_governed_pool",
                "governed_pool_missing_after_scheduler_success",
            }
        )
        should_refresh = bool(
            refresh_trigger
            and callable(refresh)
            and (auto_refresh_enabled or self_heal_refresh_allowed)
        )
        if should_refresh:
            refresh_meta["refresh_attempted"] = True
            refresh_meta["refresh_trigger"] = refresh_trigger
            refresh_meta["refresh_mode"] = (
                "auto" if auto_refresh_enabled else "self_heal"
            )
            try:
                refresh_result = refresh()
                if inspect.isawaitable(refresh_result):
                    refresh_result = await asyncio.wait_for(
                        refresh_result,
                        timeout=FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
                    )
                refresh_meta["refresh_status"] = "success"
                refresh_meta["refresh_result"] = self._scheduler._summarize_refresh_result(
                    refresh_result
                )
                refresh_meta["refreshed_before_build"] = True
                artifact = dict(await factor_gateway.build_artifact(gateway_db, snapshot) or {})
            except asyncio.TimeoutError:
                refresh_meta["refresh_status"] = "timeout"
                refresh_meta["refresh_error"] = (
                    f"factor refresh exceeded {FACTORY_FACTOR_REFRESH_TIMEOUT_SEC}s"
                )
            except Exception as exc:
                refresh_meta["refresh_status"] = "failed"
                refresh_meta["refresh_error"] = str(exc)
        elif not auto_refresh_enabled:
            refresh_meta["refresh_status"] = "disabled"
        return self._scheduler._inject_factor_refresh_meta(artifact, refresh_meta)

    def build_research_plane(
        self,
        *,
        snapshot: dict[str, Any],
        readiness: dict[str, Any] | None = None,
        autonomy_stage: dict[str, Any] | None = None,
        candidates: list[dict[str, Any]] | None = None,
        experiments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return build_research_plane_artifact(
            factor_research=snapshot.get("factor_research"),
            readiness=readiness,
            autonomy_stage=autonomy_stage,
            candidates=candidates,
            experiments=experiments,
        )

    async def run_generation(
        self,
        db: Any,
        snapshot: dict[str, Any],
    ) -> ResearchGenerationResult:
        spawner = self._factory_pkg.StrategySpawner()
        local_candidates = list(spawner.spawn(snapshot) or [])

        # 方案 C: Inject adaptive candidates based on factor IC signals
        try:
            from ...domain.adaptive_parameters import get_adaptive_candidates
            preferred_types = list(
                (snapshot.get("factor_research") or {}).get("preferred_strategy_types")
                or snapshot.get("preferred_strategy_types")
                or ["momentum", "ma_cross", "growth_factor"]
            )
            adaptive_candidates = await get_adaptive_candidates(db, preferred_types, snapshot)
            if adaptive_candidates:
                local_candidates.extend(adaptive_candidates)
        except Exception as exc:
            logger.debug("ResearchPlaneRunner: adaptive candidates failed: %s", exc)

        local_candidates, target_sanitization = await self._sanitize_local_spawn_targets(
            local_candidates,
            db,
        )
        local_spawn_report = (
            spawner.get_last_report()
            if hasattr(spawner, "get_last_report")
            else {"summary": {"candidate_count": len(local_candidates)}}
        )
        local_spawn_report = self._annotate_local_spawn_report(
            local_spawn_report,
            target_sanitization=target_sanitization,
        )
        autonomy_stage: dict[str, Any] = {"generated_count": 0}
        autonomy_candidates: list[dict[str, Any]] = []
        experiments: list[dict[str, Any]] = []
        autonomy_error: str | None = None
        try:
            autonomy_batch = await TaskOrchestrator(self._scheduler).run(db, snapshot)
            autonomy_stage = autonomy_batch.to_stage_dict()
            autonomy_candidates = list(autonomy_batch.generated_candidates or [])
            experiments = list(autonomy_batch.experiments or [])
            full_market_topn = dict(autonomy_batch.full_market_topn or {})
            full_market_score_rows = list(autonomy_batch.full_market_score_rows or [])
            if full_market_topn:
                autonomy_stage["full_market_topn"] = full_market_topn
            self._annotate_autonomy_candidates(autonomy_candidates, autonomy_stage)
        except Exception as exc:
            logger.warning("StrategyFactory: autonomy cycle failed: %s", exc)
            autonomy_error = str(exc)
            autonomy_stage = {"error": autonomy_error, "generated_count": 0}
            full_market_topn = {}
            full_market_score_rows = []

        profiled_local_candidates = [
            apply_resolved_candidate_envelope(
                apply_candidate_strategy_profile(candidate, snapshot=snapshot)
            )
            for candidate in local_candidates
        ]
        profiled_autonomy_candidates = [
            apply_resolved_candidate_envelope(
                apply_candidate_strategy_profile(candidate, snapshot=snapshot)
            )
            for candidate in autonomy_candidates
        ]

        # Enrich candidate names with target stock + style info
        from ...domain.naming import _auto_name
        for candidate in [*profiled_local_candidates, *profiled_autonomy_candidates]:
            if candidate.get("strategy_type") and candidate.get("params"):
                enriched_name = _auto_name(candidate["strategy_type"], candidate["params"])
                if enriched_name and enriched_name != f"{candidate['strategy_type']}策略":
                    candidate["name"] = enriched_name

        generated_candidates = [
            *profiled_local_candidates,
            *profiled_autonomy_candidates,
        ]

        # PR-A2: 强制注入 A 股交易规则默认值，确保所有候选回测时使用真实成本
        _A_SHARE_BACKTEST_DEFAULTS = {
            "market_ruleset": "cn_equity",
            "commission": 0.00025,
            "sell_tax_rate": 0.001,
            "min_trade_lot": 100,
            "t_plus_one": True,
            "tradability_filter": True,
            "arrival_price_policy": "next_open_proxy",
        }
        for _candidate in generated_candidates:
            _params = dict(_candidate.get("params") or {})
            for _k, _v in _A_SHARE_BACKTEST_DEFAULTS.items():
                _params.setdefault(_k, _v)
            _candidate["params"] = _params

        # PR-AI1: 股票代码白名单过滤 — 剔除 LLM 幻觉出的无效代码
        generated_candidates = await self._filter_invalid_symbols(generated_candidates, db)

        return ResearchGenerationResult(
            local_candidates=profiled_local_candidates,
            autonomy_candidates=profiled_autonomy_candidates,
            generated_candidates=generated_candidates,
            local_spawn_report=dict(local_spawn_report or {}),
            autonomy_stage=autonomy_stage,
            experiments=experiments,
            full_market_topn=full_market_topn,
            full_market_score_rows=full_market_score_rows,
            autonomy_error=autonomy_error,
            candidate_origin_counts=count_candidate_origins(generated_candidates),
        )

    @staticmethod
    def _annotate_autonomy_candidates(
        candidates: list[dict[str, Any]],
        autonomy_stage: dict[str, Any],
    ) -> None:
        factory_attempt_count = int(autonomy_stage.get("external_llm_attempt_count") or 0)
        factory_stage_attempt_count = int(
            autonomy_stage.get("external_llm_stage_attempt_count")
            or factory_attempt_count
        )
        factory_network_request_count = int(
            autonomy_stage.get("external_llm_network_request_count") or 0
        )
        factory_compatibility_skip_count = int(
            autonomy_stage.get("external_llm_compatibility_skip_count") or 0
        )
        factory_cooldown_skip_count = int(
            autonomy_stage.get("external_llm_cooldown_skip_count") or 0
        )
        factory_selected_count = int(autonomy_stage.get("external_llm_selected_count") or 0)
        for ai_candidate in list(candidates or []):
            params = dict(ai_candidate.get("params") or {})
            params["factory_global_attempt_count"] = factory_attempt_count
            params["factory_global_selected_count"] = factory_selected_count
            params["factory_attempt_count"] = factory_attempt_count
            params["factory_stage_attempt_count"] = factory_stage_attempt_count
            params["factory_network_request_count"] = factory_network_request_count
            params["factory_compatibility_skip_count"] = factory_compatibility_skip_count
            params["factory_cooldown_skip_count"] = factory_cooldown_skip_count
            params["factory_selected_count"] = factory_selected_count
            ai_candidate["params"] = params

    @staticmethod
    def _synthetic_local_spawn_targets(candidate: dict[str, Any]) -> list[str]:
        research_task = dict(candidate.get("research_task") or {})
        if not bool(research_task.get("synthetic_local_spawn")):
            return []
        target_symbols = research_task.get("target_symbols")
        if not target_symbols:
            target_symbols = candidate.get("target_symbols")
        return [
            str(code).strip()
            for code in list(target_symbols or [])
            if str(code).strip()
        ]

    @staticmethod
    def _candidate_target_symbols(candidate: dict[str, Any]) -> list[str]:
        """返回 candidate 所有声明的目标代码，覆盖 research_task / params / 顶层三处。"""
        seen: list[str] = []
        for bucket in (
            (candidate.get("research_task") or {}).get("target_symbols"),
            candidate.get("target_symbols"),
            (candidate.get("params") or {}).get("target_symbols"),
        ):
            for code in list(bucket or []):
                token = str(code or "").strip()
                if token and token not in seen:
                    seen.append(token)
        return seen

    @classmethod
    async def _sanitize_local_spawn_targets(
        cls,
        candidates: list[dict[str, Any]],
        db: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        get_klines = getattr(db, "get_klines", None)
        if not candidates or not inspect.iscoroutinefunction(get_klines):
            return list(candidates or []), {
                "enabled": False,
                "checked_candidate_count": 0,
                "pruned_candidate_count": 0,
                "pruned_symbol_count": 0,
                "insufficient_kline_codes": [],
            }

        # PR-U1+: 扫描所有 local 候选（不仅限 synthetic_local_spawn），把声明目标代码都纳入 K 线清洗。
        unique_codes: list[str] = []
        for candidate in list(candidates or []):
            for code in cls._candidate_target_symbols(candidate):
                if code not in unique_codes:
                    unique_codes.append(code)

        if not unique_codes:
            return list(candidates or []), {
                "enabled": True,
                "checked_candidate_count": 0,
                "pruned_candidate_count": 0,
                "pruned_symbol_count": 0,
                "insufficient_kline_codes": [],
            }

        async def _fetch_history(code: str) -> tuple[str, int, bool]:
            """返回 (code, k线数量, 是否最近停牌)。"""
            try:
                klines = await get_klines(code, limit=_GATE_1_MIN_KLINES + 10)
            except Exception:
                return code, 0, False
            klist = list(klines or [])
            # PR-S8: 最近 5 个交易日 volume 全 0 → 视为停牌 / 长期停牌
            recent = klist[-5:] if len(klist) >= 5 else klist
            recent_volume_sum = 0.0
            for k in recent:
                try:
                    recent_volume_sum += float((k or {}).get("volume") or 0.0)
                except (TypeError, ValueError):
                    continue
            suspended = bool(recent) and recent_volume_sum <= 0.0
            return code, len(klist), suspended

        history_results = await asyncio.gather(*[_fetch_history(code) for code in unique_codes])
        history_counts = {code: count for code, count, _ in history_results}
        suspended_codes = sorted(code for code, _, suspended in history_results if suspended)
        insufficient_codes = sorted(
            code for code, count in history_counts.items()
            if int(count or 0) < _GATE_1_MIN_KLINES
        )
        # 停牌或样本不足都视为不可交易
        invalid_codes = set(insufficient_codes) | set(suspended_codes)
        if not invalid_codes:
            return list(candidates or []), {
                "enabled": True,
                "checked_candidate_count": len(unique_codes),
                "pruned_candidate_count": 0,
                "pruned_symbol_count": 0,
                "insufficient_kline_codes": [],
                "suspended_codes": [],
            }

        sanitized_candidates: list[dict[str, Any]] = []
        pruned_candidate_count = 0
        pruned_symbol_count = 0
        for candidate in list(candidates or []):
            target_symbols = cls._candidate_target_symbols(candidate)
            if not target_symbols:
                sanitized_candidates.append(candidate)
                continue
            kept_symbols = [
                code for code in target_symbols
                if int(history_counts.get(code) or 0) >= _GATE_1_MIN_KLINES
                and code not in suspended_codes
            ]
            if not kept_symbols or kept_symbols == target_symbols:
                sanitized_candidates.append(candidate)
                continue

            pruned_candidate_count += 1
            pruned_symbol_count += len(target_symbols) - len(kept_symbols)
            item = dict(candidate or {})
            params = dict(item.get("params") or {})
            research_task = dict(item.get("research_task") or {})
            explicit_pool = {"selection_mode": "explicit", "symbols": list(kept_symbols)}

            research_task["target_symbols"] = list(kept_symbols)
            research_task["stock_pool"] = explicit_pool
            research_task["gate_1_representative_count"] = min(3, len(kept_symbols))
            if research_task.get("target_symbols_signature") is not None:
                research_task["target_symbols_signature"] = ",".join(kept_symbols)

            params["target_symbols"] = list(kept_symbols)
            params["requested_target_symbols"] = list(kept_symbols)
            params["stock_pool"] = explicit_pool

            item["research_task"] = research_task
            item["requested_target_symbols"] = list(kept_symbols)
            item["target_symbols"] = list(kept_symbols)
            item["stock_pool"] = explicit_pool
            item["params"] = params
            sanitized_candidates.append(item)

        return sanitized_candidates, {
            "enabled": True,
            "checked_candidate_count": len(unique_codes),
            "pruned_candidate_count": pruned_candidate_count,
            "pruned_symbol_count": pruned_symbol_count,
            "insufficient_kline_codes": insufficient_codes,
            "suspended_codes": suspended_codes,
        }

    # 优化 12-2：股票白名单 TTL 缓存（避免每轮全表扫描）
    _whitelist_cache: tuple[float, set[str]] | None = None
    _WHITELIST_CACHE_TTL_SEC: float = 3600.0  # 1 小时
    # PR-S6: 进程级 lock，防止并发 _filter_invalid_symbols 重复加载 whitelist
    _whitelist_cache_lock: asyncio.Lock | None = None

    @staticmethod
    async def _filter_invalid_symbols(
        candidates: list[dict[str, Any]],
        db: Any,
    ) -> list[dict[str, Any]]:
        """PR-AI1: 过滤 LLM 幻觉出的无效股票代码。

        从 stocks 表加载白名单（带 TTL 缓存），剔除不存在/已退市的代码。
        如果候选的所有 target_symbols 都无效，则丢弃整个候选。
        """
        import time as _time

        # 检查缓存
        whitelist: set[str] = set()
        cache = ResearchPlaneRunner._whitelist_cache
        if cache is not None:
            expire, cached_whitelist = cache
            if _time.time() < expire:
                whitelist = cached_whitelist

        if not whitelist:
            fetch = getattr(db, "fetch", None) or getattr(db, "fetchall", None)
            if not callable(fetch):
                return list(candidates or [])
            # PR-S6: 加 lock 防止并发场景重复全表扫描
            if ResearchPlaneRunner._whitelist_cache_lock is None:
                ResearchPlaneRunner._whitelist_cache_lock = asyncio.Lock()
            async with ResearchPlaneRunner._whitelist_cache_lock:
                # double-check：可能另一个协程在等锁期间已填充缓存
                cache = ResearchPlaneRunner._whitelist_cache
                if cache is not None:
                    expire, cached_whitelist = cache
                    if _time.time() < expire:
                        whitelist = cached_whitelist
                if not whitelist:
                    try:
                        rows = await fetch(
                            "SELECT code FROM stocks WHERE list_status = 'L'"
                        )
                        whitelist = {str(r["code"]).strip() for r in (rows or []) if r.get("code")}
                        ResearchPlaneRunner._whitelist_cache = (
                            _time.time() + ResearchPlaneRunner._WHITELIST_CACHE_TTL_SEC,
                            whitelist,
                        )
                    except Exception as exc:
                        logger.debug("_filter_invalid_symbols: failed to load whitelist: %s", exc)
                        return list(candidates or [])

        if not whitelist:
            return list(candidates or [])

        filtered: list[dict[str, Any]] = []
        dropped_symbols: list[str] = []
        for candidate in list(candidates or []):
            syms = [
                str(s).strip()
                for s in list(candidate.get("target_symbols") or [])
                if str(s).strip()
            ]
            if not syms:
                filtered.append(candidate)
                continue
            valid = [s for s in syms if s in whitelist]
            invalid = [s for s in syms if s not in whitelist]
            if invalid:
                dropped_symbols.extend(invalid)
                logger.debug(
                    "_filter_invalid_symbols: dropped invalid codes %s from candidate '%s'",
                    invalid, candidate.get("name") or candidate.get("strategy_type"),
                )
            if valid:
                candidate["target_symbols"] = valid
                params = dict(candidate.get("params") or {})
                params["target_symbols"] = valid
                if params.get("requested_target_symbols"):
                    params["requested_target_symbols"] = valid
                candidate["params"] = params
                filtered.append(candidate)
            # else: 全部无效，丢弃整个候选
        if dropped_symbols:
            logger.info(
                "_filter_invalid_symbols: removed %d invalid symbol(s): %s",
                len(dropped_symbols), dropped_symbols[:10],
            )
        return filtered

    @staticmethod
    def _annotate_local_spawn_report(
        report: dict[str, Any],
        *,
        target_sanitization: dict[str, Any],
    ) -> dict[str, Any]:
        annotated = dict(report or {})
        summary = dict(annotated.get("summary") or {})
        summary["target_symbol_sanitization_enabled"] = bool(target_sanitization.get("enabled"))
        summary["target_symbol_sanitization_checked_candidate_count"] = int(
            target_sanitization.get("checked_candidate_count") or 0
        )
        summary["target_symbol_sanitization_pruned_candidate_count"] = int(
            target_sanitization.get("pruned_candidate_count") or 0
        )
        summary["target_symbol_sanitization_pruned_symbol_count"] = int(
            target_sanitization.get("pruned_symbol_count") or 0
        )
        summary["target_symbol_sanitization_insufficient_kline_codes"] = list(
            target_sanitization.get("insufficient_kline_codes") or []
        )
        annotated["summary"] = summary
        return annotated


__all__ = [
    "ResearchGenerationResult",
    "ResearchPlaneRunner",
]
