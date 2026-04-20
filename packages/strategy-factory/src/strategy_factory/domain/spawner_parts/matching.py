    """根据每日数据快照生成候选策略。"""
    _EVENT_FOCUS_TARGETS_BY_KEYWORD = get_event_focus_targets_by_keyword()
    _TREND_CLUSTER_TYPES = frozenset({"momentum", "ma_cross", "volatility_breakout", "event_structure_breakout", "sector_rotation"})
    _LOCAL_GENERATION_CAPS = {
        "mean_reversion_short": 1,
    }
    _DIVERSIFICATION_GROUPS = {
        "quality_defensive": frozenset({"quality_factor", "value_factor", "macro_timing"}),
        "mean_reversion": frozenset({"rsi", "gap_fill", "mean_reversion_short"}),
        "flow_rotation": frozenset({"north_capital_track", "sector_rotation", "margin_divergence"}),
        "event_breakout": frozenset({"event_structure_breakout", "volatility_breakout", "momentum"}),
    }
    _POOL_PROFILE_BY_TYPE = {
        "momentum": "high_vol_growth",
        "volatility_breakout": "high_vol_growth",
        "event_structure_breakout": "high_vol_growth",
        "growth_factor": "high_vol_growth",
        "gap_fill": "high_vol_growth",
        "mean_reversion_short": "high_vol_growth",
        "rsi": "high_vol_growth",
        "quality_factor": "low_vol_defensive",
        "value_factor": "low_vol_defensive",
        "macro_timing": "low_vol_defensive",
        "north_capital_track": "cycle_resource",
        "sector_rotation": "cycle_resource",
        "margin_divergence": "cycle_resource",
        "ma_cross": "cycle_resource",
    }
    _SNAPSHOT_TARGET_SYMBOL_BUDGET_BY_TYPE = {
        "momentum": 3,
        "ma_cross": 3,
        "rsi": 3,
        "volatility_breakout": 3,
        "event_structure_breakout": 3,
        "gap_fill": 2,
        "mean_reversion_short": 2,
        "value_factor": 4,
        "quality_factor": 4,
        "growth_factor": 4,
        "multi_factor": 4,
        "macro_timing": 4,
        "sector_rotation": 4,
        "north_capital_track": 3,
        "margin_divergence": 3,
    }
    _SNAPSHOT_TARGET_FAMILY_ALIASES = {
        "momentum": ("momentum", "ma_cross", "growth_factor"),
        "ma_cross": ("ma_cross", "momentum", "quality_factor"),
        "rsi": ("rsi", "gap_fill", "mean_reversion_short", "value_factor"),
        "volatility_breakout": ("volatility_breakout", "event_structure_breakout", "momentum", "ma_cross"),
        "event_structure_breakout": ("event_structure_breakout", "volatility_breakout", "momentum", "north_capital_track"),
        "gap_fill": ("gap_fill", "rsi", "mean_reversion_short"),
        "mean_reversion_short": ("mean_reversion_short", "rsi", "gap_fill", "value_factor"),
        "value_factor": ("value_factor", "quality_factor", "multi_factor"),
        "quality_factor": ("quality_factor", "value_factor", "multi_factor"),
        "growth_factor": ("growth_factor", "momentum", "quality_factor"),
        "multi_factor": ("multi_factor", "quality_factor", "value_factor", "growth_factor"),
        "macro_timing": ("macro_timing", "quality_factor", "value_factor", "ma_cross"),
        "sector_rotation": ("sector_rotation", "north_capital_track", "quality_factor", "ma_cross"),
        "north_capital_track": ("north_capital_track", "sector_rotation", "quality_factor", "growth_factor"),
        "margin_divergence": ("margin_divergence", "sector_rotation", "value_factor", "quality_factor"),
    }

    def __init__(self):
        self.policy_version = get_spawn_policy_version()
        self.last_report: dict = {
            "summary": {
                "policy_version": self.policy_version,
                "candidate_count": 0,
                "source_counts": {},
                "strategy_type_counts": {},
                "quota_fill_count": 0,
                "signal_trigger_count": 0,
                "threshold_hit_count": 0,
                "parameter_source_counts": {},
                "quota_fill_mode_counts": {},
                "quota_fill_quality_counts": {},
                "historical_distribution_count": 0,
                "historical_guided_quota_fill_count": 0,
                "signal_aligned_quota_fill_count": 0,
                "no_signal_quota_fill_count": 0,
                "effective_quota_fill_count": 0,
            }
        }

    def get_last_report(self) -> dict:
        return self.last_report

    @staticmethod
    def _threshold(field: str, operator: str, threshold: Any, actual: Any, label: Optional[str] = None) -> dict:
        item = {
            "field": field,
            "operator": operator,
            "threshold": threshold,
            "actual": actual,
            "matched": True,
        }
        if label:
            item["label"] = label
        return item

    @staticmethod
    def _build_generation_reason(
        source: str,
        reason: str,
        trigger_signal: Optional[dict] = None,
        trigger_thresholds: Optional[List[dict]] = None,
        quota_fill: Optional[dict] = None,
        kind: str = "signal_trigger",
    ) -> dict:
        return {
            "kind": kind,
            "source": source,
            "summary": reason,
            "trigger_signal": trigger_signal or {},
            "trigger_thresholds": list(trigger_thresholds or []),
            "quota_fill": quota_fill,
        }

    @staticmethod
    def _normalize_text_list(*values: Any, limit: int = 8) -> List[str]:
        items: List[str] = []
        queue = list(values)
        while queue:
            value = queue.pop(0)
            if isinstance(value, (list, tuple, set)):
                queue[:0] = list(value)
                continue
            token = str(value or "").strip()
            if token and token not in items:
                items.append(token)
        return items[: max(1, int(limit or 8))]

    @classmethod
    def _build_event_prefilter(
        cls,
        *,
        observed_sources: Optional[List[str]] = None,
        evidence_summary: str = "",
        event_id: str = "",
        theme_code: str = "",
        focus_industries: Optional[List[str]] = None,
        event_anchor: Optional[dict[str, Any]] = None,
        confirmation_count: Optional[int] = None,
        anchor_strength: Any = None,
        required: bool = True,
        profile: str = "announcement_flow_sector_v1",
        min_confirmations: int = 1,
    ) -> dict:
        allowed_sources = ["announcement", "fund_flow", "sector_catalyst"]
        normalized_sources = [
            token
            for token in cls._normalize_text_list(observed_sources, limit=6)
            if token in allowed_sources
        ]
        normalized_focus = cls._normalize_text_list(focus_industries, limit=3)
        min_conf = max(1, int(min_confirmations or 1))
        normalized_event_anchor = dict(event_anchor or {})
        normalized_event_anchor = {
            "source": str(normalized_event_anchor.get("source") or "").strip() or None,
            "id": str(normalized_event_anchor.get("id") or "").strip() or None,
            "type": str(normalized_event_anchor.get("type") or "").strip() or None,
            "strength": normalized_event_anchor.get("strength"),
            "theme_code": str(normalized_event_anchor.get("theme_code") or "").strip() or None,
            "focus_industries": cls._normalize_text_list(
                normalized_event_anchor.get("focus_industries"),
                normalized_focus,
                limit=3,
            ),
            "target_symbols": _normalize_target_codes(normalized_event_anchor.get("target_symbols"), limit=6),
        }
        if not any(
            normalized_event_anchor.get(key) not in (None, "", [], {})
            for key in ("source", "id", "type", "theme_code", "target_symbols")
        ):
            normalized_event_anchor = {}
        effective_confirmation_count = (
            max(0, int(confirmation_count))
            if confirmation_count is not None
            else len(normalized_sources)
        )
        effective_anchor_strength = (
            anchor_strength
            if anchor_strength not in (None, "", [], {})
            else normalized_event_anchor.get("strength")
        )
        passed = (not required) or (bool(normalized_event_anchor) and effective_confirmation_count >= min_conf)
        status = "passed" if passed else ("missing" if not normalized_sources else "insufficient_confirmations")
        return {
            "required": bool(required),
            "profile": str(profile or "announcement_flow_sector_v1").strip() or "announcement_flow_sector_v1",
            "allowed_sources": list(allowed_sources),
            "observed_sources": normalized_sources,
            "observed_confirmation_count": len(normalized_sources),
            "confirmation_count": effective_confirmation_count,
            "min_confirmations": min_conf,
            "passed": passed,
            "status": status,
            "event_id": str(event_id or "").strip() or None,
            "theme_code": str(theme_code or "").strip() or None,
            "focus_industries": normalized_focus,
            "evidence_summary": str(evidence_summary or "").strip() or None,
            "event_anchor": dict(normalized_event_anchor),
            "anchor_strength": effective_anchor_strength,
        }

    @classmethod
    def _snapshot_event_anchor(
        cls,
        snapshot: Optional[dict],
        *,
        source: str = "",
        trigger_signal: Optional[dict] = None,
    ) -> dict:
        payload = dict(snapshot or {})
        source_name = str(source or payload.get("source") or "").strip().lower()
        trigger_field = str((trigger_signal or {}).get("field") or payload.get("trigger_field") or "").strip().lower()
        event_id = str(payload.get("event_id") or "").strip()
        announcement_id = str(payload.get("announcement_id") or "").strip()
        announcement_ids = cls._normalize_text_list(payload.get("announcement_ids"), limit=4)
        event_type = str(payload.get("event_type") or payload.get("catalyst_type") or "").strip().lower()
        theme_code = str(payload.get("theme_code") or "").strip()
        hot_sectors = cls._normalize_text_list(payload.get("hot_sectors"), limit=3)
        if event_id or announcement_id or announcement_ids or event_type in {"announcement", "earnings", "filing", "news"} or source_name == "announcement":
            anchor_id = event_id or announcement_id or (announcement_ids[0] if announcement_ids else "") or event_type or "announcement"
            return {
                "source": "announcement",
                "id": anchor_id,
                "type": event_type or "announcement",
                "strength": cls._safe_float(payload.get("confidence") or payload.get("intensity") or 1.0),
                "theme_code": theme_code or None,
                "focus_industries": list(hot_sectors),
                "target_symbols": _normalize_target_codes(payload.get("target_symbols"), limit=6),
            }
        if source_name == "fund_flow" or trigger_field in {"north_fund_3d_net", "margin_5d_change_pct"}:
            return {
                "source": "fund_flow",
                "id": trigger_field or source_name or "fund_flow",
                "type": "fund_flow",
                "strength": cls._safe_float((trigger_signal or {}).get("value") or payload.get(trigger_field) or 0.0),
                "focus_industries": list(hot_sectors),
                "target_symbols": _normalize_target_codes(payload.get("target_symbols"), limit=6),
            }

        event_driven = dict(payload.get("event_driven") or {})
        event_items = [dict(item or {}) for item in list(event_driven.get("events") or []) if isinstance(item, dict)]
        preferred_focus = set(hot_sectors)
        ranked_events: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
        for event in event_items:
            themes = [dict(item or {}) for item in list(event.get("themes") or []) if isinstance(item, dict)]
            for theme in themes:
                focus_name = str(theme.get("theme_name") or theme.get("theme_code") or "").strip()
                target_symbols = _normalize_target_codes(theme.get("target_symbols"), limit=6)
                score_summary = dict(theme.get("score_summary") or {})
                avg_score = cls._safe_float(score_summary.get("avg_final_score") or 0.0)
                confidence = cls._safe_float(event.get("confidence") or event.get("intensity") or 0.0)
                focus_bonus = 1.0 if (focus_name and focus_name in preferred_focus) else 0.0
                target_bonus = 0.5 if target_symbols else 0.0
                ranked_events.append((avg_score + confidence + focus_bonus + target_bonus, event, theme))
        if ranked_events:
            ranked_events.sort(key=lambda item: item[0], reverse=True)
            _score, event, theme = ranked_events[0]
            focus_name = str(theme.get("theme_name") or theme.get("theme_code") or "").strip()
            return {
                "source": "sector_catalyst",
                "id": str(event.get("event_id") or "").strip() or None,
                "type": str(event.get("event_type") or "sector_catalyst").strip() or "sector_catalyst",
                "strength": round(
                    max(
                        cls._safe_float((theme.get("score_summary") or {}).get("avg_final_score") or 0.0),
                        cls._safe_float(event.get("confidence") or event.get("intensity") or 0.0),
                    ),
                    4,
                ),
                "theme_code": str(theme.get("theme_code") or "").strip() or None,
                "focus_industries": cls._normalize_text_list(focus_name, hot_sectors, limit=3),
                "target_symbols": _normalize_target_codes(theme.get("target_symbols"), limit=6),
            }
        return {}

    @classmethod
    def _snapshot_event_prefilter(
        cls,
        snapshot: Optional[dict],
        *,
        source: str = "",
        trigger_signal: Optional[dict] = None,
    ) -> dict:
        payload = dict(snapshot or {})
        observed_sources: List[str] = []
        evidence_parts: List[str] = []
        theme_code = str(payload.get("theme_code") or "").strip()
        hot_sectors = cls._normalize_text_list(payload.get("hot_sectors"), limit=3)
        source_name = str(source or payload.get("source") or "").strip().lower()
        trigger_field = str((trigger_signal or payload.get("trigger_signal") or {}).get("field") or "").strip().lower()
        event_anchor = cls._snapshot_event_anchor(payload, source=source_name, trigger_signal=trigger_signal)
        anchor_source = str(event_anchor.get("source") or "").strip().lower()
        if anchor_source == "announcement":
            observed_sources.append("announcement")
            evidence_parts.append(f"announcement:{event_anchor.get('id') or event_anchor.get('type') or 'announcement'}")
        if anchor_source == "sector_catalyst":
            observed_sources.append("sector_catalyst")
            sector_focus = cls._normalize_text_list(event_anchor.get("focus_industries"), hot_sectors, limit=2)
            evidence_parts.append(
                f"sector_catalyst:{','.join(sector_focus) or event_anchor.get('theme_code') or event_anchor.get('id') or 'sector'}"
            )
        if source_name == "fund_flow" or trigger_field in {"north_fund_3d_net", "margin_5d_change_pct"}:
            observed_sources.append("fund_flow")
            evidence_parts.append(f"fund_flow:{trigger_field or source_name}")
        return cls._build_event_prefilter(
            observed_sources=observed_sources,
            evidence_summary=" | ".join(part for part in evidence_parts if part),
            event_id=str(event_anchor.get("id") or payload.get("event_id") or "").strip(),
            theme_code=theme_code,
            focus_industries=cls._normalize_text_list(event_anchor.get("focus_industries"), hot_sectors, limit=3),
            event_anchor=event_anchor,
            confirmation_count=len(observed_sources),
            anchor_strength=event_anchor.get("strength"),
            required=True,
        )

    @staticmethod
    def _event_anchor_has_explicit_source(event_anchor: Optional[dict[str, Any]]) -> bool:
        payload = dict(event_anchor or {})
        return str(payload.get("source") or "").strip().lower() in {"announcement", "fund_flow", "sector_catalyst"}

    @classmethod
    def _focus_industry_target_symbols(
        cls,
        strategy_type: str,
        candidate: Optional[dict],
        snapshot: Optional[dict],
        *,
        limit: int,
    ) -> List[str]:
        if str(strategy_type or "").strip().lower() != "event_structure_breakout":
            return []
        payload = dict(candidate or {})
        hints = cls._normalize_text_list(
            dict(payload.get("event_prefilter") or {}).get("focus_industries"),
            dict(payload.get("research_task") or {}).get("focus_industries"),
            dict(payload.get("research_task") or {}).get("hot_sectors"),
            dict(snapshot or {}).get("hot_sectors"),
            limit=4,
        )
        selected: List[str] = []
        seen: set[str] = set()
        for hint in hints:
            lowered = hint.lower()
            for keyword, codes in cls._EVENT_FOCUS_TARGETS_BY_KEYWORD.items():
                normalized_keyword = str(keyword or "").strip().lower()
                if not normalized_keyword:
                    continue
                if normalized_keyword not in lowered and lowered not in normalized_keyword:
                    continue
                for code in codes:
                    token = str(code or "").strip()
                    if not token or token in seen:
                        continue
                    seen.add(token)
                    selected.append(token)
        return _normalize_target_codes(selected, limit=limit)

    @classmethod
    def _event_anchor_target_symbols(
        cls,
        strategy_type: str,
        candidate: Optional[dict],
        snapshot: Optional[dict],
        *,
        limit: int,
    ) -> List[str]:
        if str(strategy_type or "").strip().lower() != "event_structure_breakout":
            return []
        payload = dict(candidate or {})
        event_prefilter = dict(payload.get("event_prefilter") or {})
        event_anchor = dict(event_prefilter.get("event_anchor") or payload.get("event_anchor") or {})
        if not event_anchor:
            event_anchor = cls._snapshot_event_anchor(
                snapshot,
                source=str(dict(payload.get("generation_reason") or {}).get("source") or ""),
                trigger_signal=dict(payload.get("trigger_signal") or {}),
            )
        return _normalize_target_codes(event_anchor.get("target_symbols"), limit=limit)
