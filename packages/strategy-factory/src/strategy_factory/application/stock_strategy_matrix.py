"""Bulk stock-strategy matrix planning for P0 factory expansion."""


from __future__ import annotations

import logging
import math
from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List

from ..domain.constants import (
    STOCK_STRATEGY_MATRIX_ENABLED,
    STOCK_FIRST_ROUTER_ENABLED,
    STOCK_FIRST_ROUTER_STRICT,
    STOCK_FIRST_ROUTER_TELEMETRY_ENABLED,
    STOCK_STRATEGY_MATRIX_BATCH_SIZE,
    STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN,
    STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK,
    STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK,
    STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN,
    STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD,
    STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
    STRATEGY_FACTORY_VECTOR_REUSE_ENABLED,
    STRATEGY_FACTORY_VECTOR_REUSE_MIN_SAMPLES,
    STRATEGY_FACTORY_VECTOR_REUSE_MIN_SIMILARITY,
    STRATEGY_FACTORY_VECTOR_REUSE_TOPN,
    STRATEGY_FACTORY_VECTOR_SIMILAR_PROFILE_ENABLED,
    preferred_strategy_types_for_factor,
)
from ._opportunity_utils import _MarketOpportunityScannerUtilityMixin
from ._stock_universe_loader import filter_stock_universe_rows_by_codes, load_stock_universe_rows
from .factory_market_views import build_full_market_topn_payload
from .factory_execution import resolve_runtime_mode_flags
from ._matrix_vector_reuse import VectorReuseService
from .research_plane_contract import build_task_artifact
from .stock_strategy_router import StockRegimeProfile, route_strategies
from .sector_taxonomy import (
    normalize_sector_labels,
    sector_profiles_for_label,
    sector_family_biases,
    sector_match_strength,
)

logger = logging.getLogger(__name__)

from strategy_factory._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'stock_strategy_matrix_parts',
    'class StockStrategyMatrixPlanner(_MarketOpportunityScannerUtilityMixin):\n',
    ['normalizers.py', 'policy.py', 'evaluation.py'],
    future_annotations=True,
)



__all__ = ["StockStrategyMatrixPlanner"]
