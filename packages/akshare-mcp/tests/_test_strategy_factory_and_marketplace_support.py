"""策略工厂 + 策略超市 全面测试

覆盖:
- 策略注册表 (StrategyRegistry)
- 9种策略的信号生成 + 回测引擎集成
- 策略工厂各组件 (DataCollector, StrategySpawner, BacktestFilter, Deduplicator, EliminationChecker)
- 策略管理器 (strategy_manager) CRUD + 生命周期 + 质检
- RRF 排名引擎
"""

import asyncio
import json
import math
import pytest
import numpy as np
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# ── 策略工厂组件 ──

from akshare_mcp.services.strategy_factory import (
    DataCollector, StrategySpawner, BacktestFilter, Deduplicator,
    EliminationChecker, MarketOpportunityScanner, StrategyFactoryScheduler, _auto_name,
    CATEGORY_MINIMUMS, REPRESENTATIVE_STOCKS,
)

# ── 排名引擎 ──

from akshare_mcp.services.ranking import rrf_rank

# ── 回测引擎 ──

from akshare_mcp.services.backtest.engine import BacktestEngine
from ._strategy_factory_marketplace_helpers import _make_klines


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _type_name(value):
    return type(value).__name__


# ═══════════════════════════════════════════════════════════════
# 8. 策略管理器 (strategy_manager) 测试
# ═══════════════════════════════════════════════════════════════

import akshare_mcp.tools.managers.strategy_manager as sm_mod

from ._strategy_factory_test_support import _DummyMCP, _StrategyConn, _StrategyDB


__all__ = [name for name in globals() if name not in {"__builtins__", "__all__"}]
