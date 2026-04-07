from __future__ import annotations

import pytest

from akshare_mcp.services.adapters.data_validation_adapter import BuiltinValidationAdapter
from akshare_mcp.tools import adapter_tools


class _DummyMCP:
    def tool(self, **_kwargs):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


def test_builtin_validation_treats_null_required_field_as_failure():
    adapter = BuiltinValidationAdapter()

    result = adapter.validate_dataset(
        records=[
            {"code": "000858", "price": 103.49, "trade_date": "2026-04-07"},
            {"code": "600519", "price": None, "trade_date": "2026-04-07"},
        ],
        expectations={
            "required_fields": ["code", "price", "trade_date"],
            "minimum_quality_threshold": 0.75,
        },
    )

    assert result.passed is False
    assert result.stats["min_quality_threshold"] == pytest.approx(0.75)
    assert result.stats["minimum_quality_threshold"] == pytest.approx(0.75)
    assert result.details[0]["expectation"] == "required_fields"
    assert result.details[0]["passed"] is False
    assert result.details[0]["invalid_records"] == [{"index": 1, "missing": ["price"]}]


@pytest.mark.asyncio
async def test_data_validation_tool_syncs_threshold_aliases_and_reports_failure():
    mcp = _DummyMCP()
    adapter_tools.register(mcp)

    result = await mcp.data_validation(
        action="validate",
        dataset_id="quotes-mixed",
        records=[
            {"code": "000858", "price": 103.49, "trade_date": "2026-04-07"},
            {"code": "600519", "price": None, "trade_date": "2026-04-07"},
        ],
        expectations={"required_fields": ["code", "price", "trade_date"]},
        minimum_quality_threshold=0.75,
    )

    assert result["success"] is True
    assert result["data"]["passed"] is False
    assert result["data"]["minimum_quality_threshold"] == pytest.approx(0.75)
    assert result["data"]["stats"]["min_quality_threshold"] == pytest.approx(0.75)
    assert result["data"]["stats"]["minimum_quality_threshold"] == pytest.approx(0.75)
    assert result["data"]["details"][0]["invalid_records"] == [{"index": 1, "missing": ["price"]}]
