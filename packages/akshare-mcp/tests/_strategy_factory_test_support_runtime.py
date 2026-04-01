from __future__ import annotations

import math
from datetime import date, datetime, timezone

class _StrategyDBRuntimeMixin:
    async def save_strategy_factory_run(self, run):
        self._factory_runs = [item for item in self._factory_runs if item.get("run_id") != run.get("run_id")]
        self._factory_runs.append(dict(run))
        self._factory_runs.sort(key=lambda item: item.get("started_at") or "", reverse=True)

    async def list_strategy_factory_runs(self, limit=20):
        return self._factory_runs[:limit]

    async def get_latest_strategy_factory_run(self):
        rows = await self.list_strategy_factory_runs(limit=1)
        return rows[0] if rows else None

    async def get_strategy_factory_run(self, run_id):
        for item in self._factory_runs:
            if item.get("run_id") == run_id:
                return item
        return None

    @staticmethod
    def _normalize_snapshot_date(snapshot_date):
        return str(snapshot_date)

    async def save_daily_snapshot(self, snapshot_date, data):
        normalized = self._normalize_snapshot_date(snapshot_date)
        item = {"snapshot_date": normalized, **dict(data)}
        self._daily_snapshots = [row for row in self._daily_snapshots if row.get("snapshot_date") != normalized]
        self._daily_snapshots.append(item)
        self._daily_snapshots.sort(key=lambda row: row.get("snapshot_date") or "", reverse=True)

    async def save_factory_market_internal_snapshot(self, item):
        payload = {"snapshot_date": self._normalize_snapshot_date((item or {}).get("snapshot_date") or (item or {}).get("date")), **dict(item or {})}
        self._factory_market_internals = [row for row in self._factory_market_internals if row.get("snapshot_date") != payload.get("snapshot_date")]
        self._factory_market_internals.append(payload)
        self._factory_market_internals.sort(key=lambda row: row.get("snapshot_date") or "", reverse=True)
        return dict(payload)

    async def get_factory_market_internal_snapshot(self, snapshot_date=None):
        if snapshot_date is None:
            return dict(self._factory_market_internals[0]) if self._factory_market_internals else None
        normalized = self._normalize_snapshot_date(snapshot_date)
        for item in self._factory_market_internals:
            if item.get("snapshot_date") == normalized:
                return dict(item)
        return None

    async def list_factory_market_internal_snapshots(self, limit=20):
        return [dict(item) for item in self._factory_market_internals[: max(1, min(int(limit or 20), 200))]]

    async def get_recent_north_fund_summary(self, days=3, sample_limit=5):
        if self._north_fund_summary is not None:
            return dict(self._north_fund_summary)
        return None

    async def get_daily_snapshot(self, snapshot_date=None):
        if snapshot_date is None:
            return self._daily_snapshots[0] if self._daily_snapshots else None
        normalized = self._normalize_snapshot_date(snapshot_date)
        for item in self._daily_snapshots:
            if item.get("snapshot_date") == normalized:
                return item
        return None

    async def list_daily_snapshots(self, limit=20, start_date=None, end_date=None):
        rows = list(self._daily_snapshots)
        if start_date:
            rows = [row for row in rows if row.get("snapshot_date") >= str(start_date)]
        if end_date:
            rows = [row for row in rows if row.get("snapshot_date") <= str(end_date)]
        return rows[:limit]

    async def save_factory_event_cluster(self, item):
        event_id = str((item or {}).get('event_id') or '').strip()
        self._factory_event_clusters = [row for row in self._factory_event_clusters if str(row.get('event_id') or '').strip() != event_id]
        saved = dict(item or {})
        saved.setdefault('event_id', event_id)
        self._factory_event_clusters.append(saved)
        self._factory_event_clusters.sort(key=lambda row: row.get('last_seen_at') or row.get('occurred_at') or '', reverse=True)
        return saved

    async def list_factory_event_clusters(self, status=None, event_type=None, limit=20):
        rows = [dict(item) for item in self._factory_event_clusters]
        if status:
            rows = [row for row in rows if str(row.get('status') or 'active') == str(status)]
        if event_type:
            rows = [row for row in rows if str(row.get('event_type') or '') == str(event_type)]
        rows.sort(key=lambda row: (row.get('last_seen_at') or row.get('occurred_at') or '', float(row.get('confidence') or 0.0)), reverse=True)
        return rows[: max(1, min(int(limit or 20), 200))]

    async def save_factory_theme_definition(self, item):
        theme_code = str((item or {}).get('theme_code') or '').strip()
        self._factory_theme_definitions = [row for row in self._factory_theme_definitions if str(row.get('theme_code') or '').strip() != theme_code]
        saved = dict(item or {})
        saved.setdefault('theme_code', theme_code)
        self._factory_theme_definitions.append(saved)
        self._factory_theme_definitions.sort(key=lambda row: str(row.get('theme_code') or ''))
        return saved

    async def list_factory_theme_definitions(self, active_only=True, limit=200):
        rows = [dict(item) for item in self._factory_theme_definitions]
        if active_only:
            rows = [row for row in rows if bool(row.get('active', True))]
        rows.sort(key=lambda row: str(row.get('theme_code') or ''))
        return rows[: max(1, min(int(limit or 200), 500))]

    async def save_factory_company_theme_exposure(self, item):
        symbol = str((item or {}).get('symbol') or '').strip()
        theme_code = str((item or {}).get('theme_code') or '').strip()
        exposure_type = str((item or {}).get('exposure_type') or 'revenue')
        self._factory_company_theme_exposures = [
            row for row in self._factory_company_theme_exposures
            if not (
                str(row.get('symbol') or '').strip() == symbol
                and str(row.get('theme_code') or '').strip() == theme_code
                and str(row.get('exposure_type') or 'revenue') == exposure_type
            )
        ]
        saved = dict(item or {})
        self._factory_company_theme_exposures.append(saved)
        self._factory_company_theme_exposures.sort(key=lambda row: float(row.get('exposure_score') or 0.0), reverse=True)
        return saved

    async def list_factory_company_theme_exposures(self, theme_codes=None, symbols=None, limit=200):
        rows = [dict(item) for item in self._factory_company_theme_exposures]
        normalized_theme_codes = {str(item).strip() for item in list(theme_codes or []) if str(item).strip()}
        normalized_symbols = {str(item).strip() for item in list(symbols or []) if str(item).strip()}
        if normalized_theme_codes:
            rows = [row for row in rows if str(row.get('theme_code') or '').strip() in normalized_theme_codes]
        if normalized_symbols:
            rows = [row for row in rows if str(row.get('symbol') or '').strip() in normalized_symbols]
        rows.sort(key=lambda row: float(row.get('exposure_score') or 0.0), reverse=True)
        return rows[: max(1, min(int(limit or 200), 500))]

    async def save_factory_event_signal(self, item):
        event_id = str((item or {}).get('event_id') or '').strip()
        symbol = str((item or {}).get('symbol') or '').strip()
        theme_code = str((item or {}).get('theme_code') or '').strip()
        self._factory_event_signals = [
            row for row in self._factory_event_signals
            if not (
                str(row.get('event_id') or '').strip() == event_id
                and str(row.get('symbol') or '').strip() == symbol
                and str(row.get('theme_code') or '').strip() == theme_code
            )
        ]
        saved = dict(item or {})
        self._factory_event_signals.append(saved)
        self._factory_event_signals.sort(key=lambda row: (float(row.get('final_score') or 0.0), row.get('observed_at') or ''), reverse=True)
        return saved

    async def list_factory_event_signals(self, event_id=None, theme_code=None, symbols=None, min_final_score=None, limit=200):
        rows = [dict(item) for item in self._factory_event_signals]
        if event_id:
            rows = [row for row in rows if str(row.get('event_id') or '').strip() == str(event_id)]
        if theme_code is not None:
            rows = [row for row in rows if str(row.get('theme_code') or '').strip() == str(theme_code)]
        normalized_symbols = {str(item).strip() for item in list(symbols or []) if str(item).strip()}
        if normalized_symbols:
            rows = [row for row in rows if str(row.get('symbol') or '').strip() in normalized_symbols]
        if min_final_score is not None:
            rows = [row for row in rows if float(row.get('final_score') or 0.0) >= float(min_final_score)]
        rows.sort(key=lambda row: (float(row.get('final_score') or 0.0), row.get('observed_at') or ''), reverse=True)
        return rows[: max(1, min(int(limit or 200), 500))]

    async def save_factory_task_evidence(self, item):
        saved = dict(item or {})
        self._factory_task_evidence.append(saved)
        self._factory_task_evidence.sort(key=lambda row: row.get('created_at') or '', reverse=True)
        return saved

    async def list_factory_task_evidence(self, task_key=None, event_id=None, limit=200):
        rows = [dict(item) for item in self._factory_task_evidence]
        if task_key:
            rows = [row for row in rows if str(row.get('task_key') or '') == str(task_key)]
        if event_id:
            rows = [row for row in rows if str(row.get('event_id') or '') == str(event_id)]
        rows.sort(key=lambda row: row.get('created_at') or '', reverse=True)
        return rows[: max(1, min(int(limit or 200), 500))]

    async def get_paper_account_by_strategy(self, strategy_id):
        for item in self._paper_accounts.values():
            if item.get('strategy_id') == strategy_id:
                return dict(item)
        return None

    async def get_paper_account(self, account_id):
        item = self._paper_accounts.get(account_id)
        return dict(item) if item else None

    async def save_paper_account(self, account):
        item = dict(account)
        existing = self._paper_accounts.get(item['id']) or {}
        merged = {**existing, **item}
        self._paper_accounts[item['id']] = merged
        return dict(merged)

    async def update_paper_account_status(self, account_id, status, stage=None, promotion_candidate=None):
        account = self._paper_accounts.get(account_id)
        if not account:
            return None
        account['status'] = status
        if stage is not None:
            account['incubation_stage'] = stage
        if promotion_candidate is not None:
            account['promotion_candidate'] = promotion_candidate
        return dict(account)

    async def list_strategy_paper_orders(self, strategy_id, signal_date=None, status=None, limit=200):
        rows = [dict(item) for item in self._paper_orders if item.get('strategy_id') == strategy_id]
        if signal_date is not None:
            rows = [item for item in rows if str(item.get('signal_date')) == str(signal_date)]
        if status is not None:
            rows = [item for item in rows if str(item.get('status')) == str(status)]
        rows.sort(key=lambda item: int(item.get('id') or 0), reverse=True)
        return rows[:limit]

    async def save_paper_order(self, order):
        item = dict(order)
        item.setdefault('id', len(self._paper_orders) + 1)
        self._paper_orders.append(item)
        return dict(item)

    async def update_paper_order(self, order_id, updates):
        for item in self._paper_orders:
            if int(item.get('id')) == int(order_id):
                item.update(dict(updates or {}))
                return dict(item)
        return None

    async def list_paper_positions(self, account_id):
        rows = [dict(item) for item in self._paper_positions.values() if item.get('account_id') == account_id]
        rows.sort(key=lambda item: str(item.get('stock_code') or ''))
        return rows

    async def save_paper_position(self, position):
        item = dict(position)
        key = (item.get('account_id'), item.get('stock_code'))
        existing = self._paper_positions.get(key) or {}
        merged = {**existing, **item}
        self._paper_positions[key] = merged
        return dict(merged)

    async def save_paper_trade(self, trade):
        item = dict(trade)
        self._paper_trades.append(item)
        return dict(item)

    async def save_paper_nav(self, nav):
        item = dict(nav)
        rows = [row for row in self._paper_nav.get(item['account_id'], []) if str(row.get('nav_date')) != str(item.get('nav_date'))]
        rows.append(item)
        self._paper_nav[item['account_id']] = rows
        return dict(item)

    async def get_paper_nav_rows(self, account_id, limit=60):
        rows = list(self._paper_nav.get(account_id, []))
        rows.sort(key=lambda row: row.get('nav_date') or '', reverse=True)
        return rows[:limit]

    async def get_paper_order_summary(self, account_id):
        orders = [item for item in self._paper_orders if item.get('account_id') == account_id]
        return {
            'total_orders': len(orders),
            'total_trades': len([item for item in orders if item.get('status') == 'filled']),
            'trade_amount': float(sum((item.get('price') or 0) * (item.get('shares') or 0) for item in orders if item.get('status') == 'filled')),
        }

    async def save_strategy_incubation_account(self, strategy_id, account_id, stage='warmup', status='active', source_run_id=None, metadata=None):
        item = {
            'id': len(self._incubation_accounts) + 1,
            'strategy_id': strategy_id,
            'account_id': account_id,
            'stage': stage,
            'status': status,
            'source_run_id': source_run_id,
            'metadata': metadata or {},
        }
        self._incubation_accounts = [row for row in self._incubation_accounts if not (row.get('strategy_id') == strategy_id and row.get('account_id') == account_id)]
        self._incubation_accounts.append(item)
        return dict(item)

    async def get_strategy_incubation_account(self, strategy_id, account_id=None):
        rows = [row for row in self._incubation_accounts if row.get('strategy_id') == strategy_id]
        if account_id:
            rows = [row for row in rows if row.get('account_id') == account_id]
        return dict(rows[-1]) if rows else None

    async def list_strategy_incubation_accounts(self, strategy_id=None, status=None, limit=20):
        rows = list(self._incubation_accounts)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_incubation_metric(self, strategy_id, metric_date, metric):
        item = {'strategy_id': strategy_id, 'metric_date': str(metric_date), **dict(metric)}
        self._incubation_metrics = [row for row in self._incubation_metrics if not (row.get('strategy_id') == strategy_id and row.get('metric_date') == str(metric_date))]
        self._incubation_metrics.append(item)
        self._incubation_metrics.sort(key=lambda row: row.get('metric_date') or '', reverse=True)
        return dict(item)

    async def get_latest_strategy_incubation_metric(self, strategy_id):
        rows = await self.list_strategy_incubation_metrics(strategy_id, limit=1)
        return rows[0] if rows else None

    async def list_strategy_incubation_metrics(self, strategy_id, limit=30, start_date=None, end_date=None):
        rows = [row for row in self._incubation_metrics if row.get('strategy_id') == strategy_id]
        if start_date:
            rows = [row for row in rows if row.get('metric_date') >= str(start_date)]
        if end_date:
            rows = [row for row in rows if row.get('metric_date') <= str(end_date)]
        rows.sort(key=lambda row: row.get('metric_date') or '', reverse=True)
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_incubation_pipeline_snapshot(self, snapshot):
        item = {'id': len(self._incubation_pipeline_snapshots) + 1, **dict(snapshot)}
        self._incubation_pipeline_snapshots.insert(0, item)
        return dict(item)

    async def get_latest_strategy_incubation_pipeline_snapshot(self, strategy_id):
        rows = await self.list_strategy_incubation_pipeline_snapshots(strategy_id=strategy_id, limit=1)
        return rows[0] if rows else None

    async def list_strategy_incubation_pipeline_snapshots(self, strategy_id=None, pipeline_stage=None, pipeline_status=None, limit=20):
        rows = list(self._incubation_pipeline_snapshots)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if pipeline_stage:
            rows = [row for row in rows if row.get('pipeline_stage') == pipeline_stage]
        if pipeline_status:
            rows = [row for row in rows if row.get('pipeline_status') == pipeline_status]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_runtime_risk_event(self, event):
        item = {'id': len(self._risk_events) + 1, **dict(event)}
        self._risk_events.append(item)
        return dict(item)

    async def list_strategy_runtime_risk_events(self, strategy_id=None, account_id=None, status=None, severity=None, limit=50):
        rows = list(self._risk_events)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if account_id:
            rows = [row for row in rows if row.get('account_id') == account_id]
        if status:
            rows = [row for row in rows if row.get('status', 'open') == status]
        if severity:
            rows = [row for row in rows if row.get('severity') == severity]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_runtime_risk_snapshot(self, snapshot):
        item = {'id': len(self._runtime_risk_snapshots) + 1, **dict(snapshot)}
        self._runtime_risk_snapshots.insert(0, item)
        return dict(item)

    async def get_latest_strategy_runtime_risk_snapshot(self, strategy_id):
        rows = await self.list_strategy_runtime_risk_snapshots(strategy_id=strategy_id, limit=1)
        return rows[0] if rows else None

    async def list_strategy_runtime_risk_snapshots(self, strategy_id=None, posture_level=None, control_mode=None, limit=20):
        rows = list(self._runtime_risk_snapshots)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if posture_level:
            rows = [row for row in rows if row.get('posture_level') == posture_level]
        if control_mode:
            rows = [row for row in rows if row.get('control_mode') == control_mode]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_runtime_alert(self, alert):
        existing = None
        alert_id = alert.get('alert_id')
        if alert_id is not None:
            for item in self._runtime_alerts:
                if int(item.get('alert_id')) == int(alert_id):
                    existing = item
                    break
        now = datetime.now(timezone.utc).isoformat()
        if existing is not None:
            existing.update(dict(alert))
            existing['updated_at'] = now
            if existing.get('status') == 'resolved' and not existing.get('resolved_at'):
                existing['resolved_at'] = now
            return dict(existing)
        item = {
            'status': 'open',
            'channels': [],
            'related_event_ids': [],
            'metadata': {},
            'created_at': now,
            'updated_at': now,
            **{k: v for k, v in dict(alert).items() if not (k == 'alert_id' and v is None)},
            'alert_id': len(self._runtime_alerts) + 1,
        }
        self._runtime_alerts.insert(0, item)
        return dict(item)

    async def get_latest_strategy_runtime_alert(self, strategy_id, alert_key=None, category=None, status='open_or_ack'):
        rows = await self.list_strategy_runtime_alerts(strategy_id=strategy_id, alert_key=alert_key, category=category, status=status, limit=1)
        return rows[0] if rows else None

    async def list_strategy_runtime_alerts(self, strategy_id=None, account_id=None, category=None, severity=None, status=None, alert_key=None, limit=50):
        rows = list(self._runtime_alerts)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if account_id:
            rows = [row for row in rows if row.get('account_id') == account_id]
        if category:
            rows = [row for row in rows if row.get('category') == category]
        if severity:
            rows = [row for row in rows if row.get('severity') == severity]
        if alert_key:
            rows = [row for row in rows if row.get('alert_key') == alert_key]
        if status:
            if status == 'open_or_ack':
                rows = [row for row in rows if row.get('status', 'open') in {'open', 'acknowledged'}]
            else:
                rows = [row for row in rows if row.get('status', 'open') == status]
        rows = sorted(rows, key=lambda row: row.get('updated_at') or row.get('created_at') or '', reverse=True)
        return [dict(row) for row in rows[:limit]]

    async def acknowledge_strategy_runtime_alert(self, alert_id, acknowledged_by=None, source='runtime_alerts'):
        now = datetime.now(timezone.utc).isoformat()
        for item in self._runtime_alerts:
            if int(item.get('alert_id')) == int(alert_id):
                if item.get('status') != 'resolved':
                    item['status'] = 'acknowledged'
                item['acknowledged_by'] = acknowledged_by
                item['acknowledged_at'] = item.get('acknowledged_at') or now
                item['updated_at'] = now
                item['metadata'] = {**dict(item.get('metadata') or {}), 'ack_source': source}
                return dict(item)
        return None

    async def resolve_strategy_runtime_alerts(self, strategy_id=None, alert_id=None, alert_key=None, category=None, resolution=None, source='runtime_alerts'):
        rows = []
        now = datetime.now(timezone.utc).isoformat()
        for item in self._runtime_alerts:
            if item.get('status', 'open') == 'resolved':
                continue
            if strategy_id and item.get('strategy_id') != strategy_id:
                continue
            if alert_id is not None and int(item.get('alert_id')) != int(alert_id):
                continue
            if alert_key and item.get('alert_key') != alert_key:
                continue
            if category and item.get('category') != category:
                continue
            item['status'] = 'resolved'
            item['resolved_at'] = item.get('resolved_at') or now
            item['updated_at'] = now
            item['metadata'] = {**dict(item.get('metadata') or {}), 'resolution': resolution or {}, 'resolution_source': source}
            rows.append(dict(item))
        return rows

    async def save_strategy_runtime_control(self, control):
        existing = self._runtime_controls.get(control['strategy_id'])
        item = {
            'id': (existing or {}).get('id', len(self._runtime_controls) + 1),
            **dict(existing or {}),
            **dict(control),
        }
        self._runtime_controls[item['strategy_id']] = item
        return dict(item)

    async def get_strategy_runtime_control(self, strategy_id):
        item = self._runtime_controls.get(strategy_id)
        return dict(item) if item else None

    async def list_strategy_runtime_controls(self, strategy_id=None, control_mode=None, status=None, limit=50):
        rows = list(self._runtime_controls.values())
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if control_mode:
            rows = [row for row in rows if row.get('control_mode') == control_mode]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_promotion_review(self, review):
        item = {'id': len(self._promotion_reviews) + 1, **dict(review)}
        self._promotion_reviews.append(item)
        return dict(item)

    async def get_latest_strategy_promotion_review(self, strategy_id):
        rows = [row for row in self._promotion_reviews if row.get('strategy_id') == strategy_id]
        return dict(rows[-1]) if rows else None

    async def list_strategy_promotion_reviews(self, strategy_id=None, status=None, limit=50):
        rows = list(self._promotion_reviews)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        rows = list(reversed(rows))
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_projection_snapshot(self, snapshot):
        item = {'id': len(self._projection_snapshots) + 1, **dict(snapshot)}
        self._projection_snapshots.append(item)
        return dict(item)

    async def get_latest_strategy_projection_snapshot(self, strategy_id, projection_type='strategy_state'):
        rows = [row for row in self._projection_snapshots if row.get('strategy_id') == strategy_id and row.get('projection_type', 'strategy_state') == projection_type]
        return dict(rows[-1]) if rows else None

    async def list_strategy_projection_snapshots(self, strategy_id=None, projection_type=None, limit=50):
        rows = list(self._projection_snapshots)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if projection_type:
            rows = [row for row in rows if row.get('projection_type') == projection_type]
        rows = list(reversed(rows))
        return [dict(row) for row in rows[:limit]]

    async def resolve_strategy_runtime_risk_event(self, event_id, resolution=None):
        for item in self._risk_events:
            if int(item.get('id')) == int(event_id):
                item['status'] = 'resolved'
                item['resolution'] = resolution or {}
                return dict(item)
        return None
