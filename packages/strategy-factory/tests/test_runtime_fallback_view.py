import ast
from pathlib import Path
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


def test_runtime_proxy_prefers_local_scheduler_symbols_even_when_legacy_package_exists(monkeypatch):
    legacy_package = SimpleNamespace(
        StrategyFactoryScheduler=object(),
        get_strategy_factory_scheduler=lambda: "legacy",
    )

    monkeypatch.setattr(runtime, "load_legacy_module", lambda _name: legacy_package)
    runtime._build_local_runtime_view.cache_clear()
    runtime._get_runtime_proxy.cache_clear()

    package = runtime.get_strategy_factory_package()

    assert package.StrategyFactoryScheduler is not legacy_package.StrategyFactoryScheduler
    assert package.get_strategy_factory_scheduler() != "legacy"


def test_factory_scheduler_should_not_import_runtime_at_module_top_level():
    source = Path(runtime.__file__).with_name("factory_scheduler.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    runtime_imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == "runtime"
    ]

    assert runtime_imports == []


def test_application_static_import_graph_should_not_have_multi_module_cycles():
    root = Path(runtime.__file__).resolve().parent
    modules = {path.stem: path for path in root.glob("*.py") if path.name != "__init__.py"}
    graph = {name: set() for name in modules}

    for name, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                target = node.module.split(".")[0]
                if target in modules:
                    graph[name].add(target)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split(".")
                    if len(parts) >= 3 and parts[0] == "strategy_factory" and parts[1] == "application" and parts[2] in modules:
                        graph[name].add(parts[2])

    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def strong_connect(node: str) -> None:
        indices[node] = len(indices)
        lowlinks[node] = indices[node]
        stack.append(node)
        on_stack.add(node)

        for target in graph[node]:
            if target not in indices:
                strong_connect(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])

        if lowlinks[node] == indices[node]:
            component: list[str] = []
            while True:
                popped = stack.pop()
                on_stack.remove(popped)
                component.append(popped)
                if popped == node:
                    break
            components.append(sorted(component))

    for node in graph:
        if node not in indices:
            strong_connect(node)

    assert [component for component in components if len(component) > 1] == []
