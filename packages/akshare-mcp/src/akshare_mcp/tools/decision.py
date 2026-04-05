"""决策工具"""

from __future__ import annotations

import asyncio

from ..storage import get_db as _default_get_db
from . import _decision_buy as _decision_buy_mod
from . import _decision_common as _decision_common_mod
from . import _decision_context as _decision_context_mod
from . import _decision_sell as _decision_sell_mod
from . import _decision_unified as _decision_unified_mod

get_db = _default_get_db
technical_analysis = _decision_common_mod.technical_analysis
factor_calculator = _decision_common_mod.factor_calculator
get_investment_analysis = _decision_common_mod.get_investment_analysis

_decision_lock = asyncio.Lock()


def _sync_decision_overrides() -> None:
    """Keep decision submodules aligned with decision-level monkeypatches."""
    for module in (
        _decision_buy_mod,
        _decision_common_mod,
        _decision_context_mod,
        _decision_sell_mod,
        _decision_unified_mod,
    ):
        module.get_db = get_db
        module.technical_analysis = technical_analysis
        module.factor_calculator = factor_calculator
    for module in (
        _decision_buy_mod,
        _decision_context_mod,
        _decision_sell_mod,
        _decision_unified_mod,
    ):
        module.get_investment_analysis = get_investment_analysis


async def should_i_buy(*args, **kwargs):
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_buy_mod.should_i_buy(*args, **kwargs)


async def should_i_sell(*args, **kwargs):
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_sell_mod.should_i_sell(*args, **kwargs)


async def build_stock_context(*args, **kwargs):
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_context_mod.build_stock_context(*args, **kwargs)


async def build_quant_context(*args, **kwargs):
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_context_mod.build_quant_context(*args, **kwargs)


async def build_event_context(*args, **kwargs):
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_context_mod.build_event_context(*args, **kwargs)


async def run_decision_gate(*args, **kwargs):
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_unified_mod.run_decision_gate(*args, **kwargs)


async def fuse_decision_payload(*args, **kwargs):
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_unified_mod.fuse_decision_payload(*args, **kwargs)


async def get_unified_decision_summary(*args, **kwargs):
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_unified_mod.get_unified_decision_summary(*args, **kwargs)


async def get_unified_decision_details(*args, **kwargs):
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_unified_mod.get_unified_decision_details(*args, **kwargs)


async def get_unified_decision(*args, **kwargs):
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_unified_mod.get_unified_decision(*args, **kwargs)


def register(mcp):
    """注册决策工具"""
    mcp.tool()(should_i_buy)
    mcp.tool()(should_i_sell)
    mcp.tool()(build_stock_context)
    mcp.tool()(build_quant_context)
    mcp.tool()(build_event_context)
    mcp.tool()(run_decision_gate)
    mcp.tool()(fuse_decision_payload)
    mcp.tool()(get_unified_decision_summary)
    mcp.tool()(get_unified_decision_details)
    mcp.tool()(get_unified_decision)
    mcp.tool()(get_investment_analysis)
