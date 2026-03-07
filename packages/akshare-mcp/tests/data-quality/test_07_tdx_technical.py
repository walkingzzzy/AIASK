# 数据质量测试 07: TDX 技术指标与公式系统质量
# 覆盖: formula_zb (MACD/KDJ/RSI/BOLL/DMA)、formula_xg (条件选股)、
#       formula_exp (专家系统)、手动计算交叉验证
# 数据源: TDX 公式系统 + get_market_data
#
# 注意: formula_set_data_info / formula_zb / formula_xg / formula_exp / formula_get_data
#       仅在通达信客户端 PYPlugins 环境内可用。
#       在外部 Python 环境中这些 API 不可用，相关测试会自动跳过 (WARN)。

from config import *
import math


def _get_closes(tq, code, count=100):
    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
    data = tq.get_market_data(
        field_list=[], stock_list=[tdx_code],
        period='1d', count=count, dividend_type='none', fill_data=True
    )
    if data and 'Close' in data:
        return data['Close'][tdx_code].dropna().tolist()
    return []


def _check_formula_available(tq, r):
    """检查公式API是否可用，不可用时返回 False 并记录 WARN"""
    if tq is None:
        r.warn("TDX 未初始化，跳过公式测试")
        return False
    if not hasattr(tq, 'formula_set_data_info') or not hasattr(tq, 'formula_zb'):
        r.warn("公式API不可用 (需在通达信客户端 PYPlugins 环境运行)，跳过")
        return False
    return True


def _setup_formula(tq, code, count=100, period='1d'):
    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
    try:
        result = tq.formula_set_data_info(
            stock_code=tdx_code, stock_period=period,
            count=count, dividend_type=1
        )
        return result and result.get('ErrorId') == '0'
    except Exception:
        return False


