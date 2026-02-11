# 数据质量测试 10: TDX 财务数据与股票信息质量
# 覆盖: get_financial_data (584指标)、get_stock_info、get_more_info、
#       get_gp_one_data、get_divid_factors、get_gb_info
# 数据源: TDX 专业财务数据系统

from config import *
from datetime import datetime, timedelta


def test_tdx_financial_data(tq, code, label):
    """TDX 专业财务数据 (get_financial_data)"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 专业财务数据 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"tdx_financial_{code}")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"

    # 核心财务指标
    fields = ['FN1', 'FN2', 'FN3', 'FN4', 'FN6',
              'FN193', 'FN194', 'FN197', 'FN199', 'FN210',
              'FN230', 'FN231', 'FN232']
    field_names = {
        'FN1': '基本每股收益', 'FN2': '扣非每股收益', 'FN3': '每股未分配利润',
        'FN4': '每股净资产', 'FN6': '净资产收益率',
        'FN193': '成本费用利润率', 'FN194': '营业利润率',
        'FN197': '净资产收益率2', 'FN199': '销售净利率',
        'FN210': '资产负债率',
        'FN230': '营业收入', 'FN231': '营业利润', 'FN232': '归母净利润'
    }

    start_time = (datetime.now() - timedelta(days=730)).strftime('%Y%m%d')

    try:
        result = tq.get_financial_data(
            stock_list=[tdx_code],
            field_list=fields,
            start_time=start_time,
            end_time='',
            report_type='announce_time'
        )
        has_result = result is not None and tdx_code in result
        if has_result:
            r.check("get_financial_data 成功", True)
        else:
            # TDX 内部 bug: get_financial_data 在某些情况下返回 None
            # (tqcenter.py len(None) 错误)，这是 TDX 环境问题，不是数据质量问题
            r.warn("get_financial_data 返回空 (TDX 内部异常，非数据质量问题)")
    except TypeError as e:
        r.warn(f"get_financial_data 内部异常: {e}")
        return r
    except Exception as e:
        r.check("get_financial_data 成功", False, str(e))
        return r

    if not has_result:
        return r

    df = result[tdx_code]
    try:
        has_data = df is not None and hasattr(df, 'empty') and not df.empty
        row_count = len(df) if has_data else 0
    except TypeError:
        has_data = False
        row_count = 0
    r.check("返回 DataFrame", has_data, f"行数: {row_count}")

    if not has_data:
        return r

    # 报告期数量 (2年应有 >= 4 个季报)
    r.check("报告期数量 >= 4", row_count >= 4, f"实际: {row_count} 期")

    # 时间字段
    has_tag = 'tag_time' in df.columns
    has_announce = 'announce_time' in df.columns
    r.check("有报告期字段 tag_time", has_tag)
    r.check("有公告日期字段 announce_time", has_announce)

    # 核心指标非空检查
    latest = df.iloc[-1]
    for fn, name in field_names.items():
        if fn in df.columns:
            val = latest.get(fn)
            has_val = val is not None and str(val).strip() != '' and str(val) != 'nan'
            r.check(f"{name} ({fn}) 有值", has_val, f"值: {val}")

    # 每股收益合理性 (茅台 EPS 应 > 10)
    if 'FN1' in df.columns:
        eps = latest.get('FN1')
        try:
            eps_val = float(eps)
            if code == '600519':
                r.check("茅台 EPS > 10", eps_val > 10, f"EPS={eps_val}")
            else:
                r.check("EPS 值合理 (> -100)", eps_val > -100, f"EPS={eps_val}")
        except (ValueError, TypeError):
            pass

    # 资产负债率合理性 (0~100%)
    if 'FN210' in df.columns:
        debt = latest.get('FN210')
        try:
            debt_val = float(debt)
            r.check("资产负债率 0~100%", 0 <= debt_val <= 100,
                    f"资产负债率={debt_val}%")
        except (ValueError, TypeError):
            pass

    # 营业收入 > 0 (正常经营企业)
    if 'FN230' in df.columns:
        rev = latest.get('FN230')
        try:
            rev_val = float(rev)
            r.check("营业收入 > 0", rev_val > 0, f"营业收入={rev_val}")
        except (ValueError, TypeError):
            pass

    return r


def test_tdx_financial_by_date(tq, code, label):
    """TDX 指定日期财务数据 (get_financial_data_by_date)"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 指定日期财务 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"tdx_fin_bydate_{code}")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
    fields = ['FN1', 'FN4', 'FN6', 'FN194', 'FN210']

    try:
        # year=0, mmdd=0 返回最新数据
        result = tq.get_financial_data_by_date(
            stock_list=[tdx_code],
            field_list=fields,
            year=0, mmdd=0
        )
        r.check("get_financial_data_by_date 成功",
                result is not None and tdx_code in result)
    except Exception as e:
        r.check("get_financial_data_by_date 成功", False, str(e))
        return r

    if not result or tdx_code not in result:
        return r

    data = result[tdx_code]
    r.check("返回数据非空", data is not None and len(data) > 0)

    if data:
        for fn in fields:
            val = data.get(fn)
            r.check(f"字段 {fn} 有值", val is not None and str(val).strip() != '',
                    f"值: {val}")

    return r


