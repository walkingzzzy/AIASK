
        @classmethod
        def _compact_research_context(cls, research_context: Optional[dict[str, Any]], compact_level: int = 0) -> dict[str, Any]:
            context = dict(research_context or {})
            structured_blocks = cls._compact_structured_research_context_blocks(
                context,
                compact_level=compact_level,
            )
            market_regime = dict(context.get("market_regime") or {})
            market_breadth = dict(context.get("market_breadth") or {})
            symbol_limit = 4 if compact_level <= 0 else (2 if compact_level == 1 else 1)
            candidate_limit = 8 if compact_level <= 0 else (4 if compact_level == 1 else 2)
            symbols = list(context.get("symbol_insights") or [])[:symbol_limit]
            candidate_universe = list(context.get("candidate_universe") or [])[:candidate_limit]
            population_state = dict(context.get("population_state") or {})
            universe_scan = dict(context.get("universe_scan") or {})
            analysis_scope = dict(context.get("analysis_scope") or {})
            selection_framework = dict(context.get("selection_framework") or {})
            task_target_context = cls._compact_task_target_context(
                context,
                compact_level=compact_level,
                symbol_limit=symbol_limit,
                candidate_limit=candidate_limit,
            )
            targeted_task = bool(task_target_context.get("targeted_task"))
            market_background_context = cls._compact_market_background_context(
                context,
                compact_level=compact_level,
                symbol_limit=symbol_limit,
                candidate_limit=candidate_limit,
                targeted_task=targeted_task,
            )
            primary_symbol_codes_source = (
                task_target_context.get("symbol_insight_codes")
                if targeted_task
                else market_background_context.get("symbol_insight_codes")
            )
            primary_candidate_codes_source = (
                task_target_context.get("candidate_universe_symbols")
                if targeted_task
                else market_background_context.get("candidate_universe_symbols")
            )
            primary_symbol_codes = list(primary_symbol_codes_source or [])
            primary_candidate_codes = list(primary_candidate_codes_source or [])
            if compact_level >= 2:
                payload = {
                    "target_context_status": context.get("target_context_status") or task_target_context.get("status"),
                    "blocked_by_target_universe": bool(context.get("blocked_by_target_universe")),
                    "market_regime": {
                        "fg_level": market_regime.get("fg_level"),
                        "fear_greed_index": cls._round_number(market_regime.get("fear_greed_index"), digits=4),
                    },
                    "task_target_context": task_target_context,
                    "market_background_context": market_background_context,
                    "candidate_universe_symbols": primary_candidate_codes[:4],
                    "symbol_insight_codes": primary_symbol_codes[:2],
                }
                return {
                    key: value
                    for key, value in {**payload, **structured_blocks}.items()
                    if value not in (None, [], {}, "")
                }
            payload = {
                "target_context_status": context.get("target_context_status") or task_target_context.get("status"),
                "blocked_by_target_universe": bool(context.get("blocked_by_target_universe")),
                "market_regime": {
                    "fg_level": market_regime.get("fg_level"),
                    "fear_greed_index": cls._round_number(market_regime.get("fear_greed_index"), digits=4),
                    "hot_sectors": list(market_regime.get("hot_sectors") or [])[: max(2, 4 - compact_level)],
                    "cold_sectors": list(market_regime.get("cold_sectors") or [])[: max(1, 3 - compact_level)],
                    "factor_ic_trend": dict(list((market_regime.get("factor_ic_trend") or {}).items())[: max(2, 4 - compact_level)]),
                },
                "market_breadth": {
                    "symbol_count": market_breadth.get("symbol_count"),
                    "trend_up_count": market_breadth.get("trend_up_count"),
                    "trend_down_count": market_breadth.get("trend_down_count"),
                    "avg_return_20d": cls._round_number(market_breadth.get("avg_return_20d"), digits=4),
                    "avg_volatility_20d": cls._round_number(market_breadth.get("avg_volatility_20d"), digits=4),
                },
                "symbol_insights": [cls._compact_symbol_insight(item, compact_level=compact_level) for item in symbols],
                "candidate_universe": [cls._compact_candidate_universe_item(item, compact_level=compact_level) for item in candidate_universe],
                "symbol_insight_codes": primary_symbol_codes,
                "candidate_universe_symbols": primary_candidate_codes,
                "task_target_context": task_target_context,
                "market_background_context": market_background_context,
                "universe_scan": {
                    "total_stock_count": universe_scan.get("total_stock_count"),
                    "scanned_stock_count": universe_scan.get("scanned_stock_count"),
                    "data_ready_count": universe_scan.get("data_ready_count"),
                    "coverage_ratio": cls._round_number(universe_scan.get("coverage_ratio"), digits=4),
                    "candidate_universe_count": universe_scan.get("candidate_universe_count"),
                    "top_industries": dict(list((universe_scan.get("top_industries") or {}).items())[: max(2, 6 - compact_level)]),
                },
                "analysis_scope": {
                    "scan_mode": analysis_scope.get("scan_mode"),
                    "scan_limit": analysis_scope.get("scan_limit"),
                    "kline_scan_limit": analysis_scope.get("kline_scan_limit"),
                    "detail_limit": analysis_scope.get("detail_limit"),
                    "candidate_pool_limit": analysis_scope.get("candidate_pool_limit"),
                },
                "selection_framework": {
                    "technical": list(selection_framework.get("technical") or [])[:4],
                    "fundamental": list(selection_framework.get("fundamental") or [])[:4],
                    "factor_names": list(selection_framework.get("factor_names") or [])[:3],
                },
                "population_state": {
                    "listed_count": population_state.get("listed_count"),
                    "incubating_count": population_state.get("incubating_count"),
                    "top_categories": dict(list((population_state.get("top_categories") or {}).items())[: max(2, 5 - compact_level)]),
                },
            }
            return {
                key: value
                for key, value in {**payload, **structured_blocks}.items()
                if value not in (None, [], {}, "")
            }

        @classmethod
        def _compact_market_summary(cls, market_summary: Optional[dict[str, Any]], compact_level: int = 0) -> dict[str, Any]:
            summary = dict(market_summary or {})
            if compact_level < 2:
                return summary
            payload = {"rows": summary.get("rows")}
            close = dict(summary.get("close") or {})
            if close:
                payload["close"] = {
                    "latest": cls._round_number(close.get("latest"), digits=4),
                    "period_return_20": cls._round_number(close.get("period_return_20"), digits=4),
                    "volatility_20": cls._round_number(close.get("volatility_20"), digits=4),
                }
            volume = dict(summary.get("volume") or {})
            if volume:
                payload["volume"] = {
                    "latest": cls._round_number(volume.get("latest"), digits=4),
                    "mean_20": cls._round_number(volume.get("mean_20"), digits=4),
                }
            return payload

        @classmethod
        def _compact_research_task(cls, research_task: Optional[dict[str, Any]], compact_level: int = 0) -> dict[str, Any]:
            task = normalize_research_task_contract(research_task)
            target_alignment_contract = dict(task.get("target_alignment_contract") or {})
            compact = {
                "task_id": task.get("task_id"),
                "task_source": task.get("task_source"),
                "opportunity_type": task.get("opportunity_type"),
                "target_symbols": list(task.get("target_symbols") or [])[:5],
                "preferred_strategy_types": list(task.get("preferred_strategy_types") or [])[:4],
                "allowed_strategy_types": list(task.get("allowed_strategy_types") or [])[:6],
                "target_symbol_policy": task.get("target_symbol_policy"),
                "universe_expansion_policy": task.get("universe_expansion_policy"),
                "preference_strength": task.get("preference_strength"),
                "validation_focus": task.get("validation_focus"),
            }
            is_event_driven_task = any(task.get(key) not in (None, "", [], {}) for key in ("event_id", "theme_code", "direction", "horizon"))
            if is_event_driven_task:
                compact.update({
                    "event_id": task.get("event_id"),
                    "event_type": task.get("event_type"),
                    "theme": task.get("theme"),
                    "theme_code": task.get("theme_code"),
                    "direction": task.get("direction"),
                    "horizon": task.get("horizon"),
                    "event_window": dict(task.get("event_window") or {}),
                    "estimation_window": dict(task.get("estimation_window") or {}),
                    "holding_window": dict(task.get("holding_window") or {}),
                })
            if compact_level <= 1:
                compact["target_alignment_contract"] = {
                    key: target_alignment_contract.get(key)
                    for key in (
                        "profile",
                        "max_candidate_target_symbols",
                        "min_coverage_ratio",
                        "min_intersection_ratio",
                        "min_required_overlap_count",
                    )
                    if target_alignment_contract.get(key) not in (None, "", [], {})
                }
                compact["theme"] = task.get("theme") or compact.get("theme")
                if task.get("stock_pool"):
                    compact["stock_pool"] = task.get("stock_pool")
                if task.get("selection_logic"):
                    compact["selection_logic"] = list(task.get("selection_logic") or [])[:3]
                if task.get("focus_industries"):
                    compact["focus_industries"] = list(task.get("focus_industries") or [])[:3]
                evidence_bundle = dict(task.get("evidence_bundle") or {})
                if evidence_bundle:
                    compact["evidence_summary"] = {
                        "event_summary": cls._compact_text(evidence_bundle.get("event_summary") or task.get("event_summary"), limit=120),
                        "theme_name": evidence_bundle.get("theme_name") or task.get("theme"),
                        "direction": evidence_bundle.get("direction") or task.get("direction"),
                        "horizon": evidence_bundle.get("horizon") or task.get("horizon"),
                        "signal_count": evidence_bundle.get("signal_count"),
                        "top_symbols": cls._normalize_code_list([
                            evidence_bundle.get("target_symbols"),
                            ((evidence_bundle.get("score_summary") or {}).get("top_symbols") if isinstance(evidence_bundle.get("score_summary"), dict) else None),
                        ], limit=4),
                        "supporting_reasons": [
                            cls._compact_text(item, limit=72)
                            for item in list(evidence_bundle.get("supporting_reasons") or [])[:3]
                        ],
                        "score_summary": dict(evidence_bundle.get("score_summary") or {}),
                    }
            if compact_level >= 2:
                compact = {
                    key: compact.get(key)
                    for key in ("task_id", "opportunity_type", "target_symbols")
                    if compact.get(key) not in (None, [], {}, "")
                }
            return {key: value for key, value in compact.items() if value not in (None, [], {}, "")}

        @staticmethod
        def _prompt_target_symbol_rule(task: Optional[dict[str, Any]]) -> str:
            policy = str((task or {}).get("target_symbol_policy") or "").strip().lower()
            if policy == "strict_intersection":
                return "strict_intersection_with_research_task"
            if policy == "prefer_intersection":
                return "prefer_intersection_with_research_task"
            return policy or "prefer_intersection_with_research_task"
