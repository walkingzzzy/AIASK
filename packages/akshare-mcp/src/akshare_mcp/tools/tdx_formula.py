"""
TdxQuant 公式计算系统模块

提供通达信公式计算功能：
- 技术指标公式 (MACD, KDJ, RSI, BOLL 等)
- 条件选股公式
- 专家系统公式

Phase 1 实现 - MCP 服务开发方案
Phase 2 增强 - Pure Python 回退 + 增强选股引擎
"""

import sys
import logging
from typing import Optional
from ..data_source import data_source
from ..utils import normalize_code
from ..services.technical_analysis import TechnicalAnalysis

logger = logging.getLogger(__name__)

_ta = TechnicalAnalysis()


# ============== 内部辅助函数 ==============

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


# ============== Python 回退函数 ==============

def _get_kline_for_fallback(stock_code: str, period: str, count: int) -> list:
    """获取 K 线数据用于公式回退计算

    对于周线/月线，先获取足够的日线数据再聚合，确保非日线周期也能正确计算。
    """
    code = normalize_code(stock_code)

    # 方式1: TDX get_market_data (非公式API，原生支持多周期)
    if data_source.is_tdx_available():
        try:
            result = data_source._get_kline_tdxquant(code, period, count)
            if result:
                return result
        except Exception:
            pass

    # 方式2: 多源回退链（仅支持日线），对周/月线需要聚合
    need_aggregate = period in ('1w', 'weekly', '1M', 'monthly')
    if need_aggregate:
        # 周线需要 count*7 天日线，月线需要 count*31 天日线
        multiplier = 7 if period in ('1w', 'weekly') else 31
        daily_count = min(count * multiplier, 2000)
        daily_klines = data_source.get_kline(code, 'daily', daily_count)
        if not daily_klines:
            return []
        return _aggregate_klines(daily_klines, period)

    p = 'daily' if period in ('1d', 'daily') else period
    return data_source.get_kline(code, p, count)


def _aggregate_klines(daily_klines: list, period: str) -> list:
    """将日线数据聚合为周线或月线"""
    from datetime import datetime

    if not daily_klines:
        return []

    # 确保时间升序
    sorted_klines = sorted(daily_klines, key=lambda x: str(x.get('date', '')))

    def _get_group_key(date_str: str) -> str:
        try:
            dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
        except (ValueError, TypeError):
            return date_str
        if period in ('1w', 'weekly'):
            # ISO 周: 年-周号
            iso = dt.isocalendar()
            return f"{iso[0]}-W{iso[1]:02d}"
        else:
            # 月线: 年-月
            return f"{dt.year}-{dt.month:02d}"

    groups: dict[str, list] = {}
    for k in sorted_klines:
        date_str = str(k.get('date', ''))
        key = _get_group_key(date_str)
        groups.setdefault(key, []).append(k)

    result = []
    for bars in groups.values():
        if not bars:
            continue
        result.append({
            'date': str(bars[-1].get('date', '')),  # 取该周期最后一天
            'open': bars[0].get('open'),
            'close': bars[-1].get('close'),
            'high': max((b.get('high') or 0) for b in bars),
            'low': min((b.get('low') or float('inf')) for b in bars),
            'volume': sum((b.get('volume') or 0) for b in bars),
            'amount': sum((b.get('amount') or 0) for b in bars),
            'source': bars[0].get('source', 'aggregated'),
        })

    return result