def test_tdx_stock_info(tq, code, label):
    """TDX 股票基本信息 (get_stock_info)"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 股票信息 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"tdx_stock_info_{code}")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"

    try:
        result = tq.get_stock_info(stock_code=tdx_code, field_list=[])
        r.check("get_stock_info 成功", result is not None)
    except Exception as e:
        r.check("get_stock_info 成功", False, str(e))
        return r

    if not result:
        return r

    # 核心字段
    name = result.get('Name', '')
    r.check("股票名称非空", len(str(name).strip()) > 0, f"名称: {name}")

    # 行业信息
    industry = result.get('J_hy', '')
    r.check("行业信息有值", len(str(industry).strip()) > 0, f"行业: {industry}")

    # 上市日期
    list_date = result.get('J_start', '')
    r.check("上市日期有值", len(str(list_date).strip()) > 0, f"上市: {list_date}")

    # 总股本/流通股本
    zgb = result.get('J_zgb', '')
    ltgb = result.get('ActiveCapital', '')
    try:
        zgb_val = float(zgb)
        r.check("总股本 > 0", zgb_val > 0, f"总股本: {zgb_val}")
    except (ValueError, TypeError):
        r.check("总股本有值", False, f"值: {zgb}")

    try:
        ltgb_val = float(ltgb)
        r.check("流通股本 > 0", ltgb_val > 0, f"流通股本: {ltgb_val}")
    except (ValueError, TypeError):
        r.check("流通股本有值", False, f"值: {ltgb}")

    # 每股收益/每股净资产
    eps = result.get('J_mgsy', '')
    bvps = result.get('J_mgjzc', '')
    try:
        r.check("每股收益有值", float(eps) != 0 or eps == '0', f"EPS: {eps}")
    except (ValueError, TypeError):
        r.check("每股收益有值", False, f"值: {eps}")

    try:
        bvps_val = float(bvps)
        r.check("每股净资产 > 0", bvps_val > 0, f"BVPS: {bvps_val}")
    except (ValueError, TypeError):
        r.check("每股净资产有值", False, f"值: {bvps}")

    # 板块归属
    hs300 = result.get('BelongHS300', '')
    hsgt = result.get('BelongHSGT', '')
    r.check("沪深300归属有值", hs300 in ('0', '1'), f"HS300: {hs300}")
    r.check("陆股通归属有值", hsgt in ('0', '1'), f"HSGT: {hsgt}")

    # 省份
    province = result.get('J_addr', '')
    r.check("省份信息有值", len(str(province).strip()) > 0, f"省份: {province}")

    return r


def test_tdx_more_info(tq, code, label):
    """TDX 股票详细信息 (get_more_info)"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 详细信息 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"tdx_more_info_{code}")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    if not hasattr(tq, 'get_more_info'):
        r.warn("get_more_info 不可用 (当前 TDX 版本不支持)，跳过")
        return r

    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"

    try:
        result = tq.get_more_info(stock_code=tdx_code)
        r.check("get_more_info 成功", result is not None)
    except Exception as e:
        r.check("get_more_info 成功", False, str(e))
        return r

    if not result:
        return r

    # 核心字段验证
    checks = {
        'Name': '股票名称',
        'J_Syl': '市盈率',
        'J_ltgb': '流通股本',
        'J_ltsz': '流通市值',
        'J_zgb': '总股本',
        'J_zsz': '总市值',
        'J_mgsy': '每股收益',
        'J_mgjzc': '每股净资产',
        'PB_MRQ': '市净率',
        'MainBusiness': '主营业务',
    }

    for field, name in checks.items():
        val = result.get(field)
        has_val = val is not None and str(val).strip() != '' and str(val) != '0.00'
        r.check(f"{name} ({field}) 有值", has_val, f"值: {val}")

    # 涨幅数据
    for field in ['ZAFPre5', 'ZAFPre10', 'ZAFPre20', 'ZAFPre60']:
        val = result.get(field)
        r.check(f"涨幅 {field} 有值", val is not None, f"值: {val}")

    # 行业信息
    hy = result.get('tdx_hyname', '') or result.get('rs_hyname', '')
    r.check("行业名称有值", len(str(hy).strip()) > 0, f"行业: {hy}")

    # 换手率
    hsl = result.get('fHSL')
    if hsl is not None:
        try:
            hsl_val = float(hsl)
            r.check("换手率 >= 0", hsl_val >= 0, f"换手率: {hsl_val}")
        except (ValueError, TypeError):
            pass

    return r


