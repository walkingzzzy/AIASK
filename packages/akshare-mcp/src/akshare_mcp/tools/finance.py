import os
import time

import akshare as ak

from ..utils import (
    fail,
    normalize_code,
    ok,
    parse_numeric,
)

# Import optimization modules
from ..core.cache_manager import cached
from ..core.rate_limiter import get_limiter


from typing import Optional, Callable, TypeVar
import sys
from datetime import datetime, timedelta
from ..baostock_api import baostock_client
from ..cache import cache
from ..date_utils import get_latest_trading_date

_RETRY_SLEEP_SECONDS = float(os.getenv("AKSHARE_RETRY_SLEEP_SECONDS", "0.5"))
_FINANCE_RETRY = int(os.getenv("AKSHARE_FINANCE_RETRY", "2"))

T = TypeVar("T")

def _call_with_retry(fn: Callable[[], T]) -> T:
    last_error: Optional[Exception] = None
    for _ in range(_FINANCE_RETRY):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if _RETRY_SLEEP_SECONDS > 0:
                time.sleep(_RETRY_SLEEP_SECONDS)
    if last_error:
        raise last_error
    raise RuntimeError("请求失败")

@cached(ttl=86400.0)  # 24h cache for financial data
def get_financials(stock_code: str) -> dict:
    """
    获取股票财务指标数据
    """
    # Rate limiting
    limiter = get_limiter("finance", max_calls=5, period=1.0)
    limiter.acquire()
    
    code = normalize_code(stock_code)
    
    # 0. Check Cache (TTL 24h)
    cached_data = cache.get(f"financials_{code}", ttl_seconds=86400)
    if cached_data:
        cached_data["cached"] = True
        return ok(cached_data)

    # Strategy:
    # 1. Try AkShare THS (Most recent)
    # 2. Try AkShare EM (Standard)
    # 3. Fallback to Baostock (Stable/Offline-like)
    
    res = None
     
    # 1 & 2. Try AkShare
    try:
        # Optimistic try
        res = _get_financials_akshare(code)
    except Exception as e:
        print(f"AkShare financial fetch failed for {code}: {e}", file=sys.stderr)

    # 3. Fallback to Baostock
    if not res:
        try:
            # Baostock generally works with Quarter/Year, so we get the latest available
            # But for "latest", we might need to guess the quarter.
            # Let's try previous quarter relative to now.
            now = datetime.now()
            # Simple logic: Check last 4 quarters
            for i in range(4):
                # approximate logic to go back quarters
                q_date = now - timedelta(days=90 * i)
                year = str(q_date.year)
                month = q_date.month
                quarter = "1" if month <= 3 else "2" if month <= 6 else "3" if month <= 9 else "4"
                
                # Fetch Balance Sheet (for BVPS/Debt) and Profit (for EPS/ROE)
                # This is expensive, so just trying once or twice might be enough.
                
                # Simplified: just try to get a valid result
                df_profit = baostock_client.get_profit_statement(code, year, quarter)
                if not df_profit.empty:
                    row = df_profit.iloc[0]
                    # Map Baostock fields to our schema
                    # pubDate, statDate, epsTTM, mbEPS, ...
                    res = {
                        "code": code,
                        "reportDate": f"{year}-Q{quarter}",
                        "eps": parse_numeric(row.get("epsTTM")), # or mbEPS
                        "roe": parse_numeric(row.get("roeAvg")),
                        "grossProfitMargin": parse_numeric(row.get("grossMargin")),
                        "netProfitMargin": parse_numeric(row.get("netProfitMargin")),
                        "source": "baostock"
                    }
                    if res: break
        except Exception as e:
            print(f"Baostock financial fetch failed for {code}: {e}", file=sys.stderr)

    if res:
        # Cache Result
        cache.set(f"financials_{code}", res)
        return ok(res)
    
    return fail(f"所有数据源均无法获取 {code} 的财务数据 (AkShare & Baostock)")

