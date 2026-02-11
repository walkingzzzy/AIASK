"""K线数据模块"""

import sys
import re
import json
import requests
from datetime import datetime, timedelta
from typing import Optional
from ..market.helpers import (
    normalize_code, safe_float, safe_int, parse_date_input,
    run_with_retry as _run_with_retry,
    KLINE_TIMEOUTS as _KLINE_TIMEOUTS,
    ok, fail
)
from ...core.cache_manager import cached
from ...core.rate_limiter import get_limiter
from ...core.validators import validate_kline
from ...data_source import data_source
try:
    from ...baostock_api import baostock_client
except (ImportError, Exception):
    baostock_client = None
try:
    import akshare as ak
except ImportError:
    ak = None
import pandas as pd


def _process_kline_akshare(df: pd.DataFrame, code: str) -> list[dict]:
    results = []
    for _, row in df.iterrows():
        date = str(row.get("日期", ""))[:10]
        open_ = safe_float(row.get("开盘"))
        close = safe_float(row.get("收盘"))
        high = safe_float(row.get("最高"))
        low = safe_float(row.get("最低"))
        if not date or open_ is None or close is None or high is None or low is None:
             continue

        results.append(
            {
                "date": date,
                "open": open_,
                "close": close,
                "high": high,
                "low": low,
                "volume": safe_int(row.get("成交量")),
                "amount": safe_float(row.get("成交额")),
                "source": "akshare"
            }
        )
    return results


@cached(ttl=3600.0)
def get_kline(stock_code: str, period: str = "daily", limit: int = 100) -> dict:
    """获取股票/ETF历史K线数据（日线/周线/月线）

    适用场景: 趋势分析、波动率估算、回测数据准备、技术指标计算

    数据源优先级: DataSource(TDX → Tushare) → AkShare → Tencent → Baostock
    时效性: 日线通常 T+0~T+1；周线/月线按自然周期更新

    Args:
        stock_code (str, required): 证券代码，6位数字，如 "600519"(贵州茅台)、"510050"(50ETF)
        period (str, optional): K线周期，可选 "daily"/"weekly"/"monthly"，默认 "daily"
        limit (int, optional): 返回条数，默认 100

    Returns:
        dict: {"success": bool, "data": list[dict], "error": str|None}
        data 每条记录包含: date(str), open(float), close(float), high(float), low(float),
        volume(int), amount(float), source(str)

    Errors:
        - 股票代码无效或所有数据源均不可用时返回 success=false

    Examples:
        get_kline("600519")
        get_kline("510050", period="weekly", limit=52)
    """
    limiter = get_limiter("kline", max_calls=5, period=1.0)
    limiter.acquire()

    code = normalize_code(stock_code)
    try:
        # 1. DataSource 优先：TDX → Tushare
        ds_results = data_source.get_kline(code, period, limit)
        if ds_results:
            validated_results = [validate_kline(item).model_dump() for item in ds_results]
            return ok(validated_results)
    except Exception as e:
        print(f"DataSource K-line fetch failed for {code}: {e}", file=sys.stderr)

    # 2. AkShare 降级
    if ak is not None:
        try:
            df = _run_with_retry(
                lambda: ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq"),
                _KLINE_TIMEOUTS,
            )
            if df is not None and not df.empty:
                df = df.tail(int(limit))
                results = _process_kline_akshare(df, code)
                if results:
                    validated_results = [validate_kline(item).model_dump() for item in results]
                    return ok(validated_results)
        except Exception as e:
            print(f"AkShare K-line fetch failed for {code}: {e}", file=sys.stderr)

        # 2.5 Tencent K线（仅日线）
        if period == "daily" and ak is not None:
            try:
                end_date = datetime.now().strftime("%Y%m%d")
                start_date = (datetime.now() - timedelta(days=int(limit) * 2 + 30)).strftime("%Y%m%d")
                market_prefix = "sh" if code.startswith("6") else "sz"
                symbol = f"{market_prefix}{code}"
                df_tx = ak.stock_zh_a_hist_tx(
                    symbol=symbol, start_date=start_date, end_date=end_date,
                    adjust="", timeout=_KLINE_TIMEOUTS[-1] if _KLINE_TIMEOUTS else None,
                )
                if df_tx is not None and not df_tx.empty:
                    results = []
                    for _, row in df_tx.tail(int(limit)).iterrows():
                        results.append({
                            "date": str(row.get("date", ""))[:10],
                            "open": safe_float(row.get("open")),
                            "close": safe_float(row.get("close")),
                            "high": safe_float(row.get("high")),
                            "low": safe_float(row.get("low")),
                            "volume": safe_int(row.get("volume")),
                            "amount": safe_float(row.get("amount")),
                            "source": "tencent",
                        })
                    if results:
                        validated_results = [validate_kline(item).model_dump() for item in results]
                        return ok(validated_results)
            except Exception as e_tx:
                print(f"Tencent K-line fetch failed for {code}: {e_tx}", file=sys.stderr)

    # 3. Baostock 降级（仅日线）
    if period == "daily" and baostock_client is not None:
        try:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=limit * 1.5 + 30)).strftime("%Y-%m-%d")
            df_bs = baostock_client.get_history_k_data(code, start_date, end_date)
            if not df_bs.empty:
                results = []
                for _, row in df_bs.tail(limit).iterrows():
                    results.append({
                        "date": row["date"],
                        "open": safe_float(row["open"]),
                        "close": safe_float(row["close"]),
                        "high": safe_float(row["high"]),
                        "low": safe_float(row["low"]),
                        "volume": safe_int(row["volume"]),
                        "amount": safe_float(row["amount"]),
                        "source": "baostock"
                    })
                validated_results = [validate_kline(item).model_dump() for item in results]
                return ok(validated_results)
        except Exception as e2:
            print(f"Baostock K-line fetch failed for {code}: {e2}", file=sys.stderr)

    return fail(f"所有数据源均无法获取 {code} 的K线数据")


