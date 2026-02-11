# 数据质量测试 01: Tushare 宏观经济数据
# 验证 CPI/PPI/M2/SHIBOR 数据可用性和字段完整性
# 使用代理实际支持的 API 名称: cn_cpi / cn_ppi / cn_m / shibor

from config import *
import pandas as pd


def test_cpi():
    """CPI 消费者物价指数"""
    print("\n" + "=" * 60)
    print("[Test 1] CPI 数据质量 (cn_cpi)")
    print("=" * 60)
    r = TestResult("CPI")

    # 代理 API 名称: cn_cpi
    try:
        df = tushare_call_api('cn_cpi')
        has_data = df is not None and not df.empty
        r.check("cn_cpi 接口可用", has_data,
                f"返回 {len(df)} 条" if has_data else "返回空")
    except Exception as e:
        r.check("cn_cpi 接口可用", False, str(e))
        return r

    if df is not None and not df.empty:
        print(f"  可用字段: {list(df.columns)}")
        # 核心字段
        for field in ['month', 'nt_val', 'nt_yoy', 'nt_mom']:
            has = field in df.columns
            r.check(f"字段 '{field}' 存在", has)
            if has:
                ratio = df[field].notna().sum() / len(df)
                r.check(f"字段 '{field}' 非空率 >= 70%", ratio >= 0.7,
                        f"非空率 {ratio:.1%}")

        # 最新值检查
        if 'nt_val' in df.columns:
            latest = df.iloc[0].get('nt_val')
            r.check("CPI 最新值合理 (90~120)", 90 <= float(latest) <= 120,
                    f"最新值: {latest}")

    return r


def test_ppi():
    """PPI 生产者物价指数"""
    print("\n" + "=" * 60)
    print("[Test 2] PPI 数据质量 (cn_ppi)")
    print("=" * 60)
    r = TestResult("PPI")

    try:
        df = tushare_call_api('cn_ppi')
        has_data = df is not None and not df.empty
        r.check("cn_ppi 接口可用", has_data,
                f"返回 {len(df)} 条" if has_data else "返回空")
    except Exception as e:
        r.check("cn_ppi 接口可用", False, str(e))
        return r

    if df is not None and not df.empty:
        print(f"  可用字段: {list(df.columns[:8])}...")
        for field in ['month', 'ppi_yoy', 'ppi_mom']:
            has = field in df.columns
            r.check(f"字段 '{field}' 存在", has)
            if has:
                ratio = df[field].notna().sum() / len(df)
                r.check(f"字段 '{field}' 非空率 >= 70%", ratio >= 0.7,
                        f"非空率 {ratio:.1%}")

    return r


def test_money_supply():
    """M2 货币供应量"""
    print("\n" + "=" * 60)
    print("[Test 3] M2 货币供应量数据质量 (cn_m)")
    print("=" * 60)
    r = TestResult("M2")

    # 代理 API 名称: cn_m
    try:
        df = tushare_call_api('cn_m')
        has_data = df is not None and not df.empty
        r.check("cn_m 接口可用", has_data,
                f"返回 {len(df)} 条" if has_data else "返回空")
    except Exception as e:
        r.check("cn_m 接口可用", False, str(e))
        return r

    if df is not None and not df.empty:
        print(f"  可用字段: {list(df.columns)}")
        for field in ['month', 'm2', 'm2_yoy', 'm2_mom']:
            has = field in df.columns
            r.check(f"字段 '{field}' 存在", has)
            if has:
                ratio = df[field].notna().sum() / len(df)
                r.check(f"字段 '{field}' 非空率 >= 70%", ratio >= 0.7,
                        f"非空率 {ratio:.1%}")

        # M2 值范围检查
        if 'm2' in df.columns:
            valid = df['m2'].dropna()
            if len(valid) > 0:
                latest = float(valid.iloc[0])
                r.check("M2 最新值合理 (> 0)", latest > 0, f"最新值: {latest:,.0f}")

    return r


def test_shibor():
    """SHIBOR 上海银行间同业拆放利率"""
    print("\n" + "=" * 60)
    print("[Test 4] SHIBOR 数据质量")
    print("=" * 60)
    r = TestResult("SHIBOR")

    try:
        df = tushare_call_api('shibor')
        has_data = df is not None and not df.empty
        r.check("shibor 接口可用", has_data,
                f"返回 {len(df)} 条" if has_data else "返回空")
    except Exception as e:
        r.check("shibor 接口可用", False, str(e))
        return r

    if df is not None and not df.empty:
        for field in ['date', 'on', '1w', '1m']:
            has = field in df.columns
            r.check(f"字段 '{field}' 存在", has)
            if has:
                ratio = df[field].notna().sum() / len(df)
                r.check(f"字段 '{field}' 非空率 >= 80%", ratio >= 0.8,
                        f"非空率 {ratio:.1%}")

        if 'on' in df.columns:
            valid = df['on'].dropna().astype(float)
            if len(valid) > 0:
                min_v, max_v = valid.min(), valid.max()
                r.check("隔夜利率范围合理 (0 ~ 15)", 0 <= min_v and max_v <= 15,
                        f"范围: [{min_v:.4f}, {max_v:.4f}]")

    return r


def main():
    print("#" * 60)
    print("#  数据质量测试 01: Tushare 宏观经济数据")
    print("#  使用代理 API: cn_cpi / cn_ppi / cn_m / shibor")
    print("#" * 60)

    results = [test_cpi(), test_ppi(), test_money_supply(), test_shibor()]

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
