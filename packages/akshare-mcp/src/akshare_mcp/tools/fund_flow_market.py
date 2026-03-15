"""
fund_flow_market.py
Dragon-tiger board, margin trading, and block trades functions.
"""

from datetime import datetime, timedelta
from typing import Any, Optional

import akshare as ak
import requests

from ..utils import fail, normalize_code, ok, parse_numeric, safe_float
from ..core.rate_limiter import get_limiter
from ..date_utils import get_latest_trading_date, format_date_dash

from .fund_flow_common import _fetch_eastmoney_datacenter


# =====================
# Dragon-tiger board
# =====================

def get_dragon_tiger(date: str = "", stock_code: str = "") -> dict:
    """
    获取龙虎榜数据

    Args:
        date: 日期，格式 YYYY-MM-DD，默认为最近交易日
        stock_code: 指定股票代码，不传则返回当日所有
    """
    try:
        date = (date or "").strip()
        if not date:
            date = get_latest_trading_date()
        else:
            date = date.replace("-", "")

        date_dash = format_date_dash(date)

        results: list[dict] = []
        df = None
        source = "unknown"

        # 1. Try Sina first
        try:
            df = ak.stock_lhb_detail_daily_sina(date=date_dash)
            if df is not None and not df.empty:
                source = "sina"
        except Exception:
            pass

        # 2. Fallback to EastMoney
        if df is None or df.empty:
            try:
                df = ak.stock_lhb_detail_em(start_date=date, end_date=date)
                if df is not None and not df.empty:
                    source = "eastmoney"
            except Exception:
                pass

        if df is None or df.empty:
            return fail(f"未获取到 {date} 龙虎榜数据 (尝试源: Sina, EastMoney)")

        target_code = normalize_code(stock_code) if stock_code else ""

        for _, row in df.iterrows():
            try:
                if source == "sina":
                    code_val = row.get("股票代码")
                    name = str(row.get("股票名称", ""))
                    close = safe_float(row.get("收盘价"))
                    change = safe_float(row.get("对应值"))
                    reason = str(row.get("指标", ""))
                    if reason.lower() == "nan":
                        reason = ""
                    buy = None
                    sell = None
                    net = None
                else:
                    code_val = row.get("代码")
                    name = str(row.get("名称", ""))
                    close = safe_float(row.get("收盘价"))
                    change = safe_float(row.get("涨跌幅"))
                    reason = str(row.get("上榜原因", ""))
                    if reason.lower() == "nan":
                        reason = ""
                    buy = safe_float(row.get("买入额"))
                    sell = safe_float(row.get("卖出额"))
                    net = safe_float(row.get("净买额"))

                if code_val is None:
                    continue
                code = normalize_code(str(code_val))
                if target_code and code != target_code:
                    continue

                results.append(
                    {
                        "code": code,
                        "name": name,
                        "closePrice": close,
                        "changePercent": change,
                        "reason": reason,
                        "buyAmount": buy if buy is not None else 0.0,
                        "sellAmount": sell if sell is not None else 0.0,
                        "netAmount": net if net is not None else 0.0,
                        "source": source,
                    }
                )
            except Exception:
                continue

        return ok(results)
    except Exception as e:
        return fail(e)


# =====================
# Margin data
# =====================

def get_margin_data(stock_code: str = "", days: int = 30) -> dict:
    """获取融资融券明细数据（支持单只股票或市场摘要）"""
    try:
        limiter = get_limiter("fund_flow", max_calls=3, period=1.0)
        limiter.acquire()

        days = int(days) if int(days or 0) > 0 else 30
        params: dict[str, Any] = {
            "sortColumns": "DATE",
            "sortTypes": -1,
            "pageSize": min(max(days, 1), 200),
            "pageNumber": 1,
            "reportName": "RPTA_WEB_RZRQ_GGMX",
            "columns": "DATE,SCODE,SECNAME,RZYE,RZMRE,RZCHE,RQYE,RQMCL,RQCHL,RZRQYE",
        }

        if stock_code:
            code = normalize_code(stock_code)
            params["filter"] = f'(SCODE="{code}")'

        items = _fetch_eastmoney_datacenter(params)
        results: list[dict] = []
        for item in items:
            results.append(
                {
                    "date": str(item.get("DATE", "")).split(" ")[0],
                    "code": normalize_code(item.get("SCODE") or stock_code),
                    "name": str(item.get("SECNAME") or ""),
                    "marginBalance": parse_numeric(item.get("RZYE")),
                    "marginBuy": parse_numeric(item.get("RZMRE")),
                    "marginRepay": parse_numeric(item.get("RZCHE")),
                    "shortBalance": parse_numeric(item.get("RQYE")),
                    "shortSell": parse_numeric(item.get("RQMCL")),
                    "shortRepay": parse_numeric(item.get("RQCHL")),
                    "totalBalance": parse_numeric(item.get("RZRQYE")),
                }
            )

        if results:
            return ok(results)

        # Fallback: market-level summary
        def scale_margin(val: Any) -> Optional[float]:
            num = parse_numeric(val)
            return num * 1e8 if num is not None else None

        df = ak.stock_margin_account_info()
        if df is not None and not df.empty:
            row = df.iloc[-1]
            summary = {
                "date": str(row.get("日期", "")),
                "code": normalize_code(stock_code) if stock_code else "",
                "name": "",
                "marginBalance": scale_margin(row.get("融资余额")),
                "marginBuy": scale_margin(row.get("融资买入额")),
                "marginRepay": None,
                "shortBalance": scale_margin(row.get("融券余额")),
                "shortSell": scale_margin(row.get("融券卖出额")),
                "shortRepay": None,
                "totalBalance": None,
            }
            return ok([summary])

        df = ak.stock_margin_sse(
            start_date="20010106",
            end_date=datetime.now().strftime("%Y%m%d"),
        )
        if df is None or df.empty:
            return fail("未获取到融资融券数据")

        row = df.iloc[-1]
        summary = {
            "date": str(row.get("信用交易日期", "")),
            "code": normalize_code(stock_code) if stock_code else "",
            "name": "",
            "marginBalance": safe_float(row.get("融资余额")),
            "marginBuy": safe_float(row.get("融资买入额")),
            "marginRepay": safe_float(row.get("融资偿还额")),
            "shortBalance": safe_float(row.get("融券余量")),
            "shortSell": safe_float(row.get("融券卖出量")),
            "shortRepay": safe_float(row.get("融券偿还量")),
            "totalBalance": None,
        }
        return ok([summary])
    except Exception as e:
        return fail(e)


