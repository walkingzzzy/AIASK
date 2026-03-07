"""TDX 公式系统 - Python 回退函数"""

from ...data_source import data_source
from ...utils import normalize_code
from ...services.technical_analysis import TechnicalAnalysis

_ta = TechnicalAnalysis()


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

    sorted_klines = sorted(daily_klines, key=lambda x: str(x.get('date', '')))

    def _get_group_key(date_str: str) -> str:
        try:
            dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
        except (ValueError, TypeError):
            return date_str
        if period in ('1w', 'weekly'):
            iso = dt.isocalendar()
            return f"{iso[0]}-W{iso[1]:02d}"
        else:
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
            'date': str(bars[-1].get('date', '')),
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

    klines = sorted(klines, key=lambda x: x.get('date', ''))

    closes = [k['close'] for k in klines if k.get('close')]
    highs = [k['high'] for k in klines if k.get('high')]
    lows = [k['low'] for k in klines if k.get('low')]
    volumes = [k.get('volume', 0) or 0 for k in klines]

    if not closes:
        return {"success": False, "data": {}, "message": "K线数据为空"}

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
    from ...services.screen_engine import engine as screen_engine
    from ...services import screen_conditions  # noqa: F401 触发条件注册

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

    if not stock_pool:
        stock_pool = _get_default_stock_pool()

    params = {}
    if formula_args:
        arg_parts = [a.strip() for a in formula_args.split(',') if a.strip()]
        if condition_id in ('upn', 'downn', 'continuous_limit_up') and arg_parts:
            params['n'] = int(arg_parts[0])

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
