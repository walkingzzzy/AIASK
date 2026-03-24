from __future__ import annotations

import pytest

from akshare_mcp.tools.managers.strategy_mgr_lifecycle import handle_factory_run_once


@pytest.mark.asyncio
async def test_handle_factory_run_once_passes_current_db_to_scheduler(monkeypatch):
    captured: dict[str, object] = {}

    class _Scheduler:
        async def run_once(self, db=None):
            captured["db"] = db
            return {"run_id": "run_test_1", "status": "success"}

    monkeypatch.setattr(
        "strategy_factory.get_strategy_factory_scheduler",
        lambda: _Scheduler(),
    )

    db = object()
    result = await handle_factory_run_once(db, {})

    assert captured["db"] is db
    assert result["success"] is True
    assert result["data"]["run_id"] == "run_test_1"
