import json
import sys
import os
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Optional

import akshare as ak
import pandas as pd
import requests

from ..utils import (
    fail,
    format_date,
    normalize_code,
    ok,
    parse_numeric,
    pick_value,
    safe_float,
    parse_date_input,
)

# Import optimization modules
from ..core.cache_manager import cached
from ..core.rate_limiter import get_limiter

# =====================
# 北向资金 Helpers
# =====================

_NORTH_FUND_STALE_DAYS = int(os.getenv("NORTH_FUND_STALE_DAYS", "5"))
_NORTH_FUND_DAILY_QUOTA = float(os.getenv("NORTH_FUND_DAILY_QUOTA", "52000000000"))
_HKEX_DAILY_STAT_URL = os.getenv(
    "HKEX_DAILY_STAT_URL",
    "https://www.hkex.com.hk/eng/csm/DailyStat/data_tab_daily_{date}e.js",
)
_RETRY_SLEEP_SECONDS = float(os.getenv("AKSHARE_RETRY_SLEEP_SECONDS", "1.0"))


def _parse_date(value: Any) -> Optional[date]:
    # Local helper for north fund, similar to utils but slightly different handling if needed
    # Using utils.parse_date_input logic but adapting to north fund raw data which might be datetime/date objects or strings
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (date, datetime)):
        return value if isinstance(value, date) else value.date()
    # reuse utils logic if possible, but keep simple here
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
    return normalized[-days:] if days > 0 else normalized


def _get_anchor_date() -> date:
    try:
        s = get_latest_trading_date()
        return datetime.strptime(s, "%Y%m%d").date()
    except Exception:
        pass
    return date.today()


def _north_fund_from_tushare(days: int) -> list[dict]:
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        return []
    try:
        import tushare as ts  # type: ignore
    except Exception:
        return []
    try:
        pro = ts.pro_api(token)
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
                payload = payload[len("tabData =") :].strip()
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
        # 使用超时保护，防止 akshare 库调用卡住导致进程挂起
        import signal
        import sys
        
        def timeout_handler(signum, frame):
            raise TimeoutError("AKShare 北向资金请求超时")
        
        # 仅在 Unix 系统设置信号超时
        if sys.platform != 'win32':
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(30)  # 30秒超时
        
        try:
            sh_df = ak.stock_hsgt_hist_em(symbol="沪股通")
            sz_df = ak.stock_hsgt_hist_em(symbol="深股通")
        finally:
            if sys.platform != 'win32':
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


@cached(ttl=300.0)  # 5min cache for north fund data
def get_north_fund(days: int = 30) -> dict:
    """
    获取北向资金数据（沪股通+深股通）

    Args:
        days: 获取最近多少天的数据，默认30天
    """
    # Rate limiting
    limiter = get_limiter("fund_flow", max_calls=3, period=1.0)
    limiter.acquire()
    
    try:
        days = int(days)
        if days <= 0:
            return fail("days 必须为正整数")

        # 尝试多个数据源，按优先级排序
        sources_status = []

        # 1. Tushare (Token required)
        results = _north_fund_from_tushare(days)
        if _north_fund_is_valid(results, _NORTH_FUND_STALE_DAYS):
            return ok({"items": results, "source": "tushare"})
        sources_status.append("tushare: skipped/invalid")

        # 2. HKEX (Official source)
        results = _north_fund_from_hkex(days)
        if _north_fund_is_valid(results, _NORTH_FUND_STALE_DAYS):
            return ok({"items": results, "source": "hkex"})
        sources_status.append("hkex: invalid/stale")

        # 3. AkShare (EastMoney Hist)
        results = _north_fund_from_akshare(days)
        if _north_fund_is_valid(results, _NORTH_FUND_STALE_DAYS):
            return ok({"items": results, "source": "akshare_em"})
        sources_status.append("akshare: invalid/stale")

        # 4. EastMoney Summary (Realtime/Recent)
        results = _north_fund_from_em_summary(days)
        if _north_fund_is_valid(results, _NORTH_FUND_STALE_DAYS):
            return ok({"items": results, "source": "em_summary"})
        sources_status.append("em_summary: invalid/stale")

        return fail(f"北向资金数据不可用: 所有数据源均失效或数据过期 ({'; '.join(sources_status)})")
    except Exception as e:
        return fail(f"系统错误: {e}")


