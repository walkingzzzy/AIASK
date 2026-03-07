# 数据质量测试 02: Tushare 财务数据
# 验证 fina_indicator/income/balancesheet 对沪深两市股票的数据质量
# 对应问题: WARN #2 (fundamental null), WARN #8 (000001 Invalid argument)

from config import *
import pandas as pd


def test_fina_indicator(ts_code, label):
    """财务指标数据质量"""
    print("\n" + "=" * 60)
    print(f"[Test] fina_indicator - {label} ({ts_code})")
    print("=" * 60)
    r = TestResult(f"fina_indicator_{ts_code}")

    try:
        df = tushare_call_api('fina_indicator', {
            'ts_code': ts_code,
            'start_date': '20240101',
            'end_date': '20260208'
        })
        r.check("接口可用", df is not None and not df.empty,
                f"返回 {len(df)} 条" if df is not None and not df.empty else "返回空")
    except Exception as e:
        r.check("接口可用", False, str(e))
        return r

    if df is not None and not df.empty:
        # 核心字段完整性
        core_fields = ['ts_code', 'end_date', 'eps', 'roe', 'grossprofit_margin',
                        'netprofit_margin', 'debt_to_assets', 'current_ratio']
        for field in core_fields:
            has = field in df.columns
            r.check(f"字段 '{field}' 存在", has)
            if has:
                non_null = df[field].notna().sum()
                ratio = non_null / len(df)
                r.check(f"字段 '{field}' 非空率 >= 50%", ratio >= 0.5,
                        f"非空率 {ratio:.1%} ({non_null}/{len(df)})")

        # EPS 值范围检查
        if 'eps' in df.columns:
            valid = df['eps'].dropna().astype(float)
            if len(valid) > 0:
                latest = valid.iloc[0]
                r.check(f"EPS 最新值非零", latest != 0, f"EPS = {latest}")

        # ROE 值范围检查
        if 'roe' in df.columns:
            valid = df['roe'].dropna().astype(float)
            if len(valid) > 0:
                latest = valid.iloc[0]
                r.check(f"ROE 最新值合理 (-100 ~ 100)", -100 <= latest <= 100,
                        f"ROE = {latest:.2f}%")

    return r


def test_income(ts_code, label):
    """利润表数据质量"""
    print("\n" + "=" * 60)
    print(f"[Test] income - {label} ({ts_code})")
    print("=" * 60)
    r = TestResult(f"income_{ts_code}")

    try:
        df = tushare_call_api('income', {
            'ts_code': ts_code,
            'start_date': '20240101',
            'end_date': '20260208'
        })
        r.check("接口可用", df is not None and not df.empty,
                f"返回 {len(df)} 条" if df is not None and not df.empty else "返回空")
    except Exception as e:
        r.check("接口可用", False, str(e))
        return r

    if df is not None and not df.empty:
        core_fields = ['ts_code', 'end_date', 'total_revenue', 'operate_profit', 'n_income']
        for field in core_fields:
            has = field in df.columns
            r.check(f"字段 '{field}' 存在", has)
            if has:
                non_null = df[field].notna().sum()
                ratio = non_null / len(df)
                r.check(f"字段 '{field}' 非空率 >= 50%", ratio >= 0.5,
                        f"非空率 {ratio:.1%}")

        # 营收非零检查
        if 'total_revenue' in df.columns:
            valid = df['total_revenue'].dropna().astype(float)
            if len(valid) > 0:
                latest = valid.iloc[0]
                r.check("营收最新值 > 0", latest > 0, f"营收 = {latest:,.0f}")

    return r


