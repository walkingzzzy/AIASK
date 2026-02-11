"""TDX 公式系统 - 便捷指标函数 + MCP 注册"""

import logging

from ...data_source import data_source
from .api import calculate_indicator, screen_stocks, get_expert_signals, get_formula_data
from .utils import _ensure_formula_api


# ============== 便捷指标函数 ==============

def calculate_macd(stock_code: str, short: int = 12, long: int = 26, signal: int = 9,
                   period: str = "1d", count: int = 100) -> dict:
    """计算 MACD 指标"""
    return calculate_indicator(stock_code, "MACD", f"{short},{long},{signal}", period, count)


def calculate_kdj(stock_code: str, n: int = 9, m1: int = 3, m2: int = 3,
                  period: str = "1d", count: int = 100) -> dict:
    """计算 KDJ 指标"""
    return calculate_indicator(stock_code, "KDJ", f"{n},{m1},{m2}", period, count)


def calculate_rsi(stock_code: str, n1: int = 6, n2: int = 12, n3: int = 24,
                  period: str = "1d", count: int = 100) -> dict:
    """计算 RSI 指标"""
    return calculate_indicator(stock_code, "RSI", f"{n1},{n2},{n3}", period, count)


def calculate_boll(stock_code: str, n: int = 20, p: int = 2,
                   period: str = "1d", count: int = 100) -> dict:
    """计算 BOLL 布林带指标"""
    return calculate_indicator(stock_code, "BOLL", f"{n},{p}", period, count)


def calculate_trix(stock_code: str, n: int = 12,
                   period: str = "1d", count: int = 100) -> dict:
    """计算 TRIX 指标"""
    return calculate_indicator(stock_code, "TRIX", f"{n}", period, count)


def calculate_dma(stock_code: str, short: int = 10, long: int = 50, m: int = 10,
                  period: str = "1d", count: int = 100) -> dict:
    """计算 DMA 指标"""
    return calculate_indicator(stock_code, "DMA", f"{short},{long},{m}", period, count)


def calculate_expma(stock_code: str, n1: int = 12, n2: int = 50,
                    period: str = "1d", count: int = 100) -> dict:
    """计算 EXPMA 指标"""
    return calculate_indicator(stock_code, "EXPMA", f"{n1},{n2}", period, count)


def calculate_dmi(stock_code: str, n: int = 14, m: int = 6,
                  period: str = "1d", count: int = 100) -> dict:
    """计算 DMI 指标"""
    return calculate_indicator(stock_code, "DMI", f"{n},{m}", period, count)


def calculate_cr(stock_code: str, n: int = 26,
                 period: str = "1d", count: int = 100) -> dict:
    """计算 CR 指标"""
    return calculate_indicator(stock_code, "CR", f"{n}", period, count)


def calculate_vr(stock_code: str, n: int = 26,
                 period: str = "1d", count: int = 100) -> dict:
    """计算 VR 指标"""
    return calculate_indicator(stock_code, "VR", f"{n}", period, count)


# ============== MCP 注册函数 ==============


def _detect_formula_capability() -> tuple[bool, list[str]]:
    """启动阶段检测公式 API 能力。"""
    missing = []
    try:
        if not data_source.is_tdx_available():
            return False, ["tdx_not_available"]

        tq = data_source.get_tdxquant()
        if tq is None:
            return False, ["tdx_init_failed"]

        for method in ("formula_set_data_info", "formula_zb"):
            if not (hasattr(tq, method) and callable(getattr(tq, method, None))):
                missing.append(method)

        return len(missing) == 0, missing
    except Exception as e:
        logging.getLogger(__name__).warning("检测公式 API 能力失败: %s", e)
        return False, ["capability_check_exception"]

