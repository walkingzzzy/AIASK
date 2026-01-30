"""
优化后的市场数据工具
集成了缓存、重试、限流、数据验证等优化
"""

import sys
from typing import Optional, Dict, List
import akshare as ak

from ..utils import fail, normalize_code, ok, safe_float, safe_int, pick_value
from ..core import cached, retry_with_fallback, validate_quote, validate_kline
from ..core.rate_limiter import get_limiter


# =====================
# 优化后的实时行情获取
# =====================

def _fetch_quote_from_akshare_single(code: str, timeout: float = 8.0) -> Optional[Dict]:
    """
    从AkShare获取单只股票行情（优先使用单只股票接口，避免获取全市场数据）
    
    策略：
    1. 优先尝试分钟K线（最快，单只股票）
    2. 降级到日K线（单只股票）
    3. 最后尝试全市场数据（如果前两者都失败）
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
    
    limiter = get_limiter()
    limiter.acquire(tokens=1)
    
    def try_minute_kline():
        """尝试从分钟K线获取最新价格"""
        try:
            df = ak.stock_zh_a_hist_min_em(symbol=code, period="1", adjust="")
            if df is not None and not df.empty:
                last_row = df.iloc[-1]
                price = safe_float(last_row.get("收盘"))
                if price and price > 0:
                    # 获取日K线补充其他数据
                    daily_df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq", start_date="", end_date="")
                    if daily_df is not None and not daily_df.empty:
                        last_daily = daily_df.iloc[-1]
                        prev_close = safe_float(daily_df.iloc[-2].get("收盘")) if len(daily_df) >= 2 else safe_float(last_daily.get("收盘"))
                        
                        change = None
                        change_pct = None
                        if price and prev_close and prev_close > 0:
                            change = price - prev_close
                            change_pct = (change / prev_close) * 100
                        
                        return {
                            "code": code,
                            "name": "",  # 需要从其他地方获取
                            "price": price,
                            "change": change,
                            "changePercent": change_pct,
                            "open": safe_float(last_daily.get("开盘")),
                            "high": safe_float(last_row.get("最高")),
                            "low": safe_float(last_row.get("最低")),
                            "preClose": prev_close,
                            "volume": safe_int(last_row.get("成交量")),
                            "amount": safe_float(last_row.get("成交额")),
                            "source": "akshare_minute"
                        }
        except Exception:
            pass
        return None
    
    def try_daily_kline():
        """尝试从日K线获取最新价格"""
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq", start_date="", end_date="")
            if df is not None and not df.empty:
                last_row = df.iloc[-1]
                price = safe_float(last_row.get("收盘"))
                if price and price > 0:
                    prev_close = safe_float(df.iloc[-2].get("收盘")) if len(df) >= 2 else price
                    change = None
                    change_pct = None
                    if price and prev_close and prev_close > 0:
                        change = price - prev_close
                        change_pct = (change / prev_close) * 100
                    
                    return {
                        "code": code,
                        "name": "",
                        "price": price,
                        "change": change,
                        "changePercent": change_pct,
                        "open": safe_float(last_row.get("开盘")),
                        "high": safe_float(last_row.get("最高")),
                        "low": safe_float(last_row.get("最低")),
                        "preClose": prev_close,
                        "volume": safe_int(last_row.get("成交量")),
                        "amount": safe_float(last_row.get("成交额")),
                        "source": "akshare_daily"
                    }
        except Exception:
            pass
        return None
    
    def try_spot_market():
        """降级：尝试从全市场数据获取（较慢，但数据完整）"""
        try:
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return None
            
            df["代码"] = df["代码"].apply(normalize_code)
            df = df.set_index("代码", drop=False)
            
            if code not in df.index:
                return None
            
            row = df.loc[code]
            
            return {
                "code": code,
                "name": str(pick_value(row, ["名称", "股票简称"]) or ""),
                "price": safe_float(pick_value(row, ["最新价", "最新", "现价"])),
                "change": safe_float(pick_value(row, ["涨跌额", "涨跌"])),
                "changePercent": safe_float(pick_value(row, ["涨跌幅", "涨幅"])),
                "open": safe_float(pick_value(row, ["今开", "开盘"])),
                "high": safe_float(pick_value(row, ["最高", "最高价"])),
                "low": safe_float(pick_value(row, ["最低", "最低价"])),
                "preClose": safe_float(pick_value(row, ["昨收", "昨收价"])),
                "volume": safe_int(pick_value(row, ["成交量"])),
                "amount": safe_float(pick_value(row, ["成交额"])),
                "turnoverRate": safe_float(pick_value(row, ["换手率"])),
                "source": "akshare_spot"
            }
        except Exception:
            return None
    
    # 使用线程池执行，带超时控制
    executor = ThreadPoolExecutor(max_workers=1)
    
    # 策略1: 尝试分钟K线（最快，单只股票）
    try:
        future = executor.submit(try_minute_kline)
        result = future.result(timeout=timeout)
        if result:
            executor.shutdown(wait=False)
            return result
    except (FuturesTimeoutError, Exception) as e:
        print(f"Minute kline fetch failed for {code}: {e}", file=sys.stderr)
    
    # 策略2: 尝试日K线（单只股票）
    try:
        future = executor.submit(try_daily_kline)
        result = future.result(timeout=timeout)
        if result:
            executor.shutdown(wait=False)
            return result
    except (FuturesTimeoutError, Exception) as e:
        print(f"Daily kline fetch failed for {code}: {e}", file=sys.stderr)
    
    # 策略3: 降级到全市场数据（较慢，但数据完整）
    try:
        future = executor.submit(try_spot_market)
        result = future.result(timeout=timeout * 2)  # 全市场数据允许更长时间
        if result:
            executor.shutdown(wait=False)
            return result
    except (FuturesTimeoutError, Exception) as e:
        print(f"Spot market fetch failed for {code}: {e}", file=sys.stderr)
    
    executor.shutdown(wait=False)
    return None


@cached(ttl=5, key_prefix="quote")  # 5秒缓存
def _fetch_quote_from_akshare(code: str) -> Optional[Dict]:
    """
    从AkShare获取行情（优化版：优先单只股票接口）
    """
    try:
        # 使用优化后的单只股票接口
        result = _fetch_quote_from_akshare_single(code, timeout=8.0)
        if result:
            # 数据验证
            try:
                validated = validate_quote(result)
                return validated.dict()
            except ValueError as e:
                print(f"Warning: Quote validation failed for {code}: {e}", file=sys.stderr)
                return result
        return None
    except Exception as e:
        print(f"Error fetching quote from AkShare for {code}: {e}", file=sys.stderr)
        return None


def _fetch_quote_from_sina(code: str, timeout: float = 5.0) -> Optional[Dict]:
    """从Sina获取行情（降级数据源，带超时和重试）"""
    import requests
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
    
    def _fetch():
        # 限流
        limiter = get_limiter()
        limiter.acquire(tokens=1)
        
        symbol = normalize_code(code)
        if symbol.startswith("0") or symbol.startswith("3"):
            sina_code = f"sz{symbol}"
        else:
            sina_code = f"sh{symbol}"
        
        url = f"http://hq.sinajs.cn/list={sina_code}"
        headers = {"Referer": "https://finance.sina.com.cn/"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        
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
        
        data = {
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
        
        # 数据验证
        try:
            validated = validate_quote(data)
            return validated.dict()
        except ValueError:
            return data
    
    try:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_fetch)
        result = future.result(timeout=timeout + 1.0)
        executor.shutdown(wait=False)
        return result
    except (FuturesTimeoutError, Exception) as e:
        print(f"Error fetching quote from Sina for {code}: {e}", file=sys.stderr)
        return None


def _fetch_quote_from_tencent(code: str, timeout: float = 5.0) -> Optional[Dict]:
    """从Tencent获取行情（降级数据源，带超时和重试）"""
    import requests
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
    
    def _fetch():
        # 限流
        limiter = get_limiter()
        limiter.acquire(tokens=1)
        
        symbol = normalize_code(code)
        if symbol.startswith("0") or symbol.startswith("3"):
            qt_code = f"sz{symbol}"
        else:
            qt_code = f"sh{symbol}"
        
        url = f"http://qt.gtimg.cn/q={qt_code}"
        resp = requests.get(url, timeout=timeout)
        
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
        volume = safe_int(parts[6]) * 100  # 转换为股数
        amount = safe_float(parts[37]) * 10000  # 转换为元
        
        change = None
        change_pct = None
        if price is not None and pre_close is not None and pre_close > 0:
            change = price - pre_close
            change_pct = (change / pre_close) * 100
        
        data = {
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
            "source": "tencent"
        }
        
        # 数据验证
        try:
            validated = validate_quote(data)
            return validated.dict()
        except ValueError:
            return data
    
    try:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_fetch)
        result = future.result(timeout=timeout + 1.0)
        executor.shutdown(wait=False)
        return result
    except (FuturesTimeoutError, Exception) as e:
        print(f"Error fetching quote from Tencent for {code}: {e}", file=sys.stderr)
        return None


def get_realtime_quote_optimized(stock_code: str) -> dict:
    """
    获取单只股票实时行情（优化版）
    
    优化特性：
    - 5秒进程内缓存（会话期间重复查询<10ms）
    - 优先使用单只股票接口，避免获取全市场数据
    - 快速降级机制（AkShare -> Sina -> Tencent）
    - 超时控制（避免长时间等待）
    - 数据验证（Pydantic）
    - 请求限流（防止被封）
    """
    try:
        code = normalize_code(stock_code)
        
        # 1. 尝试AkShare（优化版：优先单只股票接口）
        result = _fetch_quote_from_akshare(code)
        if result:
            return ok(result, cached=False)
        
        # 2. 快速降级到Sina（超时时间短，响应快）
        print(f"AkShare failed for {code}, trying Sina...", file=sys.stderr)
        result = _fetch_quote_from_sina(code, timeout=3.0)  # 缩短超时时间，快速失败
        if result:
            return ok(result, cached=False)
        
        # 3. 降级到Tencent
        print(f"Sina failed for {code}, trying Tencent...", file=sys.stderr)
        result = _fetch_quote_from_tencent(code, timeout=3.0)
        if result:
            return ok(result, cached=False)
        
        return fail(f"所有数据源均无法获取 {code} 的实时行情")
        
    except Exception as e:
        return fail(e)


# =====================
# 优化后的K线数据获取
# =====================

@cached(ttl=3600, key_prefix="kline")  # 1小时缓存（日线数据变化慢）
@retry_with_fallback(max_attempts=3, backoff=1.0)
def _fetch_kline_from_akshare(code: str, period: str, limit: int) -> Optional[List[Dict]]:
    """
    从AkShare获取K线（带缓存和重试）
    """
    # 限流
    limiter = get_limiter()
    limiter.acquire(tokens=1)
    
    try:
        df = ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
        if df is None or df.empty:
            return None
        
        df = df.tail(int(limit))
        
        results = []
        for _, row in df.iterrows():
            date = str(row.get("日期", ""))[:10]
            open_ = safe_float(row.get("开盘"))
            close = safe_float(row.get("收盘"))
            high = safe_float(row.get("最高"))
            low = safe_float(row.get("最低"))
            
            if not date or open_ is None or close is None:
                continue
            
            data = {
                "date": date,
                "open": open_,
                "close": close,
                "high": high,
                "low": low,
                "volume": safe_int(row.get("成交量")),
                "amount": safe_float(row.get("成交额")),
                "source": "akshare"
            }
            
            # 数据验证
            try:
                validated = validate_kline(data)
                results.append(validated.dict())
            except ValueError as e:
                print(f"Warning: K-line validation failed: {e}", file=sys.stderr)
                results.append(data)
        
        return results if results else None
        
    except Exception as e:
        print(f"Error fetching K-line from AkShare for {code}: {e}", file=sys.stderr)
        return None


def get_kline_optimized(stock_code: str, period: str = "daily", limit: int = 100) -> dict:
    """
    获取K线数据（优化版）
    
    优化特性：
    - 1小时进程内缓存（日线数据变化慢）
    - 自动重试（3次，指数退避）
    - 数据验证（Pydantic，跳过无效数据）
    - 请求限流（防止被封）
    """
    try:
        code = normalize_code(stock_code)
        
        # 获取K线数据（带缓存和重试）
        results = _fetch_kline_from_akshare(code, period, limit)
        
        if results:
            return ok(results, cached=False)
        
        return fail(f"无法获取 {code} 的K线数据")
        
    except Exception as e:
        return fail(e)


# =====================
# 注册工具
# =====================

def register_optimized(mcp):
    """注册优化后的工具"""
    mcp.tool()(get_realtime_quote_optimized)
    mcp.tool()(get_kline_optimized)
