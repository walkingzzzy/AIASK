# 数据质量测试 06: TDX K线数据全面质量测试
# 覆盖: 日K/周K/月K/分钟K、多股票、复权因子、OHLCV完整性、价格连续性
# 数据源: TDX get_market_data / get_market_snapshot

from config import *
import math
from datetime import datetime, timedelta


def test_tdx_daily_kline(tq, code, label):
    """TDX 日K线数据质量 - 深度验证"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 日K线 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"tdx_kline_{code}")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"

    try:
        data = tq.get_market_data(
            field_list=[],
            stock_list=[tdx_code],
            period='1d',
            start_time='20250101',
            end_time='',
            count=60,
            dividend_type='none',
            fill_data=True
        )
        r.check("get_market_data 成功", data is not None and 'Close' in data)
    except Exception as e:
        r.check("get_market_data 成功", False, str(e))
        return r

    if data is None or 'Close' not in data:
        return r

    close_df = data['Close']
    if close_df is None or close_df.empty:
        r.check("有K线数据", False)
        return r

    count = len(close_df)
    r.check(f"数据量 >= 20", count >= 20, f"实际 {count} 条")

    # 字段完整性 (包含 ForwardFactor)
    expected_fields = ['Open', 'High', 'Low', 'Close', 'Volume', 'Amount']
    for field in expected_fields:
        has = field in data
        r.check(f"字段 '{field}' 存在", has)
        if has:
            field_df = data[field]
            non_null = field_df[tdx_code].notna().sum()
            ratio = non_null / count
            r.check(f"字段 '{field}' 非空率 >= 95%", ratio >= 0.95,
                    f"非空率 {ratio:.1%}")

    # ForwardFactor 存在性 (dividend_type=none 时应返回)
    has_ff = 'ForwardFactor' in data
    r.check("前复权因子 ForwardFactor 存在", has_ff)
    if has_ff:
        ff_vals = data['ForwardFactor'][tdx_code].dropna().tolist()
        if ff_vals:
            r.check("复权因子 > 0", all(v > 0 for v in ff_vals),
                    f"范围: [{min(ff_vals):.4f}, {max(ff_vals):.4f}]")

    # 价格合理性
    closes = data['Close'][tdx_code].dropna().tolist()
    if closes:
        min_p, max_p = min(closes), max(closes)
        r.check("收盘价 > 0", min_p > 0, f"最低: {min_p}")
        r.check("收盘价 < 100000", max_p < 100000, f"最高: {max_p}")

        # OHLC 严格一致性
        if 'High' in data and 'Low' in data and 'Open' in data:
            highs = data['High'][tdx_code].dropna().tolist()
            lows = data['Low'][tdx_code].dropna().tolist()
            opens = data['Open'][tdx_code].dropna().tolist()
            n = min(len(closes), len(highs), len(lows), len(opens))

            hl_violations = sum(1 for i in range(n) if highs[i] < lows[i])
            r.check("High >= Low 一致性", hl_violations == 0,
                    f"违规: {hl_violations}/{n}")

            hc_violations = sum(1 for i in range(n) if highs[i] < closes[i] - 0.01)
            r.check("High >= Close 一致性", hc_violations == 0,
                    f"违规: {hc_violations}/{n}")

            lc_violations = sum(1 for i in range(n) if lows[i] > closes[i] + 0.01)
            r.check("Low <= Close 一致性", lc_violations == 0,
                    f"违规: {lc_violations}/{n}")

            ho_violations = sum(1 for i in range(n) if highs[i] < opens[i] - 0.01)
            r.check("High >= Open 一致性", ho_violations == 0,
                    f"违规: {ho_violations}/{n}")

            lo_violations = sum(1 for i in range(n) if lows[i] > opens[i] + 0.01)
            r.check("Low <= Open 一致性", lo_violations == 0,
                    f"违规: {lo_violations}/{n}")

        # 价格跳变检查 (日间涨跌幅不超过 22% - 含ST/涨停板)
        max_change = 0
        for i in range(1, len(closes)):
            if closes[i-1] > 0:
                change = abs(closes[i] - closes[i-1]) / closes[i-1]
                max_change = max(max_change, change)
        r.check("日间涨跌幅 < 22%", max_change < 0.22,
                f"最大变化: {max_change:.1%}")

    # 成交量/成交额一致性
    if 'Volume' in data and 'Amount' in data:
        volumes = data['Volume'][tdx_code].dropna().tolist()
        amounts = data['Amount'][tdx_code].dropna().tolist()
        if volumes and amounts:
            zero_vol = sum(1 for v in volumes if v == 0)
            r.check("成交量零值 < 5%", zero_vol / len(volumes) < 0.05,
                    f"零值: {zero_vol}/{len(volumes)}")

            # 成交额与成交量方向一致
            mismatch = 0
            for i in range(len(min(volumes, amounts, key=len))):
                if (volumes[i] > 0 and amounts[i] <= 0) or \
                   (volumes[i] == 0 and amounts[i] > 0):
                    mismatch += 1
            r.check("成交量/成交额方向一致", mismatch == 0,
                    f"不一致: {mismatch} 条")

    # 日期连续性 (不应有重复日期)
    if 'Date' in data:
        dates = data['Date'][tdx_code].dropna().tolist()
        unique_dates = len(set(dates))
        r.check("日期无重复", unique_dates == len(dates),
                f"总数: {len(dates)}, 去重: {unique_dates}")

    return r


def test_tdx_multi_period_kline(tq, code, label):
    """TDX 多周期K线数据质量 (周K/月K/分钟K)"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 多周期K线 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"tdx_multi_period_{code}")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"

    # 周K线
    try:
        wk_data = tq.get_market_data(
            field_list=[], stock_list=[tdx_code],
            period='1w', count=20, dividend_type='none', fill_data=True
        )
        has_wk = wk_data is not None and 'Close' in wk_data
        r.check("周K线获取成功", has_wk)
        if has_wk:
            wk_count = len(wk_data['Close'])
            r.check(f"周K线数据量 >= 10", wk_count >= 10, f"实际 {wk_count}")
            wk_closes = wk_data['Close'][tdx_code].dropna().tolist()
            if wk_closes:
                r.check("周K收盘价 > 0", min(wk_closes) > 0)
    except Exception as e:
        r.check("周K线获取成功", False, str(e))

    # 月K线
    try:
        mk_data = tq.get_market_data(
            field_list=[], stock_list=[tdx_code],
            period='1mon', count=12, dividend_type='none', fill_data=True
        )
        has_mk = mk_data is not None and 'Close' in mk_data
        r.check("月K线获取成功", has_mk)
        if has_mk:
            mk_count = len(mk_data['Close'])
            r.check(f"月K线数据量 >= 6", mk_count >= 6, f"实际 {mk_count}")
    except Exception as e:
        r.check("月K线获取成功", False, str(e))

    # 5分钟K线
    try:
        m5_data = tq.get_market_data(
            field_list=[], stock_list=[tdx_code],
            period='5m', count=48, dividend_type='none', fill_data=True
        )
        has_m5 = m5_data is not None and 'Close' in m5_data
        r.check("5分钟K线获取成功", has_m5)
        if has_m5:
            m5_count = len(m5_data['Close'])
            r.check(f"5分钟K线数据量 > 0", m5_count > 0, f"实际 {m5_count}")
            m5_closes = m5_data['Close'][tdx_code].dropna().tolist()
            if m5_closes:
                r.check("5分钟收盘价 > 0", min(m5_closes) > 0)
    except Exception as e:
        r.check("5分钟K线获取成功", False, str(e))

    # 15分钟K线
    try:
        m15_data = tq.get_market_data(
            field_list=[], stock_list=[tdx_code],
            period='15m', count=16, dividend_type='none', fill_data=True
        )
        has_m15 = m15_data is not None and 'Close' in m15_data
        r.check("15分钟K线获取成功", has_m15)
    except Exception as e:
        r.check("15分钟K线获取成功", False, str(e))

    # 60分钟K线
    try:
        h1_data = tq.get_market_data(
            field_list=[], stock_list=[tdx_code],
            period='1h', count=20, dividend_type='none', fill_data=True
        )
        has_h1 = h1_data is not None and 'Close' in h1_data
        r.check("60分钟K线获取成功", has_h1)
    except Exception as e:
        r.check("60分钟K线获取成功", False, str(e))

    return r


