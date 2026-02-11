"""TDX 公式系统 - 核心 API 函数

calculate_indicator / screen_stocks / get_expert_signals / get_formula_data
"""

import logging

from ...data_source import data_source
from .utils import _convert_to_tdx_code, _convert_period, _ensure_formula_api
from .fallback import (
    _fallback_calculate_indicator,
    _fallback_screen_stocks,
    _fallback_expert_signals,
    _get_kline_for_fallback,
)

logger = logging.getLogger(__name__)


def calculate_indicator(
    stock_code: str,
    formula_name: str,
    formula_args: str = "",
    period: str = "1d",
    count: int = 100,
    dividend_type: int = 1,
) -> dict:
    """
    计算技术指标公式（TDX 优先，自动回退到 Python）
    """
    if data_source.is_tdx_available():
        try:
            tq = data_source.get_tdxquant()
            if tq is not None:
                compat_err = _ensure_formula_api(tq)
                if compat_err is None:
                    tdx_code = _convert_to_tdx_code(stock_code)
                    tdx_period = _convert_period(period)

                    set_result = tq.formula_set_data_info(
                        stock_code=tdx_code, stock_period=tdx_period,
                        count=count, dividend_type=dividend_type,
                    )
                    if set_result.get("ErrorId") == "0":
                        result = tq.formula_zb(formula_name=formula_name, formula_arg=formula_args)
                        if result.get("ErrorId") == "0":
                            return {
                                "success": True,
                                "data": result.get("Data", {}),
                                "message": f"成功计算 {formula_name} 指标",
                                "stock_code": stock_code,
                                "formula_name": formula_name,
                                "formula_args": formula_args,
                                "period": period,
                                "count": count,
                                "source": "tdxquant",
                            }
        except Exception as e:
            logger.debug(f"TDX formula failed, falling back to Python: {e}")

    return _fallback_calculate_indicator(
        stock_code, formula_name, formula_args, period, count, dividend_type
    )


def screen_stocks(
    formula_name: str,
    formula_args: str = "",
    stock_pool: list = None,
    period: str = "1d",
    count: int = 100,
) -> dict:
    """
    条件选股公式（TDX 优先，自动回退到 Python 选股引擎）
    """
    if data_source.is_tdx_available():
        try:
            tq = data_source.get_tdxquant()
            if tq is not None:
                compat_err = _ensure_formula_api(tq)
                if compat_err is None:
                    pool = stock_pool
                    if pool is None or len(pool) == 0:
                        pool = data_source.get_stock_list_in_sector_tdxquant("沪深300")
                        if not pool:
                            pool = ["600519", "000001", "600036", "601318", "000858"]

                    tdx_period = _convert_period(period)
                    matched_stocks = []

                    for stock_code in pool:
                        try:
                            tdx_code = _convert_to_tdx_code(stock_code) if "." not in stock_code else stock_code
                            set_result = tq.formula_set_data_info(
                                stock_code=tdx_code, stock_period=tdx_period,
                                count=count, dividend_type=1,
                            )
                            if set_result.get("ErrorId") != "0":
                                continue

                            result = tq.formula_xg(formula_name=formula_name, formula_arg=formula_args)
                            if result.get("ErrorId") == "0":
                                data = result.get("Data", {})
                                for key, values in data.items():
                                    if values and len(values) > 0:
                                        last_value = values[-1]
                                        if last_value is not None and last_value != 0:
                                            matched_stocks.append({
                                                "stock_code": stock_code.split(".")[0] if "." in stock_code else stock_code,
                                                "tdx_code": tdx_code,
                                                "signal_name": key,
                                                "signal_value": last_value,
                                            })
                                            break
                        except Exception:
                            continue

                    return {
                        "success": True,
                        "matched": matched_stocks,
                        "total": len(pool),
                        "matched_count": len(matched_stocks),
                        "message": f"选股完成，共扫描 {len(pool)} 只股票，{len(matched_stocks)} 只符合条件",
                        "formula_name": formula_name,
                        "formula_args": formula_args,
                        "source": "tdxquant",
                    }
        except Exception as e:
            logger.debug(f"TDX screen_stocks failed, falling back to Python: {e}")

    return _fallback_screen_stocks(formula_name, formula_args, stock_pool, period, count)


