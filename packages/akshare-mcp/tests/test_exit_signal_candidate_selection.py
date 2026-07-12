"""P0-B: exit signal candidate selection and intake exit_policy readiness."""

from __future__ import annotations

import asyncio
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from akshare_mcp.services.incubation_factory.intake import IncubationIntake
from akshare_mcp.services.incubation_factory.runner import IncubationFactoryRunner


def _run(coro):
    return asyncio.run(coro)


class _FakeDb:
    def __init__(
        self,
        *,
        positions: Optional[list[dict[str, Any]]] = None,
        orders: Optional[list[dict[str, Any]]] = None,
        signals: Optional[list[dict[str, Any]]] = None,
    ):
        self._positions = list(positions or [])
        self._orders = list(orders or [])
        self._signals = list(signals or [])

    async def list_strategy_trade_positions(self, strategy_id=None, status=None, limit=500, **kwargs):
        sid = strategy_id or kwargs.get("strategy_id")
        rows = [dict(p) for p in self._positions if str(p.get("strategy_id") or sid) == str(sid or p.get("strategy_id"))]
        # if positions don't carry strategy_id, return all (tests set one strategy)
        if not any(p.get("strategy_id") for p in self._positions):
            rows = [dict(p) for p in self._positions]
        if status:
            rows = [p for p in rows if str(p.get("status") or "open").lower() == str(status).lower()]
        return rows[:limit]

    async def list_strategy_paper_orders(self, strategy_id=None, limit=1000, **kwargs):
        sid = strategy_id or kwargs.get("strategy_id")
        rows = [dict(o) for o in self._orders]
        if sid and any(o.get("strategy_id") for o in self._orders):
            rows = [o for o in rows if str(o.get("strategy_id")) == str(sid)]
        return rows[:limit]

    async def get_signals(self, strategy_id=None, limit=2000, **kwargs):
        sid = strategy_id or kwargs.get("strategy_id")
        rows = [dict(s) for s in self._signals]
        if sid and any(s.get("strategy_id") for s in self._signals):
            rows = [s for s in rows if str(s.get("strategy_id")) == str(sid)]
        return rows[:limit]


def _strategy(sid: str = "s1", *, with_exit_policy: bool = False, holding_days: int = 0) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": sid, "name": f"strat-{sid}"}
    if with_exit_policy:
        payload["runtime_playbook"] = {
            "exit_policy": {
                "time_stop_days": 5,
                "stop_loss_pct": 0.08,
            }
        }
    if holding_days > 0:
        payload["holding_window"] = {"max_days": holding_days}
    return payload


def test_exit_policy_readiness_detects_missing():
    ready = IncubationIntake._exit_policy_readiness({"id": "s1"})
    assert ready["has_exit_policy"] is False
    assert "missing_exit_policy" in ready["blockers"]


def test_exit_policy_readiness_accepts_runtime_playbook():
    ready = IncubationIntake._exit_policy_readiness(
        {
            "id": "s1",
            "runtime_playbook": {"exit_policy": {"time_stop_days": 3}},
        }
    )
    assert ready["has_exit_policy"] is True
    assert ready["blockers"] == []


def test_exit_policy_readiness_accepts_holding_window_fallback():
    ready = IncubationIntake._exit_policy_readiness(
        {"id": "s1", "holding_window": {"max_days": 10}}
    )
    assert ready["has_exit_policy"] is True
    assert ready["has_time_stop"] is True


def test_scan_and_accept_skips_missing_exit_policy():
    async def _body():
        intake = IncubationIntake()
        db = MagicMock()
        db.list_strategies = AsyncMock(
            return_value=[
                {"id": "s-bad", "name": "no-exit", "status": "incubating"},
                {
                    "id": "s-good",
                    "name": "with-exit",
                    "status": "incubating",
                    "runtime_playbook": {"exit_policy": {"time_stop_days": 5}},
                },
            ]
        )
        db.get_strategy_incubation_account = AsyncMock(return_value=None)
        db.list_paper_observation_strategies = AsyncMock(return_value=[])
        # suppress other side channels
        intake._recognize_diagnostic_observation = AsyncMock(return_value={"scanned": 0})
        intake._recognize_gate3_record_only_candidates = AsyncMock(return_value={"scanned": 0})
        intake._record_acceptance_event = AsyncMock()
        intake._strategy_explanation = lambda *a, **k: {}

        ensure = AsyncMock(
            return_value={"account": {"account_id": "acc-1", "id": "acc-1"}}
        )
        mock_service = MagicMock()
        mock_service.ensure_account = ensure

        import akshare_mcp.services.incubation_factory.intake as intake_mod

        # patch get_strategy_incubation_service used inside scan_and_accept
        original_import = None

        class _Svc:
            @staticmethod
            def ensure_account(*args, **kwargs):
                return ensure(*args, **kwargs)

        # Monkey via module import inside function: replace after import path
        from unittest.mock import patch

        with patch(
            "akshare_mcp.services.incubation.get_strategy_incubation_service",
            return_value=MagicMock(ensure_account=ensure),
        ):
            # The import is: from ..incubation import get_strategy_incubation_service
            with patch.object(
                __import__(
                    "akshare_mcp.services.incubation",
                    fromlist=["get_strategy_incubation_service"],
                ),
                "get_strategy_incubation_service",
                return_value=MagicMock(ensure_account=ensure),
            ):
                result = await intake.scan_and_accept(db)

        assert result["exit_policy_blocker_count"] == 1
        assert result["accepted"] == 1
        assert result["skipped"] == 1
        assert any(x.get("strategy_id") == "s-bad" for x in result["exit_policy_blocker_examples"])
        ensure.assert_awaited()
        # only good strategy accepted
        assert result["details"][0]["strategy_id"] == "s-good"

    _run(_body())


