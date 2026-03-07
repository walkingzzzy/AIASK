"""涨停板数据模块 — 数据源: Tushare stk_limit + daily 组合

代理 stk_limit 仅返回 5 个字段 (ts_code, trade_date, pre_close, up_limit, down_limit)，
缺少 close/pct_chg/limit/name/lu_count。

解决方案：
1. 用 stk_limit 获取涨停价 (up_limit) 和昨收 (pre_close)
2. 用 daily 获取当日 close/pct_chg
3. 通过 close == up_limit 判断涨停
4. 用 stock_basic 补全名称
"""

import logging
from datetime import datetime

import pandas as pd
import requests

from ..market.helpers import (
    normalize_code, parse_numeric, pick_value, parse_date_input,
    ok, fail
)
from ...core.cache_manager import cached
from ...core.rate_limiter import get_limiter
from ...data_source import data_source

logger = logging.getLogger(__name__)


def _tushare_http_call(api_name: str, params: dict | None = None, fields: str = ""):
    """直接通过 HTTP 调用 Tushare 代理 API"""
    http_url = data_source.get_tushare_http_url()
    token = getattr(data_source, "tushare_token", "")
    if not http_url or not token:
        return None
    try:
        payload = {"api_name": api_name, "token": token, "params": params or {}, "fields": fields}
        resp = requests.post(http_url, json=payload, timeout=30)
        result = resp.json()
        if result.get("code") != 0:
            return None
        data = result.get("data", {})
        if data:
            return pd.DataFrame(data.get("items", []), columns=data.get("fields", []))
    except Exception:
        pass
    return None


def _get_name_map() -> dict:
    """获取 ts_code → name 映射"""
    try:
        df = _tushare_http_call("stock_basic", {"exchange": "", "list_status": "L"}, fields="ts_code,name")
        if df is not None and not df.empty:
            name_map = {}
            for _, row in df.iterrows():
                code = str(row.get("ts_code", "")).split(".")[0]
                name = str(row.get("name", "") or "")
                if code and name:
                    name_map[code] = name
            return name_map
    except Exception:
        pass
    return {}


