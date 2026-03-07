# 数据质量测试 08: 跨数据源一致性
# 验证 TDX vs Tushare: K线价格、成交量、财务数据、股本数据
# 核心: 同一股票同一时间段，不同数据源的数据应高度一致

from config import *
import math
from datetime import datetime, timedelta


def _get_tushare_kline(ts_code, start_date, end_date):
    """从 Tushare 获取日K线"""
    try:
        df = tushare_call_api('daily', {
            'ts_code': ts_code,
            'start_date': start_date,
            'end_date': end_date
        })
        if df is None or df.empty:
            return {}
        result = {}
        for _, row in df.iterrows():
            date = str(row.get('trade_date', ''))
            result[date] = {
                'open': float(row.get('open', 0)),
                'close': float(row.get('close', 0)),
                'high': float(row.get('high', 0)),
                'low': float(row.get('low', 0)),
                'volume': float(row.get('vol', 0)) * 100,  # Tushare vol 单位是手
            }
        return result
    except Exception as e:
        print(f"  Tushare K线获取失败: {e}")
        return {}


def _get_tdx_kline(tq, code, count=30):
    """从 TDX 获取日K线"""
    if tq is None:
        return {}
    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
    try:
        data = tq.get_market_data(
            field_list=[], stock_list=[tdx_code],
            period='1d', count=count, dividend_type='none', fill_data=True
        )
        if not data or 'Close' not in data:
            return {}
        result = {}
        close_df = data['Close']
        for idx in close_df.index:
            date = str(idx)[:10].replace('-', '')
            result[date] = {
                'open': float(data['Open'].loc[idx, tdx_code]) if 'Open' in data else 0,
                'close': float(data['Close'].loc[idx, tdx_code]) if 'Close' in data else 0,
                'high': float(data['High'].loc[idx, tdx_code]) if 'High' in data else 0,
                'low': float(data['Low'].loc[idx, tdx_code]) if 'Low' in data else 0,
                'volume': float(data['Volume'].loc[idx, tdx_code]) if 'Volume' in data else 0,
            }
        return result
    except Exception as e:
        print(f"  TDX K线获取失败: {e}")
        return {}


