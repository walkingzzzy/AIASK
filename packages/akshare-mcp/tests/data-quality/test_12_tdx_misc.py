# 数据质量测试 12: TDX 其他数据接口质量
# 覆盖: get_ipo_info (新股/新债申购)、get_cb_info (可转债信息)、
#       get_user_sector (自定义板块)、formula_format_data + formula_set_data (公式数据)
# 数据源: TDX
#
# 注意:
# - 写操作 (create_sector/delete_sector/send_message/send_warn 等) 不在此测试范围
# - 实时订阅 (subscribe_hq/unsubscribe_hq) 不适合自动化测试
# - refresh_cache/refresh_kline 会触发客户端UI，不在此测试范围

from config import *
from datetime import datetime


def test_tdx_ipo_info(tq):
    """TDX 新股/新债申购信息 (get_ipo_info)"""
    print("\n" + "=" * 60)
    print("[Test] TDX 新股/新债申购信息")
    print("=" * 60)
    r = TestResult("tdx_ipo_info")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    if not hasattr(tq, 'get_ipo_info'):
        r.warn("get_ipo_info 不可用，跳过")
        return r

    # ipo_type=2 获取新股+新债, ipo_date=1 获取今天及以后
    try:
        result = tq.get_ipo_info(ipo_type=2, ipo_date=1)
        r.check("get_ipo_info 调用成功", True)
    except Exception as e:
        r.check("get_ipo_info 调用成功", False, str(e))
        return r

    if result is None:
        r.warn("返回 None (可能当前无新股/新债申购)")
        return r

    if not isinstance(result, list):
        r.warn(f"返回类型非预期: {type(result).__name__}")
        return r

    r.check("返回列表", True, f"数量: {len(result)}")

    if len(result) > 0:
        first = result[0]
        r.check("数据为字典格式", isinstance(first, dict),
                f"类型: {type(first).__name__}")

        if isinstance(first, dict):
            # 注意: TDX 实际返回字段名首字母大写 (Code/Name/Setcode)
            # 文档样本用小写 (code/name/setcode)，以实际为准
            # 兼容两种写法
            def get_field(d, *names):
                for n in names:
                    if n in d:
                        return d[n]
                return None

            # 核心字段检查
            code_val = get_field(first, 'Code', 'code')
            name_val = get_field(first, 'Name', 'name')
            sg_date = get_field(first, 'SGDate')
            sg_price = get_field(first, 'SGPrice')
            sg_code = get_field(first, 'SGCode')
            setcode_val = get_field(first, 'Setcode', 'setcode')

            r.check("证券代码有值", code_val is not None and str(code_val).strip() != '',
                    f"值: {code_val}")
            r.check("证券名称有值", name_val is not None and str(name_val).strip() != '',
                    f"值: {name_val}")
            r.check("申购日期有值", sg_date is not None and str(sg_date).strip() != '',
                    f"值: {sg_date}")
            r.check("申购价格有值", sg_price is not None, f"值: {sg_price}")
            r.check("申购代码有值", sg_code is not None and str(sg_code).strip() != '',
                    f"值: {sg_code}")

            # 申购价格合理性 (部分新股尚未定价，SGPrice=0.00 是正常的)
            if sg_price:
                try:
                    price_val = float(sg_price)
                    r.check("申购价格 >= 0", price_val >= 0, f"价格: {price_val}")
                    if price_val == 0:
                        r.warn("申购价格为 0 (可能尚未定价)")
                except (ValueError, TypeError):
                    pass

            # 找一条价格 > 0 的记录验证
            priced = [it for it in result if float(get_field(it, 'SGPrice') or 0) > 0]
            if priced:
                p = float(get_field(priced[0], 'SGPrice'))
                r.check("存在已定价记录", True, f"价格: {p}")
            else:
                r.warn("所有记录均未定价")

            # 日期格式 (YYYYMMDD)
            if sg_date:
                r.check("申购日期格式正确", len(str(sg_date)) == 8 and str(sg_date).isdigit(),
                        f"日期: {sg_date}")

            # 市场代码
            r.check("市场代码有值", setcode_val is not None, f"Setcode: {setcode_val}")
    else:
        r.warn("当前无新股/新债申购信息 (列表为空)")

    # 分别测试新股和新债
    for ipo_type, type_name in [(0, '新股'), (1, '新债')]:
        try:
            sub_result = tq.get_ipo_info(ipo_type=ipo_type, ipo_date=1)
            if sub_result and isinstance(sub_result, list):
                r.check(f"{type_name}查询成功", True, f"数量: {len(sub_result)}")
            else:
                r.warn(f"当前无{type_name}申购")
        except Exception as e:
            r.warn(f"{type_name}查询异常: {e}")

    # 测试 ipo_date=0 (仅今天)
    try:
        today_result = tq.get_ipo_info(ipo_type=2, ipo_date=0)
        r.check("今日申购查询成功", True,
                f"数量: {len(today_result) if isinstance(today_result, list) else 0}")
    except Exception as e:
        r.warn(f"今日申购查询异常: {e}")

    return r