def _parse_minute_period(period: str) -> Optional[int]:
    raw = str(period or "").strip().lower()
    if raw.endswith("m"):
        raw = raw[:-1]
    try:
        minutes = int(raw)
    except ValueError:
        return None
    if minutes in (1, 5, 15, 30, 60):
        return minutes
    return None


def _get_minute_kline_from_akshare(code: str, minutes: int, limit: int) -> list[dict]:
    try:
        df = _run_with_retry(
            lambda: ak.stock_zh_a_hist_min_em(symbol=code, period=str(minutes), adjust=""),
            _KLINE_TIMEOUTS,
        )
    except Exception:
        return []
    if df is None or df.empty:
        return []
    df = df.tail(int(limit))
    results = []
    for _, row in df.iterrows():
        ts = row.get("时间") or row.get("日期") or row.get("time") or row.get("date")
        date_str = str(ts)[:19]
        results.append(
            {
                "date": date_str,
                "open": safe_float(row.get("开盘") or row.get("open")),
                "close": safe_float(row.get("收盘") or row.get("close")),
                "high": safe_float(row.get("最高") or row.get("high")),
                "low": safe_float(row.get("最低") or row.get("low")),
                "volume": safe_int(row.get("成交量") or row.get("volume")),
                "amount": safe_float(row.get("成交额") or row.get("amount")),
                "source": "akshare_minute",
            }
        )
    return results


