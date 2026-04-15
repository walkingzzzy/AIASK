from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from akshare_mcp.services.signal_tracker import SignalTracker


class _BackfillDB:
    def __init__(self):
        self.pending_calls = 0
        self.kline_calls: list[dict] = []
        self.saved_batches: list[list[dict]] = []

    async def get_pending_forward_returns(
        self,
        forward_days: int,
        limit: int = 500,
        after_signal_date=None,
        after_id=None,
    ):
        self.pending_calls += 1
        if self.pending_calls > 1:
            return []
        assert forward_days == 1
        assert limit == 50
        assert after_signal_date is None
        assert after_id in (None, 0)
        return [
            {
                "id": 11,
                "strategy_id": "sid_a",
                "signal_date": date(2026, 4, 2),
                "code": "600519",
                "signal": 1,
            },
            {
                "id": 12,
                "strategy_id": "sid_b",
                "signal_date": date(2026, 4, 3),
                "code": "600519",
                "signal": -1,
            },
        ]

    async def get_klines(self, code: str, start_date=None, end_date=None, limit=None):
        self.kline_calls.append(
            {
                "code": code,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
            }
        )
        return [
            {"date": "2026-04-02", "close": 10.0, "volume": 1000},
            {"date": "2026-04-03", "close": 11.0, "volume": 1000},
            {"date": "2026-04-04", "close": 12.0, "volume": 1000},
        ]

    async def save_forward_returns_batch(self, rows):
        self.saved_batches.append(list(rows))
        return len(rows)


@pytest.mark.asyncio
async def test_signal_tracker_backfills_pending_forward_returns_from_historical_series():
    tracker = SignalTracker()
    db = _BackfillDB()

    result = await tracker.backfill_forward_returns(
        db,
        forward_days_list=[1],
        batch_limit=50,
        max_rounds=3,
    )

    assert result["computed"] == 2
    assert result["windows"]["1D"]["computed"] == 2
    assert result["windows"]["1D"]["stalled"] is False
    assert db.kline_calls == [
        {
            "code": "600519",
            "start_date": "2026-04-02",
            "end_date": None,
            "limit": None,
        }
    ]
    assert len(db.saved_batches) == 1
    assert db.saved_batches[0][0]["signal_id"] == 11
    assert db.saved_batches[0][0]["forward_days"] == 1
    assert db.saved_batches[0][0]["actual_return"] == pytest.approx(0.1)
    assert db.saved_batches[0][1]["signal_id"] == 12
    assert db.saved_batches[0][1]["actual_return"] == pytest.approx(12.0 / 11.0 - 1.0)


class _RuntimeCycleDB:
    def __init__(self):
        self.saved_signal_strategy_ids: list[str] = []
        self.saved_signal_rows: list[dict] = []
        self.saved_signal_event_snapshots: list[dict] = []
        self.quality_report_calls: list[str] = []
        self.task_runs: list[dict] = []
        self.updated_task_runs: list[dict] = []
        self.domain_events: list[dict] = []
        self.submitted_reports = {
            "sid_observe": {"summary": {"submission_lane": "observe_incubation", "paper_lane_ready": True}},
            "sid_live": {"summary": {"submission_lane": "live_ready_review", "live_review_ready": True}},
            "sid_deferred": {"summary": {"submission_lane": "deferred_submission"}},
        }
        self.rows = {
            "listed": [
                {"id": "sid_listed", "strategy_type": "momentum", "params": {}},
            ],
            "incubating": [
                {"id": "sid_incubating", "strategy_type": "momentum", "params": {}},
            ],
            "submitted": [
                {"id": "sid_observe", "strategy_type": "momentum", "params": {"incubation_budget": {"track": "observe_incubation"}}},
                {"id": "sid_live", "strategy_type": "momentum", "params": {}},
                {"id": "sid_deferred", "strategy_type": "momentum", "params": {"incubation_budget": {"track": "deferred_budget_queue"}}},
            ],
        }

    async def save_strategy_task_run(self, payload):
        self.task_runs.append(dict(payload))
        return {"id": 1, "trace_id": "trace_runtime_cycle"}

    async def list_strategies(self, status, limit=200):
        return list(self.rows.get(status, []))

    async def get_strategy_runtime_control(self, strategy_id):
        return {"control_mode": "active", "strategy_id": strategy_id}

    async def save_signals(self, strategy_id, signal_date, rows):
        self.saved_signal_rows.extend(list(rows or []))
        self.saved_signal_strategy_ids.append(strategy_id)
        return len(list(rows or []))

    async def save_strategy_signal_event_snapshot(self, payload):
        snapshot = dict(payload or {})
        self.saved_signal_event_snapshots.append(snapshot)
        return snapshot

    async def get_strategy_quality_report(self, strategy_id, report_type="submission"):
        self.quality_report_calls.append(strategy_id)
        return self.submitted_reports.get(strategy_id)

    async def update_strategy_task_run(self, task_run_id, **kwargs):
        self.updated_task_runs.append({"id": task_run_id, **kwargs})

    async def save_strategy_domain_event(self, payload):
        self.domain_events.append(dict(payload))


