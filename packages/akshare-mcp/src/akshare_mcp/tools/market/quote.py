"""实时行情模块"""

import asyncio
import requests
from datetime import datetime
from typing import Optional
from ..market.helpers import (
    normalize_code, safe_float, safe_int, pick_value, parse_numeric,
    get_spot_indexed as _get_spot_indexed,
    get_index_spot_indexed as _get_index_spot_indexed,
    get_name_map as _get_name_map,
    run_with_retry as _run_with_retry,
    QUOTE_TIMEOUTS as _QUOTE_TIMEOUTS,
    _SPOT_STALE_SECONDS, _INDEX_STALE_SECONDS,
    ok, fail
)
from ...core.cache_manager import cached
from ...core.rate_limiter import get_limiter
from ...core.validators import validate_quote
from ...data_source import data_source
from ...storage import get_db, run_with_db_cleanup
from ...utils import safe_stderr_print
from ..data_quality import build_quality_meta, infer_missing_fields, normalize_reason_list
try:
    import akshare as ak
except ImportError:
    ak = None
import pandas as pd

from ._quote_support import *

def get_realtime_quote(stock_code: str) -> dict:
    """获取单只股票实时行情（优化版）

    数据源优先级: DataSource(Tushare/公开源) → AkShare(分钟K/日K/全市场) → Sina → Tencent
    时效性: 交易时段内接近实时（秒级），非交易时段返回最近收盘数据

    Args:
        stock_code (str, required): 股票代码，6位数字，如 "600519"、"000001"

    Returns:
        dict: {"success": bool, "data": {...}}
        data 字段:
        - code (str): 标准化股票代码
        - name (str): 股票名称
        - price (float|None): 最新价
        - change (float|None): 涨跌额
        - changePercent (float|None): 涨跌幅(%)
        - open (float|None): 今开
        - high (float|None): 最高
        - low (float|None): 最低
        - preClose (float|None): 昨收
        - volume (int|None): 成交量(股)
        - amount (float|None): 成交额(元)
        - source (str): 数据来源标识，如 "data_source"/"akshare_minute"/"sina"/"tencent"

    Errors:
        - 所有数据源均不可用时返回 success=false

    Examples:
        get_realtime_quote("600519")
        get_realtime_quote("000001")
    """
    limiter = get_limiter("quote", max_calls=10, period=1.0)
    limiter.acquire()

    def _as_plain_quote(v):
        # validate_quote 可能返回 pydantic 模型；统一转为 dict 以注入结构化 trace 字段
        if hasattr(v, "model_dump"):
            try:
                return v.model_dump()
            except Exception:
                return dict(v)
        return v

    try:
        code = normalize_code(stock_code)
        attempted_sources: list[str] = []
        fallback_reason_parts: list[str] = []

        # 1. DataSource 优先：Tushare / 公开源 → akshare
        attempted_sources.append("data_source")
        try:
            res = data_source.get_realtime_quote(code)
            if res:
                validated = _as_plain_quote(validate_quote(res))
                if isinstance(validated, dict):
                    validated = _backfill_prev_close(validated, code)
                return _ok_quote_response(validated, attempted_sources=attempted_sources, source_chain=["data_source"])
        except Exception as e:
            fallback_reason_parts.append(f"data_source失败: {e}")
            safe_stderr_print(f"DataSource quote failed for {code}: {e}")

        # 2. Try AkShare
        attempted_sources.append("akshare")
        try:
            res = _get_realtime_quote_akshare(code)
        except (TimeoutError, RuntimeError, Exception) as e:
            fallback_reason_parts.append(f"akshare失败: {e}")
            safe_stderr_print(f"AkShare quote failed for {code}: {e}")
            res = None
        if res:
            validated = _as_plain_quote(validate_quote(res))
            if isinstance(validated, dict):
                validated = _backfill_prev_close(validated, code)
            return _ok_quote_response(
                validated,
                attempted_sources=attempted_sources,
                source_chain=["data_source", "akshare"],
                fallback_reason="; ".join(fallback_reason_parts) if fallback_reason_parts else "DataSource不可用，已降级至AkShare",
            )

        # 3. Try Sina
        attempted_sources.append("sina")
        safe_stderr_print(f"Trying Sina for {code}...")
        res = _get_quote_sina(code)
        if res:
            validated = _as_plain_quote(validate_quote(res))
            if isinstance(validated, dict):
                validated = _backfill_prev_close(validated, code)
            return _ok_quote_response(
                validated,
                attempted_sources=attempted_sources,
                source_chain=["data_source", "akshare", "sina"],
                fallback_reason="; ".join(fallback_reason_parts) if fallback_reason_parts else "上游源不可用，已降级至Sina",
            )

        # 4. Try Tencent
        attempted_sources.append("tencent")
        safe_stderr_print(f"Sina failed for {code}, trying Tencent...")
        res = _get_quote_tencent(code)
        if res:
            validated = _as_plain_quote(validate_quote(res))
            if isinstance(validated, dict):
                validated = _backfill_prev_close(validated, code)
            return _ok_quote_response(
                validated,
                attempted_sources=attempted_sources,
                source_chain=["data_source", "akshare", "sina", "tencent"],
                fallback_reason="; ".join(fallback_reason_parts) if fallback_reason_parts else "上游源不可用，已降级至Tencent",
            )

        attempted = " -> ".join(attempted_sources)
        reason = "; ".join(fallback_reason_parts) if fallback_reason_parts else "所有上游源均返回空数据"
        return _fail_quote_response(
            f"所有数据源均无法获取 {code} 的实时行情（attempted={attempted}, reason={reason}）",
            attempted_sources=attempted_sources,
            source_chain=["data_source", "akshare", "sina", "tencent"],
            fallback_reason=reason,
        )
    except Exception as e:
        return _fail_quote_response(
            str(e),
            attempted_sources=[],
            source_chain=["get_realtime_quote"],
            fallback_reason=str(e),
        )