def test_kline_consistency(tq, code, label):
    """K线数据跨源一致性"""
    print("\n" + "=" * 60)
    print(f"[Test] K线跨源一致性 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"kline_consistency_{code}")

    ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')

    tushare_data = _get_tushare_kline(ts_code, start_date, end_date)
    tdx_data = _get_tdx_kline(tq, code, 30)

    r.check("Tushare 有数据", len(tushare_data) > 0, f"{len(tushare_data)} 条")
    r.check("TDX 有数据", len(tdx_data) > 0, f"{len(tdx_data)} 条")

    if not tushare_data or not tdx_data:
        return r

    common_dates = sorted(set(tushare_data.keys()) & set(tdx_data.keys()))
    r.check(f"共同日期 >= 5", len(common_dates) >= 5,
            f"共同日期: {len(common_dates)} 天")

    if len(common_dates) < 3:
        return r

    tolerance = THRESHOLDS['kline_price_tolerance']
    close_diffs = []
    high_diffs = []
    low_diffs = []
    mismatches = []

    for date in common_dates:
        ts = tushare_data[date]
        tdx = tdx_data[date]

        if ts['close'] > 0 and tdx['close'] > 0:
            diff = abs(ts['close'] - tdx['close']) / ts['close']
            close_diffs.append(diff)
            if diff > tolerance:
                mismatches.append(
                    f"{date}: Tushare={ts['close']}, TDX={tdx['close']}, 差异={diff:.2%}")

        if ts['high'] > 0 and tdx['high'] > 0:
            high_diffs.append(abs(ts['high'] - tdx['high']) / ts['high'])

        if ts['low'] > 0 and tdx['low'] > 0:
            low_diffs.append(abs(ts['low'] - tdx['low']) / ts['low'])

    if close_diffs:
        avg_diff = sum(close_diffs) / len(close_diffs)
        max_diff = max(close_diffs)
        r.check(f"收盘价平均差异 < {tolerance:.0%}", avg_diff < tolerance,
                f"平均: {avg_diff:.4%}, 最大: {max_diff:.4%}")

    if high_diffs:
        avg_diff = sum(high_diffs) / len(high_diffs)
        r.check(f"最高价平均差异 < {tolerance:.0%}", avg_diff < tolerance,
                f"平均: {avg_diff:.4%}")

    if low_diffs:
        avg_diff = sum(low_diffs) / len(low_diffs)
        r.check(f"最低价平均差异 < {tolerance:.0%}", avg_diff < tolerance,
                f"平均: {avg_diff:.4%}")

    if mismatches:
        r.warn(f"价格不一致明细 ({len(mismatches)} 条)")
        for m in mismatches[:3]:
            print(f"      {m}")

    return r


def test_volume_consistency(tq, code, label):
    """成交量跨源一致性"""
    print("\n" + "=" * 60)
    print(f"[Test] 成交量跨源一致性 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"volume_consistency_{code}")

    ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')

    tushare_data = _get_tushare_kline(ts_code, start_date, end_date)
    tdx_data = _get_tdx_kline(tq, code, 30)

    if not tushare_data or not tdx_data:
        r.check("两个数据源都有数据", False)
        return r

    common_dates = sorted(set(tushare_data.keys()) & set(tdx_data.keys()))
    if len(common_dates) < 3:
        r.check("共同日期足够", False, f"仅 {len(common_dates)} 天")
        return r

    vol_diffs = []
    for date in common_dates:
        ts_vol = tushare_data[date]['volume']
        tdx_vol = tdx_data[date]['volume']
        if ts_vol > 0 and tdx_vol > 0:
            diff = abs(ts_vol - tdx_vol) / max(ts_vol, tdx_vol)
            vol_diffs.append(diff)

    if vol_diffs:
        avg_diff = sum(vol_diffs) / len(vol_diffs)
        max_diff = max(vol_diffs)
        r.check(f"成交量平均差异 < 20%", avg_diff < 0.2,
                f"平均: {avg_diff:.2%}, 最大: {max_diff:.2%}")

        if avg_diff > 0.5:
            r.warn("成交量差异较大，可能存在单位不一致 (手 vs 股)")

    return r


def test_finance_consistency(tq, code, label):
    """财务数据跨源一致性 (TDX vs Tushare)"""
    print("\n" + "=" * 60)
    print(f"[Test] 财务数据跨源一致性 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"finance_consistency_{code}")

    ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
    tdx_code = ts_code

    # Tushare 获取财务指标
    ts_data = {}
    try:
        df = tushare_call_api('fina_indicator', {
            'ts_code': ts_code,
            'limit': 1
        }, fields='ts_code,ann_date,end_date,eps,bps,roe,debt_to_assets,netprofit_margin')
        if df is not None and not df.empty:
            row = df.iloc[0]
            ts_data = {
                'eps': float(row.get('eps', 0)) if row.get('eps') else None,
                'bvps': float(row.get('bps', 0)) if row.get('bps') else None,
                'roe': float(row.get('roe', 0)) if row.get('roe') else None,
                'debt_ratio': float(row.get('debt_to_assets', 0)) if row.get('debt_to_assets') else None,
            }
            r.check("Tushare 财务数据获取成功", True)
    except Exception as e:
        r.check("Tushare 财务数据获取成功", False, str(e))

    # TDX 获取财务数据
    tdx_data = {}
    if tq is not None:
        try:
            result = tq.get_financial_data_by_date(
                stock_list=[tdx_code],
                field_list=['FN1', 'FN4', 'FN6', 'FN210'],
                year=0, mmdd=0
            )
            if result and tdx_code in result:
                data = result[tdx_code]

                def _safe_float(val):
                    """安全转换 float，处理 '--' 和其他非数值"""
                    if val is None or str(val).strip() in ('', '--', 'nan', 'None'):
                        return None
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return None

                tdx_data = {
                    'eps': _safe_float(data.get('FN1')),
                    'bvps': _safe_float(data.get('FN4')),
                    'roe': _safe_float(data.get('FN6')),
                    'debt_ratio': _safe_float(data.get('FN210')),
                }
                r.check("TDX 财务数据获取成功", True)
        except Exception as e:
            r.check("TDX 财务数据获取成功", False, str(e))

    if not ts_data or not tdx_data:
        return r

    # 对比核心指标
    comparisons = {
        'eps': ('每股收益', 0.5),      # 容差 0.5 元
        'bvps': ('每股净资产', 2.0),    # 容差 2 元
        'roe': ('净资产收益率', 5.0),   # 容差 5%
        'debt_ratio': ('资产负债率', 5.0),  # 容差 5%
    }

    for key, (name, tolerance) in comparisons.items():
        ts_val = ts_data.get(key)
        tdx_val = tdx_data.get(key)
        if ts_val is not None and tdx_val is not None:
            diff = abs(ts_val - tdx_val)
            r.check(f"{name} 差异 < {tolerance}",
                    diff < tolerance,
                    f"Tushare={ts_val:.2f}, TDX={tdx_val:.2f}, 差异={diff:.2f}")

    return r


def test_stock_info_consistency(tq, code, label):
    """股票基本信息跨源一致性"""
    print("\n" + "=" * 60)
    print(f"[Test] 股票信息跨源一致性 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"info_consistency_{code}")

    ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
    tdx_code = ts_code

    # Tushare 获取股票信息
    ts_name = None
    try:
        df = tushare_call_api('stock_basic', {
            'ts_code': ts_code
        }, fields='ts_code,name,industry,list_date')
        if df is not None and not df.empty:
            ts_name = df.iloc[0].get('name', '')
            r.check("Tushare 股票信息获取成功", True)
    except Exception as e:
        r.check("Tushare 股票信息获取成功", False, str(e))

    # TDX 获取股票信息
    tdx_name = None
    if tq is not None:
        try:
            result = tq.get_stock_info(stock_code=tdx_code, field_list=[])
            if result:
                tdx_name = result.get('Name', '')
                r.check("TDX 股票信息获取成功", True)
        except Exception as e:
            r.check("TDX 股票信息获取成功", False, str(e))

    # 名称一致性
    if ts_name and tdx_name:
        # 去除空格和特殊字符比较
        ts_clean = ts_name.strip().replace(' ', '')
        tdx_clean = tdx_name.strip().replace(' ', '')
        r.check("股票名称一致", ts_clean == tdx_clean,
                f"Tushare='{ts_name}', TDX='{tdx_name}'")

    return r


def main():
    print("#" * 60)
    print("#  数据质量测试 08: 跨数据源一致性")
    print("#  覆盖: K线价格/成交量/财务数据/股票信息")
    print("#" * 60)

    tq = init_tdx()

    results = []

    # K线一致性
    results.append(test_kline_consistency(tq, '600519', '贵州茅台'))
    results.append(test_kline_consistency(tq, '000001', '平安银行'))

    # 成交量一致性
    results.append(test_volume_consistency(tq, '600519', '贵州茅台'))

    # 财务数据一致性
    results.append(test_finance_consistency(tq, '600519', '贵州茅台'))

    # 股票信息一致性
    results.append(test_stock_info_consistency(tq, '600519', '贵州茅台'))
    results.append(test_stock_info_consistency(tq, '000001', '平安银行'))

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