def _get_financials_akshare(code: str) -> Optional[dict]:
    try:
        df = _call_with_retry(lambda: ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期"))
        if df is None or df.empty:
            # Fallback to EM
            return _get_financials_akshare_em(code)

        row = df.iloc[-1]
        report_date = str(row.get("报告期", ""))
        return {
            "code": code,
            "reportDate": report_date,
            "eps": parse_numeric(row.get("基本每股收益")),
            "bvps": parse_numeric(row.get("每股净资产")),
            "roe": parse_numeric(row.get("净资产收益率")) or parse_numeric(row.get("净资产收益率-摊薄")),
            "roa": parse_numeric(row.get("总资产收益率")),
            "grossProfitMargin": parse_numeric(row.get("销售毛利率")),
            "netProfitMargin": parse_numeric(row.get("销售净利率")),
            "debtRatio": parse_numeric(row.get("资产负债率")),
            "currentRatio": parse_numeric(row.get("流动比率")),
            "source": "akshare_ths"
        }
    except Exception:
        return _get_financials_akshare_em(code)

def _get_financials_akshare_em(code: str) -> Optional[dict]:
    df = _call_with_retry(lambda: ak.stock_financial_abstract(symbol=code))
    if df is None or df.empty:
        return None

    date_cols = [c for c in df.columns if str(c).isdigit()]
    if not date_cols:
        return None
    latest_col = sorted(date_cols)[-1]

    def pick_metric(metric: str) -> Optional[float]:
        rows = df[df["指标"] == metric]
        if rows.empty:
            return None
        return parse_numeric(rows.iloc[0].get(latest_col))

    return {
        "code": code,
        "reportDate": str(latest_col),
        "eps": pick_metric("基本每股收益"),
        "bvps": pick_metric("每股净资产"),
        "roe": pick_metric("净资产收益率"),
        "roa": pick_metric("总资产收益率"),
        "grossProfitMargin": pick_metric("销售毛利率"),
        "netProfitMargin": pick_metric("销售净利率"),
        "debtRatio": pick_metric("资产负债率"),
        "currentRatio": pick_metric("流动比率"),
        "source": "akshare_em"
    }

@cached(ttl=86400.0)  # 24h cache for stock info
def get_stock_info(stock_code: str) -> dict:
    """
    获取股票基本信息

    Args:
        stock_code: 股票代码
    """
    # Rate limiting
    limiter = get_limiter("info", max_calls=5, period=1.0)
    limiter.acquire()
    
    try:
        code = normalize_code(stock_code)
        df = None
        try:
            df = _call_with_retry(lambda: ak.stock_individual_info_em(symbol=code))
        except Exception:
            df = None
        if df is None or df.empty:
            df = ak.stock_profile_cninfo(symbol=code)
            if df is None or df.empty:
                return fail(f"未找到股票 {code} 的信息")

        info: dict[str, str] = {}
        if "item" in df.columns and "value" in df.columns:
            for _, row in df.iterrows():
                key = str(row.get("item", "")).strip()
                value = row.get("value", "")
                if not key:
                    continue
                info[key] = str(value) if value is not None else ""
        else:
            row = df.iloc[0]
            info = {str(k): str(row.get(k, "")) for k in df.columns}

        return ok(
            {
                "code": code,
                "name": info.get("股票简称", info.get("A股简称", "")),
                "industry": info.get("行业", info.get("所属行业", "")),
                "listDate": info.get("上市时间", info.get("上市日期", "")),
                "totalShares": info.get("总股本", ""),
                "floatShares": info.get("流通股", ""),
                "totalMarketCap": info.get("总市值", ""),
                "floatMarketCap": info.get("流通市值", ""),
                "raw": info,
            }
        )
    except Exception as e:
        return fail(e)


def register(mcp):
    mcp.tool()(get_financials)
    mcp.tool()(get_stock_info)
