import json
import os
import sys
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from threading import Lock
from typing import Any, Optional
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

from ..utils import (
    fail,
    normalize_code,
    ok,
    pick_value,
    parse_date_input,
    parse_numeric,
    safe_float,
    safe_int,
)
from ..data_source import data_source
from ..baostock_api import baostock_client

# Import optimization modules
from ..core.cache_manager import cached, ProcessCache
from ..core.retry import retry_with_fallback, MultiSourceFetcher
from ..core.rate_limiter import get_limiter
from ..core.validators import validate_quote, validate_kline

# =====================
# 缓存（短 TTL）
# =====================

_SPOT_TTL_SECONDS = float(os.getenv("AKSHARE_SPOT_TTL_SECONDS", "2"))
_INDEX_SPOT_TTL_SECONDS = float(os.getenv("AKSHARE_INDEX_SPOT_TTL_SECONDS", "5"))
_STOCK_LIST_TTL_SECONDS = float(os.getenv("AKSHARE_STOCK_LIST_TTL_SECONDS", "86400"))
_STOCK_LIST_STALE_SECONDS = float(os.getenv("AKSHARE_STOCK_LIST_STALE_SECONDS", "604800"))
_SPOT_TIMEOUT_SECONDS = float(os.getenv("AKSHARE_SPOT_TIMEOUT_SECONDS", "45"))
_INDEX_TIMEOUT_SECONDS = float(os.getenv("AKSHARE_INDEX_TIMEOUT_SECONDS", "45"))
_SPOT_STALE_SECONDS = float(os.getenv("AKSHARE_SPOT_STALE_SECONDS", "30"))
_INDEX_STALE_SECONDS = float(os.getenv("AKSHARE_INDEX_STALE_SECONDS", "60"))
_RETRY_SLEEP_SECONDS = float(os.getenv("AKSHARE_RETRY_SLEEP_SECONDS", "1.0"))


def _parse_timeout_list(env_key: str, default: list[float]) -> list[float]:
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return default
    parts = [p for p in re.split(r"[,\s]+", raw) if p]
    timeouts: list[float] = []
    for part in parts:
        try:
            timeouts.append(float(part))
        except ValueError:
            continue
    return timeouts or default


_QUOTE_TIMEOUTS = _parse_timeout_list("AKSHARE_QUOTE_TIMEOUTS", [15.0, 45.0])
_KLINE_TIMEOUTS = _parse_timeout_list("AKSHARE_KLINE_TIMEOUTS", [20.0, 60.0])
_MINUTE_BATCH_LIMIT = int(os.getenv("AKSHARE_MINUTE_BATCH_LIMIT", "12"))
_BATCH_FALLBACK_LIMIT = int(os.getenv("AKSHARE_BATCH_FALLBACK_LIMIT", "60"))


_spot_lock = Lock()
_spot_cache: dict[str, Any] = {"indexed": None, "ts": 0.0}

_index_lock = Lock()
_index_cache: dict[str, Any] = {"indexed": None, "ts": 0.0}

_list_lock = Lock()
_list_cache: dict[str, Any] = {"data": None, "ts": 0.0}

_spot_executor = ThreadPoolExecutor(max_workers=2)


def _run_with_timeout(fn, timeout: float) -> Any:
    """带超时的函数执行，捕获所有异常防止进程崩溃"""
    future = _spot_executor.submit(fn)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        future.cancel()
        raise TimeoutError(f"AKShare 请求超时（>{timeout}s）")
    except Exception as e:
        # 捕获所有异常，防止进程崩溃
        raise RuntimeError(f"AKShare 请求失败: {e}")


def _run_with_retry(fn, timeouts: list[float]) -> Any:
    """带重试的函数执行，增强稳定性"""
    last_error: Optional[Exception] = None
    for timeout in timeouts:
        try:
            return _run_with_timeout(fn, timeout)
        except Exception as exc:
            last_error = exc
            print(f"[akshare-mcp] 请求失败 (timeout={timeout}s): {exc}", file=sys.stderr)
            if _RETRY_SLEEP_SECONDS > 0:
                time.sleep(_RETRY_SLEEP_SECONDS)
    if last_error:
        raise last_error
    raise RuntimeError("AKShare 请求失败")


