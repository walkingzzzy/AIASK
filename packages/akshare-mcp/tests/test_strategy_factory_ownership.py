from __future__ import annotations

import asyncio
import importlib

from akshare_mcp.tools.managers import strategy_mgr_lifecycle as lifecycle


class _DispatchDb:
    def __init__(self) -> None:
        self.dispatches: dict[str, dict] = {}

    async def create_strategy_factory_dispatch(self, payload: dict) -> dict:
        item = dict(payload)
        self.dispatches[item["dispatch_id"]] = item
        return item

    async def get_strategy_factory_dispatch(self, dispatch_id: str) -> dict | None:
        return self.dispatches.get(dispatch_id)


class _StatusDb:
    async def get_latest_strategy_factory_run(self):
        return {
            "run_id": "factory_run_latest",
            "status": "success",
            "started_at": "2026-05-21T00:00:00+00:00",
            "completed_at": "2026-05-21T00:01:00+00:00",
            "summary": {"submitted": 1},
            "stages": {},
            "parity_result": {},
        }

    async def list_strategy_factory_runs(self, limit: int = 5):
        return [await self.get_latest_strategy_factory_run()]


def test_factory_run_once_queues_dispatch_by_default(monkeypatch) -> None:
    monkeypatch.delenv("STRATEGY_FACTORY_INLINE_EXECUTION_ENABLED", raising=False)

    def _boom(_db):
        raise AssertionError("scheduler must not be constructed by default")

    monkeypatch.setattr(lifecycle, "_get_strategy_factory_scheduler_with_runtime", _boom)
    db = _DispatchDb()

    result = asyncio.run(
        lifecycle.handle_factory_run_once(
            db,
            {"execution_mode": "shadow_readonly", "target_codes": ["600000"]},
        )
    )

    assert result["success"] is True
    assert result["data"]["queued"] is True
    assert result["data"]["execution_owner"] == "strategy_factory_runner"
    dispatch_id = result["data"]["dispatch_id"]
    assert db.dispatches[dispatch_id]["status"] == "queued"
    assert db.dispatches[dispatch_id]["metadata"]["target_codes"] == ["600000"]


def test_factory_dispatch_status_reads_storage_without_scheduler(monkeypatch) -> None:
    monkeypatch.delenv("STRATEGY_FACTORY_INLINE_EXECUTION_ENABLED", raising=False)

    def _boom(_db):
        raise AssertionError("scheduler must not be constructed for dispatch status")

    monkeypatch.setattr(lifecycle, "_get_strategy_factory_scheduler_with_runtime", _boom)
    db = _DispatchDb()
    db.dispatches["dispatch_1"] = {"dispatch_id": "dispatch_1", "status": "queued", "metadata": {}}

    result = asyncio.run(lifecycle.handle_factory_dispatch_status(db, {"dispatch_id": "dispatch_1"}))

    assert result["success"] is True
    assert result["data"]["dispatch_id"] == "dispatch_1"
    assert result["data"]["status"] == "queued"


def test_factory_dispatch_run_inline_passes_target_codes(monkeypatch) -> None:
    monkeypatch.setenv("STRATEGY_FACTORY_INLINE_EXECUTION_ENABLED", "1")
    calls: list[dict] = []

    class _Scheduler:
        async def dispatch_run(self, db=None, *, execution_mode=None, target_codes=None):
            calls.append(
                {
                    "db": db,
                    "execution_mode": execution_mode,
                    "target_codes": list(target_codes or []),
                }
            )
            return {
                "dispatch_id": "dispatch_inline",
                "status": "queued",
                "accepted": True,
                "queued": True,
                "already_running": False,
            }

    db = _DispatchDb()
    monkeypatch.setattr(
        lifecycle,
        "_get_strategy_factory_scheduler_with_runtime",
        lambda resolved_db: _Scheduler(),
    )

    result = asyncio.run(
        lifecycle.handle_factory_dispatch_run(
            db,
            {"execution_mode": "shadow_readonly", "target_codes": ["600000", "000001"]},
        )
    )

    assert result["success"] is True
    assert result["data"]["dispatch_id"] == "dispatch_inline"
    assert calls == [
        {
            "db": db,
            "execution_mode": "shadow_readonly",
            "target_codes": ["600000", "000001"],
        }
    ]


def test_factory_status_reads_persisted_runs_without_scheduler(monkeypatch) -> None:
    def _boom(_db):
        raise AssertionError("scheduler must not be constructed for factory_status")

    monkeypatch.setattr(lifecycle, "_get_strategy_factory_scheduler_with_runtime", _boom)

    result = asyncio.run(lifecycle.handle_factory_status(_StatusDb(), {"recent_run_limit": 1}))

    assert result["success"] is True
    assert result["data"]["running"] is False
    assert result["data"]["ownership"]["mode"] == "external_runner"
    assert result["data"]["last_result"]["run_id"] == "factory_run_latest"


def test_mcp_server_does_not_enable_strategy_factory_embedded_start_by_default(monkeypatch) -> None:
    monkeypatch.delenv("STRATEGY_FACTORY_ENABLED", raising=False)
    monkeypatch.setenv("AKSHARE_MCP_STARTUP_PROFILE", "full")
    server = importlib.import_module("akshare_mcp.server")

    assert server._strategy_factory_embedded_start_enabled("full") is False


def test_mcp_server_rejects_background_leader_when_lock_unavailable(monkeypatch) -> None:
    server = importlib.import_module("akshare_mcp.server")
    monkeypatch.setattr(server, "fcntl", None)
    monkeypatch.setattr(server, "_background_services_lock_handle", None)

    assert server._acquire_background_services_leader() is False