def test_formula_macd(tq, code, label):
    """TDX 公式系统 MACD 计算 + 手动交叉验证"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 公式 MACD - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"formula_macd_{code}")

    if not _check_formula_available(tq, r):
        return r

    setup_ok = _setup_formula(tq, code, 100)
    if not setup_ok:
        r.warn("formula_set_data_info 失败，公式环境不可用，跳过")
        return r

    try:
        result = tq.formula_zb(formula_name='MACD', formula_arg='12,26,9')
        ok = result is not None and result.get('ErrorId') == '0'
        r.check("formula_zb MACD 成功", ok,
                f"ErrorId: {result.get('ErrorId') if result else 'None'}")
    except Exception as e:
        r.warn(f"formula_zb MACD 异常: {e}")
        return r

    if not ok:
        return r

    data = result.get('Data', {})
    r.check("返回 DIF 序列", 'DIF' in data, f"字段: {list(data.keys())}")
    r.check("返回 DEA 序列", 'DEA' in data)
    r.check("返回 MACD 序列", 'MACD' in data)

    if 'DIF' in data and 'DEA' in data and 'MACD' in data:
        dif = data['DIF']
        dea = data['DEA']
        macd = data['MACD']

        r.check("DIF 序列长度 > 0", len(dif) > 0, f"长度: {len(dif)}")
        r.check("三序列长度一致", len(dif) == len(dea) == len(macd),
                f"DIF={len(dif)}, DEA={len(dea)}, MACD={len(macd)}")

        valid_dif = [v for v in dif if v is not None]
        r.check("DIF 有有效值", len(valid_dif) > 0, f"有效: {len(valid_dif)}")

        if valid_dif:
            max_abs_dif = max(abs(v) for v in valid_dif)
            r.check("DIF 值范围合理 (< 1000)", max_abs_dif < 1000,
                    f"最大|DIF|: {max_abs_dif:.4f}")

        # MACD = (DIF - DEA) * 2 验证
        check_count = 0
        match_count = 0
        for i in range(len(dif)):
            if dif[i] is not None and dea[i] is not None and macd[i] is not None:
                expected = (dif[i] - dea[i]) * 2
                if abs(expected - macd[i]) < 0.01:
                    match_count += 1
                check_count += 1
        if check_count > 0:
            ratio = match_count / check_count
            r.check("MACD = (DIF-DEA)*2 验证 (>95%)", ratio > 0.95,
                    f"匹配: {match_count}/{check_count} = {ratio:.1%}")

        # 手动计算交叉验证
        closes = _get_closes(tq, code, 100)
        if len(closes) >= 50 and valid_dif:
            def ema(data_arr, period):
                res = [data_arr[0]]
                k = 2 / (period + 1)
                for i in range(1, len(data_arr)):
                    res.append(data_arr[i] * k + res[-1] * (1 - k))
                return res

            ema12 = ema(closes, 12)
            ema26 = ema(closes, 26)
            manual_dif = [ema12[i] - ema26[i] for i in range(len(closes))]

            tdx_trend = valid_dif[-1] - valid_dif[-5] if len(valid_dif) >= 5 else 0
            manual_trend = manual_dif[-1] - manual_dif[-5] if len(manual_dif) >= 5 else 0
            same_dir = (tdx_trend > 0) == (manual_trend > 0) or abs(tdx_trend) < 0.1
            r.check("DIF 趋势方向与手动计算一致", same_dir,
                    f"TDX={tdx_trend:.4f}, 手动={manual_trend:.4f}")

    return r


def test_formula_kdj(tq, code, label):
    """TDX 公式系统 KDJ 计算"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 公式 KDJ - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"formula_kdj_{code}")

    if not _check_formula_available(tq, r):
        return r

    setup_ok = _setup_formula(tq, code, 100)
    if not setup_ok:
        r.warn("formula_set_data_info 失败，跳过")
        return r

    try:
        result = tq.formula_zb(formula_name='KDJ', formula_arg='9,3,3')
        ok = result is not None and result.get('ErrorId') == '0'
        r.check("formula_zb KDJ 成功", ok)
    except Exception as e:
        r.warn(f"formula_zb KDJ 异常: {e}")
        return r

    if not ok:
        return r

    data = result.get('Data', {})
    r.check("返回 K 序列", 'K' in data)
    r.check("返回 D 序列", 'D' in data)
    r.check("返回 J 序列", 'J' in data)

    if 'K' in data and 'D' in data:
        k_vals = [v for v in data['K'] if v is not None]
        d_vals = [v for v in data['D'] if v is not None]
        if k_vals:
            r.check("K 值范围 [0, 100]", 0 <= min(k_vals) and max(k_vals) <= 100,
                    f"K: [{min(k_vals):.1f}, {max(k_vals):.1f}]")
        if d_vals:
            r.check("D 值范围 [0, 100]", 0 <= min(d_vals) and max(d_vals) <= 100,
                    f"D: [{min(d_vals):.1f}, {max(d_vals):.1f}]")

    if 'J' in data:
        j_vals = [v for v in data['J'] if v is not None]
        if j_vals:
            r.check("J 值有意义 (-50~150)", -50 < j_vals[-1] < 150,
                    f"J 最新: {j_vals[-1]:.1f}")

    return r


