"""向量搜索工具 - 基于特征相似度的实现"""

from __future__ import annotations

import asyncio

from ..storage import get_db as _default_get_db
from . import _vector_common as _vector_common_mod
from . import _vector_search_kline as _vector_search_kline_mod
from . import _vector_search_semantic as _vector_search_semantic_mod
from . import _vector_search_similar as _vector_search_similar_mod

get_db = _default_get_db
technical_analysis = _vector_common_mod.technical_analysis
factor_calculator = _vector_common_mod.factor_calculator

_vector_lock = asyncio.Lock()


def _sync_vector_overrides() -> None:
    """Keep vector submodules aligned with vector-level monkeypatches."""
    _vector_common_mod.get_db = get_db
    _vector_common_mod.technical_analysis = technical_analysis
    _vector_common_mod.factor_calculator = factor_calculator
    _vector_search_kline_mod.get_db = get_db
    _vector_search_semantic_mod.get_db = get_db
    _vector_search_similar_mod.get_db = get_db


async def search_similar_stocks(*args, **kwargs):
    async with _vector_lock:
        _sync_vector_overrides()
        return await _vector_search_similar_mod.search_similar_stocks(*args, **kwargs)


async def search_by_kline(*args, **kwargs):
    async with _vector_lock:
        _sync_vector_overrides()
        return await _vector_search_kline_mod.search_by_kline(*args, **kwargs)


async def semantic_stock_search(*args, **kwargs):
    async with _vector_lock:
        _sync_vector_overrides()
        return await _vector_search_semantic_mod.semantic_stock_search(*args, **kwargs)


def register(mcp):
    """注册向量搜索工具"""
    mcp.tool()(search_similar_stocks)
    mcp.tool()(search_by_kline)
    mcp.tool()(semantic_stock_search)