def test_tdx_dividend_types(tq, code, label):
    """TDX 复权类型对比验证"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 复权对比 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"tdx_dividend_{code}")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"

    prices = {}
    for dtype in ['none', 'front', 'back']:
        try:
            data = tq.get_market_data(
                field_list=[], stock_list=[tdx_code],
                period='1d', count=60, dividend_type=dtype, fill_data=True
            )
            if data and 'Close' in data:
                closes = data['Close'][tdx_code].dropna().tolist()
                prices[dtype] = closes
                r.check(f"复权类型 '{dtype}' 获取成功", len(closes) > 0,
                        f"{len(closes)} 条")
            else:
                r.check(f"复权类型 '{dtype}' 获取成功", False)
        except Exception as e:
            r.check(f"复权类型 '{dtype}' 获取成功", False, str(e))

    # 不复权 vs 前复权: 最新价应相同或接近
    if 'none' in prices and 'front' in prices:
        none_last = prices['none'][-1]
        front_last = prices['front'][-1]
        diff = abs(none_last - front_last) / none_last if none_last > 0 else 0
        r.check("不复权 vs 前复权最新价接近 (<1%)", diff < 0.01,
                f"不复权={none_last:.2f}, 前复权={front_last:.2f}, 差异={diff:.4%}")

    # 前复权价格应 <= 不复权价格 (有分红的股票)
    if 'none' in prices and 'front' in prices and len(prices['none']) > 10:
        # 检查早期数据: 前复权应 <= 不复权 (因为分红导致向下调整)
        none_first = prices['none'][0]
        front_first = prices['front'][0]
        # 有分红的股票，前复权早期价格应低于不复权
        r.check("前复权早期价格 <= 不复权 (有分红)", front_first <= none_first + 0.01,
                f"前复权={front_first:.2f}, 不复权={none_first:.2f}")

    # 后复权价格应 >= 不复权价格
    if 'none' in prices and 'back' in prices and len(prices['none']) > 10:
        back_last = prices['back'][-1]
        none_last = prices['none'][-1]
        r.check("后复权最新价 >= 不复权", back_last >= none_last - 0.01,
                f"后复权={back_last:.2f}, 不复权={none_last:.2f}")

    return r


def test_tdx_multi_stock_kline(tq):
    """TDX 多股票同时获取K线"""
    print("\n" + "=" * 60)
    print("[Test] TDX 多股票批量K线")
    print("=" * 60)
    r = TestResult("tdx_multi_stock")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    stock_list = ['600519.SH', '000001.SZ', '300750.SZ']

    try:
        data = tq.get_market_data(
            field_list=[], stock_list=stock_list,
            period='1d', count=20, dividend_type='none', fill_data=True
        )
        r.check("多股票K线获取成功", data is not None and 'Close' in data)
    except Exception as e:
        r.check("多股票K线获取成功", False, str(e))
        return r

    if data and 'Close' in data:
        close_df = data['Close']
        for stock in stock_list:
            has_col = stock in close_df.columns
            r.check(f"股票 {stock} 有数据", has_col)
            if has_col:
                vals = close_df[stock].dropna().tolist()
                r.check(f"股票 {stock} 数据量 > 0", len(vals) > 0, f"{len(vals)} 条")
                if vals:
                    r.check(f"股票 {stock} 价格 > 0", min(vals) > 0)

    return r


def test_tdx_snapshot(tq, code, label):
    """TDX 实时快照数据质量"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 实时快照 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"tdx_snapshot_{code}")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"

    try:
        snap = tq.get_market_snapshot(stock_code=tdx_code)
        r.check("get_market_snapshot 成功", snap is not None)
    except Exception as e:
        r.check("get_market_snapshot 成功", False, str(e))
        return r

    if snap is None:
        return r

    # 核心字段 (注意: TDX 快照用 Max/Min 而非 High/Low)
    for field in ['Now', 'Open', 'LastClose', 'Volume', 'Amount', 'Max', 'Min']:
        val = snap.get(field)
        r.check(f"字段 '{field}' 有值", val is not None, f"值: {val}")

    # 价格合理性
    now = float(snap.get('Now', 0))
    last_close = float(snap.get('LastClose', 0))
    if now > 0 and last_close > 0:
        change = abs(now - last_close) / last_close
        r.check("现价与前收盘差异 < 22%", change < 0.22,
                f"现价={now}, 前收={last_close}, 变化={change:.2%}")

    # 内外盘
    inside = float(snap.get('Inside', 0))
    outside = float(snap.get('Outside', 0))
    volume = float(snap.get('Volume', 0))
    if volume > 0:
        r.check("内盘+外盘 > 0", inside + outside > 0,
                f"内盘={inside}, 外盘={outside}")

    # 五档盘口
    buyp = snap.get('Buyp', [])
    sellp = snap.get('Sellp', [])
    r.check("买盘有数据", len(buyp) > 0, f"买盘档数: {len(buyp)}")
    r.check("卖盘有数据", len(sellp) > 0, f"卖盘档数: {len(sellp)}")

    from datetime import datetime as _dt
    now_hour = _dt.now().hour
    is_trading = 9 <= now_hour < 15
    min_depth = 3 if is_trading else 1

    if len(buyp) >= 5:
        non_zero_buy = sum(1 for p in buyp[:5] if float(p) > 0)
        r.check(f"买五档非零 >= {min_depth}", non_zero_buy >= min_depth,
                f"非零: {non_zero_buy}/5 ({'盘中' if is_trading else '收盘后'})")
    if len(sellp) >= 5:
        non_zero_sell = sum(1 for p in sellp[:5] if float(p) > 0)
        r.check(f"卖五档非零 >= {min_depth}", non_zero_sell >= min_depth,
                f"非零: {non_zero_sell}/5 ({'盘中' if is_trading else '收盘后'})")

    # 买卖量
    buyv = snap.get('Buyv', [])
    sellv = snap.get('Sellv', [])
    r.check("买量数组长度 == 5", len(buyv) == 5, f"实际: {len(buyv)}")
    r.check("卖量数组长度 == 5", len(sellv) == 5, f"实际: {len(sellv)}")

    return r