@cached(ttl=300.0)
def get_limit_up_stocks(date: str = "") -> dict:
    """获取涨停板数据。

    策略：stk_limit (涨停价) + daily (收盘价/涨跌幅) 组合判断涨停。

    数据源优先级: Tushare Pro (stk_limit + daily + stock_basic)
    时效性: 日频，通常 T+1 发布；自动回溯最近 10 个交易日

    Args:
        date (str, optional): 日期，格式 YYYY-MM-DD 或 YYYYMMDD，默认最近交易日

    Returns:
        dict: {"success": bool, "data": list[dict]}
        每项含:
        - code (str): 股票代码
        - name (str): 股票名称
        - price (float): 收盘价/涨停价
        - changePercent (float): 涨跌幅(%)
        - limitUpPrice (float): 涨停价
        - continuousDays (int): 连板天数
        - openTimes (int): 开板次数
        - turnoverRate (float): 换手率
        - marketCap (float): 市值
        - industry (str): 所属行业

    Errors:
        - Tushare 数据源不可用或指定日期无数据时返回 success=true 但 data 为空列表

    Examples:
        get_limit_up_stocks()
        get_limit_up_stocks("2026-01-15")
    """
    from datetime import timedelta
    limiter = get_limiter("quote", max_calls=5, period=1.0)
    limiter.acquire()

    target_date = parse_date_input(date) if date else datetime.now().date()
    results: list[dict] = []

    # 尝试最近 10 个交易日
    for days_back in range(10):
        check_date = (target_date - timedelta(days=days_back)).strftime("%Y%m%d")

        # 1) 获取 stk_limit（涨停价/跌停价/昨收）
        limit_df = _tushare_http_call("stk_limit", {"trade_date": check_date})
        if limit_df is None or limit_df.empty:
            continue

        # 2) 获取 daily（收盘价/涨跌幅/成交量）
        daily_df = _tushare_http_call(
            "daily",
            {"trade_date": check_date},
            fields="ts_code,trade_date,open,high,low,close,pct_chg,vol,amount",
        )
        if daily_df is None or daily_df.empty:
            continue

        # 3) 合并两个 DataFrame
        merged = pd.merge(limit_df, daily_df, on=["ts_code", "trade_date"], how="inner")
        if merged.empty:
            continue

        # 4) 筛选涨停：close >= up_limit（允许 0.01 误差）
        merged["close_f"] = pd.to_numeric(merged["close"], errors="coerce").fillna(0)
        merged["up_limit_f"] = pd.to_numeric(merged["up_limit"], errors="coerce").fillna(0)
        merged["pre_close_f"] = pd.to_numeric(merged.get("pre_close", pd.Series(dtype=float)), errors="coerce").fillna(0)
        merged["pct_chg_f"] = pd.to_numeric(merged.get("pct_chg", pd.Series(dtype=float)), errors="coerce").fillna(0)

        up_mask = (merged["up_limit_f"] > 0) & (merged["close_f"] >= merged["up_limit_f"] - 0.01)
        up_df = merged[up_mask]

        if up_df.empty:
            continue

        # 5) 构建结果
        for _, row in up_df.iterrows():
            ts_code = str(row.get("ts_code", ""))
            code = ts_code.split(".")[0] if ts_code else ""
            if not code:
                continue

            close_price = float(row.get("close_f", 0))
            up_limit_price = float(row.get("up_limit_f", 0))
            pre_close = float(row.get("pre_close_f", 0))
            pct_chg = float(row.get("pct_chg_f", 0))
            price = close_price or up_limit_price

            results.append({
                "code": normalize_code(code),
                "name": "",  # 后面批量补全
                "price": price,
                "changePercent": pct_chg,
                "limitUpPrice": up_limit_price or price,
                "firstLimitTime": "",
                "lastLimitTime": "",
                "openTimes": 0,
                "continuousDays": 0,  # 后面尝试计算
                "turnoverRate": 0,
                "marketCap": 0,
                "industry": "",
                "concept": "",
            })

        if results:
            # 6) 批量补全名称
            name_map = _get_name_map()
            if name_map:
                for r in results:
                    r["name"] = name_map.get(r["code"], "")

            # 6.5) 补全 turnoverRate / industry 从 daily_basic
            try:
                basic_df = _tushare_http_call(
                    "daily_basic",
                    {"trade_date": check_date},
                    fields="ts_code,turnover_rate,pe,total_mv",
                )
                if basic_df is not None and not basic_df.empty:
                    basic_map = {}
                    for _, brow in basic_df.iterrows():
                        bc = str(brow.get("ts_code", "")).split(".")[0]
                        if bc:
                            basic_map[bc] = brow
                    for r in results:
                        brow = basic_map.get(r["code"])
                        if brow is not None:
                            tr = parse_numeric(brow.get("turnover_rate"))
                            if tr is not None:
                                r["turnoverRate"] = float(tr)
                            mv = parse_numeric(brow.get("total_mv"))
                            if mv is not None:
                                r["marketCap"] = float(mv)
            except Exception:
                pass

            # 6.6) 补全 industry 从 stock_basic
            try:
                industry_df = _tushare_http_call(
                    "stock_basic",
                    {"exchange": "", "list_status": "L"},
                    fields="ts_code,industry",
                )
                if industry_df is not None and not industry_df.empty:
                    ind_map = {}
                    for _, irow in industry_df.iterrows():
                        ic = str(irow.get("ts_code", "")).split(".")[0]
                        if ic:
                            ind_map[ic] = str(irow.get("industry", "") or "")
                    for r in results:
                        ind = ind_map.get(r["code"], "")
                        if ind:
                            r["industry"] = ind
            except Exception:
                pass

            # 7) 尝试计算连板天数（往前查最多 10 天）
            _fill_continuous_days(results, check_date)

            break  # 找到有数据的交易日就停止

    return ok(results)


