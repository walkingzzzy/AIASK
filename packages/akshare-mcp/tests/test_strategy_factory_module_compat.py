from akshare_mcp.services.strategy_factory import (
    BacktestFilter,
    DataCollector,
    Deduplicator,
    EliminationChecker,
    FactorResearchBuilder,
    LocalEventDrivenResearchEngine,
    MarketOpportunityScanner,
    StrategySubmitter,
    _auto_name,
    _build_strategy_panels,
    _call_optional_async,
    _extract_target_codes_from_payload,
    _normalize_target_codes,
    _resolve_strategy_sample_codes,
    _run_risk_report,
    _run_validation_report,
    _update_strategy_status,
    get_local_event_engine,
    get_strategy_factory_package,
)
from akshare_mcp.services.strategy_factory.analysis import BacktestFilter as AnalysisBacktestFilter
from akshare_mcp.services.strategy_factory.analysis import Deduplicator as AnalysisDeduplicator
from akshare_mcp.services.strategy_factory.data import DataCollector as DataModuleCollector
from akshare_mcp.services.strategy_factory.data import MarketOpportunityScanner as DataModuleScanner
from akshare_mcp.services.strategy_factory.event_engine import (
    LocalEventDrivenResearchEngine as EventEngineModule,
    get_local_event_engine as EventEngineGetter,
)
from akshare_mcp.services.strategy_factory.execution import EliminationChecker as ExecutionEliminationChecker
from akshare_mcp.services.strategy_factory.execution import StrategySubmitter as ExecutionStrategySubmitter
from akshare_mcp.services.strategy_factory.factor_research import FactorResearchBuilder as FactorResearchModule
from akshare_mcp.services.strategy_factory.candidate import StrategySpawner as CandidateSpawner
from akshare_mcp.services.strategy_factory.runtime import (
    _call_optional_async as RuntimeCallOptionalAsync,
    get_strategy_factory_package as RuntimeGetStrategyFactoryPackage,
)
from akshare_mcp.services.strategy_factory.scheduler import StrategyFactoryScheduler as SchedulerStrategyFactoryScheduler
from akshare_mcp.services.strategy_factory.utils import (
    _auto_name as UtilsAutoName,
    _build_strategy_panels as UtilsBuildPanels,
    _call_optional_async as UtilsCallOptionalAsync,
    _extract_event_context as UtilsExtractEventContext,
    _extract_target_codes_from_payload as UtilsExtractTargetCodes,
    _normalize_target_codes as UtilsNormalizeTargetCodes,
    _resolve_strategy_sample_codes as UtilsResolveStrategySampleCodes,
    _run_risk_report as UtilsRunRiskReport,
    _run_validation_report as UtilsRunValidationReport,
    _update_strategy_status as UtilsUpdateStrategyStatus,
    get_strategy_factory_package as UtilsGetStrategyFactoryPackage,
)
from akshare_mcp.services.strategy_factory import StrategyFactoryScheduler, StrategySpawner


def test_strategy_factory_leaf_module_compat_exports():
    assert DataModuleCollector is DataCollector
    assert DataModuleScanner is MarketOpportunityScanner
    assert AnalysisBacktestFilter is BacktestFilter
    assert AnalysisDeduplicator is Deduplicator
    assert ExecutionStrategySubmitter is StrategySubmitter
    assert ExecutionEliminationChecker is EliminationChecker
    assert CandidateSpawner is StrategySpawner
    assert SchedulerStrategyFactoryScheduler is StrategyFactoryScheduler
    assert FactorResearchModule is FactorResearchBuilder
    assert EventEngineModule is LocalEventDrivenResearchEngine
    assert EventEngineGetter is get_local_event_engine
    assert RuntimeGetStrategyFactoryPackage is get_strategy_factory_package
    assert RuntimeCallOptionalAsync is _call_optional_async
    assert UtilsAutoName is _auto_name
    assert UtilsUpdateStrategyStatus is _update_strategy_status
    assert UtilsNormalizeTargetCodes is _normalize_target_codes
    assert UtilsExtractTargetCodes is _extract_target_codes_from_payload
    assert UtilsResolveStrategySampleCodes is _resolve_strategy_sample_codes
    assert UtilsGetStrategyFactoryPackage is get_strategy_factory_package
    assert UtilsCallOptionalAsync is _call_optional_async
    assert callable(UtilsExtractEventContext)
    assert UtilsBuildPanels is _build_strategy_panels
    assert UtilsRunValidationReport is _run_validation_report
    assert UtilsRunRiskReport is _run_risk_report
