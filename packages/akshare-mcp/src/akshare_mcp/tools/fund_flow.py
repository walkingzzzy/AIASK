"""
fund_flow.py  (slimmed entry-point)
Individual stock fund flow + ``register(mcp)`` that wires every tool.

All heavy data-fetching logic lives in the sub-modules:
  - fund_flow_common   : shared constants / helpers / _ProxyBypass
  - fund_flow_north    : north-bound fund functions
  - fund_flow_sector   : sector & concept fund flow
  - fund_flow_market   : dragon-tiger / margin / block trades
"""

import requests

from ..utils import fail, normalize_code, ok, parse_numeric
from ..core.rate_limiter import get_limiter

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

def get_stock_fund_flow(stock_code: str) -> dict:
    """获取个股资金流向（主力/大单/中单/小单）"""
    try:
        limiter = get_limiter("fund_flow", max_calls=3, period=1.0)
        limiter.acquire()

        code = normalize_code(stock_code)
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
            return fail("未获取到资金流向数据")
        parts = str(klines[-1]).split(",")
        main_inflow = parse_numeric(parts[1]) or 0
        small_inflow = parse_numeric(parts[2]) or 0
        middle_inflow = parse_numeric(parts[3]) or 0
        large_inflow = parse_numeric(parts[4]) or 0
        super_large_inflow = parse_numeric(parts[5]) or 0

        return ok(
            {
                "code": code,
                "name": str(data.get("name") or ""),
                "mainNetInflow": main_inflow,
                "mainInflowPercent": 0,
                "superLargeNetInflow": super_large_inflow,
                "largeNetInflow": large_inflow,
                "middleNetInflow": middle_inflow,
                "smallNetInflow": small_inflow,
            }
        )
    except Exception as e:
        return fail(e)


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