def _fill_continuous_days(results: list[dict], current_date: str):
    """通过往前查 stk_limit + daily 计算连板天数。"""
    from datetime import timedelta

    if not results:
        return

    # 收集需要查连板的股票代码
    code_set = {r["code"] for r in results}
    # 记录每只股票的连板天数（当天已涨停 = 至少 1 天）
    cont_days = {code: 1 for code in code_set}

    base = datetime.strptime(current_date, "%Y%m%d").date()

    # 往前查最多 10 个自然日（约 7 个交易日）
    for days_back in range(1, 11):
        if not code_set:
            break
        prev_date = (base - timedelta(days=days_back)).strftime("%Y%m%d")

        limit_df = _tushare_http_call("stk_limit", {"trade_date": prev_date})
        if limit_df is None or limit_df.empty:
            continue

        daily_df = _tushare_http_call("daily", {"trade_date": prev_date}, fields="ts_code,close")
        if daily_df is None or daily_df.empty:
            continue

        merged = pd.merge(limit_df, daily_df, on="ts_code", how="inner")
        if merged.empty:
            continue

        merged["close_f"] = pd.to_numeric(merged["close"], errors="coerce").fillna(0)
        merged["up_limit_f"] = pd.to_numeric(merged["up_limit"], errors="coerce").fillna(0)

        # 找出当天涨停的股票
        up_codes_today = set()
        for _, row in merged.iterrows():
            if row["up_limit_f"] > 0 and row["close_f"] >= row["up_limit_f"] - 0.01:
                c = str(row.get("ts_code", "")).split(".")[0]
                if c in code_set:
                    up_codes_today.add(c)

        # 更新连板天数
        still_continuous = set()
        for c in code_set:
            if c in up_codes_today:
                cont_days[c] += 1
                still_continuous.add(c)
        # 不再连板的股票不需要继续查
        code_set = still_continuous

    # 写回结果
    for r in results:
        r["continuousDays"] = cont_days.get(r["code"], 1)


@cached(ttl=300.0)
def get_limit_up_statistics(date: str = "") -> dict:
    """获取涨停统计数据

    Args:
        date (str, optional): 日期，格式 YYYY-MM-DD 或 YYYYMMDD，默认最近交易日

    Returns:
        dict: {"success": bool, "data": {...}}
        data 字段:
        - date (str): 统计日期
        - totalLimitUp (int): 涨停总数
        - firstBoard (int): 首板数量
        - secondBoard (int): 二连板数量
        - thirdBoard (int): 三连板数量
        - higherBoard (int): 四连板及以上数量
        - failedBoard (int): 炸板数量
        - limitDown (int): 跌停数量
        - successRate (float): 封板成功率(%)

    Errors:
        - 内部调用 get_limit_up_stocks 失败时透传其错误

    Examples:
        get_limit_up_statistics()
        get_limit_up_statistics("2026-01-15")
    """
    res = get_limit_up_stocks(date)
    if not res.get("success"):
        return res
    data = res.get("data") or []
    total = len(data)

    def count_boards(target: int) -> int:
        return sum(1 for item in data if int(item.get("continuousDays", 0)) == target)

    higher = sum(1 for item in data if int(item.get("continuousDays", 0)) >= 4)
    failed = sum(1 for item in data if int(item.get("openTimes", 0)) > 0)
    denom = total + failed
    success_rate = (total / denom) * 100 if denom > 0 else 0

    target_date = (parse_date_input(date) or datetime.now().date()).isoformat()

    result = {
        "date": target_date,
        "totalLimitUp": total,
        "firstBoard": count_boards(1) if total > 0 else 0,
        "secondBoard": count_boards(2),
        "thirdBoard": count_boards(3),
        "higherBoard": higher,
        "failedBoard": failed,
        "limitDown": 0,
        "successRate": round(success_rate, 2),
    }

    return ok(result)
