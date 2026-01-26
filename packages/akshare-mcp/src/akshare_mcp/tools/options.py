from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import akshare as ak

from ..core.cache_manager import cached
from ..core.rate_limiter import get_limiter
from ..utils import (
    fail,
    ok,
    parse_numeric,
    safe_int,
)


@cached(ttl=5.0)  # 5秒缓存，期权数据实时性要求高
def get_option_chain(underlying: str, expiry_month: str = "", limit: int = 200) -> dict:
    """
    获取上交所ETF期权链数据（Sina）

    Args:
        underlying: 标的代码 510050/510300 或 50ETF/300ETF
        expiry_month: 到期月份 YYYY-MM 或 YYYYMM，不传默认最近到期
        limit: 最大合约数量（默认200）
    """
    limiter = get_limiter("options", rate=5.0)  # 5次/秒
    limiter.acquire()
    
    try:
        raw_underlying = str(underlying or "").strip().upper()
        underlying_map = {
            "510050": "50ETF",
            "50ETF": "50ETF",
            "510300": "300ETF",
            "300ETF": "300ETF",
        }
        symbol = underlying_map.get(raw_underlying)
        if not symbol:
            return fail(f"不支持的标的: {underlying}")

        underlying_code = "510050" if symbol == "50ETF" else "510300"
        underlying_spot = f"sh{underlying_code}"

        months = ak.option_sse_list_sina(symbol=symbol)
        if not months:
            return fail("未获取到期权到期月份列表")

        raw_month = str(expiry_month or "").strip().replace("-", "")
        if raw_month and len(raw_month) == 6:
            target_months = [raw_month]
        elif raw_month:
            return fail("expiry_month 格式错误，应为 YYYY-MM 或 YYYYMM")
        else:
            target_months = [months[0]]

        valid_months = [m for m in target_months if m in months]
        if not valid_months:
            return fail(f"期权到期月份不可用: {expiry_month}")

        limit = int(limit)
        if limit <= 0:
            limit = 200
        limit = min(limit, 1000)

        contracts: list[dict[str, Any]] = []
        for month in valid_months:
            call_df = ak.option_sse_codes_sina(
                symbol="看涨期权",
                trade_date=month,
                underlying=underlying_code,
            )
            put_df = ak.option_sse_codes_sina(
                symbol="看跌期权",
                trade_date=month,
                underlying=underlying_code,
            )
            call_codes = call_df["期权代码"].dropna().astype(str).tolist() if call_df is not None else []
            put_codes = put_df["期权代码"].dropna().astype(str).tolist() if put_df is not None else []
            for code in call_codes:
                contracts.append({"code": code, "type": "call", "expiryMonth": month})
            for code in put_codes:
                contracts.append({"code": code, "type": "put", "expiryMonth": month})

        truncated = len(contracts) > limit
        if truncated:
            contracts = contracts[:limit]

        def fetch_contract(contract: dict) -> Optional[dict]:
            code = contract["code"]
            df = ak.option_sse_spot_price_sina(symbol=code)
            if df is None or df.empty or "字段" not in df.columns:
                return None
            data = dict(zip(df["字段"], df["值"]))
            return {
                "code": code,
                "name": str(data.get("期权合约简称", "")),
                "type": contract["type"],
                "expiryMonth": contract["expiryMonth"],
                "strike": parse_numeric(data.get("行权价")),
                "last": parse_numeric(data.get("最新价")),
                "bid": parse_numeric(data.get("买价")),
                "ask": parse_numeric(data.get("卖价")),
                "bidVolume": safe_int(data.get("买量")),
                "askVolume": safe_int(data.get("卖量")),
                "open": parse_numeric(data.get("开盘价")),
                "high": parse_numeric(data.get("最高价")),
                "low": parse_numeric(data.get("最低价")),
                "prevClose": parse_numeric(data.get("昨收价")),
                "changePercent": parse_numeric(data.get("涨幅")),
                "volume": safe_int(data.get("成交量")),
                "amount": parse_numeric(data.get("成交额")),
                "openInterest": safe_int(data.get("持仓量")),
                "time": str(data.get("行情时间", "")),
                "underlying": str(data.get("标的股票", underlying_code)),
            }

        options: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(fetch_contract, c) for c in contracts]
            for future in futures:
                try:
                    item = future.result(timeout=10)
                    if item:
                        options.append(item)
                except Exception:
                    continue

        underlying_df = ak.option_sse_underlying_spot_price_sina(symbol=underlying_spot)
        underlying_info: dict[str, Any] = {"code": underlying_code, "symbol": underlying_spot, "name": symbol}
        if underlying_df is not None and not underlying_df.empty and "字段" in underlying_df.columns:
            data = dict(zip(underlying_df["字段"], underlying_df["值"]))
            underlying_info.update(
                {
                    "price": parse_numeric(data.get("最近成交价")),
                    "open": parse_numeric(data.get("今日开盘价")),
                    "preClose": parse_numeric(data.get("昨日收盘价")),
                    "high": parse_numeric(data.get("最高成交价")),
                    "low": parse_numeric(data.get("最低成交价")),
                    "time": str(data.get("行情时间", "")),
                    "date": str(data.get("行情日期", "")),
                }
            )

        return ok(
            {
                "underlying": underlying_info,
                "expiryMonths": months,
                "selectedExpiry": valid_months,
                "options": options,
                "truncated": truncated,
            }
        )
    except Exception as e:
        return fail(e)


def register(mcp):
    mcp.tool()(get_option_chain)