def _get_spot_indexed() -> tuple[pd.DataFrame, bool]:
    now = time.time()
    with _spot_lock:
        indexed = _spot_cache.get("indexed")
        ts = float(_spot_cache.get("ts") or 0.0)
        if indexed is not None and (now - ts) < _SPOT_TTL_SECONDS:
            return indexed, True

        df = None
        try:
            df = _run_with_timeout(ak.stock_zh_a_spot_em, _SPOT_TIMEOUT_SECONDS)
        except Exception:
            df = None
        if df is None or df.empty:
            try:
                df = _run_with_timeout(ak.stock_zh_a_spot, _SPOT_TIMEOUT_SECONDS)
            except Exception as e:
                # 超时/失败时允许短时间使用过期缓存
                stale_indexed = _spot_cache.get("indexed")
                stale_ts = float(_spot_cache.get("ts") or 0.0)
                if stale_indexed is not None and (now - stale_ts) < _SPOT_STALE_SECONDS:
                    return stale_indexed, True
                raise e
        if df is None or df.empty:
            raise RuntimeError("未获取到A股全市场行情（stock_zh_a_spot_em 为空）")

        if "代码" not in df.columns:
            raise RuntimeError("A股行情缺少“代码”列，无法索引")

        df["代码"] = df["代码"].apply(normalize_code)
        indexed = df.set_index("代码", drop=False)

        _spot_cache["indexed"] = indexed
        _spot_cache["ts"] = now
        return indexed, False


def _get_index_spot_indexed() -> tuple[pd.DataFrame, bool]:
    now = time.time()
    with _index_lock:
        indexed = _index_cache.get("indexed")
        ts = float(_index_cache.get("ts") or 0.0)
        if indexed is not None and (now - ts) < _INDEX_SPOT_TTL_SECONDS:
            return indexed, True

        try:
            df = _run_with_timeout(ak.stock_zh_index_spot_em, _INDEX_TIMEOUT_SECONDS)
        except Exception:
            df = None

        if df is None or df.empty:
            try:
                df = ak.stock_zh_index_spot_sina()
            except Exception as e:
                stale_indexed = _index_cache.get("indexed")
                stale_ts = float(_index_cache.get("ts") or 0.0)
                if stale_indexed is not None and (now - stale_ts) < _INDEX_STALE_SECONDS:
                    return stale_indexed, True
                raise e
        if df is None or df.empty:
            raise RuntimeError("未获取到指数行情（stock_zh_index_spot_em 为空）")

        if "代码" not in df.columns:
            raise RuntimeError("指数行情缺少“代码”列，无法索引")

        df["代码"] = df["代码"].astype(str).str.zfill(6)
        indexed = df.set_index("代码", drop=False)

        _index_cache["indexed"] = indexed
        _index_cache["ts"] = now
        return indexed, False


def _get_stock_list_cached() -> tuple[list[dict], bool]:
    now = time.time()
    with _list_lock:
        data = _list_cache.get("data")
        ts = float(_list_cache.get("ts") or 0.0)
        if data is not None and (now - ts) < _STOCK_LIST_TTL_SECONDS:
            return data, True

        df = None
        try:
            df = ak.stock_info_a_code_name()
        except Exception:
            df = None
        if df is None or df.empty:
            # 允许短期使用过期缓存，避免实时行情接口整体不可用
            if data is not None and (now - ts) < _STOCK_LIST_STALE_SECONDS:
                return data, True
            raise RuntimeError("未获取到A股股票列表（stock_info_a_code_name 为空）")

        records = df.to_dict(orient="records")
        _list_cache["data"] = records
        _list_cache["ts"] = now
        return records, False


def _get_name_map() -> dict[str, str]:
    try:
        data, _ = _get_stock_list_cached()
    except Exception:
        return {}
    name_map: dict[str, str] = {}
    for row in data or []:
        code = normalize_code(row.get("code") or row.get("代码") or row.get("股票代码") or "")
        name = row.get("name") or row.get("名称") or row.get("股票简称")
        if code and name:
            name_map[code] = str(name).strip()
    return name_map


def _get_daily_snapshot(code: str) -> dict[str, Optional[float]]:
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


def _coalesce_price(value: Optional[float], fallback: Optional[float]) -> Optional[float]:
    if value is None or value == 0:
        return fallback
    return value
    
