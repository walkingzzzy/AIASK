
    @classmethod
    async def _collect_event_driven_snapshot(
        cls,
        db,
    ) -> tuple[dict, str, Optional[str], Optional[dict]]:
        payload = {
            "enabled": False,
            "event_count": 0,
            "active_theme_count": 0,
            "signal_count": 0,
            "tasks_ready_count": 0,
            "events": [],
        }
        list_clusters = getattr(db, "list_factory_event_clusters", None)
        list_signals = getattr(db, "list_factory_event_signals", None)
        list_themes = getattr(db, "list_factory_theme_definitions", None)
        if not callable(list_clusters):
            return payload, "success", None, {"enabled": False}

        try:
            clusters = list_clusters(status="active", limit=8)
            if hasattr(clusters, "__await__"):
                clusters = await clusters
        except Exception as exc:
            return payload, "fallback", f"event_driven failed: {exc}", None

        theme_defs: Dict[str, dict] = {}
        if callable(list_themes):
            try:
                definitions = list_themes(active_only=True, limit=256)
                if hasattr(definitions, "__await__"):
                    definitions = await definitions
                theme_defs = {
                    str((item or {}).get("theme_code") or "").strip(): dict(item or {})
                    for item in list(definitions or [])
                    if str((item or {}).get("theme_code") or "").strip()
                }
            except Exception:
                theme_defs = {}

        payload["enabled"] = True
        raw_events = []
        total_signals = 0
        total_themes = 0
        ready_themes = 0

        for cluster in list(clusters or []):
            cluster = dict(cluster or {})
            event_id = str(cluster.get("event_id") or "").strip()
            if not event_id:
                continue
            grouped: Dict[str, dict] = {}
            for item in list(cluster.get("themes") or []):
                if isinstance(item, dict):
                    theme_code = str(
                        item.get("theme_code") or item.get("code") or item.get("theme") or ""
                    ).strip()
                    theme_name = str(item.get("theme_name") or theme_code).strip() or theme_code
                    direction = (
                        str(item.get("direction") or cluster.get("direction") or "neutral")
                        .strip()
                        .lower()
                        or "neutral"
                    )
                else:
                    theme_code = str(item or "").strip()
                    theme_name = (
                        str((theme_defs.get(theme_code) or {}).get("theme_name") or theme_code).strip()
                        or theme_code
                    )
                    direction = (
                        str(cluster.get("direction") or "neutral").strip().lower() or "neutral"
                    )
                if theme_code:
                    grouped[theme_code] = {
                        "theme_code": theme_code,
                        "theme_name": theme_name,
                        "direction": direction,
                        "signal_rows": [],
                        "supporting_reasons": [],
                    }

            signal_rows: List[dict] = []
            if callable(list_signals):
                try:
                    result = list_signals(event_id=event_id, limit=24)
                    if hasattr(result, "__await__"):
                        result = await result
                    signal_rows = [dict(item or {}) for item in list(result or [])]
                except Exception:
                    signal_rows = []

            if signal_rows:
                total_signals += len(signal_rows)
            for signal in signal_rows:
                theme_code = str(signal.get("theme_code") or "").strip() or cls._default_theme_code(
                    cluster
                )
                theme_def = theme_defs.get(theme_code) or {}
                direction = (
                    str(
                        signal.get("direction")
                        or (signal.get("evidence") or {}).get("direction")
                        or cluster.get("direction")
                        or "neutral"
                    )
                    .strip()
                    .lower()
                    or "neutral"
                )
                group = grouped.setdefault(
                    theme_code,
                    {
                        "theme_code": theme_code,
                        "theme_name": str(theme_def.get("theme_name") or theme_code).strip()
                        or theme_code,
                        "direction": direction,
                        "signal_rows": [],
                        "supporting_reasons": [],
                    },
                )
                group["direction"] = direction or group.get("direction") or "neutral"
                symbol = str(signal.get("symbol") or signal.get("code") or "").strip()
                final_score = cls._clip_score(signal.get("final_score"), default=0.0)
                theme_score = cls._clip_score(signal.get("theme_score"), default=final_score)
                exposure_score = cls._clip_score(signal.get("exposure_score"), default=final_score)
                price_confirm_score = cls._clip_score(signal.get("price_confirm_score"), default=0.0)
                flow_confirm_score = cls._clip_score(signal.get("flow_confirm_score"), default=0.0)
                rationale = cls._compact_text(
                    signal.get("rationale") or (signal.get("evidence") or {}).get("summary"),
                    limit=100,
                )
                if rationale and rationale not in group["supporting_reasons"]:
                    group["supporting_reasons"].append(rationale)
                if symbol:
                    group["signal_rows"].append(
                        {
                            "symbol": symbol,
                            "final_score": final_score,
                            "theme_score": theme_score,
                            "exposure_score": exposure_score,
                            "price_confirm_score": price_confirm_score,
                            "flow_confirm_score": flow_confirm_score,
                            "rationale": rationale,
                        }
                    )

            theme_payloads: List[dict] = []
            for theme_code, theme in grouped.items():
                signal_values = list(theme.get("signal_rows") or [])
                signal_values.sort(
                    key=lambda item: float(item.get("final_score") or 0.0), reverse=True
                )
                final_scores = [
                    cls._clip_score(item.get("final_score"), default=0.0)
                    for item in signal_values
                ]
                avg_final_score = (
                    round(sum(final_scores) / len(final_scores), 4) if final_scores else 0.0
                )
                max_final_score = round(max(final_scores), 4) if final_scores else 0.0
                from ..domain.constants import OPPORTUNITY_TARGET_SYMBOLS_PER_TASK as _COLLECT_LIMIT
                target_symbols = [
                    item.get("symbol") for item in signal_values if item.get("symbol")
                ][:_COLLECT_LIMIT]
                opportunity_hint = (
                    "factor_acceleration"
                    if "factor" in str(theme_code or "").lower()
                    else "sector_breakout"
                )
                strategy_prefs = cls._event_strategy_preferences(
                    direction=theme.get("direction") or cluster.get("direction") or "neutral",
                    theme_name=theme.get("theme_name") or theme_code,
                    opportunity_hint=opportunity_hint,
                )
                theme_direction = (
                    theme.get("direction")
                    or str(cluster.get("direction") or "neutral").strip().lower()
                    or "neutral"
                )
                theme_payload = {
                    "theme_code": theme_code,
                    "theme_name": theme.get("theme_name") or theme_code,
                    "direction": theme_direction,
                    "horizon": str(cluster.get("horizon") or "swing_5_20d").strip()
                    or "swing_5_20d",
                    "signal_count": len(signal_values),
                    "target_symbols": target_symbols,
                    "strategy_preferences": strategy_prefs,
                    "preferred_strategy_types": list(strategy_prefs),
                    "allowed_strategy_types": [],
                    "target_symbol_policy": "strict_intersection",
                    "universe_expansion_policy": "allow_same_theme_only",
                    "preference_strength": "medium",
                    "preference_reason": f"event_evidence:{theme_code}:{theme_direction}",
                    "validation_focus": "event_target_only",
                    "supporting_reasons": list(theme.get("supporting_reasons") or [])[:4],
                    "score_summary": {
                        "avg_final_score": avg_final_score,
                        "max_final_score": max_final_score,
                        "top_symbols": target_symbols,
                    },
                }
                total_themes += 1
                if target_symbols:
                    ready_themes += 1
                theme_payloads.append(theme_payload)

            if not theme_payloads:
                continue
            theme_payloads.sort(
                key=lambda item: (
                    float((item.get("score_summary") or {}).get("avg_final_score") or 0.0),
                    int(item.get("signal_count") or 0),
                ),
                reverse=True,
            )
            raw_events.append(
                {
                    "event_id": event_id,
                    "event_type": cluster.get("event_type"),
                    "event_name": cluster.get("event_name") or cluster.get("summary") or event_id,
                    "summary": cls._compact_text(
                        cluster.get("summary") or cluster.get("event_name") or event_id,
                        limit=160,
                    ),
                    "direction": str(cluster.get("direction") or "neutral").strip().lower()
                    or "neutral",
                    "intensity": cls._clip_score(cluster.get("intensity"), default=0.0),
                    "confidence": cls._clip_score(cluster.get("confidence"), default=0.0),
                    "horizon": str(cluster.get("horizon") or "swing_5_20d").strip()
                    or "swing_5_20d",
                    "occurred_at": cluster.get("occurred_at"),
                    "last_seen_at": cluster.get("last_seen_at"),
                    "themes": theme_payloads[:4],
                }
            )

        raw_events.sort(
            key=lambda item: (
                float(item.get("confidence") or 0.0),
                float(item.get("intensity") or 0.0),
                max(
                    float((theme.get("score_summary") or {}).get("avg_final_score") or 0.0)
                    for theme in list(item.get("themes") or [{}])
                ),
            ),
            reverse=True,
        )
        payload.update(
            {
                "event_count": len(raw_events),
                "active_theme_count": total_themes,
                "signal_count": total_signals,
                "tasks_ready_count": ready_themes,
                "events": raw_events[:6],
            }
        )
        return payload, "success", None, {
            "enabled": True,
            "event_count": len(raw_events),
            "active_theme_count": total_themes,
            "tasks_ready_count": ready_themes,
        }
