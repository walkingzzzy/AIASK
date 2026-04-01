"""服务层"""

from .technical_analysis import technical_analysis
from .backtest.engine import backtest_engine
from .pattern_recognition import pattern_recognition
from .cost_model import build_cost_model, effective_cost_rate, resolve_cost_assumptions
from .artifact_registry import (
    register_artifact,
    register_artifact_async,
    get_artifact,
    list_artifacts,
    get_artifact_async,
    list_artifacts_async,
)
from .factor_candidate_storage import (
    FACTOR_MEMORY_STRATEGY,
    FACTOR_MEMORY_VERSION,
    get_factor_candidate_record,
    get_factor_candidate_record_async,
    list_factor_candidate_records_async,
    save_factor_candidate_record,
)
from .signal_dsl import build_signal_definition, evaluate_signal
from .factor_llm_provider import (
    FactorLLMConfig,
    FactorLLMProvider,
    FactorLLMRequestError,
    close_factor_llm_provider,
    get_factor_llm_provider,
    get_factor_candidate_schema_path,
    load_factor_candidate_schema,
    validate_factor_generation_payload,
)
from .factor_candidate_compiler import (
    SUPPORTED_FACTOR_FIELDS,
    SUPPORTED_FACTOR_FUNCTIONS,
    build_factor_feature_frame,
    compile_factor_candidate,
    evaluate_compiled_factor,
)
from .factor_validation_pipeline import validate_factor_candidate_pipeline
from .factor_research_memory import (
    FactorResearchMemoryService,
    get_factor_research_memory_service,
)
try:
    from .strategy_llm_provider import close_strategy_llm_provider
except Exception:
    async def close_strategy_llm_provider() -> None:
        return None

try:
    from .text_embedding import close_strategy_text_embedding_service
except Exception:
    async def close_strategy_text_embedding_service() -> None:
        return None
from .validation import (
    bootstrap_ic_ci,
    deflated_sharpe_ratio,
    hansen_spa_test,
    probability_of_backtest_overfitting,
    white_reality_check,
)
from .evidence_chain import (
    create_chain, add_evidence, make_evidence, set_conclusion,
    save_chain, get_chain, query_chains_by_code, query_chains_by_date,
    list_chains, summarize_chain,
)


async def close_shared_runtime_clients() -> None:
    """关闭进程级共享 HTTP 客户端，供一次性脚本/退出钩子显式调用。"""
    await close_factor_llm_provider()
    await close_strategy_llm_provider()
    await close_strategy_text_embedding_service()

__all__ = [
    'technical_analysis',
    'backtest_engine',
    'pattern_recognition',
    'build_cost_model',
    'effective_cost_rate',
    'resolve_cost_assumptions',
    'register_artifact',
    'register_artifact_async',
    'get_artifact',
    'list_artifacts',
    'get_artifact_async',
    'list_artifacts_async',
    'FACTOR_MEMORY_STRATEGY',
    'FACTOR_MEMORY_VERSION',
    'save_factor_candidate_record',
    'get_factor_candidate_record',
    'get_factor_candidate_record_async',
    'list_factor_candidate_records_async',
    'build_signal_definition',
    'evaluate_signal',
    'FactorLLMConfig',
    'FactorLLMProvider',
    'FactorLLMRequestError',
    'close_factor_llm_provider',
    'get_factor_llm_provider',
    'get_factor_candidate_schema_path',
    'load_factor_candidate_schema',
    'validate_factor_generation_payload',
    'SUPPORTED_FACTOR_FIELDS',
    'SUPPORTED_FACTOR_FUNCTIONS',
    'build_factor_feature_frame',
    'compile_factor_candidate',
    'evaluate_compiled_factor',
    'validate_factor_candidate_pipeline',
    'FactorResearchMemoryService',
    'get_factor_research_memory_service',
    'close_strategy_llm_provider',
    'close_strategy_text_embedding_service',
    'close_shared_runtime_clients',
    'bootstrap_ic_ci',
    'deflated_sharpe_ratio',
    'probability_of_backtest_overfitting',
    'white_reality_check',
    'hansen_spa_test',
    'create_chain',
    'add_evidence',
    'make_evidence',
    'set_conclusion',
    'save_chain',
    'get_chain',
    'query_chains_by_code',
    'query_chains_by_date',
    'list_chains',
    'summarize_chain',
]