def _calc_change(price: Optional[float], prev_close: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    if price is None or prev_close is None or prev_close == 0:
        return None, None
    change = price - prev_close
    return change, (change / prev_close) * 100


def _get_minute_quote(code: str) -> dict:
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
        raise RuntimeError(f"{code} 分钟行情缺少“收盘价”")
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



import requests

def _get_quote_sina(code: str) -> Optional[dict]:
    """Fallback: Get quote from Sina interface"""
    try:
        # Sina code format: sh600519, sz000001
        symbol = normalize_code(code)
        if symbol.startswith("0") or symbol.startswith("3"):
            sina_code = f"sz{symbol}"
        else:
            sina_code = f"sh{symbol}"
            
        url = f"http://hq.sinajs.cn/list={sina_code}"
        headers = {"Referer": "https://finance.sina.com.cn/"}
        resp = requests.get(url, headers=headers, timeout=5)
        # var hq_str_sh600519="贵州茅台,1555.00,1558.05,1550.00,1566.00,1545.00,1549.95,1550.00,2400000,3700000000,..."
        text = resp.text
        if "=" not in text or '="' not in text:
            return None
            
        content = text.split('="')[1].strip('";\n')
        if not content:
            return None
            
        parts = content.split(",")
        if len(parts) < 30:
            return None
            
        # 0: name, 1: open, 2: pre_close, 3: price, 4: high, 5: low
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
            "source": "sina"
        }
    except Exception:
        return None

def _get_quote_tencent(code: str) -> Optional[dict]:
    """Fallback: Get quote from Tencent interface"""
    try:
        # Tencent code format: sh600519, sz000001
        symbol = normalize_code(code)
        if symbol.startswith("0") or symbol.startswith("3"):
            qt_code = f"sz{symbol}"
        else:
            qt_code = f"sh{symbol}"
            
        url = f"http://qt.gtimg.cn/q={qt_code}"
        resp = requests.get(url, timeout=5)
        # v_sh600519="1~贵州茅台~600519~1555.00~1558.05~1550.00~1555.00~..."
        text = resp.text
        if "=" not in text or '="' not in text:
            return None
            
        content = text.split('="')[1].strip('";\n')
        if not content:
            return None
            
        parts = content.split("~")
        if len(parts) < 40:
            return None
            
        # 1: name, 2: code, 3: price, 4: pre_close, 5: open, 33: high, 34: low
        name = parts[1]
        price = safe_float(parts[3])
        pre_close = safe_float(parts[4])
        open_ = safe_float(parts[5])
        high = safe_float(parts[33])
        low = safe_float(parts[34])
        volume = safe_int(parts[6]) # hand
        amount = safe_float(parts[37]) * 10000 # wan
        
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
            "volume": volume * 100, # convert hand to share
            "amount": amount,
            "source": "tencent"
        }
    except Exception:
        return None

def _build_exchange_code(code: str) -> str:
    symbol = normalize_code(code)
    if symbol.startswith(("0", "3")):
        return f"sz{symbol}"
    return f"sh{symbol}"

def _get_order_book_sina_direct(code: str) -> Optional[dict]:
    """Sina 直连：五档盘口"""
    try:
        symbol = normalize_code(code)
        sina_code = _build_exchange_code(symbol)
        url = f"http://hq.sinajs.cn/list={sina_code}"
        headers = {"Referer": "https://finance.sina.com.cn/"}
        resp = requests.get(url, headers=headers, timeout=5)
        text = resp.text
        if "=" not in text or '="' not in text:
            return None

        content = text.split('="', 1)[1].strip('";\n')
        if not content:
            return None

        parts = content.split(",")
        if len(parts) < 30:
            return None

        bids: list[dict] = []
        asks: list[dict] = []
        bid_volume_idx = [10, 12, 14, 16, 18]
        bid_price_idx = [11, 13, 15, 17, 19]
        ask_volume_idx = [20, 22, 24, 26, 28]
        ask_price_idx = [21, 23, 25, 27, 29]

        for i in range(5):
            bid_price = parse_numeric(parts[bid_price_idx[i]]) if bid_price_idx[i] < len(parts) else None
            bid_volume = parse_numeric(parts[bid_volume_idx[i]]) if bid_volume_idx[i] < len(parts) else None
            if bid_price is not None or bid_volume is not None:
                bids.append({"price": bid_price or 0, "volume": int(bid_volume or 0)})

            ask_price = parse_numeric(parts[ask_price_idx[i]]) if ask_price_idx[i] < len(parts) else None
            ask_volume = parse_numeric(parts[ask_volume_idx[i]]) if ask_volume_idx[i] < len(parts) else None
            if ask_price is not None or ask_volume is not None:
                asks.append({"price": ask_price or 0, "volume": int(ask_volume or 0)})

        if not bids and not asks:
            return None

        return {
            "code": symbol,
            "bids": bids,
            "asks": asks,
            "timestamp": int(time.time() * 1000),
        }
    except Exception:
        return None