def test_select_open_plus_exit_signal_without_pending_sell():
    async def _body():
        runner = IncubationFactoryRunner(dry_run=True)
        db = _FakeDb(
            positions=[{"id": "p1", "code": "000001", "status": "open"}],
            orders=[],
            signals=[{"code": "000001", "signal": -1}],
        )
        selected, total = await runner._select_exit_signal_candidates(
            db,
            strategies=[_strategy("s1")],
            limit=50,
        )
        assert total == 1
        assert len(selected) == 1
        assert selected[0]["id"] == "s1"
        assert selected[0]["_exit_signal_count"] == 1
        assert "000001" in selected[0]["_exit_codes"]

    _run(_body())


def test_select_open_plus_exit_policy_without_signal():
    async def _body():
        runner = IncubationFactoryRunner(dry_run=True)
        db = _FakeDb(
            positions=[{"id": "p1", "code": "600000", "status": "open"}],
            orders=[],
            signals=[],  # no exit signals
        )
        selected, total = await runner._select_exit_signal_candidates(
            db,
            strategies=[_strategy("s2", with_exit_policy=True)],
            limit=50,
        )
        assert total == 1
        assert selected[0]["_has_exit_policy"] is True
        assert selected[0]["_exit_signal_count"] == 0
        assert selected[0]["_exit_codes"] == ["600000"]

    _run(_body())


def test_select_blocks_when_pending_sell_covers_all_codes():
    async def _body():
        runner = IncubationFactoryRunner(dry_run=True)
        db = _FakeDb(
            positions=[
                {"id": "p1", "code": "000001", "status": "open"},
                {"id": "p2", "code": "000002", "status": "open"},
            ],
            orders=[
                {"code": "000001", "direction": "sell", "status": "pending"},
                {"code": "000002", "direction": "sell", "status": "submitted"},
            ],
            signals=[{"code": "000001", "signal": -1}],
        )
        selected, total = await runner._select_exit_signal_candidates(
            db,
            strategies=[_strategy("s3", with_exit_policy=True)],
            limit=50,
        )
        assert total == 0
        assert selected == []
        funnel = runner._last_exit_selection_funnel
        assert funnel["blocked_pending_exit_order"] == 1

    _run(_body())


def test_select_allows_other_code_when_one_has_pending_sell():
    async def _body():
        runner = IncubationFactoryRunner(dry_run=True)
        db = _FakeDb(
            positions=[
                {"id": "p1", "code": "000001", "status": "open"},
                {"id": "p2", "code": "000002", "status": "open"},
            ],
            orders=[
                {"code": "000001", "direction": "sell", "status": "pending"},
            ],
            signals=[{"code": "000002", "event_action": "exit"}],
        )
        selected, total = await runner._select_exit_signal_candidates(
            db,
            strategies=[_strategy("s4")],
            limit=50,
        )
        assert total == 1
        assert selected[0]["_exit_codes"] == ["000002"]
        assert "000001" not in selected[0]["_exit_codes"]

    _run(_body())


def test_filled_historical_sell_does_not_block_open_position():
    """Regression: old logic skipped if any sell order ever existed."""

    async def _body():
        runner = IncubationFactoryRunner(dry_run=True)
        db = _FakeDb(
            positions=[{"id": "p1", "code": "000001", "status": "open"}],
            orders=[
                # historical filled sell on same or other code must NOT block
                {"code": "000001", "direction": "sell", "status": "filled"},
                {"code": "600519", "direction": "sell", "status": "filled"},
            ],
            signals=[{"code": "000001", "signal": -1}],
        )
        selected, total = await runner._select_exit_signal_candidates(
            db,
            strategies=[_strategy("s5")],
            limit=50,
        )
        assert total == 1
        assert selected[0]["_exit_codes"] == ["000001"]
        # funnel still records filled exits in snapshot
        snap = selected[0]["_exit_funnel"]
        assert snap["filled_exit_order_count"] == 2
        assert snap["pending_exit_order_count"] == 0

    _run(_body())


