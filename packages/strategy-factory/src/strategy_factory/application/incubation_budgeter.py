"""Dynamic incubation slot allocator for the P2 factory lane."""


from __future__ import annotations

import math
from typing import Any

from ._budget_feedback import (
    extract_feedback_root,
    extract_generator_mode,
    extract_target_pool_id,
    normalize_feedback_input_contract,
    resolve_feedback_metrics,
)
from ..domain.constants import (
    FACTORY_INCUBATION_EXPLORATION_RATIO,
    FACTORY_INCUBATION_FORMAL_SLOT_COUNT,
    FACTORY_INCUBATION_OBSERVE_SLOT_COUNT,
)

_BASE_PRIORITY_SHARPE_WEIGHT = 10.0
_BASE_PRIORITY_TOTAL_RETURN_WEIGHT = 3.0
_BASE_PRIORITY_MAX_DRAWDOWN_WEIGHT = 8.0

from strategy_factory._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'incubation_budgeter_parts',
    'class IncubationBudgeter:\n',
    ['normalizers.py', 'policy.py', 'evaluation.py'],
    future_annotations=True,
)



__all__ = ["IncubationBudgeter"]