class _RuntimeControlService:
    @staticmethod
    def is_blocking_mode(control_mode):
        return False


class _PipelineService:
    def __init__(self):
        self.batch_calls: list[dict] = []
        self.strategy_calls: list[dict] = []

    async def run_batch(self, db, *, statuses=None, limit=200, source="runtime_cycle", auto_apply_review=True):
        self.batch_calls.append(
            {
                "statuses": list(statuses or []),
                "limit": limit,
                "source": source,
                "auto_apply_review": auto_apply_review,
            }
        )
        return {"count": 1, "auto_promoted": 0}

    async def run_strategy(self, db, strategy, *, source="manual", auto_apply_review=False):
        self.strategy_calls.append(
            {
                "strategy_id": strategy.get("id"),
                "source": source,
                "auto_apply_review": auto_apply_review,
            }
        )
        return {"strategy_id": strategy.get("id"), "snapshot": {"pipeline_stage": "observe"}}


class _IncubationService:
    def __init__(self):
        self.processed_strategy_ids: list[str] = []

    async def process_strategies(self, db, strategies, signal_date=None):
        self.processed_strategy_ids = [str(item.get("id")) for item in list(strategies or [])]
        return {
            "orders_created": 0,
            "orders_filled": 0,
            "nav_snapshots": 0,
            "metrics_recorded": len(self.processed_strategy_ids),
        }


class _RiskService:
    async def scan(self, db, strategies, enforce_actions=True):
        return {"event_count": 0, "action_count": 0}


class _VectorGovernanceService:
    async def reconcile_registry(self, db, index_name="strategy_behavior", profile_type="behavior"):
        return {"registry_updated": 0}


class _DomainProjectionService:
    async def rebuild_batch(self, db, statuses=None, limit=200, source="signal_tracker"):
        return {"count": 0}


class _MomentumStrategy:
    def set_parameters(self, params):
        self.params = dict(params or {})

    def generate_signals(self, closes, volumes=None):
        return [0, 1]


class _CompiledDslStrategy:
    def set_parameters(self, params):
        self.params = dict(params or {})

    def generate_signal_events_from_klines(self, klines):
        if not klines:
            return []
        return [{"index": len(klines) - 1, "signal": 1, "action": "enter"}]


class _CompiledDslLatestExitStrategy:
    def set_parameters(self, params):
        self.params = dict(params or {})

    def generate_signal_events_from_klines(self, klines):
        if len(klines) < 5:
            return []
        return [
            {"index": len(klines) - 5, "signal": 1, "action": "enter"},
            {"index": len(klines) - 2, "signal": -1, "action": "exit", "reason": "primary_stop_band"},
        ]