@cached(ttl=300.0)  # 5min cache for sector fund flow
def get_sector_fund_flow(top_n: int = 20) -> dict:
    """
    获取行业板块资金流向

    Args:
        top_n: 返回前N个板块，默认20
    """
    # Rate limiting
    limiter = get_limiter("fund_flow", max_calls=3, period=1.0)
    limiter.acquire()
    
    try:
        top_n = int(top_n)
        df = None
        last_error: Optional[Exception] = None
        
        # 增加重试次数
        max_retries = 3
        for i in range(max_retries):
            try:
                # 东方财富行业资金流向
                df = ak.stock_sector_fund_flow_rank(indicator="今日")
                if df is not None and not df.empty:
                    break
            except Exception as exc:
                last_error = exc
                if i < max_retries - 1:
                    time.sleep(1.0) # wait 1s before retry
        
        if df is None or df.empty:
            # Fallback
            fallback = _fetch_sector_flow_eastmoney(top_n)
            if fallback:
                return ok(fallback)
            
            msg = str(last_error) if last_error else "接口返回为空"
            return fail(f"未获取到行业板块资金流向数据 (Retried {max_retries} times): {msg}")

        df = df.head(top_n)
        results: list[dict] = []
        for _, row in df.iterrows():
            results.append(
                {
                    "name": str(row.get("名称", "")),
                    "changePercent": safe_float(row.get("今日涨跌幅")),
                    "mainNetInflow": safe_float(row.get("主力净流入-净额")),
                    "mainNetInflowPercent": safe_float(row.get("主力净流入-净占比")),
                    "superLargeNetInflow": safe_float(row.get("超大单净流入-净额")),
                    "largeNetInflow": safe_float(row.get("大单净流入-净额")),
                    "mediumNetInflow": safe_float(row.get("中单净流入-净额")),
                    "smallNetInflow": safe_float(row.get("小单净流入-净额")),
                }
            )
        return ok(results)
    except Exception as e:
        return fail(f"系统错误: {e}")


def _fetch_sector_flow_eastmoney(top_n: int) -> list[dict]:
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        response = requests.get(
            url,
            params={
                "pn": 1,
                "pz": top_n,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fs": "m:90+t:2",
                "fields": "f12,f14,f3,f62,f66,f184",
            },
            timeout=6,
        )
        if response.status_code != 200:
            return []
        payload = response.json()
        items = payload.get("data", {}).get("diff", []) if isinstance(payload, dict) else []
        results: list[dict] = []
        for item in items:
            change_raw = parse_numeric(item.get("f3"))
            main_in = parse_numeric(item.get("f62"))
            main_out = parse_numeric(item.get("f66"))
            net_inflow = None
            if main_in is not None and main_out is not None:
                net_inflow = main_in - main_out
            results.append(
                {
                    "name": str(item.get("f14") or ""),
                    "changePercent": change_raw / 100 if change_raw is not None else None,
                    "mainNetInflow": net_inflow if net_inflow is not None else main_in,
                    "mainNetInflowPercent": parse_numeric(item.get("f184")),
                    "superLargeNetInflow": None,
                    "largeNetInflow": None,
                    "mediumNetInflow": None,
                    "smallNetInflow": None,
                }
            )
        return results
    except Exception:
        return []


@cached(ttl=300.0)  # 5min cache for concept fund flow
def get_concept_fund_flow(top_n: int = 20) -> dict:
    """
    获取概念板块资金流向

    Args:
        top_n: 返回前N个板块，默认20
    """
    # Rate limiting
    limiter = get_limiter("fund_flow", max_calls=3, period=1.0)
    limiter.acquire()
    
    try:
        top_n = int(top_n)
        df = ak.stock_fund_flow_concept(symbol="即时")
        if df is None or df.empty:
            return fail("未获取到概念板块资金流向数据")

        df = df.head(top_n)
        results: list[dict] = []
        for _, row in df.iterrows():
            name = pick_value(row, ["行业", "概念", "名称"]) or ""
            change = safe_float(pick_value(row, ["行业-涨跌幅", "阶段涨跌幅", "涨跌幅", "最新涨跌幅"]))
            net_inflow = safe_float(pick_value(row, ["净额", "主力净流入-净额", "主力净流入"]))
            inflow = safe_float(pick_value(row, ["流入资金"]))
            outflow = safe_float(pick_value(row, ["流出资金"]))
            results.append(
                {
                    "name": str(name),
                    "changePercent": change,
                    "mainNetInflow": net_inflow if net_inflow is not None else inflow,
                    "mainNetInflowPercent": None,
                    "inflow": inflow,
                    "outflow": outflow,
                }
            )
        return ok(results)
    except Exception as e:
        return fail(e)


