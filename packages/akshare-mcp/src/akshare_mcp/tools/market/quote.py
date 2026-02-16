"""实时行情模块"""

import asyncio
import time
import requests
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
from ...storage import get_db
from ...utils import safe_stderr_print
try:
    import akshare as ak
except ImportError:
    ak = None
import pandas as pd


def _get_daily_snapshot(code: str) -> dict[str, Optional[float]]:
    """获取日K快照（用于补充 open/high/low/prev_close）

    降级链: DataSource(TDX→Tushare) → AkShare
    """
    # 1. 优先 DataSource
    try:
        ds_results = data_source.get_kline(code, "daily", 2)
        if ds_results and len(ds_results) >= 1:
            row = ds_results[-1]
            prev_close = safe_float(ds_results[-2].get("close")) if len(ds_results) >= 2 else None
            return {
                "open": safe_float(row.get("open")),
                "high": safe_float(row.get("high")),
                "low": safe_float(row.get("low")),
                "prev_close": prev_close,
            }
    except Exception:
        pass

    # 2. 降级 AkShare
    if ak is None:
        return {}
    try:
        df = _run_with_retry(
            lambda: ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq"),
            _QUOTE_TIMEOUTS,
        )
        if df is None or df.empty:
            return {}
        row = df.iloc[-1]
        prev_close = safe_float(df.iloc[-2].get("收盘")) if len(df) >= 2 else None
        return {
            "open": safe_float(row.get("开盘")),
            "high": safe_float(row.get("最高")),
            "low": safe_float(row.get("最低")),
            "prev_close": prev_close,
        }
    except Exception:
        return {}


def _coalesce_price(value: Optional[float], fallback: Optional[float]) -> Optional[float]:
    if value is None or value == 0:
        return fallback
    return value