def _get_order_book_tencent_direct(code: str) -> Optional[dict]:
    """Tencent 直连：五档盘口"""
    try:
        symbol = normalize_code(code)
        qt_code = _build_exchange_code(symbol)
        url = f"http://qt.gtimg.cn/q={qt_code}"
        resp = requests.get(url, timeout=5)
        text = resp.text
        if "=" not in text or '="' not in text:
            return None

        content = text.split('="', 1)[1].strip('";\n')
        if not content:
            return None

        parts = content.split("~")
        if len(parts) < 29:
            return None

        bids: list[dict] = []
        asks: list[dict] = []
        bid_price_idx = [9, 11, 13, 15, 17]
        bid_volume_idx = [10, 12, 14, 16, 18]
        ask_price_idx = [19, 21, 23, 25, 27]
        ask_volume_idx = [20, 22, 24, 26, 28]

        for i in range(5):
            bid_price = parse_numeric(parts[bid_price_idx[i]]) if bid_price_idx[i] < len(parts) else None
            bid_volume = parse_numeric(parts[bid_volume_idx[i]]) if bid_volume_idx[i] < len(parts) else None
            if bid_price is not None or bid_volume is not None:
                bids.append({"price": bid_price or 0, "volume": int(bid_volume or 0)})

            ask_price = parse_numeric(parts[ask_price_idx[i]]) if ask_price_idx[i] < len(parts) else None
            ask_volume = parse_numeric(parts[ask_volume_idx[i]]) if ask_volume_idx[i] < len(parts) else None
            if ask_price is not None or ask_volume is not None:
                asks.append({"price": ask_price or 0, "volume": int(ask_volume or 0)})

        if not bids and not asks:
            return None

        return {
            "code": symbol,
            "bids": bids,
            "asks": asks,
            "timestamp": int(time.time() * 1000),
        }
    except Exception:
        return None

def _get_trade_details_tencent_direct(code: str, limit: int) -> Optional[list[dict]]:
    """Tencent 直连：成交明细"""
    try:
        symbol = normalize_code(code)
        qt_code = _build_exchange_code(symbol)
        url = f"http://stock.gtimg.cn/data/index.php?appn=detail&action=data&c={qt_code}&p=1"
        resp = requests.get(url, timeout=5)
        text = resp.text
        if '"' not in text:
            return None

        start = text.find('"')
        end = text.rfind('"')
        if start < 0 or end <= start:
            return None

        content = text[start + 1:end]
        if not content:
            return None

        items = [item for item in content.split("|") if item]
        if not items:
            return None

        details: list[dict] = []
        for item in items[-limit:]:
            parts = item.split("/")
            if len(parts) < 7:
                continue
            time_str = parts[1]
            price = parse_numeric(parts[2]) or 0
            volume = int(parse_numeric(parts[4]) or 0)
            direction_raw = str(parts[6]).strip().upper()
            direction = "neutral"
            if direction_raw == "B":
                direction = "buy"
            elif direction_raw == "S":
                direction = "sell"
            details.append(
                {
                    "time": time_str,
                    "price": price,
                    "volume": volume,
                    "direction": direction,
                }
            )

        return details if details else None
    except Exception:
        return None

