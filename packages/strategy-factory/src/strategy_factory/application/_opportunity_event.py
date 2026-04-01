"""Event-driven task builders for market opportunity scanning."""

from __future__ import annotations

from typing import Any, List

from ..domain.constants import AUTONOMY_CANDIDATES_PER_TASK, EVENT_TASK_GENERATION_LIMIT_MAX


class _MarketOpportunityScannerEventMixin:
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
