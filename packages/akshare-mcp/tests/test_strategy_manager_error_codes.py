import json
from unittest.mock import MagicMock

import pytest

import akshare_mcp.tools.managers.strategy_manager as strategy_manager_mod


class _DummyMCP:
    def tool(self, **_kwargs):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn
        return _decorator


@pytest.mark.asyncio
async def test_strategy_manager_unknown_action_returns_invalid_action_code(monkeypatch):
    mcp = _DummyMCP()
    strategy_manager_mod.register_strategy_manager(mcp)
    monkeypatch.setattr(strategy_manager_mod, "get_db", lambda: MagicMock())

    result = await mcp.strategy_manager(action="does_not_exist", kwargs=json.dumps({}))

    assert result["success"] is False
    assert result["error_code"] == "STRATEGY_MANAGER_INVALID_ACTION"


@pytest.mark.asyncio
async def test_strategy_manager_detail_missing_strategy_id_returns_invalid_params(monkeypatch):
    mcp = _DummyMCP()
    strategy_manager_mod.register_strategy_manager(mcp)
    monkeypatch.setattr(strategy_manager_mod, "get_db", lambda: MagicMock())

    result = await mcp.strategy_manager(action="detail", kwargs=json.dumps({}))

    assert result["success"] is False
    assert result["error_code"] == "STRATEGY_MANAGER_INVALID_PARAMS"
    assert result["detail"]["required_any_of"] == ["strategy_id", "id"]


@pytest.mark.asyncio
async def test_strategy_manager_ai_experiments_not_found_returns_not_found_code(monkeypatch):
    mcp = _DummyMCP()
    strategy_manager_mod.register_strategy_manager(mcp)
    db = MagicMock()
    db.get_strategy_generation_experiment = None

    async def _missing(_experiment_id):
        return None

    db.get_strategy_generation_experiment = _missing
    monkeypatch.setattr(strategy_manager_mod, "get_db", lambda: db)

    result = await mcp.strategy_manager(
        action="ai_experiments",
        kwargs=json.dumps({"experiment_id": "exp_missing"}),
    )

    assert result["success"] is False
    assert result["error_code"] == "STRATEGY_MANAGER_NOT_FOUND"