def _calc_change(price: Optional[float], prev_close: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    if price is None or prev_close is None or prev_close == 0:
        return None, None
    change = price - prev_close
    return change, (change / prev_close) * 100


def _normalize_quote_for_storage(payload: dict) -> Optional[dict]:
    """将行情对象标准化为 DB save_quote 可接收结构。"""
    if not isinstance(payload, dict):
        return None
    code = normalize_code(str(payload.get("code") or "").strip()) if payload.get("code") else None
    price = safe_float(payload.get("price"))
    if not code or price is None:
        return None

    return {
        "code": code,
        "name": payload.get("name") or "",
        "price": price,
        "change": safe_float(payload.get("change")),
        "change_pct": safe_float(payload.get("changePercent") if payload.get("changePercent") is not None else payload.get("change_pct")),
        "open": safe_float(payload.get("open")),
        "high": safe_float(payload.get("high")),
        "low": safe_float(payload.get("low")),
        "pre_close": safe_float(payload.get("preClose") if payload.get("preClose") is not None else payload.get("pre_close")),
        "volume": safe_int(payload.get("volume")),
        "amount": safe_float(payload.get("amount")),
        "source": payload.get("source") or "unknown",
    }


async def _save_quote_best_effort(payload: dict) -> None:
    """尽力落库：失败不影响主流程返回。"""
    try:
        normalized = _normalize_quote_for_storage(payload)
        if not normalized:
            return
        db = get_db()
        await db.save_quote(normalized)
    except Exception as e:
        safe_stderr_print(f"[quote] save_quote skipped: {e}")


def _save_quote_nonblocking(payload: dict) -> None:
    """在同步工具函数中安全触发异步落库。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        try:
            loop.create_task(_save_quote_best_effort(payload))
        except Exception as e:
            safe_stderr_print(f"[quote] create save task failed: {e}")
        return

    try:
        asyncio.run(_save_quote_best_effort(payload))
    except Exception as e:
        safe_stderr_print(f"[quote] save_quote run failed: {e}")



def _save_quotes_nonblocking(items: list[dict]) -> None:
    """批量尽力落库（失败不影响主流程）。"""
    if not isinstance(items, list) or not items:
        return

    async def _runner() -> None:
        for item in items:
            await _save_quote_best_effort(item)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        try:
            loop.create_task(_runner())
        except Exception as e:
            safe_stderr_print(f"[quote] create batch save task failed: {e}")
        return

    try:
        asyncio.run(_runner())
    except Exception as e:
        safe_stderr_print(f"[quote] batch save run failed: {e}")



def _get_minute_quote(code: str) -> dict:
    """获取分钟行情（用于实时价格）

    降级链: DataSource(TDX 分钟K) → AkShare
    """
    # 1. 优先 TDX 分钟K线
    if data_source.is_tdx_available():
        try:
            ds_results = data_source.get_kline(code, "1m", 240)
            if ds_results:
                sample_date = str(ds_results[0].get('date', ''))
                if len(sample_date) > 10:  # 确认是分钟数据
                    last_row = ds_results[-1]
                    first_row = ds_results[0]
                    price = safe_float(last_row.get("close"))
                    if price is not None:
                        day_high = max((safe_float(r.get("high")) or 0) for r in ds_results)
                        day_low = min((safe_float(r.get("low")) or float('inf')) for r in ds_results if safe_float(r.get("low")))
                        day_volume = sum((safe_int(r.get("volume")) or 0) for r in ds_results)
                        day_amount = sum((safe_float(r.get("amount")) or 0) for r in ds_results)
                        return {
                            "price": price,
                            "open": safe_float(first_row.get("open")),
                            "high": day_high if day_high > 0 else None,
                            "low": day_low if day_low < float('inf') else None,
                            "volume": day_volume,
                            "amount": day_amount,
                            "time": str(last_row.get("date", ""))[:19],
                        }
        except Exception:
            pass

    # 2. 降级 AkShare
    if ak is None:
        raise RuntimeError(f"无法获取 {code} 分钟行情 (TDX 不可用, akshare 未安装)")
    df = _run_with_retry(
        lambda: ak.stock_zh_a_hist_min_em(symbol=code, period="1", adjust=""),
        _QUOTE_TIMEOUTS,
    )
    if df is None or df.empty:
        raise RuntimeError(f"未获取到 {code} 分钟行情数据")
    last_row = df.iloc[-1]
    first_row = df.iloc[0]
    price = safe_float(last_row.get("收盘"))
    if price is None:
        raise RuntimeError(f"{code} 分钟行情缺少收盘价")
    day_open = safe_float(first_row.get("开盘"))
    day_high = safe_float(df["最高"].max()) if "最高" in df.columns else safe_float(last_row.get("最高"))
    day_low = safe_float(df["最低"].min()) if "最低" in df.columns else safe_float(last_row.get("最低"))
    if day_open is not None and day_open <= 0:
        day_open = None
    if day_high is not None and day_high <= 0:
        day_high = None
    if day_low is not None and day_low <= 0:
        day_low = None
    day_volume = safe_int(df["成交量"].sum()) if "成交量" in df.columns else safe_int(last_row.get("成交量"))
    day_amount = safe_float(df["成交额"].sum()) if "成交额" in df.columns else safe_float(last_row.get("成交额"))
    return {
        "price": price,
        "open": day_open,
        "high": day_high,
        "low": day_low,
        "volume": day_volume,
        "amount": day_amount,
        "time": str(last_row.get("时间", "")),
    }


def _get_daily_quote(code: str, name: str) -> Optional[dict]:
    """获取日K线行情（降级用）

    降级链: DataSource(TDX→Tushare) → AkShare
    """
    # 1. 优先 DataSource
    try:
        ds_results = data_source.get_kline(code, "daily", 2)
        if ds_results and len(ds_results) >= 1:
            row = ds_results[-1]
            prev_close = safe_float(ds_results[-2].get("close")) if len(ds_results) >= 2 else None
            price = safe_float(row.get("close"))
            if price is not None:
                change, change_pct = _calc_change(price, prev_close)
                return {
                    "code": code,
                    "name": name,
                    "price": price,
                    "change": change,
                    "changePercent": change_pct,
                    "open": safe_float(row.get("open")),
                    "high": safe_float(row.get("high")),
                    "low": safe_float(row.get("low")),
                    "preClose": prev_close,
                    "volume": safe_int(row.get("volume")),
                    "amount": safe_float(row.get("amount")),
                    "fallback": "daily_kline",
                }
    except Exception:
        pass

    # 2. 降级 AkShare
    if ak is None:
        return None
    try:
        df = _run_with_retry(
            lambda: ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq"),
            _QUOTE_TIMEOUTS,
        )
        if df is None or df.empty:
            return None
        row = df.iloc[-1]
        prev_close = safe_float(df.iloc[-2].get("收盘")) if len(df) >= 2 else None
        price = safe_float(row.get("收盘"))
        if price is None:
            return None
        return {
            "code": code,
            "name": name,
            "price": price,
            "change": safe_float(row.get("涨跌额")),
            "changePercent": safe_float(row.get("涨跌幅")),
            "open": safe_float(row.get("开盘")),
            "high": safe_float(row.get("最高")),
            "low": safe_float(row.get("最低")),
            "preClose": prev_close,
            "volume": safe_int(row.get("成交量")),
            "amount": safe_float(row.get("成交额")),
            "fallback": "daily_kline",
        }
    except Exception:
        return None


def _get_quote_sina(code: str) -> Optional[dict]:
    """Fallback: Get quote from Sina interface"""
    def _http_get_with_https_preferred(url_https: str, url_http: str, headers: dict, timeout: int = 5):
        try:
            resp = requests.get(url_https, headers=headers, timeout=timeout)
            return resp, "https"
        except Exception as https_err:
            safe_stderr_print(f"[quote] HTTPS fallback source failed, try HTTP: {https_err}")
            resp = requests.get(url_http, headers=headers, timeout=timeout)
            return resp, "http_fallback"

    try:
        symbol = normalize_code(code)
        if symbol.startswith("0") or symbol.startswith("3"):
            sina_code = f"sz{symbol}"
        else:
            sina_code = f"sh{symbol}"

        url_https = f"https://hq.sinajs.cn/list={sina_code}"
        url_http = f"http://hq.sinajs.cn/list={sina_code}"
        headers = {"Referer": "https://finance.sina.com.cn/"}
        resp, transport = _http_get_with_https_preferred(url_https, url_http, headers=headers, timeout=5)
        text = resp.text
        if "=" not in text or '="' not in text:
            return None

        content = text.split('="')[1].strip('";\n')
        if not content:
            return None

        parts = content.split(",")
        if len(parts) < 30:
            return None

        name = parts[0]
        open_ = safe_float(parts[1])
        pre_close = safe_float(parts[2])
        price = safe_float(parts[3])
        high = safe_float(parts[4])
        low = safe_float(parts[5])
        volume = safe_int(parts[8])
        amount = safe_float(parts[9])

        change = None
        change_pct = None
        if price is not None and pre_close is not None and pre_close > 0:
            change = price - pre_close
            change_pct = (change / pre_close) * 100

        return {
            "code": symbol,
            "name": name,
            "price": price,
            "change": change,
            "changePercent": change_pct,
            "open": open_,
            "high": high,
            "low": low,
            "preClose": pre_close,
            "volume": volume,
            "amount": amount,
            "source": f"sina_{transport}",
        }
    except Exception:
        return None


def _get_quote_tencent(code: str) -> Optional[dict]:
    """Fallback: Get quote from Tencent interface"""
    def _http_get_with_https_preferred(url_https: str, url_http: str, timeout: int = 5):
        try:
            resp = requests.get(url_https, timeout=timeout)
            return resp, "https"
        except Exception as https_err:
            safe_stderr_print(f"[quote] HTTPS fallback source failed, try HTTP: {https_err}")
            resp = requests.get(url_http, timeout=timeout)
            return resp, "http_fallback"

    try:
        symbol = normalize_code(code)
        if symbol.startswith("0") or symbol.startswith("3"):
            qt_code = f"sz{symbol}"
        else:
            qt_code = f"sh{symbol}"

        url_https = f"https://qt.gtimg.cn/q={qt_code}"
        url_http = f"http://qt.gtimg.cn/q={qt_code}"
        resp, transport = _http_get_with_https_preferred(url_https, url_http, timeout=5)
        text = resp.text
        if "=" not in text or '="' not in text:
            return None

        content = text.split('="')[1].strip('";\n')
        if not content:
            return None

        parts = content.split("~")
        if len(parts) < 40:
            return None

        name = parts[1]
        price = safe_float(parts[3])
        pre_close = safe_float(parts[4])
        open_ = safe_float(parts[5])
        high = safe_float(parts[33])
        low = safe_float(parts[34])
        volume = safe_int(parts[6])
        amount = safe_float(parts[37]) * 10000

        change = None
        change_pct = None
        if price is not None and pre_close is not None and pre_close > 0:
            change = price - pre_close
            change_pct = (change / pre_close) * 100

        return {
            "code": symbol,
            "name": name,
            "price": price,
            "change": change,
            "changePercent": change_pct,
            "open": open_,
            "high": high,
            "low": low,
            "preClose": pre_close,
            "volume": volume * 100,
            "amount": amount,
            "source": f"tencent_{transport}",
        }
    except Exception:
        return None


def _get_realtime_quote_akshare(code: str) -> Optional[dict]:
    """从 AkShare 获取实时行情（降级用）；仅在需补 name 时调 _get_name_map，避免先于 TDX 调 akshare。"""
    def _lazy_name():
        _m = _get_name_map()
        return _m.get(code, "")

    # 策略1: 优先尝试分钟K线（最快，单只股票）
    try:
        minute = _get_minute_quote(code)
        if minute and minute.get("price"):
            snapshot = _get_daily_snapshot(code)
            prev_close = snapshot.get("prev_close")
            change, change_pct = _calc_change(minute.get("price"), prev_close)
            return {
                "code": code,
                "name": _lazy_name(),
                "price": minute.get("price"),
                "change": change,
                "changePercent": change_pct,
                "open": _coalesce_price(minute.get("open"), snapshot.get("open")),
                "high": _coalesce_price(minute.get("high"), snapshot.get("high")),
                "low": _coalesce_price(minute.get("low"), snapshot.get("low")),
                "preClose": prev_close,
                "volume": minute.get("volume"),
                "amount": minute.get("amount"),
                "time": minute.get("time"),
                "source": "akshare_minute"
            }
    except (TimeoutError, RuntimeError, Exception) as e:
        safe_stderr_print(f"Minute quote failed for {code}: {e}")

    # 策略2: 尝试日K线（单只股票）
    try:
        daily = _get_daily_quote(code, _lazy_name())
        if daily and daily.get("price"):
            daily["source"] = "akshare_daily"
            return daily
    except (TimeoutError, RuntimeError, Exception) as e:
        safe_stderr_print(f"Daily quote failed for {code}: {e}")

    # 策略3: 降级到全市场数据（较慢，但数据完整）
    try:
        df, cached = _get_spot_indexed()
        if code in df.index:
            r = df.loc[code]
            spot_name = pick_value(r, ["名称", "股票简称"]) or _lazy_name()
            price = safe_float(pick_value(r, ["最新价", "最新", "现价"]))
            if price is not None:
                return {
                    "code": code,
                    "name": str(spot_name or ""),
                    "price": price,
                    "change": safe_float(pick_value(r, ["涨跌额", "涨跌"])),
                    "changePercent": safe_float(pick_value(r, ["涨跌幅", "涨幅"])),
                    "open": safe_float(pick_value(r, ["今开", "开盘"])),
                    "high": safe_float(pick_value(r, ["最高", "最高价"])),
                    "low": safe_float(pick_value(r, ["最低", "最低价"])),
                    "preClose": safe_float(pick_value(r, ["昨收", "昨收价"])),
                    "volume": safe_int(pick_value(r, ["成交量"])),
                    "amount": safe_float(pick_value(r, ["成交额"])),
                    "turnoverRate": safe_float(pick_value(r, ["换手率"])),
                    "source": "akshare_spot"
                }
    except (TimeoutError, RuntimeError, Exception) as e:
        safe_stderr_print(f"Spot market failed for {code}: {e}")

    return None


@cached(ttl=5.0)
def get_realtime_quote(stock_code: str) -> dict:
    """获取单只股票实时行情（优化版）

    数据源优先级: DataSource(TDX → Tushare) → AkShare(分钟K/日K/全市场) → Sina → Tencent
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
        - source (str): 数据来源标识，如 "tdx"/"akshare_minute"/"sina"/"tencent"

    Errors:
        - 所有数据源均不可用时返回 success=false

    Examples:
        get_realtime_quote("600519")
        get_realtime_quote("000001")
    """
    limiter = get_limiter("quote", max_calls=10, period=1.0)
    limiter.acquire()

    def _ok_with_trace(payload: dict, attempted_sources: list[str], source_chain: list[str], fallback_reason: Optional[str] = None) -> dict:
        """P2-1: 返回结构化降级信息，便于前端/调用方解释来源链路。"""
        result = ok(payload, cached=False)
        if isinstance(result.get("data"), dict):
            data = result["data"]
            data["attempted_sources"] = attempted_sources
            data["source_chain"] = source_chain
            data["fallback_used"] = len(source_chain) > 1 or (source_chain and source_chain[0] != "data_source")
            data["fallback_reason"] = fallback_reason
            data["data_timestamp"] = time.strftime("%Y-%m-%d")
            _save_quote_nonblocking(data)
        return result

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

        # 1. DataSource 优先：TDX → Tushare → akshare
        attempted_sources.append("data_source")
        try:
            res = data_source.get_realtime_quote(code)
            if res:
                validated = _as_plain_quote(validate_quote(res))
                return _ok_with_trace(validated, attempted_sources, source_chain=["data_source"])
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
            return _ok_with_trace(
                validated,
                attempted_sources,
                source_chain=["data_source", "akshare"],
                fallback_reason="; ".join(fallback_reason_parts) if fallback_reason_parts else "DataSource不可用，已降级至AkShare",
            )

        # 3. Try Sina
        attempted_sources.append("sina")
        safe_stderr_print(f"Trying Sina for {code}...")
        res = _get_quote_sina(code)
        if res:
            validated = _as_plain_quote(validate_quote(res))
            return _ok_with_trace(
                validated,
                attempted_sources,
                source_chain=["data_source", "akshare", "sina"],
                fallback_reason="; ".join(fallback_reason_parts) if fallback_reason_parts else "上游源不可用，已降级至Sina",
            )

        # 4. Try Tencent
        attempted_sources.append("tencent")
        safe_stderr_print(f"Sina failed for {code}, trying Tencent...")
        res = _get_quote_tencent(code)
        if res:
            validated = _as_plain_quote(validate_quote(res))
            return _ok_with_trace(
                validated,
                attempted_sources,
                source_chain=["data_source", "akshare", "sina", "tencent"],
                fallback_reason="; ".join(fallback_reason_parts) if fallback_reason_parts else "上游源不可用，已降级至Tencent",
            )

        attempted = " -> ".join(attempted_sources)
        reason = "; ".join(fallback_reason_parts) if fallback_reason_parts else "所有上游源均返回空数据"
        return fail(f"所有数据源均无法获取 {code} 的实时行情（attempted={attempted}, reason={reason}）")
    except Exception as e:
        return fail(e)


def get_batch_quotes(stock_codes: list[str]) -> dict:
    """批量获取股票实时行情

    数据源优先级（逐只）: DataSource(TDX → Tushare) → AkShare(分钟K/全市场) → Sina → Tencent → 日K
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
            # 1. 优先 DataSource：TDX → Tushare → akshare
            try:
                fallback = data_source.get_realtime_quote(code)
                if fallback and fallback.get("price") is not None:
                    if not fallback.get("name"):
                        if name_map is None:
                            name_map = _get_name_map()
                        fallback["name"] = name_map.get(code, "")
                    quotes.append(fallback)
                    continue
            except Exception:
                pass

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
                except Exception:
                    pass

            if spot_df is None:
                try:
                    spot_df, spot_cached = _get_spot_indexed()
                except Exception:
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
                except Exception:
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
            except Exception:
                pass
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
