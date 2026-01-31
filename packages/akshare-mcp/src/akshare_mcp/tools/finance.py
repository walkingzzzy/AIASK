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
from ..data_source import data_source

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


def _get_financials_tushare(code: str) -> Optional[dict]:
    pro = data_source.get_tushare_pro()
    if not pro:
        return None

    ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=550)).strftime("%Y%m%d")

    try:
        indicator_df = pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=end_date)
    except Exception as e:
        print(f"[Finance] Tushare fina_indicator failed: {e}", file=sys.stderr)
        indicator_df = None

    try:
        income_df = pro.income(ts_code=ts_code, start_date=start_date, end_date=end_date)
    except Exception as e:
        print(f"[Finance] Tushare income failed: {e}", file=sys.stderr)
        income_df = None

    if (indicator_df is None or indicator_df.empty) and (income_df is None or income_df.empty):
        return None

    indicator_row = None
    if indicator_df is not None and not indicator_df.empty:
        indicator_df = indicator_df.sort_values("end_date")
        indicator_row = indicator_df.iloc[-1]

    income_row = None
    if income_df is not None and not income_df.empty:
        income_df = income_df.sort_values("end_date")
        income_row = income_df.iloc[-1]

    report_date = None
    if indicator_row is not None and indicator_row.get("end_date"):
        report_date = str(indicator_row.get("end_date"))
    elif income_row is not None and income_row.get("end_date"):
        report_date = str(income_row.get("end_date"))

    # 获取ROA，如果为空则尝试计算
    roa_value = parse_numeric(indicator_row.get("roa")) if indicator_row is not None else None
    
    # 如果ROA为空，尝试用净利润/总资产计算
    if roa_value is None and income_row is not None:
        try:
            balance_df = pro.balancesheet(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if balance_df is not None and not balance_df.empty:
                balance_df = balance_df.sort_values("end_date")
                balance_row = balance_df.iloc[-1]
                total_assets = parse_numeric(balance_row.get("total_assets"))
                net_profit = parse_numeric(income_row.get("n_income"))
                
                if total_assets and net_profit and total_assets > 0:
                    roa_value = (net_profit / total_assets) * 100
                    print(f"[Finance] Calculated ROA for {code}: {roa_value:.2f}%", file=sys.stderr)
        except Exception as e:
            print(f"[Finance] ROA calculation failed: {e}", file=sys.stderr)

    return {
        "code": code,
        "reportDate": report_date,
        "revenue": parse_numeric(income_row.get("total_revenue")) if income_row is not None else None,
        "netProfit": parse_numeric(income_row.get("n_income")) if income_row is not None else None,
        "grossProfitMargin": parse_numeric(indicator_row.get("grossprofit_margin")) if indicator_row is not None else None,
        "netProfitMargin": parse_numeric(indicator_row.get("netprofit_margin")) if indicator_row is not None else None,
        "roe": parse_numeric(indicator_row.get("roe")) if indicator_row is not None else None,
        "roa": roa_value,
        "debtRatio": parse_numeric(indicator_row.get("debt_to_assets")) if indicator_row is not None else None,
        "currentRatio": parse_numeric(indicator_row.get("current_ratio")) if indicator_row is not None else None,
        "eps": parse_numeric(indicator_row.get("eps")) if indicator_row is not None else None,
        "bvps": None,
        "source": "tushare_pro",
    }

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
    # 1. Try Tushare Pro (custom/official) - 优先使用
    # 2. Try AkShare THS (Most recent) - 降级
    # 3. Try AkShare EM (Standard) - 降级
    # 4. Fallback to Baostock (Stable/Offline-like) - 最后降级
    
    res = None
     
    # 1. Try Tushare Pro (优先，如果成功则直接返回)
    try:
        res = _get_financials_tushare(code)
        if res:
            # Tushare Pro成功，直接缓存并返回
            cache.set(f"financials_{code}", res)
            return ok(res)
    except Exception as e:
        print(f"Tushare financial fetch failed for {code}: {e}", file=sys.stderr)

    # 2 & 3. Try AkShare (降级)
    if not res:
        try:
            res = _get_financials_akshare(code)
        except Exception as e:
            print(f"AkShare financial fetch failed for {code}: {e}", file=sys.stderr)

    # 4. Fallback to Baostock
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
        
        # 尝试多个可能的ROA字段名
        roa = (
            parse_numeric(row.get("总资产收益率")) or
            parse_numeric(row.get("总资产报酬率")) or
            parse_numeric(row.get("ROA")) or
            parse_numeric(row.get("资产收益率")) or
            parse_numeric(row.get("总资产净利率"))
        )
        
        return {
            "code": code,
            "reportDate": report_date,
            "eps": parse_numeric(row.get("基本每股收益")),
            "bvps": parse_numeric(row.get("每股净资产")),
            "roe": parse_numeric(row.get("净资产收益率")) or parse_numeric(row.get("净资产收益率-摊薄")),
            "roa": roa,
            "grossProfitMargin": parse_numeric(row.get("销售毛利率")),
            "netProfitMargin": parse_numeric(row.get("销售净利率")),
            "debtRatio": parse_numeric(row.get("资产负债率")),
            "currentRatio": parse_numeric(row.get("流动比率")),
            "source": "akshare_ths"
        }
    except Exception as e:
        print(f"[Finance] AkShare THS failed: {e}", file=sys.stderr)
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

    # 尝试多个可能的ROA指标名称
    roa = (
        pick_metric("总资产收益率") or
        pick_metric("总资产报酬率") or
        pick_metric("总资产净利率") or
        pick_metric("资产收益率")
    )

    return {
        "code": code,
        "reportDate": str(latest_col),
        "eps": pick_metric("基本每股收益"),
        "bvps": pick_metric("每股净资产"),
        "roe": pick_metric("净资产收益率"),
        "roa": roa,
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

        # 1. Try Tushare Pro
        try:
            pro = data_source.get_tushare_pro()
            if pro:
                ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
                df = pro.stock_basic(
                    ts_code=ts_code,
                    list_status="L",
                    fields="ts_code,symbol,name,market,industry,list_date",
                )
        except Exception:
            df = None

        if df is not None and not df.empty:
            row = df.iloc[0]
            return ok(
                {
                    "code": code,
                    "name": str(row.get("name") or ""),
                    "industry": str(row.get("industry") or ""),
                    "listDate": str(row.get("list_date") or ""),
                    "totalShares": "",
                    "floatShares": "",
                    "totalMarketCap": "",
                    "floatMarketCap": "",
                    "raw": {k: str(row.get(k, "")) for k in df.columns},
                }
            )

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