@cached(ttl=5.0)  # 5s cache for real-time quotes
def get_realtime_quote(stock_code: str) -> dict:
    """
    获取单只股票实时行情
    """
    # Rate limiting
    limiter = get_limiter("quote", max_calls=10, period=1.0)
    limiter.acquire()
    
    try:
        code = normalize_code(stock_code)

        # 1. Try AkShare (EastMoney)
        try:
            res = _get_realtime_quote_akshare(code)
        except Exception:
            res = None
        if res:
            # Validate data
            validated = validate_quote(res)
            return ok(validated, cached=False)

        # 1.5 Try DataSource (Tushare / eFinance)
        print(f"AkShare quote failed for {code}, trying DataSource (Tushare/eFinance)...", file=sys.stderr)
        res = data_source.get_realtime_quote(code)
        if res:
            validated = validate_quote(res)
            return ok(validated, cached=False)

        print(f"AkShare quote failed for {code}, trying Sina...", file=sys.stderr)

        # 2. Try Sina
        res = _get_quote_sina(code)
        if res:
            validated = validate_quote(res)
            return ok(validated, cached=False)

        print(f"Sina quote failed for {code}, trying Tencent...", file=sys.stderr)

        # 3. Try Tencent
        res = _get_quote_tencent(code)
        if res:
            validated = validate_quote(res)
            return ok(validated, cached=False)

        return fail(f"所有数据源均无法获取 {code} 的实时行情")
    except Exception as e:
        return fail(e)

def _get_realtime_quote_akshare(code: str) -> Optional[dict]:
    name_map = _get_name_map()
    name = name_map.get(code, "")
    
    # ... (Original logic extracted to helper) ...
    # Simplified adaptation of original logic:
    
    minute_error: Optional[Exception] = None
    minute_data = None
    
    try:
        minute = _get_minute_quote(code)
        snapshot = _get_daily_snapshot(code)
        prev_close = snapshot.get("prev_close")
        change, change_pct = _calc_change(minute.get("price"), prev_close)
        minute_data = {
            "code": code,
            "name": name,
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
        return minute_data
    except Exception:
        pass

    try:
        df, cached = _get_spot_indexed()
        if code in df.index:
            r = df.loc[code]
            spot_name = pick_value(r, ["名称", "股票简称"]) or name
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
    except Exception:
        pass

    try:
        daily = _get_daily_quote(code, name)
        if daily:
            daily["source"] = "akshare_daily"
            return daily
    except Exception:
        pass
        
    return None


@cached(ttl=86400.0)  # 24h cache for stock list
def get_stock_list() -> dict:
    """获取A股股票列表，返回股票代码和名称"""
    try:
        data, cached = _get_stock_list_cached()
        return ok(data, cached=cached)
    except Exception as e:
        return fail(e)

def get_batch_quotes(stock_codes: list[str]) -> dict:
    """
    批量获取股票实时行情

    Args:
        stock_codes: 股票代码列表，如 ["000001", "600519"]
    """
    try:
        codes = [normalize_code(c) for c in stock_codes or []]
        if not codes:
            return fail("stock_codes 不能为空")

        name_map = _get_name_map()
        quotes: list[dict] = []
        missing: list[str] = []

        spot_df: Optional[pd.DataFrame] = None
        spot_cached = False
        spot_unavailable = False
        fallback_enabled = len(codes) <= _BATCH_FALLBACK_LIMIT

        use_minute = len(codes) <= _MINUTE_BATCH_LIMIT
        for code in codes:
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
                        }
                    )
                    continue

            if fallback_enabled:
                fallback = data_source.get_realtime_quote(code)
                if fallback:
                    if not fallback.get("name") and name:
                        fallback["name"] = name
                    quotes.append(fallback)
                    continue

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

        return ok(
            {
                "requested": codes,
                "found": len(quotes),
                "missing": missing,
                "quotes": quotes,
            },
            cached=spot_cached,
        )
    except Exception as e:
        return fail(e)


