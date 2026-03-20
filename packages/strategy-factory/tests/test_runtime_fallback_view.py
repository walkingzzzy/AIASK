from types import SimpleNamespace

from akshare_mcp.services.backtest.engine import BacktestEngine

from strategy_factory.application import runtime


def test_runtime_returns_local_view_when_legacy_package_missing(monkeypatch):
    monkeypatch.setattr(runtime, "load_legacy_module", lambda _name: None)
    runtime._build_local_runtime_view.cache_clear()
    runtime._get_runtime_proxy.cache_clear()

    package = runtime.get_strategy_factory_package()

    assert package.asyncio is not None
    assert package.BacktestEngine is BacktestEngine
    assert package.DataCollector.__name__ == "DataCollector"
    assert package.MarketOpportunityScanner.__name__ == "MarketOpportunityScanner"
    assert package.FactorResearchBuilder.__name__ == "FactorResearchBuilder"
    assert callable(package._build_strategy_panels)
    assert callable(package._run_validation_report)
    assert callable(package._run_risk_report)
    assert callable(package.build_legacy_gate_report)
    assert callable(package.get_strategy_factory_scheduler)
    assert callable(package.run_submission_quality_gate)
    assert callable(package._extract_event_context)


def test_runtime_proxy_prefers_legacy_symbol_and_falls_back_for_missing_symbol(monkeypatch):
    legacy_asyncio = SimpleNamespace(to_thread=object())
    legacy_package = SimpleNamespace(asyncio=legacy_asyncio)

    monkeypatch.setattr(runtime, "load_legacy_module", lambda _name: legacy_package)
    runtime._build_local_runtime_view.cache_clear()
    runtime._get_runtime_proxy.cache_clear()

    package = runtime.get_strategy_factory_package()

    assert package.asyncio is legacy_asyncio
    assert package.BacktestEngine is BacktestEngine