def _fallback_calculate_indicator(
    stock_code: str, formula_name: str, formula_args: str,
    period: str, count: int, dividend_type: int
) -> dict:
    """Pure Python 回退：当 TDX 公式 API 不可用时用 Python 计算技术指标"""
    klines = _get_kline_for_fallback(stock_code, period, count)
    if not klines:
        return {"success": False, "data": {},
                "message": f"无法获取 {stock_code} 的K线数据"}

    # 确保时间升序
    klines = sorted(klines, key=lambda x: x.get('date', ''))

    closes = [k['close'] for k in klines if k.get('close')]
    highs = [k['high'] for k in klines if k.get('high')]
    lows = [k['low'] for k in klines if k.get('low')]
    volumes = [k.get('volume', 0) or 0 for k in klines]

    if not closes:
        return {"success": False, "data": {}, "message": "K线数据为空"}

    # 解析参数
    args = [int(a.strip()) for a in formula_args.split(',') if a.strip()] if formula_args else []

    name = formula_name.upper()

    try:
        if name == 'MACD':
            fast, slow, sig = (args + [12, 26, 9])[:3]
            result = _ta.calculate_macd(closes, fast, slow, sig)
            data = {'DIF': result['macd'], 'DEA': result['signal'],
                    'MACD': [h * 2 for h in result['histogram']]}
        elif name == 'KDJ':
            n, m1, m2 = (args + [9, 3, 3])[:3]
            result = _ta.calculate_kdj(highs, lows, closes, n, m1, m2)
            data = {'K': result['k'], 'D': result['d'], 'J': result['j']}
        elif name == 'RSI':
            n1, n2, n3 = (args + [6, 12, 24])[:3]
            data = {
                'RSI1': _ta.calculate_rsi_series(closes, n1),
                'RSI2': _ta.calculate_rsi_series(closes, n2),
                'RSI3': _ta.calculate_rsi_series(closes, n3),
            }
        elif name == 'BOLL':
            n, p = (args + [20, 2])[:2]
            result = _ta.calculate_bollinger_bands(closes, n, float(p))
            data = {'BOLL': result['middle'], 'UB': result['upper'], 'LB': result['lower']}
        elif name == 'TRIX':
            n = args[0] if args else 12
            data = _ta.calculate_trix(closes, n)
        elif name == 'DMA':
            short, long_p, m = (args + [10, 50, 10])[:3]
            data = _ta.calculate_dma_indicator(closes, short, long_p, m)
        elif name == 'EXPMA':
            n1, n2 = (args + [12, 50])[:2]
            data = _ta.calculate_expma(closes, n1, n2)
        elif name == 'DMI':
            n, m = (args + [14, 6])[:2]
            data = _ta.calculate_dmi(highs, lows, closes, n, m)
        elif name == 'CR':
            n = args[0] if args else 26
            data = _ta.calculate_cr_indicator(highs, lows, closes, n)
        elif name == 'VR':
            n = args[0] if args else 26
            data = _ta.calculate_vr_indicator(closes, volumes, n)
        elif name in ('MA', 'SMA'):
            n = args[0] if args else 20
            data = {'MA': _ta._calculate_sma_numpy(closes, n)}
        elif name == 'EMA':
            n = args[0] if args else 20
            data = {'EMA': _ta._calculate_ema_numpy(closes, n)}
        else:
            return {
                "success": False, "data": {},
                "message": f"Python 回退暂不支持指标: {formula_name}，"
                           f"支持: MACD/KDJ/RSI/BOLL/TRIX/DMA/EXPMA/DMI/CR/VR/MA/EMA"
            }
    except Exception as e:
        return {"success": False, "data": {}, "message": f"Python 回退计算异常: {e}"}

    return {
        "success": True,
        "data": data,
        "message": f"成功计算 {formula_name} 指标（Python 回退）",
        "stock_code": stock_code,
        "formula_name": formula_name,
        "formula_args": formula_args,
        "period": period,
        "count": len(closes),
        "source": "python_fallback"
    }


