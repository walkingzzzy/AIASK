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
    校验公式API能力，并在缺失时返回结构化引导信息。

    核心必需方法（主链路）:
    - formula_set_data_info
    - formula_zb
    """
    core_required = ["formula_set_data_info", "formula_zb"]
    optional_related = ["formula_xg", "formula_exp", "formula_get_data", "formula_format_data", "formula_set_data"]

    missing_core = [m for m in core_required if not hasattr(tq, m)]
    missing_optional = [m for m in optional_related if not hasattr(tq, m)]

    if missing_core:
        return {
            "success": False,
            "capability": "formula_api_not_supported",
            "data": {
                "missing_core": missing_core,
                "missing_optional": missing_optional,
            },
            "message": (
                "当前 TdxQuant 版本不支持公式接口（缺少 "
                + ", ".join(missing_core)
                + " 等方法）。"
            ),
            "guidance": {
                "solutions": [
                    "方案A（推荐）：升级到支持公式 API 的 TdxQuant/tqcenter 版本",
                    "方案B：在通达信客户端中使用 公式管理器 手动计算（功能 -> 公式管理器 -> 技术指标公式）",
                ],
                "alternatives": [
                    "使用 akshare 原生技术指标工具（MA/EMA/RSI/MACD/KDJ 等）",
                    "使用 tdx_manage_subscription 进行实时行情订阅",
                    "使用 get_kline / get_minute_kline + 本地计算技术指标",
                ],
                "checks": [
                    "确认客户端已启动并登录",
                    "确认 initialize 成功且使用 PYPlugins/user/mcp_strategy.py",
                    "确认加载的是预期 tqcenter.py 路径",
                ],
            },
        }
    return None
