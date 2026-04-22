"""
fund_flow_market.py
Dragon-tiger board, margin trading, and block trades functions.
"""

from datetime import datetime, timedelta
from typing import Any, Optional

import akshare as ak
import requests

from ..utils import fail, normalize_code, ok, parse_date_input, parse_numeric, resolve_existing_security_code_sync, safe_float, validate_int_range
from ..core.rate_limiter import get_limiter
from ..date_utils import get_latest_trading_date, format_date_dash
from ..data_source import data_source
from ..storage import get_db
from .data_quality import build_quality_meta
from .market.helpers import get_name_map as _get_cached_name_map

from .fund_flow_common import _fetch_eastmoney_datacenter, _run_storage_call_sync


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
        requested_date = (date or "").strip().replace("-", "")
        if not requested_date:
            requested_date = get_latest_trading_date()

        candidate_dates = [requested_date]
        if not date:
            try:
                anchor = datetime.strptime(requested_date, "%Y%m%d")
                for offset in range(1, 6):
                    candidate_dates.append((anchor - timedelta(days=offset)).strftime("%Y%m%d"))
            except ValueError:
                pass

        resolved_date = requested_date
        results: list[dict] = []
        df = None
        source = "unknown"
        fallback_reasons: list[str] = []

        for candidate_date in candidate_dates:
            date_dash = format_date_dash(candidate_date)
            df = None
            source = "unknown"

            try:
                df = ak.stock_lhb_detail_daily_sina(date=date_dash)
                if df is not None and not df.empty:
                    source = "sina"
                    resolved_date = candidate_date
                    break
            except Exception as exc:
                fallback_reasons.append(f"sina:{candidate_date}:{exc}")

            try:
                df = ak.stock_lhb_detail_em(start_date=candidate_date, end_date=candidate_date)
                if df is not None and not df.empty:
                    source = "eastmoney"
                    resolved_date = candidate_date
                    break
            except Exception as exc:
                fallback_reasons.append(f"eastmoney:{candidate_date}:{exc}")

        if df is None or df.empty:
            response = fail(f"未获取到 {requested_date} 龙虎榜数据 (尝试源: Sina, EastMoney)")
            response.update(
                build_quality_meta(
                    source="none",
                    source_chain=["dragon_tiger.sina", "dragon_tiger.eastmoney"],
                    fallback_reason=fallback_reasons or f"未获取到 {requested_date} 龙虎榜数据",
                    asof_value=requested_date,
                    missing_fields=[],
                    degraded=True,
                    success=False,
                )
            )
            response["requested_date"] = requested_date
            return response

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

        response = ok(results)
        response.update(
            build_quality_meta(
                source=source,
                source_chain=[f"dragon_tiger.{source}"],
                fallback_reason=(
                    [f"resolved_date={resolved_date}"]
                    if resolved_date != requested_date
                    else (fallback_reasons or None)
                ),
                asof_value=resolved_date,
                missing_fields=[],
                degraded=resolved_date != requested_date,
                success=True,
                accepted_count=len(results),
                rejected_count=0,
            )
        )
        response["requested_date"] = requested_date
        response["resolved_date"] = resolved_date
        return response
    except Exception as e:
        response = fail(e)
        response.update(
            build_quality_meta(
                source="none",
                source_chain=["dragon_tiger"],
                fallback_reason=str(e),
                asof_value=(date or "").strip().replace("-", "") or None,
                missing_fields=[],
                degraded=True,
                success=False,
            )
        )
        return response


# =====================
# Margin data
# =====================


def _stock_ts_code(code: str) -> str:
    normalized = normalize_code(code)
    if normalized.startswith(("5", "6", "9")):
        return f"{normalized}.SH"
    return f"{normalized}.SZ"