def _fallback_screen_stocks(formula_name, formula_args, stock_pool, period, count):
    """Python 回退选股 — 使用选股引擎"""
    from ..services.screen_engine import engine as screen_engine
    from ..services import screen_conditions  # noqa: F401 触发条件注册

    # 通达信公式名 → 内置条件ID 映射
    TDX_TO_CONDITION = {
        'UPN': 'upn', '连续上涨': 'upn',
        '放量上攻': 'volume_breakout', '均线多头': 'ma_bull',
        'MACD金叉': 'macd_golden_cross', 'KDJ金叉': 'kdj_golden_cross',
        'RSI超卖': 'rsi_oversold', 'BOLL突破': 'boll_breakout_upper',
        '涨停': 'limit_up', '连板': 'continuous_limit_up', '首板': 'first_limit_up',
        '底部反转': 'bottom_reversal', '强势突破': 'strong_breakout',
        '趋势跟踪': 'trend_following', 'VCP': 'vcp',
        'MACD死叉': 'macd_death_cross', 'KDJ死叉': 'kdj_death_cross',
        '大阳线': 'big_yang', '大阴线': 'big_yin',
        '跳空高开': 'gap_up', '红三兵': 'pattern_three_white',
        '早晨之星': 'pattern_morning_star', '超跌反弹': 'oversold_bounce',
        '动量爆发': 'momentum_burst', '背离买入': 'divergence_buy',
    }

    condition_id = TDX_TO_CONDITION.get(formula_name)
    if not condition_id:
        # 尝试直接作为条件ID
        lower_name = formula_name.lower()
        all_ids = set(screen_engine._conditions.keys()) | set(screen_engine._composites.keys())
        if lower_name in all_ids:
            condition_id = lower_name
        elif formula_name in all_ids:
            condition_id = formula_name
        else:
            available = list(TDX_TO_CONDITION.keys()) + list(screen_engine._composites.keys())
            return {
                "success": False, "matched": [], "total": 0,
                "message": f"不支持的选股条件: '{formula_name}'。"
                           f"支持的条件: {', '.join(available)}"
            }

    # 获取股票池
    if not stock_pool:
        stock_pool = _get_default_stock_pool()

    # 解析参数
    params = {}
    if formula_args:
        arg_parts = [a.strip() for a in formula_args.split(',') if a.strip()]
        if condition_id in ('upn', 'downn', 'continuous_limit_up') and arg_parts:
            params['n'] = int(arg_parts[0])

    # 批量获取K线并扫描
    stock_data = []
    for code in stock_pool:
        code = code.split('.')[0] if '.' in code else code
        code = normalize_code(code)
        klines = _get_kline_for_fallback(code, 'daily', 100)
        if klines:
            klines = sorted(klines, key=lambda x: x.get('date', ''))
            stock_data.append({'code': code, 'name': '', 'klines': klines})

    matched = screen_engine.scan(stock_data, [condition_id], "AND", params)

    return {
        "success": True,
        "matched": matched,
        "total": len(stock_pool),
        "matched_count": len(matched),
        "message": f"选股完成，共扫描 {len(stock_pool)} 只股票，"
                   f"{len(matched)} 只符合条件 [{formula_name}]",
        "formula_name": formula_name,
        "condition_id": condition_id,
        "source": "python_screen_engine"
    }


def _fallback_expert_signals(stock_code, formula_name, formula_args, period, count):
    """Python 回退专家系统信号"""
    klines = _get_kline_for_fallback(stock_code, period, count)
    if not klines:
        return {"success": False, "signals": {},
                "message": f"无法获取 {stock_code} 的K线数据"}

    klines = sorted(klines, key=lambda x: x.get('date', ''))
    closes = [k['close'] for k in klines if k.get('close')]
    highs = [k['high'] for k in klines if k.get('high')]
    lows = [k['low'] for k in klines if k.get('low')]

    if len(closes) < 2:
        return {"success": False, "signals": {}, "message": "K线数据不足"}

    name = formula_name.upper()
    buy_signals = [None] * len(closes)
    sell_signals = [None] * len(closes)

    try:
        if name == 'MACD':
            result = _ta.calculate_macd(closes)
            dif, dea = result['macd'], result['signal']
            for i in range(1, len(closes)):
                if dif[i - 1] <= dea[i - 1] and dif[i] > dea[i]:
                    buy_signals[i] = closes[i]
                elif dif[i - 1] >= dea[i - 1] and dif[i] < dea[i]:
                    sell_signals[i] = closes[i]
        elif name == 'KDJ':
            result = _ta.calculate_kdj(highs, lows, closes)
            k, d = result['k'], result['d']
            for i in range(1, len(closes)):
                if k[i - 1] <= d[i - 1] and k[i] > d[i]:
                    buy_signals[i] = closes[i]
                elif k[i - 1] >= d[i - 1] and k[i] < d[i]:
                    sell_signals[i] = closes[i]
        elif name == 'RSI':
            args = [int(a.strip()) for a in formula_args.split(',') if a.strip()] if formula_args else [14]
            rsi = _ta.calculate_rsi_series(closes, args[0])
            for i in range(1, len(closes)):
                if rsi[i - 1] >= 30 and rsi[i] < 30:
                    buy_signals[i] = closes[i]
                elif rsi[i - 1] <= 70 and rsi[i] > 70:
                    sell_signals[i] = closes[i]
        elif name == 'BOLL':
            result = _ta.calculate_bollinger_bands(closes)
            upper, lower = result['upper'], result['lower']
            for i in range(1, len(closes)):
                if closes[i - 1] >= lower[i - 1] and closes[i] < lower[i]:
                    buy_signals[i] = closes[i]
                elif closes[i - 1] <= upper[i - 1] and closes[i] > upper[i]:
                    sell_signals[i] = closes[i]
        elif name == 'CCI':
            cci = _ta.calculate_cci(highs, lows, closes)
            for i in range(1, len(closes)):
                if cci[i - 1] <= -100 and cci[i] > -100:
                    buy_signals[i] = closes[i]
                elif cci[i - 1] >= 100 and cci[i] < 100:
                    sell_signals[i] = closes[i]
        else:
            return {
                "success": False, "signals": {},
                "message": f"Python 回退暂不支持专家系统: {formula_name}，"
                           f"支持: MACD/KDJ/RSI/BOLL/CCI"
            }
    except Exception as e:
        return {"success": False, "signals": {}, "message": f"Python 回退计算异常: {e}"}

    # 确定最新信号
    latest_signal = None
    for i in range(len(closes) - 1, -1, -1):
        if buy_signals[i] is not None:
            latest_signal = {"type": "buy", "signal": "ENTERLONG", "value": buy_signals[i]}
            break
        if sell_signals[i] is not None:
            latest_signal = {"type": "sell", "signal": "EXITLONG", "value": sell_signals[i]}
            break

    return {
        "success": True,
        "signals": {"ENTERLONG": buy_signals, "EXITLONG": sell_signals},
        "latest_signal": latest_signal,
        "message": f"成功获取 {formula_name} 专家系统信号（Python 回退）",
        "stock_code": stock_code,
        "formula_name": formula_name,
        "period": period,
        "source": "python_fallback"
    }