@pytest.mark.asyncio
async def test_signal_tracker_includes_runtime_submitted_lanes(monkeypatch):
    tracker = SignalTracker()
    db = _RuntimeCycleDB()
    pipeline_service = _PipelineService()
    incubation_service = _IncubationService()

    monkeypatch.setattr(
        "akshare_mcp.storage.get_db",
        lambda: db,
    )
    monkeypatch.setattr(
        "akshare_mcp.services.backtest.strategy_registry.StrategyRegistry.get",
        lambda _strategy_type: _MomentumStrategy,
    )
    monkeypatch.setattr(
        "akshare_mcp.services.factor_scheduler.DEFAULT_UNIVERSE",
        ["600519"],
    )
    monkeypatch.setattr(
        tracker,
        "_get_klines_with_fallback",
        AsyncMock(
            return_value=[
                {"date": f"2026-04-{idx + 1:02d}", "close": float(idx + 1), "volume": 1000}
                for idx in range(30)
            ]
        ),
    )
    monkeypatch.setattr(
        tracker,
        "backfill_forward_returns",
        AsyncMock(return_value={"computed": 0}),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.runtime_control.get_strategy_runtime_control_service",
        lambda: _RuntimeControlService(),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.incubation.get_strategy_incubation_service",
        lambda: incubation_service,
    )
    monkeypatch.setattr(
        "akshare_mcp.services.runtime_risk.get_strategy_runtime_risk_service",
        lambda: _RiskService(),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.incubation_pipeline.get_strategy_incubation_pipeline_service",
        lambda: pipeline_service,
    )
    monkeypatch.setattr(
        "akshare_mcp.tools.managers.strategy_manager._lifecycle_scan",
        AsyncMock(return_value={"transitions": []}),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.vector_governance.get_strategy_vector_governance_service",
        lambda: _VectorGovernanceService(),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.domain_projection.get_strategy_domain_projection_service",
        lambda: _DomainProjectionService(),
    )

    result = await tracker.run_once()

    assert set(db.saved_signal_strategy_ids) == {
        "sid_listed",
        "sid_incubating",
        "sid_observe",
        "sid_live",
    }
    assert "sid_deferred" not in db.saved_signal_strategy_ids
    assert set(incubation_service.processed_strategy_ids) == {
        "sid_listed",
        "sid_incubating",
        "sid_observe",
        "sid_live",
    }
    assert pipeline_service.batch_calls == [
        {
            "statuses": ["incubating"],
            "limit": 200,
            "source": "signal_tracker",
            "auto_apply_review": True,
        }
    ]
    assert pipeline_service.strategy_calls == [
        {
            "strategy_id": "sid_observe",
            "source": "signal_tracker_submitted",
            "auto_apply_review": False,
        },
        {
            "strategy_id": "sid_live",
            "source": "signal_tracker_submitted",
            "auto_apply_review": False,
        },
    ]
    assert result["signals_generated"] == 4
    assert result["signal_event_snapshots"] == 4
    assert result["submitted_runtime_pipeline_snapshots"] == 2


