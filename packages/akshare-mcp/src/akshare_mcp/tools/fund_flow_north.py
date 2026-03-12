"""
fund_flow_north.py
North-bound fund data: Tushare / HKEX / AKShare / EM-summary sources,
plus the public ``get_north_fund``, ``get_north_fund_holding``,
and ``get_north_fund_top`` functions.
"""

import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from typing import Any, Optional

import akshare as ak
import pandas as pd
import requests

from ..utils import fail, normalize_code, ok, parse_numeric, safe_float
from ..data_source import data_source
from ..core.cache_manager import cached
from ..core.rate_limiter import get_limiter
from ..date_utils import get_latest_trading_date

from .fund_flow_common import (
    _NORTH_FUND_STALE_DAYS,
    _NORTH_FUND_DAILY_QUOTA,
    _NORTH_FUND_FAST_MODE,
    _HKEX_DAILY_STAT_URL,
    _fetch_eastmoney_datacenter,
    logger,
)


# =====================
# Internal helpers
# =====================

def _parse_date(value: Any) -> Optional[date]:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (date, datetime)):
        return value if isinstance(value, date) else value.date()
    s = str(value).strip()
    if not s:
        return None
    s = s[:10]
    try:
        if "-" in s:
            return datetime.strptime(s, "%Y-%m-%d").date()
        if len(s) >= 8:
            return datetime.strptime(s[:8], "%Y%m%d").date()
    except ValueError:
        return None
    return None


def _format_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _north_fund_is_valid(results: list[dict], stale_days: int) -> bool:
    if not results:
        return False
    has_flow = any(
        (r.get("shConnect") not in (None, 0))
        or (r.get("szConnect") not in (None, 0))
        or (r.get("total") not in (None, 0))
        for r in results
    )
    if not has_flow:
        return False
    latest = max((_parse_date(r.get("date")) for r in results), default=None)
    if latest is None:
        return False
    if stale_days > 0:
        if (date.today() - latest).days > stale_days:
            return False
    return True


def _north_fund_has_flow(results: list[dict]) -> bool:
    if not results:
        return False
    return any(
        (r.get("shConnect") not in (None, 0))
        or (r.get("szConnect") not in (None, 0))
        or (r.get("total") not in (None, 0))
        for r in results
    )


def _tushare_pick_multiplier(
    totals: list[float], quota: float, tolerance: float
) -> Optional[float]:
    if not totals:
        return None
    totals_sorted = sorted(abs(val) for val in totals if val is not None)
    if not totals_sorted:
        return None
    median_total = totals_sorted[len(totals_sorted) // 2]
    if median_total <= 0:
        return None

    min_flow = float(os.getenv("NORTH_FUND_MIN_FLOW", "5e7"))
    max_flow = quota + tolerance
    candidates = (1e6, 1e4, 1e8)
    for mult in candidates:
        scaled = median_total * mult
        if min_flow <= scaled <= max_flow:
            return mult
    for mult in candidates:
        if median_total * mult <= max_flow:
            return mult
    return None


def _normalize_north_fund_results(rows: list[dict], days: int) -> list[dict]:
    seen: set[str] = set()
    normalized: list[dict] = []
    for r in rows:
        d = _parse_date(r.get("date"))
        if d is None:
            continue
        key = _format_date(d)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "date": key,
                "shConnect": r.get("shConnect"),
                "szConnect": r.get("szConnect"),
                "total": r.get("total"),
                "shCumulative": r.get("shCumulative"),
                "szCumulative": r.get("szCumulative"),
                "cumulative": r.get("cumulative"),
            }
        )
    normalized.sort(key=lambda x: x["date"])

    has_any_cumulative = any(r.get("cumulative") is not None for r in normalized)
    if not has_any_cumulative and normalized:
        sh_sum = 0.0
        sz_sum = 0.0
        for r in normalized:
            sh_val = r.get("shConnect") or 0.0
            sz_val = r.get("szConnect") or 0.0
            sh_sum += sh_val
            sz_sum += sz_val
            r["shCumulative"] = sh_sum
            r["szCumulative"] = sz_sum
            r["cumulative"] = sh_sum + sz_sum

    return normalized[-days:] if days > 0 else normalized


