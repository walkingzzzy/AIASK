"""服务层"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

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
from .factor_validation_bootstrap import run_factor_validation_bootstrap
from .factor_research_memory import (
    FactorResearchMemoryService,
    get_factor_research_memory_service,
)
from .factor_external_research import (
    FACTOR_EXTERNAL_RESEARCH_STRATEGY,
    FACTOR_EXTERNAL_RESEARCH_VERSION,
    collect_external_factor_research,
    ingest_external_factor_research,
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
from .background_tasks import drain_background_tasks

logger = logging.getLogger(__name__)
_shared_runtime_clients_closing = False


async def _best_effort_close(name: str, callback: Callable[[], Awaitable[Any] | Any]) -> None:
    try:
        result = callback()
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        logger.warning("[services] close %s failed: %s", name, exc)


def _close_market_runtime_resources() -> None:
    try:
        from ..data_source.quotes import shutdown_efinance_executor

        shutdown_efinance_executor()
    except Exception as exc:
        logger.warning("[services] close efinance executor failed: %s", exc)
    try:
        from ..tools.market.helpers import shutdown_spot_executor

        shutdown_spot_executor()
    except Exception as exc:
        logger.warning("[services] close market spot executor failed: %s", exc)
    try:
        from ..tools.managers._execution_manager_support import shutdown_realtime_quote_executor

        shutdown_realtime_quote_executor()
    except Exception as exc:
        logger.warning("[services] close execution realtime executor failed: %s", exc)
    try:
        from ..data_source.tdx_local import get_tdx_local_source

        get_tdx_local_source().reset_hq()
    except Exception as exc:
        logger.warning("[services] close TDX HQ connection failed: %s", exc)
    try:
        from ..data_source.tdx_tqcenter import reset_tq

        reset_tq()
    except Exception as exc:
        logger.warning("[services] reset TQCenter runtime failed: %s", exc)


async def close_shared_runtime_clients() -> None:
    """关闭进程级共享资源，供一次性脚本/退出钩子显式调用。"""
    global _shared_runtime_clients_closing
    if _shared_runtime_clients_closing:
        return
    _shared_runtime_clients_closing = True
    try:
        await _best_effort_close("factor LLM provider", close_factor_llm_provider)
        await _best_effort_close("strategy LLM provider", close_strategy_llm_provider)
        await _best_effort_close("strategy text embedding service", close_strategy_text_embedding_service)
        _close_market_runtime_resources()
        await _best_effort_close("background tasks", drain_background_tasks)
        try:
            from ..storage import close_db, drain_cleanup_callbacks
        except Exception:
            close_db = None
            drain_cleanup_callbacks = None
        if callable(close_db):
            await _best_effort_close("storage database", close_db)
        if callable(drain_cleanup_callbacks):
            await _best_effort_close("storage cleanup callbacks", drain_cleanup_callbacks)
    finally:
        _shared_runtime_clients_closing = False

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
    'run_factor_validation_bootstrap',
    'FactorResearchMemoryService',
    'get_factor_research_memory_service',
    'FACTOR_EXTERNAL_RESEARCH_STRATEGY',
    'FACTOR_EXTERNAL_RESEARCH_VERSION',
    'collect_external_factor_research',
    'ingest_external_factor_research',
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
