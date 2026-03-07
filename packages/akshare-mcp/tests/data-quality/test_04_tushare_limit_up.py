# 数据质量测试 04: Tushare 涨停板数据
# 验证 stk_limit + daily 组合方案的涨停筛选能力
# 对应问题: WARN #10/#11/#14 (涨停统计全0, 连板天数不可用)

from config import *
import pandas as pd
from datetime import datetime, timedelta


def test_stk_limit_and_daily():
    """stk_limit + daily 组合可用性"""
    print("\n" + "=" * 60)
    print("[Test 1] stk_limit + daily 组合可用性")
    print("=" * 60)
    r = TestResult("stk_limit_daily_combo")

    found_date = None
    limit_df = None
    daily_df = None

    for days_back in range(10):
        check_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
        try:
            ldf = tushare_call_api('stk_limit', {'trade_date': check_date})
            if ldf is None or ldf.empty:
                continue
            ddf = tushare_call_api('daily', {'trade_date': check_date},
                                   fields='ts_code,trade_date,close,pct_chg,vol')
            if ddf is None or ddf.empty:
                continue
            found_date = check_date
            limit_df = ldf
            daily_df = ddf
            break
        except Exception:
            continue

    r.check("找到有数据的交易日", found_date is not None,
            f"日期: {found_date}" if found_date else "最近10天无数据")

    if limit_df is None or daily_df is None:
        return r, None, None, None

    r.check(f"stk_limit 数据量 > 0", len(limit_df) > 0, f"共 {len(limit_df)} 条")
    r.check(f"daily 数据量 > 0", len(daily_df) > 0, f"共 {len(daily_df)} 条")

    # stk_limit 可用字段
    print(f"  stk_limit 字段: {list(limit_df.columns)}")
    print(f"  daily 字段: {list(daily_df.columns)}")

    return r, limit_df, daily_df, found_date


def test_limit_up_detection(limit_df, daily_df, date_str):
    """涨停股检测 (close >= up_limit)"""
    print("\n" + "=" * 60)
    print(f"[Test 2] 涨停股检测 ({date_str})")
    print("=" * 60)
    r = TestResult("limit_up_detection")

    # 合并
    merged = pd.merge(limit_df, daily_df, on='ts_code', how='inner',
                      suffixes=('_limit', '_daily'))
    r.check("合并成功", len(merged) > 0, f"合并后 {len(merged)} 条")

    if merged.empty:
        return r, pd.DataFrame()

    # 转数值
    merged['close_f'] = pd.to_numeric(merged['close'], errors='coerce').fillna(0)
    merged['up_limit_f'] = pd.to_numeric(merged['up_limit'], errors='coerce').fillna(0)
    merged['pct_chg_f'] = pd.to_numeric(merged.get('pct_chg', pd.Series(dtype=float)), errors='coerce').fillna(0)

    # 筛选涨停: close >= up_limit - 0.01
    up_mask = (merged['up_limit_f'] > 0) & (merged['close_f'] >= merged['up_limit_f'] - 0.01)
    up_df = merged[up_mask]

    r.check("涨停股数量 > 0", len(up_df) > 0, f"涨停: {len(up_df)} 只")

    if len(up_df) > 0:
        # 涨停股涨幅检查
        pct_values = up_df['pct_chg_f']
        avg_pct = pct_values.mean()
        r.check("涨停股平均涨幅 >= 9%", avg_pct >= 9.0,
                f"平均涨幅: {avg_pct:.2f}%")

        # 涨停股价格非零
        close_zero = (up_df['close_f'] == 0).sum()
        r.check("涨停股 close 非零", close_zero == 0,
                f"为零: {close_zero}/{len(up_df)}")

        # 打印前5只
        print(f"\n  前5只涨停股:")
        for _, row in up_df.head(5).iterrows():
            ts_code = row.get('ts_code', '')
            close = row.get('close_f', 0)
            up_limit = row.get('up_limit_f', 0)
            pct = row.get('pct_chg_f', 0)
            print(f"    {ts_code}: close={close}, up_limit={up_limit}, pct_chg={pct:.2f}%")

    # 跌停检测
    down_limit_f = pd.to_numeric(merged.get('down_limit', pd.Series(dtype=float)), errors='coerce').fillna(0)
    down_mask = (down_limit_f > 0) & (merged['close_f'] <= down_limit_f + 0.01) & (merged['close_f'] > 0)
    down_df = merged[down_mask]
    r.check("跌停股检测", True, f"跌停: {len(down_df)} 只")

    return r, up_df


