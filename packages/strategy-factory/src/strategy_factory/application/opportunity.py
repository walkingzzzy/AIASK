"""策略工厂机会扫描与研究任务生成。"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List

from ..domain.constants import (
    AUTONOMY_CANDIDATES_PER_TASK,
    AUTONOMY_MAX_RESEARCH_TASKS,
    EVENT_SNAPSHOT_MIX_MAX,
    EVENT_TASK_GENERATION_LIMIT_MAX,
    preferred_strategy_types_for_factor,
)
from ..domain.targets import _normalize_research_task_contract


class MarketOpportunityScanner:
    """根据市场快照与事件证据生成自治研究任务。"""

    def __init__(self):
        self.last_report: dict = {
            "summary": {"task_count": 0, "task_types": {}, "themes": [], "task_sources": {}},
            "tasks": [],
        }

    def get_last_report(self) -> dict:
        return dict(self.last_report)

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
            normalized["stock_pool"] = {"selection_mode": "explicit", "symbols": list(normalized.get("target_symbols") or [])}
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

    @classmethod
    def _governed_regime_preferences(cls, regime_name: str, *, fear_greed: float) -> List[str]:
        lowered = str(regime_name or "").strip().lower()
        if any(token in lowered for token in ["trend", "breakout", "momentum", "risk_on"]):
            return ["momentum", "ma_cross", "growth_factor"]
        if any(token in lowered for token in ["mean_reversion", "reversal", "oversold", "risk_off", "defensive"]):
            return ["rsi", "value_factor", "quality_factor"]
        if any(token in lowered for token in ["event", "news", "announcement"]):
            return ["macro_timing", "momentum", "multi_factor"]
        if any(token in lowered for token in ["volatility", "shock"]):
            return ["macro_timing", "rsi", "value_factor"]
        if any(token in lowered for token in ["rotation", "range", "sideways", "neutral"]):
            return ["ma_cross", "quality_factor", "multi_factor"]
        if fear_greed >= 60:
            return ["momentum", "ma_cross", "growth_factor"]
        if fear_greed <= 40:
            return ["rsi", "value_factor", "quality_factor"]
        return ["ma_cross", "quality_factor", "growth_factor"]

    @classmethod
    def _event_strategy_preferences(
        cls,
        *,
        direction: str,
        theme_name: str,
        opportunity_type: str,
    ) -> List[str]:
        lowered = str(theme_name or "").lower()
        direction = str(direction or "neutral").strip().lower() or "neutral"
        if direction in {"negative", "bearish", "cost_up"}:
            return ["quality_factor", "value_factor", "rsi"]
        if any(
            token in lowered
            for token in ["quality", "roe", "dividend", "cashflow", "防御", "高股息"]
        ):
            return ["quality_factor", "value_factor", "ma_cross"]
        if any(
            token in lowered
            for token in ["芯片", "半导体", "算力", "机器人", "ai", "军工", "油", "gas", "资源", "航运"]
        ):
            return ["momentum", "ma_cross", "growth_factor"]
        if opportunity_type == "factor_acceleration":
            return ["growth_factor", "momentum", "ma_cross"]
        if opportunity_type == "oversold_repair":
            return ["value_factor", "quality_factor", "rsi"]
        return ["ma_cross", "momentum", "quality_factor"]

    @classmethod
    def _event_opportunity_type(
        cls,
        *,
        direction: str,
        theme_name: str,
        horizon: str,
    ) -> str:
        lowered = str(theme_name or "").lower()
        direction = str(direction or "neutral").strip().lower() or "neutral"
        horizon = str(horizon or "").strip().lower()
        if direction in {"negative", "bearish", "cost_up"}:
            return "oversold_repair"
        if any(token in lowered for token in ["value", "quality", "roe", "dividend", "cashflow"]):
            return "factor_acceleration"
        if any(token in lowered for token in ["龙头", "leadership", "核心资产"]):
            return "industry_leadership"
        if any(token in horizon for token in ["1_5", "intraday", "swing_1", "5d"]):
            return "trend_expansion"
        return "sector_breakout"

    @classmethod
    def _event_generation_limit(
        cls,
        *,
        configured_limit: Any,
        avg_final_score: float,
        max_final_score: float,
        confidence: float,
        intensity: float,
        signal_count: int,
        priority: int,
    ) -> int:
        base_limit = max(1, int(configured_limit or AUTONOMY_CANDIDATES_PER_TASK))
        upper_bound = max(1, min(max(base_limit, EVENT_TASK_GENERATION_LIMIT_MAX), 10))
        evidence_strength = (
            avg_final_score * 0.35
            + max_final_score * 0.2
            + confidence * 0.15
            + intensity * 0.15
            + min(signal_count, 5) / 5.0 * 0.15
        )
        bonus = 0
        if evidence_strength >= 0.78:
            bonus += 1
        if evidence_strength >= 0.88:
            bonus += 1
        if evidence_strength >= 0.94:
            bonus += 1
        if signal_count >= 4:
            bonus += 1
        if priority >= 100:
            bonus += 1
        resolved = min(upper_bound, base_limit + bonus)
        if avg_final_score >= 0.8:
            resolved = max(resolved, min(upper_bound, max(base_limit, 2)))
        return max(1, resolved)

    @classmethod
    def _build_event_driven_tasks(cls, snapshot: dict[str, Any], rows: List[dict]) -> List[dict]:
        event_state = dict(snapshot.get("event_driven") or {})
        raw_events = list(event_state.get("events") or [])
        if not raw_events:
            return []

        row_map = cls._rows_by_code(rows)
        tasks: List[dict] = []

        for event_idx, event in enumerate(raw_events, 1):
            event_id = str(event.get("event_id") or f"event_{event_idx}").strip()
            event_name = str(event.get("event_name") or event.get("summary") or f"event_{event_idx}").strip()
            event_summary = cls._compact_text(event.get("summary") or event_name, limit=140)
            themes = list(event.get("themes") or [])
            if not themes:
                continue
            for theme_idx, theme in enumerate(themes, 1):
                theme_code = str(theme.get("theme_code") or theme.get("theme") or f"theme_{theme_idx}").strip()
                if not theme_code:
                    continue
                target_symbols = cls._normalize_codes(
                    [
                        theme.get("target_symbols"),
                        theme.get("top_symbols"),
                        (
                            (theme.get("score_summary") or {}).get("top_symbols")
                            if isinstance(theme.get("score_summary"), dict)
                            else None
                        ),
                    ],
                    limit=5,
                )
                if not target_symbols:
                    continue

                direction = str(theme.get("direction") or event.get("direction") or "neutral").strip().lower() or "neutral"
                horizon = str(theme.get("horizon") or event.get("horizon") or "swing_5_20d").strip() or "swing_5_20d"
                theme_name = str(theme.get("theme_name") or theme_code).strip() or theme_code
                opportunity_type = cls._event_opportunity_type(
                    direction=direction,
                    theme_name=theme_name,
                    horizon=horizon,
                )
                strategy_preferences = list(theme.get("strategy_preferences") or []) or cls._event_strategy_preferences(
                    direction=direction,
                    theme_name=theme_name,
                    opportunity_type=opportunity_type,
                )
                avg_final_score = cls._clip_score((theme.get("score_summary") or {}).get("avg_final_score"), default=0.0)
                max_final_score = cls._clip_score((theme.get("score_summary") or {}).get("max_final_score"), default=avg_final_score)
                confidence = cls._clip_score(event.get("confidence"), default=avg_final_score)
                intensity = cls._clip_score(event.get("intensity"), default=avg_final_score)
                signal_count = max(0, int(theme.get("signal_count") or 0))
                priority = int(
                    round(
                        55
                        + avg_final_score * 30
                        + max_final_score * 15
                        + confidence * 10
                        + intensity * 10
                        + min(signal_count, 4)
                    )
                )
                symbol_details = [cls._summarize_symbol(row_map[code]) for code in target_symbols if code in row_map]
                focus_industries = [
                    str(item.get("industry") or item.get("sector") or "").strip()
                    for item in symbol_details
                    if str(item.get("industry") or item.get("sector") or "").strip()
                ]
                focus_industries = list(dict.fromkeys(focus_industries))[:3]
                evidence_bundle = {
                    "event_id": event_id,
                    "event_name": event_name,
                    "event_type": event.get("event_type"),
                    "event_summary": event_summary,
                    "theme_code": theme_code,
                    "theme_name": theme_name,
                    "direction": direction,
                    "horizon": horizon,
                    "score_summary": dict(theme.get("score_summary") or {}),
                    "supporting_reasons": list(theme.get("supporting_reasons") or [])[:4],
                    "signal_count": signal_count,
                    "symbol_details": symbol_details,
                }
                title = f"事件主题任务·{event_name}·{theme_name}"
                rationale = (
                    f"事件 {event_name} 指向主题 {theme_name}，"
                    f"方向={direction}，候选池得分均值 {avg_final_score:.2f}，"
                    "围绕高暴露股票生成研究任务。"
                )
                generation_limit = cls._event_generation_limit(
                    configured_limit=theme.get("generation_limit"),
                    avg_final_score=avg_final_score,
                    max_final_score=max_final_score,
                    confidence=confidence,
                    intensity=intensity,
                    signal_count=signal_count,
                    priority=priority,
                )
                tasks.append(
                    cls._finalize_task(
                        {
                            "task_id": f"event_{event_id}_{theme_code}",
                            "task_key": f"event_theme:{snapshot.get('date')}:{event_id}:{theme_code}",
                            "task_source": "event_driven",
                            "event_id": event_id,
                            "event_type": event.get("event_type"),
                            "theme_code": theme_code,
                            "theme": f"event_theme_{theme_code}",
                            "title": title,
                            "opportunity_type": opportunity_type,
                            "direction": direction,
                            "horizon": horizon,
                            "rationale": rationale,
                            "event_summary": event_summary,
                            "preferred_strategy_types": strategy_preferences,
                            "strategy_preferences": strategy_preferences,
                            "allowed_strategy_types": [],
                            "target_symbol_policy": "strict_intersection",
                            "universe_expansion_policy": "allow_same_theme_only",
                            "preference_strength": "medium",
                            "preference_reason": f"event_evidence:{event_summary[:64]}",
                            "validation_focus": "event_target_only",
                            "target_symbols": target_symbols,
                            "stock_pool": {"selection_mode": "explicit", "symbols": target_symbols},
                            "focus_industries": focus_industries,
                            "focus_markets": [],
                            "priority": priority,
                            "generation_limit": generation_limit,
                            "evidence_bundle": evidence_bundle,
                            "selection_logic": list(theme.get("selection_logic") or [])[:3],
                        }
                    )
                )
        return tasks

    @classmethod
    def _build_snapshot_tasks(cls, snapshot: dict[str, Any], rows: List[dict]) -> List[dict]:
        tasks: List[dict] = []
        fg = float(snapshot.get("fear_greed_index") or 50.0)
        factor_research = dict(snapshot.get("factor_research") or {})
        active_candidate_pool = dict(factor_research.get("active_candidate_pool") or {})
        governed_family_summary = [
            dict(item or {})
            for item in list(
                factor_research.get("active_family_summary")
                or active_candidate_pool.get("family_summary")
                or []
            )
            if isinstance(item, dict)
        ]
        governed_regime_summary = [
            dict(item or {})
            for item in list(
                factor_research.get("active_regime_summary")
                or active_candidate_pool.get("regime_summary")
                or []
            )
            if isinstance(item, dict)
        ]
        governed_top_candidates = [
            dict(item or {})
            for item in list(
                factor_research.get("governed_candidates")
                or active_candidate_pool.get("top_candidates")
                or []
            )
            if isinstance(item, dict)
        ]
        hot_sectors = [str(item).strip() for item in list(snapshot.get("hot_sectors") or []) if str(item).strip()]
        cold_sectors = [str(item).strip() for item in list(snapshot.get("cold_sectors") or []) if str(item).strip()]

        regime_preferences = (
            ["momentum", "ma_cross", "growth_factor"]
            if fg >= 60
            else (
                ["rsi", "value_factor", "quality_factor"]
                if fg <= 40
                else ["ma_cross", "quality_factor", "growth_factor"]
            )
        )
        regime_type = "trend_expansion" if fg >= 60 else ("mean_reversion" if fg <= 40 else "rotation_balanced")
        primary_governed_regime = dict(governed_regime_summary[0] or {}) if governed_regime_summary else {}
        primary_governed_regime_name = str(primary_governed_regime.get("regime") or "").strip()
        if primary_governed_regime_name:
            regime_preferences = list(
                dict.fromkeys(
                    [
                        *cls._governed_regime_preferences(primary_governed_regime_name, fear_greed=fg),
                        *regime_preferences,
                    ]
                )
            )[:4]
        regime_rationale = f"恐贪指数 {fg:.1f} 对应 {regime_type}，自动寻找适配交易结构。"
        if primary_governed_regime_name:
            regime_rationale = (
                f"{regime_rationale[:-1]}，治理后候选池主导 regime="
                f"{primary_governed_regime_name} (count={int(primary_governed_regime.get('count') or 0)})。"
            )
        tasks.append(
            cls._finalize_task(
                {
                    "task_id": f"regime_{snapshot.get('date')}_{int(fg)}",
                    "task_key": f"regime:{snapshot.get('date')}:{regime_type}",
                    "task_source": "snapshot",
                    "theme": f"market_regime_{regime_type}",
                    "title": f"市场状态任务·{regime_type}",
                    "opportunity_type": regime_type,
                    "rationale": regime_rationale,
                    "preferred_strategy_types": regime_preferences,
                    "strategy_preferences": regime_preferences,
                    "target_symbol_policy": "prefer_intersection",
                    "universe_expansion_policy": "allow_market_fallback",
                    "preference_strength": "soft",
                    "preference_reason": (
                        f"snapshot_regime:fear_greed={fg:.1f};regime={regime_type}"
                        + (
                            f";governed={primary_governed_regime_name}"
                            if primary_governed_regime_name
                            else ""
                        )
                    ),
                    "validation_focus": "target_plus_representative",
                    "target_symbols": cls._top_codes(rows, limit=5),
                    "focus_industries": hot_sectors[:2] if hot_sectors else [],
                    "focus_markets": [],
                    "priority": 100,
                    "generation_limit": cls._snapshot_generation_limit(AUTONOMY_CANDIDATES_PER_TASK, priority=100),
                    "source_snapshot": {
                        "fear_greed_index": fg,
                        "fg_level": snapshot.get("fg_level"),
                        "governed_regime": primary_governed_regime_name or None,
                        "governed_regime_count": int(primary_governed_regime.get("count") or 0),
                    },
                }
            )
        )

        for idx, sector in enumerate(hot_sectors[:3], 1):
            matched = cls._match_rows(rows, [sector])
            priority = 90 - idx
            tasks.append(
                cls._finalize_task(
                    {
                        "task_id": f"hot_{idx}_{sector}",
                        "task_key": f"hot_sector:{snapshot.get('date')}:{sector}",
                        "task_source": "snapshot",
                        "theme": f"hot_sector_{sector}",
                        "title": f"热点行业任务·{sector}",
                        "opportunity_type": "sector_breakout",
                        "rationale": f"热点行业 {sector} 在快照中活跃，自动生成行业内趋势/回踩/龙头轮动策略。",
                        "preferred_strategy_types": ["momentum", "ma_cross", "growth_factor"],
                        "strategy_preferences": ["momentum", "ma_cross", "growth_factor"],
                        "target_symbol_policy": "prefer_intersection",
                        "universe_expansion_policy": "allow_market_fallback",
                        "preference_strength": "soft",
                        "preference_reason": f"sector_heat:hot={','.join(hot_sectors[:2]) or 'none'}",
                        "validation_focus": "target_plus_representative",
                        "focus_industries": [sector],
                        "target_symbols": cls._top_codes(matched or rows, limit=5),
                        "focus_markets": [],
                        "priority": priority,
                        "generation_limit": cls._snapshot_generation_limit(AUTONOMY_CANDIDATES_PER_TASK, priority=priority),
                    }
                )
            )

        for idx, sector in enumerate(cold_sectors[:2], 1):
            matched = cls._match_rows(rows, [sector])
            priority = 72 - idx
            tasks.append(
                cls._finalize_task(
                    {
                        "task_id": f"cold_{idx}_{sector}",
                        "task_key": f"cold_sector:{snapshot.get('date')}:{sector}",
                        "task_source": "snapshot",
                        "theme": f"cold_sector_{sector}",
                        "title": f"冷门修复任务·{sector}",
                        "opportunity_type": "oversold_repair",
                        "rationale": f"冷门行业 {sector} 进入观察名单，自动寻找超跌修复与估值修复机会。",
                        "preferred_strategy_types": ["value_factor", "quality_factor", "rsi"],
                        "strategy_preferences": ["value_factor", "quality_factor", "rsi"],
                        "target_symbol_policy": "prefer_intersection",
                        "universe_expansion_policy": "allow_market_fallback",
                        "preference_strength": "soft",
                        "preference_reason": f"sector_cold:cold={','.join(cold_sectors[:2]) or 'none'}",
                        "validation_focus": "target_plus_representative",
                        "focus_industries": [sector],
                        "target_symbols": cls._top_codes(matched or rows, limit=5),
                        "focus_markets": [],
                        "priority": priority,
                        "generation_limit": cls._snapshot_generation_limit(AUTONOMY_CANDIDATES_PER_TASK, priority=priority),
                    }
                )
            )

        for idx, family_item in enumerate(governed_family_summary[:2], 1):
            family_name = str(family_item.get("family") or "").strip()
            if not family_name:
                continue
            family_preferences = preferred_strategy_types_for_factor(
                family_name,
                default=regime_preferences or ["ma_cross", "momentum"],
            )
            family_rows = cls._focus_rows_for_family(
                rows,
                family_name=family_name,
                hot_sectors=hot_sectors,
                cold_sectors=cold_sectors,
            )
            focus_industries = cls._focus_industries_from_rows(family_rows) or hot_sectors[:1]
            avg_total_score = cls._safe_float(family_item.get("avg_total_score"))
            count = int(family_item.get("count") or 0)
            priority = min(
                98,
                max(
                    81,
                    int(round(78 + avg_total_score * 0.14 + min(count, 5) * 1.5)) - idx,
                ),
            )
            tasks.append(
                cls._finalize_task(
                    {
                        "task_id": f"governed_family_{idx}_{family_name}",
                        "task_key": f"governed_family:{snapshot.get('date')}:{family_name}",
                        "task_source": "snapshot",
                        "theme": f"factor_family_{family_name}",
                        "title": f"候选因子族任务·{family_name}",
                        "opportunity_type": "candidate_family_activation",
                        "rationale": (
                            f"治理后候选池显示 family={family_name} 活跃，"
                            f"count={count}，avg_score={avg_total_score:.1f}，"
                            "优先围绕该 family 组织策略生成。"
                        ),
                        "preferred_strategy_types": family_preferences,
                        "strategy_preferences": family_preferences,
                        "target_symbol_policy": "prefer_intersection",
                        "universe_expansion_policy": "allow_market_fallback",
                        "preference_strength": "medium",
                        "preference_reason": (
                            f"governed_family:{family_name};avg_score={avg_total_score:.1f};count={count}"
                        ),
                        "validation_focus": "candidate_target_only",
                        "focus_industries": focus_industries,
                        "target_symbols": cls._top_codes(family_rows, limit=5),
                        "focus_markets": [],
                        "priority": priority,
                        "generation_limit": cls._snapshot_generation_limit(
                            AUTONOMY_CANDIDATES_PER_TASK,
                            priority=priority,
                        ),
                        "factor_name": family_name,
                        "candidate_family": family_name,
                        "validation_score": round(avg_total_score, 4),
                        "expected_regime": [
                            str(item.get("regime") or "").strip()
                            for item in governed_regime_summary[:2]
                            if str(item.get("regime") or "").strip()
                        ],
                        "evidence_bundle": {
                            "governed_family": family_name,
                            "family_summary": family_item,
                            "candidate_pool_count": int(active_candidate_pool.get("count") or 0),
                        },
                    }
                )
            )

        for idx, candidate in enumerate(governed_top_candidates[:2], 1):
            artifact_id = str(candidate.get("artifact_id") or "").strip()
            candidate_name = str(candidate.get("name") or artifact_id or f"candidate_{idx}").strip()
            family_name = str(candidate.get("family") or "").strip()
            expected_regime = [
                str(item).strip()
                for item in list(candidate.get("expected_regime") or [])
                if str(item).strip()
            ]
            candidate_preferences = preferred_strategy_types_for_factor(
                family_name or candidate_name,
                default=regime_preferences or ["ma_cross", "momentum"],
            )
            family_rows = cls._focus_rows_for_family(
                rows,
                family_name=family_name or candidate_name,
                hot_sectors=hot_sectors,
                cold_sectors=cold_sectors,
            )
            focus_industries = cls._focus_industries_from_rows(family_rows) or hot_sectors[:1]
            score = cls._safe_float(candidate.get("total_score"))
            priority = min(99, max(84, int(round(84 + score * 0.12)) - idx))
            tasks.append(
                cls._finalize_task(
                    {
                        "task_id": f"governed_candidate_{idx}_{artifact_id or family_name or idx}",
                        "task_key": f"governed_candidate:{snapshot.get('date')}:{artifact_id or candidate_name}",
                        "task_source": "snapshot",
                        "theme": f"factor_candidate_{artifact_id or family_name or idx}",
                        "title": f"候选因子任务·{candidate_name}",
                        "opportunity_type": "candidate_factor_activation",
                        "rationale": (
                            f"治理后候选因子 {candidate_name} 已进入 active pool，"
                            f"family={family_name or 'unknown'}，score={score:.1f}，"
                            f"expected_regime={','.join(expected_regime) or 'n/a'}。"
                        ),
                        "preferred_strategy_types": candidate_preferences,
                        "strategy_preferences": candidate_preferences,
                        "target_symbol_policy": "prefer_intersection",
                        "universe_expansion_policy": "allow_market_fallback",
                        "preference_strength": "medium",
                        "preference_reason": (
                            f"governed_candidate:{artifact_id or candidate_name};"
                            f"family={family_name or 'unknown'};score={score:.1f}"
                        ),
                        "validation_focus": "candidate_target_only",
                        "focus_industries": focus_industries,
                        "target_symbols": cls._top_codes(family_rows, limit=5),
                        "focus_markets": [],
                        "priority": priority,
                        "generation_limit": cls._snapshot_generation_limit(
                            AUTONOMY_CANDIDATES_PER_TASK,
                            priority=priority,
                        ),
                        "factor_name": family_name or candidate_name,
                        "candidate_family": family_name,
                        "source_candidate_artifact_id": artifact_id or None,
                        "candidate_name": candidate_name,
                        "candidate_grade": candidate.get("grade"),
                        "validation_score": round(score, 4),
                        "expected_regime": expected_regime,
                        "evidence_bundle": {
                            "governed_candidate": candidate,
                            "candidate_pool_count": int(active_candidate_pool.get("count") or 0),
                        },
                    }
                )
            )

        rising_factors = [
            str(item).strip()
            for item in list(
                [item.get("family") for item in governed_family_summary]
                or factor_research.get("active_factors")
                or factor_research.get("positive_rising_factors")
                or [name for name, trend in dict(snapshot.get("factor_ic_trend") or {}).items() if str(trend) == "rising"]
            )
            if str(item).strip()
        ]
        for idx, factor_name in enumerate(rising_factors[:3], 1):
            preferences = preferred_strategy_types_for_factor(str(factor_name), default=["ma_cross", "momentum"])
            priority = 80 - idx
            tasks.append(
                cls._finalize_task(
                    {
                        "task_id": f"factor_{idx}_{factor_name}",
                        "task_key": f"factor:{snapshot.get('date')}:{factor_name}",
                        "task_source": "snapshot",
                        "theme": f"factor_rotation_{factor_name}",
                        "title": f"因子加速任务·{factor_name}",
                        "opportunity_type": "factor_acceleration",
                        "rationale": f"因子 {factor_name} 在快照中呈上升趋势，自动生成围绕该因子的选股与择时策略。",
                        "preferred_strategy_types": preferences,
                        "strategy_preferences": preferences,
                        "target_symbol_policy": "prefer_intersection",
                        "universe_expansion_policy": "allow_market_fallback",
                        "preference_strength": "soft",
                        "preference_reason": f"factor_research:{factor_name}",
                        "validation_focus": "target_plus_representative",
                        "focus_industries": hot_sectors[:1],
                        "target_symbols": cls._top_codes(rows, limit=5),
                        "focus_markets": [],
                        "priority": priority,
                        "generation_limit": cls._snapshot_generation_limit(AUTONOMY_CANDIDATES_PER_TASK, priority=priority),
                        "factor_name": factor_name,
                    }
                )
            )

        if rows:
            top_industries: Dict[str, int] = {}
            for row in rows:
                industry = str((row or {}).get("industry") or (row or {}).get("sector") or "未分类").strip() or "未分类"
                top_industries[industry] = top_industries.get(industry, 0) + 1
            ranked_industries = [item[0] for item in sorted(top_industries.items(), key=lambda item: item[1], reverse=True)]
            for idx, best_industry in enumerate(ranked_industries[:2], 1):
                matched = cls._match_rows(rows, [best_industry])
                priority = 68 - idx
                tasks.append(
                    cls._finalize_task(
                        {
                            "task_id": f"industry_{idx}_{best_industry}",
                            "task_key": f"industry:{snapshot.get('date')}:{best_industry}",
                            "task_source": "snapshot",
                            "theme": f"industry_leadership_{best_industry}",
                            "title": f"行业龙头任务·{best_industry}",
                            "opportunity_type": "industry_leadership",
                            "rationale": f"股票池中 {best_industry} 权重较高，自动生成龙头趋势与轮动策略。",
                            "preferred_strategy_types": ["ma_cross", "momentum", "quality_factor"],
                            "strategy_preferences": ["ma_cross", "momentum", "quality_factor"],
                            "target_symbol_policy": "prefer_intersection",
                            "universe_expansion_policy": "allow_market_fallback",
                            "preference_strength": "soft",
                            "preference_reason": "breadth_rotation_mix",
                            "validation_focus": "target_plus_representative",
                            "focus_industries": [best_industry],
                            "target_symbols": cls._top_codes(matched or rows, limit=5),
                            "focus_markets": [],
                            "priority": priority,
                            "generation_limit": cls._snapshot_generation_limit(AUTONOMY_CANDIDATES_PER_TASK, priority=priority),
                        }
                    )
                )
        return tasks

    async def scan(self, db, snapshot: dict[str, Any]) -> dict[str, Any]:
        snapshot = dict(snapshot or {})
        universe_rows: List[dict[str, Any]] = []
        list_stock_universe = getattr(db, "list_stock_universe", None)
        if callable(list_stock_universe):
            try:
                result = list_stock_universe(limit=120, offset=0)
                if inspect.isawaitable(result):
                    result = await result
                if isinstance(result, list):
                    universe_rows = result
                elif isinstance(result, tuple):
                    universe_rows = list(result)
                else:
                    try:
                        universe_rows = list(result or [])
                    except Exception:
                        universe_rows = []
            except Exception:
                universe_rows = []

        rows = [dict(item or {}) for item in list(universe_rows or [])]
        tasks: List[dict] = []

        event_tasks = self._deduplicate_tasks(self._build_event_driven_tasks(snapshot, rows))
        snapshot_tasks = self._deduplicate_tasks(self._build_snapshot_tasks(snapshot, rows))
        if event_tasks:
            tasks.extend(event_tasks)
            tasks.extend(self._select_snapshot_tasks_for_event_mix(event_tasks, snapshot_tasks))
        else:
            tasks.extend(snapshot_tasks)

        tasks = self._deduplicate_tasks(tasks)
        tasks.sort(key=self._task_sort_key, reverse=True)
        tasks = tasks[:AUTONOMY_MAX_RESEARCH_TASKS]
        task_sources = self._build_task_source_counts(tasks)

        type_counts: Dict[str, int] = {}
        for task in tasks:
            opportunity_type = str(task.get("opportunity_type") or "unknown")
            type_counts[opportunity_type] = type_counts.get(opportunity_type, 0) + 1

        self.last_report = {
            "summary": {
                "task_count": len(tasks),
                "task_types": type_counts,
                "themes": [str(item.get("theme") or "") for item in tasks],
                "task_sources": dict(task_sources),
                "event_task_count": len([item for item in tasks if item.get("task_source") == "event_driven"]),
                "max_tasks": AUTONOMY_MAX_RESEARCH_TASKS,
            },
            "tasks": tasks,
        }
        return self.get_last_report()


__all__ = ["MarketOpportunityScanner"]