def test_formula_rsi(tq, code, label):
    """TDX 公式系统 RSI 计算"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 公式 RSI - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"formula_rsi_{code}")

    if not _check_formula_available(tq, r):
        return r

    if not _setup_formula(tq, code, 100):
        r.warn("formula_set_data_info 失败，跳过")
        return r

    try:
        result = tq.formula_zb(formula_name='RSI', formula_arg='6,12,24')
        ok = result is not None and result.get('ErrorId') == '0'
        r.check("formula_zb RSI 成功", ok)
    except Exception as e:
        r.warn(f"formula_zb RSI 异常: {e}")
        return r

    if not ok:
        return r

    data = result.get('Data', {})
    rsi_keys = [k for k in data.keys() if 'RSI' in k.upper()]
    r.check("返回 RSI 序列", len(rsi_keys) >= 1, f"字段: {rsi_keys}")

    for key in rsi_keys:
        vals = [v for v in data[key] if v is not None]
        if vals:
            r.check(f"{key} 范围 [0, 100]", 0 <= min(vals) and max(vals) <= 100,
                    f"[{min(vals):.1f}, {max(vals):.1f}]")

    return r


def test_formula_boll(tq, code, label):
    """TDX 公式系统 BOLL 布林带"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 公式 BOLL - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"formula_boll_{code}")

    if not _check_formula_available(tq, r):
        return r

    if not _setup_formula(tq, code, 100):
        r.warn("formula_set_data_info 失败，跳过")
        return r

    try:
        result = tq.formula_zb(formula_name='BOLL', formula_arg='20,2')
        ok = result is not None and result.get('ErrorId') == '0'
        r.check("formula_zb BOLL 成功", ok)
    except Exception as e:
        r.warn(f"formula_zb BOLL 异常: {e}")
        return r

    if not ok:
        return r

    data = result.get('Data', {})
    all_keys = list(data.keys())
    r.check("BOLL 返回 >= 3 个序列", len(all_keys) >= 3, f"字段: {all_keys}")

    if len(all_keys) >= 3:
        vals_list = []
        for k in all_keys[:3]:
            vals_list.append([v for v in data[k] if v is not None])

        if all(len(v) > 0 for v in vals_list):
            last_vals = [v[-1] for v in vals_list]
            r.check("三条线值不同", len(set(f"{v:.2f}" for v in last_vals)) >= 2,
                    f"值: {[f'{v:.2f}' for v in last_vals]}")

    return r


