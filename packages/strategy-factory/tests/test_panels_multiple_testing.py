from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from strategy_factory.application.panels import _run_validation_report


@pytest.mark.asyncio
async def test_run_validation_report_forwards_strategy_family_returns(monkeypatch):
    import strategy_factory.application.panels as panels_mod

    captured: dict[str, object] = {}

    class _FakeStrategy:
        def set_parameters(self, params):
            self.params = dict(params or {})

        def generate_signals(self, closes, volumes=None):
            lookback = float(self.params.get("lookback", 20) or 20)
            threshold = float(self.params.get("threshold", 0.05) or 0.05)
            slope = max(0.05, min(2.0, threshold * lookback))
            return np.linspace(0.0, slope, len(closes), dtype=np.float64)

    class _FakePipeline:
        def __init__(self, **_kwargs):
            pass

        def run(self, factor_panel, return_panel, **kwargs):
            captured["factor_panel_shape"] = np.asarray(factor_panel).shape
            captured["return_panel_shape"] = np.asarray(return_panel).shape
            captured["strategy_returns"] = np.asarray(kwargs.get("strategy_returns"))
            captured["family_returns"] = np.asarray(kwargs.get("family_returns"))
            return {"rating": {"grade": "B"}, "multiple_testing": {"available": True}}

    monkeypatch.setattr(
        panels_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: _FakeStrategy if strategy_type == "momentum" else None),
    )
    monkeypatch.setattr(
        panels_mod,
        "get_normalize_klines",
        lambda: (lambda rows: sorted(list(rows or []), key=lambda row: str(row.get("date") or ""))),
    )
    monkeypatch.setattr(
        panels_mod,
        "get_validation_runtime",
        lambda: SimpleNamespace(FactorValidationPipeline=_FakePipeline),
    )

    klines = [
        {"date": f"2026-01-{(idx % 28) + 1:02d}", "close": float(100 + idx), "volume": float(1000 + idx)}
        for idx in range(160)
    ]
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=klines)

    report = await _run_validation_report("momentum", {"lookback": 20, "threshold": 0.05}, db)

    assert report["multiple_testing"]["available"] is True
    assert captured["factor_panel_shape"][1] >= 3
    assert captured["strategy_returns"].ndim == 1
    assert captured["strategy_returns"].size > 0
    assert captured["family_returns"].ndim == 2
    assert captured["family_returns"].shape[1] >= 2
