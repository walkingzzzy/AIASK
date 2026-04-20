"""策略工厂去重分析。"""


from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import numpy as np

from .candidate_contract import build_candidate_identity_signature, build_tested_object_hash
from .runtime import get_strategy_factory_package as _runtime_get_strategy_factory_package
from .utils import _extract_event_context as _local_extract_event_context
from ..domain.constants import DEDUP_CONCURRENCY
from ..domain.strategy_profile import infer_candidate_strategy_profile
from ..domain.targets import _build_task_signature, _extract_target_codes_from_payload, _normalize_research_task_contract

if TYPE_CHECKING:
    from ..api.contracts import VectorSearchGateway

def _compat_setting(name: str, default):
    return default


def _extract_event_context(*args, **kwargs):
    return _local_extract_event_context(*args, **kwargs)


def _get_strategy_factory_package():
    return _runtime_get_strategy_factory_package()

logger = logging.getLogger(__name__)

from strategy_factory._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'deduplicator_parts',
    'class Deduplicator:\n',
    ['normalizers.py', 'policy.py', 'evaluation.py', 'reporting.py'],
    future_annotations=True,
)
