from unittest.mock import AsyncMock, MagicMock

import pytest

from strategy_factory.application.factor_research import FactorResearchBuilder


@pytest.mark.asyncio
async def test_factor_research_uses_snapshot_date_for_freshness():
    db = MagicMock()
    db.get_factor_ic_history = AsyncMock(
        side_effect=[
            [
                {"ic_date": "2026-03-19", "ic_value": 0.06},
                {"ic_date": "2026-03-18", "ic_value": 0.05},
            ],
            [],
            [],
            [],
            [],
        ]
    )

    artifact = await FactorResearchBuilder.build(
        db,
        {
            "date": "2026-03-19",
            "factor_ic": {"value": 0.05},
            "factor_ic_trend": {"value": "rising"},
            "sources": {"factor_ic": {"status": "success"}},
        },
    )

    assert artifact["latest_factor_date"] == "2026-03-19"
    assert artifact["freshness_days"] == 0