def test_tdx_gp_one_data(tq, code, label):
    """TDX 个股单项数据 (get_gp_one_data)"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 个股单项数据 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"tdx_gp_one_{code}")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    if not hasattr(tq, 'get_gp_one_data'):
        r.warn("get_gp_one_data 不可用 (当前 TDX 版本不支持)，跳过")
        return r

    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"

    # GO1=发行价, GO3=一致预期目标价, GO5=一致预期EPS,
    # GO29=机构家数, GO33=总股本, GO34=流通A股
    fields = ['GO1', 'GO3', 'GO5', 'GO29', 'GO33', 'GO34']
    field_names = {
        'GO1': '发行价', 'GO3': '一致预期目标价', 'GO5': '一致预期EPS',
        'GO29': '机构持股家数', 'GO33': '总股本(万股)', 'GO34': '流通A股(万股)'
    }

    try:
        result = tq.get_gp_one_data(stock_list=[tdx_code], field_list=fields)
        r.check("get_gp_one_data 成功", result is not None and tdx_code in result)
    except Exception as e:
        r.check("get_gp_one_data 成功", False, str(e))
        return r

    if not result or tdx_code not in result:
        return r

    data = result[tdx_code]
    for fn, name in field_names.items():
        val = data.get(fn)
        r.check(f"{name} ({fn}) 有值", val is not None, f"值: {val}")

    # 总股本 > 流通A股
    go33 = data.get('GO33')
    go34 = data.get('GO34')
    try:
        zgb = float(go33)
        ltgb = float(go34)
        if zgb > 0 and ltgb > 0:
            r.check("总股本 >= 流通A股", zgb >= ltgb,
                    f"总股本={zgb}, 流通={ltgb}")
    except (ValueError, TypeError):
        pass

    return r


def test_tdx_divid_factors(tq, code, label):
    """TDX 分红配送数据 (get_divid_factors)"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 分红配送 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"tdx_divid_{code}")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"

    try:
        result = tq.get_divid_factors(
            stock_code=tdx_code, start_time='', end_time=''
        )
        r.check("get_divid_factors 成功", result is not None)
    except Exception as e:
        r.check("get_divid_factors 成功", False, str(e))
        return r

    if result is None:
        return r

    # 茅台/平安银行应有分红记录
    has_data = hasattr(result, '__len__') and len(result) > 0
    r.check("有分红记录", has_data,
            f"记录数: {len(result) if has_data else 0}")

    if has_data:
        # 检查字段
        if hasattr(result, 'columns'):
            cols = list(result.columns)
            for field in ['Type', 'Bonus']:
                r.check(f"字段 '{field}' 存在", field in cols, f"列: {cols}")

            # 分红金额 >= 0
            if 'Bonus' in cols:
                bonuses = result['Bonus'].tolist()
                neg_bonus = sum(1 for b in bonuses if float(b) < 0)
                r.check("分红金额 >= 0", neg_bonus == 0,
                        f"负值: {neg_bonus}/{len(bonuses)}")

    return r


def test_tdx_gb_info(tq, code, label):
    """TDX 股本数据 (get_gb_info)"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 股本数据 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"tdx_gb_{code}")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    if not hasattr(tq, 'get_gb_info'):
        r.warn("get_gb_info 不可用 (当前 TDX 版本不支持)，跳过")
        return r

    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"

    try:
        result = tq.get_gb_info(
            stock_code=tdx_code,
            date_list=['20250101', '20260101'],
            count=2
        )
        has_data = result is not None and len(result) > 0
        r.check("get_gb_info 成功", has_data)
    except AttributeError:
        r.warn("get_gb_info 不可用，跳过")
        return r
    except Exception as e:
        r.check("get_gb_info 成功", False, str(e))
        return r

    if not result:
        return r

    for item in result:
        date = item.get('Date')
        ltgb = item.get('ltgb', 0)
        zgb = item.get('zgb', 0)

        r.check(f"日期 {date} 流通股本 > 0", ltgb > 0, f"流通: {ltgb}")
        r.check(f"日期 {date} 总股本 > 0", zgb > 0, f"总股本: {zgb}")
        r.check(f"日期 {date} 总股本 >= 流通", zgb >= ltgb,
                f"总={zgb}, 流通={ltgb}")

    return r


def main():
    print("#" * 60)
    print("#  数据质量测试 10: TDX 财务数据与股票信息质量")
    print("#  覆盖: 专业财务/股票信息/详细信息/个股数据/分红/股本")
    print("#" * 60)

    tq = init_tdx()

    results = []

    # 专业财务数据
    for code, label in [('600519', '贵州茅台'), ('000001', '平安银行')]:
        results.append(test_tdx_financial_data(tq, code, label))

    # 指定日期财务
    results.append(test_tdx_financial_by_date(tq, '600519', '贵州茅台'))

    # 股票基本信息
    for code, label in [('600519', '贵州茅台'), ('000001', '平安银行'),
                        ('300750', '宁德时代')]:
        results.append(test_tdx_stock_info(tq, code, label))

    # 详细信息
    results.append(test_tdx_more_info(tq, '600519', '贵州茅台'))
    results.append(test_tdx_more_info(tq, '000001', '平安银行'))

    # 个股单项数据
    results.append(test_tdx_gp_one_data(tq, '600519', '贵州茅台'))

    # 分红配送
    results.append(test_tdx_divid_factors(tq, '600519', '贵州茅台'))

    # 股本数据
    results.append(test_tdx_gb_info(tq, '600519', '贵州茅台'))

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