def get_batch_quotes(stock_codes: list[str]) -> dict:
    """批量获取股票实时行情

    数据源优先级（逐只）: DataSource(Tushare/公开源) → AkShare(分钟K/全市场) → Sina → Tencent → 日K
    时效性: 交易时段内接近实时；批量 ≤5 只走分钟K线，>5 只走全市场快照

    Args:
        stock_codes (list[str], required): 股票代码列表，如 ["600519", "000001"]

    Returns:
        dict: {"success": bool, "data": {...}}
        data 字段:
        - requested (list[str]): 请求的代码列表
        - found (int): 成功获取数量
        - missing (list[str]): 未获取到的代码
        - quotes (list[dict]): 行情列表，每项含 code/name/price/change/changePercent/volume/amount/source

    Errors:
        - stock_codes 为空时返回 success=false

    Examples:
        get_batch_quotes(["600519", "000001", "000858"])
    """
    from ..market.helpers import _MINUTE_BATCH_LIMIT, _BATCH_FALLBACK_LIMIT

    try:
        codes = [normalize_code(c) for c in stock_codes or []]
        if not codes:
            return fail("stock_codes 不能为空")

        name_map: Optional[dict] = None  # 延后加载，仅在使用 akshare 或补 name 时再调 _get_name_map
        quotes: list[dict] = []
        missing: list[str] = []

        spot_df: Optional[pd.DataFrame] = None
        spot_cached = False
        spot_unavailable = False
        fallback_enabled = len(codes) <= _BATCH_FALLBACK_LIMIT

        use_minute = len(codes) <= _MINUTE_BATCH_LIMIT
        for code in codes:
            # 1. 优先 DataSource：Tushare / 公开源 → akshare
            try:
                fallback = data_source.get_realtime_quote(code)
                if fallback and fallback.get("price") is not None:
                    if not fallback.get("name"):
                        if name_map is None:
                            name_map = _get_name_map()
                        fallback["name"] = name_map.get(code, "")
                    quotes.append(fallback)
                    continue
            except Exception as e:
                _log_quote_source_error("batch quote datasource", code, e)

            # 以下为 akshare/其他降级路径，需要 name 时再拉取 name_map
            if name_map is None:
                name_map = _get_name_map()
            name = name_map.get(code, "")

            if use_minute:
                try:
                    minute = _get_minute_quote(code)
                    snapshot = _get_daily_snapshot(code)
                    prev_close = snapshot.get("prev_close")
                    change, change_pct = _calc_change(minute.get("price"), prev_close)
                    quotes.append(
                        {
                            "code": code,
                            "name": name,
                            "price": minute.get("price"),
                            "change": change,
                            "changePercent": change_pct,
                            "volume": minute.get("volume"),
                            "amount": minute.get("amount"),
                            "preClose": prev_close,
                            "time": minute.get("time"),
                            "source": "akshare_minute",
                        }
                    )
                    continue
                except Exception as e:
                    _log_quote_source_error("batch minute quote", code, e)

            if spot_df is None:
                try:
                    spot_df, spot_cached = _get_spot_indexed()
                except Exception as e:
                    _log_quote_source_error("batch spot snapshot", code, e)
                    spot_df = None
                    spot_unavailable = True

            if spot_df is not None and code in spot_df.index:
                row = spot_df.loc[code]
                spot_name = pick_value(row, ["名称", "股票简称"]) or name
                price = safe_float(pick_value(row, ["最新价", "最新", "现价"]))
                if price is not None:
                    quotes.append(
                        {
                            "code": code,
                            "name": str(spot_name or ""),
                            "price": price,
                            "change": safe_float(pick_value(row, ["涨跌额", "涨跌"])),
                            "changePercent": safe_float(pick_value(row, ["涨跌幅", "涨幅"])),
                            "volume": safe_int(pick_value(row, ["成交量"])),
                            "amount": safe_float(pick_value(row, ["成交额"])),
                            "source": "akshare_spot",
                        }
                    )
                    continue

            if fallback_enabled:
                fallback = _get_quote_sina(code)
                if fallback:
                    if not fallback.get("name") and name:
                        fallback["name"] = name
                    quotes.append(fallback)
                    continue

                fallback = _get_quote_tencent(code)
                if fallback:
                    if not fallback.get("name") and name:
                        fallback["name"] = name
                    quotes.append(fallback)
                    continue

            daily = None
            if not spot_unavailable:
                try:
                    daily = _get_daily_quote(code, name)
                except Exception as e:
                    _log_quote_source_error("batch daily quote", code, e)
                    daily = None
            if daily is not None:
                quotes.append(daily)
                continue

            missing.append(code)

        # 兼容历史调用：data 直接返回 quotes 列表
        # 同时在顶层补充 requested/found/missing 便于新调用读取统计信息
        result = ok(quotes, cached=spot_cached)
        result["requested"] = codes
        result["found"] = len(quotes)
        result["missing"] = missing
        result["quotes"] = quotes
        return result
    except Exception as e:
        return fail(e)

