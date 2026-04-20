"""Lightweight asyncio-based factor scheduler.

Runs batch_compute_factors periodically (default: daily at 18:00 CST)
without requiring external dependencies like APScheduler or Celery.

Optionally runs LLM factor mining after classic batch computation when
FACTOR_LLM_ENABLED=1 and FACTOR_SCHEDULER_LLM_MINING!=0. The scheduler
defaults to enabling the LLM mining leg unless it is explicitly disabled.

Usage:
    from .factor_scheduler import FactorScheduler
    scheduler = FactorScheduler()
    scheduler.start()  # non-blocking, runs in background
    # ... later ...
    scheduler.stop()
"""


import asyncio
import json
import logging
import os
from contextlib import suppress
from datetime import datetime, time, timedelta
from typing import Any, List, Optional
from uuid import uuid4

from ..env_loader import load_mcp_env

logger = logging.getLogger(__name__)

# Default stock universe for daily factor computation
DEFAULT_UNIVERSE = [
    "000001", "000002", "000063", "000069", "000100",
    "000157", "000333", "000338", "000425", "000538",
    "000568", "000596", "000625", "000651", "000661",
    "000725", "000768", "000776", "000858", "000895",
    "002001", "002007", "002024", "002027", "002032",
    "002049", "002120", "002142", "002230", "002236",
    "002271", "002304", "002352", "002371", "002415",
    "002460", "002475", "002493", "002555", "002594",
    "002714", "002736", "002841", "002916", "002938",
    "300003", "300014", "300015", "300033", "300059",
    "600000", "600009", "600010", "600011", "600015",
    "600016", "600018", "600019", "600025", "600028",
    "600029", "600030", "600031", "600036", "600048",
    "600050", "600061", "600085", "600089", "600104",
    "600109", "600111", "600115", "600132", "600150",
    "600176", "600183", "600196", "600276", "600309",
    "600332", "600346", "600352", "600362", "600383",
    "600406", "600436", "600438", "600519", "600547",
    "600570", "600585", "600588", "600600", "600660",
    "600690", "600703", "600741", "600745", "600809",
    "600837", "600887", "600893", "600900", "601006",
    "601009", "601012", "601018", "601066", "601088",
    "601100", "601111", "601138", "601155", "601166",
    "601169", "601186", "601211", "601225", "601229",
    "601236", "601238", "601288", "601318", "601328",
    "601336", "601360", "601390", "601398", "601601",
    "601607", "601618", "601628", "601633", "601668",
    "601669", "601688", "601698", "601766", "601788",
    "601800", "601818", "601857", "601877", "601878",
    "601881", "601888", "601899", "601901", "601919",
    "601933", "601939", "601985", "601988", "601989",
    "601998", "603019", "603160", "603259", "603288",
    "603501", "603799", "603833", "603899", "603986",
]

DEFAULT_FACTORS = ["momentum", "value", "quality", "growth", "volatility", "reversal"]

from akshare_mcp._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'factor_scheduler_parts',
    'class FactorScheduler:\n',
    ['context.py', 'specs.py', 'runtime.py'],
    future_annotations=False,
)



# Singleton instance
_scheduler: Optional[FactorScheduler] = None


def get_factor_scheduler() -> FactorScheduler:
    """Get or create the global FactorScheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = FactorScheduler()
    return _scheduler