def test_tdx_cb_info(tq):
    """TDX 可转债基础信息 (get_cb_info)"""
    print("\n" + "=" * 60)
    print("[Test] TDX 可转债基础信息")
    print("=" * 60)
    r = TestResult("tdx_cb_info")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    if not hasattr(tq, 'get_cb_info'):
        r.warn("get_cb_info 不可用，跳过")
        return r

    # 先获取可转债列表
    cb_codes = []
    try:
        cb_list = tq.get_stock_list(market='32')
        if cb_list and len(cb_list) > 0:
            cb_codes = cb_list[:3]  # 取前3个测试
            r.check("可转债列表获取成功", True, f"总数: {len(cb_list)}")
        else:
            r.warn("可转债列表为空")
    except Exception as e:
        r.warn(f"获取可转债列表失败: {e}")

    if not cb_codes:
        # 使用已知的可转债代码
        cb_codes = ['127063.SZ', '113050.SH']

    for cb_code in cb_codes:
        try:
            result = tq.get_cb_info(stock_code=cb_code)
            has_data = result is not None and isinstance(result, dict) and len(result) > 0
            r.check(f"get_cb_info({cb_code}) 成功", has_data)
        except Exception as e:
            r.check(f"get_cb_info({cb_code}) 成功", False, str(e))
            continue

        if not has_data:
            continue

        # 核心字段检查
        for field, name in [('KZZCode', '可转债代码'), ('HSCode', '正股代码'),
                            ('ZGPrice', '转股价格'), ('EndDate', '到期日期'),
                            ('RestScope', '剩余规模')]:
            val = result.get(field)
            has_val = val is not None and str(val).strip() != ''
            r.check(f"{cb_code} {name} ({field}) 有值", has_val, f"值: {val}")

        # 转股价格 > 0
        zg_price = result.get('ZGPrice')
        if zg_price:
            try:
                zg_val = float(zg_price)
                r.check(f"{cb_code} 转股价格 > 0", zg_val > 0, f"转股价: {zg_val}")
            except (ValueError, TypeError):
                pass

        # 到期日期格式
        end_date = result.get('EndDate', '')
        if end_date and end_date != '0':
            r.check(f"{cb_code} 到期日期格式正确",
                    len(str(end_date)) == 8 and str(end_date).isdigit(),
                    f"到期: {end_date}")

        # 只测试第一个的详细字段
        break

    return r


def test_tdx_user_sector(tq):
    """TDX 自定义板块列表 (get_user_sector) - 只读查询"""
    print("\n" + "=" * 60)
    print("[Test] TDX 自定义板块列表")
    print("=" * 60)
    r = TestResult("tdx_user_sector")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    if not hasattr(tq, 'get_user_sector'):
        r.warn("get_user_sector 不可用，跳过")
        return r

    try:
        result = tq.get_user_sector()
        r.check("get_user_sector 调用成功", True)
    except Exception as e:
        r.check("get_user_sector 调用成功", False, str(e))
        return r

    if result is None:
        r.warn("返回 None (可能无自定义板块)")
        return r

    r.check("返回列表", isinstance(result, list), f"类型: {type(result).__name__}")

    if isinstance(result, list):
        r.check("自定义板块数量", True, f"数量: {len(result)}")
        if len(result) > 0:
            first = result[0]
            r.check("板块数据为字典", isinstance(first, dict),
                    f"类型: {type(first).__name__}")
            if isinstance(first, dict):
                has_code = 'Code' in first
                has_name = 'Name' in first
                r.check("包含 Code 字段", has_code, f"值: {first.get('Code')}")
                r.check("包含 Name 字段", has_name, f"值: {first.get('Name')}")

                # 如果有自定义板块，尝试获取其成份股
                block_code = first.get('Code')
                if block_code and hasattr(tq, 'get_stock_list_in_sector'):
                    try:
                        stocks = tq.get_stock_list_in_sector(block_code, block_type=1)
                        r.check(f"自定义板块 {block_code} 成份股查询成功",
                                stocks is not None,
                                f"成份股数: {len(stocks) if stocks else 0}")
                    except Exception as e:
                        r.warn(f"自定义板块成份股查询异常: {e}")
        else:
            r.warn("无自定义板块 (列表为空)")

    return r