def get_batch_quotes_compat(codes: list[str]) -> dict:
    """批量获取股票实时行情（兼容Node.js版本）

    内部调用 get_batch_quotes，返回格式简化为 data=quotes 列表（无 requested/found/missing 包装）。

    Args:
        codes (list[str], required): 股票代码列表，如 ["600519", "000001"]

    Returns:
        dict: {"success": bool, "data": list[dict], "source": str, "cached": bool}
        data 为行情列表，每项含 code/name/price/change/changePercent/volume/amount/source

    Examples:
        get_batch_quotes_compat(["600519", "000001"])
    """
    result = get_batch_quotes(codes)

    if not result.get('success'):
        return result

    # P0-2 修复说明：
    # 旧实现假设 result['data'] 为 {'quotes': [...] }，但当前主接口 data 多数为 list，导致类型错误。
    # 新实现按多种历史结构兼容提取，保证兼容层返回稳定 list。
    data = result.get('data')
    if isinstance(data, list):
        quotes = data
    elif isinstance(data, dict) and isinstance(data.get('quotes'), list):
        quotes = data.get('quotes')
    elif isinstance(result.get('quotes'), list):
        quotes = result.get('quotes')
    else:
        quotes = []

    return {
        'success': True,
        'data': quotes,
        'source': result.get('source', 'multiple_adapters'),
        'cached': result.get('cached', False)
    }

