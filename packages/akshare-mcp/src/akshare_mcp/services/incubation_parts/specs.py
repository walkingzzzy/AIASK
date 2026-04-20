
    async def sync_signals_to_orders(self, db, strategy: dict, signal_date: date) -> dict:
        ensure = await self.ensure_account(db, strategy)
        account = ensure['account']
        account_id = account['id']
        runtime_playbook = _runtime_playbook_for_strategy(strategy)
        entry_policy = dict(runtime_playbook.get("entry_policy") or {})
        exit_policy = dict(runtime_playbook.get("exit_policy") or {})
        adverse_move_policy = dict(runtime_playbook.get("adverse_move_policy") or {})
        reentry_policy = dict(runtime_playbook.get("reentry_policy") or {})
        position_policy = dict(runtime_playbook.get("position_policy") or {})
        execution_guard = _runtime_execution_guard(strategy)
        signals = await db.get_signals(strategy['id'], start_date=signal_date, end_date=signal_date, limit=200)
        allowed_codes = _resolve_strategy_target_codes(strategy)
        if allowed_codes:
            signals = [
                item for item in list(signals or [])
                if str((item or {}).get('code') or '').strip() in allowed_codes
            ]
        list_orders_method = _get_async_db_method(db, 'list_strategy_paper_orders')
        if list_orders_method is not None:
            existing_orders = await list_orders_method(strategy['id'], signal_date)
        else:
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM paper_orders WHERE strategy_id=$1 AND signal_date=$2",
                    strategy['id'], signal_date,
                )
            existing_orders = [dict(row) for row in rows]
        existing_keys = {(row.get('code'), row.get('direction')) for row in existing_orders}
        created = []
        skipped = 0
        blocked_by_execution_guard = 0

        current_capital = float(account.get('current_capital') or account.get('initial_capital') or DEFAULT_INCUBATION_CAPITAL)
        total_value = float(account.get('total_value') or current_capital or DEFAULT_INCUBATION_CAPITAL)
        base_budget_pct = max(0.01, _safe_float(position_policy.get("base_budget_pct"), 0.12))
        max_position_pct = max(0.02, _safe_float(position_policy.get("max_position_pct"), 0.25))
        max_concurrent_positions = max(1, _safe_int(position_policy.get("max_concurrent_positions"), 2))
        order_style = str(entry_policy.get("order_style") or "limit").strip().lower() or "limit"
        max_slippage_bps = max(0.0, _safe_float(entry_policy.get("max_slippage_bps"), 0.0))
        cooldown_days = max(0, _safe_int(reentry_policy.get("cooldown_days"), 0))
        initial_stop_loss_pct = max(0.0, _safe_float(exit_policy.get("initial_stop_loss_pct"), 0.0))
        time_stop_days = max(0, _safe_int(exit_policy.get("time_stop_days"), 0))
        loss_bands = sorted(
            [
                dict(item or {})
                for item in list(adverse_move_policy.get("loss_bands") or [])
                if _safe_float((item or {}).get("threshold_pct") or (item or {}).get("loss_pct"), 0.0) > 0
            ],
            key=lambda item: _safe_float(item.get("threshold_pct") or item.get("loss_pct"), 0.0),
        )

        positions = {
            str(item.get('stock_code') or '').strip(): dict(item)
            for item in await self._list_positions(db, account_id)
            if int(item.get('quantity') or 0) > 0
        }
        list_trade_positions = _get_async_db_method(db, "list_strategy_trade_positions")
        trade_positions = (
            await list_trade_positions(strategy_id=strategy['id'], account_id=account_id, limit=200)
            if list_trade_positions is not None
            else []
        )
        open_trade_positions: dict[str, dict] = {}
        latest_closed_by_code: dict[str, dict] = {}
        for row in list(trade_positions or []):
            item = dict(row or {})
            code = str(item.get("code") or "").strip()
            status = str(item.get("status") or "").strip().lower()
            if not code:
                continue
            if status in {"pending_entry", "open"}:
                open_trade_positions[code] = item
            elif status == "closed":
                latest_closed_by_code[code] = item

        active_position_codes = set(positions.keys()) | set(open_trade_positions.keys())
        current_open_slots = len(active_position_codes)

        async def _persist_order(
            *,
            code: str,
            direction: str,
            shares: int,
            price: float,
            source: str,
            signal_id: str,
            position_id: str,
            reason: Optional[str] = None,
        ) -> Optional[dict]:
            if shares <= 0:
                return None
            order = {
                'account_id': account_id,
                'strategy_id': strategy['id'],
                'signal_date': signal_date,
                'source': source,
                'code': code,
                'direction': direction,
                'shares': shares,
                'price': round(float(price), 4),
                'order_type': order_style if direction == 'buy' else 'marketable_limit',
                'status': 'pending',
                'signal_id': signal_id,
                'position_id': position_id,
            }
            if reason:
                order['reason'] = reason
            save_order_method = _get_async_db_method(db, 'save_paper_order')
            if save_order_method is not None:
                return await save_order_method(order)
            async with db.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO paper_orders
                        (account_id, strategy_id, signal_date, source, code, direction, shares, price,
                         order_type, status, signal_id, position_id, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW(), NOW())
                    RETURNING *
                    """,
                    account_id,
                    strategy['id'],
                    signal_date,
                    source,
                    code,
                    direction,
                    shares,
                    round(float(price), 4),
                    order.get('order_type') or 'limit',
                    'pending',
                    signal_id,
                    position_id,
                )
            return dict(row)

        def _order_price(base_price: float, direction: str) -> float:
            if order_style != "marketable_limit" or max_slippage_bps <= 0:
                return round(float(base_price), 4)
            multiplier = 1.0 + (max_slippage_bps / 10000.0)
            if direction == 'sell':
                multiplier = max(0.0, 1.0 - (max_slippage_bps / 10000.0))
            return round(float(base_price) * multiplier, 4)

        def _cooldown_active(code: str) -> bool:
            if cooldown_days <= 0:
                return False
            latest_closed = dict(latest_closed_by_code.get(code) or {})
            closed_at = _parse_datetime(latest_closed.get("closed_at") or latest_closed.get("exit_ts"))
            if closed_at is None:
                return False
            reference = datetime.combine(signal_date, datetime.min.time(), tzinfo=timezone.utc)
            return (reference - closed_at).days < cooldown_days

        async def _maybe_seed_position(
            *,
            code: str,
            direction: str,
            signal_id: str,
            position_id: str,
            saved_order: dict,
        ) -> None:
            bound_position = open_trade_positions.get(code) if direction == 'sell' else {}
            await _save_trade_position_seed(
                db,
                {
                    'position_id': position_id,
                    'strategy_id': strategy['id'],
                    'account_id': account_id,
                    'signal_id': signal_id,
                    'code': code,
                    'direction': 'long',
                    'status': 'pending_exit' if direction == 'sell' else 'pending_entry',
                    'entry_order_id': str(saved_order.get('id')) if direction == 'buy' else (bound_position or {}).get('entry_order_id'),
                    'exit_order_id': str(saved_order.get('id')) if direction == 'sell' else (bound_position or {}).get('exit_order_id'),
                    'opened_at': (bound_position or {}).get('opened_at'),
                    'last_trade_time': (bound_position or {}).get('last_trade_time'),
                },
            )

        for code, position in list(positions.items()):
            if (code, 'sell') in existing_keys:
                continue
            shares = int(position.get('quantity') or 0)
            if shares <= 0:
                continue
            latest_price = await self._price_on_or_before(db, code, signal_date)
            if latest_price is None or latest_price <= 0:
                continue
            entry_price = _safe_float(position.get('cost_price'), 0.0)
            pnl_ratio = (latest_price / entry_price - 1.0) if entry_price > 0 else 0.0
            open_position = dict(open_trade_positions.get(code) or {})
            prior_exit_shares = int(open_position.get("exit_shares") or 0)
            reason = None
            exit_shares = shares
            if initial_stop_loss_pct > 0 and pnl_ratio <= -initial_stop_loss_pct:
                reason = 'runtime_playbook_stop_loss'
            elif time_stop_days > 0:
                opened_at = _parse_datetime(open_position.get('opened_at') or open_position.get('entry_ts'))
                reference = datetime.combine(signal_date, datetime.min.time(), tzinfo=timezone.utc)
                if opened_at is not None and (reference - opened_at).days >= time_stop_days:
                    reason = 'runtime_playbook_time_stop'
            if reason is None:
                for band in loss_bands:
                    threshold = abs(_safe_float(band.get("threshold_pct") or band.get("loss_pct"), 0.0))
                    action = str(band.get("action") or "").strip().lower()
                    if threshold <= 0 or action in {"", "hold"} or pnl_ratio > -threshold:
                        continue
                    if action == 'reduce':
                        if prior_exit_shares > 0:
                            continue
                        reduced = int((shares * 0.5) / 100) * 100
                        exit_shares = reduced if reduced >= 100 else shares
                    else:
                        exit_shares = shares
                    reason = f"runtime_playbook_{str(band.get('label') or action).strip().lower()}"
                    break
            if not reason:
                continue
            signal_id = _build_signal_id(strategy['id'], {'reason': reason}, signal_date, code, 'sell')
            position_id = str((open_position or {}).get('position_id') or _build_position_id(strategy['id'], account_id, code, signal_id))
            saved_order = await _persist_order(
                code=code,
                direction='sell',
                shares=exit_shares,
                price=_order_price(latest_price, 'sell'),
                source='runtime_playbook',
                signal_id=signal_id,
                position_id=position_id,
                reason=reason,
            )
            if saved_order is None:
                skipped += 1
                continue
            created.append(saved_order)
            await _persist_runtime_signal_evidence(
                db,
                strategy,
                signal_id=signal_id,
                position_id=position_id,
                account_id=account_id,
                signal_date=signal_date,
                code=code,
                reason=reason,
            )
            await _maybe_seed_position(
                code=code,
                direction='sell',
                signal_id=signal_id,
                position_id=position_id,
                saved_order=saved_order,
            )
            existing_keys.add((code, 'sell'))

        for signal in signals:
            code = str(signal.get('code') or '').strip()
            latest_signal = int(signal.get('signal') or 0)
            if not code or latest_signal == 0:
                continue
            direction = 'buy' if latest_signal > 0 else 'sell'
            if direction == 'buy' and not execution_guard.get("allow_signal_entries"):
                blocked_by_execution_guard += 1
                skipped += 1
                continue
            if (code, direction) in existing_keys:
                skipped += 1
                continue
            price = await self._price_on_or_before(db, code, signal_date)
            if price is None or price <= 0:
                skipped += 1
                continue
            if direction == 'buy':
                if code in active_position_codes:
                    skipped += 1
                    continue
                if _cooldown_active(code):
                    skipped += 1
                    continue
                if current_open_slots >= max_concurrent_positions:
                    skipped += 1
                    continue
                budget_per_trade = max(
                    min(current_capital * base_budget_pct, total_value * max_position_pct),
                    5000.0,
                )
                min_lot_cost = float(price) * 100.0
                max_affordable_budget = max(
                    0.0,
                    min(float(current_capital), float(total_value) * max_position_pct),
                )
                if budget_per_trade < min_lot_cost <= max_affordable_budget:
                    budget_per_trade = min_lot_cost
                shares = int(budget_per_trade / price / 100) * 100
                if shares < 100:
                    skipped += 1
                    continue
            else:
                position = dict(positions.get(code) or {})
                shares = int(position.get('quantity') or 0)
                if shares <= 0:
                    skipped += 1
                    continue
            signal_id = _build_signal_id(strategy['id'], dict(signal or {}), signal_date, code, direction)
            bound_position = open_trade_positions.get(code) if direction == 'sell' else None
            position_id = str((bound_position or {}).get('position_id') or '').strip()
            if not position_id:
                position_id = _build_position_id(strategy['id'], account_id, code, signal_id)
            saved_order = await _persist_order(
                code=code,
                direction=direction,
                shares=shares,
                price=_order_price(price, direction),
                source='strategy_signal',
                signal_id=signal_id,
                position_id=position_id,
            )
            if saved_order is None:
                skipped += 1
                continue
            created.append(saved_order)
            await _maybe_seed_position(
                code=code,
                direction=direction,
                signal_id=signal_id,
                position_id=position_id,
                saved_order=saved_order,
            )
            await _persist_signal_evidence(
                db,
                strategy,
                signal_id=signal_id,
                position_id=position_id,
                account_id=account_id,
                signal_date=signal_date,
                code=code,
            )
            existing_keys.add((code, direction))
            if direction == 'buy':
                active_position_codes.add(code)
                current_open_slots += 1

        if created or skipped:
            await self._record_domain_event(
                db,
                strategy['id'],
                'incubation.orders_synced',
                {
                    'account_id': account_id,
                    'signal_date': str(signal_date),
                    'created_count': len(created),
                    'skipped_count': skipped,
                    'blocked_by_execution_guard': blocked_by_execution_guard,
                    'execution_guard': execution_guard,
                    'codes': [item.get('code') for item in created if item.get('code')],
                },
                correlation_id=str(signal_date),
            )

        return {
            'strategy_id': strategy['id'],
            'account_id': account_id,
            'created_count': len(created),
            'skipped_count': skipped,
            'blocked_by_execution_guard': blocked_by_execution_guard,
            'execution_guard': execution_guard,
            'orders': created,
        }

    async def force_close_open_positions(
        self,
        db,
        strategy: dict,
        signal_date: date,
        *,
        reason: str = 'replay_window_end_forced_exit',
        source: str = 'history_replay',
    ) -> dict:
        ensure = await self.ensure_account(db, strategy)
        account = ensure['account']
        account_id = account['id']
        runtime_playbook = _runtime_playbook_for_strategy(strategy)
        entry_policy = dict(runtime_playbook.get("entry_policy") or {})
        order_style = str(entry_policy.get("order_style") or "marketable_limit").strip().lower() or "marketable_limit"
        max_slippage_bps = max(0.0, _safe_float(entry_policy.get("max_slippage_bps"), 0.0))
        list_orders_method = _get_async_db_method(db, 'list_strategy_paper_orders')
        if list_orders_method is not None:
            existing_orders = await list_orders_method(strategy['id'], signal_date)
        else:
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM paper_orders WHERE strategy_id=$1 AND signal_date=$2",
                    strategy['id'], signal_date,
                )
            existing_orders = [dict(row) for row in rows]
        existing_keys = {(row.get('code'), row.get('direction')) for row in existing_orders}
        positions = {
            str(item.get('stock_code') or '').strip(): dict(item)
            for item in await self._list_positions(db, account_id)
            if int(item.get('quantity') or 0) > 0
        }
        list_trade_positions = _get_async_db_method(db, "list_strategy_trade_positions")
        trade_positions = (
            await list_trade_positions(strategy_id=strategy['id'], account_id=account_id, limit=200)
            if list_trade_positions is not None
            else []
        )
        open_trade_positions: dict[str, dict] = {}
        for row in list(trade_positions or []):
            item = dict(row or {})
            code = str(item.get("code") or "").strip()
            status = str(item.get("status") or "").strip().lower()
            if code and status in {"pending_entry", "open"}:
                open_trade_positions[code] = item

        def _order_price(base_price: float) -> float:
            if order_style != "marketable_limit" or max_slippage_bps <= 0:
                return round(float(base_price), 4)
            multiplier = max(0.0, 1.0 - (max_slippage_bps / 10000.0))
            return round(float(base_price) * multiplier, 4)

        created = []
        skipped = 0
        save_order_method = _get_async_db_method(db, 'save_paper_order')

        for code, position in list(positions.items()):
            if (code, 'sell') in existing_keys:
                skipped += 1
                continue
            shares = int(position.get('quantity') or 0)
            if shares <= 0:
                skipped += 1
                continue
            latest_price = await self._price_on_or_before(db, code, signal_date)
            if latest_price is None or latest_price <= 0:
                skipped += 1
                continue
            open_position = dict(open_trade_positions.get(code) or {})
            signal_id = _build_signal_id(
                strategy['id'],
                {'reason': reason, 'forced_exit': True},
                signal_date,
                code,
                'sell',
            )
            position_id = str(
                (open_position or {}).get('position_id')
                or _build_position_id(strategy['id'], account_id, code, signal_id)
            )
            order = {
                'account_id': account_id,
                'strategy_id': strategy['id'],
                'signal_date': signal_date,
                'source': source,
                'code': code,
                'direction': 'sell',
                'shares': shares,
                'price': _order_price(latest_price),
                'order_type': 'marketable_limit',
                'status': 'pending',
                'signal_id': signal_id,
                'position_id': position_id,
                'reason': reason,
            }
            if save_order_method is not None:
                saved_order = await save_order_method(order)
            else:
                async with db.acquire() as conn:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO paper_orders
                            (account_id, strategy_id, signal_date, source, code, direction, shares, price,
                             order_type, status, signal_id, position_id, reason, created_at, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                                $9, $10, $11, $12, $13, NOW(), NOW())
                        RETURNING *
                        """,
                        account_id,
                        strategy['id'],
                        signal_date,
                        source,
                        code,
                        'sell',
                        shares,
                        _order_price(latest_price),
                        'marketable_limit',
                        'pending',
                        signal_id,
                        position_id,
                        reason,
                    )
                saved_order = dict(row) if row else None
            if not saved_order:
                skipped += 1
                continue
            created.append(saved_order)
            await _persist_runtime_signal_evidence(
                db,
                strategy,
                signal_id=signal_id,
                position_id=position_id,
                account_id=account_id,
                signal_date=signal_date,
                code=code,
                reason=reason,
            )
            await _save_trade_position_seed(
                db,
                {
                    'position_id': position_id,
                    'strategy_id': strategy['id'],
                    'account_id': account_id,
                    'signal_id': signal_id,
                    'code': code,
                    'direction': 'long',
                    'status': 'pending_exit',
                    'entry_order_id': (open_position or {}).get('entry_order_id'),
                    'exit_order_id': str(saved_order.get('id')) if saved_order else None,
                    'opened_at': (open_position or {}).get('opened_at') or self._execution_timestamp(signal_date),
                    'last_trade_time': (open_position or {}).get('last_trade_time') or self._execution_timestamp(signal_date),
                },
            )
            existing_keys.add((code, 'sell'))

        if created or skipped:
            await self._record_domain_event(
                db,
                strategy['id'],
                'incubation.replay_window_force_close',
                {
                    'account_id': account_id,
                    'signal_date': str(signal_date),
                    'created_count': len(created),
                    'skipped_count': skipped,
                    'reason': reason,
                    'codes': [item.get('code') for item in created if item.get('code')],
                },
                correlation_id=f"{signal_date}:force_close",
                severity='warning' if created else 'info',
            )

        return {
            'strategy_id': strategy['id'],
            'account_id': account_id,
            'created_count': len(created),
            'skipped_count': skipped,
            'orders': created,
            'reason': reason,
        }

    # Fix #12: 6 阶段孵化映射
    @staticmethod
    def _derive_incubation_stage(overview: dict, open_risk_count: int = 0) -> str:
        """根据信号质量与风险状态推导当前阶段。"""
        from .strategy_lifecycle_shared import resolve_incubation_pipeline_stage

        if str(overview.get('pipeline_stage') or '').strip():
            return str(overview.get('pipeline_stage'))
        return resolve_incubation_pipeline_stage(
            overview.get('signal_quality') or {},
            open_risk_count=open_risk_count,
            execution_audit_gate_status=overview.get('execution_audit_gate_status'),
        )
