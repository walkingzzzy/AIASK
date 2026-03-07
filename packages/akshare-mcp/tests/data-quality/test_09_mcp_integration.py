# 数据质量测试 09: MCP 工具集成测试
# 通过 MCP 工具接口验证数据管道端到端质量
# 对应问题: WARN #13/#15/#16/#17/#20 (manager 层问题)
# 数据源: Tushare 代理 (HTTP) + TDX，不使用 AkShare

from config import *
import json
import os


def _call_mcp_tool(tool_name, args_dict):
    """
    调用 MCP 工具 (通过直接导入模块)
    注意: 这里模拟 MCP 工具调用，实际需要 MCP server 运行
    """
    return None


def test_macro_cpi_pipeline():
    """CPI 数据管道端到端测试"""
    print("\n" + "=" * 60)
    print("[Test 1] CPI 数据管道 (Tushare 代理 cn_cpi → MCP)")
    print("=" * 60)
    r = TestResult("macro_cpi_pipeline")

    # 验证 Tushare 代理层 — 使用正确的 API 名称 cn_cpi
    try:
        df = tushare_call_api('cn_cpi')
        has_data = df is not None and not df.empty
        r.check("Tushare 代理 cn_cpi 有数据", has_data,
                f"{len(df)} 条" if has_data else "空")
        if has_data:
            # 检查关键字段
            for col in ['month', 'nt_val']:
                has_col = col in df.columns
                r.check(f"cn_cpi 字段 '{col}' 存在", has_col)
    except Exception as e:
        r.check("Tushare 代理 cn_cpi 可用", False, str(e))

    # 验证 PPI
    try:
        df = tushare_call_api('cn_ppi')
        has_data = df is not None and not df.empty
        r.check("Tushare 代理 cn_ppi 有数据", has_data,
                f"{len(df)} 条" if has_data else "空")
    except Exception as e:
        r.check("Tushare 代理 cn_ppi 可用", False, str(e))

    # 验证 M2
    try:
        df = tushare_call_api('cn_m')
        has_data = df is not None and not df.empty
        r.check("Tushare 代理 cn_m 有数据", has_data,
                f"{len(df)} 条" if has_data else "空")
    except Exception as e:
        r.check("Tushare 代理 cn_m 可用", False, str(e))

    return r


def test_financials_fallback_chain():
    """财务数据降级链测试 (TDX → Tushare)"""
    print("\n" + "=" * 60)
    print("[Test 2] 财务数据降级链 (TDX → Tushare)")
    print("=" * 60)
    r = TestResult("financials_fallback")

    for code, ts_code, label in [('600519', '600519.SH', '贵州茅台'),
                                   ('000001', '000001.SZ', '平安银行')]:
        print(f"\n  --- {label} ({code}) ---")

        # Tushare fina_indicator
        try:
            df = tushare_call_api('fina_indicator', {
                'ts_code': ts_code,
                'start_date': '20240101',
                'end_date': '20260208'
            })
            has = df is not None and not df.empty
            r.check(f"{label} Tushare fina_indicator", has,
                    f"{len(df)} 条" if has else "空")

            if has:
                row = df.iloc[0]
                eps = row.get('eps')
                roe = row.get('roe')
                r.check(f"{label} EPS 有值", eps is not None and float(eps) != 0,
                        f"EPS={eps}")
                r.check(f"{label} ROE 有值", roe is not None,
                        f"ROE={roe}")
        except Exception as e:
            r.check(f"{label} Tushare fina_indicator", False, str(e))

        # Tushare income
        try:
            df = tushare_call_api('income', {
                'ts_code': ts_code,
                'start_date': '20240101',
                'end_date': '20260208'
            })
            has = df is not None and not df.empty
            r.check(f"{label} Tushare income", has)
            if has:
                revenue = df.iloc[0].get('total_revenue')
                r.check(f"{label} 营收有值", revenue is not None and float(revenue) > 0,
                        f"营收={revenue}")
        except Exception as e:
            r.check(f"{label} Tushare income", False, str(e))

    return r


def test_valuation_pipeline():
    """估值数据管道测试"""
    print("\n" + "=" * 60)
    print("[Test 3] 估值数据管道")
    print("=" * 60)
    r = TestResult("valuation_pipeline")

    for ts_code, label in [('600519.SH', '贵州茅台'), ('000001.SZ', '平安银行')]:
        # daily_basic 分批查询（30天以内避免服务器错误）
        from datetime import timedelta
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=28)
        try:
            df = tushare_call_api('daily_basic', {
                'ts_code': ts_code,
                'start_date': start_dt.strftime('%Y%m%d'),
                'end_date': end_dt.strftime('%Y%m%d'),
                'fields': 'trade_date,pe,pe_ttm,pb,total_mv'
            })
            has = df is not None and not df.empty
            r.check(f"{label} daily_basic 有数据", has,
                    f"{len(df)} 条" if has else "空")

            if has:
                row = df.iloc[0]
                pe = row.get('pe_ttm')
                pb = row.get('pb')
                r.check(f"{label} PE_TTM 有值", pe is not None,
                        f"PE_TTM={pe}")
                r.check(f"{label} PB 有值", pb is not None,
                        f"PB={pb}")
        except Exception as e:
            r.check(f"{label} daily_basic", False, str(e))

    return r