@cached(ttl=3600.0)  # 1h cache for historical K-line data
def get_kline(stock_code: str, period: str = "daily", limit: int = 100) -> dict:
    """
    获取K线数据
    """
    # Rate limiting
    limiter = get_limiter("kline", max_calls=5, period=1.0)
    limiter.acquire()
    
    code = normalize_code(stock_code)
    try:
        # 1. Try AkShare
        df = _run_with_retry(
            lambda: ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq"),
            _KLINE_TIMEOUTS,
        )
        if df is None or df.empty:
            raise RuntimeError("AkShare K-line empty")

        df = df.tail(int(limit))
        results = _process_kline_akshare(df, code)
        
        # Validate K-line data
        validated_results = [validate_kline(item) for item in results]
        return ok(validated_results)
    except Exception as e:
        print(f"AkShare K-line fetch failed for {code}: {e}", file=sys.stderr)
        
        # 1.5 Try DataSource (Tushare / Baostock / eFinance)
        print(f"Trying DataSource K-line fallback for {code}...", file=sys.stderr)
        ds_results = data_source.get_kline(code, period, limit)
        if ds_results:
            validated_results = [validate_kline(item) for item in ds_results]
            return ok(validated_results)

        # 2. Try Tencent daily history (limited range)
        if period == "daily":
            try:
                end_date = datetime.now().strftime("%Y%m%d")
                start_date = (datetime.now() - timedelta(days=int(limit) * 2 + 30)).strftime("%Y%m%d")
                market_prefix = "sh" if code.startswith("6") else "sz"
                symbol = f"{market_prefix}{code}"
                df_tx = ak.stock_zh_a_hist_tx(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    adjust="",
                    timeout=_KLINE_TIMEOUTS[-1] if _KLINE_TIMEOUTS else None,
                )
                if df_tx is not None and not df_tx.empty:
                    results = []
                    for _, row in df_tx.tail(int(limit)).iterrows():
                        results.append(
                            {
                                "date": str(row.get("date", ""))[:10],
                                "open": safe_float(row.get("open")),
                                "close": safe_float(row.get("close")),
                                "high": safe_float(row.get("high")),
                                "low": safe_float(row.get("low")),
                                "volume": safe_int(row.get("volume")),
                                "amount": safe_float(row.get("amount")),
                                "source": "tencent",
                            }
                        )
                    if results:
                        validated_results = [validate_kline(item) for item in results]
                        return ok(validated_results)
            except Exception as e_tx:
                print(f"Tencent K-line fetch failed for {code}: {e_tx}", file=sys.stderr)
        
        # 3. Fallback to Baostock
        # Only supports daily for now easily
        if period == "daily":
            try:
                end_date = datetime.now().strftime("%Y-%m-%d")
                # Estimate start date to cover 'limit'
                # 100 days ~ 5 months ~ 150 days buffer
                start_date = (datetime.now() - timedelta(days=limit * 1.5 + 30)).strftime("%Y-%m-%d")
                
                df_bs = baostock_client.get_history_k_data(code, start_date, end_date)
                if not df_bs.empty:
                    # Baostock returns strings, need conversion
                    results = []
                    # take last 'limit'
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
                    validated_results = [validate_kline(item) for item in results]
                    return ok(validated_results)
            except Exception as e2:
                print(f"Baostock K-line fetch failed for {code}: {e2}", file=sys.stderr)

        return fail(f"所有数据源均无法获取 {code} 的K线数据")

def _process_kline_akshare(df: pd.DataFrame, code: str) -> list[dict]:
    results = []
    for _, row in df.iterrows():
        date = str(row.get("日期", ""))[:10]
        open_ = safe_float(row.get("开盘"))
        close = safe_float(row.get("收盘"))
        high = safe_float(row.get("最高"))
        low = safe_float(row.get("最低"))
        if not date or open_ is None or close is None or high is None or low is None:
             continue # skip invalid rows instead of fail

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


