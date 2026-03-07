# 数据质量测试 03: Tushare 历史估值数据
# 验证 daily_basic 历史 PE/PB 数据连续性和完整性
# 对应问题: WARN #9 (get_historical_valuation 数据不足)
#
# 已知代理行为:
#   1. fields 必须在外层，不能在 params 里（config.py 已自动处理）
#   2. 查询范围仅包含非交易日时，代理返回错误而非空 DataFrame
#      分批时最后一批可能恰好只包含非交易日（如周末），需要容忍此错误

from config import *
import pandas as pd
from datetime import datetime, timedelta


def test_historical_valuation(ts_code, label, days=30):
    """历史估值数据连续性"""
    print("\n" + "=" * 60)
    print(f"[Test] 历史估值 {days}天 - {label} ({ts_code})")
    print("=" * 60)
    r = TestResult(f"hist_val_{ts_code}_{days}d")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # 分批查询（每批最多 30 天）
    df = pd.DataFrame()
    batch_size = 30
    cur_start = start_date
    batch_errors = []
    while cur_start <= end_date:
        cur_end = min(cur_start + timedelta(days=batch_size - 1), end_date)
        s_str = cur_start.strftime('%Y%m%d')
        e_str = cur_end.strftime('%Y%m%d')
        try:
            batch_df = tushare_call_api('daily_basic', {
                'ts_code': ts_code,
                'start_date': s_str,
                'end_date': e_str,
                'fields': 'trade_date,pe_ttm,pb,total_mv,close,turnover_rate'
            })
            if batch_df is not None and not batch_df.empty:
                df = pd.concat([df, batch_df], ignore_index=True)
        except Exception as e:
            # 判断是否是"仅非交易日"导致的错误
            span_days = (cur_end - cur_start).days + 1
            if span_days <= 3:
                # 短范围（<=3天）失败可能是全部非交易日，记录但不算严重错误
                batch_errors.append(f"批次 {s_str}-{e_str} ({span_days}天): {e} [可能全为非交易日]")
            else:
                # 长范围失败是真正的数据质量问题
                batch_errors.append(f"批次 {s_str}-{e_str} ({span_days}天): {e}")
                r.check(f"批次 {s_str}-{e_str} 查询成功", False, str(e))
        cur_start = cur_end + timedelta(days=1)

    # 打印短范围错误作为信息
    for err in batch_errors:
        if '可能全为非交易日' in err:
            print(f"  [i] {err}")

    has_data = not df.empty
    r.check("分批查询有数据", has_data,
            f"返回 {len(df)} 条" if has_data else "返回空")

    if df is None or df.empty:
        return r

    # 数据量检查
    # 30天约有 20~22 个交易日，90天约有 60~65 个交易日
    expected_min = max(days * 0.5, 5)
    r.check(f"数据量 >= {expected_min:.0f} 条", len(df) >= expected_min,
            f"实际 {len(df)} 条")

    # PE_TTM 连续性
    if 'pe_ttm' in df.columns:
        pe_valid = df['pe_ttm'].notna().sum()
        pe_ratio = pe_valid / len(df)
        r.check(f"PE_TTM 非空率 >= 80%", pe_ratio >= 0.8,
                f"非空率 {pe_ratio:.1%} ({pe_valid}/{len(df)})")

        import math
        pe_values = df['pe_ttm'].dropna().astype(float)
        nan_count = sum(1 for v in pe_values if math.isnan(v) or math.isinf(v))
        r.check("PE_TTM 无 NaN/Inf", nan_count == 0,
                f"发现 {nan_count} 个异常值")

        # 值稳定性 (相邻日 PE 变化不应超过 50%)
        if len(pe_values) >= 2:
            pe_sorted = pe_values.sort_index()
            max_change = 0
            for i in range(1, len(pe_sorted)):
                prev, curr = pe_sorted.iloc[i-1], pe_sorted.iloc[i]
                if prev != 0:
                    change = abs((curr - prev) / prev)
                    max_change = max(max_change, change)
            r.check("PE_TTM 日间变化 < 50%", max_change < 0.5,
                    f"最大日间变化 {max_change:.1%}")

    # PB 连续性
    if 'pb' in df.columns:
        pb_valid = df['pb'].notna().sum()
        pb_ratio = pb_valid / len(df)
        r.check(f"PB 非空率 >= 80%", pb_ratio >= 0.8,
                f"非空率 {pb_ratio:.1%} ({pb_valid}/{len(df)})")

    # 总市值连续性
    if 'total_mv' in df.columns:
        mv_valid = df['total_mv'].notna().sum()
        mv_ratio = mv_valid / len(df)
        r.check(f"总市值非空率 >= 80%", mv_ratio >= 0.8,
                f"非空率 {mv_ratio:.1%} ({mv_valid}/{len(df)})")

    # 收盘价连续性
    if 'close' in df.columns:
        close_valid = df['close'].notna().sum()
        close_ratio = close_valid / len(df)
        r.check(f"收盘价非空率 >= 90%", close_ratio >= 0.9,
                f"非空率 {close_ratio:.1%}")

    return r


