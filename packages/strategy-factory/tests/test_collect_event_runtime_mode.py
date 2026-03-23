from unittest.mock import AsyncMock, MagicMock

import pytest

from strategy_factory.application.collect import DataCollector


class _FakeSentimentAnalyzer:
    def calculate_fear_greed_index(self, _index_klines, _breadth):
        return {"index": 62, "level": "greed", "components": {"breadth": 0.7}}


def _build_db():
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=[{"close": 1.0, "volume": 1.0}] * 60)
    db.get_limit_up_stats = AsyncMock(return_value={"up_count": 8})
    db.get_factor_ic_history = AsyncMock(return_value=[{"ic_value": 0.08}] * 10)
    db.count_strategies_by_type = AsyncMock(
        side_effect=lambda status: {"momentum": 1} if status == "listed" else {"momentum": 0}
    )
    db.save_daily_snapshot = AsyncMock()
    db.get_recent_north_fund_summary = AsyncMock(return_value=None)
    db.get_recent_margin_summary = AsyncMock(return_value=None)
    db.get_factory_market_internal_snapshot = AsyncMock(return_value=None)
    db.list_factory_event_clusters = AsyncMock(return_value=[])
    db.list_factory_theme_definitions = AsyncMock(return_value=[])
    db.list_factory_event_signals = AsyncMock(return_value=[])
    db.list_daily_snapshots = AsyncMock(return_value=[])
    return db


@pytest.mark.asyncio
async def test_collect_defaults_to_event_readonly_mode(monkeypatch):
    collector = DataCollector()
    db = _build_db()
    engine = MagicMock()
    engine.refresh = AsyncMock(
        return_value={
            "engine": "local_db_rule_v1",
            "enabled": True,
            "market_internals": {"margin_proxy_5d_change_pct": 3.2},
        }
    )
    package = MagicMock()
    package.get_local_event_engine = MagicMock(return_value=engine)

    monkeypatch.delenv("STRATEGY_FACTORY_EVENT_RUNTIME_MODE", raising=False)
    monkeypatch.setattr(
        "strategy_factory.application.collect.get_strategy_factory_package",
        lambda: package,
    )
    monkeypatch.setattr(
        "strategy_factory.application.collect.get_sentiment_analyzer",
        lambda: _FakeSentimentAnalyzer(),
    )

    snapshot = await collector.collect(db)

    engine.refresh.assert_not_awaited()
    assert snapshot["event_runtime"]["mode"] == "readonly"
    assert snapshot["event_runtime"]["read_only"] is True
    assert snapshot["sources"]["event_driven"]["details"]["runtime_mode"] == "readonly"
    assert snapshot["sources"]["event_driven"]["details"]["refresh_attempted"] is False


@pytest.mark.asyncio
async def test_collect_refresh_mode_executes_local_event_refresh(monkeypatch):
    collector = DataCollector()
    db = _build_db()
    engine = MagicMock()
    engine.refresh = AsyncMock(
        return_value={
            "engine": "local_db_rule_v1",
            "enabled": True,
            "market_internals": {
                "margin_proxy_5d_change_pct": 4.5,
                "hot_sectors": ["AI"],
                "cold_sectors": ["煤炭"],
            },
        }
    )
    package = MagicMock()
    package.get_local_event_engine = MagicMock(return_value=engine)

    monkeypatch.setenv("STRATEGY_FACTORY_EVENT_RUNTIME_MODE", "refresh")
    monkeypatch.setattr(
        "strategy_factory.application.collect.get_strategy_factory_package",
        lambda: package,
    )
    monkeypatch.setattr(
        "strategy_factory.application.collect.get_sentiment_analyzer",
        lambda: _FakeSentimentAnalyzer(),
    )

    snapshot = await collector.collect(db)

    engine.refresh.assert_awaited_once()
    assert snapshot["event_runtime"]["mode"] == "refresh"
    assert snapshot["event_runtime"]["refresh_attempted"] is True
    assert snapshot["margin_5d_change_pct"] == 4.5
    assert snapshot["hot_sectors"] == ["AI"]
    assert snapshot["cold_sectors"] == ["煤炭"]
    assert snapshot["sources"]["event_driven"]["details"]["runtime_mode"] == "refresh"


@pytest.mark.asyncio
async def test_collect_reuses_recent_successful_fear_greed_snapshot(monkeypatch):
    collector = DataCollector(index_kline_provider=AsyncMock(return_value={"success": False}))
    db = _build_db()
    db.get_klines = AsyncMock(return_value=[])
    db.list_daily_snapshots = AsyncMock(
        return_value=[
            {
                "date": "2026-03-21",
                "fear_greed_index": 72,
                "fg_level": "greed",
                "fg_components": {"breadth": 0.91},
                "sources": {"fear_greed": {"status": "success"}},
            },
            {
                "date": "2026-03-20",
                "fear_greed_index": 50,
                "fg_level": "neutral",
                "fg_components": {},
                "sources": {"fear_greed": {"status": "fallback"}},
            },
        ]
    )
    package = MagicMock()
    package.get_local_event_engine = MagicMock(return_value=MagicMock(refresh=AsyncMock(return_value={})))

    monkeypatch.delenv("STRATEGY_FACTORY_EVENT_RUNTIME_MODE", raising=False)
    monkeypatch.setattr(
        "strategy_factory.application.collect.get_strategy_factory_package",
        lambda: package,
    )
    monkeypatch.setattr(
        "strategy_factory.application.collect.get_sentiment_analyzer",
        lambda: _FakeSentimentAnalyzer(),
    )

    snapshot = await collector.collect(db)

    assert snapshot["fear_greed_index"] == 72
    assert snapshot["fg_level"] == "greed"
    assert snapshot["fg_components"] == {"breadth": 0.91}
    assert snapshot["sources"]["fear_greed"]["status"] == "fallback"
    assert (
        snapshot["sources"]["fear_greed"]["details"]["reused_snapshot_date"]
        == "2026-03-21"
    )
    assert snapshot["sources"]["fear_greed"]["details"]["reuse_mode"] == "recent_successful_snapshot"


@pytest.mark.asyncio
async def test_collect_uses_db_margin_summary_when_local_proxy_missing(monkeypatch):
    collector = DataCollector()
    db = _build_db()
    db.get_recent_margin_summary = AsyncMock(
        return_value={
            "margin_balance_change_5d": 3.46,
            "margin_balance_latest": 100.0,
            "margin_buy_latest": 20.0,
            "source": "margin_market_flow",
            "stale": False,
        }
    )
    package = MagicMock()
    package.get_local_event_engine = MagicMock(return_value=MagicMock(refresh=AsyncMock(return_value={})))

    monkeypatch.delenv("STRATEGY_FACTORY_EVENT_RUNTIME_MODE", raising=False)
    monkeypatch.setattr(
        "strategy_factory.application.collect.get_strategy_factory_package",
        lambda: package,
    )
    monkeypatch.setattr(
        "strategy_factory.application.collect.get_sentiment_analyzer",
        lambda: _FakeSentimentAnalyzer(),
    )

    snapshot = await collector.collect(db)

    assert snapshot["margin_5d_change_pct"] == 3.46
    assert snapshot["sources"]["margin_data"]["status"] == "success"
    assert snapshot["sources"]["margin_data"]["details"]["mode"] == "db_method"