def get_index_quote(index_code: str) -> dict:
    """获取指数实时行情

    降级链: 东财 push2 (get_index_spot_indexed) → AkShare Sina 接口
    时效性: 交易时段内接近实时

    Args:
        index_code (str, required): 指数代码，如 "000001"(上证指数)、"399001"(深证成指)、"399006"(创业板指)

    Returns:
        dict: {"success": bool, "data": {...}}
        data 字段:
        - code (str): 标准化指数代码
        - name (str): 指数名称
        - price (float): 最新点位
        - change (float|None): 涨跌额
        - changePercent (float|None): 涨跌幅(%)
        - open (float|None): 今开
        - high (float|None): 最高
        - low (float|None): 最低
        - preClose (float|None): 昨收
        - volume (int|None): 成交量
        - amount (float|None): 成交额

    Errors:
        - 指数代码不存在时返回 success=false
        - 数据源返回异常时返回 success=true 但 price=None 并附 message

    Examples:
        get_index_quote("000001")
        get_index_quote("399006")
    """
    try:
        code = normalize_code(index_code)
        df, cached = _get_index_spot_indexed()
        if code not in df.index:
            # 东财 push2 没找到，尝试 AkShare Sina 接口
            try:
                if ak is not None:
                    df_sina = ak.stock_zh_index_spot_sina()
                    if df_sina is not None and not df_sina.empty:
                        df_sina["代码"] = df_sina["代码"].apply(normalize_code)
                        df_sina = df_sina.set_index("代码", drop=False)
                        if code in df_sina.index:
                            df = df_sina
                            cached = False
            except Exception as e:
                safe_stderr_print(f"[quote] index sina fallback failed for {code}: {e}")
            if code not in df.index:
                return fail(f"未找到指数 {code}")

        r = df.loc[code]
        price = safe_float(pick_value(r, ["最新价", "最新", "现价"]))
        if price is None:
            return fail(f"指数 {code} 缺少价格数据")

        return ok(
            {
                "code": code,
                "name": str(pick_value(r, ["名称", "指数名称"]) or ""),
                "price": price,
                "change": safe_float(pick_value(r, ["涨跌额", "涨跌"])),
                "changePercent": safe_float(pick_value(r, ["涨跌幅", "涨幅"])),
                "open": safe_float(pick_value(r, ["今开", "开盘"])),
                "high": safe_float(pick_value(r, ["最高", "最高价"])),
                "low": safe_float(pick_value(r, ["最低", "最低价"])),
                "preClose": safe_float(pick_value(r, ["昨收", "昨收价"])),
                "volume": safe_int(pick_value(r, ["成交量"])),
                "amount": safe_float(pick_value(r, ["成交额"])),
            },
            cached=cached,
        )
    except Exception as e:
        err = str(e)
        if "decode" in err.lower() or "starting with" in err or "'<'" in err:
            # Fallback: try Tushare index_daily for the latest data point
            try:
                ts_pro = data_source.get_tushare_pro()
                if ts_pro is not None:
                    code_fb = normalize_code(index_code)
                    ts_code = f"{code_fb}.SZ" if code_fb.startswith("39") else f"{code_fb}.SH"
                    from datetime import datetime as _dt, timedelta as _td
                    end_d = _dt.now().strftime("%Y%m%d")
                    start_d = (_dt.now() - _td(days=10)).strftime("%Y%m%d")
                    df_ts = ts_pro.index_daily(ts_code=ts_code, start_date=start_d, end_date=end_d)
                    if df_ts is not None and not df_ts.empty:
                        row_ts = df_ts.iloc[0]  # latest date first
                        ts_price = safe_float(row_ts.get("close"))
                        ts_pre = safe_float(row_ts.get("pre_close"))
                        ts_change, ts_pct = _calc_change(ts_price, ts_pre)
                        if ts_price is not None:
                            return ok(
                                {
                                    "code": code_fb,
                                    "name": "",
                                    "price": ts_price,
                                    "change": ts_change,
                                    "changePercent": ts_pct,
                                    "open": safe_float(row_ts.get("open")),
                                    "high": safe_float(row_ts.get("high")),
                                    "low": safe_float(row_ts.get("low")),
                                    "preClose": ts_pre,
                                    "volume": safe_float(row_ts.get("vol")),
                                    "amount": safe_float(row_ts.get("amount")),
                                    "source": "tushare_index_daily_fallback",
                                },
                                cached=False,
                            )
            except Exception as e:
                safe_stderr_print(f"[quote] tushare index daily fallback failed for {index_code}: {e}")
            return ok(
                {
                    "code": index_code,
                    "name": "",
                    "price": None,
                    "change": None,
                    "changePercent": None,
                    "message": f"指数数据暂时不可用（数据源返回异常）: {err[:200]}",
                },
                cached=False,
            )
        return fail(e)
