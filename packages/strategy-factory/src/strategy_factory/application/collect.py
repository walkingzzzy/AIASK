"""策略工厂数据快照采集。"""


from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import numpy as np

from ..domain.constants import FACTORY_RESEARCH_FACTORS, resolve_event_runtime_mode
from .runtime import get_strategy_factory_package

logger = logging.getLogger(__name__)


def get_sentiment_analyzer():
    from ..infrastructure.mcp_services import get_sentiment_analyzer as _get_sentiment_analyzer

    return _get_sentiment_analyzer()

from strategy_factory._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'collect_parts',
    'class DataCollector:\n',
    ['normalizers.py', 'policy.py', 'evaluation.py'],
    future_annotations=True,
)



__all__ = ["DataCollector"]
