from strategy_factory import (
    BACKTEST_AI_PROTOTYPE_THRESHOLDS,
    BacktestFilter,
    CATEGORY_MINIMUMS,
    DataCollector,
    DEPRECATION_THRESHOLDS,
    Deduplicator,
    EliminationChecker,
    FactorResearchBuilder,
    LLM_FAN_OUT_COUNT,
    LocalEventDrivenResearchEngine,
    MarketOpportunityScanner,
    PIPELINE_MODE,
    PIPELINE_STAGE_MAX_TOKENS,
    PIPELINE_STAGE_TEMPERATURE,
    PIPELINE_STAGE_TIMEOUTS,
    PIPELINE_STAGE_TIMEOUT_SEC,
    PROMOTION_THRESHOLDS,
    PROVISIONAL_PASS_THRESHOLDS,
    QUALITY_GATE_THRESHOLDS,
    RISK_REPORT_THRESHOLDS,
    StrategyFactoryScheduler,
    StrategySpawner,
    StrategySubmitter,
    _call_optional_async,
    auto_name,
    build_strategy_panels,
    call_optional_async,
    extract_event_context,
    get_factory_constants,
    get_local_event_engine,
    get_strategy_factory_scheduler,
    preferred_strategy_types_for_factor,
    run_submission_quality_gate,
)
from strategy_factory.application.backtest_filter import BacktestFilter as ImplBacktestFilter
from strategy_factory.application.collect import DataCollector as ImplDataCollector
from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler as ImplStrategyFactoryScheduler


def test_public_facade_exports_expected_symbols():
    assert StrategyFactoryScheduler.__name__ == "StrategyFactoryScheduler"
    assert StrategySpawner.__name__ == "StrategySpawner"
    assert BacktestFilter.__name__ == "BacktestFilter"
    assert Deduplicator.__name__ == "Deduplicator"
    assert StrategySubmitter.__name__ == "StrategySubmitter"
    assert EliminationChecker.__name__ == "EliminationChecker"
    assert DataCollector.__name__ == "DataCollector"
    assert MarketOpportunityScanner.__name__ == "MarketOpportunityScanner"
    assert FactorResearchBuilder.__name__ == "FactorResearchBuilder"
    assert LocalEventDrivenResearchEngine.__name__ == "LocalEventDrivenResearchEngine"
    assert callable(get_local_event_engine)
    assert callable(get_strategy_factory_scheduler)
    assert callable(run_submission_quality_gate)
    assert callable(build_strategy_panels)
    assert callable(extract_event_context)
    assert callable(_call_optional_async)
    assert callable(call_optional_async)
    assert callable(auto_name)
    assert callable(preferred_strategy_types_for_factor)


def test_public_facade_class_exports_point_to_local_implementations():
    assert BacktestFilter is ImplBacktestFilter
    assert DataCollector is ImplDataCollector
    assert StrategyFactoryScheduler is ImplStrategyFactoryScheduler


def test_public_facade_exports_selected_constants():
    assert CATEGORY_MINIMUMS["momentum"] >= 1
    assert BACKTEST_AI_PROTOTYPE_THRESHOLDS["sharpe_min"] <= 0.15
    assert PROMOTION_THRESHOLDS["sharpe_min"] >= 0.5
    assert DEPRECATION_THRESHOLDS["sharpe_negative"] == 0.0
    assert PROVISIONAL_PASS_THRESHOLDS["trades_min"] >= 1
    assert QUALITY_GATE_THRESHOLDS["purged_kfold_ic_min"] >= 0.0
    assert RISK_REPORT_THRESHOLDS["var_percent_max"] > 0
    assert LLM_FAN_OUT_COUNT >= 1
    assert PIPELINE_MODE in {"staged", "monolithic"}
    assert PIPELINE_STAGE_TIMEOUT_SEC > 0
    assert "strategy_generation" in PIPELINE_STAGE_TIMEOUTS
    assert "strategy_generation" in PIPELINE_STAGE_MAX_TOKENS
    assert "strategy_generation" in PIPELINE_STAGE_TEMPERATURE
    assert preferred_strategy_types_for_factor("value")[:1] == ["value_factor"]


def test_get_factory_constants_returns_existing_thresholds():
    constants = get_factory_constants()
    assert "BACKTEST_DEFAULT_THRESHOLDS" in constants
    assert "FACTORY_SCHEDULE_MODE" in constants


def test_auto_name_uses_public_facade_helper():
    assert auto_name("ma_cross", {"short_period": 8, "long_period": 21}) == "均线交叉·快8慢21"
