"""SQLite 适配器 — 策略 AI Mixin (generation experiments / task runs / factory runs)"""


import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from .strategy_factory_json_budget import (
    bounded_json_text,
    full_market_score_retention_runs,
    full_market_score_topn,
    strategy_json_field_max_bytes,
)
from aiask_quant_core._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'strategy_ai_parts',
    'class StrategyAIMixin:\n',
    ['reads.py', 'writes.py', 'queries.py', 'mappers.py'],
    future_annotations=False,
)
