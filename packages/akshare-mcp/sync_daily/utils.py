"""
同步脚本工具函数
"""

from datetime import date
from typing import Optional


def _to_ts_code(code: str) -> str:
    """股票代码 → Tushare 格式: 600519 → 600519.SH"""
    if code.startswith('6'):
        return f"{code}.SH"
    elif code.startswith(('0', '3')):
        return f"{code}.SZ"
    return f"{code}.BJ"


def _to_date(s: str) -> Optional[date]:
    """YYYYMMDD 字符串 → date 对象"""
    try:
        s = str(s).strip()
        if len(s) >= 8:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except (ValueError, TypeError):
        pass
    return None


def _safe_float(v) -> Optional[float]:
    try:
        if v is None or (hasattr(v, '__float__') and str(v) in ('nan', 'inf', '-inf')):
            return None
        f = float(v)
        if f != f:  # NaN check
            return None
        return f
    except (ValueError, TypeError):
        return None


def _safe_int(v) -> Optional[int]:
    f = _safe_float(v)
    return int(f) if f is not None else None
