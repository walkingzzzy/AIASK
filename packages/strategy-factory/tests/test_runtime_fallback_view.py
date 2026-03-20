from strategy_factory.application import runtime


def test_runtime_returns_local_view_when_legacy_package_missing(monkeypatch):
    monkeypatch.setattr(runtime, "load_legacy_module", lambda _name: None)
    runtime._build_local_runtime_view.cache_clear()

    package = runtime.get_strategy_factory_package()

    assert package.asyncio is not None
    assert package.MarketOpportunityScanner.__name__ == "MarketOpportunityScanner"
    assert package.FactorResearchBuilder.__name__ == "FactorResearchBuilder"
    assert callable(package._build_strategy_panels)
    assert callable(package._run_validation_report)
    assert callable(package._run_risk_report)
    assert callable(package.build_legacy_gate_report)
    assert callable(package.get_strategy_factory_scheduler)
    assert callable(package.run_submission_quality_gate)
    assert callable(package._extract_event_context)