@pytest.mark.asyncio
async def test_signal_tracker_prefers_strategy_target_symbols_over_default_universe(monkeypatch):
    tracker = SignalTracker()
    db = _RuntimeCycleDB()
    db.rows["listed"] = [
        {
            "id": "sid_targeted",
            "strategy_type": "momentum",
            "params": {
                "target_symbols": ["688981"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["688981"]},
            },
        }
    ]
    db.rows["incubating"] = []
    db.rows["submitted"] = []
    pipeline_service = _PipelineService()
    incubation_service = _IncubationService()

    monkeypatch.setattr(
        "akshare_mcp.storage.get_db",
        lambda: db,
    )
    monkeypatch.setattr(
        "akshare_mcp.services.backtest.strategy_registry.StrategyRegistry.get",
        lambda _strategy_type: _MomentumStrategy,
    )
    monkeypatch.setattr(
        "akshare_mcp.services.factor_scheduler.DEFAULT_UNIVERSE",
        ["600519"],
    )
    get_klines_mock = AsyncMock(
        return_value=[
            {"date": f"2026-04-{idx + 1:02d}", "close": float(idx + 1), "volume": 1000}
            for idx in range(30)
        ]
    )
    monkeypatch.setattr(
        tracker,
        "_get_klines_with_fallback",
        get_klines_mock,
    )
    monkeypatch.setattr(
        tracker,
        "backfill_forward_returns",
        AsyncMock(return_value={"computed": 0}),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.runtime_control.get_strategy_runtime_control_service",
        lambda: _RuntimeControlService(),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.incubation.get_strategy_incubation_service",
        lambda: incubation_service,
    )
    monkeypatch.setattr(
        "akshare_mcp.services.runtime_risk.get_strategy_runtime_risk_service",
        lambda: _RiskService(),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.incubation_pipeline.get_strategy_incubation_pipeline_service",
        lambda: pipeline_service,
    )
    monkeypatch.setattr(
        "akshare_mcp.tools.managers.strategy_manager._lifecycle_scan",
        AsyncMock(return_value={"transitions": []}),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.vector_governance.get_strategy_vector_governance_service",
        lambda: _VectorGovernanceService(),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.domain_projection.get_strategy_domain_projection_service",
        lambda: _DomainProjectionService(),
    )

    result = await tracker.run_once()

    queried_codes = [call.args[1] for call in get_klines_mock.await_args_list]
    assert queried_codes == ["688981"]
    assert db.saved_signal_strategy_ids == ["sid_targeted"]
    assert result["signals_generated"] == 1


@pytest.mark.asyncio
async def test_signal_tracker_prefers_compiled_dsl_runtime_instance(monkeypatch):
    tracker = SignalTracker()
    db = _RuntimeCycleDB()
    db.rows["listed"] = [
        {
            "id": "sid_compiled_dsl",
            "strategy_type": "ma_cross",
            "params": {
                "target_symbols": ["688981"],
                "dsl": {
                    "entry": {"all": []},
                    "exit": {"any": []},
                    "metadata": {"target_symbols": ["688981"]},
                },
            },
        }
    ]
    db.rows["incubating"] = []
    db.rows["submitted"] = []
    pipeline_service = _PipelineService()
    incubation_service = _IncubationService()

    monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
    monkeypatch.setattr(
        "akshare_mcp.services.backtest.strategy_registry.StrategyRegistry.create_runtime_strategy",
        lambda _strategy_type, _params=None: (_CompiledDslStrategy(), "compiled_dsl"),
    )
    monkeypatch.setattr("akshare_mcp.services.factor_scheduler.DEFAULT_UNIVERSE", ["600519"])
    monkeypatch.setattr(
        tracker,
        "_get_klines_with_fallback",
        AsyncMock(
            return_value=[
                {"date": f"2026-04-{idx + 1:02d}", "open": 10.0 + idx, "high": 10.4 + idx, "low": 9.8 + idx, "close": 10.2 + idx, "volume": 1000 + idx}
                for idx in range(30)
            ]
        ),
    )
    monkeypatch.setattr(tracker, "backfill_forward_returns", AsyncMock(return_value={"computed": 0}))
    monkeypatch.setattr(
        "akshare_mcp.services.runtime_control.get_strategy_runtime_control_service",
        lambda: _RuntimeControlService(),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.incubation.get_strategy_incubation_service",
        lambda: incubation_service,
    )
    monkeypatch.setattr(
        "akshare_mcp.services.runtime_risk.get_strategy_runtime_risk_service",
        lambda: _RiskService(),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.incubation_pipeline.get_strategy_incubation_pipeline_service",
        lambda: pipeline_service,
    )
    monkeypatch.setattr(
        "akshare_mcp.tools.managers.strategy_manager._lifecycle_scan",
        AsyncMock(return_value={"transitions": []}),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.vector_governance.get_strategy_vector_governance_service",
        lambda: _VectorGovernanceService(),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.domain_projection.get_strategy_domain_projection_service",
        lambda: _DomainProjectionService(),
    )

    result = await tracker.run_once()

    assert result["signals_generated"] == 1
    assert db.saved_signal_strategy_ids == ["sid_compiled_dsl"]
    assert len(db.saved_signal_rows) == 1
    assert db.saved_signal_rows[0]["code"] == "688981"
    assert db.saved_signal_rows[0]["signal"] == 1
    assert db.saved_signal_rows[0]["execution_semantic_mode"] == "compiled_dsl"
    assert db.saved_signal_rows[0]["action_source"] == "dsl_entry"
    assert db.saved_signal_rows[0]["event_action"] == "enter"
    assert len(db.saved_signal_event_snapshots) == 1
    assert db.saved_signal_event_snapshots[0]["latest_bar_signal"] == 1
    assert db.saved_signal_event_snapshots[0]["latest_event_action_source"] == "dsl_entry"