def _margin_rows_from_db(stock_code: str = "", days: int = 30) -> list[dict]:
    try:
        db = get_db()
        limit = min(max(int(days or 30), 1), 200)
        code = normalize_code(stock_code) if stock_code else ""
        if code:
            rows = _run_storage_call_sync(
                lambda: db.get_margin_detail_latest(limit=limit, ts_code=_stock_ts_code(code)),
                timeout=20.0,
            )
            if not isinstance(rows, list) or not rows:
                return []
            name_map = _get_cached_name_map() or {}
            return [
                {
                    "date": str(row.get("trade_date") or ""),
                    "code": normalize_code(row.get("code") or code),
                    "name": str(name_map.get(normalize_code(row.get("code") or code), "")),
                    "marginBalance": parse_numeric(row.get("marginBalance")),
                    "marginBuy": parse_numeric(row.get("marginBuy")),
                    "marginRepay": parse_numeric(row.get("marginRepay")),
                    "shortBalance": parse_numeric(row.get("shortBalance")),
                    "shortSell": parse_numeric(row.get("shortSell")),
                    "shortRepay": parse_numeric(row.get("shortRepay")),
                    "totalBalance": parse_numeric(row.get("totalBalance")),
                    "source": row.get("source") or "margin_detail",
                }
                for row in rows
                if row.get("trade_date")
            ]

        rows = _run_storage_call_sync(
            lambda: db.get_margin_market_history(days=limit),
            timeout=20.0,
        )
        if not isinstance(rows, list) or not rows:
            return []
        return [
            {
                "date": str(row.get("trade_date") or ""),
                "code": "",
                "name": "",
                "marginBalance": parse_numeric(row.get("marginBalance")),
                "marginBuy": parse_numeric(row.get("marginBuy")),
                "marginRepay": parse_numeric(row.get("marginRepay")),
                "shortBalance": parse_numeric(row.get("shortBalance")),
                "shortSell": parse_numeric(row.get("shortSell")),
                "shortRepay": None,
                "totalBalance": parse_numeric(row.get("totalBalance")),
                "source": row.get("source") or "margin_market_flow",
            }
            for row in rows
            if row.get("trade_date")
        ]
    except Exception:
        return []


def _margin_ranking_from_db(top_n: int = 20, sort_by: str = "balance") -> list[dict]:
    try:
        db = get_db()
        rows = _run_storage_call_sync(
            lambda: db.get_margin_ranking(top_n=top_n, sort_by=sort_by),
            timeout=20.0,
        )
        if not isinstance(rows, list) or not rows:
            return []
        name_map = _get_cached_name_map() or {}
        return [
            {
                "date": str(row.get("trade_date") or ""),
                "code": normalize_code(row.get("code") or ""),
                "name": str(name_map.get(normalize_code(row.get("code") or ""), "")),
                "marginBalance": parse_numeric(row.get("marginBalance")),
                "marginBuy": parse_numeric(row.get("marginBuy")),
                "shortSell": parse_numeric(row.get("shortSell")),
                "totalBalance": parse_numeric(row.get("totalBalance")),
                "source": row.get("source") or "margin_detail_ranking",
            }
            for row in rows
            if row.get("trade_date")
        ]
    except Exception:
        return []

def get_margin_data(stock_code: str = "", days: int = 30) -> dict:
    """获取融资融券明细数据（支持单只股票或市场摘要）"""
    try:
        limiter = get_limiter("fund_flow", max_calls=3, period=1.0)
        limiter.acquire()

        days = int(days) if int(days or 0) > 0 else 30
        db_rows = _margin_rows_from_db(stock_code=stock_code, days=days)
        if db_rows:
            return ok(db_rows)
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

        top_n, top_n_error = validate_int_range(top_n, field_name="top_n", minimum=1)
        if top_n_error:
            return fail(top_n_error)
        db_rows = _margin_ranking_from_db(top_n=top_n, sort_by=sort_by)
        if db_rows:
            return ok(db_rows)
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

def _normalize_name_text(value: Any) -> str:
    return "".join(str(value or "").strip().upper().split())


def _get_security_meta_map(codes: set[str]) -> dict[str, dict[str, str]]:
    meta_map: dict[str, dict[str, str]] = {}
    if not codes:
        return meta_map

    try:
        name_map = _get_cached_name_map()
    except Exception:
        name_map = {}

    for code in codes:
        if code in name_map:
            meta_map[code] = {"name": str(name_map.get(code) or "").strip(), "industry": ""}

    if len(codes) > 50:
        return meta_map

    try:
        pro = data_source.get_tushare_pro()
    except Exception:
        pro = None

    if not pro:
        return meta_map

    for code in sorted(codes):
        ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
        try:
            df = pro.stock_basic(ts_code=ts_code, list_status="L", fields="ts_code,name,industry")
        except Exception:
            continue
        if df is None or df.empty:
            continue
        row = df.iloc[0]
        meta_map[code] = {
            "name": str(row.get("name") or meta_map.get(code, {}).get("name") or "").strip(),
            "industry": str(row.get("industry") or "").strip(),
        }
    return meta_map


