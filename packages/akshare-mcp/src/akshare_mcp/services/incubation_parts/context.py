    async def _get_strategy_account(self, db, strategy_id: str) -> Optional[dict]:
        method = _get_async_db_method(db, 'get_paper_account_by_strategy')
        if method is not None:
            return await method(strategy_id)
        acquire = _get_db_acquire(db)
        if acquire is None:
            return None
        async with acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM paper_accounts WHERE strategy_id=$1 ORDER BY created_at LIMIT 1",
                strategy_id,
            )
        return dict(row) if row else None

    async def _save_strategy_account(self, db, account: dict) -> dict:
        method = _get_async_db_method(db, 'save_paper_account')
        if method is not None:
            return await method(account)
        acquire = _get_db_acquire(db)
        if acquire is None:
            return dict(account)
        async with acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_accounts
                    (id, user_id, name, initial_capital, current_capital, total_value, risk_rules,
                     strategy_id, account_type, incubation_stage, promotion_candidate, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    risk_rules = EXCLUDED.risk_rules,
                    strategy_id = EXCLUDED.strategy_id,
                    account_type = EXCLUDED.account_type,
                    incubation_stage = EXCLUDED.incubation_stage,
                    promotion_candidate = EXCLUDED.promotion_candidate,
                    status = EXCLUDED.status,
                    total_value = EXCLUDED.total_value,
                    current_capital = EXCLUDED.current_capital
                RETURNING *
                """,
                account['id'],
                account.get('user_id') or 'strategy_factory',
                account['name'],
                float(account.get('initial_capital') or DEFAULT_INCUBATION_CAPITAL),
                float(account.get('current_capital') or DEFAULT_INCUBATION_CAPITAL),
                float(account.get('total_value') or DEFAULT_INCUBATION_CAPITAL),
                json.dumps(_safe_rules_dict(account.get('risk_rules')) or DEFAULT_INCUBATION_RULES),
                account.get('strategy_id'),
                account.get('account_type') or 'incubation',
                account.get('incubation_stage') or 'warmup',
                bool(account.get('promotion_candidate')),
                account.get('status') or 'active',
            )
        return dict(row)

    async def _record_domain_event(self, db, strategy_id: Optional[str], event_type: str, payload: dict, *, source: str = 'incubation', severity: str = 'info', correlation_id: Optional[str] = None):
        method = _get_async_db_method(db, 'save_strategy_domain_event')
        if method is not None:
            await method({
                'strategy_id': strategy_id,
                'aggregate_type': 'strategy',
                'aggregate_id': strategy_id,
                'event_type': event_type,
                'source': source,
                'severity': severity,
                'correlation_id': correlation_id,
                'payload': payload,
            })

    async def ensure_account(self, db, strategy: dict, stage: str = 'warmup', source_run_id: Optional[str] = None) -> dict:
        strategy_id = strategy['id']
        trace_metadata = dict(strategy.get('_closure_trace') or {})
        binding_method = _get_async_db_method(db, 'get_strategy_incubation_account')
        binding = await binding_method(strategy_id) if binding_method is not None else None
        account = None
        created = False
        if binding:
            account = await self._get_strategy_account(db, strategy_id)
        if not account:
            account = await self._get_strategy_account(db, strategy_id)
        if not account:
            account = await self._save_strategy_account(db, {
                'id': f'inc_{uuid4().hex[:8]}',
                'user_id': 'strategy_factory',
                'name': f"孵化_{str(strategy.get('name') or strategy_id)[:24]}",
                'initial_capital': DEFAULT_INCUBATION_CAPITAL,
                'current_capital': DEFAULT_INCUBATION_CAPITAL,
                'total_value': DEFAULT_INCUBATION_CAPITAL,
                'risk_rules': _strategy_account_risk_rules(strategy),
                'strategy_id': strategy_id,
                'account_type': 'incubation',
                'incubation_stage': stage,
                'promotion_candidate': False,
                'status': 'active',
            })
            created = True

        bind = await db.save_strategy_incubation_account(
            strategy_id,
            account['id'],
            stage=stage,
            status='active',
            source_run_id=source_run_id,
            metadata={
                'strategy_name': strategy.get('name'),
                'strategy_type': strategy.get('strategy_type'),
                **trace_metadata,
            },
        )
        await self._record_domain_event(
            db,
            strategy_id,
            'incubation.account_bound',
            {
                'account_id': account['id'],
                'stage': stage,
                'created': created,
                'source_run_id': source_run_id,
                'trace': trace_metadata,
            },
            correlation_id=trace_metadata.get('correlation_id') or source_run_id,
        )
        return {'created': created, 'account': account, 'binding': bind}

    async def _latest_price(self, db, code: str) -> Optional[float]:
        try:
            klines = await db.get_klines(code, limit=1)
            if klines:
                return float(klines[-1].get('close') or 0) or None
        except Exception:
            return None
        return None

    async def _price_on_or_before(self, db, code: str, as_of_date: Optional[date] = None) -> Optional[float]:
        code_token = str(code or '').strip()
        if not code_token:
            return None
        if as_of_date and hasattr(db, 'get_klines'):
            try:
                klines = await db.get_klines(
                    code_token,
                    end_date=str(as_of_date),
                    limit=1,
                )
                if klines:
                    return float((klines[-1] or {}).get('close') or 0.0) or None
            except Exception:
                pass
        return await self._latest_price(db, code_token)

    @staticmethod
    def _execution_timestamp(signal_date: Optional[date]) -> datetime:
        resolved_date = signal_date if isinstance(signal_date, date) else date.today()
        return datetime.combine(resolved_date, datetime.min.time(), tzinfo=timezone.utc)

    async def _list_positions(self, db, account_id: str) -> list[dict]:
        method = _get_async_db_method(db, 'list_paper_positions')
        if method is not None:
            return await method(account_id)
        async with db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM paper_positions WHERE account_id = $1 ORDER BY stock_code",
                account_id,
            )
        return [dict(row) for row in rows]

    async def _save_position(self, db, position: dict) -> dict:
        method = _get_async_db_method(db, 'save_paper_position')
        if method is not None:
            return await method(position)
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_positions
                    (account_id, stock_code, stock_name, quantity, cost_price, current_price, market_value, profit_rate, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (account_id, stock_code) DO UPDATE SET
                    stock_name = EXCLUDED.stock_name,
                    quantity = EXCLUDED.quantity,
                    cost_price = EXCLUDED.cost_price,
                    current_price = EXCLUDED.current_price,
                    market_value = EXCLUDED.market_value,
                    profit_rate = EXCLUDED.profit_rate,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *
                """,
                position.get('account_id'),
                position.get('stock_code'),
                position.get('stock_name') or position.get('stock_code') or '',
                int(position.get('quantity') or 0),
                float(position.get('cost_price') or 0.0),
                position.get('current_price'),
                position.get('market_value'),
                position.get('profit_rate'),
            )
        return dict(row)

    async def _save_trade(self, db, trade: dict) -> dict:
        method = _get_async_db_method(db, 'save_paper_trade')
        if method is not None:
            return await method(trade)
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_trades
                    (id, account_id, stock_code, stock_name, trade_type, price, quantity, amount, commission,
                     trade_time, reason, strategy_id, source_order_id, signal_id, position_id, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, CURRENT_TIMESTAMP)
                RETURNING *
                """,
                trade.get('id'),
                trade.get('account_id'),
                trade.get('stock_code'),
                trade.get('stock_name') or trade.get('stock_code') or '',
                trade.get('trade_type'),
                float(trade.get('price') or 0.0),
                int(trade.get('quantity') or 0),
                float(trade.get('amount') or 0.0),
                float(trade.get('commission') or 0.0),
                trade.get('trade_time'),
                trade.get('reason'),
                trade.get('strategy_id'),
                trade.get('source_order_id'),
                trade.get('signal_id'),
                trade.get('position_id'),
            )
        return dict(row)

    async def _update_order(self, db, order_id: int, updates: dict) -> Optional[dict]:
        method = _get_async_db_method(db, 'update_paper_order')
        if method is not None:
            return await method(order_id, updates)
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE paper_orders
                SET price = COALESCE($2, price),
                    shares = COALESCE($3, shares),
                    status = COALESCE($4, status),
                    commission = COALESCE($5, commission),
                    reason = COALESCE($6, reason),
                    filled_at = COALESCE($7, filled_at),
                    signal_id = COALESCE($8, signal_id),
                    position_id = COALESCE($9, position_id),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                RETURNING *
                """,
                int(order_id),
                updates.get('price'),
                updates.get('shares'),
                updates.get('status'),
                updates.get('commission'),
                updates.get('reason'),
                updates.get('filled_at'),
                updates.get('signal_id'),
                updates.get('position_id'),
            )
        return dict(row) if row else None

    async def _save_nav_snapshot(self, db, account: dict, nav_date: date, cash: float, market_value: float) -> dict:
        account_id = account['id']
        total_value = round(cash + market_value, 4)
        nav_rows_method = _get_async_db_method(db, 'get_paper_nav_rows')
        rows = await nav_rows_method(account_id, limit=2) if nav_rows_method is not None else []
        prev = next((row for row in rows if str(row.get('nav_date')) != str(nav_date)), None)
        prev_total = float((prev or {}).get('total_value') or account.get('initial_capital') or total_value or DEFAULT_INCUBATION_CAPITAL)
        daily_return = ((total_value - prev_total) / prev_total) if prev_total > 0 else 0.0
        snapshot = {
            'account_id': account_id,
            'nav_date': nav_date,
            'total_value': total_value,
            'cash': round(cash, 4),
            'market_value': round(market_value, 4),
            'daily_return': round(daily_return, 6),
        }
        save_nav_method = _get_async_db_method(db, 'save_paper_nav')
        if save_nav_method is not None:
            await save_nav_method(snapshot)
        else:
            async with db.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO paper_nav (account_id, nav_date, total_value, cash, market_value, daily_return, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP)
                    ON CONFLICT (account_id, nav_date) DO UPDATE
                    SET total_value=$3, cash=$4, market_value=$5, daily_return=$6
                    """,
                    snapshot['account_id'], snapshot['nav_date'], snapshot['total_value'], snapshot['cash'], snapshot['market_value'], snapshot['daily_return'],
                )
        updated_account = await self._save_strategy_account(db, {
            **account,
            'current_capital': round(cash, 4),
            'total_value': total_value,
        })
        return {'snapshot': snapshot, 'account': updated_account}

    async def settle_orders(self, db, strategy: dict, signal_date: Optional[date] = None) -> dict:
        signal_date = signal_date or date.today()
        ensure = await self.ensure_account(db, strategy)
        account = ensure['account']
        account_id = account['id']
        list_orders_method = _get_async_db_method(db, 'list_strategy_paper_orders')
        orders = await list_orders_method(strategy['id'], signal_date) if list_orders_method is not None else []
        executable = [item for item in orders if str(item.get('status') or 'pending') in {'pending', 'submitted'}]
        positions = {str(item.get('stock_code') or ''): dict(item) for item in await self._list_positions(db, account_id)}
        cash = float(account.get('current_capital') or account.get('initial_capital') or DEFAULT_INCUBATION_CAPITAL)
        filled = []
        rejected = []
        execution_ts = self._execution_timestamp(signal_date)

        for order in executable:
            code = str(order.get('code') or '').strip()
            direction = str(order.get('direction') or '').strip().lower()
            shares = int(order.get('shares') or 0)
            if not code or shares <= 0 or direction not in {'buy', 'sell'}:
                rejected.append(await self._update_order(db, order['id'], {'status': 'rejected', 'reason': 'invalid_order'}))
                continue
            exec_price = await self._price_on_or_before(db, code, signal_date) or float(order.get('price') or 0)
            if exec_price <= 0:
                rejected.append(await self._update_order(db, order['id'], {'status': 'rejected', 'reason': 'price_unavailable'}))
                continue
            commission = round(exec_price * shares * 0.0003, 4)
            position = dict(positions.get(code) or {})
            current_qty = int(position.get('quantity') or 0)
            if direction == 'buy':
                amount = round(exec_price * shares, 4)
                total_cost = amount + commission
                if cash + 1e-9 < total_cost:
                    rejected.append(await self._update_order(db, order['id'], {'status': 'rejected', 'reason': 'insufficient_cash', 'price': round(exec_price, 4), 'commission': commission}))
                    continue
                cash = round(cash - total_cost, 4)
                new_qty = current_qty + shares
                avg_cost = float(position.get('cost_price') or 0.0)
                new_cost = ((avg_cost * current_qty) + amount) / max(new_qty, 1)
                latest_price = await self._price_on_or_before(db, code, signal_date) or exec_price
                market_value = round(latest_price * new_qty, 4)
                positions[code] = await self._save_position(db, {
                    'account_id': account_id,
                    'stock_code': code,
                    'stock_name': position.get('stock_name') or code,
                    'quantity': new_qty,
                    'cost_price': round(new_cost, 6),
                    'current_price': round(latest_price, 4),
                    'market_value': market_value,
                    'profit_rate': round(((latest_price - new_cost) / new_cost), 6) if new_cost > 0 else 0.0,
                })
            else:
                if current_qty < shares:
                    rejected.append(await self._update_order(db, order['id'], {'status': 'rejected', 'reason': 'insufficient_position', 'price': round(exec_price, 4)}))
                    continue
                amount = round(exec_price * shares, 4)
                cash = round(cash + amount - commission, 4)
                new_qty = current_qty - shares
                avg_cost = float(position.get('cost_price') or 0.0)
                latest_price = await self._price_on_or_before(db, code, signal_date) or exec_price
                market_value = round(latest_price * new_qty, 4)
                positions[code] = await self._save_position(db, {
                    'account_id': account_id,
                    'stock_code': code,
                    'stock_name': position.get('stock_name') or code,
                    'quantity': new_qty,
                    'cost_price': round(avg_cost, 6),
                    'current_price': round(latest_price, 4),
                    'market_value': market_value,
                    'profit_rate': round(((latest_price - avg_cost) / avg_cost), 6) if avg_cost > 0 else 0.0,
                })
            trade = await self._save_trade(db, {
                'id': f"ptr_{uuid4().hex[:10]}",
                'account_id': account_id,
                'stock_code': code,
                'stock_name': (positions.get(code) or {}).get('stock_name') or code,
                'trade_type': direction,
                'price': round(exec_price, 4),
                'quantity': shares,
                'amount': amount,
                'commission': commission,
                'trade_time': execution_ts,
                'reason': order.get('reason') or order.get('source') or 'strategy_signal',
                'strategy_id': strategy['id'],
                'source_order_id': str(order.get('id')),
                'signal_id': order.get('signal_id'),
                'position_id': order.get('position_id'),
            })
            updated_order = await self._update_order(db, order['id'], {
                'status': 'filled',
                'price': round(exec_price, 4),
                'commission': commission,
                'filled_at': execution_ts,
                'signal_id': order.get('signal_id'),
                'position_id': order.get('position_id'),
            })
            await _record_trade_audit_fill(db, updated_order or order, trade)
            filled.append({'order': updated_order, 'trade': trade})

        market_value = 0.0
        for code, position in list(positions.items()):
            qty = int(position.get('quantity') or 0)
            if qty <= 0:
                continue
            latest_price = await self._price_on_or_before(db, code, signal_date) or float(position.get('current_price') or position.get('cost_price') or 0.0)
            avg_cost = float(position.get('cost_price') or 0.0)
            market_value += latest_price * qty
            positions[code] = await self._save_position(db, {
                **position,
                'account_id': account_id,
                'stock_code': code,
                'current_price': round(latest_price, 4),
                'market_value': round(latest_price * qty, 4),
                'profit_rate': round(((latest_price - avg_cost) / avg_cost), 6) if avg_cost > 0 else 0.0,
            })

        nav_result = await self._save_nav_snapshot(db, account, signal_date, cash, market_value)
        if filled or rejected:
            await self._record_domain_event(
                db,
                strategy['id'],
                'incubation.orders_settled',
                {
                    'account_id': account_id,
                    'signal_date': str(signal_date),
                    'filled_count': len(filled),
                    'rejected_count': len([item for item in rejected if item]),
                    'nav': nav_result['snapshot'],
                },
                correlation_id=str(signal_date),
                severity='warning' if rejected else 'info',
            )
        await self._record_domain_event(
            db,
            strategy['id'],
            'incubation.nav_recorded',
            {
                'account_id': account_id,
                'signal_date': str(signal_date),
                'nav': nav_result['snapshot'],
            },
            correlation_id=str(signal_date),
        )
        return {
            'strategy_id': strategy['id'],
            'account_id': account_id,
            'filled_count': len(filled),
            'rejected_count': len([item for item in rejected if item]),
            'nav_snapshot': nav_result['snapshot'],
            'cash': nav_result['snapshot']['cash'],
            'market_value': nav_result['snapshot']['market_value'],
        }
