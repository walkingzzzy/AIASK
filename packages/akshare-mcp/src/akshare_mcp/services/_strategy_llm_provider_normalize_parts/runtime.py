
        @classmethod
        def _sanitize_condition_for_candidate(cls, node: Any) -> dict[str, Any]:
            if not isinstance(node, dict):
                return {}
            if 'all' in node:
                return {'all': [cls._sanitize_condition_for_candidate(item) for item in list(node.get('all') or []) if cls._sanitize_condition_for_candidate(item)]}
            if 'any' in node:
                return {'any': [cls._sanitize_condition_for_candidate(item) for item in list(node.get('any') or []) if cls._sanitize_condition_for_candidate(item)]}
            if 'not' in node:
                child = cls._sanitize_condition_for_candidate(node.get('not'))
                return {'not': child} if child else {}
            op = str(node.get('op') or '').strip().lower()
            left = cls._sanitize_expr_for_candidate(node.get('left') or {})
            right = cls._sanitize_expr_for_candidate(node.get('right') or {})
            left_indicator = str(left.get('indicator') or '').strip().lower()
            right_indicator = str(right.get('indicator') or '').strip().lower()
            if left_indicator == 'volume_ratio' and 'value' not in right and right_indicator != 'volume_ratio':
                right = {'value': 1.0}
            elif left_indicator == 'rsi' and 'value' not in right and right_indicator != 'rsi':
                right = {'value': 60.0 if op in {'gt', 'gte', 'cross_above'} else 40.0}
            elif left_indicator == 'roc' and 'value' not in right and right_indicator != 'roc':
                right = {'value': 0.01 if op in {'gt', 'gte', 'cross_above'} else -0.01}
            elif left_indicator == 'zscore' and 'value' not in right and right_indicator != 'zscore':
                right = {'value': 0.5 if op in {'gt', 'gte', 'cross_above'} else -0.5}
            return {'op': op, 'left': left, 'right': right}

        @classmethod
        def _sanitize_dsl_for_candidate(cls, dsl: dict[str, Any]) -> dict[str, Any]:
            payload = dict(dsl or {})
            payload['entry'] = cls._sanitize_condition_for_candidate(payload.get('entry'))
            payload['exit'] = cls._sanitize_condition_for_candidate(payload.get('exit'))
            return payload

        @staticmethod
        def _summarize_market_frame(frame: Optional[pd.DataFrame]) -> dict[str, Any]:
            if frame is None or frame.empty:
                return {"rows": 0}
            compact = frame.tail(min(len(frame), 120)).copy()
            result = {"rows": int(len(compact)), "columns": [str(col) for col in compact.columns.tolist()]}
            if "close" in compact.columns:
                close = pd.to_numeric(compact["close"], errors="coerce").dropna()
                if len(close) >= 2:
                    result["close"] = {
                        "latest": float(close.iloc[-1]),
                        "period_return_20": float(close.iloc[-1] / max(close.iloc[max(0, len(close) - 20)], 1e-9) - 1.0) if len(close) >= 20 else float(close.iloc[-1] / max(close.iloc[0], 1e-9) - 1.0),
                        "period_return_full": float(close.iloc[-1] / max(close.iloc[0], 1e-9) - 1.0),
                        "volatility_20": float(close.pct_change().dropna().tail(20).std() if len(close) > 20 else close.pct_change().dropna().std() or 0.0),
                    }
            if "volume" in compact.columns:
                volume = pd.to_numeric(compact["volume"], errors="coerce").dropna()
                if len(volume) >= 5:
                    result["volume"] = {
                        "latest": float(volume.iloc[-1]),
                        "mean_20": float(volume.tail(20).mean()),
                    }
            return result

        @staticmethod
        def _normalize_limit(limit: int) -> int:
            return max(1, min(int(limit or 3), 8))

        @staticmethod
        def _prompt_profile_name(compact_level: int) -> str:
            if compact_level <= 0:
                return "normal"
            if compact_level == 1:
                return "compact"
            return "minimal"

        @classmethod
        def _compact_snapshot(cls, snapshot: dict[str, Any], compact_level: int = 0) -> dict[str, Any]:
            payload: dict[str, Any] = {}
            for key in (
                "date",
                "fear_greed_index",
                "fg_level",
                "listed_count",
                "incubating_count",
                "degraded",
                "margin_5d_change_pct",
                "north_fund_3d_net",
                "factor_ic",
                "factor_ic_trend",
            ):
                if key in snapshot and snapshot.get(key) is not None:
                    payload[key] = cls._round_number(snapshot.get(key), digits=4)

            hot_limit = 4 if compact_level <= 0 else 2
            cold_limit = 3 if compact_level <= 0 else 2
            if snapshot.get("hot_sectors"):
                payload["hot_sectors"] = [str(item) for item in list(snapshot.get("hot_sectors") or [])[:hot_limit]]
            if snapshot.get("cold_sectors"):
                payload["cold_sectors"] = [str(item) for item in list(snapshot.get("cold_sectors") or [])[:cold_limit]]

            category_counts = snapshot.get("category_counts") or {}
            if isinstance(category_counts, dict) and category_counts:
                sorted_items = sorted(category_counts.items(), key=lambda item: item[1], reverse=True)
                payload["category_counts"] = {str(key): int(value) for key, value in sorted_items[: max(2, 5 - compact_level)]}

            completeness = dict(snapshot.get("completeness") or {})
            if completeness:
                payload["data_quality"] = {
                    "completion_ratio": cls._round_number(completeness.get("completion_ratio") or 0.0, digits=4),
                    "missing_sources": [
                        str(item) for item in list(completeness.get("missing_sources") or [])[: max(1, 3 - min(compact_level, 2))]
                    ],
                }

            failure_reasons = list(snapshot.get("failure_reasons") or [])
            if failure_reasons:
                payload["failure_reasons"] = [
                    {
                        "source": str((item or {}).get("source") or ""),
                        "reason": str((item or {}).get("reason") or ""),
                    }
                    for item in failure_reasons[: max(1, 2 - min(compact_level, 1))]
                ]
            return payload

        @classmethod
        def _compact_parent_strategies(cls, parent_strategies: list[dict[str, Any]], compact_level: int = 0) -> list[dict[str, Any]]:
            rows = []
            for item in list(parent_strategies or [])[: max(1, 3 - min(compact_level, 1))]:
                rows.append({
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "strategy_type": item.get("strategy_type"),
                    "status": item.get("status"),
                    "tags": list(item.get("tags") or [])[: max(1, 3 - compact_level)],
                })
            return rows

        @classmethod
        def _compact_history_summary(cls, history_summary: list[dict[str, Any]], compact_level: int = 0) -> list[dict[str, Any]]:
            rows = []
            for item in list(history_summary or [])[: max(2, 6 - compact_level * 2)]:
                payload = {
                    "parent_strategy_id": item.get("parent_strategy_id"),
                    "generator_type": item.get("generator_type"),
                    "status": item.get("status"),
                    "decision": item.get("decision"),
                    "final_score": cls._round_number(item.get("final_score"), digits=4),
                }
                if item.get("family_hint") not in (None, "", [], {}):
                    payload["family_hint"] = item.get("family_hint")
                if item.get("validation_focus") not in (None, "", [], {}):
                    payload["validation_focus"] = item.get("validation_focus")
                if item.get("replay_ready") is not None:
                    payload["replay_ready"] = bool(item.get("replay_ready"))
                target_symbols = list(item.get("target_symbols") or [])
                if target_symbols:
                    payload["target_symbols"] = target_symbols[: max(1, 4 - compact_level)]
                rows.append(payload)
            return rows

        @classmethod
        def _compact_symbol_insight(cls, item: dict[str, Any], compact_level: int = 0) -> dict[str, Any]:
            payload = {
                "code": item.get("code"),
                "name": item.get("name"),
                "industry": item.get("industry"),
                "close": cls._round_number(item.get("close"), digits=4),
                "return_20d": cls._round_number(item.get("return_20d"), digits=4),
                "trend_state": item.get("trend_state"),
            }
            if compact_level <= 1:
                payload["return_5d"] = cls._round_number(item.get("return_5d"), digits=4)
                payload["volume_ratio_20"] = cls._round_number(item.get("volume_ratio_20"), digits=4)
            if compact_level == 0:
                payload["volatility_20d"] = cls._round_number(item.get("volatility_20d"), digits=4)
                payload["price_vs_sma20"] = item.get("price_vs_sma20")
            return payload

        @classmethod
        def _compact_candidate_universe_item(cls, item: dict[str, Any], compact_level: int = 0) -> dict[str, Any]:
            payload = {
                "code": item.get("code"),
                "name": item.get("name"),
                "industry": item.get("industry"),
                "return_20d": cls._round_number(item.get("return_20d"), digits=4),
                "trend_state": item.get("trend_state"),
                "volume_ratio_20": cls._round_number(item.get("volume_ratio_20"), digits=4),
                "screen_score": cls._round_number(item.get("screen_score"), digits=4),
            }
            if compact_level == 0:
                payload["market_cap"] = cls._round_number(item.get("market_cap"), digits=4)
                payload["pe_ratio"] = cls._round_number(item.get("pe_ratio"), digits=4)
                payload["pb_ratio"] = cls._round_number(item.get("pb_ratio"), digits=4)
                payload["factor_snapshot"] = {str(key): cls._round_number(value, digits=4) for key, value in dict(item.get("factor_snapshot") or {}).items()}
                payload["financial_snapshot"] = {
                    "revenue_growth": cls._round_number((item.get("financial_snapshot") or {}).get("revenue_growth"), digits=4),
                    "profit_growth": cls._round_number((item.get("financial_snapshot") or {}).get("profit_growth"), digits=4),
                    "roe": cls._round_number((item.get("financial_snapshot") or {}).get("roe"), digits=4),
                }
            elif compact_level == 1:
                factor_snapshot = dict(item.get("factor_snapshot") or {})
                if factor_snapshot:
                    top_factor_items = list(factor_snapshot.items())[:3]
                    payload["factor_snapshot"] = {str(key): cls._round_number(value, digits=4) for key, value in top_factor_items}
            return payload

        @classmethod
        def _compact_task_target_context(
            cls,
            context: dict[str, Any],
            *,
            compact_level: int,
            symbol_limit: int,
            candidate_limit: int,
        ) -> dict[str, Any]:
            task_target_context = dict(context.get("task_target_context") or {})
            research_task = dict(context.get("research_task") or {})
            requested_target_symbols = cls._normalize_code_list([
                task_target_context.get("requested_target_symbols"),
                research_task.get("target_symbols"),
            ], limit=8)
            target_symbol_set = set(requested_target_symbols)
            raw_symbols = [dict(item or {}) for item in list(context.get("symbol_insights") or [])]
            raw_candidates = [dict(item or {}) for item in list(context.get("candidate_universe") or [])]
            compact_symbols = [dict(item or {}) for item in list(task_target_context.get("symbol_insights") or [])]
            compact_candidates = [dict(item or {}) for item in list(task_target_context.get("candidate_universe") or [])]
            if target_symbol_set:
                filtered_symbols = [item for item in raw_symbols if str(item.get("code") or "").strip() in target_symbol_set]
                filtered_candidates = [item for item in raw_candidates if str(item.get("code") or "").strip() in target_symbol_set]
            else:
                filtered_symbols = raw_symbols
                filtered_candidates = raw_candidates
            effective_symbols = filtered_symbols or compact_symbols
            effective_candidates = filtered_candidates or compact_candidates
            matched_target_symbols = cls._normalize_code_list([
                task_target_context.get("matched_target_symbols"),
                [
                    item.get("code")
                    for item in [*effective_symbols, *effective_candidates]
                    if str(item.get("code") or "").strip()
                ],
            ], limit=8)
            compact_payload = {
                "targeted_task": bool(task_target_context.get("targeted_task") or requested_target_symbols),
                "status": task_target_context.get("status") or context.get("target_context_status"),
                "blocked_by_target_universe": bool(
                    task_target_context.get("blocked_by_target_universe")
                    or context.get("blocked_by_target_universe")
                ),
                "requested_target_symbols": requested_target_symbols,
                "matched_target_symbols": matched_target_symbols,
                "symbol_count": int(task_target_context.get("symbol_count") or len(effective_symbols)),
                "candidate_universe_count": int(task_target_context.get("candidate_universe_count") or len(effective_candidates)),
                "symbol_insight_codes": cls._normalize_code_list([
                    task_target_context.get("symbol_insight_codes"),
                    [item.get("code") for item in effective_symbols],
                ], limit=max(2, symbol_limit)),
                "candidate_universe_symbols": cls._normalize_code_list([
                    task_target_context.get("candidate_universe_symbols"),
                    [item.get("code") for item in effective_candidates],
                ], limit=max(2, candidate_limit)),
            }
            if compact_level >= 2:
                return {
                    key: value
                    for key, value in compact_payload.items()
                    if value not in (None, [], {}, "")
                }
            compact_payload["symbol_insights"] = [
                cls._compact_symbol_insight(item, compact_level=compact_level)
                for item in effective_symbols[:symbol_limit]
            ]
            compact_payload["candidate_universe"] = [
                cls._compact_candidate_universe_item(item, compact_level=compact_level)
                for item in effective_candidates[:candidate_limit]
            ]
            return {
                key: value
                for key, value in compact_payload.items()
                if value not in (None, [], {}, "")
            }

        @classmethod
        def _compact_market_background_context(
            cls,
            context: dict[str, Any],
            *,
            compact_level: int,
            symbol_limit: int,
            candidate_limit: int,
            targeted_task: bool,
        ) -> dict[str, Any]:
            market_background_context = dict(context.get("market_background_context") or {})
            raw_symbols = [dict(item or {}) for item in list(market_background_context.get("symbol_insights") or [])]
            raw_candidates = [dict(item or {}) for item in list(market_background_context.get("candidate_universe") or [])]
            if not raw_symbols and not targeted_task:
                raw_symbols = [dict(item or {}) for item in list(context.get("symbol_insights") or [])]
            if not raw_candidates and not targeted_task:
                raw_candidates = [dict(item or {}) for item in list(context.get("candidate_universe") or [])]
            compact_payload = {
                "available": bool(
                    market_background_context.get("available")
                    or raw_symbols
                    or raw_candidates
                    or market_background_context
                ),
                "symbol_count": int(market_background_context.get("symbol_count") or len(raw_symbols)),
                "candidate_universe_count": int(
                    market_background_context.get("candidate_universe_count") or len(raw_candidates)
                ),
                "symbol_insight_codes": cls._normalize_code_list([
                    market_background_context.get("symbol_insight_codes"),
                    [item.get("code") for item in raw_symbols],
                ], limit=max(2, symbol_limit)),
                "candidate_universe_symbols": cls._normalize_code_list([
                    market_background_context.get("candidate_universe_symbols"),
                    [item.get("code") for item in raw_candidates],
                ], limit=max(2, candidate_limit)),
                "total_stock_count": market_background_context.get("total_stock_count"),
                "scanned_stock_count": market_background_context.get("scanned_stock_count"),
                "data_ready_count": market_background_context.get("data_ready_count"),
                "coverage_ratio": cls._round_number(market_background_context.get("coverage_ratio"), digits=4),
                "top_industries": dict(list((market_background_context.get("top_industries") or {}).items())[:4]),
                "cache_reused": bool(market_background_context.get("cache_reused")),
            }
            if compact_level >= 2:
                return {
                    key: value
                    for key, value in compact_payload.items()
                    if value not in (None, [], {}, "")
                }
            compact_payload["symbol_insights"] = [
                cls._compact_symbol_insight(item, compact_level=compact_level)
                for item in raw_symbols[:symbol_limit]
            ]
            compact_payload["candidate_universe"] = [
                cls._compact_candidate_universe_item(item, compact_level=compact_level)
                for item in raw_candidates[:candidate_limit]
            ]
            return {
                key: value
                for key, value in compact_payload.items()
                if value not in (None, [], {}, "")
            }

        @classmethod
        def _compact_structured_research_value(cls, value: Any, *, compact_level: int) -> Any:
            list_limit = 8 if compact_level <= 0 else (4 if compact_level == 1 else 2)
            dict_limit = 16 if compact_level <= 0 else (10 if compact_level == 1 else 6)
            if isinstance(value, dict):
                compacted: dict[str, Any] = {}
                for index, (key, item) in enumerate(value.items()):
                    if index >= dict_limit:
                        break
                    compact_item = cls._compact_structured_research_value(item, compact_level=compact_level)
                    if compact_item in (None, [], {}, ""):
                        continue
                    compacted[str(key)] = compact_item
                return compacted
            if isinstance(value, list):
                compacted_items = [
                    cls._compact_structured_research_value(item, compact_level=compact_level)
                    for item in value[:list_limit]
                ]
                return [item for item in compacted_items if item not in (None, [], {}, "")]
            if isinstance(value, float):
                return cls._round_number(value, digits=4)
            return value

        @classmethod
        def _compact_structured_research_context_blocks(
            cls,
            context: dict[str, Any],
            *,
            compact_level: int,
        ) -> dict[str, Any]:
            compacted: dict[str, Any] = {}
            for block_key in (
                "strategy_context",
                "backtest_summary",
                "regime_panel",
                "capacity_panel",
                "generalization_seed",
            ):
                block_value = context.get(block_key)
                if block_value in (None, [], {}, ""):
                    continue
                compacted[block_key] = cls._compact_structured_research_value(
                    block_value,
                    compact_level=compact_level,
                )
            return compacted