@pytest.mark.asyncio
async def test_signal_tracker_persists_recent_event_snapshot_when_latest_bar_signal_is_zero(monkeypatch):
    tracker = SignalTracker()
    db = _RuntimeCycleDB()
    db.rows["listed"] = [
        {
            "id": "sid_recent_exit",
            "strategy_type": "ma_cross",
            "params": {
                "target_symbols": ["688981"],
                "dsl": {
                    "entry": {"all": []},
                    "exit": {"any": []},
                    "metadata": {"target_symbols": ["688981"]},
                },
            },
        }
    ]
    db.rows["incubating"] = []
    db.rows["submitted"] = []
    pipeline_service = _PipelineService()
    incubation_service = _IncubationService()

    monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
    monkeypatch.setattr(
        "akshare_mcp.services.backtest.strategy_registry.StrategyRegistry.create_runtime_strategy",
        lambda _strategy_type, _params=None: (_CompiledDslLatestExitStrategy(), "compiled_dsl"),
    )
    monkeypatch.setattr("akshare_mcp.services.factor_scheduler.DEFAULT_UNIVERSE", ["688981"])
    monkeypatch.setattr(
        tracker,
        "_get_klines_with_fallback",
        AsyncMock(
            return_value=[
                {"date": f"2026-04-{idx + 1:02d}", "open": 10.0 + idx, "high": 10.4 + idx, "low": 9.8 + idx, "close": 10.2 + idx, "volume": 1000 + idx}
                for idx in range(30)
            ]
        ),
    )
    monkeypatch.setattr(tracker, "backfill_forward_returns", AsyncMock(return_value={"computed": 0}))
    monkeypatch.setattr(
        "akshare_mcp.services.runtime_control.get_strategy_runtime_control_service",
        lambda: _RuntimeControlService(),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.incubation.get_strategy_incubation_service",
        lambda: incubation_service,
    )
    monkeypatch.setattr(
        "akshare_mcp.services.runtime_risk.get_strategy_runtime_risk_service",
        lambda: _RiskService(),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.incubation_pipeline.get_strategy_incubation_pipeline_service",
        lambda: pipeline_service,
    )
    monkeypatch.setattr(
        "akshare_mcp.tools.managers.strategy_manager._lifecycle_scan",
        AsyncMock(return_value={"transitions": []}),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.vector_governance.get_strategy_vector_governance_service",
        lambda: _VectorGovernanceService(),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.domain_projection.get_strategy_domain_projection_service",
        lambda: _DomainProjectionService(),
    )

    result = await tracker.run_once()

    assert result["signals_generated"] == 0
    assert result["signal_event_snapshots"] == 1
    assert db.saved_signal_rows == []
    assert len(db.saved_signal_event_snapshots) == 1
    snapshot = db.saved_signal_event_snapshots[0]
    assert snapshot["latest_bar_signal"] == 0
    assert snapshot["latest_event_signal"] == -1
    assert snapshot["latest_event_action"] == "exit"
    assert snapshot["latest_event_action_source"] == "runtime_playbook_stop"
    assert snapshot["latest_event_reason"] == "primary_stop_band"
    assert snapshot["latest_exit_date"] == "2026-04-29"
    assert snapshot["recent_events"][-1]["signal"] == -1
