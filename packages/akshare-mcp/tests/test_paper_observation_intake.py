"""DEV-V1 P1: paper observation intake 单元测试."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from akshare_mcp.services.incubation_factory.intake import IncubationIntake


@pytest.fixture
def intake():
    return IncubationIntake()


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for key in (
        "INCUBATION_FACTORY_PAPER_INTAKE_ENABLED",
        "INCUBATION_FACTORY_PAPER_INTAKE_BATCH_LIMIT",
        "INCUBATION_FACTORY_DIAGNOSTIC_INTAKE_ENABLED",
        "INCUBATION_FACTORY_DIAGNOSTIC_BATCH_LIMIT",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.mark.asyncio
async def test_paper_intake_disabled_by_default(intake):
    """默认 toggle OFF: 不查询 paper 候选。"""
    db = MagicMock()
    db.list_paper_observation_strategies = AsyncMock(return_value=[
        {"id": "s1", "strategy_type": "volatility_breakout"},
    ])
    result = await intake._list_paper_observation_strategies(db)
    assert result == []
    db.list_paper_observation_strategies.assert_not_called()


@pytest.mark.asyncio
async def test_paper_intake_enabled_returns_candidates(intake, monkeypatch):
    monkeypatch.setenv("INCUBATION_FACTORY_PAPER_INTAKE_ENABLED", "1")
    db = MagicMock()
    db.list_paper_observation_strategies = AsyncMock(return_value=[
        {"id": "s1", "strategy_type": "volatility_breakout"},
        {"id": "s2", "strategy_type": "value_factor"},
    ])
    result = await intake._list_paper_observation_strategies(db)
    assert len(result) == 2
    db.list_paper_observation_strategies.assert_called_once_with(limit=50)


@pytest.mark.asyncio
async def test_paper_intake_respects_batch_limit(intake, monkeypatch):
    monkeypatch.setenv("INCUBATION_FACTORY_PAPER_INTAKE_ENABLED", "1")
    monkeypatch.setenv("INCUBATION_FACTORY_PAPER_INTAKE_BATCH_LIMIT", "10")
    db = MagicMock()
    db.list_paper_observation_strategies = AsyncMock(return_value=[])
    await intake._list_paper_observation_strategies(db)
    db.list_paper_observation_strategies.assert_called_once_with(limit=10)


@pytest.mark.asyncio
async def test_paper_intake_db_method_missing_returns_empty(intake, monkeypatch):
    """db 不实现 list_paper_observation_strategies 时降级返回空,不抛异常。"""
    monkeypatch.setenv("INCUBATION_FACTORY_PAPER_INTAKE_ENABLED", "1")
    db = MagicMock(spec=[])  # 不实现任何 method
    result = await intake._list_paper_observation_strategies(db)
    assert result == []


@pytest.mark.asyncio
async def test_paper_intake_db_call_exception_returns_empty(intake, monkeypatch):
    """db 调用异常时降级返回空,Phase 2 不被打断。"""
    monkeypatch.setenv("INCUBATION_FACTORY_PAPER_INTAKE_ENABLED", "1")
    db = MagicMock()
    db.list_paper_observation_strategies = AsyncMock(side_effect=RuntimeError("boom"))
    result = await intake._list_paper_observation_strategies(db)
    assert result == []


@pytest.mark.asyncio
async def test_record_paper_intake_event_writes_domain_event(intake):
    db = MagicMock()
    db.save_strategy_domain_event = AsyncMock()
    strategy = {
        "id": "s1",
        "name": "test_volatility",
        "strategy_type": "volatility_breakout",
    }
    await intake._record_paper_intake_event(db, strategy)
    db.save_strategy_domain_event.assert_called_once()
    payload = db.save_strategy_domain_event.call_args[0][0]
    assert payload["event_type"] == "incubation_factory.paper_observation_recognized"
    assert payload["aggregate_type"] == "incubation_factory"
    assert payload["source"] == "incubation_factory_intake_paper"
    assert payload["payload"]["stage"] == "paper"


@pytest.mark.asyncio
async def test_record_paper_intake_event_swallows_db_exception(intake):
    """db.save_strategy_domain_event 抛异常时不再上抛,只 debug log。"""
    db = MagicMock()
    db.save_strategy_domain_event = AsyncMock(side_effect=RuntimeError("boom"))
    strategy = {"id": "s1", "name": "test", "strategy_type": "volatility_breakout"}
    # 不抛异常即为通过
    await intake._record_paper_intake_event(db, strategy)


@pytest.mark.asyncio
async def test_record_paper_intake_event_no_db_method(intake):
    """db 不实现 save_strategy_domain_event 时静默返回。"""
    db = MagicMock(spec=[])
    strategy = {"id": "s1"}
    await intake._record_paper_intake_event(db, strategy)


@pytest.mark.asyncio
async def test_diagnostic_intake_disabled_by_default(intake):
    db = MagicMock()
    db.list_diagnostic_observation_strategies = AsyncMock(return_value=[
        {"id": "s1", "strategy_type": "volatility_breakout"},
    ])
    result = await intake._list_diagnostic_observation_strategies(db)
    assert result == []
    db.list_diagnostic_observation_strategies.assert_not_called()


@pytest.mark.asyncio
async def test_diagnostic_intake_enabled_respects_batch_limit(intake, monkeypatch):
    monkeypatch.setenv("INCUBATION_FACTORY_DIAGNOSTIC_INTAKE_ENABLED", "1")
    monkeypatch.setenv("INCUBATION_FACTORY_DIAGNOSTIC_BATCH_LIMIT", "3")
    db = MagicMock()
    db.list_diagnostic_observation_strategies = AsyncMock(return_value=[
        {"id": "s1", "strategy_type": "volatility_breakout"},
    ])
    result = await intake._list_diagnostic_observation_strategies(db)
    assert len(result) == 1
    db.list_diagnostic_observation_strategies.assert_called_once_with(limit=3)


@pytest.mark.asyncio
async def test_diagnostic_intake_db_failure_returns_empty(intake, monkeypatch):
    monkeypatch.setenv("INCUBATION_FACTORY_DIAGNOSTIC_INTAKE_ENABLED", "1")
    db = MagicMock()
    db.list_diagnostic_observation_strategies = AsyncMock(side_effect=RuntimeError("boom"))
    result = await intake._list_diagnostic_observation_strategies(db)
    assert result == []


@pytest.mark.asyncio
async def test_record_diagnostic_intake_event_writes_domain_event(intake):
    db = MagicMock()
    db.save_strategy_domain_event = AsyncMock()
    strategy = {
        "id": "s_diag",
        "name": "diag_test",
        "strategy_type": "volatility_breakout",
    }
    await intake._record_diagnostic_intake_event(db, strategy)
    db.save_strategy_domain_event.assert_called_once()
    payload = db.save_strategy_domain_event.call_args[0][0]
    assert payload["event_type"] == "incubation_factory.diagnostic_observation_recognized"
    assert payload["source"] == "incubation_factory_intake_diagnostic"
    assert payload["payload"]["stage"] == "diagnostic"
    assert payload["payload"]["diagnostic_observation"] is True
