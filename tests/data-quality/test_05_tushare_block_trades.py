# 数据质量测试 05: Tushare 大宗交易 + 名称映射
# 验证 block_trade 数据和 stock_basic 名称映射
# 对应问题: WARN #7 (get_block_trades name 为空)

from config import *
import pandas as pd
from datetime import datetime, timedelta


def test_block_trade_data():
    """大宗交易数据可用性"""
    print("\n" + "=" * 60)
    print("[Test 1] block_trade 数据可用性")
    print("=" * 60)
    r = TestResult("block_trade")

    found_date = None
    found_df = None

    for days_back in range(10):
        check_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
        try:
            df = tushare_call_api('block_trade', {'trade_date': check_date})
            if df is not None and not df.empty:
                found_date = check_date
                found_df = df
                break
        except Exception:
            continue

    r.check("找到有数据的交易日", found_date is not None,
            f"日期: {found_date}" if found_date else "最近10天无数据")

    if found_df is None or found_df.empty:
        return r

    r.check(f"数据量 > 0", len(found_df) > 0, f"共 {len(found_df)} 条")

    # 字段检查
    core_fields = ['ts_code', 'trade_date', 'price', 'vol', 'amount']
    for field in core_fields:
        has = field in found_df.columns
        r.check(f"字段 '{field}' 存在", has)

    # 名称字段检查 (这是核心问题)
    if 'name' in found_df.columns:
        name_valid = (found_df['name'].notna() & (found_df['name'] != '')).sum()
        name_ratio = name_valid / len(found_df)
        r.check(f"name 字段有值率 >= 50%", name_ratio >= 0.5,
                f"有值: {name_valid}/{len(found_df)} ({name_ratio:.1%})")
    else:
        r.warn("block_trade 无 name 字段 (需要从 stock_basic 补充)")

    # 价格非零检查
    if 'price' in found_df.columns:
        price_zero = (found_df['price'].astype(float) == 0).sum()
        r.check("price 非零", price_zero == 0,
                f"为零: {price_zero}/{len(found_df)}")

    return r


def test_stock_basic_name_mapping():
    """stock_basic 名称映射完整性"""
    print("\n" + "=" * 60)
    print("[Test 2] stock_basic 名称映射")
    print("=" * 60)
    r = TestResult("stock_basic_name")

    try:
        df = tushare_call_api('stock_basic', {
            'exchange': '',
            'list_status': 'L',
        }, fields='ts_code,symbol,name,industry')
        r.check("stock_basic 接口可用", df is not None and not df.empty,
                f"返回 {len(df)} 条" if df is not None and not df.empty else "返回空")
    except Exception as e:
        r.check("stock_basic 接口可用", False, str(e))
        return r

    if df is None or df.empty:
        return r

    # 名称完整性
    name_valid = (df['name'].notna() & (df['name'] != '')).sum()
    name_ratio = name_valid / len(df)
    r.check(f"name 非空率 >= 99%", name_ratio >= 0.99,
            f"非空率 {name_ratio:.1%} ({name_valid}/{len(df)})")

    # 测试特定股票名称
    test_codes = {
        '600519.SH': '贵州茅台',
        '000001.SZ': '平安银行',
        '000858.SZ': '五粮液',
    }
    for ts_code, expected_name in test_codes.items():
        match = df[df['ts_code'] == ts_code]
        if not match.empty:
            actual_name = match.iloc[0]['name']
            r.check(f"{ts_code} 名称正确", expected_name in str(actual_name),
                    f"期望含'{expected_name}', 实际'{actual_name}'")
        else:
            r.check(f"{ts_code} 存在", False)

    # 行业字段
    if 'industry' in df.columns:
        industry_valid = (df['industry'].notna() & (df['industry'] != '')).sum()
        industry_ratio = industry_valid / len(df)
        r.check(f"industry 非空率 >= 80%", industry_ratio >= 0.8,
                f"非空率 {industry_ratio:.1%}")

    return r


def test_name_join_simulation():
    """模拟大宗交易 + 名称 JOIN"""
    print("\n" + "=" * 60)
    print("[Test 3] 大宗交易名称补全模拟")
    print("=" * 60)
    r = TestResult("name_join")

    # 获取大宗交易
    trade_df = None
    for days_back in range(10):
        check_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
        try:
            trade_df = tushare_call_api('block_trade', {'trade_date': check_date})
            if trade_df is not None and not trade_df.empty:
                break
        except Exception:
            continue

    if trade_df is None or trade_df.empty:
        r.check("有大宗交易数据", False)
        return r

    # 获取名称映射
    try:
        basic_df = tushare_call_api('stock_basic', {
            'exchange': '', 'list_status': 'L'
        }, fields='ts_code,name')
    except Exception as e:
        r.check("stock_basic 可用", False, str(e))
        return r

    if basic_df is None or basic_df.empty:
        r.check("stock_basic 有数据", False)
        return r

    # 构建名称映射
    name_map = {}
    for _, row in basic_df.iterrows():
        code = str(row.get('ts_code', '')).split('.')[0]
        name = str(row.get('name', '') or '')
        if code and name:
            name_map[code] = name

    # 模拟补全
    total = len(trade_df)
    matched = 0
    for _, row in trade_df.iterrows():
        ts_code = str(row.get('ts_code', ''))
        code = ts_code.split('.')[0]
        if code in name_map:
            matched += 1

    match_ratio = matched / total if total > 0 else 0
    r.check(f"名称匹配率 >= 90%", match_ratio >= 0.9,
            f"匹配: {matched}/{total} ({match_ratio:.1%})")

    return r


def main():
    print("#" * 60)
    print("#  数据质量测试 05: Tushare 大宗交易 + 名称映射")
    print("#" * 60)

    results = [
        test_block_trade_data(),
        test_stock_basic_name_mapping(),
        test_name_join_simulation(),
    ]

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
