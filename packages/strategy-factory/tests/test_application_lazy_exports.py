import strategy_factory.application as application

from strategy_factory.application.backtest_filter import BacktestFilter
from strategy_factory.application.collect import DataCollector
from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler


def test_application_package_lazy_exports_resolve_local_symbols():
    assert application.BacktestFilter is BacktestFilter
    assert application.DataCollector is DataCollector
    assert application.StrategyFactoryScheduler is StrategyFactoryScheduler
