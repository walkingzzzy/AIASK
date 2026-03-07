# 数据质量测试 11: TDX 交易数据与市场数据质量
# 覆盖: get_gpjy_value (龙虎榜/融资融券/陆股通/大宗交易)、
#       get_scjy_value (涨跌停/北向资金/市场融资)、
#       get_bkjy_value (板块交易数据)、
#       get_trading_dates (交易日历)、
#       get_sector_list / get_stock_list_in_sector (板块成份股)
# 数据源: TDX 财务数据系统
#
# 重要发现:
# 1. 字段名必须不带前导零: GP3(正确) vs GP03(错误), BK5(正确) vs BK05(错误)
# 2. get_gpjy_value/get_scjy_value 需要先在客户端下载股票数据包
# 3. 返回格式可能是 [['val1','val2']] 或 [{'Date':..,'Value':[...]}]
# 4. 值为 '--' 表示该日期无数据

from config import *
from datetime import datetime, timedelta


def _safe_float(val):
    """安全转换浮点数，处理 '--' 等无效值"""
    if val is None or val == '--' or val == '':
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _extract_values(field_data):
    """从字段数据中提取值列表。
    TDX 返回格式可能是:
      - [{'Date': '20250102', 'Value': ['141405.89', '11113.00']}]  (时间范围)
      - [['10.00', '24.00']]  (时间范围，简化格式)
      - ['--', '--']  (by_date 接口)
    返回: (values_list, record_count) 或 (None, 0)
    """
    if field_data is None:
        return None, 0
    if isinstance(field_data, list) and len(field_data) > 0:
        first = field_data[0]
        if isinstance(first, dict) and 'Value' in first:
            # 格式: [{'Date': ..., 'Value': [...]}]
            return first['Value'], len(field_data)
        elif isinstance(first, list):
            # 格式: [['val1', 'val2']]
            return first, len(field_data)
        elif isinstance(first, str):
            # 格式: ['val1', 'val2'] (by_date 接口)
            return field_data, 1
    return None, 0