def test_valuation_cross_stock():
    """跨股票估值数据对比"""
    print("\n" + "=" * 60)
    print("[Test] 跨股票估值数据对比")
    print("=" * 60)
    r = TestResult("cross_stock_valuation")

    stocks = [
        ('600519.SH', '贵州茅台'),
        ('000001.SZ', '平安银行'),
        ('000858.SZ', '五粮液'),
    ]

    trade_date = None
    # 找最近有数据的交易日（用 7 天范围查询）
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=7)
    try:
        df = tushare_call_api('daily_basic', {
            'ts_code': '600519.SH',
            'start_date': start_dt.strftime('%Y%m%d'),
            'end_date': end_dt.strftime('%Y%m%d'),
            'fields': 'trade_date,pe_ttm,pb,total_mv'
        })
        if df is not None and not df.empty:
            trade_date = str(df.iloc[0]['trade_date'])
    except Exception:
        pass

    if not trade_date:
        r.check("找到有效交易日", False, "最近7天无数据")
        return r

    r.check(f"使用交易日: {trade_date}", True)

    # 用日期范围查询每只股票（避免 trade_date 单日查询在非交易日失败）
    for ts_code, name in stocks:
        try:
            td = datetime.strptime(trade_date, '%Y%m%d')
            range_start = (td - timedelta(days=3)).strftime('%Y%m%d')
            range_end = trade_date
            df = tushare_call_api('daily_basic', {
                'ts_code': ts_code,
                'start_date': range_start,
                'end_date': range_end,
                'fields': 'ts_code,trade_date,pe_ttm,pb,total_mv'
            })
            if df is not None and not df.empty:
                # 取最接近 trade_date 的那条
                row = df.iloc[0]
                pe = row.get('pe_ttm')
                pb = row.get('pb')
                mv = row.get('total_mv')
                r.check(f"{name} PE/PB/市值有值",
                        pe is not None or pb is not None,
                        f"PE={pe}, PB={pb}, 市值={mv}")
            else:
                r.check(f"{name} 有数据", False, "返回空")
        except Exception as e:
            r.check(f"{name} 查询成功", False, str(e))

    return r


def main():
    print("#" * 60)
    print("#  数据质量测试 03: Tushare 历史估值数据")
    print("#" * 60)

    results = []

    # 30天历史估值
    results.append(test_historical_valuation('600519.SH', '贵州茅台', 30))
    results.append(test_historical_valuation('000001.SZ', '平安银行', 30))

    # 90天历史估值 (更长周期)
    results.append(test_historical_valuation('600519.SH', '贵州茅台', 90))

    # 跨股票对比
    results.append(test_valuation_cross_stock())

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