def test_no_open_positions_not_selected():
    async def _body():
        runner = IncubationFactoryRunner(dry_run=True)
        db = _FakeDb(
            positions=[],
            orders=[],
            signals=[{"code": "000001", "signal": -1}],
        )
        selected, total = await runner._select_exit_signal_candidates(
            db,
            strategies=[_strategy("s6", with_exit_policy=True)],
            limit=50,
        )
        assert total == 0
        assert selected == []

    _run(_body())


def test_open_without_exit_trigger_blocked():
    async def _body():
        runner = IncubationFactoryRunner(dry_run=True)
        db = _FakeDb(
            positions=[{"id": "p1", "code": "000001", "status": "open"}],
            orders=[],
            signals=[{"code": "000001", "signal": 1}],  # entry only
        )
        selected, total = await runner._select_exit_signal_candidates(
            db,
            strategies=[_strategy("s7")],  # no exit policy
            limit=50,
        )
        assert total == 0
        assert runner._last_exit_selection_funnel["blocked_no_exit_trigger"] == 1

    _run(_body())


def test_exit_funnel_snapshot_metrics():
    runner = IncubationFactoryRunner(dry_run=True)
    snap = runner._exit_funnel_snapshot(
        open_positions=[{"code": "A"}, {"code": "B"}],
        exit_signal_count=2,
        has_exit_policy=True,
        exit_orders=[
            {"code": "A", "direction": "sell", "status": "pending"},
            {"code": "B", "direction": "sell", "status": "filled"},
        ],
    )
    assert snap["open_position_count"] == 2
    assert snap["pending_exit_order_count"] == 1
    assert snap["filled_exit_order_count"] == 1
    assert snap["codes_needing_exit"] == ["B"]
    assert snap["eligible_for_exit_order"] is True


def test_run_exit_uses_created_count_field():
    """force_close returns created_count; runner must map it (not orders_created)."""

    async def _body():
        runner = IncubationFactoryRunner(dry_run=False)
        # pretoggle path: paper_execution_backlog_enabled
        import akshare_mcp.config._strategy_factory_toggles as toggles

        # Force backlog enabled and batch limit
        original_enabled = toggles.paper_execution_backlog_enabled
        original_limit = toggles.paper_execution_backlog_batch_limit
        toggles.paper_execution_backlog_enabled = lambda: True
        toggles.paper_execution_backlog_batch_limit = lambda: 10
        try:
            strategy = _strategy("s8", with_exit_policy=True)
            strategy["_exit_signal_count"] = 1
            strategy["_open_positions"] = [{"code": "000001", "status": "open"}]
            strategy["_has_exit_policy"] = True
            strategy["_exit_codes"] = ["000001"]
            strategy["_exit_funnel"] = {
                "eligible_for_exit_order": True,
                "codes_needing_exit": ["000001"],
            }
            strategy["_exit_selection_funnel_totals"] = {
                "eligible_open_with_exit": 1,
                "eligible_exit_code_count": 1,
            }

            async def _select(db, *, strategies=None, limit=200):
                return [strategy], 1

            runner._select_exit_signal_candidates = _select  # type: ignore

            close_calls = {}

            class _Incubation:
                async def force_close_open_positions(self, db, strategy=None, as_of=None, **kwargs):
                    close_calls["args"] = (strategy, as_of)
                    close_calls["kwargs"] = kwargs
                    return {
                        "created_count": 2,
                        "skipped_count": 0,
                        "skip_reason_counts": {},
                    }

                async def settle_orders(self, db, strategy=None, as_of=None, **kwargs):
                    return {"filled_count": 1, "positions_closed": 1}

            from unittest.mock import patch

            # runner does: from ..incubation import get_strategy_incubation_service
            with patch(
                "akshare_mcp.services.incubation.get_strategy_incubation_service",
                return_value=_Incubation(),
            ):
                result = await runner._run_exit_signal_paper_execution(
                    MagicMock(),
                    strategies=[strategy],
                )

            assert result["exit_orders_created"] == 2
            assert result["exit_orders_filled"] == 1
            assert result["positions_closed"] == 1
            assert result["exit_order_conversion"] == 1.0
            assert result["exit_order_overcreation_count"] == 1
            assert result["items"][0]["orders_created"] == 2
        finally:
            toggles.paper_execution_backlog_enabled = original_enabled
            toggles.paper_execution_backlog_batch_limit = original_limit

    _run(_body())