def _get_anchor_date() -> date:
    try:
        s = get_latest_trading_date()
        return datetime.strptime(s, "%Y%m%d").date()
    except Exception:
        pass
    return date.today()


# =====================
# Data source: Tushare
# =====================

def _north_fund_from_tushare(days: int) -> list[dict]:
    try:
        pro = data_source.get_tushare_pro()
        if not pro:
            return []
        anchor = _get_anchor_date()
        end_date = anchor.strftime("%Y%m%d")
        start_date = (anchor - timedelta(days=days * 3)).strftime("%Y%m%d")
        df = pro.moneyflow_hsgt(start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return []

        quota = _NORTH_FUND_DAILY_QUOTA
        tolerance = quota * 0.05
        totals: list[float] = []
        for _, row in df.iterrows():
            sh_raw = parse_numeric(row.get("hgt"))
            sz_raw = parse_numeric(row.get("sgt"))
            if sh_raw is None or sz_raw is None:
                continue
            totals.append(abs(sh_raw) + abs(sz_raw))
        multiplier = _tushare_pick_multiplier(totals, quota, tolerance)
        if multiplier is None:
            return []

        results: list[dict] = []
        for _, row in df.iterrows():
            trade_date = row.get("trade_date") or row.get("date")
            d = _parse_date(trade_date)
            if d is None:
                continue
            sh = parse_numeric(row.get("hgt"))
            sz = parse_numeric(row.get("sgt"))
            if sh is None or sz is None:
                continue
            sh_val = sh * multiplier
            sz_val = sz * multiplier
            if (
                abs(sh_val) > quota + tolerance
                or abs(sz_val) > quota + tolerance
            ):
                continue
            results.append(
                {
                    "date": _format_date(d),
                    "shConnect": sh_val,
                    "szConnect": sz_val,
                    "total": sh_val + sz_val,
                    "shCumulative": None,
                    "szCumulative": None,
                    "cumulative": None,
                }
            )
        return _normalize_north_fund_results(results, days)
    except Exception:
        return []


# =====================
# Data source: HKEX
# =====================

def _hkex_schema_index(schema_row: list[Any], candidates: tuple[str, ...]) -> Optional[int]:
    for idx, raw in enumerate(schema_row):
        label = str(raw or "").strip().lower()
        if not label:
            continue
        for cand in candidates:
            if cand in label:
                return idx
    return None


def _hkex_extract_table_value(table: dict, idx: Optional[int]) -> Any:
    if idx is None:
        return None
    tr = table.get("tr", [])
    if not isinstance(tr, list) or idx >= len(tr):
        return None
    try:
        return tr[idx].get("td", [[None]])[0][0]
    except Exception:
        return None


def _hkex_is_sentinel_value(raw: Any) -> bool:
    s = str(raw or "").strip()
    if not s:
        return True
    lower = s.lower()
    if lower in {"-", "--", "na", "n/a", "none"}:
        return True
    s = s.replace(",", "")
    return re.fullmatch(r"9{6,}", s) is not None


def _hkex_parse_dqb(raw: Any) -> Optional[float]:
    if _hkex_is_sentinel_value(raw):
        return None
    val = parse_numeric(raw)
    if val is None or val < 0:
        return None
    if val < 1e7:
        val *= 1e6
    if val > _NORTH_FUND_DAILY_QUOTA * 1.05:
        return None
    return val


def _north_fund_from_hkex(days: int) -> list[dict]:
    results: list[dict] = []
    max_lookback = max(days * 3, 10)
    quota = _NORTH_FUND_DAILY_QUOTA
    tolerance = quota * 0.05
    anchor = _get_anchor_date()
    for i in range(max_lookback):
        day = anchor - timedelta(days=i)
        url = _HKEX_DAILY_STAT_URL.format(date=day.strftime("%Y%m%d"))
        try:
            resp = requests.get(url, timeout=6)
            if resp.status_code != 200 or "tabData" not in resp.text:
                continue
            payload = resp.text.strip()
            if payload.startswith("tabData ="):
                payload = payload[len("tabData ="):].strip()
            if payload.endswith(";"):
                payload = payload[:-1]
            data = json.loads(payload)
        except Exception:
            continue

        sh_dqb = None
        sz_dqb = None
        for item in data:
            market = item.get("market")
            if market not in ("SSE Northbound", "SZSE Northbound"):
                continue
            if not item.get("tradingDay"):
                continue
            table = item.get("content", [{}])[0].get("table", {})
            schema = table.get("schema", [])
            if not schema or not isinstance(schema, list) or not schema[0]:
                continue
            schema_row = schema[0]
            if not isinstance(schema_row, list):
                continue
            dqb_idx = _hkex_schema_index(schema_row, ("dqb", "daily quota balance"))
            if dqb_idx is None:
                continue
            raw_dqb = _hkex_extract_table_value(table, dqb_idx)
            dqb_val = _hkex_parse_dqb(raw_dqb)
            if dqb_val is None:
                continue
            turnover_idx = _hkex_schema_index(schema_row, ("total turnover",))
            trade_idx = _hkex_schema_index(schema_row, ("total trade count", "trade count"))
            if turnover_idx is not None:
                turnover = parse_numeric(_hkex_extract_table_value(table, turnover_idx))
                if turnover is None or turnover < 0:
                    continue
            if trade_idx is not None:
                trade_count = parse_numeric(_hkex_extract_table_value(table, trade_idx))
                if trade_count is None or trade_count < 0:
                    continue
            if market == "SSE Northbound":
                sh_dqb = dqb_val
            else:
                sz_dqb = dqb_val

        if sh_dqb is None or sz_dqb is None:
            continue

        sh_net = quota - sh_dqb
        sz_net = quota - sz_dqb
        if (
            sh_net < -tolerance
            or sz_net < -tolerance
            or sh_net > quota + tolerance
            or sz_net > quota + tolerance
        ):
            continue

        results.append(
            {
                "date": _format_date(day),
                "shConnect": sh_net,
                "szConnect": sz_net,
                "total": sh_net + sz_net,
                "shCumulative": None,
                "szCumulative": None,
                "cumulative": None,
            }
        )
        if len(results) >= days:
            break

    return _normalize_north_fund_results(results, days)


# =====================
# Data source: AKShare EM
# =====================

def _north_fund_from_akshare(days: int) -> list[dict]:
    def normalize_date(val: Any) -> str:
        s = str(val or "").strip()
        if not s:
            return ""
        s = s[:10]
        if "-" not in s and len(s) == 8:
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return s

    def extract_net(row: pd.Series) -> Optional[float]:
        net = parse_numeric(row.get("当日成交净买额"))
        if net is None:
            net = parse_numeric(row.get("当日资金流入"))
        if net is None:
            buy = parse_numeric(row.get("买入成交额"))
            sell = parse_numeric(row.get("卖出成交额"))
            if buy is not None and sell is not None:
                net = buy - sell
        return net

    try:
        import signal

        def timeout_handler(signum, frame):
            raise TimeoutError("AKShare north-fund request timeout")

        if sys.platform != "win32":
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(30)

        try:
            sh_df = ak.stock_hsgt_hist_em(symbol="沪股通")
            sz_df = ak.stock_hsgt_hist_em(symbol="深股通")
        finally:
            if sys.platform != "win32":
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

        if sh_df is None or sh_df.empty or sz_df is None or sz_df.empty:
            return []

        sh_map: dict[str, dict[str, Optional[float]]] = {}
        for _, row in sh_df.iterrows():
            date_str = normalize_date(row.get("日期", ""))
            if not date_str:
                continue
            net = parse_numeric(extract_net(row))
            if net is None:
                continue
            cum = parse_numeric(row.get("历史累计净买额"))
            sh_map[date_str] = {"net": net * 1e8, "cumulative": cum * 1e8 if cum is not None else None}

        sz_map: dict[str, dict[str, Optional[float]]] = {}
        for _, row in sz_df.iterrows():
            date_str = normalize_date(row.get("日期", ""))
            if not date_str:
                continue
            net = parse_numeric(extract_net(row))
            if net is None:
                continue
            cum = parse_numeric(row.get("历史累计净买额"))
            sz_map[date_str] = {"net": net * 1e8, "cumulative": cum * 1e8 if cum is not None else None}

        common_dates = sorted(set(sh_map.keys()) & set(sz_map.keys()), reverse=True)
        if not common_dates:
            return []

        selected = sorted(common_dates[: min(days, len(common_dates))])
        results: list[dict] = []
        for d in selected:
            sh = sh_map[d]
            sz = sz_map[d]
            cumulative = None
            if sh.get("cumulative") is not None and sz.get("cumulative") is not None:
                cumulative = sh["cumulative"] + sz["cumulative"]
            results.append(
                {
                    "date": d,
                    "shConnect": sh["net"],
                    "szConnect": sz["net"],
                    "total": sh["net"] + sz["net"],
                    "shCumulative": sh.get("cumulative"),
                    "szCumulative": sz.get("cumulative"),
                    "cumulative": cumulative,
                }
            )

        return _normalize_north_fund_results(results, days)
    except TimeoutError:
        print("[akshare-mcp] _north_fund_from_akshare timeout", file=sys.stderr)
        return []
    except Exception as e:
        print(f"[akshare-mcp] _north_fund_from_akshare error: {e}", file=sys.stderr)
        return []


# =====================
# Data source: EM summary
# =====================

def _north_fund_from_em_summary(days: int) -> list[dict]:
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
    except Exception:
        return []
    if df is None or df.empty:
        return []

    summary: dict[str, dict[str, Optional[float]]] = {}
    for _, row in df.iterrows():
        date_str = _format_date(_parse_date(row.get("交易日")) or date.today())
        board = str(row.get("板块") or "").strip()
        direction = str(row.get("资金方向") or "").strip()
        if direction != "北向":
            continue
        net = parse_numeric(row.get("成交净买额")) or parse_numeric(row.get("资金净流入"))
        if net is None:
            continue
        if 0 < abs(net) < 1e6:
            logger.warning(
                "_north_fund_from_em_summary: value %.2f seems too small for yuan unit, "
                "possible upstream API unit change",
                net,
            )
        if date_str not in summary:
            summary[date_str] = {"sh": None, "sz": None}
        if board == "沪股通":
            summary[date_str]["sh"] = net
        elif board == "深股通":
            summary[date_str]["sz"] = net

    results: list[dict] = []
    for d, values in summary.items():
        sh = values.get("sh")
        sz = values.get("sz")
        if sh is None or sz is None:
            continue
        results.append(
            {
                "date": d,
                "shConnect": sh,
                "szConnect": sz,
                "total": sh + sz,
                "shCumulative": None,
                "szCumulative": None,
                "cumulative": None,
            }
        )

    results.sort(key=lambda x: x["date"])
    return results[-days:] if days > 0 else results


# =====================
# Public API functions
# =====================

@cached(ttl=300.0)
def get_north_fund(days: int = 30) -> dict:
    """
    获取北向资金数据（沪股通+深股通）

    Args:
        days: 获取最近多少天的数据，默认30天
    """
    limiter = get_limiter("fund_flow", max_calls=3, period=1.0)
    limiter.acquire()

    try:
        days = int(days)
        if days <= 0:
            return fail("days 必须为正整数")

        sources_status = []
        stale_candidates: list[tuple[str, list[dict]]] = []

        if _NORTH_FUND_FAST_MODE:
            source_chain = [
                ("akshare_em", _north_fund_from_akshare),
                ("em_summary", _north_fund_from_em_summary),
            ]
        else:
            source_chain = [
                ("tushare", _north_fund_from_tushare),
                ("hkex", _north_fund_from_hkex),
                ("akshare_em", _north_fund_from_akshare),
                ("em_summary", _north_fund_from_em_summary),
            ]

        for name, fetcher in source_chain:
            results = fetcher(days)
            if _north_fund_is_valid(results, _NORTH_FUND_STALE_DAYS):
                return ok({"items": results, "source": name})
            if _north_fund_has_flow(results):
                stale_candidates.append((name, results))
            sources_status.append(f"{name}: invalid/stale")

        if stale_candidates:
            def latest_date(rows: list[dict]) -> Optional[date]:
                return max((_parse_date(r.get("date")) for r in rows), default=None)

            best_source, best_rows = max(
                stale_candidates,
                key=lambda item: latest_date(item[1]) or date.min,
            )
            result = ok({"items": best_rows, "source": f"{best_source}_stale", "stale": True})
            result["_no_cache"] = True
            return result

        return fail(
            f"北向资金数据不可用: 所有数据源均失效或数据过期 ({'; '.join(sources_status)})"
        )
    except Exception as e:
        return fail(f"系统错误: {e}")


def get_north_fund_holding(stock_code: str) -> dict:
    """获取单只股票北向资金持股"""
    try:
        code = normalize_code(stock_code)
        items = _fetch_eastmoney_datacenter(
            {
                "sortColumns": "TRADE_DATE",
                "sortTypes": -1,
                "pageSize": 2,
                "pageNumber": 1,
                "reportName": "RPT_MUTUAL_HOLDSTOCKNORTH_STA",
                "columns": "TRADE_DATE,SECURITY_CODE,SECURITY_NAME,HOLD_SHARES,HOLD_MARKET_CAP,HOLD_SHARES_RATIO",
                "filter": f'(SECURITY_CODE="{code}")',
            }
        )
        if not items:
            return ok({"shares": 0, "ratio": 0, "change": 0})
        latest = items[0]
        prev = items[1] if len(items) > 1 else None
        latest_shares = parse_numeric(latest.get("HOLD_SHARES")) or 0
        prev_shares = parse_numeric(prev.get("HOLD_SHARES")) if prev else 0
        return ok(
            {
                "shares": latest_shares,
                "ratio": parse_numeric(latest.get("HOLD_SHARES_RATIO")) or 0,
                "change": latest_shares - (prev_shares or 0),
            }
        )
    except Exception as e:
        return fail(e)


def get_north_fund_top(top_n: int = 20) -> dict:
    """获取北向资金持股排行"""
    try:
        top_n = int(top_n) if int(top_n or 0) > 0 else 20
        items = _fetch_eastmoney_datacenter(
            {
                "sortColumns": "HOLD_MARKET_CAP",
                "sortTypes": -1,
                "pageSize": top_n,
                "pageNumber": 1,
                "reportName": "RPT_MUTUAL_HOLDSTOCKNORTH_STA",
                "columns": "SECURITY_CODE,SECURITY_NAME,HOLD_SHARES,HOLD_MARKET_CAP,HOLD_SHARES_RATIO",
            }
        )
        results = []
        for item in items:
            results.append(
                {
                    "code": normalize_code(item.get("SECURITY_CODE")),
                    "name": str(item.get("SECURITY_NAME") or ""),
                    "shares": parse_numeric(item.get("HOLD_SHARES")) or 0,
                    "ratio": parse_numeric(item.get("HOLD_SHARES_RATIO")) or 0,
                    "marketCap": parse_numeric(item.get("HOLD_MARKET_CAP")) or 0,
                }
            )
        return ok(results)
    except Exception as e:
        return fail(e)
