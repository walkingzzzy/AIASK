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


def _mock_governed_factor_research(
    monkeypatch,
    *,
    factor_names=None,
    preferred_strategy_types=None,
):
    resolved_factor_names = [str(item) for item in (factor_names or ["quality"]) if str(item).strip()]
    resolved_preferred = [
        str(item) for item in (preferred_strategy_types or ["sector_breakout"]) if str(item).strip()
    ]
    candidate_families = list(resolved_preferred[: len(resolved_factor_names)])
    if len(candidate_families) < len(resolved_factor_names):
        fill_value = resolved_preferred[-1] if resolved_preferred else "sector_breakout"
        candidate_families.extend([fill_value] * (len(resolved_factor_names) - len(candidate_families)))
    monkeypatch.setattr(
        "strategy_factory.infrastructure.mcp_adapters.MCPFactorResearchGatewayImpl.build_artifact",
        AsyncMock(
            return_value={
                "active_factors": [{"factor_name": name} for name in resolved_factor_names],
                "active_candidates": [
                    {"factor_name": name, "family": family}
                    for name, family in zip(resolved_factor_names, candidate_families)
                ],
                "active_family_summary": [{"family": family, "count": 1} for family in resolved_preferred],
                "active_regime_summary": [{"regime": "neutral", "count": len(resolved_factor_names) or 1}],
                "preferred_strategy_types": list(resolved_preferred),
                "source_chain": ["governed_candidate_pool"],
                "research_rationale": ["mock governed pool ready"],
                "degraded": False,
                "summary": {
                    "active_factor_count": len(resolved_factor_names),
                    "active_candidate_count": len(resolved_factor_names),
                    "ranked_factor_count": len(resolved_factor_names),
                    "top_factor_names": list(resolved_factor_names),
                    "top_candidate_names": list(candidate_families),
                    "preferred_strategy_types": list(resolved_preferred),
                    "factor_source_mode": "governed_candidate_pool",
                    "governed_candidate_pool_mode": "strict_governed",
                    "governed_candidate_pool_provisional": False,
                    "governed_candidate_pool_active": True,
                    "governed_candidate_pool_runtime_state": "active",
                    "governed_source_candidate_count": len(resolved_factor_names),
                    "governed_blocked_candidate_count": 0,
                    "governed_pending_candidate_count": 0,
                    "governed_blocked_ratio": 0.0,
                    "governed_pending_ratio": 0.0,
                    "governed_freshness_days": 0.0,
                    "scheduler_recent_success": True,
                    "scheduler_llm_validation_status": "success",
                    "quality_flags": [],
                },
                "freshness_repair": {
                    "auto_refresh_enabled": True,
                    "refresh_attempted": False,
                    "refresh_status": "not_needed",
                    "refresh_trigger": None,
                },
            }
        ),
    )


# ═══════════════════════════════════════════════════════════════
# 8. 策略管理器 (strategy_manager) 测试
# ═══════════════════════════════════════════════════════════════

import akshare_mcp.tools.managers.strategy_manager as sm_mod

from ._strategy_factory_test_support import _DummyMCP, _StrategyConn, _StrategyDB


__all__ = [name for name in globals() if name not in {"__builtins__", "__all__"}]
