import importlib
import inspect

import pytest


OLD_PACKAGE = "akshare_mcp.services.strategy_factory"
NEW_PUBLIC_MODULES = ("strategy_factory", "strategy_factory.api.facade")

CORE_SYMBOLS = (
    "StrategyFactoryScheduler",
    "StrategySpawner",
    "BacktestFilter",
    "Deduplicator",
    "StrategySubmitter",
    "EliminationChecker",
    "get_strategy_factory_scheduler",
)

EXTENDED_SYMBOLS = (
    "DataCollector",
    "MarketOpportunityScanner",
    "FactorResearchBuilder",
    "LocalEventDrivenResearchEngine",
    "get_local_event_engine",
)

PATCH_SURFACE_SYMBOLS = (
    "asyncio",
    "get_strategy_factory_package",
    "_call_optional_async",
    "_build_strategy_panels",
    "_run_validation_report",
    "_run_risk_report",
)


def _load_old_package():
    return importlib.import_module(OLD_PACKAGE)


def _resolve_new_public_symbol(symbol_name: str):
    loaded_any = False
    for module_name in NEW_PUBLIC_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        loaded_any = True
        if hasattr(module, symbol_name):
            return getattr(module, symbol_name)
    if not loaded_any:
        pytest.skip("strategy_factory 独立包尚未接入，先仅校验旧路径契约。")
    pytest.fail(f"新公共入口未暴露符号: {symbol_name}")


def _assert_symbol_equivalent(old_symbol, new_symbol) -> None:
    if old_symbol is new_symbol:
        return
    assert inspect.isclass(old_symbol) == inspect.isclass(new_symbol)
    assert callable(old_symbol) == callable(new_symbol)
    assert getattr(old_symbol, "__name__", None) == getattr(new_symbol, "__name__", None)


def test_old_package_exposes_core_migration_contract_symbols():
    package = _load_old_package()
    for symbol_name in CORE_SYMBOLS:
        assert hasattr(package, symbol_name), symbol_name


def test_old_package_exposes_extended_migration_contract_symbols():
    package = _load_old_package()
    for symbol_name in EXTENDED_SYMBOLS:
        assert hasattr(package, symbol_name), symbol_name


def test_old_package_preserves_patch_surface_symbols():
    package = _load_old_package()
    for symbol_name in PATCH_SURFACE_SYMBOLS:
        assert hasattr(package, symbol_name), symbol_name


def test_old_factory_scheduler_module_preserves_runtime_patch_points():
    module = importlib.import_module("akshare_mcp.services.strategy_factory.factory_scheduler")
    assert hasattr(module, "get_strategy_factory_package")
    assert hasattr(module, "_call_optional_async")


@pytest.mark.parametrize("symbol_name", CORE_SYMBOLS)
def test_old_and_new_public_symbols_are_compatible_when_new_package_exists(symbol_name):
    old_symbol = getattr(_load_old_package(), symbol_name)
    new_symbol = _resolve_new_public_symbol(symbol_name)
    _assert_symbol_equivalent(old_symbol, new_symbol)


@pytest.mark.parametrize("symbol_name", EXTENDED_SYMBOLS)
def test_old_and_new_extended_symbols_are_compatible_when_new_package_exists(symbol_name):
    old_symbol = getattr(_load_old_package(), symbol_name)
    new_symbol = _resolve_new_public_symbol(symbol_name)
    _assert_symbol_equivalent(old_symbol, new_symbol)
