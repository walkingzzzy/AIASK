"""策略工厂去重分析。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from .legacy_bridge import get_compat_symbol, get_compat_value
from .runtime import get_strategy_factory_package as _runtime_get_strategy_factory_package
from .utils import _extract_event_context as _local_extract_event_context
from akshare_mcp.services.vector_search import VectorSearchEngine

from ..domain.constants import DEDUP_CONCURRENCY
from ..domain.targets import _extract_target_codes_from_payload


_LEGACY_DEDUPLICATOR_MODULE = "akshare_mcp.services.strategy_factory.deduplicator"
_LEGACY_RUNTIME_MODULE = "akshare_mcp.services.strategy_factory.runtime"
_LEGACY_UTILS_MODULE = "akshare_mcp.services.strategy_factory.utils"

def _compat_setting(name: str, default):
    return get_compat_value(_LEGACY_DEDUPLICATOR_MODULE, name, default)


def _extract_event_context(*args, **kwargs):
    return get_compat_symbol(
        _LEGACY_UTILS_MODULE,
        "_extract_event_context",
        _local_extract_event_context,
    )(*args, **kwargs)


def _get_strategy_factory_package():
    target = get_compat_symbol(
        _LEGACY_RUNTIME_MODULE,
        "get_strategy_factory_package",
        _runtime_get_strategy_factory_package,
    )
    return target()

logger = logging.getLogger(__name__)


class Deduplicator:
    """去除与已有策略参数过于相似的候选。"""

    THRESHOLD = 0.85
    VECTOR_TRIGGER_THRESHOLD = 0.65
    VECTOR_THRESHOLD = 0.93
    MAX_VECTOR_CANDIDATES = 8

    def __init__(self):
        self.last_report: dict = {
            "summary": {
                "input_count": 0,
                "kept_count": 0,
                "dropped_count": 0,
                "vector_checks": 0,
                "existing_scan_count": 0,
                "coarse_candidate_count": 0,
                "coarse_filtered_count": 0,
                "coarse_hit_ratio": 0.0,
                "coarse_tag_hit_count": 0,
                "coarse_target_hit_count": 0,
                "vector_candidate_count": 0,
                "vector_candidate_trimmed_count": 0,
            },
            "kept": [],
            "dropped": [],
        }
        self._behavior_cache: Dict[str, Optional[List[dict]]] = {}
        self._vector_engine = VectorSearchEngine(backend="index", allow_fallback=True)

    @staticmethod
    def _normalize_strategy_type(value: object) -> str:
        return str(value or "").strip().lower()

    @classmethod
    def _bucket_existing_by_type(cls, rows: List[dict]) -> Dict[str, List[dict]]:
        buckets: Dict[str, List[dict]] = {}
        for item in list(rows or []):
            strategy_type = cls._normalize_strategy_type((item or {}).get("strategy_type"))
            if not strategy_type:
                continue
            buckets.setdefault(strategy_type, []).append(item)
        return buckets

    @staticmethod
    def _tag_overlap(left_payload: Optional[dict], right_payload: Optional[dict]) -> float:
        left = {
            str(item).strip().lower()
            for item in list((left_payload or {}).get("tags") or [])
            if str(item).strip()
        }
        right = {
            str(item).strip().lower()
            for item in list((right_payload or {}).get("tags") or [])
            if str(item).strip()
        }
        if not left or not right:
            return 0.0
        union = left | right
        if not union:
            return 0.0
        return round(len(left & right) / len(union), 4)

    def _select_vector_candidates(self, suspicious: List[dict]) -> List[Tuple[dict, float]]:
        ranked = sorted(
            list(suspicious or []),
            key=lambda item: (
                float(item.get("effective_similarity") or 0.0),
                float(item.get("target_overlap") or 0.0) if item.get("target_overlap") is not None else -1.0,
                float(item.get("tag_overlap") or 0.0),
            ),
            reverse=True,
        )
        selected: List[Tuple[dict, float]] = []
        for item in ranked[: self.MAX_VECTOR_CANDIDATES]:
            existing_item = dict(item.get("existing_item") or {})
            if not existing_item:
                continue
            selected.append((existing_item, float(item.get("effective_similarity") or 0.0)))
        return selected

    @staticmethod
    def _candidate_refresh_rank(candidate: Optional[dict]) -> tuple[float, float, float]:
        item = dict(candidate or {})
        metrics = dict(item.get('backtest_metrics') or (item.get('backtest_result') or {}).get('metrics') or {})
        sharpe = float(metrics.get('sharpe_ratio') or 0.0)
        total_return = float(metrics.get('total_return') or 0.0)
        max_drawdown = float(metrics.get('max_drawdown') or 1.0)
        return (round(sharpe, 6), round(total_return, 6), round(-max_drawdown, 6))

    @classmethod
    def _collapse_refresh_existing_candidates(cls, unique: List[dict]) -> tuple[List[dict], List[dict]]:
        collapsed: List[dict] = []
        dropped: List[dict] = []
        kept_by_strategy: dict[str, int] = {}

        for candidate in unique:
            detail = dict(candidate.get('dedup_result') or {})
            if not detail.get('refresh_existing'):
                collapsed.append(candidate)
                continue
            matched_strategy_id = str(detail.get('matched_strategy_id') or '').strip()
            if not matched_strategy_id:
                collapsed.append(candidate)
                continue
            current_rank = cls._candidate_refresh_rank(candidate)
            if matched_strategy_id not in kept_by_strategy:
                kept_by_strategy[matched_strategy_id] = len(collapsed)
                collapsed.append(candidate)
                continue

            kept_index = kept_by_strategy[matched_strategy_id]
            kept_candidate = collapsed[kept_index]
            kept_rank = cls._candidate_refresh_rank(kept_candidate)
            if current_rank > kept_rank:
                previous = dict(kept_candidate)
                previous_detail = dict(previous.get('dedup_result') or {})
                previous_detail.update({
                    'duplicate': True,
                    'duplicate_level': 'refresh_existing_conflict',
                    'match_type': 'refresh_existing',
                    'reason': f"同一目标策略 {matched_strategy_id} 已有更优刷新候选，按回测表现折叠当前候选",
                })
                previous['dedup_result'] = previous_detail
                dropped.append(previous)
                collapsed[kept_index] = candidate
            else:
                current = dict(candidate)
                current_detail = dict(current.get('dedup_result') or {})
                current_detail.update({
                    'duplicate': True,
                    'duplicate_level': 'refresh_existing_conflict',
                    'match_type': 'refresh_existing',
                    'reason': f"同一目标策略 {matched_strategy_id} 已有更优刷新候选，按回测表现折叠当前候选",
                })
                current['dedup_result'] = current_detail
                dropped.append(current)

        return collapsed, dropped

    @staticmethod
    def _merge_metrics(left: Optional[dict], right: Optional[dict]) -> dict:
        merged: dict[str, int] = {}
        for key in {
            "scanned_count",
            "coarse_candidate_count",
            "coarse_tag_hit_count",
            "coarse_target_hit_count",
            "vector_candidate_count",
            "vector_candidate_trimmed_count",
        }:
            merged[key] = int((left or {}).get(key) or 0) + int((right or {}).get(key) or 0)
        return merged

    @staticmethod
    def _select_detail(base_detail: Optional[dict], intra_detail: Optional[dict]) -> dict:
        left = dict(base_detail or {})
        right = dict(intra_detail or {})
        if (
            left.get("refresh_existing")
            and right.get("duplicate")
            and not str(right.get("matched_strategy_id") or "").strip()
        ):
            return left
        if right.get("duplicate"):
            return right
        if left.get("duplicate"):
            return left
        if left.get("refresh_existing"):
            return left
        if right.get("refresh_existing"):
            return right
        left_similarity = float(left.get("effective_similarity") or 0.0)
        right_similarity = float(right.get("effective_similarity") or 0.0)
        return right if right_similarity > left_similarity else left

    async def _analyze_against_existing(
        self,
        candidates: List[dict],
        existing_by_type: Dict[str, List[dict]],
        db,
    ) -> List[tuple[dict, dict, dict]]:
        concurrency = max(1, int(_compat_setting("DEDUP_CONCURRENCY", DEDUP_CONCURRENCY) or 1))
        sem = asyncio.Semaphore(concurrency)

        async def _run(candidate: dict) -> tuple[dict, dict, dict]:
            strategy_type = self._normalize_strategy_type(candidate.get("strategy_type"))
            persisted_bucket = list(existing_by_type.get(strategy_type, []))
            async with sem:
                detail, metrics = await self._find_duplicate(candidate, persisted_bucket, db)
            return candidate, detail, metrics

        return await asyncio.gather(*[_run(candidate) for candidate in list(candidates or [])])

    async def deduplicate(self, candidates: List[dict], db) -> List[dict]:
        existing: List[dict] = []
        for status in ("listed", "incubating"):
            try:
                rows = await db.list_strategies(status, limit=500)
                existing.extend(rows)
            except Exception as exc:
                logger.warning("deduplicator: failed to load %s strategies: %s", status, exc)

        existing_by_type = self._bucket_existing_by_type(existing)
        await self._prewarm_candidate_behaviors(candidates, db)
        analyzed_candidates = await self._analyze_against_existing(candidates, existing_by_type, db)

        unique: List[dict] = []
        dropped: List[dict] = []
        vector_checks = 0
        refreshed_existing = 0
        existing_scan_count = 0
        coarse_candidate_count = 0
        coarse_tag_hit_count = 0
        coarse_target_hit_count = 0
        vector_candidate_count = 0
        vector_candidate_trimmed_count = 0
        intra_batch_checks = 0

        for candidate, persisted_detail, persisted_metrics in analyzed_candidates:
            strategy_type = self._normalize_strategy_type(candidate.get("strategy_type"))
            metrics = dict(persisted_metrics or {})
            detail = dict(persisted_detail or {})
            intra_bucket = [item for item in unique if self._normalize_strategy_type(item.get("strategy_type")) == strategy_type]
            if intra_bucket and not detail.get("duplicate"):
                intra_batch_checks += 1
                intra_detail, intra_metrics = await self._find_duplicate(candidate, intra_bucket, db)
                metrics = self._merge_metrics(metrics, intra_metrics)
                detail = self._select_detail(detail, intra_detail)
            candidate["dedup_result"] = detail
            existing_scan_count += int(metrics.get("scanned_count") or 0)
            coarse_candidate_count += int(metrics.get("coarse_candidate_count") or 0)
            coarse_tag_hit_count += int(metrics.get("coarse_tag_hit_count") or 0)
            coarse_target_hit_count += int(metrics.get("coarse_target_hit_count") or 0)
            vector_candidate_count += int(metrics.get("vector_candidate_count") or 0)
            vector_candidate_trimmed_count += int(metrics.get("vector_candidate_trimmed_count") or 0)
            if detail.get("vector_checked"):
                vector_checks += 1
            if detail.get("duplicate"):
                dropped.append({**candidate})
                continue
            if detail.get("refresh_existing"):
                refreshed_existing += 1
            unique.append(candidate)

        collapsed_unique, collapsed_dropped = self._collapse_refresh_existing_candidates(unique)
        dropped.extend(collapsed_dropped)
        unique = collapsed_unique
        refreshed_existing = len([item for item in unique if dict(item.get("dedup_result") or {}).get("refresh_existing")])
        coarse_filtered_count = max(existing_scan_count - coarse_candidate_count, 0)
        coarse_hit_ratio = round(coarse_candidate_count / existing_scan_count, 4) if existing_scan_count else 0.0
        self.last_report = {
            "summary": {
                "input_count": len(candidates),
                "existing_count": len(existing),
                "existing_scan_count": existing_scan_count,
                "coarse_candidate_count": coarse_candidate_count,
                "coarse_filtered_count": coarse_filtered_count,
                "coarse_hit_ratio": coarse_hit_ratio,
                "coarse_tag_hit_count": coarse_tag_hit_count,
                "coarse_target_hit_count": coarse_target_hit_count,
                "kept_count": len(unique),
                "dropped_count": len(dropped),
                "refreshed_existing_count": refreshed_existing,
                "vector_checks": vector_checks,
                "vector_candidate_count": vector_candidate_count,
                "vector_candidate_trimmed_count": vector_candidate_trimmed_count,
                "candidate_analysis_concurrency": max(1, int(_compat_setting("DEDUP_CONCURRENCY", DEDUP_CONCURRENCY) or 1)),
                "persisted_existing_phase_count": len(analyzed_candidates),
                "intra_batch_check_count": intra_batch_checks,
                "param_threshold": self.THRESHOLD,
                "vector_threshold": self.VECTOR_THRESHOLD,
            },
            "kept": [{
                "strategy_type": item.get("strategy_type"),
                "generator_type": item.get("generator_type"),
                "params": item.get("params"),
                "target_symbols": item.get("target_symbols") or [],
                "stock_pool": item.get("stock_pool") or {},
                "tags": item.get("tags") or [],
                "spawn_reason": item.get("spawn_reason"),
                "dedup_result": item.get("dedup_result"),
            } for item in unique],
            "dropped": [{
                "strategy_type": item.get("strategy_type"),
                "generator_type": item.get("generator_type"),
                "params": item.get("params"),
                "target_symbols": item.get("target_symbols") or [],
                "stock_pool": item.get("stock_pool") or {},
                "tags": item.get("tags") or [],
                "spawn_reason": item.get("spawn_reason"),
                "dedup_result": item.get("dedup_result"),
            } for item in dropped],
        }
        return unique

    @staticmethod
    def _should_refresh_existing(candidate: Optional[dict], match: Optional[dict]) -> bool:
        candidate = dict(candidate or {})
        match = dict(match or {})
        matched_status = str(match.get("matched_status") or "").strip().lower()
        if matched_status not in {"incubating", "listed", "published"}:
            return False
        if not str(match.get("matched_strategy_id") or "").strip():
            return False
        research_task = dict(candidate.get("research_task") or {})
        event_context = dict(candidate.get("event_context") or {}) or _extract_event_context(research_task)
        has_event_context = bool(
            event_context.get("event_id")
            or event_context.get("theme_code")
            or research_task.get("task_source") == "event_driven"
            or str(candidate.get("source") or "").startswith("strategy_factory:")
        )
        has_explicit_universe = bool(_extract_target_codes_from_payload(candidate, limit=20))
        return bool(has_event_context and has_explicit_universe)

    async def _find_duplicate(self, candidate: dict, existing: list, db) -> tuple[dict, dict]:
        best_match: Optional[dict] = None
        suspicious: List[dict] = []
        candidate_params = self._normalize_params(candidate.get("params"))
        metrics = {
            "scanned_count": 0,
            "coarse_candidate_count": 0,
            "coarse_tag_hit_count": 0,
            "coarse_target_hit_count": 0,
            "vector_candidate_count": 0,
            "vector_candidate_trimmed_count": 0,
        }
        for existing_item in existing:
            metrics["scanned_count"] += 1
            existing_params = self._normalize_params(existing_item.get("params"))
            param_similarity = self._param_sim(candidate_params, existing_params)
            target_overlap = self._target_overlap(candidate, existing_item)
            tag_overlap = self._tag_overlap(candidate, existing_item)
            if tag_overlap > 0:
                metrics["coarse_tag_hit_count"] += 1
            if target_overlap is not None and target_overlap > 0:
                metrics["coarse_target_hit_count"] += 1
            effective_similarity = self._effective_similarity(param_similarity, target_overlap)
            match = {
                "matched_strategy_id": existing_item.get("id"),
                "matched_name": existing_item.get("name") or existing_item.get("strategy_type"),
                "matched_status": existing_item.get("status"),
                "param_similarity": round(param_similarity, 4),
                "target_overlap": target_overlap,
                "effective_similarity": round(effective_similarity, 4),
            }
            if best_match is None or effective_similarity > best_match.get("effective_similarity", 0):
                best_match = match
            if effective_similarity >= self.THRESHOLD:
                overlap_text = f", 目标池重合度 {target_overlap:.4f}" if target_overlap is not None else ""
                if self._should_refresh_existing(candidate, match):
                    return {
                        "duplicate": False,
                        "refresh_existing": True,
                        "duplicate_level": "refresh_existing",
                        "match_type": "parameter",
                        "reason": f"综合相似度 {effective_similarity:.4f} ≥ 阈值 {self.THRESHOLD:.2f}（参数 {param_similarity:.4f}{overlap_text}），命中已有策略并转为刷新复用",
                        "threshold": self.THRESHOLD,
                        "vector_threshold": self.VECTOR_THRESHOLD,
                        "vector_checked": False,
                        **match,
                    }, metrics
                return {
                    "duplicate": True,
                    "duplicate_level": "parameter",
                    "match_type": "parameter",
                    "reason": f"综合相似度 {effective_similarity:.4f} ≥ 阈值 {self.THRESHOLD:.2f}（参数 {param_similarity:.4f}{overlap_text}）",
                    "threshold": self.THRESHOLD,
                    "vector_threshold": self.VECTOR_THRESHOLD,
                    "vector_checked": False,
                    **match,
                }, metrics
            if effective_similarity >= self.VECTOR_TRIGGER_THRESHOLD:
                suspicious.append({
                    "existing_item": existing_item,
                    "param_similarity": round(param_similarity, 4),
                    "target_overlap": target_overlap,
                    "tag_overlap": round(tag_overlap, 4),
                    "effective_similarity": round(effective_similarity, 4),
                })

        metrics["coarse_candidate_count"] = len(suspicious)
        vector_candidates = self._select_vector_candidates(suspicious)
        metrics["vector_candidate_count"] = len(vector_candidates)
        metrics["vector_candidate_trimmed_count"] = max(0, len(suspicious) - len(vector_candidates))
        vector_detail = await self._vector_check(candidate, vector_candidates, db) if vector_candidates else None
        resolved_vector_threshold = self.VECTOR_THRESHOLD
        vector_keep_reason: Optional[str] = None
        if vector_detail:
            vector_similarity = float(vector_detail.get("similarity") or 0.0)
            param_similarity = float(vector_detail.get("param_similarity") or 0.0)
            target_overlap = vector_detail.get("target_overlap")
            has_candidate_universe = bool(_extract_target_codes_from_payload(candidate, limit=20))
            require_param_confirmation = False
            if has_candidate_universe and target_overlap is None:
                resolved_vector_threshold = max(self.VECTOR_THRESHOLD, 0.98)
                require_param_confirmation = True
            vector_confirmed = vector_similarity >= resolved_vector_threshold
            if require_param_confirmation:
                vector_confirmed = vector_confirmed and param_similarity >= self.THRESHOLD
            if vector_confirmed:
                if require_param_confirmation:
                    reason = (
                        f"行为向量相似度 {vector_similarity:.4f} ≥ 阈值 {resolved_vector_threshold:.2f}，"
                        f"且目标池缺失场景下参数相似度 {param_similarity:.4f} ≥ {self.THRESHOLD:.2f}"
                    )
                else:
                    reason = f"行为向量相似度 {vector_similarity:.4f} ≥ 阈值 {resolved_vector_threshold:.2f}"
                return {
                    "duplicate": True,
                    "duplicate_level": "vector",
                    "match_type": "vector",
                    "reason": reason,
                    "threshold": self.THRESHOLD,
                    "vector_threshold": resolved_vector_threshold,
                    "vector_checked": True,
                    "param_similarity": round(param_similarity, 4),
                    "target_overlap": target_overlap,
                    "effective_similarity": round(vector_detail.get("effective_similarity", 0.0), 4),
                    "vector_similarity": round(vector_similarity, 4),
                    "vector_backend": vector_detail.get("backend"),
                    "matched_strategy_id": vector_detail.get("matched_strategy_id"),
                    "matched_name": vector_detail.get("matched_name"),
                    "matched_status": vector_detail.get("matched_status"),
                }, metrics
            if require_param_confirmation and vector_similarity >= self.VECTOR_THRESHOLD:
                vector_keep_reason = (
                    f"行为向量相似但命中策略缺少目标池信息，参数相似度 {param_similarity:.4f} < {self.THRESHOLD:.2f}，暂不判重"
                )

        return {
            "duplicate": False,
            "refresh_existing": False,
            "duplicate_level": "unique",
            "match_type": None,
            "reason": vector_keep_reason or "未命中重复策略",
            "threshold": self.THRESHOLD,
            "vector_threshold": resolved_vector_threshold,
            "vector_checked": vector_detail is not None,
            "param_similarity": round((vector_detail or best_match or {}).get("param_similarity", 0.0), 4),
            "target_overlap": (vector_detail or best_match or {}).get("target_overlap"),
            "effective_similarity": round((vector_detail or best_match or {}).get("effective_similarity", 0.0), 4),
            "vector_similarity": round((vector_detail or {}).get("similarity", 0.0), 4),
            "vector_backend": (vector_detail or {}).get("backend"),
            "matched_strategy_id": (vector_detail or best_match or {}).get("matched_strategy_id"),
            "matched_name": (vector_detail or best_match or {}).get("matched_name"),
            "matched_status": (vector_detail or best_match or {}).get("matched_status"),
        }, metrics

    async def _prewarm_candidate_behaviors(self, candidates: List[dict], db) -> None:
        payloads = [
            (str(item.get("strategy_type") or "").strip(), self._normalize_params(item.get("params")))
            for item in list(candidates or [])
            if str(item.get("strategy_type") or "").strip()
        ]
        if payloads:
            await self._bounded_behavior_gather(payloads, db)

    @staticmethod
    def _normalize_params(value: object) -> dict:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except Exception:
                return {}
            return dict(parsed) if isinstance(parsed, dict) else {}
        return {}

    async def _bounded_behavior_gather(self, payloads: List[Tuple[str, dict]], db) -> List[Optional[List[dict]]]:
        concurrency = max(1, int(_compat_setting("DEDUP_CONCURRENCY", DEDUP_CONCURRENCY) or 1))
        sem = asyncio.Semaphore(concurrency)

        async def _run(strategy_type: str, params: dict) -> Optional[List[dict]]:
            async with sem:
                return await self._build_behavior_klines(strategy_type, params, db)

        return await asyncio.gather(*[
            _run(strategy_type, params)
            for strategy_type, params in payloads
        ])

    async def _vector_check(self, candidate: dict, suspicious: List[Tuple[dict, float]], db) -> Optional[dict]:
        query_strategy_type = str(candidate.get("strategy_type") or "").strip()
        query_params = self._normalize_params(candidate.get("params"))
        suspicious_payloads = [
            (str(existing_item.get("strategy_type") or "").strip(), self._normalize_params(existing_item.get("params")))
            for existing_item, _ in list(suspicious or [])
            if str(existing_item.get("strategy_type") or "").strip()
        ]
        gathered = await self._bounded_behavior_gather([(query_strategy_type, query_params), *suspicious_payloads], db)
        query_klines = gathered[0] if gathered else None
        if not query_klines:
            return None

        candidate_klines_dict: Dict[str, List[dict]] = {}
        match_meta: Dict[str, dict] = {}
        for idx, (existing_item, effective_similarity) in enumerate(suspicious):
            params = self._normalize_params(existing_item.get("params"))
            klines = gathered[idx + 1] if idx + 1 < len(gathered) else None
            if not klines:
                continue
            code = str(existing_item.get("id") or existing_item.get("name") or f"candidate_{idx}")
            candidate_klines_dict[code] = klines
            match_meta[code] = {
                "matched_strategy_id": existing_item.get("id"),
                "matched_name": existing_item.get("name") or existing_item.get("strategy_type"),
                "matched_status": existing_item.get("status"),
                "param_similarity": self._param_sim(candidate.get("params", {}), params),
                "target_overlap": self._target_overlap(candidate, existing_item),
                "effective_similarity": effective_similarity,
            }
        if not candidate_klines_dict:
            return None

        results = self._vector_engine.find_similar_patterns(
            query_klines=query_klines,
            candidate_klines_dict=candidate_klines_dict,
            top_k=1,
            method="returns",
            metric="cosine",
            backend="index",
            allow_fallback=True,
        )
        if not results:
            return None
        top = results[0]
        meta = match_meta.get(str(top.get("code")), {})
        return {
            "similarity": float(top.get("similarity") or 0.0),
            "backend": self._vector_engine.last_backend_used,
            **meta,
        }

    async def _build_behavior_klines(self, strategy_type: str, params: dict, db) -> Optional[List[dict]]:
        factory_pkg = _get_strategy_factory_package()
        cache_key = f"{strategy_type}:{json.dumps(params or {}, sort_keys=True, ensure_ascii=False, default=str)}"
        if cache_key in self._behavior_cache:
            return self._behavior_cache[cache_key]
        panels = await factory_pkg._build_strategy_panels(strategy_type, params, db, sample_size=4)
        series = panels.get("strategy_returns")
        if series is None or len(series) < 30:
            self._behavior_cache[cache_key] = None
            return None
        nonzero_ratio = float(np.count_nonzero(series)) / len(series)
        if nonzero_ratio < 0.1:
            self._behavior_cache[cache_key] = None
            return None
        price = 100.0
        pseudo_klines: List[dict] = []
        for ret in np.asarray(series[-60:], dtype=np.float64):
            open_price = price
            price = open_price * (1 + float(ret))
            pseudo_klines.append({
                "open": round(open_price, 6),
                "high": round(max(open_price, price), 6),
                "low": round(min(open_price, price), 6),
                "close": round(price, 6),
                "volume": 1.0,
            })
        self._behavior_cache[cache_key] = pseudo_klines
        return pseudo_klines

    def get_last_report(self) -> dict:
        return self.last_report

    @staticmethod
    def _target_overlap(left_payload: Optional[dict], right_payload: Optional[dict]) -> Optional[float]:
        left = set(_extract_target_codes_from_payload(left_payload or {}, limit=20))
        right = set(_extract_target_codes_from_payload(right_payload or {}, limit=20))
        if not left or not right:
            return None
        union = left | right
        if not union:
            return None
        return round(len(left & right) / len(union), 4)

    @classmethod
    def _effective_similarity(cls, param_similarity: float, target_overlap: Optional[float]) -> float:
        if target_overlap is None:
            return float(param_similarity)
        return round((float(param_similarity) + float(target_overlap)) / 2.0, 4)

    @staticmethod
    def _param_sim(left: dict, right: dict) -> float:
        keys = set(left.keys()) & set(right.keys())
        if not keys:
            return 0.0
        sims: List[float] = []
        for key in keys:
            left_value = left[key]
            right_value = right[key]
            if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
                denom = max(abs(left_value), abs(right_value), 1e-9)
                sims.append(1.0 - abs(left_value - right_value) / denom)
            elif left_value == right_value:
                sims.append(1.0)
        return float(np.mean(sims)) if sims else 0.0