def _get_default_stock_pool() -> list:
    """获取默认股票池（上限50只，避免批量K线拉取过载）"""
    if data_source.is_tdx_available():
        pool = data_source.get_stock_list_in_sector_tdxquant("沪深300")
        if pool:
            return [c.split('.')[0] for c in pool][:50]

    try:
        import akshare as ak
        df = ak.index_stock_cons_csindex(symbol="000300")
        if df is not None and not df.empty:
            col = '成分券代码' if '成分券代码' in df.columns else df.columns[0]
            return df[col].tolist()[:50]
    except Exception:
        pass

    return [
        "600519", "000001", "600036", "601318", "000858",
        "600276", "601166", "000333", "600030", "601398",
        "600900", "601012", "600809", "000568", "002714",
        "601888", "600887", "000651", "601668", "600585",
    ]


# ============== 公式计算函数 ==============

def calculate_indicator(
    stock_code: str,
    formula_name: str,
    formula_args: str = "",
    period: str = "1d",
    count: int = 100,
    dividend_type: int = 1
) -> dict:
    """计算技术指标公式（TDX 优先，自动回退到 Python）"""
    # 尝试 TDX 原生公式
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
                        count=count, dividend_type=dividend_type
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
                                "source": "tdxquant"
                            }
        except Exception as e:
            logger.debug(f"TDX formula failed, falling back to Python: {e}")

    # Python 回退
    return _fallback_calculate_indicator(
        stock_code, formula_name, formula_args, period, count, dividend_type
    )


def screen_stocks(
    formula_name: str,
    formula_args: str = "",
    stock_pool: list = None,
    period: str = "1d",
    count: int = 100
) -> dict:
    """
    条件选股公式（TDX 优先，自动回退到 Python 选股引擎）

    Args:
        formula_name: 选股公式名称 (如 UPN, 放量上攻, MACD金叉)
        formula_args: 公式参数 (如 "3")
        stock_pool: 股票池列表，为空则使用沪深300成分股
        period: K线周期
        count: K线数量

    Returns:
        dict: {"success": bool, "matched": list, "total": int, "message": str}
    """
    # 尝试 TDX 原生条件选股
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
                                stock_code=tdx_code,
                                stock_period=tdx_period,
                                count=count,
                                dividend_type=1
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
                                                "signal_value": last_value
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
                        "source": "tdxquant"
                    }
        except Exception as e:
            logger.debug(f"TDX screen_stocks failed, falling back to Python: {e}")

    # Python 回退选股引擎
    return _fallback_screen_stocks(formula_name, formula_args, stock_pool, period, count)