def _parse_order_book_df(df: pd.DataFrame, code: str) -> Optional[dict]:
    if df is None or df.empty:
        return None

    bids: list[dict] = []
    asks: list[dict] = []

    if "item" in df.columns and "value" in df.columns:
        mapping = {str(row.get("item", "")).strip(): row.get("value") for _, row in df.iterrows()}

        def pick_price(keys: list[str]) -> Optional[float]:
            for key in keys:
                if key in mapping:
                    val = parse_numeric(mapping.get(key))
                    if val is not None:
                        return val
            return None

        def pick_volume(keys: list[str]) -> Optional[int]:
            for key in keys:
                if key in mapping:
                    val = parse_numeric(mapping.get(key))
                    if val is not None:
                        return int(val)
            return None

        for i in range(1, 6):
            price = pick_price([f"买{i}", f"买{i}价", f"买{i}价格"])
            volume = pick_volume([f"买{i}量", f"买{i}手", f"买{i}数量"])
            if price is not None or volume is not None:
                bids.append({"price": price or 0, "volume": volume or 0})

            price = pick_price([f"卖{i}", f"卖{i}价", f"卖{i}价格"])
            volume = pick_volume([f"卖{i}量", f"卖{i}手", f"卖{i}数量"])
            if price is not None or volume is not None:
                asks.append({"price": price or 0, "volume": volume or 0})
    else:
        row = df.iloc[0].to_dict()
        for i in range(1, 6):
            bid_price = parse_numeric(pick_value(pd.Series(row), [f"买{i}价", f"买{i}", f"bid{i}"]))
            bid_volume = parse_numeric(pick_value(pd.Series(row), [f"买{i}量", f"buy{i}"]))
            if bid_price is not None or bid_volume is not None:
                bids.append({"price": bid_price or 0, "volume": int(bid_volume or 0)})

            ask_price = parse_numeric(pick_value(pd.Series(row), [f"卖{i}价", f"卖{i}", f"ask{i}"]))
            ask_volume = parse_numeric(pick_value(pd.Series(row), [f"卖{i}量", f"sell{i}"]))
            if ask_price is not None or ask_volume is not None:
                asks.append({"price": ask_price or 0, "volume": int(ask_volume or 0)})

    if not bids and not asks:
        return None

    return {
        "code": code,
        "bids": bids,
        "asks": asks,
        "timestamp": int(time.time() * 1000),
    }


