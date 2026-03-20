from strategy_factory.api import facade
from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler


def test_facade_uses_local_scheduler_singleton_when_legacy_package_missing(monkeypatch):
    class _RuntimeView:
        def __init__(self):
            self._scheduler = StrategyFactoryScheduler()

        def get_strategy_factory_scheduler(self):
            return self._scheduler

    runtime_view = _RuntimeView()
    monkeypatch.setattr(facade, "_runtime_get_strategy_factory_package", lambda: runtime_view)

    first = facade.get_strategy_factory_scheduler()
    second = facade.get_strategy_factory_scheduler()

    assert isinstance(first, StrategyFactoryScheduler)
    assert first is second


def test_facade_uses_local_extract_event_context_when_legacy_utils_missing(monkeypatch):
    monkeypatch.setattr(facade, "_runtime_get_strategy_factory_package", lambda: object())

    context = facade.extract_event_context(
        {
            "task_key": "task-1",
            "event_id": "evt-1",
            "theme_code": "ai",
            "target_symbols": ["600519"],
        }
    )

    assert context["task_key"] == "task-1"
    assert context["event_id"] == "evt-1"
    assert context["theme_code"] == "ai"
    assert context["target_symbols"] == ["600519"]