def get_margin_ranking(top_n: int = 20, sort_by: str = "balance") -> dict:
    """获取融资融券排行"""
    try:
        limiter = get_limiter("fund_flow", max_calls=3, period=1.0)
        limiter.acquire()

        top_n = int(top_n) if int(top_n or 0) > 0 else 20
        sort_map = {"balance": "RZRQYE", "buy": "RZMRE", "sell": "RQMCL"}
        sort_column = sort_map.get(sort_by, "RZRQYE")

        latest = _fetch_eastmoney_datacenter(
            {
                "sortColumns": "DATE",
                "sortTypes": -1,
                "pageSize": 1,
                "pageNumber": 1,
                "reportName": "RPTA_WEB_RZRQ_GGMX",
                "columns": "DATE",
            }
        )
        if not latest:
            return ok([])
        latest_date = latest[0].get("DATE")
        if not latest_date:
            return ok([])

        items = _fetch_eastmoney_datacenter(
            {
                "sortColumns": sort_column,
                "sortTypes": -1,
                "pageSize": top_n,
                "pageNumber": 1,
                "reportName": "RPTA_WEB_RZRQ_GGMX",
                "columns": "DATE,SCODE,SECNAME,RZYE,RZMRE,RQMCL,RZRQYE",
                "filter": f"(DATE='{latest_date}')",
            }
        )
        results = []
        for item in items:
            results.append(
                {
                    "date": str(item.get("DATE", "")).split(" ")[0],
                    "code": normalize_code(item.get("SCODE")),
                    "name": str(item.get("SECNAME") or ""),
                    "marginBalance": parse_numeric(item.get("RZYE")),
                    "marginBuy": parse_numeric(item.get("RZMRE")),
                    "shortSell": parse_numeric(item.get("RQMCL")),
                    "totalBalance": parse_numeric(item.get("RZRQYE")),
                }
            )
        return ok(results)
    except Exception as e:
        return fail(e)


# =====================
# Block trades
# =====================

def get_block_trades(date: str = "", stock_code: str = "", limit: int = 500) -> dict:
    """获取大宗交易数据"""
    try:
        limiter = get_limiter("fund_flow", max_calls=3, period=1.0)
        limiter.acquire()

        target = date or datetime.now().strftime("%Y-%m-%d")
        code = normalize_code(stock_code) if stock_code else ""

        def _fetch_for_trade_date(trade_date: str) -> list[dict]:
            params: dict[str, Any] = {
                "sortColumns": "SECURITY_CODE",
                "sortTypes": "1",
                "pageSize": min(max(int(limit), 1), 1000),
                "pageNumber": 1,
                "reportName": "RPT_DATA_BLOCKTRADE",
                "columns": (
                    "TRADE_DATE,SECURITY_CODE,SECUCODE,SECURITY_NAME_ABBR,CHANGE_RATE,"
                    "CLOSE_PRICE,DEAL_PRICE,PREMIUM_RATIO,DEAL_VOLUME,DEAL_AMT,TURNOVER_RATE,"
                    "BUYER_NAME,SELLER_NAME,CHANGE_RATE_1DAYS,CHANGE_RATE_5DAYS,"
                    "CHANGE_RATE_10DAYS,CHANGE_RATE_20DAYS,BUYER_CODE,SELLER_CODE"
                ),
                "source": "WEB",
                "client": "WEB",
                "filter": f"(SECURITY_TYPE_WEB=1)(TRADE_DATE>='{trade_date}')(TRADE_DATE<='{trade_date}')",
            }
            if code:
                params["filter"] += f'(SECURITY_CODE="{code}")'
            return _fetch_eastmoney_datacenter(params)

        items = _fetch_for_trade_date(target)
        if code and not date and not items:
            for offset in range(1, 31):
                fallback_date = (datetime.now() - timedelta(days=offset)).strftime("%Y-%m-%d")
                items = _fetch_for_trade_date(fallback_date)
                if items:
                    break
        results = []
        for item in items:
            results.append(
                {
                    "date": str(item.get("TRADE_DATE", "")).split(" ")[0],
                    "code": normalize_code(item.get("SECURITY_CODE")),
                    "name": str(item.get("SECURITY_NAME_ABBR") or ""),
                    "price": parse_numeric(item.get("DEAL_PRICE")) or 0,
                    "volume": parse_numeric(item.get("DEAL_VOLUME")) or 0,
                    "amount": parse_numeric(item.get("DEAL_AMT")) or 0,
                    "premium": parse_numeric(item.get("PREMIUM_RATIO")) or 0,
                    "buyer": str(item.get("BUYER_NAME") or ""),
                    "seller": str(item.get("SELLER_NAME") or ""),
                }
            )
        return ok(results)
    except Exception as e:
        return fail(e)
