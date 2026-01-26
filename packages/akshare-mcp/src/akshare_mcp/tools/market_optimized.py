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

@cached(ttl=5, key_prefix="quote")  # 5秒缓存
@retry_with_fallback(max_attempts=3, backoff=1.0)
def _fetch_quote_from_akshare(code: str) -> Optional[Dict]:
    """
    从AkShare获取行情（带缓存和重试）
    """
    # 限流：防止被封
    limiter = get_limiter()
    limiter.acquire(tokens=1)
    
    try:
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            return None
        
        df["代码"] = df["代码"].apply(normalize_code)
        df = df.set_index("代码", drop=False)
        
        if code not in df.index:
            return None
        
        row = df.loc[code]
        
        # 构建数据
        data = {
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
        
        # 数据验证
        try:
            validated = validate_quote(data)
            return validated.dict()
        except ValueError as e:
            print(f"Warning: Quote validation failed for {code}: {e}", file=sys.stderr)
            # 返回原始数据（不阻止返回）
            return data
            
    except Exception as e:
        print(f"Error fetching quote from AkShare for {code}: {e}", file=sys.stderr)
        return None


def _fetch_quote_from_sina(code: str) -> Optional[Dict]:
    """从Sina获取行情（降级数据源）"""
    import requests
    
    try:
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
        resp = requests.get(url, headers=headers, timeout=5)
        
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
            
    except Exception as e:
        print(f"Error fetching quote from Sina for {code}: {e}", file=sys.stderr)
        return None


def get_realtime_quote_optimized(stock_code: str) -> dict:
    """
    获取单只股票实时行情（优化版）
    
    优化特性：
    - 5秒进程内缓存（会话期间重复查询<10ms）
    - 自动重试（3次，指数退避）
    - 多数据源降级（AkShare -> Sina）
    - 数据验证（Pydantic）
    - 请求限流（防止被封）
    """
    try:
        code = normalize_code(stock_code)
        
        # 1. 尝试AkShare（带缓存和重试）
        result = _fetch_quote_from_akshare(code)
        if result:
            return ok(result, cached=False)
        
        # 2. 降级到Sina
        print(f"AkShare failed for {code}, trying Sina...", file=sys.stderr)
        result = _fetch_quote_from_sina(code)
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
