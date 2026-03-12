"""策略工厂机会扫描与研究任务生成。"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional

from .constants import (
    AUTONOMY_CANDIDATES_PER_TASK,
    AUTONOMY_MAX_RESEARCH_TASKS,
    EVENT_SNAPSHOT_MIX_MAX,
    EVENT_TASK_GENERATION_LIMIT_MAX,
)


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
        codes: List[str] = []
        seen: set[str] = set()

        def visit(value: Any) -> None:
            if value is None:
                return
            if isinstance(value, dict):
                for key in ("symbol", "code", "stock_code"):
                    if value.get(key) is not None:
                        visit(value.get(key))
                for key in ("symbols", "codes", "stock_codes", "target_symbols"):
                    if value.get(key) is not None:
                        visit(value.get(key))
                return
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    visit(item)
                return
            raw = str(value or "").strip()
            if not raw:
                return
            if any(sep in raw for sep in [",", ";", "|", "\n", "\t", " "]):
                normalized = raw.replace(";", ",").replace("|", ",").replace("\n", ",").replace("\t", ",").replace(" ", ",")
                for part in normalized.split(","):
                    visit(part)
                return
            code = raw.split(".")[0].strip()
            if not code or code in seen:
                return
            seen.add(code)
            codes.append(code)

        visit(values)
        return codes[: max(1, min(int(limit or 5), 12))]

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

    @staticmethod
    def _task_sort_key(item: dict) -> tuple[int, int, int]:
        source = str(item.get("task_source") or "").strip()
        return (
            1 if source == "event_driven" else 0,
            int(item.get("priority") or 0),
            int(item.get("generation_limit") or 0),
        )

    @classmethod
    def _select_snapshot_tasks_for_event_mix(cls, event_tasks: List[dict], snapshot_tasks: List[dict]) -> List[dict]:
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
        blocked_opportunity_types = {
            str(item.get("opportunity_type") or "").strip()
            for item in list(event_tasks or [])
            if str(item.get("opportunity_type") or "").strip()
        }

        for task in sorted(cls._deduplicate_tasks(snapshot_tasks), key=cls._task_sort_key, reverse=True):
            theme = str(task.get("theme") or "").strip()
            opportunity_type = str(task.get("opportunity_type") or "").strip()
            if theme and theme in seen_themes:
                continue
            if opportunity_type and opportunity_type in blocked_opportunity_types:
                continue
            selected.append(task)
            if theme:
                seen_themes.add(theme)
            if opportunity_type:
                blocked_opportunity_types.add(opportunity_type)
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
            haystack = " ".join([
                str((row or {}).get("industry") or ""),
                str((row or {}).get("sector") or ""),
                str((row or {}).get("name") or ""),
                str((row or {}).get("code") or ""),
            ])
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
        return text[: max(0, limit - 1)] + "..."

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
            return ["rsi", "quality_factor", "value_factor"]
        if any(token in lowered for token in ["quality", "roe", "dividend", "cashflow", "防御", "高股息"]):
            return ["quality_factor", "value_factor", "ma_cross"]
        if any(token in lowered for token in ["芯片", "半导体", "算力", "机器人", "ai", "军工", "油", "gas", "资源", "航运"]):
            return ["momentum", "ma_cross", "growth_factor"]
        if opportunity_type == "factor_acceleration":
            return ["growth_factor", "momentum", "ma_cross"]
        if opportunity_type == "oversold_repair":
            return ["rsi", "value_factor", "quality_factor"]
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
                target_symbols = cls._normalize_codes([
                    theme.get("target_symbols"),
                    theme.get("top_symbols"),
                    ((theme.get("score_summary") or {}).get("top_symbols") if isinstance(theme.get("score_summary"), dict) else None),
                ], limit=5)
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
                priority = int(round(
                    55
                    + avg_final_score * 30
                    + max_final_score * 15
                    + confidence * 10
                    + intensity * 10
                    + min(signal_count, 4)
                ))
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
                    f"围绕高暴露股票生成研究任务。"
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
                tasks.append({
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
                    "strategy_preferences": strategy_preferences,
                    "target_symbols": target_symbols,
                    "stock_pool": {"selection_mode": "explicit", "symbols": target_symbols},
                    "focus_industries": focus_industries,
                    "focus_markets": [],
                    "priority": priority,
                    "generation_limit": generation_limit,
                    "evidence_bundle": evidence_bundle,
                    "selection_logic": list(theme.get("selection_logic") or [])[:3],
                })
        return tasks

    @classmethod
    def _build_snapshot_tasks(cls, snapshot: dict[str, Any], rows: List[dict]) -> List[dict]:
        tasks: List[dict] = []
        fg = float(snapshot.get("fear_greed_index") or 50.0)
        factor_research = dict(snapshot.get("factor_research") or {})
        hot_sectors = [str(item).strip() for item in list(snapshot.get("hot_sectors") or []) if str(item).strip()]
        cold_sectors = [str(item).strip() for item in list(snapshot.get("cold_sectors") or []) if str(item).strip()]

        regime_preferences = ["momentum", "ma_cross", "growth_factor"] if fg >= 60 else (["rsi", "value_factor", "quality_factor"] if fg <= 40 else ["ma_cross", "quality_factor", "growth_factor"])
        regime_type = "trend_expansion" if fg >= 60 else ("mean_reversion" if fg <= 40 else "rotation_balanced")
        tasks.append({
            "task_id": f"regime_{snapshot.get('date')}_{int(fg)}",
            "task_key": f"regime:{snapshot.get('date')}:{regime_type}",
            "task_source": "snapshot",
            "theme": f"market_regime_{regime_type}",
            "title": f"市场状态任务·{regime_type}",
            "opportunity_type": regime_type,
            "rationale": f"恐贪指数 {fg:.1f} 对应 {regime_type}，自动寻找适配交易结构。",
            "strategy_preferences": regime_preferences,
            "target_symbols": cls._top_codes(rows, limit=5),
            "focus_industries": hot_sectors[:2] if hot_sectors else [],
            "focus_markets": [],
            "priority": 100,
            "generation_limit": max(2, AUTONOMY_CANDIDATES_PER_TASK),
            "source_snapshot": {"fear_greed_index": fg, "fg_level": snapshot.get("fg_level")},
        })

        for idx, sector in enumerate(hot_sectors[:2], 1):
            matched = cls._match_rows(rows, [sector])
            tasks.append({
                "task_id": f"hot_{idx}_{sector}",
                "task_key": f"hot_sector:{snapshot.get('date')}:{sector}",
                "task_source": "snapshot",
                "theme": f"hot_sector_{sector}",
                "title": f"热点行业任务·{sector}",
                "opportunity_type": "sector_breakout",
                "rationale": f"热点行业 {sector} 在快照中活跃，自动生成行业内趋势/回踩/龙头轮动策略。",
                "strategy_preferences": ["momentum", "ma_cross", "growth_factor"],
                "focus_industries": [sector],
                "target_symbols": cls._top_codes(matched or rows, limit=5),
                "focus_markets": [],
                "priority": 90 - idx,
                "generation_limit": AUTONOMY_CANDIDATES_PER_TASK,
            })

        for idx, sector in enumerate(cold_sectors[:1], 1):
            matched = cls._match_rows(rows, [sector])
            tasks.append({
                "task_id": f"cold_{idx}_{sector}",
                "task_key": f"cold_sector:{snapshot.get('date')}:{sector}",
                "task_source": "snapshot",
                "theme": f"cold_sector_{sector}",
                "title": f"冷门修复任务·{sector}",
                "opportunity_type": "oversold_repair",
                "rationale": f"冷门行业 {sector} 进入观察名单，自动寻找超跌修复与估值修复机会。",
                "strategy_preferences": ["rsi", "value_factor", "quality_factor"],
                "focus_industries": [sector],
                "target_symbols": cls._top_codes(matched or rows, limit=5),
                "focus_markets": [],
                "priority": 72 - idx,
                "generation_limit": AUTONOMY_CANDIDATES_PER_TASK,
            })

        rising_factors = [
            str(item).strip()
            for item in list(
                factor_research.get("active_factors")
                or factor_research.get("positive_rising_factors")
                or [name for name, trend in dict(snapshot.get("factor_ic_trend") or {}).items() if str(trend) == "rising"]
            )
            if str(item).strip()
        ]
        factor_mapping = {
            "value": ["value_factor", "quality_factor"],
            "quality": ["quality_factor", "value_factor"],
            "growth": ["growth_factor", "momentum"],
            "momentum": ["momentum", "ma_cross"],
        }
        for idx, factor_name in enumerate(rising_factors[:2], 1):
            preferences = ["ma_cross", "momentum"]
            lowered = str(factor_name).lower()
            for token, mapped in factor_mapping.items():
                if token in lowered:
                    preferences = mapped
                    break
            tasks.append({
                "task_id": f"factor_{idx}_{factor_name}",
                "task_key": f"factor:{snapshot.get('date')}:{factor_name}",
                "task_source": "snapshot",
                "theme": f"factor_rotation_{factor_name}",
                "title": f"因子加速任务·{factor_name}",
                "opportunity_type": "factor_acceleration",
                "rationale": f"因子 {factor_name} 在快照中呈上升趋势，自动生成围绕该因子的选股与择时策略。",
                "strategy_preferences": preferences,
                "focus_industries": hot_sectors[:1],
                "target_symbols": cls._top_codes(rows, limit=5),
                "focus_markets": [],
                "priority": 80 - idx,
                "generation_limit": AUTONOMY_CANDIDATES_PER_TASK,
                "factor_name": factor_name,
            })

        if rows:
            top_industries: Dict[str, int] = {}
            for row in rows:
                industry = str((row or {}).get("industry") or (row or {}).get("sector") or "未分类").strip() or "未分类"
                top_industries[industry] = top_industries.get(industry, 0) + 1
            best_industry = sorted(top_industries.items(), key=lambda item: item[1], reverse=True)[0][0] if top_industries else None
            if best_industry:
                matched = cls._match_rows(rows, [best_industry])
                tasks.append({
                    "task_id": f"industry_{best_industry}",
                    "task_key": f"industry:{snapshot.get('date')}:{best_industry}",
                    "task_source": "snapshot",
                    "theme": f"industry_leadership_{best_industry}",
                    "title": f"行业龙头任务·{best_industry}",
                    "opportunity_type": "industry_leadership",
                    "rationale": f"股票池中 {best_industry} 权重较高，自动生成龙头趋势与轮动策略。",
                    "strategy_preferences": ["ma_cross", "momentum", "quality_factor"],
                    "focus_industries": [best_industry],
                    "target_symbols": cls._top_codes(matched or rows, limit=5),
                    "focus_markets": [],
                    "priority": 68,
                    "generation_limit": AUTONOMY_CANDIDATES_PER_TASK,
                })
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