def test_tdx_formula_data_pipeline(tq):
    """TDX 公式数据管道 (formula_format_data + formula_set_data)"""
    print("\n" + "=" * 60)
    print("[Test] TDX 公式数据管道")
    print("=" * 60)
    r = TestResult("tdx_formula_pipeline")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    # 检查公式 API 可用性
    has_format = hasattr(tq, 'formula_format_data')
    has_set = hasattr(tq, 'formula_set_data')
    has_set_info = hasattr(tq, 'formula_set_data_info')
    has_zb = hasattr(tq, 'formula_zb')

    if not has_format:
        r.warn("formula_format_data 不可用 (需在通达信客户端环境运行)，跳过")
        return r

    # Step 1: 获取K线数据
    tdx_code = '600519.SH'
    try:
        kline = tq.get_market_data(
            field_list=[], stock_list=[tdx_code],
            period='1d', count=20, dividend_type='none', fill_data=True
        )
        r.check("获取K线数据成功", kline is not None and 'Close' in kline)
    except Exception as e:
        r.check("获取K线数据成功", False, str(e))
        return r

    # Step 2: 格式化K线数据
    try:
        formatted = tq.formula_format_data(kline)
        has_formatted = formatted is not None and tdx_code in formatted
        r.check("formula_format_data 成功", has_formatted)
    except Exception as e:
        r.check("formula_format_data 成功", False, str(e))
        return r

    if not has_formatted:
        return r

    data_list = formatted[tdx_code]
    r.check("格式化数据非空", len(data_list) > 0, f"数据量: {len(data_list)}")

    if len(data_list) > 0:
        first = data_list[0]
        r.check("格式化数据为字典", isinstance(first, dict))
        # 检查必要字段
        for field in ['Open', 'High', 'Low', 'Close', 'Volume', 'Amount']:
            r.check(f"格式化数据含 {field}", field in first)

    # Step 3: formula_set_data (如果可用)
    if has_set:
        try:
            set_result = tq.formula_set_data(
                stock_code=tdx_code,
                stock_period='1d',
                stock_data=data_list,
                count=len(data_list),
                dividend_type=0
            )
            ok = set_result and set_result.get('ErrorId') == '0'
            r.check("formula_set_data 成功", ok,
                    f"结果: {set_result}")
        except Exception as e:
            r.warn(f"formula_set_data 异常: {e}")
    else:
        r.warn("formula_set_data 不可用，跳过")

    # Step 4: 用 formula_set_data 设置的数据调用 formula_zb
    if has_zb and has_set:
        try:
            zb_result = tq.formula_zb(formula_name='MACD', formula_arg='12,26,9')
            ok = zb_result and zb_result.get('ErrorId') == '0'
            r.check("formula_set_data → formula_zb 联动成功", ok)
            if ok:
                data = zb_result.get('Data', {})
                r.check("MACD 返回 DIF/DEA/MACD", 'DIF' in data and 'DEA' in data,
                        f"字段: {list(data.keys())}")
        except Exception as e:
            r.warn(f"formula_zb 异常: {e}")

    return r


def main():
    print("#" * 60)
    print("#  数据质量测试 12: TDX 其他数据接口质量")
    print("#  覆盖: 新股申购/可转债信息/自定义板块/公式数据管道")
    print("#" * 60)

    tq = init_tdx()

    results = []

    results.append(test_tdx_ipo_info(tq))
    results.append(test_tdx_cb_info(tq))
    results.append(test_tdx_user_sector(tq))
    results.append(test_tdx_formula_data_pipeline(tq))

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