from ..date_utils import get_latest_trading_date, format_date_dash

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
             # Use unified utility to get latest trading date
             date = get_latest_trading_date()
        else:
            date = date.replace("-", "")

        # Target date string for Sina: YYYY-MM-DD
        date_dash = format_date_dash(date)

        results: list[dict] = []
        df = None
        source = "unknown"

        # 1. Try Sina First (Scheme C: Redundancy)
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
        
        # Normalize columns because Sina and EM return different columns
        # Sina: 股票代码, 股票名称, 收盘价, 对应日涨跌幅, 上榜原因, 累积买入额(万), 累积卖出额(万), 净额(万) -- values might be scaled
        # EM: 代码, 名称, 收盘价, 涨跌幅, 上榜原因, 买入额, 卖出额, 净买额
        
        for _, row in df.iterrows():
            try:
                # Handle Sina Columns
                if source == "sina":
                    code_val = row.get("股票代码")
                    name = str(row.get("股票名称", ""))
                    close = safe_float(row.get("收盘价"))
                    # '对应值' is likely the specific value related to the reason (e.g. deviation or turnover)
                    # For consistency, we put it in changePercent if it looks like a percentage, or just keep it.
                    # Given '指标' is the reason.
                    change = safe_float(row.get("对应值")) 
                    reason = str(row.get("指标", ""))
                    
                    # Sina summary API doesn't provide specific seat buy/sell info in this endpoint
                    buy = None
                    sell = None
                    net = None
                else: 
                    # EM Columns
                    code_val = row.get("代码")
                    name = str(row.get("名称", ""))
                    close = safe_float(row.get("收盘价"))
                    change = safe_float(row.get("涨跌幅"))
                    reason = str(row.get("上榜原因", ""))
                    buy = safe_float(row.get("买入额"))
                    sell = safe_float(row.get("卖出额"))
                    net = safe_float(row.get("净买额"))

                if code_val is None: continue
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
                        "buyAmount": buy,
                        "sellAmount": sell,
                        "netAmount": net,
                        "source": source
                    }
                )
            except Exception:
                continue
                
        return ok(results)
    except Exception as e:
        return fail(e)

def _check_lhb_exists(date_str: str) -> bool:
    # Lightweight check using Sina
    try:
        d = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        df = ak.stock_lhb_detail_daily_sina(date=d)
        return df is not None and not df.empty
    except:
        return False


def get_margin_data() -> dict:
    """获取市场融资融券数据"""
    try:
        def scale_margin(val: Any) -> Optional[float]:
            num = parse_numeric(val)
            return num * 1e8 if num is not None else None

        df = ak.stock_margin_account_info()
        if df is not None and not df.empty:
            row = df.iloc[-1]
            return ok(
                {
                    "date": str(row.get("日期", "")),
                    "marginBalance": scale_margin(row.get("融资余额")),
                    "marginBuy": scale_margin(row.get("融资买入额")),
                    "marginRepay": None,
                    "shortBalance": scale_margin(row.get("融券余额")),
                    "shortSell": scale_margin(row.get("融券卖出额")),
                    "shortRepay": None,
                }
            )

        df = ak.stock_margin_sse(start_date="20010106", end_date=datetime.now().strftime("%Y%m%d"))
        if df is None or df.empty:
            return fail("未获取到融资融券数据")

        row = df.iloc[-1]
        return ok(
            {
                "date": str(row.get("信用交易日期", "")),
                "marginBalance": safe_float(row.get("融资余额")),
                "marginBuy": safe_float(row.get("融资买入额")),
                "marginRepay": safe_float(row.get("融资偿还额")),
                "shortBalance": safe_float(row.get("融券余量")),
                "shortSell": safe_float(row.get("融券卖出量")),
                "shortRepay": safe_float(row.get("融券偿还量")),
            }
        )
    except Exception as e:
        return fail(e)


def register(mcp):
    mcp.tool()(get_north_fund)
    mcp.tool()(get_sector_fund_flow)
    mcp.tool()(get_concept_fund_flow)
    mcp.tool()(get_dragon_tiger)
    mcp.tool()(get_margin_data)