def _get_minute_kline_from_sina(code: str, minutes: int, limit: int) -> list[dict]:
    try:
        if code.startswith("6") or code.startswith("68"):
            symbol = f"sh{code}"
        elif code.startswith("8") or code.startswith("4"):
            symbol = f"bj{code}"
        else:
            symbol = f"sz{code}"

        url = (
            "https://quotes.sina.cn/cn/api/jsonp_v2.php/"
            f"data=/CN_MarketDataService.getKLineData?symbol={symbol}&scale={minutes}&ma=no&datalen={limit}"
        )
        resp = requests.get(
            url,
            headers={
                "Referer": "https://finance.sina.com.cn",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=15,
        )
        payload = resp.text or ""
        match = re.search(r"\(\[([\s\S]*?)\]\)", payload)
        if not match:
            return []
        klines = json.loads(f"[{match.group(1)}]")
        results = []
        for item in klines:
            results.append(
                {
                    "date": str(item.get("day") or "")[:19],
                    "open": safe_float(item.get("open")),
                    "close": safe_float(item.get("close")),
                    "high": safe_float(item.get("high")),
                    "low": safe_float(item.get("low")),
                    "volume": safe_int(item.get("volume")),
                    "amount": safe_float(item.get("amount")),
                    "source": "sina",
                }
            )
        return results
    except Exception:
        return []


@cached(ttl=60.0)
def get_minute_kline(stock_code: str, period: str = "5m", limit: int = 300) -> dict:
    """获取分钟级K线数据（盘中实时）

    数据源优先级: TDX（唯一支持分钟级的 DataSource 路径） → AkShare → Sina
    时效性: 仅交易时段（9:30-15:00）有效，盘后数据为当日最后快照

    Args:
        stock_code (str, required): 证券代码，6位数字
        period (str, optional): 分钟周期，可选 "1m"/"5m"/"15m"/"30m"/"60m"，默认 "5m"
        limit (int, optional): 返回条数，默认 300

    Returns:
        dict: 与 get_kline 结构一致，date 字段包含时间部分（如 "2025-06-01 14:30:00"）

    Errors:
        - period 不在枚举范围内时返回 success=false

    Examples:
        get_minute_kline("600519")
        get_minute_kline("000001", period="15m", limit=100)
    """
    limiter = get_limiter("kline", max_calls=5, period=1.0)
    limiter.acquire()

    code = normalize_code(stock_code)
    minutes = _parse_minute_period(period)
    if minutes is None:
        return fail("period 必须为 1m/5m/15m/30m/60m")

    # 1. 优先 TDX 分钟K线（TDX 是唯一支持分钟级的 DataSource 路径）
    if data_source.is_tdx_available():
        try:
            ds_results = data_source.get_kline(code, period, limit)
            if ds_results:
                # 验证返回的确实是分钟数据（日期字段应包含时间部分）
                sample_date = str(ds_results[0].get('date', ''))
                if len(sample_date) > 10:  # 分钟数据日期格式: "2026-02-06 14:30:00"
                    validated_results = [validate_kline(item).model_dump() for item in ds_results]
                    return ok(validated_results)
                # 如果返回的是日线数据（仅日期），跳过
        except Exception as e:
            print(f"DataSource minute kline fetch failed for {code}: {e}", file=sys.stderr)

    results = _get_minute_kline_from_akshare(code, minutes, limit)
    if not results:
        results = _get_minute_kline_from_sina(code, minutes, limit)

    if not results:
        return fail(f"所有数据源均无法获取 {code} 的{minutes}分钟K线数据")

    validated_results = [validate_kline(item).model_dump() for item in results]
    return ok(validated_results)


def get_kline_data(
    code: str,
    period: str = "daily",
    start_date: str = None,
    end_date: str = None,
    limit: int = 30,
    adjust: str = ""
) -> dict:
    """获取K线数据（Node.js 参数兼容入口，支持日期区间查询）

    与 get_kline 的区别: 支持 start_date/end_date 日期区间过滤和复权类型选择。
    Node 兼容映射: 已作为独立工具注册；无日期参数时内部 fallback 到 get_kline。

    数据源优先级: DataSource(TDX → Tushare) → AkShare → Tencent → Baostock

    Args:
        code (str, required): 股票/ETF 代码，6位数字，如 "600519"、"510050"
        period (str, optional): K线周期，可选 "daily"/"weekly"/"monthly"/"1m"/"5m"/"15m"/"30m"/"60m"，默认 "daily"
        start_date (str, optional): 开始日期，格式 "YYYY-MM-DD" 或 "YYYYMMDD"
        end_date (str, optional): 结束日期，格式 "YYYY-MM-DD" 或 "YYYYMMDD"
        limit (int, optional): 未指定日期区间时生效，默认 30
        adjust (str, optional): 复权类型，""(不复权) / "qfq"(前复权) / "hfq"(后复权)，默认 ""

    参数依赖:
        - 当 start_date/end_date 存在时，按日期区间过滤，limit 不生效
        - 当 start_date/end_date 均为空时，按 limit 返回最近 N 条

    Returns:
        dict: 与 get_kline 返回结构一致

    Examples:
        get_kline_data("600519", start_date="2025-01-01", end_date="2025-06-30")
        get_kline_data("000001", period="weekly", limit=50, adjust="qfq")
    """
    period_map = {
        'daily': 'daily',
        'weekly': 'weekly',
        'monthly': 'monthly',
        '101': 'daily',
        '102': 'weekly',
        '103': 'monthly',
        '1m': '1',
        '5m': '5',
        '15m': '15',
        '30m': '30',
        '60m': '60',
    }
    
    mapped_period = period_map.get(period, period)
    
    if start_date or end_date:
        limiter = get_limiter("kline", max_calls=5, period=1.0)
        limiter.acquire()

        code_normalized = normalize_code(code)
        # 优先 TDX（与 docs/tdx-quant get_market_data 一致），再 akshare
        try:
            from datetime import datetime as _dt
            start_d = (start_date or "").replace("-", "")[:8] or "19900101"
            end_d = (end_date or "").replace("-", "")[:8] or _dt.now().strftime("%Y%m%d")
            if start_d > end_d:
                start_d, end_d = end_d, start_d
            limit_est = min(500, max(100, (_dt.strptime(end_d, "%Y%m%d") - _dt.strptime(start_d, "%Y%m%d")).days + 50))
            ds_results = data_source.get_kline(code_normalized, mapped_period, limit_est)
            if ds_results:
                start_norm = start_d[:4] + "-" + start_d[4:6] + "-" + start_d[6:8]
                end_norm = end_d[:4] + "-" + end_d[4:6] + "-" + end_d[6:8]
                filtered = [r for r in ds_results if start_norm <= (r.get("date") or "")[:10] <= end_norm]
                if filtered:
                    validated_results = [validate_kline(item).model_dump() for item in filtered]
                    return ok(validated_results)
        except Exception as e_ds:
            print(f"DataSource K-line (date range) failed for {code_normalized}: {e_ds}", file=sys.stderr)

        if ak is None:
            return fail(f'无法获取 {code} 的K线数据 (日期范围查询, 所有数据源均失败)')
        try:
            df = ak.stock_zh_a_hist(
                symbol=code_normalized,
                period=mapped_period,
                start_date=start_date.replace('-', '') if start_date else None,
                end_date=end_date.replace('-', '') if end_date else None,
                adjust=adjust or "qfq"
            )
            if df is None or df.empty:
                return fail(f'No kline data for {code}')
            results = _process_kline_akshare(df, code_normalized)
            validated_results = [validate_kline(item).model_dump() for item in results]
            return ok(validated_results)
        except Exception as e:
            return fail(f'Failed to get kline data: {str(e)}')

    return get_kline(code, mapped_period, limit)

# ============================================================
# 指数 K 线（独立于个股 K 线，避免代码混淆）
# ============================================================

# 指数代码 → TDX 代码映射（上证指数在 TDX 中为 999999.SH）
_INDEX_TDX_MAP = {
    "000001": "999999.SH",   # 上证指数
    "000300": "000300.SH",   # 沪深300
    "000016": "000016.SH",   # 上证50
    "000905": "000905.SH",   # 中证500
    "399001": "399001.SZ",   # 深证成指
    "399006": "399006.SZ",   # 创业板指
    "399005": "399005.SZ",   # 中小板指
}

# 指数代码 → AkShare symbol 映射
_INDEX_AK_MAP = {
    "000001": "sh000001",
    "000300": "sh000300",
    "000016": "sh000016",
    "000905": "sh000905",
    "399001": "sz399001",
    "399006": "sz399006",
    "399005": "sz399005",
}


def get_index_kline(index_code: str, period: str = "daily", limit: int = 60) -> dict:
    """获取指数K线数据（专用函数，避免与个股代码混淆）

    适用场景: 指数趋势分析、大盘走势回顾

    数据源优先级: TDX (get_market_data) → AkShare (stock_zh_index_daily_em) → Tushare
    时效性: 日线 T+0~T+1

    Args:
        index_code (str, required): 指数代码，如 "000001"(上证指数)、"399001"(深证成指)、"399006"(创业板指)
        period (str, optional): K线周期，目前仅支持 "daily"，默认 "daily"
        limit (int, optional): 数据条数，默认 60

    Returns:
        dict: {"success": bool, "data": list[dict]}
        data 每条记录包含: date(str), open(float), close(float), high(float), low(float),
        volume(int), amount(float), source(str)

    Errors:
        - 所有数据源均不可用时返回 success=false

    Examples:
        get_index_kline("000001")
        get_index_kline("399006", limit=120)
    """
    code = normalize_code(index_code)

    # 1. TDX 优先
    if data_source.is_tdx_available():
        try:
            tq = data_source.get_tdxquant()
            if tq is not None:
                tdx_code = _INDEX_TDX_MAP.get(code)
                if tdx_code is None:
                    # 通用映射：上海指数 .SH，深圳指数 .SZ
                    if code.startswith("39"):
                        tdx_code = f"{code}.SZ"
                    else:
                        tdx_code = f"{code}.SH"

                period_map = {"daily": "1d", "weekly": "1w", "monthly": "1M"}
                tdx_period = period_map.get(period, "1d")

                data = tq.get_market_data(
                    stock_list=[tdx_code],
                    period=tdx_period,
                    count=limit,
                    dividend_type='none',
                    fill_data=True,
                )
                if data and "Close" in data:
                    close_df = data.get("Close")
                    if close_df is not None and not close_df.empty:
                        results = []
                        for idx in close_df.index:
                            results.append({
                                "date": str(idx)[:10],
                                "open": safe_float(data["Open"].loc[idx, tdx_code]) if "Open" in data else None,
                                "close": safe_float(data["Close"].loc[idx, tdx_code]) if "Close" in data else None,
                                "high": safe_float(data["High"].loc[idx, tdx_code]) if "High" in data else None,
                                "low": safe_float(data["Low"].loc[idx, tdx_code]) if "Low" in data else None,
                                "volume": safe_int(data["Volume"].loc[idx, tdx_code]) if "Volume" in data else None,
                                "amount": safe_float(data["Amount"].loc[idx, tdx_code]) if "Amount" in data else None,
                                "source": "tdxquant_index",
                            })
                        if results:
                            return ok(results)
        except Exception as e:
            print(f"TDX index kline failed for {code}: {e}", file=sys.stderr)

    # 2. AkShare 降级：使用指数专用 API
    if ak is not None:
        try:
            ak_symbol = _INDEX_AK_MAP.get(code)
            if ak_symbol is None:
                if code.startswith("39"):
                    ak_symbol = f"sz{code}"
                else:
                    ak_symbol = f"sh{code}"

            df = _run_with_retry(
                lambda: ak.stock_zh_index_daily_em(symbol=ak_symbol),
                _KLINE_TIMEOUTS,
            )
            if df is not None and not df.empty:
                df = df.tail(int(limit))
                results = []
                for _, row in df.iterrows():
                    date_val = row.get("date") or row.get("日期") or ""
                    results.append({
                        "date": str(date_val)[:10],
                        "open": safe_float(row.get("open") or row.get("开盘")),
                        "close": safe_float(row.get("close") or row.get("收盘")),
                        "high": safe_float(row.get("high") or row.get("最高")),
                        "low": safe_float(row.get("low") or row.get("最低")),
                        "volume": safe_int(row.get("volume") or row.get("成交量")),
                        "amount": safe_float(row.get("amount") or row.get("成交额")),
                        "source": "akshare_index",
                    })
                if results:
                    return ok(results)
        except Exception as e:
            print(f"AkShare index kline failed for {code}: {e}", file=sys.stderr)

    # 3. Tushare 降级
    ts_pro = data_source.get_tushare_pro()
    if ts_pro is not None and period == "daily":
        try:
            # 指数在 Tushare 中的代码格式
            if code.startswith("39"):
                ts_code = f"{code}.SZ"
            else:
                ts_code = f"{code}.SH"
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=limit * 2 + 30)).strftime("%Y%m%d")
            df = ts_pro.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if df is not None and not df.empty:
                df = df.iloc[::-1].tail(limit)
                results = []
                for _, row in df.iterrows():
                    td = str(row.get("trade_date", ""))
                    results.append({
                        "date": f"{td[:4]}-{td[4:6]}-{td[6:]}" if len(td) >= 8 else td,
                        "open": safe_float(row.get("open")),
                        "close": safe_float(row.get("close")),
                        "high": safe_float(row.get("high")),
                        "low": safe_float(row.get("low")),
                        "volume": safe_float(row.get("vol")),
                        "amount": safe_float(row.get("amount")),
                        "source": "tushare_index",
                    })
                if results:
                    return ok(results)
        except Exception as e:
            print(f"Tushare index kline failed for {code}: {e}", file=sys.stderr)

    return fail(f"所有数据源均无法获取指数 {code} 的K线数据")