def main():
    print("#" * 60)
    print("#  数据质量测试 06: TDX K线数据全面质量测试")
    print("#  覆盖: 日K/周K/月K/分钟K、复权、多股票、快照")
    print("#" * 60)

    tq = init_tdx()

    results = []

    # 日K线深度验证 (多股票)
    for code, label in [('600519', '贵州茅台'), ('000001', '平安银行'),
                        ('300750', '宁德时代')]:
        results.append(test_tdx_daily_kline(tq, code, label))

    # 多周期K线
    results.append(test_tdx_multi_period_kline(tq, '600519', '贵州茅台'))

    # 复权类型对比
    results.append(test_tdx_dividend_types(tq, '600519', '贵州茅台'))

    # 多股票批量
    results.append(test_tdx_multi_stock_kline(tq))

    # 快照
    for code, label in [('600519', '贵州茅台'), ('000001', '平安银行')]:
        results.append(test_tdx_snapshot(tq, code, label))

    print("\n" + "=" * 60)
    print("汇总")
    print("=" * 60)
    total_pass, total_fail, total_warn = 0, 0, 0
    for r in results:
        p, f, w = r.summary()
        total_pass += p
        total_fail += f
        total_warn += w

    print(f"\n总计: {total_pass} 通过, {total_fail} 失败, {total_warn} 警告")
    return total_fail == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