def get_expert_signals(
    stock_code: str,
    formula_name: str,
    formula_args: str = "",
    period: str = "1d",
    count: int = 100,
    dividend_type: int = 1,
) -> dict:
    """
    获取专家系统信号（TDX 优先，自动回退到 Python）
    """
    if data_source.is_tdx_available():
        try:
            tq = data_source.get_tdxquant()
            if tq is not None:
                compat_err = _ensure_formula_api(tq)
                if compat_err is None:
                    tdx_code = _convert_to_tdx_code(stock_code)
                    tdx_period = _convert_period(period)

                    set_result = tq.formula_set_data_info(
                        stock_code=tdx_code, stock_period=tdx_period,
                        count=count, dividend_type=dividend_type,
                    )
                    if set_result.get("ErrorId") == "0":
                        result = tq.formula_exp(formula_name=formula_name, formula_arg=formula_args)
                        if result.get("ErrorId") == "0":
                            data = result.get("Data", {})
                            signals = {}
                            latest_signal = None

                            for key, values in data.items():
                                if values and len(values) > 0:
                                    signals[key] = values
                                    last_value = values[-1]
                                    if last_value is not None and last_value != 0:
                                        if "LONG" in key.upper() or "BUY" in key.upper():
                                            latest_signal = {"type": "buy", "signal": key, "value": last_value}
                                        elif "SHORT" in key.upper() or "SELL" in key.upper() or "EXIT" in key.upper():
                                            latest_signal = {"type": "sell", "signal": key, "value": last_value}

                            return {
                                "success": True,
                                "signals": signals,
                                "latest_signal": latest_signal,
                                "message": f"成功获取 {formula_name} 专家系统信号",
                                "stock_code": stock_code,
                                "formula_name": formula_name,
                                "formula_args": formula_args,
                                "period": period,
                                "source": "tdxquant",
                            }
        except Exception as e:
            logger.debug(f"TDX expert_signals failed, falling back to Python: {e}")

    return _fallback_expert_signals(stock_code, formula_name, formula_args, period, count)


def get_formula_data(
    stock_code: str,
    period: str = "1d",
    count: int = 100,
    dividend_type: int = 1,
) -> dict:
    """
    获取公式系统K线数据（TDX 优先，自动回退到 Python）
    """
    if data_source.is_tdx_available():
        try:
            tq = data_source.get_tdxquant()
            if tq is not None:
                compat_err = _ensure_formula_api(tq)
                if compat_err is None:
                    tdx_code = _convert_to_tdx_code(stock_code)
                    tdx_period = _convert_period(period)

                    set_result = tq.formula_set_data_info(
                        stock_code=tdx_code, stock_period=tdx_period,
                        count=count, dividend_type=dividend_type,
                    )
                    if set_result.get("ErrorId") == "0":
                        result = tq.formula_get_data()
                        if result.get("ErrorId") == "0":
                            kline_data = result.get("Data", [])
                            return {
                                "success": True,
                                "data": kline_data,
                                "code": result.get("Code", tdx_code),
                                "count": len(kline_data),
                                "message": f"成功获取 {len(kline_data)} 条K线数据",
                                "stock_code": stock_code,
                                "period": period,
                                "dividend_type": dividend_type,
                                "source": "tdxquant",
                            }
        except Exception as e:
            logger.debug(f"TDX formula_data failed, falling back to Python: {e}")

    # Python 回退
    klines = _get_kline_for_fallback(stock_code, period, count)
    if not klines:
        return {"success": False, "data": [], "message": f"无法获取 {stock_code} 的K线数据"}

    klines = sorted(klines, key=lambda x: x.get("date", ""))
    formatted = [
        {
            "Date": k.get("date", ""),
            "Open": k.get("open", 0),
            "High": k.get("high", 0),
            "Low": k.get("low", 0),
            "Close": k.get("close", 0),
            "Volume": k.get("volume", 0),
            "Amount": k.get("amount", 0),
        }
        for k in klines
    ]

    return {
        "success": True,
        "data": formatted,
        "count": len(formatted),
        "message": f"成功获取 {len(formatted)} 条K线数据（Python 回退）",
        "stock_code": stock_code,
        "period": period,
        "dividend_type": dividend_type,
        "source": "python_fallback",
    }