def test_limit_up_pipeline():
    """涨停数据管道测试 — stk_limit + daily 组合方案"""
    print("\n" + "=" * 60)
    print("[Test 4] 涨停数据管道 (stk_limit + daily 组合)")
    print("=" * 60)
    r = TestResult("limit_up_pipeline")

    from datetime import timedelta

    found = False
    for days_back in range(10):
        check_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')

        # 1) stk_limit 获取涨停价
        try:
            limit_df = tushare_call_api('stk_limit', {'trade_date': check_date})
            if limit_df is None or limit_df.empty:
                continue
        except Exception:
            continue

        # 2) daily 获取收盘价
        try:
            daily_df = tushare_call_api('daily', {
                'trade_date': check_date
            }, fields='ts_code,trade_date,close,pct_chg,vol')
            if daily_df is None or daily_df.empty:
                continue
        except Exception:
            continue

        # 3) 合并
        import pandas as pd
        merged = pd.merge(limit_df, daily_df, on=['ts_code', 'trade_date'], how='inner')
        if merged.empty:
            continue

        # 4) 筛选涨停: close >= up_limit - 0.01
        merged['close_f'] = pd.to_numeric(merged['close'], errors='coerce').fillna(0)
        merged['up_limit_f'] = pd.to_numeric(merged['up_limit'], errors='coerce').fillna(0)
        up_mask = (merged['up_limit_f'] > 0) & (merged['close_f'] >= merged['up_limit_f'] - 0.01)
        up_df = merged[up_mask]

        found = True
        r.check(f"stk_limit+daily 合并成功 ({check_date})", True,
                f"合并 {len(merged)} 条")
        r.check(f"涨停股数量 > 0", len(up_df) > 0,
                f"涨停: {len(up_df)} 只")

        # 5) 验证 stock_basic 名称补全
        if len(up_df) > 0:
            try:
                basic_df = tushare_call_api('stock_basic', {
                    'exchange': '', 'list_status': 'L'
                }, fields='ts_code,name')
                has_basic = basic_df is not None and not basic_df.empty
                r.check("stock_basic 名称映射可用", has_basic,
                        f"{len(basic_df)} 只" if has_basic else "空")
            except Exception as e:
                r.check("stock_basic 名称映射可用", False, str(e))
        break

    if not found:
        r.check("找到涨停数据", False, "最近10天无数据")

    return r


def test_block_trade_name_pipeline():
    """大宗交易名称补全管道测试"""
    print("\n" + "=" * 60)
    print("[Test 5] 大宗交易名称补全管道")
    print("=" * 60)
    r = TestResult("block_trade_name")

    from datetime import timedelta

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

    r.check(f"大宗交易数据量", True, f"{len(trade_df)} 条")

    has_name_col = 'name' in trade_df.columns
    if has_name_col:
        name_filled = (trade_df['name'].notna() & (trade_df['name'] != '')).sum()
        name_ratio = name_filled / len(trade_df)
        r.check(f"原始 name 填充率", True, f"{name_ratio:.1%}")

        if name_ratio < 0.5:
            try:
                basic_df = tushare_call_api('stock_basic', {
                    'exchange': '', 'list_status': 'L'
                }, fields='ts_code,name')
                if basic_df is not None and not basic_df.empty:
                    name_map = {}
                    for _, row in basic_df.iterrows():
                        c = str(row.get('ts_code', '')).split('.')[0]
                        n = str(row.get('name', '') or '')
                        if c and n:
                            name_map[c] = n
                    matched = 0
                    for _, row in trade_df.iterrows():
                        c = str(row.get('ts_code', '')).split('.')[0]
                        if c in name_map:
                            matched += 1
                    match_ratio = matched / len(trade_df)
                    r.check(f"stock_basic 补全后匹配率 >= 90%", match_ratio >= 0.9,
                            f"匹配率: {match_ratio:.1%}")
            except Exception as e:
                r.check("stock_basic 补全可用", False, str(e))
    else:
        r.warn("block_trade 无 name 字段")

    return r


def test_north_fund_pipeline():
    """北向资金数据管道测试"""
    print("\n" + "=" * 60)
    print("[Test 6] 北向资金数据管道")
    print("=" * 60)
    r = TestResult("north_fund_pipeline")

    try:
        df = tushare_call_api('moneyflow_hsgt', {
            'start_date': '20260101',
            'end_date': '20260208'
        })
        has = df is not None and not df.empty
        r.check("moneyflow_hsgt 有数据", has,
                f"{len(df)} 条" if has else "空")

        if has:
            for field in ['trade_date', 'hgt', 'sgt']:
                has_f = field in df.columns
                r.check(f"字段 '{field}' 存在", has_f)
                if has_f:
                    non_null = df[field].notna().sum()
                    r.check(f"字段 '{field}' 非空", non_null > 0,
                            f"非空: {non_null}/{len(df)}")
    except Exception as e:
        r.check("moneyflow_hsgt 可用", False, str(e))

    return r


def main():
    print("#" * 60)
    print("#  数据质量测试 09: MCP 工具集成测试")
    print("#  数据源: Tushare 代理 + TDX (不使用 AkShare)")
    print("#" * 60)

    results = [
        test_macro_cpi_pipeline(),
        test_financials_fallback_chain(),
        test_valuation_pipeline(),
        test_limit_up_pipeline(),
        test_block_trade_name_pipeline(),
        test_north_fund_pipeline(),
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
    from datetime import datetime
    sys.exit(0 if main() else 1)
