"""TDX 公式系统 - 内部辅助函数"""

import logging
from typing import Optional
from ...utils import normalize_code

logger = logging.getLogger(__name__)


def _convert_to_tdx_code(code: str) -> str:
    """转换股票代码为 TdxQuant 格式: 600519 → 600519.SH, 510050 → 510050.SH"""
    code = normalize_code(code)
    # 6xx = 沪市主板, 5xx = 沪市ETF/基金
    if code.startswith(("6", "5")):
        return f"{code}.SH"
    elif code.startswith(("0", "3", "1")):
        # 0xx/3xx = 深市股票, 1xx = 深市ETF/可转债
        return f"{code}.SZ"
    else:
        return f"{code}.BJ"


def _convert_period(period: str) -> str:
    """转换周期格式为 TDX 格式"""
    period_map = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "60m": "1h", "1h": "1h", "1d": "1d", "daily": "1d",
        "1w": "1w", "weekly": "1w", "1M": "1M", "monthly": "1M"
    }
    return period_map.get(period, "1d")


def _ensure_formula_api(tq) -> Optional[dict]:
    """
    兼容不同版本 tqcenter/TdxQuant 的公式 API。
    当前线上失败点：部分版本没有 formula_set_data_info 方法，导致所有公式工具直接报错。
    """
    required = ["formula_set_data_info", "formula_zb", "formula_xg", "formula_exp", "formula_get_data"]
    missing = [m for m in required if not hasattr(tq, m)]
    if missing:
        return {
            "success": False,
            "data": {},
            "message": (
                "当前 TdxQuant/tqcenter 版本不支持公式接口，缺少方法: "
                + ", ".join(missing)
                + "。请升级 tqcenter/TdxQuant 或使用不依赖公式接口的技术指标工具（akshare/tdx_calculate_* 以外的工具）。"
            ),
        }
    return None
