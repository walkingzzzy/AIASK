import akshare_mcp.services.strategy_factory.runtime as legacy_runtime

from strategy_factory.application.quality_gates import get_strategy_factory_package


def test_quality_gates_uses_legacy_runtime_patch_point(monkeypatch):
    sentinel = object()

    monkeypatch.setattr(legacy_runtime, "get_strategy_factory_package", lambda: sentinel)

    assert get_strategy_factory_package() is sentinel