def get_expert_signals(
    stock_code: str,
    formula_name: str,
    formula_args: str = "",
    period: str = "1d",
    count: int = 100,
    dividend_type: int = 1
) -> dict:
    """
    获取专家系统信号（TDX 优先，自动回退到 Python）

    Args:
        stock_code: 股票代码 (如 600519)
        formula_name: 专家系统公式名称 (如 MACD, KDJ, RSI, BOLL, CCI)
        formula_args: 公式参数 (如 "12")
        period: K线周期
        count: K线数量
        dividend_type: 复权类型

    Returns:
        dict: {"success": bool, "signals": dict, "message": str}
    """
    # 尝试 TDX 原生专家系统
    if data_source.is_tdx_available():
        try:
            tq = data_source.get_tdxquant()
            if tq is not None:
                compat_err = _ensure_formula_api(tq)
                if compat_err is None:
                    tdx_code = _convert_to_tdx_code(stock_code)
                    tdx_period = _convert_period(period)

                    set_result = tq.formula_set_data_info(
                        stock_code=tdx_code,
                        stock_period=tdx_period,
                        count=count,
                        dividend_type=dividend_type
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
                                "source": "tdxquant"
                            }
        except Exception as e:
            logger.debug(f"TDX expert_signals failed, falling back to Python: {e}")

    # Python 回退
    return _fallback_expert_signals(stock_code, formula_name, formula_args, period, count)



# ============== 公式数据获取函数 ==============

def get_formula_data(
    stock_code: str,
    period: str = "1d",
    count: int = 100,
    dividend_type: int = 1
) -> dict:
    """
    获取公式系统K线数据（TDX 优先，自动回退到 Python）

    Args:
        stock_code: 股票代码 (如 600519)
        period: K线周期 (1m/5m/15m/30m/1h/1d/1w/1M)
        count: K线数量 (最大24000，-1获取全部)
        dividend_type: 复权类型 (0不复权 1前复权 2后复权)

    Returns:
        dict: {"success": bool, "data": list, "message": str}
    """
    # 尝试 TDX 原生公式数据
    if data_source.is_tdx_available():
        try:
            tq = data_source.get_tdxquant()
            if tq is not None:
                compat_err = _ensure_formula_api(tq)
                if compat_err is None:
                    tdx_code = _convert_to_tdx_code(stock_code)
                    tdx_period = _convert_period(period)

                    set_result = tq.formula_set_data_info(
                        stock_code=tdx_code,
                        stock_period=tdx_period,
                        count=count,
                        dividend_type=dividend_type
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
                                "source": "tdxquant"
                            }
        except Exception as e:
            logger.debug(f"TDX formula_data failed, falling back to Python: {e}")

    # Python 回退：使用通用K线获取
    klines = _get_kline_for_fallback(stock_code, period, count)
    if not klines:
        return {
            "success": False,
            "data": [],
            "message": f"无法获取 {stock_code} 的K线数据"
        }

    klines = sorted(klines, key=lambda x: x.get('date', ''))
    # 转换为与 TDX 格式兼容的字段名
    formatted = []
    for k in klines:
        formatted.append({
            "Date": k.get('date', ''),
            "Open": k.get('open', 0),
            "High": k.get('high', 0),
            "Low": k.get('low', 0),
            "Close": k.get('close', 0),
            "Volume": k.get('volume', 0),
            "Amount": k.get('amount', 0),
        })

    return {
        "success": True,
        "data": formatted,
        "count": len(formatted),
        "message": f"成功获取 {len(formatted)} 条K线数据（Python 回退）",
        "stock_code": stock_code,
        "period": period,
        "dividend_type": dividend_type,
        "source": "python_fallback"
    }


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

