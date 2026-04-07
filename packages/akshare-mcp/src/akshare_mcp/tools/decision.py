"""决策工具"""

from __future__ import annotations

import asyncio

from ..storage import get_db as _default_get_db
from ..services.decision_contracts import (
    get_unified_decision_details_payload as _default_get_unified_decision_details_payload,
    get_unified_decision_summary_payload as _default_get_unified_decision_summary_payload,
)
from . import _decision_buy as _decision_buy_mod
from . import _decision_common as _decision_common_mod
from . import _decision_context as _decision_context_mod
from . import _decision_sell as _decision_sell_mod
from . import _decision_unified as _decision_unified_mod

get_db = _default_get_db
technical_analysis = _decision_common_mod.technical_analysis
factor_calculator = _decision_common_mod.factor_calculator
get_unified_decision_summary_payload = _default_get_unified_decision_summary_payload
get_unified_decision_details_payload = _default_get_unified_decision_details_payload

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
    _decision_common_mod.get_unified_decision_summary_payload = get_unified_decision_summary_payload
    _decision_common_mod.get_unified_decision_details_payload = get_unified_decision_details_payload
    _decision_unified_mod.get_unified_decision_summary_payload = get_unified_decision_summary_payload
    _decision_unified_mod.get_unified_decision_details_payload = get_unified_decision_details_payload
    for module in (
        _decision_buy_mod,
        _decision_context_mod,
        _decision_sell_mod,
        _decision_unified_mod,
    ):
        module.get_investment_analysis = get_investment_analysis


async def get_investment_analysis(
    code: str | None = None,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
):
    """投资分析数据汇聚：透传顶层 monkeypatch 到底层实现。

    注意：这里不能再次等待 ``_decision_lock``。
    ``should_i_buy`` / ``should_i_sell`` 会在持有该锁时调用当前函数；
    如果在这里重入同一把锁，会形成自锁并最终把整个 MCP 请求拖到超时。
    """
    _sync_decision_overrides()
    return await _decision_common_mod.get_investment_analysis(
        code=code,
        stock_code=stock_code,
        symbol=symbol,
        ticker=ticker,
    )


async def should_i_buy(
    code: str | None = None,
    investment_style: str = 'balanced',
    as_of: str = '',
    adjust: str = '',
    price_source_policy: str = 'auto',
    explain: bool = True,
    strict_mode: bool = False,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
):
    """买入建议 - 综合估值、技术、基本面、因子分析"""
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_buy_mod.should_i_buy(
            code=code, investment_style=investment_style, as_of=as_of,
            adjust=adjust, price_source_policy=price_source_policy,
            explain=explain, strict_mode=strict_mode,
            stock_code=stock_code, symbol=symbol, ticker=ticker,
        )


async def should_i_sell(
    code: str | None = None,
    buy_price: float = 0.0,
    holding_days: int = 0,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
):
    """卖出建议 - 综合止盈止损、技术信号、持仓时间分析"""
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_sell_mod.should_i_sell(
            code=code, buy_price=buy_price, holding_days=holding_days,
            stock_code=stock_code, symbol=symbol, ticker=ticker,
        )


async def build_stock_context(
    code: str | None = None,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
):
    """构建股票上下文：基础骨架 + 行情快照 + 资金流 + 产业链。"""
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_context_mod.build_stock_context(
            code=code, stock_code=stock_code, symbol=symbol, ticker=ticker,
        )


async def build_quant_context(
    code: str | None = None,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
):
    """构建量化上下文：因子画像 + 条件收益 + 相似形态 + OOS 验证。"""
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_context_mod.build_quant_context(
            code=code, stock_code=stock_code, symbol=symbol, ticker=ticker,
        )


async def build_event_context(
    code: str | None = None,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
    news_limit: int = 12,
    notice_days: int = 30,
    report_limit: int = 6,
):
    """构建事件上下文：新闻/公告/研报聚合、事件分类与 veto 候选。"""
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_context_mod.build_event_context(
            code=code, stock_code=stock_code, symbol=symbol, ticker=ticker,
            news_limit=news_limit, notice_days=notice_days, report_limit=report_limit,
        )


async def run_decision_gate(
    code: str | None = None,
    investment_style: str = 'balanced',
    user_id: str | None = None,
    stock_context: dict | None = None,
    quant_context: dict | None = None,
    event_context: dict | None = None,
    user_context: dict | None = None,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
):
    """运行统一决策规则闸门，可传入现成上下文，也可按代码自动构建。"""
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_unified_mod.run_decision_gate(
            code=code, investment_style=investment_style, user_id=user_id,
            stock_context=stock_context, quant_context=quant_context,
            event_context=event_context, user_context=user_context,
            stock_code=stock_code, symbol=symbol, ticker=ticker,
        )


async def fuse_decision_payload(
    code: str | None = None,
    investment_style: str = 'balanced',
    user_id: str | None = None,
    stock_context: dict | None = None,
    quant_context: dict | None = None,
    event_context: dict | None = None,
    user_context: dict | None = None,
    gate: dict | None = None,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
):
    """融合统一决策上下文，输出 action/summary/weights/raw_ai_output。"""
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_unified_mod.fuse_decision_payload(
            code=code, investment_style=investment_style, user_id=user_id,
            stock_context=stock_context, quant_context=quant_context,
            event_context=event_context, user_context=user_context,
            gate=gate, stock_code=stock_code, symbol=symbol, ticker=ticker,
        )


async def get_unified_decision_summary(
    code: str | None = None,
    investment_style: str = 'balanced',
    user_id: str | None = None,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
):
    """统一决策摘要：输出前端友好的 summary 卡片。"""
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_unified_mod.get_unified_decision_summary(
            code=code, investment_style=investment_style, user_id=user_id,
            stock_code=stock_code, symbol=symbol, ticker=ticker,
        )


async def get_unified_decision_details(
    code: str | None = None,
    investment_style: str = 'balanced',
    user_id: str | None = None,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
):
    """统一决策详情：输出 summary + 全量 details 证据。"""
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_unified_mod.get_unified_decision_details(
            code=code, investment_style=investment_style, user_id=user_id,
            stock_code=stock_code, symbol=symbol, ticker=ticker,
        )


async def get_unified_decision(
    code: str | None = None,
    detail_level: str = 'summary',
    investment_style: str = 'balanced',
    user_id: str | None = None,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
):
    """统一决策兼容包装器：按 detail_level 返回 summary 或 details。"""
    async with _decision_lock:
        _sync_decision_overrides()
        return await _decision_unified_mod.get_unified_decision(
            code=code, detail_level=detail_level, investment_style=investment_style,
            user_id=user_id, stock_code=stock_code, symbol=symbol, ticker=ticker,
        )


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
