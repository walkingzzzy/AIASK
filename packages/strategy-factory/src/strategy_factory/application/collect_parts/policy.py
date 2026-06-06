
    @staticmethod
    def _decoded_event_mapping(value) -> dict:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str) and value.strip():
            try:
                import json

                decoded = json.loads(value)
                return dict(decoded) if isinstance(decoded, dict) else {}
            except Exception:
                return {}
        return {}

    @classmethod
    def _verified_normalized_event_anchor(cls, cluster: dict) -> dict:
        payload = dict(cluster or {})
        evidence = cls._decoded_event_mapping(payload.get("evidence"))
        source_types = {
            str(item or "").strip().lower()
            for item in list(payload.get("source_types") or [])
            if str(item or "").strip()
        }
        source = str(evidence.get("source") or payload.get("source") or "").strip().lower()
        source_tier = str(
            evidence.get("source_tier")
            or payload.get("source_tier")
            or ""
        ).strip().lower()
        doc_uids = [
            str(item or "").strip()
            for item in list(evidence.get("source_doc_uids") or payload.get("source_doc_uids") or [])
            if str(item or "").strip()
        ]
        anchor_id = str(
            evidence.get("event_anchor_id")
            or payload.get("event_anchor_id")
            or payload.get("event_id")
            or ""
        ).strip()
        normalized_status = str(
            evidence.get("normalized_event_status")
            or payload.get("normalized_event_status")
            or ""
        ).strip().lower()
        validation_summary = dict(
            evidence.get("validation_summary")
            or payload.get("validation_summary")
            or {}
        )
        occurrence_status = str(
            evidence.get("occurrence_status")
            or payload.get("occurrence_status")
            or validation_summary.get("occurrence_status")
            or ""
        ).strip()
        alpha_confirmation_status = str(
            evidence.get("alpha_confirmation_status")
            or payload.get("alpha_confirmation_status")
            or validation_summary.get("alpha_confirmation_status")
            or ""
        ).strip()
        conflict_count = int(
            evidence.get("conflict_count")
            or payload.get("conflict_count")
            or validation_summary.get("conflict_count")
            or 0
        )
        verified_flag = bool(evidence.get("verified_event_anchor") or payload.get("verified_event_anchor"))
        official_or_institutional = source_tier in {"tier_a", "tier_b"}
        normalized_source = (
            source == "market_events_normalized"
            or "market_events_normalized" in source_types
        )
        verified = bool(
            normalized_source
            and official_or_institutional
            and verified_flag
            and anchor_id
            and doc_uids
            and normalized_status in {"", "verified"}
            and (not occurrence_status or occurrence_status.startswith("verified"))
            and alpha_confirmation_status not in {"news_only_rejected", "source_degraded", "conflicted"}
            and conflict_count <= 0
        )
        reason = None
        if not verified:
            if not normalized_source:
                reason = "not_normalized_event_source"
            elif not official_or_institutional:
                reason = "non_official_or_paid_source"
            elif not anchor_id:
                reason = "missing_event_anchor_id"
            elif not doc_uids:
                reason = "missing_source_doc_uids"
            elif normalized_status and normalized_status != "verified":
                reason = normalized_status
            elif alpha_confirmation_status == "conflicted" or conflict_count > 0:
                reason = "direction_conflict"
            elif alpha_confirmation_status in {"news_only_rejected", "source_degraded"}:
                reason = alpha_confirmation_status
            elif occurrence_status and not occurrence_status.startswith("verified"):
                reason = occurrence_status
            else:
                reason = "unverified_event_anchor"
        return {
            "verified": verified,
            "reason": reason,
            "event_anchor_id": anchor_id or None,
            "source_doc_uids": doc_uids,
            "source_tier": source_tier or "unknown",
            "source": source or "unknown",
            "source_types": sorted(source_types),
            "provider_chain": list(evidence.get("provider_chain") or payload.get("provider_chain") or []),
            "reliability_score": cls._clip_score(
                evidence.get("reliability_score") or payload.get("reliability_score"),
                default=0.0,
            ),
            "evidence_time": evidence.get("evidence_time") or payload.get("evidence_time"),
            "normalized_event_status": normalized_status or None,
            "validation_summary": validation_summary,
            "occurrence_status": occurrence_status or None,
            "alpha_confirmation_status": alpha_confirmation_status or None,
            "confidence_cap_reason": (
                evidence.get("confidence_cap_reason")
                or payload.get("confidence_cap_reason")
                or validation_summary.get("confidence_cap_reason")
            ),
            "needs_alpha_confirmation": bool(
                evidence.get("needs_alpha_confirmation")
                or payload.get("needs_alpha_confirmation")
                or alpha_confirmation_status == "single_anchor_unconfirmed"
            ),
            "conflict_count": conflict_count,
        }

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
            "diagnostic_events": [],
            "event_source_counts": {},
            "source_tier_counts": {},
            "verified_event_count": 0,
            "provisional_event_count": 0,
            "single_anchor_event_count": 0,
            "multi_source_confirmed_event_count": 0,
            "conflict_event_count": 0,
            "news_only_rejected_count": 0,
            "stale_event_count": 0,
            "post_hoc_rejected_count": 0,
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
            diagnostic_clusters = list_clusters(status="diagnostic", limit=8)
            if hasattr(diagnostic_clusters, "__await__"):
                diagnostic_clusters = await diagnostic_clusters
            clusters = [*list(clusters or []), *list(diagnostic_clusters or [])]
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
        diagnostic_events = []
        event_source_counts: Dict[str, int] = {}
        source_tier_counts: Dict[str, int] = {}
        verified_event_count = 0
        provisional_event_count = 0
        single_anchor_event_count = 0
        multi_source_confirmed_event_count = 0
        conflict_event_count = 0
        news_only_rejected_count = 0
        stale_event_count = 0
        post_hoc_rejected_count = 0

        for cluster in list(clusters or []):
            cluster = dict(cluster or {})
            event_id = str(cluster.get("event_id") or "").strip()
            if not event_id:
                continue
            anchor = cls._verified_normalized_event_anchor(cluster)
            source_key = str(anchor.get("source") or "unknown").strip().lower() or "unknown"
            tier_key = str(anchor.get("source_tier") or "unknown").strip().lower() or "unknown"
            event_source_counts[source_key] = event_source_counts.get(source_key, 0) + 1
            source_tier_counts[tier_key] = source_tier_counts.get(tier_key, 0) + 1
            status = str(anchor.get("normalized_event_status") or "").strip().lower()
            reason = str(anchor.get("reason") or "").strip().lower()
            if status in {"provisional", "degraded"}:
                provisional_event_count += 1
            alpha_status = str(anchor.get("alpha_confirmation_status") or "").strip().lower()
            if alpha_status == "single_anchor_unconfirmed":
                single_anchor_event_count += 1
            if alpha_status == "confirmed":
                multi_source_confirmed_event_count += 1
            if alpha_status == "conflicted" or int(anchor.get("conflict_count") or 0) > 0 or reason == "direction_conflict":
                conflict_event_count += 1
            if reason in {"news_only_or_low_tier_source", "non_official_or_paid_source", "news_only_rejected"}:
                news_only_rejected_count += 1
            if reason == "stale_event" or status == "stale":
                stale_event_count += 1
            if reason == "post_hoc_rejected" or status == "post_hoc_rejected":
                post_hoc_rejected_count += 1
            if not anchor.get("verified"):
                diagnostic_events.append(
                    {
                        "event_id": event_id,
                        "event_type": cluster.get("event_type"),
                        "event_name": cluster.get("event_name") or cluster.get("summary") or event_id,
                        "reason": anchor.get("reason") or "unverified_event_anchor",
                        "source_tier": anchor.get("source_tier"),
                        "source": anchor.get("source"),
                        "event_validation_summary": dict(anchor.get("validation_summary") or {}),
                        "occurrence_status": anchor.get("occurrence_status"),
                        "alpha_confirmation_status": anchor.get("alpha_confirmation_status"),
                        "confidence_cap_reason": anchor.get("confidence_cap_reason"),
                        "needs_alpha_confirmation": bool(anchor.get("needs_alpha_confirmation")),
                        "conflict_count": int(anchor.get("conflict_count") or 0),
                    }
                )
                continue
            verified_event_count += 1
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
                            "event_anchor_id": anchor.get("event_anchor_id"),
                            "source_doc_uids": list(anchor.get("source_doc_uids") or []),
                            "source_tier": anchor.get("source_tier"),
                            "reliability_score": anchor.get("reliability_score"),
                            "event_validation_summary": dict(anchor.get("validation_summary") or {}),
                            "alpha_confirmation_status": anchor.get("alpha_confirmation_status"),
                            "confidence_cap_reason": anchor.get("confidence_cap_reason"),
                            "needs_alpha_confirmation": bool(anchor.get("needs_alpha_confirmation")),
                            "conflict_count": int(anchor.get("conflict_count") or 0),
                            "verified_event_anchor": True,
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
                    "event_anchor_id": anchor.get("event_anchor_id"),
                    "source_doc_uids": list(anchor.get("source_doc_uids") or []),
                    "source_tier": anchor.get("source_tier"),
                    "source": "market_events_normalized",
                    "provider_chain": list(anchor.get("provider_chain") or []),
                    "reliability_score": anchor.get("reliability_score"),
                    "evidence_time": anchor.get("evidence_time"),
                    "verified_event_anchor": True,
                    "validation_summary": dict(anchor.get("validation_summary") or {}),
                    "occurrence_status": anchor.get("occurrence_status"),
                    "alpha_confirmation_status": anchor.get("alpha_confirmation_status"),
                    "confidence_cap_reason": anchor.get("confidence_cap_reason"),
                    "needs_alpha_confirmation": bool(anchor.get("needs_alpha_confirmation")),
                    "conflict_count": int(anchor.get("conflict_count") or 0),
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
                    "event_anchor_id": anchor.get("event_anchor_id"),
                    "source_doc_uids": list(anchor.get("source_doc_uids") or []),
                    "source_tier": anchor.get("source_tier"),
                    "source": "market_events_normalized",
                    "provider_chain": list(anchor.get("provider_chain") or []),
                    "reliability_score": anchor.get("reliability_score"),
                    "evidence_time": anchor.get("evidence_time"),
                    "verified_event_anchor": True,
                    "validation_summary": dict(anchor.get("validation_summary") or {}),
                    "occurrence_status": anchor.get("occurrence_status"),
                    "alpha_confirmation_status": anchor.get("alpha_confirmation_status"),
                    "confidence_cap_reason": anchor.get("confidence_cap_reason"),
                    "needs_alpha_confirmation": bool(anchor.get("needs_alpha_confirmation")),
                    "conflict_count": int(anchor.get("conflict_count") or 0),
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
                "diagnostic_events": diagnostic_events[:12],
                "event_source_counts": event_source_counts,
                "source_tier_counts": source_tier_counts,
                "verified_event_count": verified_event_count,
                "provisional_event_count": provisional_event_count,
                "single_anchor_event_count": single_anchor_event_count,
                "multi_source_confirmed_event_count": multi_source_confirmed_event_count,
                "conflict_event_count": conflict_event_count,
                "news_only_rejected_count": news_only_rejected_count,
                "stale_event_count": stale_event_count,
                "post_hoc_rejected_count": post_hoc_rejected_count,
            }
        )
        return payload, "success", None, {
            "enabled": True,
            "event_count": len(raw_events),
            "active_theme_count": total_themes,
            "tasks_ready_count": ready_themes,
            "verified_event_count": verified_event_count,
            "single_anchor_event_count": single_anchor_event_count,
            "multi_source_confirmed_event_count": multi_source_confirmed_event_count,
            "conflict_event_count": conflict_event_count,
            "diagnostic_event_count": len(diagnostic_events),
            "event_source_counts": event_source_counts,
            "source_tier_counts": source_tier_counts,
        }
