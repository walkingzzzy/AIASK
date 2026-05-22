"""策略自治生成：本地 LLM 代理 + 参数进化 + 实验闭环。"""


from __future__ import annotations

import asyncio
from collections import Counter
import logging
from datetime import date
from typing import Any, Optional
from uuid import uuid4

from strategy_factory import extract_event_context as _extract_event_context
from .strategy_autonomy_components import (  # noqa: F401
    CandidateGenerationService,
    CommitteeReviewService,
    ExperimentRecorder,
)
from .strategy_autonomy_lifecycle import AutonomyLifecycleTracker

# --- Sub-module re-exports (backward compatibility) ---
from .strategy_spec import (  # noqa: F401
    DEFAULT_CODES,
    RESEARCH_CANDIDATE_POOL_LIMIT,
    RESEARCH_FINANCIAL_DETAIL_LIMIT,
    RESEARCH_KLINE_SCAN_LIMIT,
    RESEARCH_SYMBOL_DETAIL_LIMIT,
    RESEARCH_UNIVERSE_PAGE_SIZE,
    RESEARCH_UNIVERSE_SCAN_LIMIT,
    StrategySpec,
    _safe_normalize_research_task,
)
from .strategy_generators import RuleStrategyGenerator, LLMProxyStrategyGenerator  # noqa: F401
from .strategy_optimizer import BanditParameterOptimizer  # noqa: F401
from .strategy_reviewer import MultiAgentStrategyReviewer  # noqa: F401

logger = logging.getLogger(__name__)

from akshare_mcp._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'strategy_autonomy_parts',
    'class AutonomyCycleOrchestrator:\n',
    ['context.py', 'specs.py', 'runtime.py'],
    future_annotations=True,
)



class StrategyAutonomyService(AutonomyCycleOrchestrator):
    """Backward-compatible public entry point for autonomy orchestration."""


_strategy_autonomy_service: Optional[StrategyAutonomyService] = None


def get_strategy_autonomy_service() -> StrategyAutonomyService:
    global _strategy_autonomy_service
    if _strategy_autonomy_service is None:
        _strategy_autonomy_service = StrategyAutonomyService()
    return _strategy_autonomy_service