def register(mcp):
    """注册 TDX 公式计算工具到 MCP 服务"""

    @mcp.tool()
    def tdx_calculate_indicator(
        stock_code: str,
        formula_name: str,
        formula_args: str = "",
        period: str = "1d",
        count: int = 100,
        dividend_type: int = 1
    ) -> dict:
        """
        [TDX] 计算技术指标公式

        使用通达信公式系统计算技术指标，支持 MACD、KDJ、RSI、BOLL 等所有通达信内置指标。

        Args:
            stock_code: 股票代码 (如 600519, 000001)
            formula_name: 公式名称 (如 MACD, KDJ, RSI, BOLL, MA, EMA, WMA)
            formula_args: 公式参数，逗号分隔 (如 "12,26,9" 对应 MACD 的短期、长期、信号线周期)
            period: K线周期 (1m/5m/15m/30m/1h/1d/1w/1M)
            count: K线数量 (最大24000，-1获取全部)
            dividend_type: 复权类型 (0不复权 1前复权 2后复权)

        Returns:
            dict: 包含指标计算结果的字典

        Examples:
            - MACD: formula_name="MACD", formula_args="12,26,9"
            - KDJ: formula_name="KDJ", formula_args="9,3,3"
            - RSI: formula_name="RSI", formula_args="6,12,24"
            - BOLL: formula_name="BOLL", formula_args="20,2"
        """
        return calculate_indicator(stock_code, formula_name, formula_args, period, count, dividend_type)

    @mcp.tool()
    def tdx_screen_stocks(
        formula_name: str,
        formula_args: str = "",
        stock_pool: list = None,
        period: str = "1d",
        count: int = 100
    ) -> dict:
        """
        [TDX] 条件选股

        使用通达信条件选股公式筛选符合条件的股票。

        Args:
            formula_name: 选股公式名称 (如 UPN, 放量上攻, 均线多头)
            formula_args: 公式参数 (如 "3")
            stock_pool: 股票池列表，为空则使用沪深300成分股
            period: K线周期
            count: K线数量

        Returns:
            dict: 包含符合条件股票列表的字典
        """
        return screen_stocks(formula_name, formula_args, stock_pool, period, count)

    @mcp.tool()
    def tdx_get_expert_signals(
        stock_code: str,
        formula_name: str,
        formula_args: str = "",
        period: str = "1d",
        count: int = 100,
        dividend_type: int = 1
    ) -> dict:
        """
        [TDX] 获取专家系统信号

        使用通达信专家系统公式获取买卖信号。

        Args:
            stock_code: 股票代码 (如 600519)
            formula_name: 专家系统公式名称 (如 CCI, BIAS)
            formula_args: 公式参数 (如 "12")
            period: K线周期
            count: K线数量
            dividend_type: 复权类型

        Returns:
            dict: 包含买卖信号的字典，latest_signal 字段表示最新信号
        """
        return get_expert_signals(stock_code, formula_name, formula_args, period, count, dividend_type)

    @mcp.tool()
    def tdx_calculate_macd(
        stock_code: str,
        short: int = 12,
        long: int = 26,
        signal: int = 9,
        period: str = "1d",
        count: int = 100
    ) -> dict:
        """
        [TDX] 计算 MACD 指标

        快捷计算 MACD 指标，返回 DIF、DEA、MACD 柱状图数据。

        Args:
            stock_code: 股票代码
            short: 短期EMA周期 (默认12)
            long: 长期EMA周期 (默认26)
            signal: 信号线周期 (默认9)
            period: K线周期
            count: K线数量
        """
        return calculate_macd(stock_code, short, long, signal, period, count)

    @mcp.tool()
    def tdx_calculate_kdj(
        stock_code: str,
        n: int = 9,
        m1: int = 3,
        m2: int = 3,
        period: str = "1d",
        count: int = 100
    ) -> dict:
        """
        [TDX] 计算 KDJ 指标

        快捷计算 KDJ 随机指标，返回 K、D、J 值。

        Args:
            stock_code: 股票代码
            n: RSV周期 (默认9)
            m1: K值平滑周期 (默认3)
            m2: D值平滑周期 (默认3)
            period: K线周期
            count: K线数量
        """
        return calculate_kdj(stock_code, n, m1, m2, period, count)

    @mcp.tool()
    def tdx_calculate_rsi(
        stock_code: str,
        n1: int = 6,
        n2: int = 12,
        n3: int = 24,
        period: str = "1d",
        count: int = 100
    ) -> dict:
        """
        [TDX] 计算 RSI 指标

        快捷计算 RSI 相对强弱指标。

        Args:
            stock_code: 股票代码
            n1: 短期RSI周期 (默认6)
            n2: 中期RSI周期 (默认12)
            n3: 长期RSI周期 (默认24)
            period: K线周期
            count: K线数量
        """
        return calculate_rsi(stock_code, n1, n2, n3, period, count)

    @mcp.tool()
    def tdx_calculate_boll(
        stock_code: str,
        n: int = 20,
        p: int = 2,
        period: str = "1d",
        count: int = 100
    ) -> dict:
        """
        [TDX] 计算 BOLL 布林带指标

        快捷计算布林带指标，返回上轨、中轨、下轨数据。

        Args:
            stock_code: 股票代码
            n: 移动平均周期 (默认20)
            p: 标准差倍数 (默认2)
            period: K线周期
            count: K线数量
        """
        return calculate_boll(stock_code, n, p, period, count)



    @mcp.tool()
    def tdx_calculate_trix(
        stock_code: str,
        n: int = 12,
        period: str = "1d",
        count: int = 100
    ) -> dict:
        """
        [TDX] 计算 TRIX 指标

        Args:
            stock_code: 股票代码
            n: TRIX 周期
            period: K线周期
            count: K线数量
        """
        return calculate_trix(stock_code, n, period, count)

    @mcp.tool()
    def tdx_calculate_dma(
        stock_code: str,
        short: int = 10,
        long: int = 50,
        m: int = 10,
        period: str = "1d",
        count: int = 100
    ) -> dict:
        """
        [TDX] 计算 DMA 指标

        Args:
            stock_code: 股票代码
            short: 短期周期
            long: 长期周期
            m: 平滑周期
            period: K线周期
            count: K线数量
        """
        return calculate_dma(stock_code, short, long, m, period, count)

    @mcp.tool()
    def tdx_calculate_expma(
        stock_code: str,
        n1: int = 12,
        n2: int = 50,
        period: str = "1d",
        count: int = 100
    ) -> dict:
        """
        [TDX] 计算 EXPMA 指标

        Args:
            stock_code: 股票代码
            n1: 短期周期
            n2: 长期周期
            period: K线周期
            count: K线数量
        """
        return calculate_expma(stock_code, n1, n2, period, count)

    @mcp.tool()
    def tdx_calculate_dmi(
        stock_code: str,
        n: int = 14,
        m: int = 6,
        period: str = "1d",
        count: int = 100
    ) -> dict:
        """
        [TDX] 计算 DMI 指标

        Args:
            stock_code: 股票代码
            n: DMI 周期
            m: 平滑周期
            period: K线周期
            count: K线数量
        """
        return calculate_dmi(stock_code, n, m, period, count)

    @mcp.tool()
    def tdx_calculate_cr(
        stock_code: str,
        n: int = 26,
        period: str = "1d",
        count: int = 100
    ) -> dict:
        """
        [TDX] 计算 CR 指标

        Args:
            stock_code: 股票代码
            n: CR 周期
            period: K线周期
            count: K线数量
        """
        return calculate_cr(stock_code, n, period, count)

    @mcp.tool()
    def tdx_calculate_vr(
        stock_code: str,
        n: int = 26,
        period: str = "1d",
        count: int = 100
    ) -> dict:
        """
        [TDX] 计算 VR 指标

        Args:
            stock_code: 股票代码
            n: VR 周期
            period: K线周期
            count: K线数量
        """
        return calculate_vr(stock_code, n, period, count)

    @mcp.tool()
    def tdx_get_formula_data(
        stock_code: str,
        period: str = "1d",
        count: int = 100,
        dividend_type: int = 1
    ) -> dict:
        """
        [TDX] 获取公式系统K线数据

        获取与公式计算相同的基础K线数据，可用于自定义分析。

        Args:
            stock_code: 股票代码 (如 600519)
            period: K线周期 (1m/5m/15m/30m/1h/1d/1w/1M)
            count: K线数量 (最大24000，-1获取全部)
            dividend_type: 复权类型 (0不复权 1前复权 2后复权)

        Returns:
            dict: 包含K线数据列表，每条记录包含 Date/Open/High/Low/Close/Volume/Amount
        """
        return get_formula_data(stock_code, period, count, dividend_type)

