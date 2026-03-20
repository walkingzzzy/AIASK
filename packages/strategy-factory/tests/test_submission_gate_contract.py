from unittest.mock import AsyncMock, MagicMock

import pytest

from strategy_factory.application.submission_gate import run_submission_quality_gate


@pytest.mark.asyncio
async def test_submission_gate_returns_failure_for_unknown_strategy_type():
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=[])

    result = await run_submission_quality_gate(
        db,
        {"strategy_type": "unknown_strategy_type", "params": {}},
    )

    assert result["passed"] is False
    assert "registry" in str(result.get("reason") or "").lower()