def _finalize_block_trade_results(
    items: list[dict],
    *,
    source_chain: list[str],
    fallback_reason: list[str] | None = None,
) -> tuple[list[dict], dict]:
    results: list[dict] = []
    codes = {normalize_code(item.get("code")) for item in items if item.get("code")}
    security_meta = _get_security_meta_map(codes)

    name_backfilled = 0
    name_corrected = 0
    code_mismatch_count = 0
    industry_backfilled = 0
    missing_name_count = 0

    for item in items:
        code = normalize_code(item.get("code"))
        if not code:
            continue

        raw_name = str(item.get("name") or "").strip()
        alt_code = normalize_code(item.get("alt_code") or "")
        if alt_code and alt_code != code:
            code_mismatch_count += 1

        meta = security_meta.get(code, {})
        canonical_name = str(meta.get("name") or "").strip()
        canonical_industry = str(meta.get("industry") or "").strip()

        derived_fields: list[str] = []
        final_name = raw_name
        if canonical_name:
            if not raw_name:
                final_name = canonical_name
                name_backfilled += 1
                derived_fields.append("name")
            elif _normalize_name_text(raw_name) != _normalize_name_text(canonical_name):
                final_name = canonical_name
                name_corrected += 1
                derived_fields.append("name")
        if not final_name:
            missing_name_count += 1

        industry = str(item.get("industry") or "").strip()
        if not industry and canonical_industry:
            industry = canonical_industry
            industry_backfilled += 1
            derived_fields.append("industry")

        missing_fields = []
        if not final_name:
            missing_fields.append("name")
        if item.get("price") is None:
            missing_fields.append("price")
        if item.get("volume") is None:
            missing_fields.append("volume")
        if item.get("amount") is None:
            missing_fields.append("amount")

        results.append(
            {
                "date": item.get("date"),
                "code": code,
                "name": final_name,
                "industry": industry,
                "price": item.get("price"),
                "volume": item.get("volume"),
                "amount": item.get("amount"),
                "premium": item.get("premium"),
                "buyer": item.get("buyer"),
                "seller": item.get("seller"),
                "dataQuality": {
                    "source": "eastmoney_block_trade",
                    "derived_fields": derived_fields,
                    "missing_fields": missing_fields,
                },
            }
        )

    data_quality = {
        "count": len(results),
        "name_backfilled_count": name_backfilled,
        "name_corrected_count": name_corrected,
        "industry_backfilled_count": industry_backfilled,
        "missing_name_count": missing_name_count,
        "code_mismatch_count": code_mismatch_count,
        "fallback_used": len(source_chain) > 1,
        "source_chain": source_chain,
        "fallback_reason": [str(item).strip() for item in list(fallback_reason or []) if str(item).strip()],
    }
    return results, data_quality

def get_block_trades(date: str = "", stock_code: str = "", limit: int = 500) -> dict:
    """获取大宗交易数据"""
    try:
        limiter = get_limiter("fund_flow", max_calls=3, period=1.0)
        limiter.acquire()
        limit, limit_error = validate_int_range(limit, field_name="limit", minimum=1, maximum=1000)
        if limit_error:
            response = fail("limit 必须为正整数")
            response["source"] = "none"
            return response
        if date and parse_date_input(date) is None:
            response = fail(f"date 无效: {date}")
            response["source"] = "none"
            return response

        target = date or datetime.now().strftime("%Y-%m-%d")
        if stock_code:
            code, _, code_error = resolve_existing_security_code_sync(stock_code=stock_code)
            if code_error:
                response = fail(code_error)
                response["source"] = "none"
                return response
        else:
            code = ""
        source_chain = ["eastmoney.block_trades"]
        fallback_reason: list[str] = []

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
                    source_chain.append("eastmoney.block_trades.backtrack")
                    fallback_reason.append(f"no block trades on {target}, fallback to {fallback_date}")
                    break
        results = []
        for item in items:
            security_code = normalize_code(item.get("SECURITY_CODE"))
            secucode = normalize_code(str(item.get("SECUCODE", "")).split(".")[0] if item.get("SECUCODE") else "")
            normalized_code = security_code or secucode
            results.append(
                {
                    "date": str(item.get("TRADE_DATE", "")).split(" ")[0],
                    "code": normalized_code,
                    "alt_code": secucode,
                    "name": str(item.get("SECURITY_NAME_ABBR") or ""),
                    "price": parse_numeric(item.get("DEAL_PRICE")),
                    "volume": parse_numeric(item.get("DEAL_VOLUME")),
                    "amount": parse_numeric(item.get("DEAL_AMT")),
                    "premium": parse_numeric(item.get("PREMIUM_RATIO")),
                    "buyer": str(item.get("BUYER_NAME") or ""),
                    "seller": str(item.get("SELLER_NAME") or ""),
                }
            )
        finalized, data_quality = _finalize_block_trade_results(
            results,
            source_chain=source_chain,
            fallback_reason=fallback_reason,
        )
        response = ok(finalized)
        response["source"] = "eastmoney_block_trade"
        response["source_chain"] = source_chain
        if fallback_reason:
            response["fallback_reason"] = fallback_reason
        response["degraded"] = bool(data_quality.get("missing_name_count")) or bool(data_quality.get("code_mismatch_count"))
        response["data_quality"] = data_quality
        return response
    except Exception as e:
        return fail(e)