def register(mcp):
    """注册 TDX 公式计算工具到 MCP 服务"""
    formula_supported, missing_methods = _detect_formula_capability()
    tool_unavailable_tag = "" if formula_supported else " [当前环境不可用]"
    env_requirement = (
        "⚠️ 环境要求：需满足 hasattr(tq, 'formula_zb') 且 "
        "hasattr(tq, 'formula_set_data_info') 为 True。\n"
        "如当前环境不支持：\n"
        "- 方案A（推荐）：升级到支持公式 API 的 TdxQuant/tqcenter 版本；\n"
        "- 方案B：在通达信客户端公式管理器手动执行；\n"
        "- 方案C：继续使用本工具的 Python 回退（支持 MACD/KDJ/RSI/BOLL 等常用指标）。"
    )

    if not formula_supported:
        logging.getLogger(__name__).warning(
            "TDX 公式 API 当前环境不可用，仍注册工具并依赖回退。缺失能力: %s",
            ", ".join(missing_methods) if missing_methods else "unknown",
        )

    @mcp.tool()
    def tdx_calculate_indicator(
        stock_code: str,
        formula_name: str,
        formula_args: str = "",
        period: str = "1d",
        count: int = 100,
        dividend_type: int = 1,
    ) -> dict:
        f"""
        [TDX] 计算技术指标公式{tool_unavailable_tag}

        使用通达信公式系统计算技术指标，支持 MACD、KDJ、RSI、BOLL 等所有通达信内置指标。
        数据源优先级: TdxQuant 原生公式 → Python 回退计算

        {env_requirement}

        Args:
            stock_code (str, required): 股票代码，如 "600519"、"000001"
            formula_name (str, required): 公式名称，支持: MACD/KDJ/RSI/BOLL/TRIX/DMA/EXPMA/DMI/CR/VR/MA/EMA
            formula_args (str, optional): 公式参数，逗号分隔（如 "12,26,9"）
            period (str, optional): K线周期，可选 1m/5m/15m/30m/1h/1d/1w/1M，默认 "1d"
            count (int, optional): K线数量，最大 24000，-1 获取全部，默认 100
            dividend_type (int, optional): 复权类型，0不复权/1前复权/2后复权，默认 1

        Returns:
            dict: {"success": bool, "data": dict, "message": str, "stock_code": str,
                   "formula_name": str, "formula_args": str, "period": str, "count": int, "source": str}
            data 结构因指标而异:
            - MACD: {"DIF": list, "DEA": list, "MACD": list}
            - KDJ: {"K": list, "D": list, "J": list}
            - RSI: {"RSI1": list, "RSI2": list, "RSI3": list}
            - BOLL: {"BOLL": list, "UB": list, "LB": list}
            source: "tdxquant" 或 "python_fallback"

        Errors:
            - Python 回退不支持的指标返回错误并列出支持列表
            - K线数据不可用时返回 success=false

        Examples:
            - MACD: formula_name="MACD", formula_args="12,26,9"
            - KDJ: formula_name="KDJ", formula_args="9,3,3"
            - RSI: formula_name="RSI", formula_args="6,12,24"
            - BOLL: formula_name="BOLL", formula_args="20,2"
        """
        return calculate_indicator(stock_code, formula_name, formula_args, period, count, dividend_type)

    # 注意：函数体内 f-string 不是 Python 的编译期 docstring，
    # 这里显式回填 __doc__，确保 MCP 框架与回归脚本能读取到动态标记。
    tdx_calculate_indicator.__doc__ = f"""
        [TDX] 计算技术指标公式{tool_unavailable_tag}

        使用通达信公式系统计算技术指标，支持 MACD、KDJ、RSI、BOLL 等所有通达信内置指标。
        数据源优先级: TdxQuant 原生公式 → Python 回退计算

        {env_requirement}
    """

    @mcp.tool()
    def tdx_screen_stocks(
        formula_name: str,
        formula_args: str = "",
        stock_pool: list = None,
        period: str = "1d",
        count: int = 100,
    ) -> dict:
        """
        [TDX] 条件选股

        使用通达信条件选股公式筛选符合条件的股票。
        数据源优先级: TdxQuant 原生选股 → Python 选股引擎（降级）

        Args:
            formula_name (str, required): 选股公式名称，支持: UPN/放量上攻/均线多头/MACD金叉/KDJ金叉/涨停/连板 等
            formula_args (str, optional): 公式参数（如 "3" 表示连续3天）
            stock_pool (list[str], optional): 股票池列表，为空则使用沪深300成分股
            period (str, optional): K线周期，默认 "1d"
            count (int, optional): K线数量，默认 100

        Returns:
            dict: {"success": bool, "matched": list[dict], "total": int, "matched_count": int,
                   "message": str, "formula_name": str, "source": str}
            matched 每项含: stock_code(str), signal_name(str), signal_value(float)

        Errors:
            - 不支持的选股条件返回错误并列出可用条件

        Examples:
            tdx_screen_stocks("MACD金叉")
            tdx_screen_stocks("UPN", formula_args="3", stock_pool=["600519","000001","000858"])
        """
        return screen_stocks(formula_name, formula_args, stock_pool, period, count)

    @mcp.tool()
    def tdx_get_expert_signals(
        stock_code: str,
        formula_name: str,
        formula_args: str = "",
        period: str = "1d",
        count: int = 100,
        dividend_type: int = 1,
    ) -> dict:
        """
        [TDX] 获取专家系统信号

        使用通达信专家系统公式获取买卖信号。
        数据源优先级: TdxQuant 原生专家系统 → Python 回退

        Args:
            stock_code (str, required): 股票代码，如 "600519"
            formula_name (str, required): 专家系统公式名称，支持: MACD/KDJ/RSI/BOLL/CCI
            formula_args (str, optional): 公式参数（如 "12"）
            period (str, optional): K线周期，默认 "1d"
            count (int, optional): K线数量，默认 100
            dividend_type (int, optional): 复权类型，默认 1

        Returns:
            dict: {"success": bool, "signals": dict, "latest_signal": dict|null, "message": str, "source": str}
            signals: {"ENTERLONG": list, "EXITLONG": list}（买入/卖出信号序列，null 表示无信号）
            latest_signal: {"type": "buy"|"sell", "signal": str, "value": float} 或 null

        Errors:
            - Python 回退不支持的公式返回错误并列出支持列表

        Examples:
            tdx_get_expert_signals("600519", "MACD")
            tdx_get_expert_signals("000001", "KDJ", formula_args="9,3,3")
        """
        return get_expert_signals(stock_code, formula_name, formula_args, period, count, dividend_type)

    @mcp.tool()
    def tdx_calculate_macd(
        stock_code: str, short: int = 12, long: int = 26, signal: int = 9,
        period: str = "1d", count: int = 100,
    ) -> dict:
        """
        [TDX] 计算 MACD 指标

        快捷计算 MACD 指标，返回 DIF、DEA、MACD 柱状图数据。

        Args:
            stock_code (str, required): 股票代码
            short (int, optional): 短期EMA周期，默认 12
            long (int, optional): 长期EMA周期，默认 26
            signal (int, optional): 信号线周期，默认 9
            period (str, optional): K线周期，默认 "1d"
            count (int, optional): K线数量，默认 100

        Returns:
            dict: {"success": bool, "data": {"DIF": list, "DEA": list, "MACD": list}, "source": str}

        Examples:
            tdx_calculate_macd("600519")
            tdx_calculate_macd("000001", short=10, long=20, signal=5)
        """
        return calculate_macd(stock_code, short, long, signal, period, count)

    @mcp.tool()
    def tdx_calculate_kdj(
        stock_code: str, n: int = 9, m1: int = 3, m2: int = 3,
        period: str = "1d", count: int = 100,
    ) -> dict:
        """
        [TDX] 计算 KDJ 指标

        快捷计算 KDJ 随机指标，返回 K、D、J 值。

        Args:
            stock_code (str, required): 股票代码
            n (int, optional): RSV周期，默认 9
            m1 (int, optional): K值平滑周期，默认 3
            m2 (int, optional): D值平滑周期，默认 3
            period (str, optional): K线周期，默认 "1d"
            count (int, optional): K线数量，默认 100

        Returns:
            dict: {"success": bool, "data": {"K": list, "D": list, "J": list}, "source": str}

        Examples:
            tdx_calculate_kdj("600519")
            tdx_calculate_kdj("000001", n=14)
        """
        return calculate_kdj(stock_code, n, m1, m2, period, count)

    @mcp.tool()
    def tdx_calculate_rsi(
        stock_code: str, n1: int = 6, n2: int = 12, n3: int = 24,
        period: str = "1d", count: int = 100,
    ) -> dict:
        """
        [TDX] 计算 RSI 指标

        快捷计算 RSI 相对强弱指标。

        Args:
            stock_code (str, required): 股票代码
            n1 (int, optional): 短期RSI周期，默认 6
            n2 (int, optional): 中期RSI周期，默认 12
            n3 (int, optional): 长期RSI周期，默认 24
            period (str, optional): K线周期，默认 "1d"
            count (int, optional): K线数量，默认 100

        Returns:
            dict: {"success": bool, "data": {"RSI1": list, "RSI2": list, "RSI3": list}, "source": str}

        Examples:
            tdx_calculate_rsi("600519")
            tdx_calculate_rsi("000001", n1=14)
        """
        return calculate_rsi(stock_code, n1, n2, n3, period, count)

    @mcp.tool()
    def tdx_calculate_boll(
        stock_code: str, n: int = 20, p: int = 2,
        period: str = "1d", count: int = 100,
    ) -> dict:
        """
        [TDX] 计算 BOLL 布林带指标

        快捷计算布林带指标，返回上轨、中轨、下轨数据。

        Args:
            stock_code (str, required): 股票代码
            n (int, optional): 移动平均周期，默认 20
            p (int, optional): 标准差倍数，默认 2
            period (str, optional): K线周期，默认 "1d"
            count (int, optional): K线数量，默认 100

        Returns:
            dict: {"success": bool, "data": {"BOLL": list, "UB": list, "LB": list}, "source": str}

        Examples:
            tdx_calculate_boll("600519")
            tdx_calculate_boll("000001", n=26, p=2)
        """
        return calculate_boll(stock_code, n, p, period, count)

    @mcp.tool()
    def tdx_calculate_trix(
        stock_code: str, n: int = 12,
        period: str = "1d", count: int = 100,
    ) -> dict:
        """
        [TDX] 计算 TRIX 指标

        Args:
            stock_code (str, required): 股票代码
            n (int, optional): TRIX 周期，默认 12
            period (str, optional): K线周期，默认 "1d"
            count (int, optional): K线数量，默认 100

        Returns:
            dict: {"success": bool, "data": dict, "source": str}

        Examples:
            tdx_calculate_trix("600519")
            tdx_calculate_trix("000001", n=20)
        """
        return calculate_trix(stock_code, n, period, count)

    @mcp.tool()
    def tdx_calculate_dma(
        stock_code: str, short: int = 10, long: int = 50, m: int = 10,
        period: str = "1d", count: int = 100,
    ) -> dict:
        """
        [TDX] 计算 DMA 指标

        Args:
            stock_code (str, required): 股票代码
            short (int, optional): 短期周期，默认 10
            long (int, optional): 长期周期，默认 50
            m (int, optional): 平滑周期，默认 10
            period (str, optional): K线周期，默认 "1d"
            count (int, optional): K线数量，默认 100

        Returns:
            dict: {"success": bool, "data": dict, "source": str}

        Examples:
            tdx_calculate_dma("600519")
        """
        return calculate_dma(stock_code, short, long, m, period, count)

    @mcp.tool()
    def tdx_calculate_expma(
        stock_code: str, n1: int = 12, n2: int = 50,
        period: str = "1d", count: int = 100,
    ) -> dict:
        """
        [TDX] 计算 EXPMA 指标

        Args:
            stock_code (str, required): 股票代码
            n1 (int, optional): 短期周期，默认 12
            n2 (int, optional): 长期周期，默认 50
            period (str, optional): K线周期，默认 "1d"
            count (int, optional): K线数量，默认 100

        Returns:
            dict: {"success": bool, "data": dict, "source": str}

        Examples:
            tdx_calculate_expma("600519")
        """
        return calculate_expma(stock_code, n1, n2, period, count)

    @mcp.tool()
    def tdx_calculate_dmi(
        stock_code: str, n: int = 14, m: int = 6,
        period: str = "1d", count: int = 100,
    ) -> dict:
        """
        [TDX] 计算 DMI 指标

        Args:
            stock_code (str, required): 股票代码
            n (int, optional): DMI 周期，默认 14
            m (int, optional): 平滑周期，默认 6
            period (str, optional): K线周期，默认 "1d"
            count (int, optional): K线数量，默认 100

        Returns:
            dict: {"success": bool, "data": dict, "source": str}

        Examples:
            tdx_calculate_dmi("600519")
        """
        return calculate_dmi(stock_code, n, m, period, count)

    @mcp.tool()
    def tdx_calculate_cr(
        stock_code: str, n: int = 26,
        period: str = "1d", count: int = 100,
    ) -> dict:
        """
        [TDX] 计算 CR 指标

        Args:
            stock_code (str, required): 股票代码
            n (int, optional): CR 周期，默认 26
            period (str, optional): K线周期，默认 "1d"
            count (int, optional): K线数量，默认 100

        Returns:
            dict: {"success": bool, "data": dict, "source": str}

        Examples:
            tdx_calculate_cr("600519")
        """
        return calculate_cr(stock_code, n, period, count)

    @mcp.tool()
    def tdx_calculate_vr(
        stock_code: str, n: int = 26,
        period: str = "1d", count: int = 100,
    ) -> dict:
        """
        [TDX] 计算 VR 指标

        Args:
            stock_code (str, required): 股票代码
            n (int, optional): VR 周期，默认 26
            period (str, optional): K线周期，默认 "1d"
            count (int, optional): K线数量，默认 100

        Returns:
            dict: {"success": bool, "data": dict, "source": str}

        Examples:
            tdx_calculate_vr("600519")
        """
        return calculate_vr(stock_code, n, period, count)

    @mcp.tool()
    def tdx_get_formula_data(
        stock_code: str,
        period: str = "1d",
        count: int = 100,
        dividend_type: int = 1,
    ) -> dict:
        f"""
        [TDX] 获取公式系统K线数据{tool_unavailable_tag}

        获取与公式计算相同的基础K线数据，可用于自定义分析。
        数据源优先级: TdxQuant 原生 → Python 回退

        {env_requirement}

        Args:
            stock_code (str, required): 股票代码，如 "600519"
            period (str, optional): K线周期，可选 1m/5m/15m/30m/1h/1d/1w/1M，默认 "1d"
            count (int, optional): K线数量，最大 24000，-1 获取全部，默认 100
            dividend_type (int, optional): 复权类型，0不复权/1前复权/2后复权，默认 1

        Returns:
            dict: {"success": bool, "data": list[dict], "count": int, "message": str, "source": str}
            每条K线包含: Date(str), Open(float), High(float), Low(float), Close(float), Volume(int), Amount(float)

        Errors:
            - K线数据不可用时返回 success=false

        Examples:
            tdx_get_formula_data("600519")
            tdx_get_formula_data("000001", period="1w", count=50)
        """
        return get_formula_data(stock_code, period, count, dividend_type)

    tdx_get_formula_data.__doc__ = f"""
        [TDX] 获取公式系统K线数据{tool_unavailable_tag}

        获取与公式计算相同的基础K线数据，可用于自定义分析。
        数据源优先级: TdxQuant 原生 → Python 回退

        {env_requirement}
    """
