"""Shared helpers for market opportunity scanning."""

from __future__ import annotations

from typing import Any, Dict, List

from ..domain.constants import (
    AUTONOMY_CANDIDATES_PER_TASK,
    AUTONOMY_MAX_RESEARCH_TASKS,
    EVENT_SNAPSHOT_MIX_MAX,
    EVENT_TASK_GENERATION_LIMIT_MAX,
)
from ..domain.targets import _normalize_research_task_contract


class _MarketOpportunityScannerUtilityMixin:
    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _clip_score(value: Any, default: float = 0.0) -> float:
        try:
            score = float(value)
        except Exception:
            score = float(default)
        return max(0.0, min(score, 1.0))

    @staticmethod
    def _normalize_codes(values: Any, limit: int = 5) -> List[str]:
        from ..domain.targets import _normalize_target_codes

        return _normalize_target_codes(values, limit=limit)

    @classmethod
    def _summarize_symbol(cls, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "code": row.get("code"),
            "name": row.get("name"),
            "industry": row.get("industry"),
            "sector": row.get("sector") or row.get("industry"),
            "market": row.get("market"),
            "market_cap": cls._safe_float(row.get("market_cap")),
            "pe_ratio": row.get("pe_ratio"),
            "pb_ratio": row.get("pb_ratio"),
        }

    @staticmethod
    def _deduplicate_tasks(tasks: List[dict]) -> List[dict]:
        unique: List[dict] = []
        seen: set[str] = set()
        for item in tasks:
            key = str(item.get("task_key") or item.get("task_id") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    @staticmethod
    def _build_task_source_counts(tasks: List[dict]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in list(tasks or []):
            source = str(item.get("task_source") or "unknown").strip() or "unknown"
            counts[source] = counts.get(source, 0) + 1
        return counts

    @classmethod
    def _task_target_overlap(cls, left: dict, right: dict) -> float:
        left_codes = set(cls._normalize_codes(left.get("target_symbols"), limit=8))
        right_codes = set(cls._normalize_codes(right.get("target_symbols"), limit=8))
        if not left_codes or not right_codes:
            return 0.0
        base = min(len(left_codes), len(right_codes))
        if base <= 0:
            return 0.0
        return round(len(left_codes & right_codes) / base, 4)

    @staticmethod
    def _task_industries(task: dict) -> set[str]:
        return {
            str(item or "").strip()
            for item in list(task.get("focus_industries") or [])
            if str(item or "").strip()
        }

    @classmethod
    def _tasks_are_redundant_for_mix(cls, left: dict, right: dict) -> bool:
        if str(left.get("opportunity_type") or "").strip() != str(right.get("opportunity_type") or "").strip():
            return False
        if cls._task_target_overlap(left, right) >= 0.6:
            return True
        return bool(cls._task_industries(left) & cls._task_industries(right))

    @staticmethod
    def _snapshot_generation_limit(base_limit: Any, *, priority: int = 0) -> int:
        resolved = max(2, int(base_limit or AUTONOMY_CANDIDATES_PER_TASK))
        upper_bound = max(resolved, min(EVENT_TASK_GENERATION_LIMIT_MAX, AUTONOMY_CANDIDATES_PER_TASK + 2))
        bonus = 0
        if priority >= 85:
            bonus += 1
        if priority >= 100:
            bonus += 1
        return min(upper_bound, resolved + bonus)

    @staticmethod
    def _task_sort_key(item: dict) -> tuple[int, int, int]:
        source = str(item.get("task_source") or "").strip()
        return (
            1 if source == "event_driven" else 0,
            int(item.get("priority") or 0),
            int(item.get("generation_limit") or 0),
        )

    @staticmethod
    def _finalize_task(task: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_research_task_contract(task)
        if normalized.get("target_symbols") and not normalized.get("stock_pool"):
            normalized["stock_pool"] = {
                "selection_mode": "explicit",
                "symbols": list(normalized.get("target_symbols") or []),
            }
        return normalized

    @classmethod
    def _select_snapshot_tasks_for_event_mix(
        cls,
        event_tasks: List[dict],
        snapshot_tasks: List[dict],
    ) -> List[dict]:
        remaining = max(0, AUTONOMY_MAX_RESEARCH_TASKS - len(event_tasks))
        if remaining <= 0 or not snapshot_tasks:
            return []

        snapshot_limit = min(EVENT_SNAPSHOT_MIX_MAX, remaining)
        selected: List[dict] = []
        seen_themes = {
            str(item.get("theme") or "").strip()
            for item in list(event_tasks or [])
            if str(item.get("theme") or "").strip()
        }
        reference_tasks = list(event_tasks or [])

        for task in sorted(cls._deduplicate_tasks(snapshot_tasks), key=cls._task_sort_key, reverse=True):
            theme = str(task.get("theme") or "").strip()
            if theme and theme in seen_themes:
                continue
            if any(cls._tasks_are_redundant_for_mix(task, existing) for existing in reference_tasks):
                continue
            selected.append(task)
            if theme:
                seen_themes.add(theme)
            reference_tasks.append(task)
            if len(selected) >= snapshot_limit:
                break
        return selected

    @staticmethod
    def _match_rows(rows: List[dict], keywords: List[str]) -> List[dict]:
        normalized = [str(item or "").strip() for item in keywords if str(item or "").strip()]
        if not normalized:
            return []
        matched: List[dict] = []
        for row in rows:
            haystack = " ".join(
                [
                    str((row or {}).get("industry") or ""),
                    str((row or {}).get("sector") or ""),
                    str((row or {}).get("name") or ""),
                    str((row or {}).get("code") or ""),
                ]
            )
            if any(token in haystack for token in normalized):
                matched.append(row)
        return matched

    @staticmethod
    def _top_codes(rows: List[dict], limit: int = 5) -> List[str]:
        ranked = sorted(
            [dict(item or {}) for item in rows],
            key=lambda item: (float(item.get("market_cap") or 0.0), str(item.get("code") or "")),
            reverse=True,
        )
        codes: List[str] = []
        for row in ranked:
            code = str((row or {}).get("code") or "").strip()
            if code and code not in codes:
                codes.append(code)
            if len(codes) >= limit:
                break
        return codes

    @staticmethod
    def _rows_by_code(rows: List[dict]) -> Dict[str, dict]:
        return {
            str((row or {}).get("code") or "").strip(): dict(row or {})
            for row in rows
            if str((row or {}).get("code") or "").strip()
        }

    @staticmethod
    def _compact_text(value: Any, limit: int = 120) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)] + "..."

    @classmethod
    def _focus_rows_for_family(
        cls,
        rows: List[dict],
        *,
        family_name: str,
        hot_sectors: List[str],
        cold_sectors: List[str],
    ) -> List[dict]:
        lowered = str(family_name or "").strip().lower()
        keywords: List[str] = []
        if any(
            token in lowered
            for token in ["momentum", "growth", "sentiment", "capital_flow", "event", "liquidity"]
        ):
            keywords = list(hot_sectors[:2])
        elif any(token in lowered for token in ["value", "quality", "reversal", "volatility"]):
            keywords = list(cold_sectors[:2] or hot_sectors[:1])
        elif hot_sectors:
            keywords = list(hot_sectors[:1])
        matched = cls._match_rows(rows, keywords)
        return matched or list(rows or [])

    @classmethod
    def _focus_industries_from_rows(cls, rows: List[dict], limit: int = 3) -> List[str]:
        items: List[str] = []
        for row in list(rows or []):
            industry = str((row or {}).get("industry") or (row or {}).get("sector") or "").strip()
            if industry and industry not in items:
                items.append(industry)
            if len(items) >= limit:
                break
        return items
