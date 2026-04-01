from ._decision_common import *

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
    try:
        code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
        if not code:
            return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
        built_stock = stock_context if isinstance(stock_context, dict) else await _build_stock_context(code)
        built_quant = quant_context if isinstance(quant_context, dict) else await _build_quant_context(code)
        built_event = event_context if isinstance(event_context, dict) else await _build_event_context(code)
        built_user = user_context if isinstance(user_context, dict) else await _build_user_context(user_id)
        gate = _build_rule_gates(
            code=code,
            investment_style=investment_style,
            stock_context=built_stock,
            quant_context=built_quant,
            event_context=built_event,
            user_context=built_user,
        )
        return ok(gate)
    except Exception as e:
        return fail(str(e))

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
    try:
        code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
        if not code:
            return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
        built_stock = stock_context if isinstance(stock_context, dict) else await _build_stock_context(code)
        built_quant = quant_context if isinstance(quant_context, dict) else await _build_quant_context(code)
        built_event = event_context if isinstance(event_context, dict) else await _build_event_context(code)
        built_user = user_context if isinstance(user_context, dict) else await _build_user_context(user_id)
        built_gate = gate if isinstance(gate, dict) else _build_rule_gates(
            code=code,
            investment_style=investment_style,
            stock_context=built_stock,
            quant_context=built_quant,
            event_context=built_event,
            user_context=built_user,
        )
        return ok(
            _fuse_unified_decision(
                stock_context=built_stock,
                quant_context=built_quant,
                event_context=built_event,
                user_context=built_user,
                gate=built_gate,
            )
        )
    except Exception as e:
        return fail(str(e))

async def get_unified_decision_summary(
    code: str | None = None,
    investment_style: str = 'balanced',
    user_id: str | None = None,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
):
    """统一决策摘要：输出前端友好的 summary 卡片。"""
    try:
        code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
        if not code:
            return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
        payload = await get_unified_decision_summary_payload(
            code=code,
            investment_style=investment_style,
            user_id=user_id,
        )
        return ok(payload)
    except Exception as e:
        return fail(str(e))

async def get_unified_decision_details(
    code: str | None = None,
    investment_style: str = 'balanced',
    user_id: str | None = None,
    stock_code: str | None = None,
    symbol: str | None = None,
    ticker: str | None = None,
):
    """统一决策详情：输出 summary + 全量 details 证据。"""
    try:
        code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
        if not code:
            return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
        payload = await get_unified_decision_details_payload(
            code=code,
            investment_style=investment_style,
            user_id=user_id,
        )
        return ok(payload)
    except Exception as e:
        return fail(str(e))

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
    try:
        code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
        if not code:
            return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
        if str(detail_level or 'summary').strip().lower() == 'details':
            payload = await get_unified_decision_details_payload(
                code=code,
                investment_style=investment_style,
                user_id=user_id,
            )
        else:
            payload = await get_unified_decision_summary_payload(
                code=code,
                investment_style=investment_style,
                user_id=user_id,
            )
        return ok(payload)
    except Exception as e:
        return fail(str(e))
