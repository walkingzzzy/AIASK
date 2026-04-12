from __future__ import annotations

from datetime import datetime, timezone

class _StrategyDBLifecycleMixin:
    async def list_strategies(self, status, strategy_type=None, limit=20, offset=0):
        allowed_statuses = self._expand_strategy_status_filter(status)
        return [
            dict(s, status=self._normalize_strategy_status(s.get("status")))
            for s in self._strategies.values()
            if allowed_statuses is None or self._normalize_strategy_status(s.get("status")) in allowed_statuses
        ][offset:offset + limit]

    async def get_strategy_metrics(self, sid):
        return self._metrics.get(sid, [])

    async def save_strategy_metrics(self, sid, period, metrics):
        self._metrics.setdefault(sid, []).append({"period": period, **metrics})

    async def get_reviews(self, sid, limit=10):
        return self._reviews

    async def save_review(self, sid, user_id, rating, comment):
        self._reviews.append({"strategy_id": sid, "user_id": user_id, "rating": rating})

    async def subscribe_strategy(self, sid, user_id):
        self._subs.add((sid, user_id))

    async def unsubscribe_strategy(self, sid, user_id):
        self._subs.discard((sid, user_id))

    async def is_subscribed(self, sid, user_id):
        return (sid, user_id) in self._subs

    async def list_user_subscriptions(self, user_id):
        return [{"strategy_id": s} for s, u in self._subs if u == user_id]

    async def get_signal_stats(self, sid, lookback_days=None, eps=None):
        return self._signal_stats.get(sid, {"hit_rate": {}, "forward_ic": {}, "forward_sharpe": {}, "total_signals": 0})

    async def get_signals(self, sid, start_date=None, end_date=None, limit=100):
        return []

    async def get_signals_public(self, sid, start_date=None, end_date=None, limit=100):
        return []

    async def get_klines(self, code, limit=200):
        return [
            {"date": f"2026-01-{(idx % 28) + 1:02d}", "open": 10 + idx * 0.1, "high": 10.2 + idx * 0.1, "low": 9.8 + idx * 0.1, "close": 10 + idx * 0.1, "volume": 1000 + idx}
            for idx in range(limit)
        ]

    async def list_stock_universe(self, limit=200, offset=0, min_market_cap=None, industry=None, market=None):
        rows = [
            {"code": "600519", "name": "贵州茅台", "industry": "白酒", "sector": "消费", "market": "SH", "market_cap": 2.1e12, "pe_ratio": 24.0, "pb_ratio": 9.2},
            {"code": "000858", "name": "五粮液", "industry": "白酒", "sector": "消费", "market": "SZ", "market_cap": 8.5e11, "pe_ratio": 18.5, "pb_ratio": 5.1},
            {"code": "300750", "name": "宁德时代", "industry": "电池", "sector": "新能源", "market": "SZ", "market_cap": 9.8e11, "pe_ratio": 21.0, "pb_ratio": 4.2},
            {"code": "601318", "name": "中国平安", "industry": "保险", "sector": "金融", "market": "SH", "market_cap": 7.0e11, "pe_ratio": 9.5, "pb_ratio": 1.1},
            {"code": "600036", "name": "招商银行", "industry": "银行", "sector": "金融", "market": "SH", "market_cap": 8.0e11, "pe_ratio": 6.2, "pb_ratio": 0.9},
            {"code": "000333", "name": "美的集团", "industry": "家电", "sector": "消费", "market": "SZ", "market_cap": 5.4e11, "pe_ratio": 12.0, "pb_ratio": 2.8},
        ]
        filtered = rows
        if industry:
            filtered = [row for row in filtered if industry in str(row.get("industry") or "")]
        if min_market_cap is not None:
            filtered = [row for row in filtered if float(row.get("market_cap") or 0.0) >= float(min_market_cap)]
        return filtered[offset: offset + limit]

    async def count_stock_universe(self, min_market_cap=None, industry=None, market=None):
        rows = await self.list_stock_universe(limit=1000, offset=0, min_market_cap=min_market_cap, industry=industry, market=market)
        return len(rows)

    async def get_financials(self, code, limit=4):
        return [{"code": code, "report_date": "2025-12-31", "revenue_growth": 0.12, "profit_growth": 0.15, "roe": 0.18}]

    async def get_factor_values(self, stock_codes, factor_name, start_date=None, end_date=None):
        rows = []
        for idx, code in enumerate(list(stock_codes or []), 1):
            rows.append({"stock_code": code, "factor_date": "2026-03-07", "factor_name": factor_name, "factor_value": 0.1 * idx})
        return rows

    async def count_strategies_by_type(self, status):
        counts = {}
        allowed_statuses = self._expand_strategy_status_filter(status)
        for s in self._strategies.values():
            if self._normalize_strategy_status(s.get("status")) in allowed_statuses:
                t = s.get("strategy_type", "unknown")
                counts[t] = counts.get(t, 0) + 1
        return counts

    async def save_strategy_quality_report(self, sid, report_type, report):
        now = datetime.now().isoformat()
        existing = self._quality_reports.get((sid, report_type)) or {}
        self._quality_reports[(sid, report_type)] = {
            **dict(report),
            "report_type": report_type,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
        }

    async def get_strategy_quality_report(self, sid, report_type="submission"):
        return self._quality_reports.get((sid, report_type))

    async def get_latest_strategy_quality_report(self, sid):
        rows = await self.list_strategy_quality_reports(sid, limit=1)
        return rows[0] if rows else None

    async def list_strategy_quality_reports(self, sid, limit=10):
        rows = [
            dict(report)
            for (strategy_id, _report_type), report in self._quality_reports.items()
            if strategy_id == sid
        ]
        rows.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return rows[:limit]

    async def list_strategy_status_events(
        self,
        sid,
        event_type=None,
        from_status=None,
        to_status=None,
        actor_id=None,
        start_time=None,
        end_time=None,
        limit=50,
    ):
        rows = list(reversed(self._events.get(sid, [])))
        start_dt = self._parse_event_time(start_time)
        end_dt = self._parse_event_time(end_time)
        filtered = []
        for item in rows:
            if event_type and item.get("event_type") != event_type:
                continue
            if from_status and item.get("from_status") != from_status:
                continue
            if to_status and item.get("to_status") != to_status:
                continue
            if actor_id and item.get("actor_id") != actor_id:
                continue
            created_at = self._parse_event_time(item.get("created_at"))
            if start_dt and (created_at is None or created_at < start_dt):
                continue
            if end_dt and (created_at is None or created_at > end_dt):
                continue
            filtered.append(dict(item))
        return filtered[: max(1, min(int(limit or 50), 200))]

    async def save_strategy_domain_event(self, event):
        item = {'id': len(self._domain_events) + 1, 'created_at': datetime.now(timezone.utc).isoformat(), **dict(event)}
        self._domain_events.append(item)
        return dict(item)

    async def list_strategy_domain_events(self, strategy_id=None, aggregate_type=None, event_type=None, source=None, correlation_id=None, limit=50):
        rows = list(reversed(self._domain_events))
        filtered = []
        for item in rows:
            if strategy_id is not None and item.get('strategy_id') != strategy_id:
                continue
            if aggregate_type and item.get('aggregate_type') != aggregate_type:
                continue
            if event_type and item.get('event_type') != event_type:
                continue
            if source and item.get('source') != source:
                continue
            if correlation_id and item.get('correlation_id') != correlation_id:
                continue
            filtered.append(dict(item))
        return filtered[: max(1, min(int(limit or 50), 500))]
