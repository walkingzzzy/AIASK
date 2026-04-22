"""
fund_flow.py  (slimmed entry-point)
Individual stock fund flow + ``register(mcp)`` that wires every tool.

All heavy data-fetching logic lives in the sub-modules:
  - fund_flow_common   : shared constants / helpers / _ProxyBypass
  - fund_flow_north    : north-bound fund functions
  - fund_flow_sector   : sector & concept fund flow
  - fund_flow_market   : dragon-tiger / margin / block trades
"""

from datetime import date, timedelta

import requests

from ..core.rate_limiter import get_limiter
from ..data_source import data_source
from ..services.db_first_market_context import load_db_first_stock_fund_flow
from ..storage import get_db
from ..utils import (
    attach_argument_contract_meta,
    fail,
    normalize_code,
    ok,
    parse_numeric,
    resolve_canonical_arg,
    resolve_existing_security_code_sync,
)
from .fund_flow_common import _run_storage_call_sync

# -- Re-export public functions from sub-modules so existing
#    ``from ...fund_flow import get_north_fund`` style imports keep working.

from .fund_flow_north import (                      # noqa: F401
    get_north_fund,
    get_north_fund_holding,
    get_north_fund_top,
)
from .fund_flow_sector import (                     # noqa: F401
    get_sector_fund_flow,
    get_concept_fund_flow,
)
from .fund_flow_market import (                     # noqa: F401
    get_dragon_tiger,
    get_margin_data,
    get_margin_ranking,
    get_block_trades,
)


# =====================
# Individual stock fund flow (kept here)
# =====================


def _format_trade_date(value) -> str:
    raw = str(value or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return raw[:10] if raw else ""


def _get_stock_fund_flow_from_tushare(code: str) -> dict | None:
    try:
        pro = data_source.get_tushare_pro()
        if not pro:
            return None
        ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        df = pro.moneyflow(
            ts_code=ts_code,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        if df is None or df.empty:
            return None
        row = df.sort_values("trade_date", ascending=False).iloc[0].to_dict()
        small_inflow = (parse_numeric(row.get("buy_sm_amount")) or 0.0) - (parse_numeric(row.get("sell_sm_amount")) or 0.0)
        middle_inflow = (parse_numeric(row.get("buy_md_amount")) or 0.0) - (parse_numeric(row.get("sell_md_amount")) or 0.0)
        large_inflow = (parse_numeric(row.get("buy_lg_amount")) or 0.0) - (parse_numeric(row.get("sell_lg_amount")) or 0.0)
        super_large_inflow = (parse_numeric(row.get("buy_elg_amount")) or 0.0) - (parse_numeric(row.get("sell_elg_amount")) or 0.0)
        main_inflow = large_inflow + super_large_inflow
        denominator = sum(abs(value) for value in (small_inflow, middle_inflow, large_inflow, super_large_inflow))
        main_ratio = round(main_inflow / denominator * 100.0, 4) if denominator > 0 else None
        return {
            "code": code,
            "name": "",
            "mainNetInflow": main_inflow,
            "mainInflowPercent": main_ratio,
            "superLargeNetInflow": super_large_inflow,
            "largeNetInflow": large_inflow,
            "middleNetInflow": middle_inflow,
            "smallNetInflow": small_inflow,
            "tradeDate": _format_trade_date(row.get("trade_date")),
            "source": "tushare.moneyflow",
        }
    except Exception:
        return None

def get_stock_fund_flow(
    code: str = "",
    *,
    stock_code: str = "",
    symbol: str = "",
    ticker: str = "",
    prefer_db: bool = True,
) -> dict:
    """获取个股资金流向（主力/大单/中单/小单）"""
    try:
        limiter = get_limiter("fund_flow", max_calls=3, period=1.0)
        limiter.acquire()

        raw_code, alias_hits, _ = resolve_canonical_arg(
            "code",
            code,
            stock_code=stock_code,
            symbol=symbol,
            ticker=ticker,
        )
        code, _, error = resolve_existing_security_code_sync(code=raw_code)
        canonical_args = {"code": code or normalize_code(raw_code)}
        if error:
            return attach_argument_contract_meta(
                fail(error),
                canonical_tool="get_stock_fund_flow",
                canonical_args=canonical_args,
                alias_hits=alias_hits,
            )

        def _respond(payload: dict) -> dict:
            return attach_argument_contract_meta(
                payload,
                canonical_tool="get_stock_fund_flow",
                canonical_args=canonical_args,
                alias_hits=alias_hits,
            )

        if prefer_db:
            try:
                db_payload, _ = _run_storage_call_sync(
                    lambda: load_db_first_stock_fund_flow(get_db(), code),
                    timeout=8.0,
                )
                if db_payload:
                    return _respond(ok(db_payload))
            except Exception:
                pass

        tushare_payload = _get_stock_fund_flow_from_tushare(code)
        if tushare_payload:
            return _respond(ok(tushare_payload))

        market = "1" if code.startswith("6") else "0"
        secid = f"{market}.{code}"
        url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
        resp = requests.get(
            url,
            params={
                "secid": secid,
                "klt": 101,
                "fields1": "f1,f2,f3",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62",
                "lmt": 1,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        data = resp.json().get("data", {}) if resp.status_code == 200 else {}
        klines = data.get("klines") or []
        if not klines:
            return _respond(fail("未获取到资金流向数据"))
        parts = str(klines[-1]).split(",")
        main_inflow = parse_numeric(parts[1]) or 0
        small_inflow = parse_numeric(parts[2]) or 0
        middle_inflow = parse_numeric(parts[3]) or 0
        large_inflow = parse_numeric(parts[4]) or 0
        super_large_inflow = parse_numeric(parts[5]) or 0

        return _respond(ok(
            {
                "code": code,
                "name": str(data.get("name") or ""),
                "mainNetInflow": main_inflow,
                "mainInflowPercent": 0,
                "superLargeNetInflow": super_large_inflow,
                "largeNetInflow": large_inflow,
                "middleNetInflow": middle_inflow,
                "smallNetInflow": small_inflow,
                "source": "eastmoney.push2.fflow",
            }
        ))
    except Exception as e:
        return attach_argument_contract_meta(
            fail(e),
            canonical_tool="get_stock_fund_flow",
            canonical_args={"code": normalize_code(code) if code else ""},
            alias_hits=[],
        )


# =====================
# MCP tool registration
# =====================

def register(mcp):
    mcp.tool()(get_north_fund)
    mcp.tool()(get_sector_fund_flow)
    mcp.tool()(get_concept_fund_flow)
    mcp.tool()(get_dragon_tiger)
    mcp.tool()(get_margin_data)
    mcp.tool()(get_margin_ranking)
    mcp.tool()(get_block_trades)
    mcp.tool()(get_north_fund_holding)
    mcp.tool()(get_north_fund_top)
    mcp.tool()(get_stock_fund_flow)