def _parse_trade_direction(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return "neutral"
    if "买" in text:
        return "buy"
    if "卖" in text:
        return "sell"
    return "neutral"


@cached(ttl=5.0)
def get_order_book(stock_code: str) -> dict:
    """
    获取五档盘口数据
    """
    limiter = get_limiter("quote", max_calls=10, period=1.0)
    limiter.acquire()

    code = normalize_code(stock_code)
    df = None
    for func_name, args in (
        ("stock_bid_ask_em", {"symbol": code}),
        ("stock_bid_ask_em", {"code": code}),
        ("stock_bid_ask_sina", {"symbol": code}),
    ):
        func = getattr(ak, func_name, None)
        if not func:
            continue
        try:
            df = func(**args)
        except Exception:
            df = None
        parsed = _parse_order_book_df(df, code)
        if parsed:
            return ok(parsed)

    for direct_fetch in (_get_order_book_sina_direct, _get_order_book_tencent_direct):
        parsed = direct_fetch(code)
        if parsed:
            return ok(parsed)

    return fail(f"未获取到 {code} 的盘口数据 (尝试源: AkShare, Sina, Tencent)")


@cached(ttl=5.0)
def get_trade_details(stock_code: str, limit: int = 20) -> dict:
    """
    获取成交明细
    """
    limiter = get_limiter("quote", max_calls=10, period=1.0)
    limiter.acquire()

    code = normalize_code(stock_code)
    limit = int(limit) if int(limit or 0) > 0 else 20
    df = None
    for func_name, args in (
        ("stock_intraday_em", {"symbol": code}),
        ("stock_intraday_sina", {"symbol": code}),
        ("stock_intraday_em", {"code": code}),
    ):
        func = getattr(ak, func_name, None)
        if not func:
            continue
        try:
            df = func(**args)
        except Exception:
            df = None
        if df is not None and not df.empty:
            break

    if df is None or df.empty:
        direct = _get_trade_details_tencent_direct(code, limit)
        if direct:
            return ok(direct)
        return fail(f"未获取到 {code} 的成交明细数据 (尝试源: AkShare, Tencent)")

    df = df.tail(limit)
    records: list[dict] = []
    for _, row in df.iterrows():
        records.append(
            {
                "time": str(pick_value(row, ["时间", "成交时间", "time"]) or ""),
                "price": parse_numeric(pick_value(row, ["成交价", "价格", "price"])) or 0,
                "volume": int(parse_numeric(pick_value(row, ["成交量", "数量", "volume"])) or 0),
                "direction": _parse_trade_direction(pick_value(row, ["买卖盘性质", "性质", "direction"])),
            }
        )

    return ok(records)


@cached(ttl=60.0)
def get_limit_up_stocks(date: str = "") -> dict:
    """
    获取涨停板数据
    """
    limiter = get_limiter("quote", max_calls=5, period=1.0)
    limiter.acquire()

    target_date = parse_date_input(date) if date else datetime.now().date()
    date_str = target_date.strftime("%Y%m%d") if target_date else ""
    func = getattr(ak, "stock_zt_pool_em", None)
    if not func:
        return fail("当前环境不支持涨停板数据接口")

    try:
        df = func(date=date_str) if date_str else func()
    except Exception as e:
        return fail(e)

    if df is None or df.empty:
        return ok([])

    results: list[dict] = []
    for _, row in df.iterrows():
        results.append(
            {
                "code": normalize_code(pick_value(row, ["代码", "股票代码", "code"]) or ""),
                "name": str(pick_value(row, ["名称", "股票简称", "name"]) or ""),
                "price": parse_numeric(pick_value(row, ["最新价", "收盘价", "price"])) or 0,
                "changePercent": parse_numeric(pick_value(row, ["涨跌幅", "涨幅", "changePercent"])) or 0,
                "limitUpPrice": parse_numeric(pick_value(row, ["涨停价", "涨停价格", "limit_up"])) or 0,
                "firstLimitTime": str(pick_value(row, ["首次封板时间", "首次封板", "first_time"]) or ""),
                "lastLimitTime": str(pick_value(row, ["最后封板时间", "最后封板", "last_time"]) or ""),
                "openTimes": int(parse_numeric(pick_value(row, ["开板次数", "开板", "open_times"])) or 0),
                "continuousDays": int(parse_numeric(pick_value(row, ["连板数", "连续涨停天数", "boards"])) or 0),
                "turnoverRate": parse_numeric(pick_value(row, ["换手率", "turnover"])) or 0,
                "marketCap": parse_numeric(pick_value(row, ["最新市值", "流通市值", "市值", "market_cap"])) or 0,
                "industry": str(pick_value(row, ["所属行业", "行业", "industry"]) or ""),
                "concept": str(pick_value(row, ["所属概念", "概念", "concept"]) or ""),
            }
        )

    return ok(results)


@cached(ttl=60.0)
def get_limit_up_statistics(date: str = "") -> dict:
    """
    获取涨停统计数据
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

    return ok(
        {
            "date": (parse_date_input(date) or datetime.now().date()).isoformat(),
            "totalLimitUp": total,
            "firstBoard": count_boards(1),
            "secondBoard": count_boards(2),
            "thirdBoard": count_boards(3),
            "higherBoard": higher,
            "failedBoard": failed,
            "limitDown": 0,
            "successRate": round(success_rate, 2),
        }
    )


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


@cached(ttl=60.0)  # 1分钟缓存，分钟级数据刷新更频繁
def get_minute_kline(stock_code: str, period: str = "5m", limit: int = 300) -> dict:
    """
    获取分钟K线数据
    """
    limiter = get_limiter("kline", max_calls=5, period=1.0)
    limiter.acquire()

    code = normalize_code(stock_code)
    minutes = _parse_minute_period(period)
    if minutes is None:
        return fail("period 必须为 1m/5m/15m/30m/60m")

    results = _get_minute_kline_from_akshare(code, minutes, limit)
    if not results:
        results = _get_minute_kline_from_sina(code, minutes, limit)

    if not results:
        return fail(f"所有数据源均无法获取 {code} 的{minutes}分钟K线数据")

    validated_results = [validate_kline(item) for item in results]
    return ok(validated_results)


def get_index_quote(index_code: str) -> dict:
    """
    获取指数实时行情

    Args:
        index_code: 指数代码，如 000001(上证指数)、399001(深证成指)、399006(创业板指)
    """
    try:
        code = normalize_code(index_code)
        df, cached = _get_index_spot_indexed()
        if code not in df.index:
            try:
                df = ak.stock_zh_index_spot_sina()
                if df is None or df.empty:
                    return fail(f"未找到指数 {code}")
                df["代码"] = df["代码"].apply(normalize_code)
                df = df.set_index("代码", drop=False)
                cached = False
            except Exception:
                return fail(f"未找到指数 {code}")
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
        return fail(e)


def register(mcp):
    mcp.tool()(get_stock_list)
    mcp.tool()(get_realtime_quote)
    mcp.tool()(get_batch_quotes)
    mcp.tool()(get_kline)
    mcp.tool()(get_minute_kline)
    mcp.tool()(get_order_book)
    mcp.tool()(get_trade_details)
    mcp.tool()(get_limit_up_stocks)
    mcp.tool()(get_limit_up_statistics)
    mcp.tool()(get_index_quote)