def test_name_supplement(up_df):
    """名称补全测试"""
    print("\n" + "=" * 60)
    print("[Test 3] 涨停股名称补全")
    print("=" * 60)
    r = TestResult("name_supplement")

    if up_df is None or up_df.empty:
        r.check("有涨停股数据", False)
        return r

    # 获取 stock_basic 名称映射
    try:
        basic_df = tushare_call_api('stock_basic', {'exchange': '', 'list_status': 'L'},
                                     fields='ts_code,name')
        r.check("stock_basic 可用", basic_df is not None and not basic_df.empty)
    except Exception as e:
        r.check("stock_basic 可用", False, str(e))
        return r

    if basic_df is None or basic_df.empty:
        return r

    name_map = {}
    for _, row in basic_df.iterrows():
        code = str(row.get('ts_code', '')).split('.')[0]
        name = str(row.get('name', '') or '')
        if code and name:
            name_map[code] = name

    # 匹配率
    matched = 0
    for _, row in up_df.iterrows():
        code = str(row.get('ts_code', '')).split('.')[0]
        if code in name_map:
            matched += 1

    match_ratio = matched / len(up_df) if len(up_df) > 0 else 0
    r.check(f"涨停股名称匹配率 >= 90%", match_ratio >= 0.9,
            f"匹配: {matched}/{len(up_df)} ({match_ratio:.1%})")

    # 打印前5只带名称
    print(f"\n  前5只涨停股 (带名称):")
    for _, row in up_df.head(5).iterrows():
        ts_code = row.get('ts_code', '')
        code = ts_code.split('.')[0]
        name = name_map.get(code, '?')
        close = row.get('close_f', 0)
        pct = row.get('pct_chg_f', 0)
        print(f"    {code} {name}: close={close}, pct_chg={pct:.2f}%")

    return r


def test_continuous_days_calculation(limit_df, daily_df, date_str):
    """连板天数计算测试"""
    print("\n" + "=" * 60)
    print(f"[Test 4] 连板天数计算 ({date_str})")
    print("=" * 60)
    r = TestResult("continuous_days")

    # 先找出当天涨停股
    merged = pd.merge(limit_df, daily_df, on='ts_code', how='inner')
    merged['close_f'] = pd.to_numeric(merged['close'], errors='coerce').fillna(0)
    merged['up_limit_f'] = pd.to_numeric(merged['up_limit'], errors='coerce').fillna(0)
    up_mask = (merged['up_limit_f'] > 0) & (merged['close_f'] >= merged['up_limit_f'] - 0.01)
    up_codes = set()
    for _, row in merged[up_mask].iterrows():
        up_codes.add(str(row.get('ts_code', '')).split('.')[0])

    r.check("当天涨停股数量 > 0", len(up_codes) > 0, f"{len(up_codes)} 只")

    if not up_codes:
        return r

    # 往前查 1 天看是否有连板
    base = datetime.strptime(date_str, '%Y%m%d').date()
    found_prev = False
    prev_up_codes = set()

    for days_back in range(1, 5):
        prev_date = (base - timedelta(days=days_back)).strftime('%Y%m%d')
        try:
            prev_limit = tushare_call_api('stk_limit', {'trade_date': prev_date})
            prev_daily = tushare_call_api('daily', {'trade_date': prev_date}, fields='ts_code,close')
            if prev_limit is None or prev_limit.empty or prev_daily is None or prev_daily.empty:
                continue
            prev_merged = pd.merge(prev_limit, prev_daily, on='ts_code', how='inner')
            prev_merged['close_f'] = pd.to_numeric(prev_merged['close'], errors='coerce').fillna(0)
            prev_merged['up_limit_f'] = pd.to_numeric(prev_merged['up_limit'], errors='coerce').fillna(0)
            prev_up = (prev_merged['up_limit_f'] > 0) & (prev_merged['close_f'] >= prev_merged['up_limit_f'] - 0.01)
            for _, row in prev_merged[prev_up].iterrows():
                prev_up_codes.add(str(row.get('ts_code', '')).split('.')[0])
            found_prev = True
            break
        except Exception:
            continue

    if found_prev:
        # 连板 = 今天涨停 且 昨天也涨停
        continuous = up_codes & prev_up_codes
        r.check("连板计算可行", True,
                f"今日涨停: {len(up_codes)}, 前日涨停: {len(prev_up_codes)}, 连板: {len(continuous)}")
        if continuous:
            print(f"  连板股票: {list(continuous)[:10]}")
    else:
        r.warn("未找到前一交易日数据")

    return r


def main():
    print("#" * 60)
    print("#  数据质量测试 04: Tushare 涨停板数据")
    print("#  方案: stk_limit + daily 组合检测涨停")
    print("#" * 60)

    results = []

    result1, limit_df, daily_df, date_str = test_stk_limit_and_daily()
    results.append(result1)

    if limit_df is not None and daily_df is not None:
        r2, up_df = test_limit_up_detection(limit_df, daily_df, date_str)
        results.append(r2)
        results.append(test_name_supplement(up_df))
        results.append(test_continuous_days_calculation(limit_df, daily_df, date_str))
    else:
        print("\n  [SKIP] 无数据，跳过后续测试")

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