def test_tdx_gpjy_value(tq, code, label):
    """TDX 股票交易数据 (融资融券/陆股通/大宗交易)"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 股票交易数据 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"tdx_gpjy_{code}")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    if not hasattr(tq, 'get_gpjy_value'):
        r.warn("get_gpjy_value 不可用，跳过")
        return r

    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')

    # 重要: 字段名不带前导零 (GP3 而非 GP03)
    fields = ['GP3', 'GP6', 'GP15', 'GP16', 'GP21']
    field_names = {
        'GP3': '融资融券', 'GP6': '陆股通持股',
        'GP15': '涨跌停', 'GP16': '总市值', 'GP21': '股息率'
    }

    try:
        result = tq.get_gpjy_value(
            stock_list=[tdx_code],
            field_list=fields,
            start_time=start_date,
            end_time=end_date
        )
        r.check("get_gpjy_value 调用成功", result is not None,
                f"返回类型: {type(result).__name__}")
    except Exception as e:
        r.check("get_gpjy_value 调用成功", False, str(e))
        return r

    if not result:
        return r

    has_stock = tdx_code in result
    r.check(f"包含股票 {tdx_code}", has_stock)

    if not has_stock:
        return r

    data = result[tdx_code]

    # 数据可能为 None (需要在客户端下载股票数据包)
    if data is None:
        r.warn("股票交易数据为 None (可能需要在客户端下载股票数据包)",
               "文档说明: 需要先在客户端中下载股票数据包")
        # 改用 by_date 接口验证 API 可用性
        if hasattr(tq, 'get_gpjy_value_by_date'):
            try:
                result_bd = tq.get_gpjy_value_by_date(
                    stock_list=[tdx_code],
                    field_list=fields,
                    year=0, mmdd=0
                )
                if result_bd and tdx_code in result_bd:
                    data_bd = result_bd[tdx_code]
                    if isinstance(data_bd, dict) and len(data_bd) > 0:
                        r.check("get_gpjy_value_by_date 可用", True,
                                f"字段: {list(data_bd.keys())}")
                        # 检查是否有有效数据 (非 '--')
                        has_real = False
                        for fn, vals in data_bd.items():
                            if isinstance(vals, list):
                                for v in vals:
                                    if v != '--' and _safe_float(v) is not None:
                                        has_real = True
                                        break
                        if has_real:
                            r.check("by_date 有有效数据", True)
                        else:
                            r.warn("by_date 数据全为 '--' (数据包未下载)")
                    else:
                        r.warn("by_date 返回空数据")
                else:
                    r.warn("by_date 无结果")
            except Exception as e:
                r.warn(f"by_date 调用失败: {e}")
        return r

    if not isinstance(data, dict):
        r.warn(f"返回数据格式异常 (type={type(data).__name__})")
        return r

    # 有数据时验证每个字段
    found_fields = 0
    for fn, name in field_names.items():
        field_data = data.get(fn)
        values, count = _extract_values(field_data)
        has_data = values is not None and len(values) > 0
        r.check(f"{name} ({fn}) 有数据", has_data,
                f"记录数: {count}" if has_data else "无数据")
        if has_data:
            found_fields += 1
            # 验证值可解析
            valid_vals = [v for v in values if _safe_float(v) is not None]
            r.check(f"{name} 值可解析", len(valid_vals) > 0,
                    f"有效值: {len(valid_vals)}/{len(values)}")

    r.check("至少 1 个字段有数据", found_fields > 0, f"有数据字段: {found_fields}/{len(field_names)}")

    return r


def test_tdx_gpjy_by_date(tq, code, label):
    """TDX 指定日期股票交易数据"""
    print("\n" + "=" * 60)
    print(f"[Test] TDX 指定日期交易数据 - {label} ({code})")
    print("=" * 60)
    r = TestResult(f"tdx_gpjy_date_{code}")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    if not hasattr(tq, 'get_gpjy_value_by_date'):
        r.warn("get_gpjy_value_by_date 不可用，跳过")
        return r

    tdx_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
    # 不带前导零
    fields = ['GP3', 'GP6', 'GP16']

    try:
        # year=0, mmdd=0 返回最新
        result = tq.get_gpjy_value_by_date(
            stock_list=[tdx_code],
            field_list=fields,
            year=0, mmdd=0
        )
        r.check("get_gpjy_value_by_date 调用成功",
                result is not None and tdx_code in result)
    except Exception as e:
        r.check("get_gpjy_value_by_date 调用成功", False, str(e))
        return r

    if not result or tdx_code not in result:
        return r

    data = result[tdx_code]
    if not data or not isinstance(data, dict):
        r.warn("返回数据为空或格式异常")
        return r

    r.check("返回字段数 > 0", len(data) > 0, f"字段: {list(data.keys())}")

    # by_date 返回格式: {'GP16': ['val1', 'val2'], ...}
    has_real_data = False
    for fn in fields:
        val = data.get(fn)
        if isinstance(val, list) and len(val) > 0:
            r.check(f"{fn} 有返回值", True, f"值: {val}")
            # 检查是否有非 '--' 的有效值
            for v in val:
                if v != '--' and _safe_float(v) is not None:
                    has_real_data = True
                    break
        else:
            r.warn(f"{fn} 无数据")

    if has_real_data:
        r.check("有有效数值 (非 '--')", True)
    else:
        r.warn("所有值均为 '--' (数据包可能未下载)")

    return r


def test_tdx_scjy_value(tq):
    """TDX 市场交易数据 (涨跌停/北向资金/融资融券)"""
    print("\n" + "=" * 60)
    print("[Test] TDX 市场交易数据")
    print("=" * 60)
    r = TestResult("tdx_scjy")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    if not hasattr(tq, 'get_scjy_value'):
        r.warn("get_scjy_value 不可用，跳过")
        return r

    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')

    # 不带前导零
    fields = ['SC1', 'SC2', 'SC3', 'SC4', 'SC20', 'SC31']
    field_names = {
        'SC1': '融资融券余额', 'SC2': '陆股通流入',
        'SC3': '涨停股个数', 'SC4': '跌停股个数',
        'SC20': '陆股通净买入', 'SC31': '涨跌家数'
    }

    # 先尝试时间范围查询
    try:
        result = tq.get_scjy_value(
            field_list=fields,
            start_time=start_date,
            end_time=end_date
        )
        r.check("get_scjy_value 调用成功", True)
    except Exception as e:
        r.check("get_scjy_value 调用成功", False, str(e))
        return r

    if result is not None and isinstance(result, dict) and len(result) > 0:
        # 时间范围查询有数据
        r.check("时间范围查询有数据", True, f"字段: {list(result.keys())}")
        for fn, name in field_names.items():
            field_data = result.get(fn)
            values, count = _extract_values(field_data)
            has_data = values is not None and len(values) > 0
            r.check(f"{name} ({fn}) 有数据", has_data,
                    f"记录数: {count}" if has_data else "无数据")
    else:
        # 时间范围查询无数据，尝试 by_date
        r.warn("时间范围查询返回 None (可能需要下载数据包)")

        if hasattr(tq, 'get_scjy_value_by_date'):
            try:
                result_bd = tq.get_scjy_value_by_date(
                    field_list=fields,
                    year=0, mmdd=0
                )
                if result_bd and isinstance(result_bd, dict):
                    r.check("get_scjy_value_by_date 可用", True,
                            f"字段: {list(result_bd.keys())}")
                    has_real = False
                    for fn, vals in result_bd.items():
                        if isinstance(vals, list):
                            for v in vals:
                                if v != '--' and _safe_float(v) is not None:
                                    has_real = True
                                    break
                    if has_real:
                        r.check("by_date 有有效数据", True)
                    else:
                        r.warn("by_date 数据全为 '--' (数据包未下载)")
                else:
                    r.warn("by_date 无结果")
            except Exception as e:
                r.warn(f"by_date 调用失败: {e}")

    return r


def test_tdx_bkjy_value(tq):
    """TDX 板块交易数据"""
    print("\n" + "=" * 60)
    print("[Test] TDX 板块交易数据")
    print("=" * 60)
    r = TestResult("tdx_bkjy")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    if not hasattr(tq, 'get_bkjy_value'):
        r.warn("get_bkjy_value 不可用，跳过")
        return r

    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')

    # 白酒板块，不带前导零
    block_code = '880660.SH'
    # BK9=涨跌数, BK12=涨停数, BK13=跌停数 已确认有数据
    # BK5=市盈率, BK6=市净率, BK10=总市值 可能需要数据包
    fields = ['BK5', 'BK6', 'BK9', 'BK10', 'BK12', 'BK13']
    field_names = {
        'BK5': '市盈率TTM', 'BK6': '市净率MRQ',
        'BK9': '涨跌数', 'BK10': '板块总市值',
        'BK12': '涨停数', 'BK13': '跌停数'
    }

    try:
        result = tq.get_bkjy_value(
            stock_list=[block_code],
            field_list=fields,
            start_time=start_date,
            end_time=end_date
        )
        r.check("get_bkjy_value 调用成功",
                result is not None and block_code in result)
    except Exception as e:
        r.check("get_bkjy_value 调用成功", False, str(e))
        return r

    if not result or block_code not in result:
        return r

    data = result[block_code]
    if not data or not isinstance(data, dict):
        r.warn("板块数据为空或格式异常")
        return r

    r.check("返回字段数 > 0", len(data) > 0, f"字段: {list(data.keys())}")

    found_fields = 0
    for fn, name in field_names.items():
        field_data = data.get(fn)
        values, count = _extract_values(field_data)
        has_data = values is not None and len(values) > 0
        if has_data:
            found_fields += 1
            r.check(f"{name} ({fn}) 有数据", True, f"值: {values}")
            # 验证值可解析
            valid_vals = [v for v in values if _safe_float(v) is not None]
            r.check(f"{name} 值可解析", len(valid_vals) > 0,
                    f"有效: {len(valid_vals)}/{len(values)}")
        else:
            r.warn(f"{name} ({fn}) 无数据 (可能需要下载数据包)")

    r.check("至少 2 个字段有数据", found_fields >= 2,
            f"有数据字段: {found_fields}/{len(field_names)}")

    # 涨跌数验证 (BK9 已确认有数据)
    bk9_data = data.get('BK9')
    bk9_vals, _ = _extract_values(bk9_data)
    if bk9_vals and len(bk9_vals) >= 2:
        up = _safe_float(bk9_vals[0])
        down = _safe_float(bk9_vals[1])
        if up is not None and down is not None:
            r.check("涨跌数 >= 0", up >= 0 and down >= 0,
                    f"上涨: {up}, 下跌: {down}")

    return r


def test_tdx_bkjy_by_date(tq):
    """TDX 指定日期板块交易数据"""
    print("\n" + "=" * 60)
    print("[Test] TDX 指定日期板块交易数据")
    print("=" * 60)
    r = TestResult("tdx_bkjy_date")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    if not hasattr(tq, 'get_bkjy_value_by_date'):
        r.warn("get_bkjy_value_by_date 不可用，跳过")
        return r

    block_code = '880660.SH'
    fields = ['BK5', 'BK6', 'BK9', 'BK10']

    try:
        result = tq.get_bkjy_value_by_date(
            stock_list=[block_code],
            field_list=fields,
            year=0, mmdd=0
        )
        r.check("get_bkjy_value_by_date 调用成功",
                result is not None and block_code in result)
    except Exception as e:
        r.check("get_bkjy_value_by_date 调用成功", False, str(e))
        return r

    if not result or block_code not in result:
        return r

    data = result[block_code]
    if not isinstance(data, dict) or len(data) == 0:
        r.warn("返回数据为空")
        return r

    r.check("返回字段数 > 0", len(data) > 0, f"字段: {list(data.keys())}")

    has_real = False
    for fn, vals in data.items():
        if isinstance(vals, list):
            for v in vals:
                if v != '--' and _safe_float(v) is not None:
                    has_real = True
                    break

    if has_real:
        r.check("有有效数值 (非 '--')", True)
    else:
        r.warn("所有值均为 '--' (数据包可能未下载)")

    return r


def test_tdx_trading_dates(tq):
    """TDX 交易日历"""
    print("\n" + "=" * 60)
    print("[Test] TDX 交易日历")
    print("=" * 60)
    r = TestResult("tdx_trading_dates")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    # 获取最近10个交易日
    try:
        dates = tq.get_trading_dates(
            market='SH', start_time='20250101', end_time='', count=10
        )
        r.check("get_trading_dates 成功", dates is not None and len(dates) > 0)
    except Exception as e:
        r.check("get_trading_dates 成功", False, str(e))
        return r

    if not dates:
        return r

    r.check("返回 10 个交易日", len(dates) == 10, f"实际: {len(dates)}")

    # 日期格式验证 (YYYYMMDD)
    valid_format = all(len(str(d)) == 8 and str(d).isdigit() for d in dates)
    r.check("日期格式正确 (YYYYMMDD)", valid_format,
            f"示例: {dates[:3]}")

    # 日期递增
    sorted_dates = sorted(dates)
    r.check("日期递增排列", dates == sorted_dates)

    # 不含周末
    import datetime as dt_mod
    weekend_count = 0
    for d in dates:
        ds = str(d)
        try:
            date_obj = dt_mod.datetime.strptime(ds, '%Y%m%d')
            if date_obj.weekday() >= 5:
                weekend_count += 1
        except ValueError:
            pass
    r.check("不含周末", weekend_count == 0, f"周末数: {weekend_count}")

    # 获取指定范围
    try:
        range_dates = tq.get_trading_dates(
            market='SH', start_time='20250101', end_time='20250131'
        )
        r.check("范围查询成功", range_dates is not None and len(range_dates) > 0,
                f"2025年1月交易日: {len(range_dates) if range_dates else 0}")
        if range_dates:
            all_in_range = all(20250101 <= int(d) <= 20250131 for d in range_dates)
            r.check("日期在指定范围内", all_in_range)
    except Exception as e:
        r.check("范围查询成功", False, str(e))

    return r


def test_tdx_sector_list(tq):
    """TDX 板块列表与成份股"""
    print("\n" + "=" * 60)
    print("[Test] TDX 板块列表与成份股")
    print("=" * 60)
    r = TestResult("tdx_sector")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    # 获取板块列表
    try:
        sectors = tq.get_sector_list()
        r.check("get_sector_list 成功", sectors is not None and len(sectors) > 0,
                f"板块数: {len(sectors) if sectors else 0}")
    except Exception as e:
        r.check("get_sector_list 成功", False, str(e))
        return r

    if not sectors:
        return r

    r.check("板块数量 > 50", len(sectors) > 50, f"实际: {len(sectors)}")

    # 板块代码格式
    valid_codes = sum(1 for s in sectors if '.' in str(s))
    r.check("板块代码含市场后缀", valid_codes == len(sectors),
            f"有效: {valid_codes}/{len(sectors)}")

    # 获取成份股 (沪深300)
    try:
        hs300 = tq.get_stock_list(market='23')
        r.check("沪深300成份股获取成功", hs300 is not None and len(hs300) > 0,
                f"成份股数: {len(hs300) if hs300 else 0}")
        if hs300:
            r.check("沪深300成份股 >= 200", len(hs300) >= 200,
                    f"实际: {len(hs300)}")
            has_mt = any('600519' in str(s) for s in hs300)
            r.check("茅台在沪深300中", has_mt)
    except Exception as e:
        r.check("沪深300成份股获取成功", False, str(e))

    # 获取板块成份股
    if sectors:
        test_block = sectors[0]
        try:
            stocks = tq.get_stock_list_in_sector(test_block)
            r.check(f"板块 {test_block} 成份股获取成功",
                    stocks is not None and len(stocks) > 0,
                    f"成份股数: {len(stocks) if stocks else 0}")
        except Exception as e:
            r.check(f"板块成份股获取成功", False, str(e))

    # 获取全部A股
    try:
        all_a = tq.get_stock_list(market='5')
        r.check("全部A股获取成功", all_a is not None and len(all_a) > 0,
                f"A股数: {len(all_a) if all_a else 0}")
        if all_a:
            r.check("A股数量 > 3000", len(all_a) > 3000, f"实际: {len(all_a)}")
    except Exception as e:
        r.check("全部A股获取成功", False, str(e))

    # 获取行业板块
    try:
        industries = tq.get_stock_list(market='11')
        r.check("行业板块获取成功", industries is not None and len(industries) > 0,
                f"行业数: {len(industries) if industries else 0}")
    except Exception as e:
        r.check("行业板块获取成功", False, str(e))

    return r


def test_tdx_stock_list_types(tq):
    """TDX 各类股票列表"""
    print("\n" + "=" * 60)
    print("[Test] TDX 各类股票列表")
    print("=" * 60)
    r = TestResult("tdx_stock_lists")

    if tq is None:
        r.check("TDX 可用", False, "TDX 未初始化")
        return r

    market_types = {
        '5': ('全部A股', 3000),
        '23': ('沪深300', 200),
        '24': ('中证500', 400),
        '51': ('创业板', 500),
        '52': ('科创板', 100),
        '12': ('概念板块', 10),
        '32': ('可转债', 100),
    }

    for market, (name, min_count) in market_types.items():
        try:
            stocks = tq.get_stock_list(market=market)
            has_data = stocks is not None and len(stocks) > 0
            r.check(f"{name} (market={market}) 有数据", has_data,
                    f"数量: {len(stocks) if stocks else 0}")
            if has_data:
                r.check(f"{name} 数量 >= {min_count}", len(stocks) >= min_count,
                        f"实际: {len(stocks)}")
        except Exception as e:
            r.check(f"{name} 获取成功", False, str(e))

    return r


def main():
    print("#" * 60)
    print("#  数据质量测试 11: TDX 交易数据与市场数据质量")
    print("#  覆盖: 股票交易/市场交易/板块交易/交易日历/板块成份股")
    print("#" * 60)

    tq = init_tdx()

    results = []

    # 股票交易数据
    results.append(test_tdx_gpjy_value(tq, '600519', '贵州茅台'))
    results.append(test_tdx_gpjy_by_date(tq, '600519', '贵州茅台'))

    # 市场交易数据
    results.append(test_tdx_scjy_value(tq))

    # 板块交易数据
    results.append(test_tdx_bkjy_value(tq))
    results.append(test_tdx_bkjy_by_date(tq))

    # 交易日历
    results.append(test_tdx_trading_dates(tq))

    # 板块与成份股
    results.append(test_tdx_sector_list(tq))
    results.append(test_tdx_stock_list_types(tq))

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
