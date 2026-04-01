"""Shared strategy-factory test support helpers."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone

from ._strategy_factory_test_support_experiments import _StrategyDBExperimentMixin
from ._strategy_factory_test_support_lifecycle import _StrategyDBLifecycleMixin
from ._strategy_factory_test_support_runtime import _StrategyDBRuntimeMixin
from ._strategy_factory_test_support_vector import _StrategyDBVectorMixin

class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn
        return _decorator


class _StrategyConn:
    """模拟策略管理器所需的DB连接"""
    def __init__(self):
        self.strategies = {}
        self.metrics = {}
        self.reviews = []
        self.subscriptions = set()

    async def fetchrow(self, query, *args):
        if 'FROM strategies WHERE id' in query:
            return self.strategies.get(args[0])
        return None

    async def fetch(self, query, *args):
        if 'FROM strategies' in query and 'status' in query:
            return [s for s in self.strategies.values()
                    if s.get("status") == args[0]]
        if 'FROM strategy_metrics' in query:
            sid = args[0]
            return self.metrics.get(sid, [])
        if 'FROM strategy_reviews' in query:
            return self.reviews
        return []

    async def fetchval(self, query, *args):
        return 0

    async def execute(self, query, *args):
        if 'INSERT INTO strategies' in query or 'UPSERT' in query.upper():
            pass
        elif 'UPDATE strategies SET status' in query:
            sid = args[1] if len(args) > 1 else args[0]
            if sid in self.strategies:
                self.strategies[sid]["status"] = args[0]



class _StrategyDB(
    _StrategyDBLifecycleMixin,
    _StrategyDBRuntimeMixin,
    _StrategyDBVectorMixin,
    _StrategyDBExperimentMixin,
):
    def __init__(self):
        self._pgvector_enabled = False
        self._strategies = {}
        self._metrics = {}
        self._reviews = []
        self._subs = set()
        self._quality_reports = {}
        self._events = {}
        self._signal_stats = {}
        self._factory_runs = []
        self._daily_snapshots = []
        self._factory_event_clusters = []
        self._factory_theme_definitions = []
        self._factory_company_theme_exposures = []
        self._factory_event_signals = []
        self._factory_task_evidence = []
        self._factory_market_internals = []
        self._north_fund_summary = None
        self._paper_accounts = {}
        self._paper_orders = []
        self._paper_positions = {}
        self._paper_trades = []
        self._paper_nav = {}
        self._incubation_accounts = []
        self._incubation_metrics = []
        self._incubation_pipeline_snapshots = []
        self._risk_events = []
        self._runtime_risk_snapshots = []
        self._vector_profiles = []
        self._vector_profile_store = []
        self._vector_indexes = []
        self._vector_index_snapshots = []
        self._vector_index_items = []
        self._vector_index_item_store = []
        self._vector_hnsw_indexes = []
        self._experiments = {}
        self._task_runs = []
        self._domain_events = []
        self._runtime_controls = {}
        self._runtime_alerts = []
        self._promotion_reviews = []
        self._projection_snapshots = []

    def supports_pgvector(self):
        return bool(self._pgvector_enabled)

    def get_vector_backend(self):
        return 'pgvector' if self.supports_pgvector() else 'index'

    @staticmethod
    def _sanitize_index_part(value):
        text = ''.join(ch if str(ch).isalnum() else '_' for ch in str(value or 'na'))
        text = text.strip('_')
        return text or 'na'

    @staticmethod
    def _timestamp_key(value):
        if value is None:
            return ''
        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).strip()
            if not text:
                return ''
            try:
                dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
            except ValueError:
                return text
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    @classmethod
    def _best_timestamp(cls, row):
        for key in ('activated_at', 'built_at', 'updated_at', 'created_at', 'last_seen'):
            value = row.get(key)
            if value is not None:
                return cls._timestamp_key(value)
        return ''

    def acquire(self):
        class _Acq:
            def __init__(self, conn):
                self.conn = conn
            async def __aenter__(self):
                return self.conn
            async def __aexit__(self, *a):
                return False
        return _Acq(_StrategyConn())

    @staticmethod
    def _normalize_strategy_status(status):
        normalized = str(status or "").strip().lower()
        return "listed" if normalized == "published" else normalized

    @classmethod
    def _expand_strategy_status_filter(cls, status):
        if status is None:
            return None
        raw_values = status if isinstance(status, (list, tuple, set)) else [status]
        allowed = set()
        for item in raw_values:
            normalized = cls._normalize_strategy_status(item)
            if normalized in {"", "all", "*"}:
                return None
            if normalized == "visible":
                allowed.update({"incubating", "listed", "published"})
                continue
            if normalized == "listed":
                allowed.update({"listed", "published"})
                continue
            allowed.add(normalized)
        return allowed or None

    async def save_strategy(self, data):
        item = dict(data)
        item["status"] = self._normalize_strategy_status(item.get("status", "draft"))
        self._strategies[data["id"]] = item
        return item

    async def get_strategy(self, sid):
        strategy = self._strategies.get(sid)
        if not strategy:
            return None
        item = dict(strategy)
        item["status"] = self._normalize_strategy_status(item.get("status"))
        return item

    async def update_strategy_status(self, sid, status, actor_id="system", reason=None, metadata=None):
        if sid in self._strategies:
            previous = self._normalize_strategy_status(self._strategies[sid].get("status"))
            normalized = self._normalize_strategy_status(status)
            self._strategies[sid]["status"] = normalized
            if previous != normalized:
                created_at = datetime.now(timezone.utc).isoformat()
                self._events.setdefault(sid, []).append({
                    "from_status": previous,
                    "to_status": normalized,
                    "event_type": "status_change",
                    "actor_id": actor_id,
                    "reason": reason,
                    "metadata": metadata or {},
                    "created_at": created_at,
                })
                self._domain_events.append({
                    'id': len(self._domain_events) + 1,
                    'strategy_id': sid,
                    'aggregate_type': 'strategy',
                    'aggregate_id': sid,
                    'event_type': 'strategy.status_changed',
                    'source': actor_id,
                    'severity': 'info',
                    'correlation_id': (metadata or {}).get('task_run_id') if isinstance(metadata, dict) else None,
                    'payload': {'from_status': previous, 'to_status': normalized, 'reason': reason, 'metadata': metadata or {}},
                    'created_at': created_at,
                })

    @staticmethod
    def _parse_event_time(value):
        if not value:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
