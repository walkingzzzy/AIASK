"""策略工厂候选生成。"""


from __future__ import annotations

import json
import random
from typing import Any, Dict, List, Optional

from .constants import (
    CATEGORY_MINIMUMS,
    SPAWNER_EVENT_SOURCE_BASE_CAP,
    SPAWNER_EVENT_SOURCE_SUPPLEMENTAL_BONUS,
    SPAWNER_EVENT_FILL_BUDGET_MAX,
    SPAWNER_FILL_BUDGET_MAX,
    SPAWNER_TARGET_TOTAL,
    STRATEGY_FACTORY_FACTOR_IC_CLASSIC_FALLING_MAX_IC,
    STRATEGY_FACTORY_FACTOR_IC_CLASSIC_MIN_IC,
    STRATEGY_FACTORY_FACTOR_IC_GENERIC_INTAKE_ENABLED,
    STRATEGY_FACTORY_FACTOR_IC_GENERIC_MIN_ABS_IC,
    STRATEGY_FACTORY_FACTOR_IC_GENERIC_MAX_FACTORS,
    preferred_strategy_types_for_factor,
)
from .parameter_distribution_registry import ParameterDistributionRegistry
from .spawn_policy_registry import (
    get_event_focus_targets_by_keyword,
    get_event_ready_source_weights,
    get_spawn_policy_version,
)
from .targets import _normalize_target_codes

from strategy_factory._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'spawner_parts',
    'class StrategySpawner:\n',
    ['matching.py', 'selection.py', 'factories.py', 'serialization.py', 'part_5.py'],
    future_annotations=True,
)