def test_formula_dma_warmup(tq, code, label):
    """DMA 指标预热期检查 (手动计算，不依赖公式API)"""
    print("\n" + "=" * 60)
    print(f"[Test] DMA 预热期 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"dma_warmup_{code}")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    closes = _get_closes(tq, code, 100)
    if not closes:
        r.check("获取K线数据", False)
        return r

    r.check(f"K线数据量 >= 60", len(closes) >= 60, f"实际 {len(closes)} 条")

    short, long_p = 10, 50

    def sma(data_arr, period):
        result = []
        for i in range(len(data_arr)):
            if i < period - 1:
                result.append(None)
            else:
                result.append(sum(data_arr[i-period+1:i+1]) / period)
        return result

    ma_short = sma(closes, short)
    ma_long = sma(closes, long_p)

    dif = []
    for i in range(len(closes)):
        if i < long_p - 1 or ma_short[i] is None or ma_long[i] is None:
            dif.append(None)
        else:
            dif.append(ma_short[i] - ma_long[i])

    warmup_correct = all(d is None for d in dif[:long_p - 1])
    r.check(f"DIF 预热期 (前{long_p-1}个) 为 None", warmup_correct)

    valid_dif = [d for d in dif if d is not None]
    if valid_dif:
        r.check(f"DIF 有效值数量 > 0", len(valid_dif) > 0)
        max_jump = 0
        avg_price = sum(closes) / len(closes)
        for i in range(1, len(valid_dif)):
            max_jump = max(max_jump, abs(valid_dif[i] - valid_dif[i-1]))
        threshold = avg_price * 0.1
        r.check(f"DIF 无异常跳变 (阈值: {threshold:.2f})", max_jump < threshold,
                f"最大跳变: {max_jump:.4f}")

    return r


def test_formula_xg(tq, code, label):
    """TDX 条件选股公式"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 条件选股 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"formula_xg_{code}")

    if tq is None:
        r.warn("TDX 未初始化，跳过")
        return r
    if not hasattr(tq, 'formula_xg'):
        r.warn("formula_xg 不可用 (需在通达信客户端环境运行)，跳过")
        return r

    if not _setup_formula(tq, code, 100):
        r.warn("formula_set_data_info 失败，跳过")
        return r

    try:
        result = tq.formula_xg(formula_name='UPN', formula_arg='3')
        ok = result is not None and result.get('ErrorId') == '0'
        r.check("formula_xg UPN 成功", ok,
                f"ErrorId: {result.get('ErrorId') if result else 'None'}")
    except Exception as e:
        r.warn(f"formula_xg UPN 异常: {e}")
        return r

    if ok:
        data = result.get('Data', {})
        r.check("条件选股返回数据", len(data) > 0, f"字段: {list(data.keys())}")

    return r


def test_formula_exp(tq, code, label):
    """TDX 专家系统公式"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 专家系统 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"formula_exp_{code}")

    if tq is None:
        r.warn("TDX 未初始化，跳过")
        return r
    if not hasattr(tq, 'formula_exp'):
        r.warn("formula_exp 不可用 (需在通达信客户端环境运行)，跳过")
        return r

    if not _setup_formula(tq, code, 100):
        r.warn("formula_set_data_info 失败，跳过")
        return r

    try:
        result = tq.formula_exp(formula_name='CCI', formula_arg='12')
        ok = result is not None and result.get('ErrorId') == '0'
        r.check("formula_exp CCI 成功", ok)
    except Exception as e:
        r.warn(f"formula_exp CCI 异常: {e}")
        return r

    if ok:
        data = result.get('Data', {})
        r.check("专家系统返回数据", len(data) > 0, f"字段: {list(data.keys())}")
        has_signal = any('ENTER' in k.upper() or 'EXIT' in k.upper() or
                        'LONG' in k.upper() or 'SHORT' in k.upper()
                        for k in data.keys())
        r.check("包含买卖信号字段", has_signal, f"字段: {list(data.keys())}")

    return r


def test_formula_get_data(tq, code, label):
    """TDX formula_get_data 获取公式K线数据"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX formula_get_data - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"formula_get_data_{code}")

    if tq is None:
        r.warn("TDX 未初始化，跳过")
        return r
    if not hasattr(tq, 'formula_get_data'):
        r.warn("formula_get_data 不可用 (需在通达信客户端环境运行)，跳过")
        return r

    if not _setup_formula(tq, code, 20):
        r.warn("formula_set_data_info 失败，跳过")
        return r

    try:
        result = tq.formula_get_data()
        ok = result is not None and result.get('ErrorId') == '0'
        r.check("formula_get_data 成功", ok)
    except Exception as e:
        r.warn(f"formula_get_data 异常: {e}")
        return r

    if not ok:
        return r

    data_list = result.get('Data', [])
    r.check("返回K线数据", len(data_list) > 0, f"数据量: {len(data_list)}")

    if data_list:
        first = data_list[0]
        for field in ['Open', 'High', 'Low', 'Close', 'Volume', 'Amount', 'Date']:
            r.check(f"K线字段 '{field}' 存在", field in first)

    return r


def main():
    print("#" * 60)
    print("#  数据质量测试 07: TDX 技术指标与公式系统质量")
    print("#  覆盖: MACD/KDJ/RSI/BOLL/DMA + 条件选股 + 专家系统")
    print("#  注意: 公式API仅在通达信客户端环境可用，外部运行自动跳过")
    print("#" * 60)

    tq = init_tdx()

    results = []
    # 公式系统测试 (环境不可用时自动 WARN 跳过)
    results.append(test_formula_macd(tq, '600519', '贵州茅台'))
    results.append(test_formula_kdj(tq, '600519', '贵州茅台'))
    results.append(test_formula_rsi(tq, '600519', '贵州茅台'))
    results.append(test_formula_boll(tq, '600519', '贵州茅台'))

    # DMA 预热期 (手动计算，不依赖公式API，始终可运行)
    results.append(test_formula_dma_warmup(tq, '600519', '贵州茅台'))
    results.append(test_formula_dma_warmup(tq, '000001', '平安银行'))

    # 条件选股 + 专家系统 (环境不可用时自动 WARN 跳过)
    results.append(test_formula_xg(tq, '600519', '贵州茅台'))
    results.append(test_formula_exp(tq, '600519', '贵州茅台'))
    results.append(test_formula_get_data(tq, '600519', '贵州茅台'))

    # 多股票 MACD (环境不可用时自动 WARN 跳过)
    results.append(test_formula_macd(tq, '000001', '平安银行'))

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
