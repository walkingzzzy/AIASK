
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from copy import deepcopy
from typing import Any, Optional

import pandas as pd
def _get_strategy_factory_imports():
    from strategy_factory.api import (
        extract_event_context as _extract_event_context,
        preferred_strategy_types_for_factor,
    )
    from strategy_factory.api.constants import (
        CATEGORY_MINIMUMS,
        LLM_FAN_OUT_COUNT,
        PIPELINE_MODE,
        PIPELINE_STAGE_TIMEOUTS,
        PIPELINE_STAGE_TIMEOUT_SEC,
    )
    from strategy_factory.api.semantic_contract import HypothesisLoweringCompiler
    from strategy_factory.api.semantic_contract import validate_precompile_candidate_contract
    from strategy_factory.api.semantic_contract import synthesize_confidence_contract
    from strategy_factory.api.semantic_contract import apply_target_symbol_policy, normalize_research_task_contract
    return {
        "CATEGORY_MINIMUMS": CATEGORY_MINIMUMS,
        "HypothesisLoweringCompiler": HypothesisLoweringCompiler,
        "LLM_FAN_OUT_COUNT": LLM_FAN_OUT_COUNT,
        "PIPELINE_MODE": PIPELINE_MODE,
        "PIPELINE_STAGE_TIMEOUTS": PIPELINE_STAGE_TIMEOUTS,
        "PIPELINE_STAGE_TIMEOUT_SEC": PIPELINE_STAGE_TIMEOUT_SEC,
        "extract_event_context": _extract_event_context,
        "preferred_strategy_types_for_factor": preferred_strategy_types_for_factor,
        "apply_target_symbol_policy": apply_target_symbol_policy,
        "normalize_research_task_contract": normalize_research_task_contract,
        "synthesize_confidence_contract": synthesize_confidence_contract,
        "validate_precompile_candidate_contract": validate_precompile_candidate_contract,
    }


import functools as _functools


@_functools.lru_cache(maxsize=1)
def _sf():
    return _get_strategy_factory_imports()


class _LazyProxy:
    """Module-level proxy to defer strategy_factory imports until first access."""
    def __getattr__(self, name):
        return _sf()[name]

_lazy = _LazyProxy()


def __getattr__(name):
    _map = {
        "CATEGORY_MINIMUMS": "CATEGORY_MINIMUMS",
        "LLM_FAN_OUT_COUNT": "LLM_FAN_OUT_COUNT",
        "PIPELINE_MODE": "PIPELINE_MODE",
        "_extract_event_context": "extract_event_context",
        "HypothesisLoweringCompiler": "HypothesisLoweringCompiler",
        "preferred_strategy_types_for_factor": "preferred_strategy_types_for_factor",
        "apply_target_symbol_policy": "apply_target_symbol_policy",
        "normalize_research_task_contract": "normalize_research_task_contract",
        "synthesize_confidence_contract": "synthesize_confidence_contract",
        "validate_precompile_candidate_contract": "validate_precompile_candidate_contract",
    }
    if name in _map:
        return _sf()[_map[name]]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


CATEGORY_MINIMUMS = _sf()["CATEGORY_MINIMUMS"]
HypothesisLoweringCompiler = _sf()["HypothesisLoweringCompiler"]
LLM_FAN_OUT_COUNT = _sf()["LLM_FAN_OUT_COUNT"]
PIPELINE_MODE = _sf()["PIPELINE_MODE"]
_extract_event_context = _sf()["extract_event_context"]
preferred_strategy_types_for_factor = _sf()["preferred_strategy_types_for_factor"]
apply_target_symbol_policy = _sf()["apply_target_symbol_policy"]
normalize_research_task_contract = _sf()["normalize_research_task_contract"]
synthesize_confidence_contract = _sf()["synthesize_confidence_contract"]
validate_precompile_candidate_contract = _sf()["validate_precompile_candidate_contract"]

from .llm_alpha import LLMAlphaMiner
from .data_pipeline import normalize_klines
from .strategy_dsl import compile_strategy_blueprint
from .strategy_hypothesis_generator import LLMHypothesisGenerator
from .strategy_llm_provider import get_strategy_llm_provider
from .strategy_open_dsl import (
    compile_open_dsl_candidate,
    is_open_dsl_candidate,
)
from .strategy_pipeline import get_strategy_pipeline
from .strategy_spec import (
    DEFAULT_CODES,
    RESEARCH_CANDIDATE_POOL_LIMIT,
    RESEARCH_FINANCIAL_DETAIL_LIMIT,
    RESEARCH_KLINE_SCAN_LIMIT,
    RESEARCH_SYMBOL_DETAIL_LIMIT,
    RESEARCH_UNIVERSE_PAGE_SIZE,
    RESEARCH_UNIVERSE_SCAN_LIMIT,
    StrategySpec,
    _default_holding_horizon,
    _default_rebalance_rule,
    _default_risk_rules,
)

logger = logging.getLogger(__name__)