def test_balancesheet(ts_code, label):
    """资产负债表数据质量"""
    print("\n" + "=" * 60)
    print(f"[Test] balancesheet - {label} ({ts_code})")
    print("=" * 60)
    r = TestResult(f"balancesheet_{ts_code}")

    try:
        df = tushare_call_api('balancesheet', {
            'ts_code': ts_code,
            'start_date': '20240101',
            'end_date': '20260208'
        })
        r.check("接口可用", df is not None and not df.empty,
                f"返回 {len(df)} 条" if df is not None and not df.empty else "返回空")
    except Exception as e:
        r.check("接口可用", False, str(e))
        return r

    if df is not None and not df.empty:
        core_fields = ['ts_code', 'end_date', 'total_assets', 'total_liab',
                        'total_hldr_eqy_exc_min_int']
        for field in core_fields:
            has = field in df.columns
            r.check(f"字段 '{field}' 存在", has)
            if has:
                non_null = df[field].notna().sum()
                ratio = non_null / len(df)
                r.check(f"字段 '{field}' 非空率 >= 50%", ratio >= 0.5,
                        f"非空率 {ratio:.1%}")

        # 总资产 > 总负债 检查
        if 'total_assets' in df.columns and 'total_liab' in df.columns:
            row = df.iloc[0]
            assets = float(row.get('total_assets', 0) or 0)
            liab = float(row.get('total_liab', 0) or 0)
            r.check("总资产 > 总负债", assets > liab,
                    f"总资产={assets:,.0f}, 总负债={liab:,.0f}")

    return r


def test_daily_basic_valuation(ts_code, label):
    """每日估值指标 (PE/PB/总市值)"""
    print("\n" + "=" * 60)
    print(f"[Test] daily_basic 估值 - {label} ({ts_code})")
    print("=" * 60)
    r = TestResult(f"daily_basic_{ts_code}")

    try:
        df = tushare_call_api('daily_basic', {
            'ts_code': ts_code,
            'start_date': '20260101',
            'end_date': '20260208'
        })
        r.check("接口可用", df is not None and not df.empty,
                f"返回 {len(df)} 条" if df is not None and not df.empty else "返回空")
    except Exception as e:
        r.check("接口可用", False, str(e))
        return r

    if df is not None and not df.empty:
        # PE/PB/总市值字段
        for field in ['pe', 'pe_ttm', 'pb', 'total_mv', 'circ_mv', 'turnover_rate']:
            has = field in df.columns
            r.check(f"字段 '{field}' 存在", has)
            if has:
                non_null = df[field].notna().sum()
                ratio = non_null / len(df)
                r.check(f"字段 '{field}' 非空率 >= 70%", ratio >= 0.7,
                        f"非空率 {ratio:.1%}")

        # PE 值范围
        if 'pe_ttm' in df.columns:
            valid = df['pe_ttm'].dropna().astype(float)
            if len(valid) > 0:
                latest = valid.iloc[0]
                r.check(f"PE_TTM 值合理 (范围 -1000~10000)", -1000 < latest < 10000,
                        f"PE_TTM = {latest:.2f}")

        # PB 值范围
        if 'pb' in df.columns:
            valid = df['pb'].dropna().astype(float)
            if len(valid) > 0:
                latest = valid.iloc[0]
                r.check(f"PB 值合理 (范围 -100~1000)", -100 < latest < 1000,
                        f"PB = {latest:.2f}")

    return r


def main():
    print("#" * 60)
    print("#  数据质量测试 02: Tushare 财务数据")
    print("#" * 60)

    results = []

    # 沪市: 600519 贵州茅台
    results.append(test_fina_indicator('600519.SH', '贵州茅台'))
    results.append(test_income('600519.SH', '贵州茅台'))
    results.append(test_balancesheet('600519.SH', '贵州茅台'))
    results.append(test_daily_basic_valuation('600519.SH', '贵州茅台'))

    # 深市: 000001 平安银行 (之前报 Invalid argument 的问题股)
    results.append(test_fina_indicator('000001.SZ', '平安银行'))
    results.append(test_income('000001.SZ', '平安银行'))
    results.append(test_balancesheet('000001.SZ', '平安银行'))
    results.append(test_daily_basic_valuation('000001.SZ', '平安银行'))

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
