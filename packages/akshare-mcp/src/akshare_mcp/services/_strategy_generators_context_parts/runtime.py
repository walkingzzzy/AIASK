
        async def _build_research_context(
            self,
            db,
            snapshot: Optional[dict[str, Any]],
            *,
            parent_strategies: Optional[list[dict]] = None,
            history_summary: Optional[list[dict]] = None,
            research_task: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            snapshot = snapshot or {}
            research_task = normalize_research_task_contract(research_task or {})
            shared_generation_context = dict(snapshot.get('_shared_generation_context') or {})
            shared_research_context = dict(shared_generation_context.get('research_context') or {})
            if shared_research_context:
                reused_context = self._reuse_shared_research_context(
                    shared_research_context,
                    snapshot=snapshot,
                    parent_strategies=parent_strategies,
                    history_summary=history_summary,
                    research_task=research_task,
                )
                if reused_context is not None:
                    return reused_context
            universe_rows = await self._load_universe_rows(db)
            universe_total_count = 0
            if hasattr(db, 'count_stock_universe'):
                try:
                    universe_total_count = int(await db.count_stock_universe())
                except Exception:
                    universe_total_count = 0
            if universe_total_count <= 0:
                universe_total_count = len(universe_rows)

            # PR-S23: 当 research_task.target_symbols 命中的股票不在
            # 默认按市值排序的前 RESEARCH_UNIVERSE_SCAN_LIMIT 名 universe 内时
            # （例如 BULK 矩阵抽中的 market_cap NULL 中小盘股），by-code 直接
            # 把它们补进 universe_rows，避免 _build_research_context 走
            # _build_blocked_research_context 把整条 LLM 路径 short-circuit 掉。
            task_target_symbols_preview = self._normalize_code_list(
                (research_task or {}).get('target_symbols')
            )
            if task_target_symbols_preview and hasattr(db, 'list_stocks_by_codes'):
                existing_codes = {
                    str((row or {}).get('code') or '').strip()
                    for row in universe_rows
                }
                missing_codes = [
                    code for code in task_target_symbols_preview
                    if code and code not in existing_codes
                ]
                if missing_codes:
                    try:
                        extra_rows = await db.list_stocks_by_codes(missing_codes)
                    except Exception:
                        extra_rows = []
                    if extra_rows:
                        universe_rows = list(universe_rows) + [
                            dict(item or {}) for item in extra_rows
                        ]

            breadth_rows: list[dict[str, Any]] = []
            symbol_insights: list[dict[str, Any]] = []
            candidate_universe: list[dict[str, Any]] = []
            task_target_symbols = self._normalize_code_list(research_task.get('target_symbols'))
            task_focus_industries = [str(item).strip() for item in list(research_task.get('focus_industries') or []) if str(item).strip()]
            task_focus_markets = [str(item).strip() for item in list(research_task.get('focus_markets') or []) if str(item).strip()]
            has_market_filters = bool(task_focus_industries or task_focus_markets)
            filtered_rows = list(universe_rows)
            top_industries: dict[str, int] = {}
            if universe_rows:
                industry_counts: dict[str, int] = {}
                for row in universe_rows:
                    industry = str((row or {}).get('industry') or (row or {}).get('sector') or '未分类').strip() or '未分类'
                    industry_counts[industry] = industry_counts.get(industry, 0) + 1
                top_industries = {
                    str(key): int(value)
                    for key, value in sorted(industry_counts.items(), key=lambda item: item[1], reverse=True)[:8]
                }
            if task_target_symbols:
                target_set = set(task_target_symbols)
                targeted = [row for row in filtered_rows if str((row or {}).get('code') or "").strip() in target_set]
                if not targeted:
                    return self._build_blocked_research_context(
                        snapshot=snapshot,
                        research_task=research_task,
                        parent_strategies=parent_strategies,
                        history_summary=history_summary,
                        universe_total_count=universe_total_count,
                        top_industries=top_industries,
                        cache_reused=False,
                    )
                filtered_rows = targeted
            elif task_focus_industries:
                industry_filtered = [
                    row for row in filtered_rows
                    if any(keyword in str((row or {}).get('industry') or (row or {}).get('sector') or "") for keyword in task_focus_industries)
                ]
                if industry_filtered:
                    filtered_rows = industry_filtered
            if task_focus_markets:
                market_filtered = [row for row in filtered_rows if str((row or {}).get('market') or "").strip() in set(task_focus_markets)]
                if market_filtered:
                    filtered_rows = market_filtered
            if task_target_symbols and not filtered_rows:
                return self._build_blocked_research_context(
                    snapshot=snapshot,
                    research_task=research_task,
                    parent_strategies=parent_strategies,
                    history_summary=history_summary,
                    universe_total_count=universe_total_count,
                    top_industries=top_industries,
                    cache_reused=False,
                )
            scan_rows = list(filtered_rows[: min(len(filtered_rows), RESEARCH_KLINE_SCAN_LIMIT)])

            for row in scan_rows:
                code = str((row or {}).get('code') or '').strip()
                if not code:
                    continue
                try:
                    klines = await db.get_klines(code, limit=180)
                except Exception:
                    klines = []
                if not klines:
                    continue
                frame = pd.DataFrame(klines)
                summary = self._summarize_symbol_frame(code, frame)
                if summary is None:
                    continue
                enriched = {
                    **dict(row or {}),
                    **summary,
                    'name': (row or {}).get('name') or code,
                    'industry': (row or {}).get('industry') or (row or {}).get('sector'),
                    'sector': (row or {}).get('sector') or (row or {}).get('industry'),
                    'market_cap': (row or {}).get('market_cap'),
                    'pe_ratio': (row or {}).get('pe_ratio'),
                    'pb_ratio': (row or {}).get('pb_ratio'),
                }
                breadth_rows.append(enriched)
            if breadth_rows:
                symbol_insights = [dict(item) for item in breadth_rows[:RESEARCH_SYMBOL_DETAIL_LIMIT]]
                scored = []
                for item in breadth_rows:
                    ranked = dict(item)
                    ranked['screen_score'] = self._rank_symbol_context(ranked)
                    scored.append(ranked)
                scored.sort(key=lambda item: (self._safe_float(item.get('screen_score')), self._safe_float(item.get('market_cap'))), reverse=True)
                candidate_universe = [dict(item) for item in scored[:RESEARCH_CANDIDATE_POOL_LIMIT]]
                candidate_codes = [str(item.get('code') or '') for item in candidate_universe if str(item.get('code') or '').strip()]
                factor_snapshot = await self._fetch_factor_snapshot(db, candidate_codes, snapshot)
                for item in candidate_universe[:RESEARCH_FINANCIAL_DETAIL_LIMIT]:
                    if hasattr(db, 'get_financials'):
                        try:
                            financials = await db.get_financials(item['code'], limit=1)
                        except Exception:
                            financials = []
                        item['financial_snapshot'] = dict((financials or [None])[0] or {})
                for item in candidate_universe:
                    item['factor_snapshot'] = dict(factor_snapshot.get(str(item.get('code') or '')) or {})
                    item['screen_score'] = self._rank_symbol_context(item)
                candidate_universe.sort(key=lambda item: (self._safe_float(item.get('screen_score')), self._safe_float(item.get('market_cap'))), reverse=True)

            if task_target_symbols and not symbol_insights and not candidate_universe:
                return self._build_blocked_research_context(
                    snapshot=snapshot,
                    research_task=research_task,
                    parent_strategies=parent_strategies,
                    history_summary=history_summary,
                    universe_total_count=universe_total_count,
                    top_industries=top_industries,
                    cache_reused=False,
                )

            if not symbol_insights and not task_target_symbols:
                for code in DEFAULT_CODES:
                    try:
                        klines = await db.get_klines(code, limit=180)
                    except Exception:
                        klines = []
                    if not klines:
                        continue
                    frame = pd.DataFrame(klines)
                    summary = self._summarize_symbol_frame(code, frame)
                    if summary is not None:
                        symbol_insights.append(summary)
                candidate_universe = [dict(item, screen_score=self._rank_symbol_context(item)) for item in symbol_insights[: min(len(symbol_insights), RESEARCH_CANDIDATE_POOL_LIMIT)]]

            trend_up_count = len([item for item in symbol_insights if item.get('trend_state') == 'uptrend'])
            trend_down_count = len([item for item in symbol_insights if item.get('trend_state') == 'downtrend'])
            avg_return_20d = round(sum(self._safe_float(item.get('return_20d')) for item in symbol_insights) / max(len(symbol_insights), 1), 6) if symbol_insights else 0.0
            avg_volatility_20d = round(sum(self._safe_float(item.get('volatility_20d')) for item in symbol_insights) / max(len(symbol_insights), 1), 6) if symbol_insights else 0.0
            category_counts = dict(snapshot.get('category_counts') or {})
            top_categories = {
                str(key): int(value)
                for key, value in sorted(category_counts.items(), key=lambda item: item[1], reverse=True)[:5]
            }
            scanned_stock_count = len(universe_rows) if universe_rows else len(symbol_insights)
            data_ready_count = len(breadth_rows) if breadth_rows else len(symbol_insights)
            coverage_ratio = round(scanned_stock_count / max(universe_total_count, 1), 6) if universe_total_count else 0.0
            target_context_status = (
                'targeted_active'
                if task_target_symbols
                else ('filtered_market_context' if has_market_filters else 'broad_market_context')
            )
            task_target_context = self._build_task_target_context(
                research_task=research_task,
                symbol_insights=symbol_insights,
                candidate_universe=candidate_universe,
                status=target_context_status,
            )
            market_background_context = self._build_market_background_context(
                symbol_insights=symbol_insights if not task_target_symbols else [],
                candidate_universe=candidate_universe if not task_target_symbols else [],
                universe_scan={
                    'total_stock_count': universe_total_count,
                    'scanned_stock_count': scanned_stock_count,
                    'data_ready_count': data_ready_count,
                    'coverage_ratio': coverage_ratio,
                    'cache_reused': False,
                },
                top_industries=top_industries,
                cache_reused=False,
            )
            return {
                'research_task': {
                    'task_id': research_task.get('task_id'),
                    'theme': research_task.get('theme'),
                    'opportunity_type': research_task.get('opportunity_type'),
                    'focus_industries': task_focus_industries,
                    'focus_markets': task_focus_markets,
                    'target_symbols': task_target_symbols,
                    'priority': research_task.get('priority'),
                    'strategy_preferences': list(research_task.get('strategy_preferences') or []),
                    'generation_limit': research_task.get('generation_limit'),
                    'rationale': research_task.get('rationale'),
                    'task_source': research_task.get('task_source'),
                },
                'market_regime': {
                    'fg_level': snapshot.get('fg_level'),
                    'fear_greed_index': snapshot.get('fear_greed_index'),
                    'hot_sectors': list(snapshot.get('hot_sectors') or [])[:4],
                    'cold_sectors': list(snapshot.get('cold_sectors') or [])[:3],
                    'factor_ic': dict(snapshot.get('factor_ic') or {}),
                    'factor_ic_trend': dict(snapshot.get('factor_ic_trend') or {}),
                    'factor_research': dict(snapshot.get('factor_research') or {}),
                },
                'market_breadth': {
                    'symbol_count': len(symbol_insights),
                    'trend_up_count': trend_up_count,
                    'trend_down_count': trend_down_count,
                    'avg_return_20d': avg_return_20d,
                    'avg_volatility_20d': avg_volatility_20d,
                },
                'symbol_insights': symbol_insights,
                'candidate_universe': candidate_universe,
                'symbol_insight_codes': list(task_target_context.get('symbol_insight_codes') or []),
                'candidate_universe_symbols': list(task_target_context.get('candidate_universe_symbols') or []),
                'target_context_status': target_context_status,
                'blocked_by_target_universe': False,
                'task_target_context': task_target_context,
                'market_background_context': market_background_context,
                'universe_scan': {
                    'total_stock_count': universe_total_count,
                    'scanned_stock_count': scanned_stock_count,
                    'data_ready_count': data_ready_count,
                    'coverage_ratio': coverage_ratio,
                    'detail_symbol_count': len(symbol_insights),
                    'candidate_universe_count': len(candidate_universe),
                    'top_industries': top_industries,
                    'cache_reused': False,
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
                    'scan_mode': (
                        'target_context_only'
                        if task_target_symbols
                        else (
                            'filtered_universe_scan_with_focused_detail'
                            if has_market_filters
                            else 'broad_universe_scan_with_focused_detail'
                        )
                    ),
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

        @staticmethod
        def _summarize_research_context(context: Optional[dict[str, Any]]) -> dict[str, Any]:
            payload = dict(context or {})
            breadth = dict(payload.get('market_breadth') or {})
            regime = dict(payload.get('market_regime') or {})
            universe_scan = dict(payload.get('universe_scan') or {})
            candidate_universe = list(payload.get('candidate_universe') or [])
            task_target_context = dict(payload.get('task_target_context') or {})
            market_background_context = dict(payload.get('market_background_context') or {})
            blocked_by_target_universe = bool(payload.get('blocked_by_target_universe'))
            task_targeted = bool(task_target_context.get('targeted_task'))
            context_mode = (
                'blocked_target_context'
                if blocked_by_target_universe
                else ('target_only' if task_targeted else 'broad_market')
            )
            return {
                'context_mode': context_mode,
                'symbol_count': int(breadth.get('symbol_count') or 0),
                'trend_up_count': int(breadth.get('trend_up_count') or 0),
                'trend_down_count': int(breadth.get('trend_down_count') or 0),
                'avg_return_20d': breadth.get('avg_return_20d'),
                'avg_volatility_20d': breadth.get('avg_volatility_20d'),
                'candidate_universe_count': len(candidate_universe),
                'candidate_codes': [str((item or {}).get('code') or '') for item in candidate_universe[:5]],
                'universe_total_count': int(universe_scan.get('total_stock_count') or 0),
                'universe_scanned_count': int(universe_scan.get('scanned_stock_count') or 0),
                'data_ready_count': int(universe_scan.get('data_ready_count') or 0),
                'coverage_ratio': universe_scan.get('coverage_ratio'),
                'cache_reused': bool(universe_scan.get('cache_reused')),
                'fg_level': regime.get('fg_level'),
                'fear_greed_index': regime.get('fear_greed_index'),
                'hot_sectors': list(regime.get('hot_sectors') or [])[:3],
                'cold_sectors': list(regime.get('cold_sectors') or [])[:2],
                'target_context_status': payload.get('target_context_status'),
                'blocked_by_target_universe': blocked_by_target_universe,
                'task_targeted': task_targeted,
                'task_target_symbol_count': len(list(task_target_context.get('requested_target_symbols') or [])),
                'task_target_matched_count': len(list(task_target_context.get('matched_target_symbols') or [])),
                'target_context_symbol_count': int(task_target_context.get('symbol_count') or 0),
                'target_context_candidate_count': int(task_target_context.get('candidate_universe_count') or 0),
                'market_background_available': bool(market_background_context.get('available')),
                'market_background_symbol_count': int(market_background_context.get('symbol_count') or 0),
                'market_background_candidate_count': int(market_background_context.get('candidate_universe_count') or 0),
            }
