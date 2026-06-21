
    async def record_metrics(self, db, strategy: dict, metric_date: Optional[date] = None) -> Optional[dict]:
        metric_date = metric_date or date.today()
        binding = await self.ensure_account(db, strategy)
        account = binding['account']
        account_id = account['id']

        nav_rows_method = _get_async_db_method(db, 'get_paper_nav_rows')
        if nav_rows_method is not None:
            nav_rows = await nav_rows_method(account_id, limit=60)
            order_summary = await db.get_paper_order_summary(account_id)
        else:
            async with db.acquire() as conn:
                nav_rows = [dict(row) for row in await conn.fetch(
                    "SELECT * FROM paper_nav WHERE account_id=$1 ORDER BY nav_date DESC LIMIT 60",
                    account_id,
                )]
                summary = await conn.fetchrow(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN status IN ('pending','submitted') THEN 1 ELSE 0 END), 0) AS total_orders,
                        COALESCE(SUM(CASE WHEN status = 'filled' THEN 1 ELSE 0 END), 0) AS filled_orders
                    FROM paper_orders
                    WHERE account_id=$1
                    """,
                    account_id,
                )
                trade_summary = await conn.fetchrow(
                    "SELECT COALESCE(COUNT(*), 0) AS total_trades, COALESCE(SUM(amount), 0) AS trade_amount FROM paper_trades WHERE account_id=$1",
                    account_id,
                )
                order_summary = {
                    'total_orders': int((summary or {}).get('total_orders') or 0),
                    'filled_orders': int((summary or {}).get('filled_orders') or 0),
                    'total_trades': int((trade_summary or {}).get('total_trades') or 0),
                    'trade_amount': float((trade_summary or {}).get('trade_amount') or 0.0),
                }

        latest_nav = nav_rows[0] if nav_rows else None
        total_value = float((latest_nav or {}).get('total_value') or account.get('total_value') or account.get('initial_capital') or DEFAULT_INCUBATION_CAPITAL)
        cash = float((latest_nav or {}).get('cash') or account.get('current_capital') or 0.0)
        market_value = float((latest_nav or {}).get('market_value') or max(total_value - cash, 0.0))
        daily_return = float((latest_nav or {}).get('daily_return') or 0.0)

        nav_values = [float(row.get('total_value') or 0) for row in reversed(nav_rows)]
        peak = nav_values[0] if nav_values else total_value
        max_drawdown = 0.0
        for value in nav_values:
            peak = max(peak, value)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - value) / peak)

        returns = [float(row.get('daily_return') or 0) for row in nav_rows if row.get('daily_return') is not None]
        # Fix #9: 至少需要 20 个数据点才能计算有统计意义的 Sharpe
        if len(returns) >= 20:
            mean_r = sum(returns) / len(returns)
            variance = sum((item - mean_r) ** 2 for item in returns) / max(len(returns) - 1, 1)
            std_r = variance ** 0.5
            sharpe_ratio = (mean_r / std_r) * (252 ** 0.5) if std_r > 0 else 0.0
        else:
            sharpe_ratio = 0.0

        signal_stats = await db.get_signal_stats(strategy['id'])
        hit_rate_5d = float((signal_stats.get('hit_rate') or {}).get(5, (signal_stats.get('hit_rate') or {}).get('5', 0)) or 0)
        forward_ic_5d = float((signal_stats.get('forward_ic') or {}).get(5, (signal_stats.get('forward_ic') or {}).get('5', 0)) or 0)
        forward_sharpe_5d = float((signal_stats.get('forward_sharpe') or {}).get(5, (signal_stats.get('forward_sharpe') or {}).get('5', 0)) or 0)
        total_signals = int(signal_stats.get('total_signals') or 0)

        metrics = await db.get_strategy_metrics(strategy['id'])
        backtest = next((item for item in metrics if item.get('period') in ('all', 'backtest')), {})
        baseline_sharpe = float(backtest.get('sharpe_ratio') or 0)
        baseline_mdd = abs(float(backtest.get('max_drawdown') or 0))
        alpha_decay = max(0.0, baseline_sharpe - max(forward_sharpe_5d, 0.0))
        drift_score = (abs(max_drawdown - baseline_mdd) + abs(baseline_sharpe - forward_sharpe_5d)) / 2 if baseline_sharpe or baseline_mdd else 0.0
        exposure_rate = (market_value / total_value) if total_value > 0 else 0.0
        turnover_rate = float(order_summary.get('trade_amount') or 0.0) / total_value if total_value > 0 else 0.0

        from .strategy_lifecycle_shared import build_incubation_overview as _build_incubation_overview
        overview = await _build_incubation_overview(db, strategy)
        signal_quality = dict(overview.get('signal_quality') or {})
        execution_quality = dict(overview.get('execution_quality') or {})
        signal_quality_5d = dict((signal_quality.get('by_horizon') or {}).get('5') or {})
        overview_without_signal_quality = dict(overview)
        overview_without_signal_quality.pop('signal_quality', None)
        overview_without_signal_quality.pop('execution_quality', None)
        decision = 'promote' if overview.get('promotion_ready') else ('observe' if not overview.get('deprecation_risk') else 'halt')
        open_risk_count = 0
        if hasattr(db, 'list_strategy_runtime_risk_events'):
            open_risks = await db.list_strategy_runtime_risk_events(
                strategy_id=str(strategy['id']),
                status='open',
                limit=20,
            )
            open_risk_count = len(list(open_risks or []))
        derived_stage = self._derive_incubation_stage(overview, open_risk_count=open_risk_count)

        metric = await db.save_strategy_incubation_metric(strategy['id'], metric_date, {
            'account_id': account_id,
            # Fix #12: 使用完整的 6 阶段映射替代二元分类
            'stage': derived_stage,
            'total_value': round(total_value, 4),
            'cash': round(cash, 4),
            'market_value': round(market_value, 4),
            'nav': round(total_value / max(float(account.get('initial_capital') or DEFAULT_INCUBATION_CAPITAL), 1.0), 6),
            'daily_return': round(daily_return, 6),
            'max_drawdown': round(max_drawdown, 6),
            'sharpe_ratio': round(sharpe_ratio, 6),
            'hit_rate_5d': round(hit_rate_5d, 6),
            'hit_rate_lcb_5d': round(float(signal_quality_5d.get('hit_rate_lcb') or 0.0), 6) if signal_quality_5d.get('hit_rate_lcb') is not None else None,
            'skill_lcb_5d': round(float(signal_quality_5d.get('skill_lcb') or 0.0), 6) if signal_quality_5d.get('skill_lcb') is not None else None,
            'effective_n_5d': int(signal_quality_5d.get('effective_n') or 0) if signal_quality_5d.get('effective_n') is not None else None,
            'recent_hit_rate_5d': round(float(signal_quality_5d.get('recent_hit_rate') or 0.0), 6) if signal_quality_5d.get('recent_hit_rate') is not None else None,
            'recent_skill_lcb_5d': round(float(signal_quality_5d.get('recent_skill_lcb') or 0.0), 6) if signal_quality_5d.get('recent_skill_lcb') is not None else None,
            'stability_gap_5d': round(float(signal_quality_5d.get('stability_gap') or 0.0), 6) if signal_quality_5d.get('stability_gap') is not None else None,
            'forward_ic_5d': round(forward_ic_5d, 6),
            'forward_sharpe_5d': round(forward_sharpe_5d, 6),
            'total_signals': total_signals,
            'total_orders': int(order_summary.get('total_orders') or 0),
            'total_trades': int(order_summary.get('total_trades') or 0),
            'turnover_rate': round(turnover_rate, 6),
            'exposure_rate': round(exposure_rate, 6),
            'alpha_decay': round(alpha_decay, 6),
            'drift_score': round(drift_score, 6),
            'blockers': overview.get('blockers') or [],
            'risk_flags': overview.get('risk_flags') or [],
            'decision': decision,
            'metadata': {
                'overview': overview_without_signal_quality,
                'signal_quality': signal_quality,
                'execution_quality': execution_quality,
                'binding_created': bool(binding.get('created')),
                'open_risk_count': open_risk_count,
            },
        })
        update_account_status_method = _get_async_db_method(db, 'update_paper_account_status')
        if update_account_status_method is not None:
            await update_account_status_method(
                account_id,
                'active',
                stage=metric.get('stage') or 'warmup',
                promotion_candidate=bool(overview.get('promotion_ready')),
            )
        await self._record_domain_event(
            db,
            strategy['id'],
            'incubation.metric_recorded',
            {
                'account_id': account_id,
                'metric_date': str(metric_date),
                'decision': metric.get('decision'),
                'stage': metric.get('stage'),
                'nav': metric.get('nav'),
                'promotion_candidate': bool(overview.get('promotion_ready')),
            },
            correlation_id=str(metric_date),
        )
        return metric

    async def process_strategies(self, db, strategies: list[dict], signal_date: Optional[date] = None) -> dict:
        signal_date = signal_date or date.today()
        accounts_bound = 0
        orders_created = 0
        orders_filled = 0
        rejected_orders = 0
        nav_snapshots = 0
        metrics_recorded = 0
        skip_reason_counts: dict[str, int] = {}
        items = []
        for strategy in strategies:
            try:
                ensure = await self.ensure_account(db, strategy)
                accounts_bound += 1 if ensure.get('created') else 0
                sync_result = await self.sync_signals_to_orders(db, strategy, signal_date)
                settle_result = await self.settle_orders(db, strategy, signal_date)
                metric = await self.record_metrics(db, strategy, signal_date)
                orders_created += int(sync_result.get('created_count') or 0)
                orders_filled += int(settle_result.get('filled_count') or 0)
                rejected_orders += int(settle_result.get('rejected_count') or 0)
                nav_snapshots += 1 if settle_result.get('nav_snapshot') else 0
                metrics_recorded += 1 if metric else 0
                for reason, count in dict(sync_result.get('skip_reason_counts') or {}).items():
                    token = str(reason or 'unknown').strip() or 'unknown'
                    skip_reason_counts[token] = int(skip_reason_counts.get(token) or 0) + int(count or 0)
                items.append({
                    'strategy_id': strategy.get('id'),
                    'account_id': (ensure.get('account') or {}).get('id'),
                    'orders_created': sync_result.get('created_count', 0),
                    'orders_skipped': sync_result.get('skipped_count', 0),
                    'skip_reason_counts': dict(sync_result.get('skip_reason_counts') or {}),
                    'orders_filled': settle_result.get('filled_count', 0),
                    'rejected_orders': settle_result.get('rejected_count', 0),
                    'nav': (settle_result.get('nav_snapshot') or {}).get('total_value'),
                    'decision': (metric or {}).get('decision'),
                })
            except Exception as exc:
                logger.warning('StrategyIncubationService.process_strategies failed for %s: %s', strategy.get('id'), exc)
                items.append({'strategy_id': strategy.get('id'), 'error': str(exc)})
        return {
            'count': len(strategies),
            'accounts_bound': accounts_bound,
            'orders_created': orders_created,
            'orders_filled': orders_filled,
            'rejected_orders': rejected_orders,
            'skip_reason_counts': dict(skip_reason_counts),
            'nav_snapshots': nav_snapshots,
            'metrics_recorded': metrics_recorded,
            'items': items,
        }

    async def _resolve_replay_dates(
        self,
        db,
        strategy: dict,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        include_market_days: bool = True,
        max_dates: int = 1500,
    ) -> list[date]:
        strategy_id = str(strategy.get('id') or '').strip()
        if not strategy_id:
            return []

        resolved_start = start_date
        resolved_end = end_date
        signal_rows = await db.get_signals(
            strategy_id,
            start_date=start_date,
            end_date=end_date,
            limit=max(1000, int(max_dates or 1500) * 20),
        )
        signal_dates = sorted(
            {
                item.get('signal_date')
                for item in list(signal_rows or [])
                if isinstance(item.get('signal_date'), date)
            }
        )
        if signal_dates and resolved_start is None:
            resolved_start = signal_dates[0]
        if signal_dates and resolved_end is None:
            resolved_end = max(signal_dates[-1], date.today())
        if resolved_start is None:
            resolved_start = date.today()
        if resolved_end is None:
            resolved_end = max(resolved_start, date.today())
        if resolved_end < resolved_start:
            resolved_end = resolved_start

        replay_dates: set[date] = set(signal_dates)
        if include_market_days and hasattr(db, 'get_klines'):
            candidate_codes = list(_resolve_strategy_target_codes(strategy))
            if not candidate_codes:
                candidate_codes = list(
                    {
                        str(item.get('code') or '').strip()
                        for item in list(signal_rows or [])
                        if str(item.get('code') or '').strip()
                    }
                )
            for code in candidate_codes[:3]:
                try:
                    klines = await db.get_klines(
                        code,
                        start_date=str(resolved_start),
                        end_date=str(resolved_end),
                    )
                except Exception as exc:
                    logger.warning(
                        'StrategyIncubationService._resolve_replay_dates kline lookup failed for %s/%s: %s',
                        strategy_id,
                        code,
                        exc,
                    )
                    continue
                kline_dates = []
                for row in list(klines or []):
                    trade_date = row.get('date')
                    if isinstance(trade_date, str):
                        try:
                            trade_date = date.fromisoformat(trade_date[:10])
                        except Exception:
                            trade_date = None
                    if isinstance(trade_date, date):
                        kline_dates.append(trade_date)
                if kline_dates:
                    replay_dates.update(kline_dates)
                    break

        ordered = sorted(
            trade_date
            for trade_date in replay_dates
            if isinstance(trade_date, date) and resolved_start <= trade_date <= resolved_end
        )
        if max_dates and len(ordered) > int(max_dates):
            ordered = ordered[-int(max_dates):]
        return ordered

    async def replay_strategy_history(
        self,
        db,
        strategy: dict,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        include_market_days: bool = True,
        max_dates: int = 1500,
        force_close_open_positions: bool = False,
        run_acceptance: bool = True,
    ) -> dict:
        strategy_id = str(strategy.get('id') or '').strip()
        replay_dates = await self._resolve_replay_dates(
            db,
            strategy,
            start_date=start_date,
            end_date=end_date,
            include_market_days=include_market_days,
            max_dates=max_dates,
        )
        replayed_days = 0
        orders_created = 0
        orders_filled = 0
        rejected_orders = 0
        metrics_recorded = 0
        non_empty_days = 0
        last_day_result = None
        daily_results: list[dict] = []

        for replay_date in replay_dates:
            day_result = await self.process_strategies(
                db,
                [strategy],
                signal_date=replay_date,
            )
            replayed_days += 1
            orders_created += int(day_result.get('orders_created') or 0)
            orders_filled += int(day_result.get('orders_filled') or 0)
            rejected_orders += int(day_result.get('rejected_orders') or 0)
            metrics_recorded += int(day_result.get('metrics_recorded') or 0)
            if any(
                int(day_result.get(key) or 0) > 0
                for key in ('orders_created', 'orders_filled', 'rejected_orders')
            ):
                non_empty_days += 1
            daily_results.append(
                {
                    'signal_date': str(replay_date),
                    'orders_created': int(day_result.get('orders_created') or 0),
                    'orders_filled': int(day_result.get('orders_filled') or 0),
                    'rejected_orders': int(day_result.get('rejected_orders') or 0),
                    'metrics_recorded': int(day_result.get('metrics_recorded') or 0),
                }
            )
            last_day_result = day_result

        if force_close_open_positions and replay_dates:
            close_result = await self.force_close_open_positions(
                db,
                strategy,
                replay_dates[-1],
            )
            created_count = int(close_result.get('created_count') or 0)
            if created_count > 0:
                settle_result = await self.settle_orders(db, strategy, replay_dates[-1])
                metric = await self.record_metrics(db, strategy, replay_dates[-1])
                orders_created += created_count
                orders_filled += int(settle_result.get('filled_count') or 0)
                rejected_orders += int(settle_result.get('rejected_count') or 0)
                metrics_recorded += 1 if metric else 0
                non_empty_days += 1
                last_day_result = {
                    'count': 1,
                    'accounts_bound': 0,
                    'orders_created': created_count,
                    'orders_filled': int(settle_result.get('filled_count') or 0),
                    'rejected_orders': int(settle_result.get('rejected_count') or 0),
                    'nav_snapshots': 1 if settle_result.get('nav_snapshot') else 0,
                    'metrics_recorded': 1 if metric else 0,
                    'items': [
                        {
                            'strategy_id': strategy.get('id'),
                            'forced_window_close': True,
                            'reason': close_result.get('reason'),
                            'orders_created': created_count,
                            'orders_filled': int(settle_result.get('filled_count') or 0),
                            'rejected_orders': int(settle_result.get('rejected_count') or 0),
                        }
                    ],
                }
                daily_results.append(
                    {
                        'signal_date': str(replay_dates[-1]),
                        'orders_created': created_count,
                        'orders_filled': int(settle_result.get('filled_count') or 0),
                        'rejected_orders': int(settle_result.get('rejected_count') or 0),
                        'metrics_recorded': 1 if metric else 0,
                        'window_force_close': True,
                        'reason': close_result.get('reason'),
                    }
                )

        acceptance = None
        if run_acceptance and hasattr(db, 'run_execution_audit_acceptance'):
            acceptance = await db.run_execution_audit_acceptance(
                strategy_id=strategy_id,
                backfill=True,
            )

        return {
            'strategy_id': strategy_id,
            'replayed_days': replayed_days,
            'non_empty_days': non_empty_days,
            'orders_created': orders_created,
            'orders_filled': orders_filled,
            'rejected_orders': rejected_orders,
            'metrics_recorded': metrics_recorded,
            'start_date': str(replay_dates[0]) if replay_dates else None,
            'end_date': str(replay_dates[-1]) if replay_dates else None,
            'daily_results': daily_results,
            'last_day_result': last_day_result,
            'acceptance': acceptance,
        }

    async def replay_strategies_history(
        self,
        db,
        strategies: list[dict],
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        include_market_days: bool = True,
        max_dates: int = 1500,
        force_close_open_positions: bool = False,
        run_acceptance: bool = True,
    ) -> dict:
        items = []
        replayed_days = 0
        non_empty_days = 0
        orders_created = 0
        orders_filled = 0
        rejected_orders = 0
        metrics_recorded = 0
        acceptance_status_counts: dict[str, int] = {}
        execution_audit_gate_status_counts: dict[str, int] = {}
        execution_hard_gate_passed_count = 0
        acceptance_overall_ready_count = 0
        acceptance_sample_gap_count = 0
        acceptance_realized_trade_count_total = 0

        def _count(target: dict[str, int], value: object, *, default: str = "missing") -> None:
            key = str(value or "").strip() or default
            target[key] = target.get(key, 0) + 1

        def _acceptance_has_sample_gap(payload: dict) -> bool:
            if "sample_gap" in {str(item or "").strip() for item in list(payload.get("gap_categories") or [])}:
                return True
            for detail in list(payload.get("blocker_details") or []):
                if isinstance(detail, dict) and str(detail.get("category") or "").strip() == "sample_gap":
                    return True
            return False

        for strategy in list(strategies or []):
            try:
                result = await self.replay_strategy_history(
                    db,
                    strategy,
                    start_date=start_date,
                    end_date=end_date,
                    include_market_days=include_market_days,
                    max_dates=max_dates,
                    force_close_open_positions=force_close_open_positions,
                    run_acceptance=run_acceptance,
                )
            except Exception as exc:
                logger.warning(
                    'StrategyIncubationService.replay_strategies_history failed for %s: %s',
                    strategy.get('id'),
                    exc,
                )
                result = {
                    'strategy_id': strategy.get('id'),
                    'error': str(exc),
                    'replayed_days': 0,
                    'non_empty_days': 0,
                    'orders_created': 0,
                    'orders_filled': 0,
                    'rejected_orders': 0,
                    'metrics_recorded': 0,
                }
            items.append(result)
            replayed_days += int(result.get('replayed_days') or 0)
            non_empty_days += int(result.get('non_empty_days') or 0)
            orders_created += int(result.get('orders_created') or 0)
            orders_filled += int(result.get('orders_filled') or 0)
            rejected_orders += int(result.get('rejected_orders') or 0)
            metrics_recorded += int(result.get('metrics_recorded') or 0)
            acceptance = result.get('acceptance')
            if isinstance(acceptance, dict):
                _count(acceptance_status_counts, acceptance.get('status'))
                trade_audit_summary = dict(acceptance.get('trade_audit_summary') or {})
                gate_status = (
                    str(acceptance.get('execution_audit_gate_status') or '').strip()
                    or str(trade_audit_summary.get('execution_audit_gate_status') or '').strip()
                    or 'missing'
                )
                _count(execution_audit_gate_status_counts, gate_status)
                acceptance_matrix = dict(acceptance.get('acceptance_matrix') or {})
                if bool(acceptance_matrix.get('overall_ready')) or str(acceptance.get('status') or '') == 'ready':
                    acceptance_overall_ready_count += 1
                if bool(acceptance.get('execution_hard_gate_passed')):
                    execution_hard_gate_passed_count += 1
                if _acceptance_has_sample_gap(acceptance):
                    acceptance_sample_gap_count += 1
                acceptance_realized_trade_count_total += int(trade_audit_summary.get('realized_trade_count') or 0)
        return {
            'count': len(list(strategies or [])),
            'replayed_days': replayed_days,
            'non_empty_days': non_empty_days,
            'orders_created': orders_created,
            'orders_filled': orders_filled,
            'rejected_orders': rejected_orders,
            'metrics_recorded': metrics_recorded,
            'acceptance_status_counts': acceptance_status_counts,
            'execution_audit_gate_status_counts': execution_audit_gate_status_counts,
            'execution_hard_gate_passed_count': execution_hard_gate_passed_count,
            'acceptance_overall_ready_count': acceptance_overall_ready_count,
            'acceptance_sample_gap_count': acceptance_sample_gap_count,
            'acceptance_realized_trade_count_total': acceptance_realized_trade_count_total,
            'items': items,
        }
