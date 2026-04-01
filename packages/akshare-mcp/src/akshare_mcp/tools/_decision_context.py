from ._decision_common import *

async def build_stock_context(
    code: str | None = None,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
):
    """构建股票上下文：基础骨架 + 行情快照 + 资金流 + 产业链。"""
    try:
        code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
        if not code:
            return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
        return ok(await _build_stock_context(code))
    except Exception as e:
        return fail(str(e))

async def build_quant_context(
    code: str | None = None,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
):
    """构建量化上下文：因子画像 + 条件收益 + 相似形态 + OOS 验证。"""
    try:
        code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
        if not code:
            return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
        return ok(await _build_quant_context(code))
    except Exception as e:
        return fail(str(e))

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
    try:
        code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
        if not code:
            return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
        return ok(
            await _build_event_context(
                code,
                news_limit=news_limit,
                notice_days=notice_days,
                report_limit=report_limit,
            )
        )
    except Exception as e:
        return fail(str(e))
