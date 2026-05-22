        def _safe_float(value: Any) -> float:
            try:
                return float(value or 0.0)
            except Exception:
                return 0.0

        @staticmethod
        def _normalize_code_list(values: Any, limit: int = 12) -> list[str]:
            codes: list[str] = []
            seen: set[str] = set()

            def visit(value: Any):
                if value is None:
                    return
                if isinstance(value, dict):
                    for key in ('code', 'symbol', 'stock_code'):
                        if value.get(key) is not None:
                            visit(value.get(key))
                    for key in ('codes', 'symbols', 'stock_codes', 'target_symbols'):
                        if value.get(key) is not None:
                            visit(value.get(key))
                    return
                if isinstance(value, (list, tuple, set)):
                    for item in value:
                        visit(item)
                    return
                raw = str(value or '').strip()
                if not raw:
                    return
                if any(sep in raw for sep in [',', ';', '|', '\n', '\t', ' ']):
                    normalized = raw.replace(';', ',').replace('|', ',').replace('\n', ',').replace('\t', ',').replace(' ', ',')
                    for part in normalized.split(','):
                        visit(part)
                    return
                code = raw.split('.')[0].strip()
                if not code or code in seen:
                    return
                seen.add(code)
                codes.append(code)

            visit(values)
            return codes[: max(1, min(int(limit or 12), 40))]

        @classmethod
        def _summarize_symbol_frame(cls, code: str, frame: pd.DataFrame) -> Optional[dict[str, Any]]:
            if frame is None or frame.empty or 'close' not in frame.columns:
                return None
            compact = frame.tail(min(len(frame), 120)).copy()
            close = pd.to_numeric(compact['close'], errors='coerce').dropna()
            if len(close) < 20:
                return None
            volume = pd.to_numeric(compact.get('volume'), errors='coerce').dropna() if 'volume' in compact.columns else pd.Series(dtype=float)
            sma5 = float(close.tail(5).mean())
            sma20 = float(close.tail(20).mean())
            latest = float(close.iloc[-1])
            return_5d = (latest / float(close.iloc[-6]) - 1.0) if len(close) >= 6 and float(close.iloc[-6]) else 0.0
            return_20d = (latest / float(close.iloc[-21]) - 1.0) if len(close) >= 21 and float(close.iloc[-21]) else 0.0
            volatility_20d = float(close.pct_change().tail(20).std(ddof=0) or 0.0)
            volume_ratio_20 = float(volume.tail(5).mean() / max(float(volume.tail(20).mean() or 1.0), 1.0)) if len(volume) >= 20 else 1.0
            trend_state = 'sideways'
            if latest >= sma20 and sma5 >= sma20:
                trend_state = 'uptrend'
            elif latest < sma20 and sma5 < sma20:
                trend_state = 'downtrend'
            return {
                'code': code,
                'close': round(latest, 6),
                'return_5d': round(return_5d, 6),
                'return_20d': round(return_20d, 6),
                'volatility_20d': round(volatility_20d, 6),
                'price_vs_sma20': 'above' if latest >= sma20 else 'below',
                'sma5_vs_sma20': 'above' if sma5 >= sma20 else 'below',
                'trend_state': trend_state,
                'volume_ratio_20': round(volume_ratio_20, 6),
            }

        @classmethod
        def _rank_symbol_context(cls, item: dict[str, Any]) -> float:
            score = 0.0
            score += cls._safe_float(item.get('return_20d')) * 5.0
            score += cls._safe_float(item.get('return_5d')) * 2.0
            score -= cls._safe_float(item.get('volatility_20d')) * 1.5
            if item.get('trend_state') == 'uptrend':
                score += 0.35
            if item.get('price_vs_sma20') == 'above':
                score += 0.12
            if item.get('sma5_vs_sma20') == 'above':
                score += 0.08
            score += min(max(cls._safe_float(item.get('volume_ratio_20')) - 1.0, -0.5), 0.5) * 0.3
            market_cap = cls._safe_float(item.get('market_cap'))
            if market_cap > 0:
                score += min(market_cap / 1_000_000_000_000, 0.15)
            pe_ratio = item.get('pe_ratio')
            if isinstance(pe_ratio, (int, float)) and 0 < float(pe_ratio) < 40:
                score += 0.05
            pb_ratio = item.get('pb_ratio')
            if isinstance(pb_ratio, (int, float)) and 0 < float(pb_ratio) < 8:
                score += 0.03
            financial_snapshot = dict(item.get('financial_snapshot') or {})
            if cls._safe_float(financial_snapshot.get('revenue_growth')) > 0:
                score += 0.05
            if cls._safe_float(financial_snapshot.get('profit_growth')) > 0:
                score += 0.05
            factor_snapshot = dict(item.get('factor_snapshot') or {})
            positive_factor_count = len([v for v in factor_snapshot.values() if isinstance(v, (int, float)) and float(v) > 0])
            score += min(positive_factor_count, 3) * 0.03
            return round(score, 6)

        async def _load_universe_rows(self, db) -> list[dict[str, Any]]:
            if not hasattr(db, 'list_stock_universe'):
                return []
            rows: list[dict[str, Any]] = []
            offset = 0
            while len(rows) < RESEARCH_UNIVERSE_SCAN_LIMIT:
                batch_limit = min(RESEARCH_UNIVERSE_PAGE_SIZE, RESEARCH_UNIVERSE_SCAN_LIMIT - len(rows))
                if batch_limit <= 0:
                    break
                try:
                    batch = await db.list_stock_universe(limit=batch_limit, offset=offset)
                except TypeError:
                    batch = await db.list_stock_universe(limit=batch_limit)
                except Exception:
                    break
                if not batch:
                    break
                rows.extend([dict(item or {}) for item in batch])
                offset += len(batch)
                if len(batch) < batch_limit:
                    break
            return rows

        async def _fetch_factor_snapshot(self, db, codes: list[str], snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
            if not codes or not hasattr(db, 'get_factor_values'):
                return {}
            factor_names: list[str] = []
            for payload in (dict(snapshot.get('factor_ic_trend') or {}), dict(snapshot.get('factor_ic') or {})):
                for key in payload.keys():
                    factor_name = str(key or '').strip()
                    if factor_name and factor_name not in factor_names:
                        factor_names.append(factor_name)
            factor_names = factor_names[:3]
            if not factor_names:
                return {}
            factor_snapshot: dict[str, dict[str, Any]] = {code: {} for code in codes}
            for factor_name in factor_names:
                try:
                    rows = await db.get_factor_values(codes, factor_name)
                except Exception:
                    continue
                latest_by_code: dict[str, tuple[str, float]] = {}
                for row in list(rows or []):
                    code = str((row or {}).get('stock_code') or (row or {}).get('code') or '').strip()
                    if not code:
                        continue
                    factor_date = str((row or {}).get('factor_date') or '')
                    factor_value = self._safe_float((row or {}).get('factor_value'))
                    current = latest_by_code.get(code)
                    if current is None or factor_date >= current[0]:
                        latest_by_code[code] = (factor_date, factor_value)
                for code, payload in latest_by_code.items():
                    factor_snapshot.setdefault(code, {})[factor_name] = payload[1]
            return {code: values for code, values in factor_snapshot.items() if values}

        async def build_shared_research_context(
            self,
            db,
            snapshot: Optional[dict[str, Any]],
            *,
            parent_strategies: Optional[list[dict]] = None,
            history_summary: Optional[list[dict]] = None,
        ) -> dict[str, Any]:
            base_snapshot = dict(snapshot or {})
            base_snapshot.pop('_shared_generation_context', None)
            return await self._build_research_context(
                db,
                base_snapshot,
                parent_strategies=parent_strategies,
                history_summary=history_summary,
                research_task={},
            )

        @classmethod
        def _build_market_background_context(
            cls,
            *,
            symbol_insights: Optional[list[dict[str, Any]]] = None,
            candidate_universe: Optional[list[dict[str, Any]]] = None,
            universe_scan: Optional[dict[str, Any]] = None,
            top_industries: Optional[dict[str, Any]] = None,
            cache_reused: bool = False,
        ) -> dict[str, Any]:
            symbol_insights = [dict(item or {}) for item in list(symbol_insights or [])]
            candidate_universe = [dict(item or {}) for item in list(candidate_universe or [])]
            universe_scan_payload = dict(universe_scan or {})
            return {
                'available': bool(symbol_insights or candidate_universe or universe_scan_payload or top_industries),
                'symbol_count': len(symbol_insights),
                'candidate_universe_count': len(candidate_universe),
                'symbol_insight_codes': cls._normalize_code_list(
                    [item.get('code') for item in symbol_insights],
                    limit=RESEARCH_SYMBOL_DETAIL_LIMIT,
                ),
                'candidate_universe_symbols': cls._normalize_code_list(
                    [item.get('code') for item in candidate_universe],
                    limit=RESEARCH_CANDIDATE_POOL_LIMIT,
                ),
                'total_stock_count': int(universe_scan_payload.get('total_stock_count') or 0),
                'scanned_stock_count': int(universe_scan_payload.get('scanned_stock_count') or 0),
                'data_ready_count': int(universe_scan_payload.get('data_ready_count') or 0),
                'coverage_ratio': universe_scan_payload.get('coverage_ratio'),
                'top_industries': dict(top_industries or universe_scan_payload.get('top_industries') or {}),
                'cache_reused': bool(cache_reused or universe_scan_payload.get('cache_reused')),
            }

        @classmethod
        def _build_task_target_context(
            cls,
            *,
            research_task: Optional[dict[str, Any]],
            symbol_insights: Optional[list[dict[str, Any]]] = None,
            candidate_universe: Optional[list[dict[str, Any]]] = None,
            status: str,
            blocked_by_target_universe: bool = False,
        ) -> dict[str, Any]:
            task = normalize_research_task_contract(research_task or {})
            symbol_insights = [dict(item or {}) for item in list(symbol_insights or [])]
            candidate_universe = [dict(item or {}) for item in list(candidate_universe or [])]
            requested_target_symbols = cls._normalize_code_list(task.get('target_symbols'))
            target_symbol_set = set(requested_target_symbols)
            matched_target_symbols = cls._normalize_code_list(
                [
                    item.get('code')
                    for item in [*symbol_insights, *candidate_universe]
                    if str(item.get('code') or '').strip() in target_symbol_set
                ],
                limit=RESEARCH_CANDIDATE_POOL_LIMIT,
            )
            return {
                'targeted_task': bool(requested_target_symbols),
                'status': str(status or 'broad_market_context'),
                'blocked_by_target_universe': bool(blocked_by_target_universe),
                'requested_target_symbols': requested_target_symbols,
                'matched_target_symbols': matched_target_symbols,
                'focus_industries': [
                    str(item).strip()
                    for item in list(task.get('focus_industries') or [])
                    if str(item).strip()
                ],
                'focus_markets': [
                    str(item).strip()
                    for item in list(task.get('focus_markets') or [])
                    if str(item).strip()
                ],
                'symbol_count': len(symbol_insights),
                'candidate_universe_count': len(candidate_universe),
                'symbol_insight_codes': cls._normalize_code_list(
                    [item.get('code') for item in symbol_insights],
                    limit=RESEARCH_SYMBOL_DETAIL_LIMIT,
                ),
                'candidate_universe_symbols': cls._normalize_code_list(
                    [item.get('code') for item in candidate_universe],
                    limit=RESEARCH_CANDIDATE_POOL_LIMIT,
                ),
            }

        @classmethod
        def _build_blocked_research_context(
            cls,
            *,
            snapshot: dict[str, Any],
            research_task: Optional[dict[str, Any]],
            parent_strategies: Optional[list[dict]] = None,
            history_summary: Optional[list[dict]] = None,
            universe_total_count: int = 0,
            top_industries: Optional[dict[str, Any]] = None,
            market_background_context: Optional[dict[str, Any]] = None,
            cache_reused: bool = False,
        ) -> dict[str, Any]:
            task = normalize_research_task_contract(research_task or {})
            market_regime = {
                'fg_level': snapshot.get('fg_level'),
                'fear_greed_index': snapshot.get('fear_greed_index'),
                'hot_sectors': list(snapshot.get('hot_sectors') or [])[:4],
                'cold_sectors': list(snapshot.get('cold_sectors') or [])[:3],
                'factor_ic': dict(snapshot.get('factor_ic') or {}),
                'factor_ic_trend': dict(snapshot.get('factor_ic_trend') or {}),
                'factor_research': dict(snapshot.get('factor_research') or {}),
            }
            task_target_context = cls._build_task_target_context(
                research_task=task,
                symbol_insights=[],
                candidate_universe=[],
                status='blocked_by_target_universe',
                blocked_by_target_universe=True,
            )
            background_context = dict(
                market_background_context
                or cls._build_market_background_context(
                    universe_scan={
                        'total_stock_count': universe_total_count,
                        'scanned_stock_count': 0,
                        'data_ready_count': 0,
                        'coverage_ratio': 0.0,
                        'cache_reused': cache_reused,
                    },
                    top_industries=top_industries,
                    cache_reused=cache_reused,
                )
            )
            top_categories = {
                str(key): int(value)
                for key, value in sorted(
                    dict(snapshot.get('category_counts') or {}).items(),
                    key=lambda item: item[1],
                    reverse=True,
                )[:5]
            }
            return {
                'research_task': {
                    'task_id': task.get('task_id'),
                    'theme': task.get('theme'),
                    'opportunity_type': task.get('opportunity_type'),
                    'focus_industries': list(task.get('focus_industries') or []),
                    'focus_markets': list(task.get('focus_markets') or []),
                    'target_symbols': list(task.get('target_symbols') or []),
                    'priority': task.get('priority'),
                    'strategy_preferences': list(task.get('strategy_preferences') or []),
                    'generation_limit': task.get('generation_limit'),
                    'rationale': task.get('rationale'),
                    'task_source': task.get('task_source'),
                },
                'market_regime': market_regime,
                'market_breadth': {
                    'symbol_count': 0,
                    'trend_up_count': 0,
                    'trend_down_count': 0,
                    'avg_return_20d': 0.0,
                    'avg_volatility_20d': 0.0,
                },
                'symbol_insights': [],
                'candidate_universe': [],
                'symbol_insight_codes': [],
                'candidate_universe_symbols': [],
                'target_context_status': 'blocked_by_target_universe',
                'blocked_by_target_universe': True,
                'task_target_context': task_target_context,
                'market_background_context': background_context,
                'universe_scan': {
                    'total_stock_count': universe_total_count,
                    'scanned_stock_count': 0,
                    'data_ready_count': 0,
                    'coverage_ratio': 0.0,
                    'detail_symbol_count': 0,
                    'candidate_universe_count': 0,
                    'top_industries': dict(top_industries or {}),
                    'cache_reused': bool(cache_reused),
                },
                'selection_framework': {
                    'technical': ['trend_state', 'return_20d', 'return_5d', 'volume_ratio_20', 'price_vs_sma20'],
                    'fundamental': ['market_cap', 'pe_ratio', 'pb_ratio', 'revenue_growth', 'profit_growth'],
                    'factor_names': [
                        str(key)
                        for key in list(
                            ((snapshot.get('factor_research') or {}).get('summary') or {}).get('top_factor_names')
                            or (snapshot.get('factor_research') or {}).get('active_factors')
                            or list((snapshot.get('factor_ic_trend') or {}).keys())[:3]
                        )[:3]
                    ],
                },
                'analysis_scope': {
                    'scan_mode': 'target_context_blocked',
                    'scan_limit': RESEARCH_UNIVERSE_SCAN_LIMIT,
                    'kline_scan_limit': RESEARCH_KLINE_SCAN_LIMIT,
                    'detail_limit': RESEARCH_SYMBOL_DETAIL_LIMIT,
                    'candidate_pool_limit': RESEARCH_CANDIDATE_POOL_LIMIT,
                },
                'population_state': {
                    'listed_count': int(snapshot.get('listed_count') or universe_total_count or 0),
                    'incubating_count': int(snapshot.get('incubating_count') or 0),
                    'top_categories': top_categories,
                },
                'parent_context': [
                    {
                        'id': item.get('id'),
                        'name': item.get('name'),
                        'strategy_type': item.get('strategy_type'),
                        'status': item.get('status'),
                    }
                    for item in list(parent_strategies or [])[:3]
                ],
                'experiment_feedback': [
                    {
                        'generator_type': item.get('generator_type'),
                        'status': item.get('status'),
                        'decision': item.get('decision'),
                        'final_score': item.get('final_score'),
                    }
                    for item in list(history_summary or [])[:4]
                ],
            }
